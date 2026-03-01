from __future__ import annotations

import gc
import io
import tempfile
from pathlib import Path
from typing import Optional

import numpy as np
import soundfile as sf
from faster_whisper import WhisperModel


class WhisperTranscriber:
    """faster-whisper を使ったローカル STT。CUDA / CPU 両対応。"""

    def __init__(
        self,
        model_size: str = "small",
        device: str = "cuda",
        compute_type: str = "float16",
        language: str = "ja",
        download_root: Optional[str] = None,
    ) -> None:
        self.language = language
        print(f"[STT] モデルをロード中: {model_size} ({device}/{compute_type})")
        self._model = WhisperModel(
            model_size,
            device=device,
            compute_type=compute_type,
            download_root=download_root,
        )
        print("[STT] モデルのロード完了")

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        """音声配列をテキストに変換する。

        Args:
            audio: shape (N,) の float32 配列
            sample_rate: サンプリングレート

        Returns:
            認識テキスト。音声なし・エラー時は空文字列。
        """
        if audio.size == 0:
            return ""

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            sf.write(f.name, audio, sample_rate)
            tmp_path = Path(f.name)

        try:
            segments, _ = self._model.transcribe(
                str(tmp_path),
                language=self.language,
                beam_size=5,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 500},
            )
            text = " ".join(seg.text.strip() for seg in segments)
        finally:
            tmp_path.unlink(missing_ok=True)

        return text.strip()

    def unload(self) -> None:
        """モデルをアンロードして VRAM を解放する。"""
        del self._model
        self._model = None  # type: ignore[assignment]
        gc.collect()
