"""
STT → LLM → TTS パイプライン スモークテスト
オーディオデバイスなしで動作確認できます。

使い方:
  python smoke_test.py                    # 全ステップをテスト（日本語音声を合成して STT へ）
  python smoke_test.py --wav path/to.wav  # 既存 WAV ファイルを STT 入力に使用
  python smoke_test.py --text "こんにちは" # STT をスキップして LLM → TTS のみテスト
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf

# プロジェクトルートから実行する前提
sys.path.insert(0, str(Path(__file__).parent))

from src.config.settings import Settings
from src.llm.client import OllamaClient
from src.stt.transcriber import WhisperTranscriber
from src.tts.synthesizer import PiperSynthesizer

OUTPUT_WAV = Path("output_response.wav")


def generate_silence(duration_sec: float = 1.0, sample_rate: int = 16000) -> np.ndarray:
    """テスト用の無音配列を生成する。"""
    return np.zeros(int(sample_rate * duration_sec), dtype=np.float32)


def test_llm(settings: Settings) -> str:
    """LLM 単体テスト。"""
    print("\n" + "=" * 50)
    print("  [Step 2] LLM テスト")
    print("=" * 50)
    llm = OllamaClient(
        model=settings.llm.model,
        base_url=settings.llm.base_url,
        system_prompt=settings.llm.system_prompt,
        keep_alive=settings.llm.keep_alive,
    )
    test_message = "「はい」と一言だけ日本語で答えてください。"
    print(f"[LLM] 入力: {test_message}")
    t0 = time.time()
    response = llm.chat(test_message)
    elapsed = time.time() - t0
    print(f"[LLM] 応答 ({elapsed:.1f}s): {response}")
    return response


def test_tts(settings: Settings, text: str) -> None:
    """TTS 単体テスト。WAV ファイルに保存する。"""
    print("\n" + "=" * 50)
    print("  [Step 3] TTS テスト")
    print("=" * 50)
    tts = PiperSynthesizer(
        model_path=settings.tts.model_path,
        speaker_id=settings.tts.speaker_id,
        length_scale=settings.tts.length_scale,
    )
    print(f"[TTS] 合成テキスト: {text[:60]}{'...' if len(text) > 60 else ''}")
    t0 = time.time()
    wav_bytes = tts.synthesize(text)
    elapsed = time.time() - t0
    OUTPUT_WAV.write_bytes(wav_bytes)
    print(f"[TTS] 完了 ({elapsed:.1f}s) → 保存先: {OUTPUT_WAV.resolve()}")
    print(f"[TTS] ファイルサイズ: {len(wav_bytes) / 1024:.1f} KB")


def test_stt(settings: Settings, wav_path: Path | None) -> str:
    """STT 単体テスト。wav_path が None のとき TTS で音声を生成して使う。"""
    print("\n" + "=" * 50)
    print("  [Step 1] STT テスト")
    print("=" * 50)

    if wav_path is None:
        # TTS で「こんにちは、テストです」を生成して STT に渡す
        print("[STT] テスト用音声を TTS で生成します...")
        tts = PiperSynthesizer(
            model_path=settings.tts.model_path,
            speaker_id=settings.tts.speaker_id,
            length_scale=settings.tts.length_scale,
        )
        wav_bytes = tts.synthesize("こんにちは、テストです。")
        tmp_wav = Path("/tmp/stt_input_test.wav")
        tmp_wav.write_bytes(wav_bytes)
        wav_path = tmp_wav
        print(f"[STT] 生成完了 → {wav_path}")

    audio, sample_rate = sf.read(str(wav_path), dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)  # ステレオ → モノラル

    print(f"[STT] 入力: {wav_path.name}  ({len(audio)/sample_rate:.1f}s, {sample_rate}Hz)")
    transcriber = WhisperTranscriber(
        model_size=settings.stt.model,
        device=settings.stt.device,
        compute_type=settings.stt.compute_type,
        language=settings.stt.language,
        download_root=settings.stt.download_root,
    )
    t0 = time.time()
    text = transcriber.transcribe(audio, sample_rate)
    elapsed = time.time() - t0
    print(f"[STT] 認識結果 ({elapsed:.1f}s): '{text}'")
    return text


def main() -> None:
    parser = argparse.ArgumentParser(description="voice-chatbot スモークテスト")
    parser.add_argument("--config", default="config.yaml", help="設定ファイルのパス")
    parser.add_argument("--wav", type=Path, default=None, help="STT 入力に使う WAV ファイル")
    parser.add_argument("--text", type=str, default=None, help="STT をスキップして直接 LLM に渡すテキスト")
    parser.add_argument("--skip-stt", action="store_true", help="STT ステップをスキップ")
    args = parser.parse_args()

    print("=" * 50)
    print("  voice-chatbot スモークテスト開始")
    print("=" * 50)

    settings = Settings.from_yaml(args.config)

    try:
        if args.text:
            # テキスト直接入力: LLM → TTS のみ
            print(f"\n[モード] テキスト直接入力: '{args.text}'")
            llm = OllamaClient(
                model=settings.llm.model,
                base_url=settings.llm.base_url,
                system_prompt=settings.llm.system_prompt,
                keep_alive=settings.llm.keep_alive,
            )
            print(f"[LLM] 入力: {args.text}")
            t0 = time.time()
            response = llm.chat(args.text)
            print(f"[LLM] 応答 ({time.time()-t0:.1f}s): {response}")
            test_tts(settings, response)

        elif args.skip_stt:
            # LLM → TTS のみ
            response = test_llm(settings)
            test_tts(settings, response)

        else:
            # 全ステップ: STT → LLM → TTS
            stt_text = test_stt(settings, args.wav)

            if stt_text:
                llm = OllamaClient(
                    model=settings.llm.model,
                    base_url=settings.llm.base_url,
                    system_prompt=settings.llm.system_prompt,
                    keep_alive=settings.llm.keep_alive,
                )
                print(f"\n[LLM] 入力: {stt_text}")
                t0 = time.time()
                response = llm.chat(stt_text)
                print(f"[LLM] 応答 ({time.time()-t0:.1f}s): {response}")
                test_tts(settings, response)
            else:
                print("[警告] STT 結果が空でした。--text オプションで直接テキストを渡してください。")

        print("\n" + "=" * 50)
        print("  全ステップ完了")
        print(f"  出力 WAV: {OUTPUT_WAV.resolve()}")
        print("=" * 50)

    except KeyboardInterrupt:
        print("\n中断しました。")
        sys.exit(0)


if __name__ == "__main__":
    main()
