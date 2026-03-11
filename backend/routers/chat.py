"""チャット ルーター — ルートエージェント

intent_classifier で intent を判定し、専門エージェントへ振り分ける。

- send_email  → action パラメータを返す（フロント側でモーダル表示）
- web_search  → バックエンドで検索を実行し、結果を LLM コンテキストに注入して返答
- general     → LLM に直接渡す
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
    action: Optional[str] = None           # "send_email" | "web_search" | None
    action_params: Optional[dict] = None   # intent に応じたパラメータ


# ──────────────────────────────────────────────
# 検索ヘルパー（web_search.py の _do_search を再利用）
# ──────────────────────────────────────────────

def _do_search(query: str, max_results: int = 5) -> list[dict]:
    try:
        from ddgs import DDGS  # type: ignore
    except ImportError:
        try:
            from duckduckgo_search import DDGS  # type: ignore[no-redef]
        except ImportError:
            return []
    with DDGS() as ddgs:
        return list(ddgs.text(query, max_results=max_results))


# ──────────────────────────────────────────────
# エンドポイント
# ──────────────────────────────────────────────

@router.post("", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    llm=Depends(get_llm_client),
) -> ChatResponse:
    """テキストメッセージをルートエージェントで処理する。

    web_search intent の場合は検索を内部で実行し、
    検索結果を LLM コンテキストに注入してから返答を生成する。
    これにより LLM が検索結果を参照でき、フォローアップ質問にも対応できる。
    """
    intent, params = await classify_intent(req.message, llm)
    print(f"[chat] message={req.message!r}  intent={intent}  params={params}")

    # ── メール送信 ──────────────────────────────
    if intent == INTENT_EMAIL and params:
        try:
            reply: str = await asyncio.to_thread(llm.chat, req.message)
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"LLM 推論エラー: {exc}") from exc
        return ChatResponse(reply=reply, action=INTENT_EMAIL, action_params=params)

    # ── Web 検索 ────────────────────────────────
    if intent == INTENT_WEB_SEARCH and params:
        query: str = params["query"]

        # 検索を実行（失敗しても空リストで続行）
        try:
            raw_results: list[dict] = await asyncio.to_thread(_do_search, query, 5)
        except Exception as exc:
            print(f"[chat] search error: {exc}")
            raw_results = []

        # 検索結果をコンテキストとして LLM に注入
        if raw_results:
            snippets = "\n".join(
                f"[{i + 1}] {r.get('title', '')}: {r.get('body', '')}"
                for i, r in enumerate(raw_results[:5])
            )
            context_message = (
                f"{req.message}\n\n"
                f"[Web検索結果]\n{snippets}\n\n"
                f"上記の検索結果をもとに、日本語で簡潔に答えてください。"
            )
        else:
            context_message = req.message

        try:
            reply = await asyncio.to_thread(llm.chat, context_message)
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"LLM 推論エラー: {exc}") from exc

        # フロント表示用に結果リストも返す
        results_for_display = [
            {"title": r.get("title", ""), "body": r.get("body", ""), "href": r.get("href", "")}
            for r in raw_results
        ]
        return ChatResponse(
            reply=reply,
            action=INTENT_WEB_SEARCH,
            action_params={"query": query, "results": results_for_display},
        )

    # ── 通常会話 ────────────────────────────────
    try:
        reply = await asyncio.to_thread(llm.chat, req.message)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"LLM 推論エラー: {exc}") from exc

    return ChatResponse(reply=reply)


@router.delete("/history")
async def clear_history(llm=Depends(get_llm_client)) -> dict[str, str]:
    """会話履歴をリセットする。"""
    llm.clear_history()
    return {"status": "cleared"}
