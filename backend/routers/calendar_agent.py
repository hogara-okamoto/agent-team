"""カレンダーエージェント

ローカル JSON ファイル（backend/data/calendar.json）に予定を保存・管理する。

対応操作:
  - add    : 予定を追加する
  - list   : 指定日の予定を取得する（デフォルト: 今日）
  - delete : 予定を削除する
"""
from __future__ import annotations

import asyncio
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/calendar", tags=["calendar"])

# 保存先
_DATA_DIR = Path(__file__).parent.parent / "data"
_CALENDAR_FILE = _DATA_DIR / "calendar.json"


# ──────────────────────────────────────────────
# スキーマ
# ──────────────────────────────────────────────

class Event(BaseModel):
    id: str
    title: str
    date: str        # "YYYY-MM-DD"
    time: str        # "HH:MM" or ""
    note: str = ""


class AddEventRequest(BaseModel):
    title: str
    date: str        # "YYYY-MM-DD"
    time: str = ""
    note: str = ""


class ListEventsResponse(BaseModel):
    date: str
    events: list[Event]


class DeleteEventRequest(BaseModel):
    event_id: str


# ──────────────────────────────────────────────
# ストレージ
# ──────────────────────────────────────────────

def _load() -> list[dict]:
    if not _CALENDAR_FILE.exists():
        return []
    try:
        return json.loads(_CALENDAR_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save(events: list[dict]) -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    _CALENDAR_FILE.write_text(
        json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _new_id() -> str:
    import time
    return str(int(time.time() * 1000))


# ──────────────────────────────────────────────
# エンドポイント
# ──────────────────────────────────────────────

@router.post("/add", response_model=Event)
async def add_event(req: AddEventRequest) -> Event:
    """予定を追加する。"""
    # 日付形式バリデーション
    try:
        datetime.strptime(req.date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail=f"日付形式が不正です: {req.date!r}")

    events = _load()
    event = {
        "id": _new_id(),
        "title": req.title,
        "date": req.date,
        "time": req.time,
        "note": req.note,
    }
    events.append(event)
    _save(events)
    return Event(**event)


@router.get("/list", response_model=ListEventsResponse)
async def list_events(date: Optional[str] = None) -> ListEventsResponse:
    """指定日（デフォルト: 今日）の予定を返す。"""
    target = date or str(datetime.now().date())
    try:
        datetime.strptime(target, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail=f"日付形式が不正です: {target!r}")

    all_events = _load()
    day_events = [e for e in all_events if e.get("date") == target]
    # 時刻でソート（時刻なしは末尾）
    day_events.sort(key=lambda e: e.get("time") or "99:99")
    return ListEventsResponse(
        date=target,
        events=[Event(**e) for e in day_events],
    )


@router.delete("/delete")
async def delete_event(req: DeleteEventRequest) -> dict[str, str]:
    """ID で予定を削除する。"""
    events = _load()
    new_events = [e for e in events if e.get("id") != req.event_id]
    if len(new_events) == len(events):
        raise HTTPException(status_code=404, detail=f"予定が見つかりません: {req.event_id!r}")
    _save(new_events)
    return {"status": "deleted", "event_id": req.event_id}


# ──────────────────────────────────────────────
# チャット用ヘルパー（intent_classifier / chat.py から呼ばれる）
# ──────────────────────────────────────────────

# 日付解析ユーティリティ
_TODAY_WORDS = {"今日", "本日", "きょう"}
_TOMORROW_WORDS = {"明日", "あした", "あす"}
_DAY_AFTER_WORDS = {"明後日", "あさって"}

_DATE_ISO_RE = re.compile(r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})日?")  # 2026-03-16 / 2026年3月16日
_DATE_COMPACT_RE = re.compile(r"(\d{4})(\d{2})(\d{2})")                # 20260316
_DATE_RE = re.compile(r"(\d{1,2})[月/\-](\d{1,2})日?")                 # 3月16日 / 3/16
_TIME_RE = re.compile(r"(\d{1,2})時(?:(\d{1,2})分)?")


def parse_date_str(text: str) -> str:
    """テキストから日付を解析して "YYYY-MM-DD" を返す。不明なら今日。"""
    today = datetime.now().date()
    if any(w in text for w in _TODAY_WORDS):
        return str(today)
    if any(w in text for w in _TOMORROW_WORDS):
        return str(today + timedelta(days=1))
    if any(w in text for w in _DAY_AFTER_WORDS):
        return str(today + timedelta(days=2))

    # YYYY-MM-DD / YYYY/MM/DD / YYYY年MM月DD日
    m = _DATE_ISO_RE.search(text)
    if m:
        try:
            return str(date(int(m.group(1)), int(m.group(2)), int(m.group(3))))
        except ValueError:
            pass

    # YYYYMMDD（8桁連続）
    m = _DATE_COMPACT_RE.search(text)
    if m:
        try:
            return str(date(int(m.group(1)), int(m.group(2)), int(m.group(3))))
        except ValueError:
            pass

    # MM月DD日 / MM/DD
    m = _DATE_RE.search(text)
    if m:
        month = int(m.group(1))
        day = int(m.group(2))
        year = today.year
        try:
            d = date(year, month, day)
            if d < today:
                d = date(year + 1, month, day)
            return str(d)
        except ValueError:
            pass

    return str(today)


def parse_time_str(text: str) -> str:
    """テキストから時刻を解析して "HH:MM" を返す。不明なら空文字。"""
    m = _TIME_RE.search(text)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2) or 0)
        return f"{hour:02d}:{minute:02d}"
    return ""


def get_events_text(target_date: str) -> str:
    """指定日の予定をテキスト形式で返す（LLM コンテキスト用）。"""
    all_events = _load()
    day_events = [e for e in all_events if e.get("date") == target_date]
    day_events.sort(key=lambda e: e.get("time") or "99:99")

    if not day_events:
        return f"{target_date} の予定はありません。"

    lines = [f"{target_date} の予定:"]
    for e in day_events:
        time_part = f" {e['time']}" if e.get("time") else ""
        note_part = f"（{e['note']}）" if e.get("note") else ""
        lines.append(f"  ・{time_part} {e['title']}{note_part}".strip())
    return "\n".join(lines)


def add_event_from_text(title: str, date_str: str, time_str: str = "", note: str = "") -> str:
    """テキスト解析済みの情報で予定を追加し、確認メッセージを返す。"""
    events = _load()
    event = {
        "id": _new_id(),
        "title": title,
        "date": date_str,
        "time": time_str,
        "note": note,
    }
    events.append(event)
    _save(events)

    time_part = f" {time_str}" if time_str else ""
    return f"{date_str}{time_part} に「{title}」を追加しました。"
