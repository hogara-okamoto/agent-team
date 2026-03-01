from __future__ import annotations

import io

import numpy as np
import sounddevice as sd
import soundfile as sf


class AudioPlayer:
    """音声再生クラス。WAV バイト列または numpy 配列を再生する。"""

    def play_wav_bytes(self, wav_bytes: bytes) -> None:
        """WAV バイト列を再生する。"""
        audio, samplerate = sf.read(io.BytesIO(wav_bytes), dtype="float32")
        sd.play(audio, samplerate)
        sd.wait()

    def play_array(self, audio: np.ndarray, samplerate: int) -> None:
        """numpy 配列を再生する。"""
        sd.play(audio, samplerate)
        sd.wait()
