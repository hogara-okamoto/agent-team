from __future__ import annotations

import io
import json
import os
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Optional


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
