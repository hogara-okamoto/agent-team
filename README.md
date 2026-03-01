# ローカル音声エージェント

マイクに話しかけると、**完全ローカルの AI** が日本語で音声回答するデスクトップアプリです。
外部サーバーへのデータ送信は一切ありません。

```
マイク → [Electron] → STT → LLM → TTS → スピーカー
         (Windows)       (WSL2 FastAPI バックエンド)
```

---

## スクリーンショット

> *(準備中)*

---

## 特徴

- **完全ローカル動作** — 音声・テキストが外部に送信されない
- **日本語対応** — STT / TTS ともに日本語に最適化
- **低遅延** — GPU（RTX 3050 Ti）で faster-whisper を高速実行
- **テキスト入力フォールバック** — マイクなしでも LLM と会話できる
- **コンポーネント障害に強い** — STT/LLM/TTS のどれかが未起動でも他は動作継続

---

## アーキテクチャ

```
┌──────────────────────────────────────┐
│  Electron アプリ（Windows）           │
│                                      │
│  マイク → Web Audio API → WAV        │
│        ↓ HTTP POST /transcribe       │
│  ←←← WAV 受信 → <Audio> 再生        │
└───────────────┬──────────────────────┘
                │ localhost:8000
┌───────────────▼──────────────────────┐
│  FastAPI バックエンド（WSL2）         │
│                                      │
│  POST /transcribe  WAV  → テキスト   │
│  POST /chat        テキスト → 返答   │
│  POST /synthesize  テキスト → WAV    │
│  GET  /health      状態確認          │
└──────────────────────────────────────┘
```

---

## 技術スタック

| 役割 | 技術 |
|---|---|
| STT | [faster-whisper](https://github.com/SYSTRAN/faster-whisper) |
| LLM | [Ollama](https://ollama.com/) + llama3.2:3b |
| TTS | [open_jtalk](https://open-jtalk.sourceforge.net/) |
| バックエンド | [FastAPI](https://fastapi.tiangolo.com/) + uvicorn |
| フロントエンド | [Electron](https://www.electronjs.org/) + [React](https://react.dev/) + [Vite](https://vitejs.dev/) |
| 実行環境 | WSL2 / Debian 11 + Windows 11 |

---

## 動作要件

| 項目 | 要件 |
|---|---|
| OS | Windows 11 + WSL2（Debian/Ubuntu） |
| GPU | NVIDIA GPU（CUDA 対応）推奨 |
| RAM | 8 GB 以上 |
| Node.js | v18 以上 |
| Python | 3.11 以上 |

---

## セットアップ

### 1. リポジトリのクローン

```bash
git clone <repo-url>
cd agent-team
```

### 2. システムパッケージ（WSL2 側）

```bash
sudo apt-get update
sudo apt-get install -y \
    open-jtalk open-jtalk-mecab-naist-jdic hts-voice-nitech-jp-atr503-m001 \
    libportaudio2 portaudio19-dev zstd
```

### 3. 日本語フォント（WSL2 側）

```bash
sudo mkdir -p /usr/local/share/fonts/noto
sudo curl -L "https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/Japanese/NotoSansCJKjp-Regular.otf" \
  -o /usr/local/share/fonts/noto/NotoSansCJKjp-Regular.otf
sudo curl -L "https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/Japanese/NotoSansCJKjp-Bold.otf" \
  -o /usr/local/share/fonts/noto/NotoSansCJKjp-Bold.otf
sudo fc-cache -f /usr/local/share/fonts/noto
```

### 4. Python 環境（WSL2 側）

```bash
python -m venv .venv
.venv/bin/pip install -r voice-chatbot/requirements.txt
.venv/bin/pip install fastapi "uvicorn[standard]" python-multipart
```

### 5. Ollama（WSL2 側）

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama serve > /tmp/ollama.log 2>&1 &
ollama pull llama3.2:3b
```

### 6. フロントエンド依存パッケージ

```bash
cd frontend
npm install
```

---

## 起動方法

**ターミナル1（WSL2）** — バックエンドを起動

```bash
cd agent-team/backend
ollama serve > /tmp/ollama.log 2>&1 &   # Ollama が未起動の場合
python3 main.py   #.venvの環境で実行
```

**ターミナル2（Windows / WSL2）** — Electron アプリを起動

```bash
cd agent-team/frontend
npm run build   # 初回またはコード変更後
npm start
```

> 開発時（ホットリロード）は `npm run dev`

---

## ディレクトリ構成

```
agent-team/
├── voice-chatbot/          # STT / LLM / TTS コアライブラリ
│   ├── src/
│   │   ├── stt/            # faster-whisper ラッパー
│   │   ├── llm/            # Ollama クライアント
│   │   ├── tts/            # open_jtalk / piper シンセサイザー
│   │   └── config/         # Settings（pydantic）
│   └── requirements.txt
├── backend/                # FastAPI バックエンド
│   ├── main.py
│   ├── dependencies.py     # lifespan / DI
│   └── routers/
│       ├── transcribe.py
│       ├── chat.py
│       └── synthesize.py
├── frontend/               # Electron + React フロントエンド
│   ├── electron/
│   │   ├── main.js         # メインプロセス
│   │   └── preload.js
│   └── src/
│       ├── App.jsx
│       ├── api.js           # FastAPI クライアント
│       ├── audioUtils.js    # WAV エンコーダ
│       └── components/
│           ├── ChatLog.jsx
│           └── RecordButton.jsx
└── Docs/
    ├── roadmap.md
    └── setup-voice-chatbot.md
```

---

## ロードマップ

- [x] STT / LLM / TTS のローカル動作
- [x] FastAPI バックエンド（`/transcribe` `/chat` `/synthesize`）
- [x] Electron フロントエンド（マイク録音・会話ループ）
- [x] エンドツーエンドの音声会話
- [ ] システムトレイ常駐
- [ ] グローバルホットキーで呼び出し（キー押下で録音開始）
- [ ] ウェイクワードで呼び出し（発話で自動録音開始）
- [ ] Windows 起動時に自動起動
- [ ] 会話履歴の永続化
- [ ] 専門エージェント（ファイル操作・Web 検索・コード実行）

---

## ライセンス

MIT
