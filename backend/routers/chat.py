from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from dependencies import get_llm_client

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str


@router.post("", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    llm=Depends(get_llm_client),
) -> ChatResponse:
    """テキストメッセージを LLM に送り、応答を返す。会話履歴は保持される。"""
    try:
        reply: str = await asyncio.to_thread(llm.chat, req.message)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"LLM 推論エラー: {exc}") from exc
    return ChatResponse(reply=reply)


@router.delete("/history")
async def clear_history(llm=Depends(get_llm_client)) -> dict[str, str]:
    """会話履歴をリセットする。"""
    llm.clear_history()
    return {"status": "cleared"}
