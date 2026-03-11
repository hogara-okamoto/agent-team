#!/bin/bash
# start-backend.sh
# WSL2 で Ollama + FastAPI バックエンドをバックグラウンド起動する。
# 既に起動済みの場合はスキップする。
# Electron の main.js から `wsl -- bash ~/projects/agent-team/scripts/start-backend.sh` で呼ばれる。

PROJECT_DIR="$HOME/projects/agent-team"
VENV="$PROJECT_DIR/.venv"
LOG_DIR="$HOME/.local/log/voice-agent"

mkdir -p "$LOG_DIR"

# --- Ollama ---
OLLAMA=/usr/local/bin/ollama

if pgrep -x ollama > /dev/null; then
  echo "[backend] ollama: already running"
else
  nohup "$OLLAMA" serve > "$LOG_DIR/ollama.log" 2>&1 &
  echo "[backend] ollama: started (pid $!)"
fi

# Ollama が HTTP 応答するまで待つ（最大60秒）
for i in $(seq 1 60); do
  if curl -sf http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "[backend] ollama: ready (${i}s)"
    break
  fi
  if [ "$i" -eq 60 ]; then
    echo "[backend] ollama: timed out waiting for ready"
  fi
  sleep 1
done

# --- FastAPI (uvicorn) ---
if pgrep -f "uvicorn main:app" > /dev/null; then
  echo "[backend] uvicorn: already running"
else
  cd "$PROJECT_DIR/backend"
  source "$VENV/bin/activate"
  nohup uvicorn main:app --host 0.0.0.0 --port 8000 \
    > "$LOG_DIR/backend.log" 2>&1 &
  echo "[backend] uvicorn: started (pid $!)"
fi
