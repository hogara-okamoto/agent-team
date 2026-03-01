from __future__ import annotations

import asyncio
import io

import numpy as np
import soundfile as sf
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from dependencies import get_transcriber

router = APIRouter(prefix="/transcribe", tags=["transcribe"])


class TranscribeResponse(BaseModel):
    text: str


@router.post("", response_model=TranscribeResponse)
async def transcribe(
    file: UploadFile = File(...),
    transcriber=Depends(get_transcriber),
) -> TranscribeResponse:
    """音声ファイル（WAV）を受け取り、文字起こし結果を返す。"""
    audio_bytes = await file.read()

    try:
        audio, sample_rate = sf.read(io.BytesIO(audio_bytes), dtype="float32")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"音声ファイルの解析に失敗しました: {exc}")

    if audio.ndim > 1:
        audio = audio.mean(axis=1)  # ステレオ → モノラル

    text: str = await asyncio.to_thread(transcriber.transcribe, audio, sample_rate)
    return TranscribeResponse(text=text)
