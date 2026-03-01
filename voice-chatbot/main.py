import argparse
import sys
from pathlib import Path

from src.config.settings import Settings
from src.pipeline.voice_pipeline import VoicePipeline


def _check_audio_device() -> bool:
    """マイクデバイスが利用可能か確認する。"""
    try:
        import sounddevice as sd
        devices = sd.query_devices()
        # デフォルト入力デバイスが存在するか確認
        sd.query_devices(kind="input")
        return True
    except Exception:
        return False


def _run_text_input_mode(pipeline: VoicePipeline) -> None:
    """マイク不使用のテキスト入力フォールバックモード。

    STT をスキップし、キーボードで入力したテキストを LLM → TTS に渡す。
    TTS 出力は output_response.wav に保存する。
    """
    print("\n[フォールバック] テキスト入力モードで起動します。")
    print("  マイク/スピーカーが利用できないため、テキスト入力で動作します。")
    print("  TTS 出力は output_response.wav に保存されます。")
    print("  終了: 「終了」と入力するか Ctrl+C を押してください。\n")

    EXIT_WORDS = {"quit", "exit", "終了", "おわり", "終わり", "やめて", "ストップ"}

    while True:
        try:
            user_text = input("[You] ").strip()
        except EOFError:
            break

        if not user_text:
            continue
        if user_text.lower() in EXIT_WORDS:
            print("終了します。")
            break

        # LLM
        print("[LLM] 推論中...")
        assistant_text = pipeline.llm.chat(user_text)
        print(f"[Bot] {assistant_text}")

        # TTS → ファイル保存
        print("[TTS] 音声合成中...")
        wav_bytes = pipeline.tts.synthesize(assistant_text)
        out_path = Path("output_response.wav")
        out_path.write_bytes(wav_bytes)
        print(f"[TTS] 保存完了: {out_path.resolve()} ({len(wav_bytes) // 1024} KB)\n")


def _run_wav_input_mode(pipeline: VoicePipeline, wav_path: Path) -> None:
    """WAV ファイルを STT 入力とし、LLM → TTS を実行するモード。"""
    import numpy as np
    import soundfile as sf

    print(f"\n[WAV 入力モード] {wav_path}")
    audio, sample_rate = sf.read(str(wav_path), dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)

    print("[STT] 文字起こし中...")
    user_text = pipeline.transcriber.transcribe(audio, sample_rate)
    if not user_text:
        print("[STT] 認識結果が空でした。終了します。")
        return
    print(f"[You] {user_text}")

    print("[LLM] 推論中...")
    assistant_text = pipeline.llm.chat(user_text)
    print(f"[Bot] {assistant_text}")

    print("[TTS] 音声合成中...")
    wav_bytes = pipeline.tts.synthesize(assistant_text)
    out_path = Path("output_response.wav")
    out_path.write_bytes(wav_bytes)
    print(f"[TTS] 保存完了: {out_path.resolve()} ({len(wav_bytes) // 1024} KB)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ローカル完結 音声チャットボット (STT → LLM → TTS)"
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="設定ファイルのパス (デフォルト: config.yaml)",
    )
    parser.add_argument(
        "--wav",
        type=Path,
        default=None,
        help="WAV ファイルを STT 入力として使用する（マイク不使用）",
    )
    args = parser.parse_args()

    print("=" * 50)
    print("  ローカル音声チャットボット")
    print("  終了: Ctrl+C または「終了」と発話")
    print("=" * 50)

    settings = Settings.from_yaml(args.config)
    pipeline = VoicePipeline(settings)

    try:
        # --wav 指定時は WAV ファイル入力モード
        if args.wav is not None:
            if not args.wav.exists():
                print(f"[ERROR] WAV ファイルが見つかりません: {args.wav}", file=sys.stderr)
                sys.exit(1)
            _run_wav_input_mode(pipeline, args.wav)
            return

        # マイクデバイスの確認
        if not _check_audio_device():
            print("\n[警告] マイクデバイスが見つかりません。")
            print("  原因として以下が考えられます:")
            print("  - devcontainer / WSL2 でオーディオが無効")
            print("  - PortAudio ライブラリ未インストール")
            _run_text_input_mode(pipeline)
            return

        # 通常の音声会話モード
        pipeline.run()

    except KeyboardInterrupt:
        print("\n終了しました。")
        sys.exit(0)


if __name__ == "__main__":
    main()
