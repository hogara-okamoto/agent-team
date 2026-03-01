from __future__ import annotations

import numpy as np
import sounddevice as sd


class AudioRecorder:
    """マイク録音クラス。無音検出（VAD）付きで発話区間を自動切り出し。"""

    def __init__(
        self,
        sample_rate: int = 16000,
        chunk_duration: float = 0.1,
        silence_threshold: float = 0.02,
        silence_duration: float = 1.5,
        max_record_duration: float = 30.0,
    ) -> None:
        self.sample_rate = sample_rate
        self.chunk_size = int(sample_rate * chunk_duration)
        self.silence_threshold = silence_threshold
        self.silence_frames = int(silence_duration / chunk_duration)
        self.max_frames = int(max_record_duration / chunk_duration)

    def _rms(self, audio: np.ndarray) -> float:
        return float(np.sqrt(np.mean(audio**2)))

    def record(self) -> np.ndarray:
        """発話が終わるまで録音し、音声データを返す。

        Returns:
            shape (N,) の float32 配列。無音のみの場合は空配列。
        """
        print("\n[録音] 話しかけてください...")

        frames: list[np.ndarray] = []
        silent_count = 0
        started = False

        with sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
        ) as stream:
            while len(frames) < self.max_frames:
                chunk, _ = stream.read(self.chunk_size)
                chunk_flat = chunk.flatten()
                rms = self._rms(chunk_flat)

                if rms > self.silence_threshold:
                    if not started:
                        print("[録音] 音声を検出しました...")
                        started = True
                    frames.append(chunk_flat)
                    silent_count = 0
                elif started:
                    frames.append(chunk_flat)
                    silent_count += 1
                    if silent_count >= self.silence_frames:
                        break

        if not frames:
            print("[録音] 音声が検出されませんでした。")
            return np.array([], dtype="float32")

        audio = np.concatenate(frames)
        print(f"[録音] 完了 ({len(audio) / self.sample_rate:.1f} 秒)")
        return audio
