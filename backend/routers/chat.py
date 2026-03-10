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

# メール送信 intent のキーワード（いずれか1つ以上含む場合に intent 判定を試みる）
_EMAIL_KEYWORDS = [
    "メール", "mail", "Mail",
    "アポ", "アポイント",
    "送って", "送りたい", "送信して", "送ってほしい", "送ってください",
    "ミーティング", "打ち合わせ", "連絡して",
]

_JSON_RE = re.compile(r"```json?\s*(.*?)\s*```", re.DOTALL)


def _has_email_keyword(text: str) -> bool:
    return any(kw in text for kw in _EMAIL_KEYWORDS)


async def _extract_email_params(text: str, llm) -> Optional[dict]:
    """LLM を使ってメール送信パラメータを抽出する。会話履歴には追加しない。
    client_name は必須。purpose・date_str が不明な場合はデフォルト値を使う。
    """
    prompt = (
        f"次のユーザー発言から、メールを送る相手の名前を抽出してください。\n"
        f"発言: {text}\n\n"
        f"メールを送る意図がある場合は以下のJSON形式で出力してください。\n"
        f"意図が全くない場合だけ null と出力してください。\n"
        f"purpose や date_str が不明な場合は空文字にしてください。\n\n"
        f'{{"client_name": "相手の名前（姓のみ可）", '
        f'"purpose": "用件（不明なら空文字）", '
        f'"date_str": "日時（不明なら空文字）"}}'
    )
    raw = await asyncio.to_thread(
        llm._client.chat,
        model=llm.model,
        messages=[
            {
                "role": "system",
                "content": (
                    "ユーザーの発言からメール送信の意図とパラメータを抽出します。"
                    "JSONまたは null のみ出力してください。余分なテキストは不要です。"
                ),
            },
            {"role": "user", "content": prompt},
        ],
        think=False,
    )
    content = raw.message.content.strip()
    try:
        if content.lower() == "null":
            return None
        m = _JSON_RE.search(content)
        text_to_parse = m.group(1) if m else content.strip("`").strip()
        data = json.loads(text_to_parse)
        # client_name が抽出できた場合のみ有効とする
        if not data.get("client_name", "").strip():
            return None
        # purpose・date_str のデフォルト
        if not data.get("purpose"):
            data["purpose"] = "ご連絡"
        if not data.get("date_str"):
            data["date_str"] = "近日中"
        return data
    except Exception:
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

    # キーワードが含まれる場合のみ intent 抽出を試みる（余分な LLM 呼び出しを避ける）
    has_kw = _has_email_keyword(req.message)
    print(f"[chat] message={req.message!r}  has_email_keyword={has_kw}")
    if has_kw:
        params = await _extract_email_params(req.message, llm)
        print(f"[chat] extract_email_params => {params}")
        if params:
            action = "send_email"
            action_params = params

    # 通常の会話 LLM 呼び出し（履歴に追加される）
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
