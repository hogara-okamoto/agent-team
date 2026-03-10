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
- **低遅延** — GPU（RTX 4000 Ada / 12GB VRAM）で faster-whisper large-v3-turbo を高速実行
- **テキスト入力フォールバック** — マイクなしでも LLM と会話できる
- **コンポーネント障害に強い** — STT/LLM/TTS のどれかが未起動でも他は動作継続
- **システムトレイ常駐** — × ボタンで非表示にしてもバックグラウンドで常駐
- **グローバルホットキー** — `Ctrl+Shift+Space` でいつでも即呼び出し・録音開始
- **無音自動停止（VAD）** — 発話後 3 秒無音で録音を自動停止
- **ウェイクワード呼び出し** — 「エージェント」「岡本」と話しかけると自動で録音開始
- **Windows 自動起動** — PC 起動時にトレイアイコン＋バックエンドが自動で立ち上がる
- **メール送信エージェント** — 音声でアポ依頼 → クライアント検索 → メール文案生成 → Gmail 送信

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
│  POST /transcribe   WAV  → テキスト  │
│  POST /chat         テキスト → 返答  │
│  POST /synthesize   テキスト → WAV   │
│  GET  /health       状態確認         │
│  POST /wakeword     ウェイクワード判定│
│  POST /email/draft  メール文案生成   │
│  POST /email/send   Gmail 送信       │
└──────────────────────────────────────┘
```

---

## 技術スタック

| 役割 | 技術 |
|---|---|
| STT | [faster-whisper](https://github.com/SYSTRAN/faster-whisper) large-v3-turbo |
| LLM | [Ollama](https://ollama.com/) + qwen3.5:9b（thinking: false） |
| TTS | [VOICEVOX](https://voicevox.hiroshiba.jp/)（主）/ [open_jtalk](https://open-jtalk.sourceforge.net/) / [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M)（切り替え対応） |
| バックエンド | [FastAPI](https://fastapi.tiangolo.com/) + uvicorn |
| フロントエンド | [Electron](https://www.electronjs.org/) + [React](https://react.dev/) + [Vite](https://vitejs.dev/) |
| 実行環境 | WSL2 / Debian 11 + Windows 11 |

---

## 動作要件

| 項目 | 要件 |
|---|---|
| OS | Windows 11 + WSL2（Debian/Ubuntu） |
| GPU | NVIDIA GPU（CUDA 対応）推奨 ※ RTX 4000 Ada / 12GB VRAM で動作確認済み |
| VRAM | 12 GB 以上推奨（qwen3.5:9b 約7GB + Whisper large-v3-turbo 約1.5GB） |
| RAM | 16 GB 以上推奨 |
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
ollama pull qwen3.5:9b
```

### 6. VOICEVOX Engine（Docker / WSL2 側）

```bash
# GPU 版（RTX 4000 Ada など NVIDIA GPU が必要）
docker run -d --gpus all --restart=always \
  -p 50021:50021 voicevox/voicevox_engine:nvidia-latest

# 起動確認
curl http://localhost:50021/version
```

> 初回のみ `docker update --restart=always voicevox` 相当の設定が `--restart=always` で自動適用される。
> Docker Desktop を自動起動設定にすれば PC 再起動後も自動で VOICEVOX が起動する。

### 7. Gmail 認証情報（メール送信エージェントを使う場合）

`backend/.env` を各マシンで手動作成してください（`.gitignore` 対象のため `git pull` では届きません）。

```bash
# WSL2 側
cat > agent-team/backend/.env <<'EOF'
GMAIL_ADDRESS=your-address@gmail.com
GMAIL_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx
EOF
```

> Gmail の「アプリ パスワード」は Google アカウント → セキュリティ → 2段階認証を有効にした上で発行できます。

### 8. フロントエンド依存パッケージ

```bash
# Windows 側（C:\Users\<user>\projects\agent-team\frontend）
cd frontend
npm install
```

---

## 起動方法

**ターミナル1（WSL2）** — バックエンドを起動

```bash
cd agent-team/backend
ollama serve > /tmp/ollama.log 2>&1 &   # Ollama が未起動の場合
# VOICEVOX は Docker Desktop 起動時に自動起動（--restart=always 設定済みの場合）
python3 main.py
```

**ターミナル2（Windows）** — Electron アプリを起動

```bash
# C:\Users\<user>\projects\agent-team\frontend
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
│   │   ├── tts/            # openjtalk / voicevox / kokoro / piper シンセサイザー
│   │   └── config/         # Settings（pydantic）
│   └── requirements.txt
├── backend/                # FastAPI バックエンド
│   ├── main.py
│   ├── dependencies.py     # lifespan / DI
│   ├── .env                # ※ git 管理外・各マシンで手動作成（GMAIL_ADDRESS 等）
│   └── routers/
│       ├── transcribe.py
│       ├── chat.py         # intent 検出（メール送信）含む
│       ├── synthesize.py
│       ├── wakeword.py     # ウェイクワード判定
│       └── email_agent.py  # メール文案生成・Gmail 送信
├── data/
│   └── clients.json        # クライアント一覧（name / company / email）
├── frontend/               # Electron + React フロントエンド
│   ├── electron/
│   │   ├── main.js         # メインプロセス（Tray・ホットキー・ウィンドウ管理）
│   │   ├── preload.js      # IPC ブリッジ
│   │   └── icon.png        # システムトレイアイコン
│   └── src/
│       ├── App.jsx
│       ├── api.js           # FastAPI クライアント
│       ├── audioUtils.js    # WAV エンコーダ
│       ├── hooks/
│       │   └── useWakeWord.js  # 常時 VAD + ウェイクワード検出
│       └── components/
│           ├── ChatLog.jsx
│           ├── RecordButton.jsx
│           └── EmailDraftModal.jsx  # メール確認・送信モーダル
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
- [x] システムトレイ常駐（Tray アイコン・コンテキストメニュー・×で非表示）
- [x] グローバルホットキーで呼び出し（`Ctrl+Shift+Space` で録音開始）
- [x] 無音自動停止 VAD（発話後 3 秒無音で自動停止）
- [x] ウェイクワードで呼び出し（「エージェント」「岡本」で自動録音開始）
- [x] Windows 起動時に自動起動
- [x] メール送信エージェント（音声でアポ依頼 → Gmail 送信）
- [ ] 会話履歴の永続化
- [ ] 専門エージェント（ファイル操作・Web 検索・コード実行）
  - [x] メール送信エージェント（アポイント日時の調整・Gmail 送信）

---

## ライセンス

MIT
