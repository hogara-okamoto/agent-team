"""チャット ルーター — ルートエージェント

intent_classifier で intent を判定し、専門エージェントへ振り分ける。

- send_email  → action パラメータを返す（フロント側でモーダル表示）
- web_search  → バックエンドで検索を実行し、結果を LLM コンテキストに注入して返答
- general     → LLM に直接渡す
"""
from __future__ import annotations

import asyncio
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from dependencies import get_llm_client, get_wake_words
from routers.intent_classifier import (
    INTENT_EMAIL,
    INTENT_WEB_SEARCH,
    INTENT_CALENDAR,
    INTENT_YOUTUBE,
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
# 日付コンテキスト注入ヘルパー
# ──────────────────────────────────────────────

_WEEKDAY_JP = ["月曜日", "火曜日", "水曜日", "木曜日", "金曜日", "土曜日", "日曜日"]
_DATE_MENTION_RE = re.compile(
    r"(\d{4}[-/年]\d{1,2}[-/月]\d{1,2}日?|\d{1,2}月\d{1,2}日|\d{8})"
)


def _build_date_context(message: str) -> str:
    """メッセージ内の日付と今日の日付を正確に計算してコンテキスト文字列を返す。"""
    from datetime import date, datetime

    today = date.today()
    lines = [f"今日の日付: {today} ({_WEEKDAY_JP[today.weekday()]})"]

    for m in _DATE_MENTION_RE.finditer(message):
        raw = m.group(0)
        # パース試行
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y年%m月%d日", "%Y%m%d"):
            try:
                d = datetime.strptime(raw.replace("年", "-").replace("月", "-").replace("日", ""), fmt.replace("年","-").replace("月","-").replace("日","")).date()
                lines.append(f"{raw} → {d} ({_WEEKDAY_JP[d.weekday()]})")
                break
            except ValueError:
                continue
        else:
            # MM月DD日 形式
            mm = re.match(r"(\d{1,2})月(\d{1,2})日?$", raw)
            if mm:
                year = today.year
                try:
                    from datetime import date as _date
                    d = _date(year, int(mm.group(1)), int(mm.group(2)))
                    if d < today:
                        d = _date(year + 1, int(mm.group(1)), int(mm.group(2)))
                    lines.append(f"{raw} → {d} ({_WEEKDAY_JP[d.weekday()]})")
                except ValueError:
                    pass

    return "\n".join(lines)


def _needs_date_context(message: str) -> bool:
    """日付・曜日に関する質問かどうか判定する。"""
    DATE_QUERY_WORDS = ["何曜日", "曜日", "何日", "今日", "明日", "明後日", "今週", "来週", "日付", "今年", "何年"]
    return any(w in message for w in DATE_QUERY_WORDS) or bool(_DATE_MENTION_RE.search(message))


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
    # ウェイクワードをメッセージ先頭から除去（STT がウェイクワードを含む場合の対策）
    message = req.message
    for ww in get_wake_words():
        message = re.sub(rf"^{re.escape(ww)}[、,\s　]*", "", message).strip()

    intent, params = await classify_intent(message, llm)
    print(f"[chat] message={message!r}  intent={intent}  params={params}")

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

    # ── YouTube 再生 ─────────────────────────────
    if intent == INTENT_YOUTUBE and params:
        from routers.youtube_agent import search_youtube
        query: str = params["query"]

        url: Optional[str] = await asyncio.to_thread(search_youtube, query)
        if url:
            reply = f"「{query}」をYouTubeで再生します。"
        else:
            # API キー未設定または検索失敗時: フォールバック URL（検索結果ページ）
            import urllib.parse
            url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}"
            reply = f"「{query}」をYouTubeで検索します。"

        return ChatResponse(
            reply=reply,
            action=INTENT_YOUTUBE,
            action_params={"query": query, "url": url},
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
    # 日付・曜日に関する質問は正確な値をコンテキストに注入
    if _needs_date_context(message):
        date_ctx = _build_date_context(message)
        llm_message = f"{message}\n\n[日付情報（正確）]\n{date_ctx}\n\n上記の日付情報をもとに正確に答えてください。"
    else:
        llm_message = message

    try:
        reply = await asyncio.to_thread(llm.chat, llm_message)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"LLM 推論エラー: {exc}") from exc

    return ChatResponse(reply=reply)


@router.delete("/history")
async def clear_history(llm=Depends(get_llm_client)) -> dict[str, str]:
    """会話履歴をリセットする。"""
    llm.clear_history()
    return {"status": "cleared"}
