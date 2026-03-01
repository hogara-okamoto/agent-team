"""LLM クライアントのユニットテスト。"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.llm.client import OllamaClient


@pytest.fixture
def client():
    with patch("src.llm.client.ollama.Client"):
        c = OllamaClient(model="llama3.2:3b", system_prompt="テスト用システムプロンプト")
        c._client = MagicMock()
        yield c


def test_chat_returns_assistant_text(client: OllamaClient):
    """chat() がアシスタントの応答テキストを返すこと。"""
    mock_response = MagicMock()
    mock_response.message.content = "テスト応答"
    client._client.chat.return_value = mock_response

    result = client.chat("こんにちは")
    assert result == "テスト応答"


def test_chat_updates_history(client: OllamaClient):
    """chat() 後に user / assistant の両メッセージが履歴に追加されること。"""
    mock_response = MagicMock()
    mock_response.message.content = "応答"
    client._client.chat.return_value = mock_response

    client.chat("質問")

    assert len(client.history) == 2
    assert client.history[0] == {"role": "user", "content": "質問"}
    assert client.history[1] == {"role": "assistant", "content": "応答"}


def test_chat_includes_system_prompt_in_messages(client: OllamaClient):
    """LLM に送るメッセージ列の先頭がシステムプロンプトであること。"""
    mock_response = MagicMock()
    mock_response.message.content = "ok"
    client._client.chat.return_value = mock_response

    client.chat("テスト")

    call_args = client._client.chat.call_args
    messages = call_args.kwargs["messages"]
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == "テスト用システムプロンプト"


def test_clear_history(client: OllamaClient):
    """clear_history() で履歴が空になること。"""
    client.history = [{"role": "user", "content": "dummy"}]
    client.clear_history()
    assert client.history == []


def test_keep_alive_passed_to_api(client: OllamaClient):
    """keep_alive 値が API 呼び出しに渡されること。"""
    client.keep_alive = 0
    mock_response = MagicMock()
    mock_response.message.content = "ok"
    client._client.chat.return_value = mock_response

    client.chat("test")

    call_args = client._client.chat.call_args
    assert call_args.kwargs["keep_alive"] == 0
