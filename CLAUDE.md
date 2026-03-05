# Agent Team — プロジェクト概要

## プロジェクトの目的

外部にデータを送信せず、音声会話でエージェントに指示を出せる、
**常時起動型のローカルルートエージェント**を構築する。

```
ユーザー（音声） ←→ ルートエージェント ←→ 各専門エージェント
                       （常時起動・完全ローカル）
```

詳細なロードマップ → [`Docs/roadmap.md`](Docs/roadmap.md)

---

## 現在の状態（2026-03-05）

| コンポーネント | 状態 | 詳細 |
|---|---|---|
| STT（音声認識） | ✅ 完了 | faster-whisper large-v3（GPU: RTX 4000 Ada） |
| LLM | ✅ 完了 | Ollama + qwen2.5:14b |
| TTS（日本語音声合成） | ✅ 完了 | VOICEVOX（主）/ open_jtalk / Style-Bert-VITS2 / XTTS v2 切り替え対応 |
| FastAPI バックエンド | ✅ 完了 | `backend/` — `/transcribe` `/chat` `/synthesize` `/health` |
| Electron フロントエンド | ✅ 完了 | `frontend/` — 録音・STT・LLM・TTS 再生の完全ループ |
| マイク入力 | ✅ 完了 | Electron Web Audio API（Web 側でマイク取得） |
| スピーカー出力 | ✅ 完了 | Electron `<Audio>` で WAV 再生 |
| エンドツーエンド会話ループ | ✅ 完了 | 録音 → STT → LLM → TTS → 再生 が動作確認済み |
| システムトレイ常駐 | ✅ 完了 | Tray アイコン・コンテキストメニュー・×で非表示 |
| グローバルホットキー | ✅ 完了 | Ctrl+Shift+Space で表示＋録音自動開始 |
| 無音自動停止（VAD） | ✅ 完了 | 発話後 5 秒無音で録音を自動停止 |

---

## ディレクトリ構成

```
agent-team/
├── voice-chatbot/        # STT / LLM / TTS コアライブラリ
│   ├── src/
│   │   ├── stt/          # faster-whisper ラッパー
│   │   ├── llm/          # Ollama クライアント
│   │   ├── tts/          # openjtalk / voicevox / style_bert_vits2 / xtts / piper シンセサイザー
│   │   └── config/       # Settings（pydantic）
│   └── requirements.txt
├── backend/              # FastAPI バックエンド（WSL2 で起動）
│   ├── main.py
│   ├── dependencies.py   # lifespan でモデルをシングルトン管理
│   └── routers/          # transcribe / chat / synthesize
├── frontend/             # Electron + React フロントエンド（Windows で起動）
│   ├── electron/         # main.js / preload.js
│   ├── src/              # React コンポーネント・API クライアント・WAV エンコーダ
│   └── dist/             # Vite ビルド成果物
├── .venv/                # 共有 Python venv（backend 用）
├── Docs/
│   ├── roadmap.md
│   └── setup-voice-chatbot.md
└── CLAUDE.md
```

---

## 技術スタック

| 役割 | 技術 |
|---|---|
| STT | faster-whisper large-v3（GPU: RTX 4000 Ada / 20GB VRAM） |
| LLM | Ollama / qwen2.5:14b |
| TTS | VOICEVOX（主）/ open_jtalk / Style-Bert-VITS2 / XTTS v2（`config.yaml` で切り替え） |
| バックエンド API | FastAPI + uvicorn（Python） |
| フロントエンド | Electron + React + Vite |
| 音声録音 | Web Audio API（ScriptProcessor → PCM → WAV） |
| 日本語フォント | Noto Sans CJK JP（システム） + Google Fonts（オンライン時） |
| 実行環境 | WSL2 / Debian 11 + Windows 11 |

---

## 開発ルール

### Python バージョン

- **Python 3.11.14 を使用すること**
- 実行環境: `/usr/local/python/current/bin/python`（システム Python）
- `agent-team/.venv` を共有 venv として使用する

### AI 開発チームの役割分担

| 役割 | 担当 |
|---|---|
| **[Architect]** | 全体設計・ディレクトリ構成・ライブラリ選定 |
| **[Developer]** | 実装（クリーンコード・型安全・DRY原則） |
| **[QA]** | エッジケース・テスト・セキュリティ確認 |

タスク実行順序: Plan（Architect）→ Execute（Developer）→ Review（QA）

### コマンド実行の指針

- ファイル変更前に必ず現状を確認する
- 破壊的変更の前にはバックアップ／Git commit を確認する
- テスト失敗時は原因を分析してから修正する

---

## 環境構築

詳細手順 → [`Docs/setup-voice-chatbot.md`](Docs/setup-voice-chatbot.md)
