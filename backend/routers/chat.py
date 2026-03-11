"""チャット ルーター

ユーザーメッセージをルートエージェントで処理する。
intent_classifier でメール送信・Web 検索などの専門エージェント intent を検出し、
通常会話は LLM にそのまま渡す。
"""
from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from dependencies import get_llm_client
from routers.intent_classifier import (
    INTENT_EMAIL,
    INTENT_WEB_SEARCH,
    classify_intent,
)

router = APIRouter(prefix="/chat", tags=["chat"])


# ──────────────────────────────────────────────
# スキーマ
# ──────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str
    action: Optional[str] = None          # "send_email" | "web_search" | None
    action_params: Optional[dict] = None  # intent に応じたパラメータ


# ──────────────────────────────────────────────
# エンドポイント
# ──────────────────────────────────────────────

@router.post("", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    llm=Depends(get_llm_client),
) -> ChatResponse:
    """テキストメッセージをルートエージェントで処理する。

    - メール送信 intent → action: "send_email" + action_params
    - Web 検索 intent   → action: "web_search"  + action_params: {query}
    - 通常会話          → action: None（LLM が直接回答）
    """
    intent, params = await classify_intent(req.message, llm)
    print(f"[chat] message={req.message!r}  intent={intent}  params={params}")

    try:
        reply: str = await asyncio.to_thread(llm.chat, req.message)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"LLM 推論エラー: {exc}") from exc

    action: Optional[str] = None
    action_params: Optional[dict] = None

    if intent == INTENT_EMAIL and params:
        action = INTENT_EMAIL
        action_params = params
    elif intent == INTENT_WEB_SEARCH and params:
        action = INTENT_WEB_SEARCH
        action_params = params

    return ChatResponse(reply=reply, action=action, action_params=action_params)


@router.delete("/history")
async def clear_history(llm=Depends(get_llm_client)) -> dict[str, str]:
    """会話履歴をリセットする。"""
    llm.clear_history()
    return {"status": "cleared"}
