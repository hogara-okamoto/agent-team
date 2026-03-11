"""FastAPI バックエンド — ローカル音声エージェント

起動方法（agent-team/backend/ ディレクトリで実行）:
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload

エンドポイント:
    POST /transcribe      WAV → テキスト（STT）
    POST /chat            テキスト → テキスト（LLM）
    DELETE /chat/history  会話履歴をリセット
    POST /synthesize      テキスト → WAV（TTS）
    GET  /health          ヘルスチェック
"""
from __future__ import annotations

import sys
from pathlib import Path

# voice-chatbot の src パッケージを import パスに追加
sys.path.insert(0, str(Path(__file__).parent.parent / "voice-chatbot"))

# .env を環境変数に読み込む（GMAIL_ADDRESS / GMAIL_APP_PASSWORD など）
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from dependencies import lifespan
from routers import chat, synthesize, transcribe, wakeword
from routers import email_agent, web_search

app = FastAPI(
    title="Voice Chatbot API",
    description="ローカル音声エージェント バックエンド API（STT / LLM / TTS）",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Electron からのアクセスを許可
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(transcribe.router)
app.include_router(chat.router)
app.include_router(synthesize.router)
app.include_router(wakeword.router)
app.include_router(email_agent.router)
app.include_router(web_search.router)


@app.get("/health", tags=["system"])
async def health() -> dict[str, object]:
    """サーバーの死活確認。各コンポーネントの状態も返す。"""
    from dependencies import get_status
    return {"status": "ok", "components": get_status()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
