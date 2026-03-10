"""ウェイクワード検出エンドポイント

POST /wakeword
    短い音声クリップを受け取り、Whisper で文字起こしを行い、
    設定されたウェイクワードが含まれているかを返す。
    フロントエンドの常時マイクモニタリングと組み合わせて使用する。
"""
from __future__ import annotations

import asyncio
import io

import soundfile as sf
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from dependencies import get_transcriber, get_wake_words

router = APIRouter(prefix="/wakeword", tags=["wakeword"])


class WakeWordResponse(BaseModel):
    detected: bool
    text: str


@router.post("", response_model=WakeWordResponse)
async def check_wakeword(
    file: UploadFile = File(...),
    transcriber=Depends(get_transcriber),
    wake_words: list[str] = Depends(get_wake_words),
) -> WakeWordResponse:
    """音声クリップにウェイクワードが含まれているか判定する。

    - 文字起こしは既存の Whisper モデルを使用（追加依存なし）
    - ウェイクワードは config.yaml の wake_word.words で設定
    """
    audio_bytes = await file.read()

    try:
        audio, sample_rate = sf.read(io.BytesIO(audio_bytes), dtype="float32")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"音声ファイルの解析に失敗しました: {exc}")

    if audio.ndim > 1:
        audio = audio.mean(axis=1)

    text: str = await asyncio.to_thread(transcriber.transcribe, audio, sample_rate)

    text_lower = text.lower()
    detected = any(w.lower() in text_lower for w in wake_words)

    return WakeWordResponse(detected=detected, text=text)
