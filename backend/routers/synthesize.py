from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from dependencies import get_tts_synthesizer

router = APIRouter(prefix="/synthesize", tags=["synthesize"])


class SynthesizeRequest(BaseModel):
    text: str


@router.post("", response_class=Response)
async def synthesize(
    req: SynthesizeRequest,
    tts=Depends(get_tts_synthesizer),
) -> Response:
    """テキストを音声合成して WAV バイト列を返す。"""
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="テキストが空です")

    try:
        wav_bytes: bytes = await asyncio.to_thread(tts.synthesize, req.text)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"TTS 合成エラー: {exc}") from exc
    return Response(content=wav_bytes, media_type="audio/wav")
