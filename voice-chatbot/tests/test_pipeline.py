"""VoicePipeline のユニットテスト。"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.config.settings import Settings
from src.pipeline.voice_pipeline import VoicePipeline


@pytest.fixture
def pipeline():
    """全コンポーネントをモック化した VoicePipeline を返す。"""
    settings = Settings(
        stt={"model": "tiny", "device": "cpu", "compute_type": "int8"},
        tts={"model_path": "/dummy/model.onnx"},
    )
    with (
        patch("src.pipeline.voice_pipeline.AudioRecorder"),
        patch("src.pipeline.voice_pipeline.AudioPlayer"),
        patch("src.pipeline.voice_pipeline.WhisperTranscriber"),
        patch("src.pipeline.voice_pipeline.OllamaClient"),
        patch("src.pipeline.voice_pipeline.PiperSynthesizer"),
    ):
        p = VoicePipeline(settings)
        p.recorder = MagicMock()
        p.player = MagicMock()
        p.transcriber = MagicMock()
        p.llm = MagicMock()
        p.tts = MagicMock()
        yield p


def test_run_once_skips_empty_audio(pipeline: VoicePipeline):
    """録音結果が空配列の場合、STT 以降をスキップして ("", "") を返すこと。"""
    pipeline.recorder.record.return_value = np.array([], dtype="float32")

    user_text, assistant_text = pipeline.run_once()

    assert user_text == ""
    assert assistant_text == ""
    pipeline.transcriber.transcribe.assert_not_called()


def test_run_once_skips_empty_transcription(pipeline: VoicePipeline):
    """STT 結果が空文字の場合、LLM 以降をスキップすること。"""
    pipeline.recorder.record.return_value = np.ones(16000, dtype="float32")
    pipeline.transcriber.transcribe.return_value = ""

    user_text, assistant_text = pipeline.run_once()

    assert user_text == ""
    pipeline.llm.chat.assert_not_called()


def test_run_once_full_pipeline(pipeline: VoicePipeline):
    """正常フロー: STT → LLM → TTS → 再生 が全て呼ばれること。"""
    pipeline.recorder.record.return_value = np.ones(16000, dtype="float32")
    pipeline.transcriber.transcribe.return_value = "こんにちは"
    pipeline.llm.chat.return_value = "こんにちは！"
    pipeline.tts.synthesize.return_value = b"RIFF....WAVE"

    user_text, assistant_text = pipeline.run_once()

    assert user_text == "こんにちは"
    assert assistant_text == "こんにちは！"
    pipeline.llm.chat.assert_called_once_with("こんにちは")
    pipeline.tts.synthesize.assert_called_once_with("こんにちは！")
    pipeline.player.play_wav_bytes.assert_called_once()


def test_run_exits_on_exit_word(pipeline: VoicePipeline):
    """終了ワードで run() ループが止まること。"""
    pipeline.recorder.record.return_value = np.ones(16000, dtype="float32")
    pipeline.transcriber.transcribe.return_value = "終了"
    pipeline.llm.chat.return_value = "さようなら"
    pipeline.tts.synthesize.return_value = b"RIFF....WAVE"

    # run() が無限ループに入らず正常終了すること
    pipeline.run()

    assert pipeline.recorder.record.call_count == 1
