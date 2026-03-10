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
if pgrep -x ollama > /dev/null; then
  echo "[backend] ollama: already running"
else
  setsid nohup ollama serve > "$LOG_DIR/ollama.log" 2>&1 &
  disown $!
  echo "[backend] ollama: started (pid $!)"
fi

# --- FastAPI (uvicorn) ---
if pgrep -f "uvicorn main:app" > /dev/null; then
  echo "[backend] uvicorn: already running"
else
  cd "$PROJECT_DIR/backend"
  source "$VENV/bin/activate"
  setsid nohup uvicorn main:app --host 0.0.0.0 --port 8000 \
    > "$LOG_DIR/backend.log" 2>&1 &
  disown $!
  echo "[backend] uvicorn: started (pid $!)"
fi
