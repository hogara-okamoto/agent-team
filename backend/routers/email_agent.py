"""メール送信エージェント ルーター

エンドポイント:
    POST /email/draft   クライアント名・用件・日時 → メール文案を生成
    POST /email/send    メール文案 → Gmail SMTP で送信
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from dependencies import get_llm_client

router = APIRouter(prefix="/email", tags=["email"])

CLIENTS_PATH = Path(__file__).parent.parent.parent / "data" / "clients.json"

_JSON_RE = re.compile(r"```json?\s*(.*?)\s*```", re.DOTALL)


def _load_clients() -> list[dict]:
    if not CLIENTS_PATH.exists():
        return []
    return json.loads(CLIENTS_PATH.read_text(encoding="utf-8"))


def _normalize(text: str) -> str:
    """検索用に数字・記号を正規化する（全角→半角、ひらがな→カタカナなど）。"""
    # 全角数字→半角
    text = text.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    return text.lower()


def _find_client(name: str) -> Optional[dict]:
    """名前または会社名で部分一致検索する。
    - 姓のみ / フルネーム / 会社名（略称含む）いずれでも一致させる。
    """
    name_n = _normalize(name)
    for client in _load_clients():
        c_name = _normalize(client.get("name", ""))
        c_company = _normalize(client.get("company", ""))
        # 姓のみ一致（名前フィールドの先頭の単語と比較）
        c_last = c_name.split()[0] if c_name.split() else c_name
        if (
            name_n in c_name
            or name_n in c_company
            or c_last == name_n
            or name_n in c_last
        ):
            return client
    return None


def _extract_json(text: str) -> dict:
    """LLM 出力からコードブロックを除去して JSON をパースする。"""
    # ```json ... ``` ブロックがあれば中身だけ取り出す
    m = _JSON_RE.search(text)
    if m:
        text = m.group(1)
    else:
        text = text.strip().strip("`")
    return json.loads(text)


# ──────────────────────────────────────────────
# スキーマ
# ──────────────────────────────────────────────

class DraftRequest(BaseModel):
    client_name: str          # 例: "山田"
    purpose: str              # 例: "ミーティングのアポイント"
    date_str: str             # 例: "明日", "来週月曜"


class DraftResponse(BaseModel):
    to: str                   # 宛先メールアドレス（未登録なら空文字）
    to_name: str              # 敬称付き宛名 例: "山田 太郎 様"
    company: str
    subject: str
    body: str
    client_found: bool        # クライアントリストで見つかったか


class SendRequest(BaseModel):
    to: str
    subject: str
    body: str


# ──────────────────────────────────────────────
# エンドポイント
# ──────────────────────────────────────────────

@router.post("/draft", response_model=DraftResponse)
async def create_draft(req: DraftRequest, llm=Depends(get_llm_client)) -> DraftResponse:
    """クライアントを検索し、LLM でビジネスメール文案を生成する。"""
    client = _find_client(req.client_name)
    if client:
        to_email = client["email"]
        to_name = f"{client['name']} 様"
        company = client.get("company", "")
        client_found = True
    else:
        to_email = ""
        to_name = f"{req.client_name} 様"
        company = ""
        client_found = False

    prompt = (
        f"以下の条件でビジネスメールの件名と本文を日本語で作成してください。\n"
        f"宛先: {company} {to_name}\n"
        f"用件: {req.purpose}\n"
        f"希望日時: {req.date_str}\n"
        f"送信者名: 岡本\n\n"
        f"出力形式（JSONのみ・余分なテキスト不要）:\n"
        f'{{"subject": "件名", "body": "本文全文（改行は\\nで表現）"}}'
    )

    raw = await asyncio.to_thread(
        llm._client.chat,
        model=llm.model,
        messages=[
            {
                "role": "system",
                "content": (
                    "あなたはビジネスメール作成の専門家です。"
                    "日本語のみで答えてください。JSONのみ出力してください。"
                ),
            },
            {"role": "user", "content": prompt},
        ],
        think=False,
    )

    try:
        data = _extract_json(raw.message.content)
        subject: str = data["subject"]
        body: str = data["body"]
    except Exception:
        # LLM が JSON を返せなかった場合のフォールバック
        subject = f"{req.purpose}のご相談"
        body = (
            f"{company} {to_name}\n\n"
            f"いつもお世話になっております。岡本です。\n\n"
            f"{req.date_str}に{req.purpose}についてご相談させていただきたく、"
            f"ご都合のよいお時間をお知らせいただけますでしょうか。\n\n"
            f"どうぞよろしくお願いいたします。\n\n岡本"
        )

    return DraftResponse(
        to=to_email,
        to_name=to_name,
        company=company,
        subject=subject,
        body=body,
        client_found=client_found,
    )


@router.post("/send")
async def send_email(req: SendRequest) -> dict[str, str]:
    """Gmail SMTP でメールを送信する。"""
    gmail_address = os.environ.get("GMAIL_ADDRESS", "")
    app_password = os.environ.get("GMAIL_APP_PASSWORD", "")

    if not gmail_address or not app_password:
        raise HTTPException(
            status_code=500,
            detail="Gmail 認証情報が未設定です（backend/.env に GMAIL_ADDRESS / GMAIL_APP_PASSWORD を設定してください）",
        )
    if not req.to:
        raise HTTPException(status_code=400, detail="宛先メールアドレスが設定されていません")

    msg = MIMEMultipart()
    msg["From"] = gmail_address
    msg["To"] = req.to
    msg["Subject"] = req.subject
    msg.attach(MIMEText(req.body, "plain", "utf-8"))

    try:
        await asyncio.to_thread(_smtp_send, gmail_address, app_password, req.to, msg.as_string())
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"メール送信失敗: {exc}") from exc

    return {"status": "sent", "to": req.to}


def _smtp_send(gmail_address: str, app_password: str, to: str, message: str) -> None:
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail_address, app_password)
        server.sendmail(gmail_address, to, message)
