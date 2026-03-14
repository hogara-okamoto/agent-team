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
INTENT_CALENDAR = "calendar"
INTENT_YOUTUBE = "youtube_play"
INTENT_WEATHER = "weather"
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
# 「岡本さん、」「エージェント、」「岡本さん 」などの呼びかけ前置きを除去
# セパレータ: 読点・カンマ・スペース（1文字以上必須）
_CALL_PREFIX_RE = re.compile(r"^[^\s、。！？]{1,8}(?:さん|様|くん|ちゃん)?[、,\s　]+")
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
# カレンダー intent
# ──────────────────────────────────────────────

_CALENDAR_ADD_KEYWORDS = [
    "予定を追加", "予定追加", "スケジュール追加", "スケジュールを追加",
    "予定を入れて", "予定を登録", "カレンダーに追加",
    "予定を作って", "予定をいれて", "アポを入れて", "アポを登録",
]
_CALENDAR_LIST_KEYWORDS = [
    "予定を確認", "予定は", "予定を教えて", "スケジュールを確認",
    "スケジュールは", "スケジュールを教えて", "カレンダーを確認",
    "今日の予定", "明日の予定", "明後日の予定",
    "今週の予定", "何か予定", "予定がある",
]
_CALENDAR_KEYWORDS = _CALENDAR_ADD_KEYWORDS + _CALENDAR_LIST_KEYWORDS


def _has_calendar_keyword(text: str) -> bool:
    return any(kw in text for kw in _CALENDAR_KEYWORDS)


def _is_calendar_add(text: str) -> bool:
    return any(kw in text for kw in _CALENDAR_ADD_KEYWORDS)


async def _extract_calendar_add_params(text: str, llm) -> dict:
    """予定追加のパラメータを LLM で抽出する。"""
    from routers.calendar_agent import parse_date_str, parse_time_str

    result = await _llm_json(
        f"次の発言から予定追加のパラメータを抽出してください。\n"
        f"発言: {text}\n\n"
        f"JSONのみ出力（不明な項目は空文字）:\n"
        f'{{"title":"予定のタイトル","date_str":"日時の表現(例:明日,3月15日など)","time_str":"時刻の表現(例:14時,午後3時など)","note":"備考"}}',
        llm,
    )
    date_str_raw = (result or {}).get("date_str") or ""
    time_str_raw = (result or {}).get("time_str") or ""
    title = (result or {}).get("title") or ""
    note = (result or {}).get("note") or ""

    # LLM が取り出した日付・時刻テキストをパース
    date_parsed = parse_date_str(date_str_raw or text)
    time_parsed = parse_time_str(time_str_raw or text)

    # タイトルが抽出できなかった場合は正規表現でフォールバック
    if not title:
        # 「〇〇を追加して」「〇〇の予定」などからタイトルを取り出す
        m = re.search(r"「(.+?)」", text)
        if m:
            title = m.group(1)
        else:
            m = re.search(r"(.+?)(?:を|の予定|のアポ|をカレンダー|を追加|を登録|を入れて)", text)
            if m:
                title = m.group(1).strip()
            else:
                title = "予定"

    return {
        "operation": "add",
        "title": title,
        "date": date_parsed,
        "time": time_parsed,
        "note": note,
    }


# ──────────────────────────────────────────────
# 天気 intent
# ──────────────────────────────────────────────

_WEATHER_KEYWORDS = ["天気", "気温", "天気予報", "降水確率", "雨が降る", "傘が必要", "晴れる", "雪が降る"]

# 「東京の天気」「大阪の明日の気温」などから都市名を抽出
_WEATHER_CITY_RE = re.compile(r"([^\s、。！？の]{1,6})の(?:今日|明日|明後日)?(?:の)?(?:天気|気温|天気予報|降水確率)")

# 日付オフセット対応表
_WEATHER_DATE_MAP = {
    "今日": 0, "本日": 0, "きょう": 0,
    "明日": 1, "あした": 1, "あす": 1,
    "明後日": 2, "あさって": 2,
}


def _has_weather_keyword(text: str) -> bool:
    return any(kw in text for kw in _WEATHER_KEYWORDS)


def _extract_weather_params(text: str) -> dict:
    """都市名と日付オフセットを抽出する。"""
    # 日付オフセット
    date_offset = 0
    for word, offset in _WEATHER_DATE_MAP.items():
        if word in text:
            date_offset = offset
            break

    # 都市名（「東京の天気」パターン）
    m = _WEATHER_CITY_RE.search(text)
    city = m.group(1).strip() if m else "東京"

    # 呼びかけ前置きが都市名になっていないか除外
    _SELF_NAMES_WEATHER = {"岡本", "エージェント", "私", "僕", "俺", "今日", "明日", "明後日"}
    if city in _SELF_NAMES_WEATHER:
        city = "東京"

    return {"city": city, "date_offset": date_offset}


# ──────────────────────────────────────────────
# YouTube intent
# ──────────────────────────────────────────────

_YOUTUBE_KEYWORDS = [
    "YouTube", "ユーチューブ", "youtube",
    "かけて", "流して", "再生して", "再生お願い",
    "音楽をかけて", "BGMをかけて", "曲をかけて",
    "音楽を流して", "BGMを流して",
]

# 「かけて」「流して」だけでは誤検知しやすいため、YouTube 文脈か音楽動詞と組み合わせた場合のみ検出
_YOUTUBE_SERVICE_RE = re.compile(r"YouTube|ユーチューブ|youtube", re.IGNORECASE)
_YOUTUBE_VERB_RE = re.compile(r"かけて|流して|再生して|再生お願い")
_MUSIC_NOUN_RE = re.compile(r"音楽|BGM|曲|ミュージック|ジャズ|ロック|クラシック|ポップス|ヒップホップ|R&B|演歌|J-POP|アニソン|lofi|ローファイ")

_YOUTUBE_STOP_RE = re.compile(
    r"(?:YouTube|ユーチューブ)?.*?(?:とめて|止めて|停止|消して|切って|終わって|閉じて|やめて)",
    re.IGNORECASE,
)
INTENT_YOUTUBE_STOP = "youtube_stop"


def _has_youtube_stop_keyword(text: str) -> bool:
    """YouTube 停止 intent かどうかを判定する。"""
    stop_verbs = [
        "とめて", "止めて", "停止", "消して", "切って",
        "終わって", "閉じて", "やめて",
        "終了", "終わり", "オフ", "止まれ", "閉じろ",
    ]
    has_stop = any(v in text for v in stop_verbs)
    has_youtube = _YOUTUBE_SERVICE_RE.search(text) is not None
    has_music = _MUSIC_NOUN_RE.search(text) is not None

    if has_stop and (has_youtube or has_music):
        return True

    # 「YouTube終了」「YouTube止まれ」のように YouTube名 + 停止名詞だけのケース
    # （動詞活用なしで体言止めになることが多い）
    if has_youtube and has_stop:
        return True

    # 「YouTube」単体で停止動詞があれば（動詞なし「YouTube終了」も包含）
    if has_youtube and any(v in text for v in ["終了", "終わり", "停止", "オフ"]):
        return True

    return False


def _has_youtube_keyword(text: str) -> bool:
    """YouTube 操作 intent かどうかを判定する。
    - 「YouTube で〇〇をかけて」 → True（サービス名あり）
    - 「ジャズをかけて」 → True（音楽ジャンル + 再生動詞）
    - 「アラームをかけて」 → False（音楽名詞なし）
    """
    if _YOUTUBE_SERVICE_RE.search(text):
        return True
    # 再生動詞 + 音楽名詞の組み合わせ
    if _YOUTUBE_VERB_RE.search(text) and _MUSIC_NOUN_RE.search(text):
        return True
    return False


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

    # 2. YouTube 停止 intent（再生より先に判定）
    if _has_youtube_stop_keyword(message):
        return INTENT_YOUTUBE_STOP, {}

    # 3. YouTube 再生 intent
    if _has_youtube_keyword(message):
        from routers.youtube_agent import extract_youtube_query
        query = extract_youtube_query(message)
        return INTENT_YOUTUBE, {"query": query}

    # 4. カレンダー intent
    if _has_calendar_keyword(message):
        if _is_calendar_add(message):
            params = await _extract_calendar_add_params(message, llm)
            return INTENT_CALENDAR, params
        else:
            # 予定確認: 日付を解析
            from routers.calendar_agent import parse_date_str
            date_str = parse_date_str(message)
            return INTENT_CALENDAR, {"operation": "list", "date": date_str}

    # 5. 天気 intent（Web 検索より前に判定）
    if _has_weather_keyword(message):
        params = _extract_weather_params(message)
        return INTENT_WEATHER, params

    # 6. Web 検索 intent
    if _has_search_keyword(message):
        query = _extract_search_query(message)
        return INTENT_WEB_SEARCH, {"query": query}

    # 4. 通常会話（LLM にそのまま渡す）
    return INTENT_GENERAL, None
