from __future__ import annotations

from typing import Iterator

import ollama


class OllamaClient:
    """Ollama ローカル LLM クライアント。会話履歴管理・ストリーミング対応。"""

    def __init__(
        self,
        model: str = "llama3.2:3b",
        base_url: str = "http://localhost:11434",
        system_prompt: str = "あなたは親切なアシスタントです。",
        keep_alive: int = 0,
    ) -> None:
        self.model = model
        self.keep_alive = keep_alive
        self.system_prompt = system_prompt
        self._client = ollama.Client(host=base_url)
        self.history: list[dict[str, str]] = []

    def _build_messages(self) -> list[dict[str, str]]:
        return [{"role": "system", "content": self.system_prompt}] + self.history

    def chat(self, user_message: str) -> str:
        """ユーザーメッセージを送り、応答テキストを返す。

        keep_alive=0 により推論後すぐに VRAM を解放する。
        """
        self.history.append({"role": "user", "content": user_message})

        response = self._client.chat(
            model=self.model,
            messages=self._build_messages(),
            keep_alive=self.keep_alive,
        )
        assistant_text: str = response.message.content
        self.history.append({"role": "assistant", "content": assistant_text})
        return assistant_text

    def chat_stream(self, user_message: str) -> Iterator[str]:
        """ストリーミングで応答チャンクを yield する。"""
        self.history.append({"role": "user", "content": user_message})

        stream = self._client.chat(
            model=self.model,
            messages=self._build_messages(),
            keep_alive=self.keep_alive,
            stream=True,
        )
        full_response = ""
        for chunk in stream:
            content: str = chunk.message.content or ""
            if content:
                full_response += content
                yield content

        self.history.append({"role": "assistant", "content": full_response})

    def clear_history(self) -> None:
        """会話履歴をリセットする。"""
        self.history = []
