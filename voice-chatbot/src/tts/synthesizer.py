from __future__ import annotations

import array
import io
import json
import os
import re
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Optional

# open_jtalk が「文末」と認識する句読点
_SENTENCE_END = frozenset('。！？!?')


def _strip_markdown(text: str) -> str:
    """TTS に渡す前に Markdown 記法を除去する。
    **bold**, *italic*, # 見出し, 番号リスト, コードブロック等を自然なテキストに変換する。
    """
    # コードブロック（```...```）を除去
    text = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
    # インラインコード（`code`）を除去
    text = re.sub(r'`[^`]+`', '', text)
    # 見出し（## 見出し → 見出し）
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    # bold/italic（**text** / *text* / __text__ / _text_）
    text = re.sub(r'\*{1,3}([^*]+)\*{1,3}', r'\1', text)
    text = re.sub(r'_{1,2}([^_]+)_{1,2}', r'\1', text)
    # 番号付きリスト（1. 2. など → そのまま残すが行頭の番号は除去）
    text = re.sub(r'^\d+\.\s+', '', text, flags=re.MULTILINE)
    # 箇条書き（- / * / + 行頭）
    text = re.sub(r'^[-*+]\s+', '', text, flags=re.MULTILINE)
    # リンク（[text](url) → text）
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    # 水平線
    text = re.sub(r'^[-*_]{3,}$', '', text, flags=re.MULTILINE)
    # 連続する空白・改行を整理
    text = re.sub(r'\n{2,}', '。', text)
    text = re.sub(r'[ \t]+', ' ', text)
    return text.strip()


_BREAK_RE = re.compile(r'(?<=[。！？!?\n、,をにがでもやからのでけど])')
_MAX_CHARS = 20  # これを超えると open_jtalk の prosody が崩れやすい


def _split_sentences(text: str) -> list[str]:
    """日本語テキストを open_jtalk が自然に読める長さに分割する。

    句読点・助詞・読点で分割後、MAX_CHARS 以下になるよう貪欲に結合する。
    長文をそのまま渡すと HTS モデルが後半の韻律を崩すため。
    """
    raw = [p.strip() for p in _BREAK_RE.split(text) if p.strip()]

    result: list[str] = []
    current = ""
    for part in raw:
        candidate = current + part if current else part
        if len(candidate) <= _MAX_CHARS:
            current = candidate
        else:
            if current:
                result.append(current)
            current = part  # 単独で超える場合はそのまま（仕方なし）
    if current:
        result.append(current)
    return result


def _ensure_sentence_end(text: str) -> str:
    """open_jtalk が自然な文末イントネーションを生成できるよう、
    句読点がない場合は「。」を補完する。
    補完しないと最後の音素が引き延ばされて不自然になる。"""
    return text if text[-1] in _SENTENCE_END else text + '。'


def _trim_trailing_silence(wav_bytes: bytes, threshold: int = 300, padding_ms: int = 120) -> bytes:
    """WAV 末尾の無音・引き延ばし音をトリムする。
    threshold : 無音とみなす int16 絶対値（0-32767）
    padding_ms: トリム後に残す余白（ミリ秒）
    """
    with wave.open(io.BytesIO(wav_bytes), "rb") as w:
        params = w.getparams()
        frames = w.readframes(w.getnframes())

    samples = array.array('h', frames)
    n = len(samples)

    # 末尾から threshold を超える最後のサンプル位置を探す
    last_active = n - 1
    while last_active > 0 and abs(samples[last_active]) <= threshold:
        last_active -= 1

    padding = int(params.framerate * padding_ms / 1000)
    end = min(last_active + padding, n)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as out:
        out.setparams(params)
        out.writeframes(samples[:end].tobytes())
    buf.seek(0)
    return buf.read()


def _concat_wavs(wav_bytes_list: list[bytes]) -> bytes:
    """複数の WAV バイト列を1つに結合する。"""
    if len(wav_bytes_list) == 1:
        return wav_bytes_list[0]
    all_frames = b""
    params = None
    for wav_bytes in wav_bytes_list:
        with wave.open(io.BytesIO(wav_bytes), "rb") as w:
            if params is None:
                params = w.getparams()
            all_frames += w.readframes(w.getnframes())
    buf = io.BytesIO()
    with wave.open(buf, "wb") as out:
        out.setparams(params)
        out.writeframes(all_frames)
    buf.seek(0)
    return buf.read()


# piper C++ バイナリのデフォルト配置場所（フラット構造）
# 構造: models/piper-bin/piper, models/piper-bin/*.so, models/piper-bin/espeak-ng-data/
_BIN_DIR = Path(__file__).parent.parent.parent / "models" / "piper-bin"


class OpenJTalkSynthesizer:
    """open_jtalk コマンド経由の日本語 TTS。

    piper バイナリが OpenJTalk 非対応のため、システムの open_jtalk を使う。
    必要パッケージ: open-jtalk open-jtalk-mecab-naist-jdic hts-voice-nitech-jp-atr503-m001
    """

    def __init__(self, dict_dir: str, voice_path: str) -> None:
        self._dict_dir = dict_dir
        self._voice_path = voice_path

        if not Path(dict_dir).exists():
            raise FileNotFoundError(f"OpenJTalk 辞書が見つかりません: {dict_dir}")
        if not Path(voice_path).exists():
            raise FileNotFoundError(f"HTS ボイスが見つかりません: {voice_path}")

        print(f"[TTS] OpenJTalk モード: {Path(voice_path).name}")

    def synthesize(self, text: str) -> bytes:
        text = _strip_markdown(text)
        sentences = _split_sentences(text)
        if not sentences:
            sentences = [text]
        # 個別セグメントはトリムせず（英語混じりなど振幅が小さい文が無音化するため）
        # _ensure_sentence_end で「。」を補完することで末尾の伸びを抑制する
        wav_list = [self._synthesize_one(_ensure_sentence_end(s)) for s in sentences]
        # 最終結合 WAV の末尾無音だけをトリムする
        return _trim_trailing_silence(_concat_wavs(wav_list))

    def _synthesize_one(self, text: str) -> bytes:
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp_path = Path(tmp.name)
        tmp.close()

        cmd = [
            "open_jtalk",
            "-x", self._dict_dir,
            "-m", self._voice_path,
            "-ow", str(tmp_path),
        ]

        try:
            result = subprocess.run(
                cmd,
                input=text.encode("utf-8"),
                capture_output=True,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"open_jtalk エラー:\n{result.stderr.decode(errors='replace')}"
                )
            return tmp_path.read_bytes()
        finally:
            tmp_path.unlink(missing_ok=True)


class PiperSynthesizer:
    """piper-tts を使ったローカル TTS。ONNX モデルで CPU 動作。

    phoneme_type が "openjtalk" のモデルは Python piper-tts パッケージが
    未対応のため、models/piper-bin/piper バイナリ経由で合成する。
    """

    def __init__(
        self,
        model_path: str,
        speaker_id: Optional[int] = None,
        length_scale: float = 1.0,
    ) -> None:
        onnx_path = Path(model_path)
        config_path = Path(str(model_path) + ".json")

        if not onnx_path.exists():
            raise FileNotFoundError(
                f"TTS モデルが見つかりません: {onnx_path}\n"
                "models/tts/ に .onnx と .onnx.json を配置してください。\n"
                "ダウンロード: https://github.com/rhasspy/piper/releases"
            )

        self._model_path = str(onnx_path)
        self.speaker_id = speaker_id
        self.length_scale = length_scale

        # phoneme_type を JSON から読み取る
        phoneme_type = "espeak"
        if config_path.exists():
            with open(config_path, encoding="utf-8") as f:
                phoneme_type = json.load(f).get("phoneme_type", "espeak")

        self._use_binary = phoneme_type == "openjtalk"

        if self._use_binary:
            bin_path = _BIN_DIR / "piper"
            if not bin_path.exists():
                raise FileNotFoundError(
                    f"openjtalk モデルには piper バイナリが必要です: {bin_path}\n"
                    "models/piper-bin/ に piper バイナリと共有ライブラリを配置してください。"
                )
            self._bin_path = str(bin_path)
            self._lib_dir = str(_BIN_DIR)
            self._espeak_data = str(_BIN_DIR / "espeak-ng-data")
            print(f"[TTS] モデルをロード中: {onnx_path.name} (openjtalk/binary モード)")
        else:
            from piper.voice import PiperVoice

            print(f"[TTS] モデルをロード中: {onnx_path.name}")
            self._voice = PiperVoice.load(
                str(onnx_path),
                config_path=str(config_path) if config_path.exists() else None,
            )

        print("[TTS] モデルのロード完了")

    def synthesize(self, text: str) -> bytes:
        """テキストを WAV バイト列に変換する。

        Args:
            text: 読み上げるテキスト

        Returns:
            WAV 形式のバイト列
        """
        if self._use_binary:
            return self._synthesize_binary(text)

        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as wav_file:
            self._voice.synthesize(
                text,
                wav_file,
                speaker_id=self.speaker_id,
                length_scale=self.length_scale,
            )
        wav_buffer.seek(0)
        return wav_buffer.read()

    def _synthesize_binary(self, text: str) -> bytes:
        """piper C++ バイナリ経由で合成する（openjtalk モデル用）。"""
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp_path = Path(tmp.name)
        tmp.close()

        env = {
            **os.environ,
            "LD_LIBRARY_PATH": self._lib_dir,
            "ESPEAK_DATA_PATH": self._espeak_data,
        }
        cmd = [
            self._bin_path,
            "--model", self._model_path,
            "--output_file", str(tmp_path),
            "--length_scale", str(self.length_scale),
        ]
        if self.speaker_id is not None:
            cmd += ["--speaker", str(self.speaker_id)]

        try:
            result = subprocess.run(
                cmd,
                input=text.encode("utf-8"),
                capture_output=True,
                env=env,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"piper バイナリがエラーを返しました:\n{result.stderr.decode(errors='replace')}"
                )
            return tmp_path.read_bytes()
        finally:
            tmp_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# VOICEVOX
# ---------------------------------------------------------------------------

class VOICEVOXSynthesizer:
    """VOICEVOX Engine 経由の日本語 TTS（REST API）。

    事前に VOICEVOX Engine を起動しておく必要がある。
    GPU Docker:
        docker run --gpus all -p 50021:50021 voicevox/voicevox_engine:nvidia-latest
    CPU Docker:
        docker run -p 50021:50021 voicevox/voicevox_engine:cpu-ubuntu20.04-latest

    主なスピーカー ID:
        1=四国めたん, 3=ずんだもん, 8=春日部つむぎ, 13=青山龍星, 14=冥鳴ひまり
    """

    def __init__(self, base_url: str = "http://localhost:50021", speaker: int = 3) -> None:
        import urllib.request
        self._base_url = base_url.rstrip("/")
        self._speaker = speaker
        try:
            urllib.request.urlopen(f"{self._base_url}/version", timeout=5)
        except Exception as e:
            raise RuntimeError(
                f"VOICEVOX Engine に接続できません ({base_url})\n"
                f"Engine が起動しているか確認してください: {e}"
            )
        print(f"[TTS] VOICEVOX モード: speaker={speaker}, url={base_url}")

    def synthesize(self, text: str) -> bytes:
        import json
        import urllib.parse
        import urllib.request

        text = _strip_markdown(text).strip()
        if not text:
            return b""

        # Step 1: テキスト → 音声クエリ
        query_url = (
            f"{self._base_url}/audio_query"
            f"?text={urllib.parse.quote(text)}&speaker={self._speaker}"
        )
        req = urllib.request.Request(query_url, method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:
            query = json.loads(resp.read().decode("utf-8"))

        # Step 2: クエリ → WAV
        synth_url = f"{self._base_url}/synthesis?speaker={self._speaker}"
        data = json.dumps(query).encode("utf-8")
        req = urllib.request.Request(
            synth_url, data=data, method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            wav_bytes = resp.read()

        return _trim_trailing_silence(wav_bytes)


# ---------------------------------------------------------------------------
# Kokoro-82M
# ---------------------------------------------------------------------------

class KokoroSynthesizer:
    """Kokoro-82M を使ったローカル TTS（CPU 動作可・GPU 推奨）。

    インストール:
        pip install kokoro
        apt-get install espeak-ng   # 音素変換に必要

    主な日本語ボイス:
        jf_alpha, jf_kokoro, jf_gongitsune, jf_nezumi, jf_tebukuro  （女性）
        jm_kumo                                                        （男性）
    """

    _SAMPLE_RATE = 24000

    def __init__(self, voice: str = "jf_alpha", speed: float = 1.0, device: str = "cuda") -> None:
        try:
            from kokoro import KPipeline
        except ImportError as e:
            raise ImportError(
                "Kokoro が未インストールです。\n"
                "pip install kokoro && apt-get install -y espeak-ng を実行してください。"
            ) from e

        # CUDA が使えない場合は CPU にフォールバック
        try:
            import torch
            if device == "cuda" and not torch.cuda.is_available():
                device = "cpu"
        except ImportError:
            device = "cpu"

        print(f"[TTS] Kokoro モード: voice={voice}, speed={speed}, device={device}")
        self._pipeline = KPipeline(lang_code="j", device=device)
        self._voice = voice
        self._speed = speed
        print("[TTS] Kokoro ロード完了")

    def synthesize(self, text: str) -> bytes:
        import array as arr
        import numpy as np

        text = _strip_markdown(text).strip()
        if not text:
            return b""

        # Kokoro は長文も一括処理できるが、複数チャンクで返す場合があるので結合する
        all_samples: list = []
        for _, _, audio in self._pipeline(text, voice=self._voice, speed=self._speed):
            if audio is not None and len(audio) > 0:
                all_samples.append(audio)

        if not all_samples:
            return b""

        combined = np.concatenate(all_samples) if len(all_samples) > 1 else all_samples[0]

        # float32 → int16
        samples = arr.array(
            "h",
            (max(-32768, min(32767, int(s * 32767))) for s in combined),
        )
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(self._SAMPLE_RATE)
            w.writeframes(samples.tobytes())
        buf.seek(0)

        return _trim_trailing_silence(buf.read())
