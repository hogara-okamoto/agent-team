"""チャット ルーター

通常会話に加え、メール送信 intent を検出した場合は
action: "send_email" と抽出パラメータを返す。
"""
from __future__ import annotations

import asyncio
import json
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from dependencies import get_llm_client

router = APIRouter(prefix="/chat", tags=["chat"])

# ──────────────────────────────────────────────
# intent 検出ロジック
# ──────────────────────────────────────────────

# メール送信 intent のキーワード
_EMAIL_KEYWORDS = [
    "メール", "mail", "Mail",
    "アポ", "アポイント",
    "送って", "送りたい", "送信して", "送ってほしい", "送ってください",
    "ミーティング", "打ち合わせ", "連絡して",
]

# 「〇〇さんに」「〇〇様に」「〇〇さんへ」パターンで宛先名を抽出する正規表現
# 1〜8文字の非区切り文字 + (さん|様|氏|くん) + (に|へ)
_RECIPIENT_RE = re.compile(r"([^\s、。！？\n]{1,8}?)(?:さん|様|氏|くん)(?:に|へ)")

# エージェント自身の名前など、宛先として除外する語
_SELF_NAMES: set[str] = {"岡本", "エージェント", "私", "僕", "俺", "自分"}

# JSON コードブロック除去用
_JSON_RE = re.compile(r"```json?\s*(.*?)\s*```", re.DOTALL)


def _has_email_keyword(text: str) -> bool:
    return any(kw in text for kw in _EMAIL_KEYWORDS)


def _extract_recipient_regex(text: str) -> Optional[str]:
    """「〇〇さんに」パターンで宛先名を確実に抽出する。"""
    for match in _RECIPIENT_RE.finditer(text):
        name = match.group(1).strip()
        if name and name not in _SELF_NAMES and len(name) >= 1:
            return name
    return None


async def _extract_params_llm(text: str, llm) -> Optional[dict]:
    """LLM で client_name / purpose / date_str を抽出する（LLM バックアップ用）。"""
    prompt = (
        f"次の発言からメール送信のパラメータを抽出してください。\n"
        f"発言: {text}\n\n"
        f"JSONのみ出力（意図なしの場合は null）:\n"
        f'{{"client_name":"名前","purpose":"用件(不明なら空)","date_str":"日時(不明なら空)"}}'
    )
    raw = await asyncio.to_thread(
        llm._client.chat,
        model=llm.model,
        messages=[
            {"role": "system", "content": "JSONまたは null のみ出力してください。"},
            {"role": "user", "content": prompt},
        ],
        think=False,
    )
    content = raw.message.content.strip()
    try:
        if content.lower() == "null":
            return None
        m = _JSON_RE.search(content)
        return json.loads(m.group(1) if m else content.strip("`").strip())
    except Exception:
        return None


async def _extract_email_params(text: str, llm) -> Optional[dict]:
    """メール送信パラメータを抽出する。
    Step1: 正規表現で宛先名を確実に取得。
    Step2: 正規表現で取れなかった場合のみ LLM で抽出（最大1回リトライ）。
    """
    # Step1: 正規表現で宛先名を取得（高速・確実）
    client_name = _extract_recipient_regex(text)

    if client_name:
        # 宛先が取れたら purpose / date_str は LLM に任せるが失敗してもデフォルト値を使う
        llm_result = await _extract_params_llm(text, llm)
        purpose = (llm_result or {}).get("purpose") or ""
        date_str = (llm_result or {}).get("date_str") or ""
        return {
            "client_name": client_name,
            "purpose": purpose or "ご連絡",
            "date_str": date_str or "近日中",
        }

    # Step2: 正規表現で取れなかった場合は LLM で抽出（1回リトライ付き）
    for _ in range(2):
        result = await _extract_params_llm(text, llm)
        if result and result.get("client_name", "").strip():
            result.setdefault("purpose", "ご連絡")
            result.setdefault("date_str", "近日中")
            if not result["purpose"]:
                result["purpose"] = "ご連絡"
            if not result["date_str"]:
                result["date_str"] = "近日中"
            return result

    return None


# ──────────────────────────────────────────────
# スキーマ
# ──────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str
    action: Optional[str] = None          # "send_email" | None
    action_params: Optional[dict] = None  # client_name / purpose / date_str


# ──────────────────────────────────────────────
# エンドポイント
# ──────────────────────────────────────────────

@router.post("", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    llm=Depends(get_llm_client),
) -> ChatResponse:
    """テキストメッセージを LLM に送り、応答を返す。
    メール送信 intent を検出した場合は action フィールドも返す。
    """
    action: Optional[str] = None
    action_params: Optional[dict] = None

    if _has_email_keyword(req.message):
        params = await _extract_email_params(req.message, llm)
        print(f"[chat] message={req.message!r}  params={params}")
        if params:
            action = "send_email"
            action_params = params

    try:
        reply: str = await asyncio.to_thread(llm.chat, req.message)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"LLM 推論エラー: {exc}") from exc

    return ChatResponse(reply=reply, action=action, action_params=action_params)


@router.delete("/history")
async def clear_history(llm=Depends(get_llm_client)) -> dict[str, str]:
    """会話履歴をリセットする。"""
    llm.clear_history()
    return {"status": "cleared"}
