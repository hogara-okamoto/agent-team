"""TTS モジュールのユニットテスト。"""
from __future__ import annotations

import io
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.tts.synthesizer import PiperSynthesizer


def _make_dummy_wav() -> bytes:
    """テスト用の最小 WAV バイト列を生成する。"""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(22050)
        wf.writeframes(b"\x00" * 200)
    buf.seek(0)
    return buf.read()


@pytest.fixture
def synth(tmp_path: Path):
    model_file = tmp_path / "test.onnx"
    model_file.touch()
    (tmp_path / "test.onnx.json").touch()

    with patch("src.tts.synthesizer.PiperVoice.load") as mock_load:
        mock_voice = MagicMock()

        def fake_synthesize(text, wav_file, **kwargs):
            dummy = _make_dummy_wav()
            # wave.open でラップされた wav_file に書き込む
            with wave.open(io.BytesIO(dummy)) as src:
                wav_file.setnchannels(src.getnchannels())
                wav_file.setsampwidth(src.getsampwidth())
                wav_file.setframerate(src.getframerate())
                wav_file.writeframes(src.readframes(src.getnframes()))

        mock_voice.synthesize.side_effect = fake_synthesize
        mock_load.return_value = mock_voice

        yield PiperSynthesizer(str(model_file))


def test_synthesize_returns_bytes(synth: PiperSynthesizer):
    """synthesize() が bytes を返すこと。"""
    result = synth.synthesize("テスト音声")
    assert isinstance(result, bytes)
    assert len(result) > 0


def test_synthesize_returns_valid_wav(synth: PiperSynthesizer):
    """返り値が WAV ヘッダを持つこと。"""
    result = synth.synthesize("テスト")
    assert result[:4] == b"RIFF"
    assert result[8:12] == b"WAVE"


def test_model_not_found_raises_file_not_found():
    """存在しない .onnx パスで FileNotFoundError が発生すること。"""
    with pytest.raises(FileNotFoundError, match="TTS モデルが見つかりません"):
        PiperSynthesizer("/nonexistent/path/model.onnx")
