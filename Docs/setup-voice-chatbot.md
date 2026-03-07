# セットアップ手順

> コンテナ再構築後や WSL2 環境への展開時はこの手順に従うこと。
> 確認済み動作環境: NVIDIA RTX 4000 Ada / 12GB VRAM / CUDA / Debian 11 (bullseye)

---

## 1. システムパッケージ（apt）

```bash
sudo apt-get update
sudo apt-get install -y \
    libportaudio2 portaudio19-dev \
    zstd \
    open-jtalk open-jtalk-mecab-naist-jdic hts-voice-nitech-jp-atr503-m001
```

---

## 2. 日本語フォント（Electron UI 用）

Debian 11 の apt には `fonts-noto-cjk` が含まれないため、直接インストールする。

```bash
sudo mkdir -p /usr/local/share/fonts/noto

sudo curl -L "https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/Japanese/NotoSansCJKjp-Regular.otf" \
  -o /usr/local/share/fonts/noto/NotoSansCJKjp-Regular.otf

sudo curl -L "https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/Japanese/NotoSansCJKjp-Bold.otf" \
  -o /usr/local/share/fonts/noto/NotoSansCJKjp-Bold.otf

sudo fc-cache -f /usr/local/share/fonts/noto

# 確認
fc-list | grep "Noto Sans CJK JP"
```

---

## 3. Python 環境（バックエンド共有 venv）

Python 3.11.14 は `/usr/local/python/current/bin/python` にインストール済み。

```bash
cd agent-team

# 共有 venv 作成（初回のみ）
python -m venv .venv

# 依存パッケージをインストール
.venv/bin/pip install -r voice-chatbot/requirements.txt
.venv/bin/pip install fastapi "uvicorn[standard]" python-multipart
```

---

## 4. CUDA ライブラリパス（STT GPU 高速化必須）

`~/.bashrc` の末尾に追記。

```bash
VENV_SITE="$HOME/agent-team/.venv/lib/python3.11/site-packages"
export LD_LIBRARY_PATH="${VENV_SITE}/nvidia/cublas/lib:${VENV_SITE}/nvidia/cudnn/lib:${LD_LIBRARY_PATH:-}"
```

---

## 5. Ollama のセットアップ

```bash
curl -fsSL https://ollama.com/install.sh | sh

# 起動（コンテナ再起動のたびに必要）
ollama serve > /tmp/ollama.log 2>&1 &

# モデル取得（初回のみ・約 9GB）
ollama pull qwen3.5:9b
```

> WSL2 は systemd が動かないため `ollama serve` を手動で起動すること。

---

## 6. VOICEVOX Engine（Docker）

VOICEVOX は Docker コンテナとして起動する。GPU 版を推奨（RTX 4000 Ada 対応）。

```bash
# 初回起動（--restart=always で Docker 起動時に自動再起動）
docker run -d --gpus all --restart=always \
  -p 50021:50021 voicevox/voicevox_engine:nvidia-latest

# 起動確認
curl http://localhost:50021/version

# GPU なし環境（CPU 版）
# docker run -d --restart=always -p 50021:50021 voicevox/voicevox_engine:latest
```

**Docker Desktop 自動起動設定（Windows）**:
`Docker Desktop → Settings → General → "Start Docker Desktop when you sign in"` にチェックを入れると、
PC 起動時に Docker が自動起動し、VOICEVOX コンテナも自動で起動する。

**スピーカー番号の目安:**

| 番号 | キャラクター |
|---|---|
| 1 | 四国めたん |
| 3 | ずんだもん |
| 8 | 春日部つむぎ |
| 13 | ナースロボ＿タイプT |

`config.yaml` の `voicevox_speaker` で変更可能。全スピーカー一覧:
```bash
curl http://localhost:50021/speakers | python3 -m json.tool | grep '"name"'
```

---

## 7. FastAPI バックエンドの起動

```bash
cd agent-team/backend

# 起動（ポート 8000）
python3 main.py

# 動作確認
curl http://localhost:8000/health
```

バックエンドは WSL2 側で起動したまま維持すること。
各コンポーネントが未初期化の場合、対応エンドポイントは 503 を返して継続動作する。

---

## 8. Electron フロントエンドの起動（Windows 側）

リポジトリは Windows 側（例: `C:\Users\<user>\projects\agent-team`）にクローンすること。
WSL2 の UNC パス（`\\wsl.localhost\...`）では `npm install` が失敗する。

```bash
# Windows 側のターミナル（PowerShell / Git Bash）
cd C:\Users\<user>\projects\agent-team\frontend

# 依存パッケージ（初回のみ）
npm install

# 本番起動
npm run build
npm start

# 開発時（ホットリロード）
npm run dev
```

> **マイク権限**: `session.setPermissionRequestHandler` で自動許可済み（Electron 33 / Chromium 130 対応）。
> 初回起動時に Windows がマイクアクセスを確認する場合は「許可」を選択すること。

---

## TTS エンジンの選択

`voice-chatbot/config.yaml` の `tts.engine` で切り替える。

| エンジン | 品質 | 追加要件 |
|---|---|---|
| `voicevox` | 高品質 ⭐推奨 | Docker（手順6） |
| `style_bert_vits2` | 最高品質 | Style-Bert-VITS2 サーバー起動 |
| `xtts` | 高品質（多言語） | `pip install TTS`、参照 WAV 必要 |
| `openjtalk` | 標準 | 追加インストール不要（手順1） |
| `piper` | 標準 | piper バイナリ別途必要 |

---

## トラブルシューティング

| エラー | 原因 | 対処 |
|---|---|---|
| 日本語が□□□になる | フォント未インストール | 手順2を実行。インターネット接続時は Google Fonts が自動適用 |
| マイクが使えない | Electron のパーミッション | `main.js` に `setPermissionRequestHandler` が設定されているか確認 |
| `libcublas.so.12 is not found` | LD_LIBRARY_PATH 未設定 | 手順4の CUDA パス設定を確認 |
| `PortAudio library not found` | libportaudio2 未インストール | `sudo apt-get install libportaudio2` |
| Ollama 接続エラー | サーバー未起動 | `ollama serve &` を実行 |
| `open_jtalk: command not found` | open-jtalk 未インストール | 手順1を実行 |
| バックエンドが 503 を返す | モデル未初期化 | `/health` でどのコンポーネントが失敗しているか確認 |
| VOICEVOX に接続できない | コンテナ未起動 | `docker ps` で確認、未起動なら手順6を実行 |
| npm install が EPERM/UNC エラー | WSL2 パスで実行している | Windows 側のフォルダ（`C:\...`）でコマンドを実行する |
| STT が初回起動時に遅い | large-v3 モデルのダウンロード | 約 3GB をダウンロード中（`models/whisper/` に保存後は高速起動） |
