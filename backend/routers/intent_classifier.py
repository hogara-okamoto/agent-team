"""Intent classifier — ルートエージェントの振り分けロジック

ユーザーメッセージを intent タイプに分類し、専門エージェントへ振り分ける。
新しいエージェントを追加するには:
  1. INTENT_* 定数を追加
  2. キーワードリスト / パラメータ抽出関数を追加
  3. classify_intent() に分岐を追加
"""
from __future__ import annotations

import asyncio
import json
import re
from typing import Optional

# ──────────────────────────────────────────────
# Intent type 定数
# ──────────────────────────────────────────────
INTENT_EMAIL = "send_email"
INTENT_WEB_SEARCH = "web_search"
INTENT_GENERAL = "general"

# ──────────────────────────────────────────────
# 共通ユーティリティ
# ──────────────────────────────────────────────
_JSON_RE = re.compile(r"```json?\s*(.*?)\s*```", re.DOTALL)


async def _llm_json(prompt: str, llm) -> Optional[dict]:
    """LLM に JSON を生成させ、パースして返す。失敗時は None。"""
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


# ──────────────────────────────────────────────
# メール送信 intent
# ──────────────────────────────────────────────
_EMAIL_KEYWORDS = [
    "メール", "mail", "Mail",
    "アポ", "アポイント",
    "送って", "送りたい", "送信して", "送ってほしい", "送ってください",
    "ミーティング", "打ち合わせ", "連絡して",
]

# 「〇〇さんに」「〇〇様へ」パターン
_RECIPIENT_RE = re.compile(r"([^\s、。！？\n]{1,8}?)(?:さん|様|氏|くん)(?:に|へ)")
# エージェント自身・一人称などを除外
_SELF_NAMES: set[str] = {"岡本", "エージェント", "私", "僕", "俺", "自分"}


def _has_email_keyword(text: str) -> bool:
    return any(kw in text for kw in _EMAIL_KEYWORDS)


def _extract_recipient_regex(text: str) -> Optional[str]:
    for match in _RECIPIENT_RE.finditer(text):
        name = match.group(1).strip()
        if name and name not in _SELF_NAMES:
            return name
    return None


async def _extract_email_params(text: str, llm) -> Optional[dict]:
    """メール送信パラメータを抽出する。
    Step1: 正規表現で宛先名を高速抽出。
    Step2: 失敗した場合のみ LLM で抽出（最大2回）。
    """
    client_name = _extract_recipient_regex(text)

    if client_name:
        llm_result = await _llm_json(
            f"次の発言からメール送信のパラメータを抽出してください。\n"
            f"発言: {text}\n\n"
            f"JSONのみ出力（意図なしの場合は null）:\n"
            f'{{"client_name":"名前","purpose":"用件(不明なら空)","date_str":"日時(不明なら空)"}}',
            llm,
        )
        purpose = (llm_result or {}).get("purpose") or ""
        date_str = (llm_result or {}).get("date_str") or ""
        return {
            "client_name": client_name,
            "purpose": purpose or "ご連絡",
            "date_str": date_str or "近日中",
        }

    for _ in range(2):
        result = await _llm_json(
            f"次の発言からメール送信のパラメータを抽出してください。\n"
            f"発言: {text}\n\n"
            f"JSONのみ出力（意図なしの場合は null）:\n"
            f'{{"client_name":"名前","purpose":"用件(不明なら空)","date_str":"日時(不明なら空)"}}',
            llm,
        )
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
# Web 検索 intent
# ──────────────────────────────────────────────

# 明示的な検索動詞（"教えて" は汎用すぎるため除外）
_SEARCH_VERBS = [
    "検索して", "検索する", "検索お願い",
    "調べて", "調べてほしい", "調べてください", "調べたい",
    "ネットで", "インターネットで", "ウェブで", "Web検索",
    "最新ニュース", "ニュースを調",
]
# LLM が答えられないリアルタイムデータを含む語（動詞なしでも検索を起動）
_REALTIME_KEYWORDS = [
    "天気", "気温", "天気予報", "降水確率",
    "為替", "株価", "レート", "ドル円",
    "ニュース", "最新の", "最新情報",
]
_SEARCH_KEYWORDS = _SEARCH_VERBS + _REALTIME_KEYWORDS

# 「〇〇を調べて」「〇〇について検索して」「〇〇を教えて」からクエリを取り出す
_SEARCH_QUERY_RE = re.compile(
    r"(.+?)(?:を|について|に関して)?\s*"
    r"(?:検索して|調べて|ネットで|インターネットで|ウェブで|Web検索|教えて)"
)
# 「今日」「今年」など複合語にはマッチしないよう (?!日|年|月|週|夜|朝|後) を追加
_LATEST_RE = re.compile(r"(?:最新の?|今(?!日|年|月|週|夜|朝|後)の?)\s*(.+?)(?:について|に関して|を)?$")
_FILLER_RE = re.compile(r"^(?:ちょっと|少し|すこし|ちょいと)\s*")
# 「岡本さん、」「エージェント、」などの呼びかけ前置きを除去
_CALL_PREFIX_RE = re.compile(r"^[^\s、。！？]{1,8}(?:さん|様|くん|ちゃん)?[、,]\s*")
# 末尾の依頼動詞を除去するフォールバック用（「〇〇を教えて東京」→「東京」が残るのを防ぐため
# 全体をクエリとして使う前に整形する）
_REQUEST_SUFFIX_RE = re.compile(
    r"(?:を|について|に関して)?\s*(?:教えて|知りたい|知らせて)[^。！？]*$"
)


def _has_search_keyword(text: str) -> bool:
    return any(kw in text for kw in _SEARCH_KEYWORDS)


def _extract_search_query(text: str) -> str:
    """ユーザーメッセージから検索クエリを抽出する。"""
    # 呼びかけ前置き（「岡本さん、」など）を除去してから処理
    clean = _CALL_PREFIX_RE.sub("", text.strip())

    # パターン1: 「〇〇を調べて」「〇〇について検索して」「〇〇を教えて」
    m = _SEARCH_QUERY_RE.search(clean)
    if m:
        query = _FILLER_RE.sub("", m.group(1).strip())
        if query:
            # マッチ後に残った文字列（「東京」など）があれば末尾に追加
            # 「ください」「下さい」などの丁寧語は除去
            after = re.sub(r"^(?:ください|下さい|ね|よ|な)\s*", "", clean[m.end():].strip()).rstrip("。、！？")
            return f"{query} {after}".strip() if after else query

    # パターン2: 「最新の〇〇」「今の〇〇」（文頭のみ）
    m = _LATEST_RE.match(clean)
    if m:
        return m.group(1).strip()

    # フォールバック: 末尾の依頼動詞を除去してクエリとする
    fallback = _REQUEST_SUFFIX_RE.sub("", clean).strip().rstrip("。、！？")
    return fallback if fallback else clean


# ──────────────────────────────────────────────
# メイン分類関数
# ──────────────────────────────────────────────

async def classify_intent(
    message: str,
    llm,
) -> tuple[str, Optional[dict]]:
    """ユーザーメッセージの intent を分類し、専門エージェントのパラメータを返す。

    Returns:
        (intent_type, params)
        - intent_type: INTENT_EMAIL | INTENT_WEB_SEARCH | INTENT_GENERAL
        - params: intent に応じた dict、または None（INTENT_GENERAL の場合）

    新しいエージェントを追加する際は、ここに分岐を追加する。
    """
    # 1. メール送信 intent（高優先度）
    if _has_email_keyword(message):
        params = await _extract_email_params(message, llm)
        if params:
            return INTENT_EMAIL, params

    # 2. Web 検索 intent
    if _has_search_keyword(message):
        query = _extract_search_query(message)
        return INTENT_WEB_SEARCH, {"query": query}

    # 3. 通常会話（LLM にそのまま渡す）
    return INTENT_GENERAL, None
