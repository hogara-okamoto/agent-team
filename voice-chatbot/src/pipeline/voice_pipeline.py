from __future__ import annotations

from src.audio.player import AudioPlayer
from src.audio.recorder import AudioRecorder
from src.config.settings import Settings
from src.llm.client import OllamaClient
from src.stt.transcriber import WhisperTranscriber
from src.tts.synthesizer import OpenJTalkSynthesizer, PiperSynthesizer

_EXIT_WORDS = {"quit", "exit", "終了", "おわり", "終わり", "やめて", "ストップ"}


class VoicePipeline:
    """STT → LLM → TTS の逐次パイプライン。"""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

        self.recorder = AudioRecorder(
            sample_rate=settings.audio.sample_rate,
            chunk_duration=settings.audio.chunk_duration,
            silence_threshold=settings.audio.silence_threshold,
            silence_duration=settings.audio.silence_duration,
            max_record_duration=settings.audio.max_record_duration,
        )
        self.player = AudioPlayer()
        self.transcriber = WhisperTranscriber(
            model_size=settings.stt.model,
            device=settings.stt.device,
            compute_type=settings.stt.compute_type,
            language=settings.stt.language,
            download_root=settings.stt.download_root,
        )
        self.llm = OllamaClient(
            model=settings.llm.model,
            base_url=settings.llm.base_url,
            system_prompt=settings.llm.system_prompt,
            keep_alive=settings.llm.keep_alive,
        )
        if settings.tts.engine == "openjtalk":
            self.tts = OpenJTalkSynthesizer(
                dict_dir=settings.tts.openjtalk_dict,
                voice_path=settings.tts.openjtalk_voice,
            )
        else:
            self.tts = PiperSynthesizer(
                model_path=settings.tts.model_path,
                speaker_id=settings.tts.speaker_id,
                length_scale=settings.tts.length_scale,
            )

    def run_once(self) -> tuple[str, str]:
        """1 ターンの会話を実行する。

        Returns:
            (user_text, assistant_text)。スキップ時は ("", "")。
        """
        # ── Step 1: 録音 ──────────────────────────────
        audio = self.recorder.record()
        if audio.size == 0:
            return ("", "")

        # ── Step 2: STT ───────────────────────────────
        print("[STT] 文字起こし中...")
        user_text = self.transcriber.transcribe(audio, self.settings.audio.sample_rate)
        if not user_text:
            print("[STT] 認識結果が空でした。")
            return ("", "")
        print(f"[You]  {user_text}")

        # ── Step 3: LLM ───────────────────────────────
        print("[LLM] 推論中...")
        assistant_text = self.llm.chat(user_text)
        print(f"[Bot]  {assistant_text}")

        # ── Step 4: TTS ───────────────────────────────
        print("[TTS] 音声合成中...")
        wav_bytes = self.tts.synthesize(assistant_text)

        # ── Step 5: 再生 ──────────────────────────────
        self.player.play_wav_bytes(wav_bytes)

        return (user_text, assistant_text)

    def run(self) -> None:
        """会話ループ。終了ワードまたは KeyboardInterrupt で停止。"""
        while True:
            user_text, _ = self.run_once()
            if user_text.strip().lower() in _EXIT_WORDS:
                print("終了します。")
                break
