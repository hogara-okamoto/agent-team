"""STT モジュールのユニットテスト。"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.stt.transcriber import WhisperTranscriber


@pytest.fixture
def transcriber():
    with patch("src.stt.transcriber.WhisperModel") as MockModel:
        MockModel.return_value = MagicMock()
        t = WhisperTranscriber(model_size="tiny", device="cpu", compute_type="int8")
        t._model = MockModel.return_value
        yield t


def test_transcribe_empty_audio_returns_empty(transcriber: WhisperTranscriber):
    """空配列を渡すと空文字列が返ること（モデルを呼ばない）。"""
    result = transcriber.transcribe(np.array([], dtype="float32"))
    assert result == ""
    transcriber._model.transcribe.assert_not_called()


def test_transcribe_returns_joined_segments(transcriber: WhisperTranscriber):
    """複数セグメントが空白で結合されること。"""
    seg1 = MagicMock()
    seg1.text = "こんにちは"
    seg2 = MagicMock()
    seg2.text = " 世界"
    transcriber._model.transcribe.return_value = ([seg1, seg2], MagicMock())

    audio = np.zeros(16000, dtype="float32")
    result = transcriber.transcribe(audio)

    assert "こんにちは" in result
    assert "世界" in result


def test_transcribe_strips_whitespace(transcriber: WhisperTranscriber):
    """前後の空白がトリミングされること。"""
    seg = MagicMock()
    seg.text = "  テスト  "
    transcriber._model.transcribe.return_value = ([seg], MagicMock())

    audio = np.zeros(16000, dtype="float32")
    result = transcriber.transcribe(audio)
    assert result == "テスト"


def test_unload_clears_model(transcriber: WhisperTranscriber):
    """unload() 後にモデルが None になること。"""
    transcriber.unload()
    assert transcriber._model is None
