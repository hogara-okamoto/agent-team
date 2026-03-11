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
    INTENT_CALENDAR,
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
# 検索ヘルパー
# Google Custom Search API が設定されていれば優先、なければ DuckDuckGo にフォールバック
# ──────────────────────────────────────────────

def _google_search(query: str, api_key: str, cx: str, max_results: int) -> list[dict]:
    """Google Custom Search JSON API で検索する。"""
    import httpx
    resp = httpx.get(
        "https://www.googleapis.com/customsearch/v1",
        params={
            "key": api_key,
            "cx": cx,
            "q": query,
            "num": min(max_results, 10),
            "lr": "lang_ja",
        },
        timeout=10,
    )
    resp.raise_for_status()
    items = resp.json().get("items", [])
    return [
        {"title": i.get("title", ""), "body": i.get("snippet", ""), "href": i.get("link", "")}
        for i in items
    ]


def _do_search(query: str, max_results: int = 5) -> list[dict]:
    """Google Custom Search 優先、未設定なら DuckDuckGo にフォールバック。"""
    import os
    api_key = os.getenv("GOOGLE_API_KEY", "")
    cx = os.getenv("GOOGLE_CX", "")

    if api_key and cx:
        print(f"[search] Google Custom Search: {query!r}")
        return _google_search(query, api_key, cx, max_results)

    # フォールバック: DuckDuckGo
    print(f"[search] DuckDuckGo (Google 未設定): {query!r}")
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

    # ── カレンダー ──────────────────────────────
    if intent == INTENT_CALENDAR and params:
        from routers.calendar_agent import get_events_text, add_event_from_text

        operation = params.get("operation", "list")

        if operation == "add":
            title = params.get("title", "予定")
            date_str = params.get("date", "")
            time_str = params.get("time", "")
            note = params.get("note", "")
            result_text = await asyncio.to_thread(
                add_event_from_text, title, date_str, time_str, note
            )
            return ChatResponse(
                reply=result_text,
                action=INTENT_CALENDAR,
                action_params={"operation": "add", "date": date_str, "title": title},
            )
        else:
            # list
            date_str = params.get("date", "")
            events_text = await asyncio.to_thread(get_events_text, date_str)
            # LLM に自然な文章で返答させる
            context_message = (
                f"{req.message}\n\n"
                f"[カレンダー情報]\n{events_text}\n\n"
                f"上記の情報をもとに、日本語で自然に答えてください。"
            )
            try:
                reply = await asyncio.to_thread(llm.chat, context_message)
            except Exception as exc:
                raise HTTPException(status_code=503, detail=f"LLM 推論エラー: {exc}") from exc
            return ChatResponse(
                reply=reply,
                action=INTENT_CALENDAR,
                action_params={"operation": "list", "date": date_str, "events_text": events_text},
            )

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
