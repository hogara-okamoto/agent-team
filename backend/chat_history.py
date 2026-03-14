"""会話履歴の永続化ユーティリティ

backend/data/chat_history.jsonl に 1 行 1 エントリ形式で追記する。
サーバー再起動後も直近の会話をロードして LLM に文脈を渡せる。

エントリ形式:
    {"role": "user", "content": "...", "timestamp": "...", "intent": "general"}
    {"role": "assistant", "content": "...", "timestamp": "..."}
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

_DATA_DIR = Path(__file__).parent / "data"
_HISTORY_FILE = _DATA_DIR / "chat_history.jsonl"

# サーバー起動時に読み込む最大メッセージ数（user + assistant 合計）
DEFAULT_LOAD_MESSAGES = 20


def append_turn(role: str, content: str, intent: str = "") -> None:
    """1 メッセージを JSONL に追記する。"""
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    entry: dict = {
        "role": role,
        "content": content,
        "timestamp": datetime.now().isoformat(),
    }
    if intent:
        entry["intent"] = intent
    with _HISTORY_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def load_recent(n_messages: int = DEFAULT_LOAD_MESSAGES) -> list[dict[str, str]]:
    """直近 n_messages 件を OllamaClient.history 形式（role + content のみ）で返す。"""
    if not _HISTORY_FILE.exists():
        return []

    lines = _HISTORY_FILE.read_text(encoding="utf-8").strip().splitlines()
    entries: list[dict] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    recent = entries[-n_messages:]
    return [{"role": e["role"], "content": e["content"]} for e in recent]
