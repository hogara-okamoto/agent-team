"""Web 検索エージェント

DuckDuckGo Search API を使用してオフラインで Web 検索を実行し、
LLM で結果を日本語要約して返す。

依存: duckduckgo-search >= 6.0
  pip install duckduckgo-search
"""
from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from dependencies import get_llm_client

router = APIRouter(prefix="/search", tags=["search"])


# ──────────────────────────────────────────────
# スキーマ
# ──────────────────────────────────────────────

class SearchRequest(BaseModel):
    query: str
    max_results: int = 5


class SearchResult(BaseModel):
    title: str
    body: str
    href: str


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]
    summary: str


# ──────────────────────────────────────────────
# 検索・要約ロジック
# ──────────────────────────────────────────────

def _do_search(query: str, max_results: int) -> list[dict]:
    """DuckDuckGo でテキスト検索する（同期関数、to_thread で呼ぶ）。"""
    try:
        from duckduckgo_search import DDGS  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "duckduckgo-search がインストールされていません。"
            " pip install duckduckgo-search を実行してください。"
        ) from exc
    with DDGS() as ddgs:
        return list(ddgs.text(query, max_results=max_results))


async def _summarize(query: str, results: list[dict], llm) -> str:
    """LLM で検索結果を日本語 3 文以内で要約する。"""
    if not results:
        return "検索結果が見つかりませんでした。"

    snippets = "\n".join(
        f"[{i + 1}] {r.get('title', '')}: {r.get('body', '')}"
        for i, r in enumerate(results[:5])
    )
    prompt = (
        f"「{query}」の Web 検索結果を日本語で 3 文以内に要約してください。\n\n"
        f"検索結果:\n{snippets}"
    )
    try:
        raw = await asyncio.to_thread(
            llm._client.chat,
            model=llm.model,
            messages=[
                {"role": "system", "content": "日本語だけで簡潔に答えてください。"},
                {"role": "user", "content": prompt},
            ],
            think=False,
        )
        return raw.message.content.strip()
    except Exception:
        # LLM 失敗時は先頭スニペットをそのまま返す
        r = results[0]
        return f"{r.get('title', '')}: {r.get('body', '')[:200]}"


# ──────────────────────────────────────────────
# エンドポイント
# ──────────────────────────────────────────────

@router.post("", response_model=SearchResponse)
async def web_search(
    req: SearchRequest,
    llm=Depends(get_llm_client),
) -> SearchResponse:
    """Web 検索を実行し、結果と LLM による日本語要約を返す。"""
    try:
        raw_results: list[dict] = await asyncio.to_thread(
            _do_search, req.query, req.max_results
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"検索エラー: {exc}") from exc

    results = [
        SearchResult(
            title=r.get("title", ""),
            body=r.get("body", ""),
            href=r.get("href", ""),
        )
        for r in raw_results
    ]

    summary = await _summarize(req.query, raw_results, llm)

    return SearchResponse(query=req.query, results=results, summary=summary)
