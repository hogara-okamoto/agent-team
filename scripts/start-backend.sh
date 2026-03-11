#!/bin/bash
# start-backend.sh
# WSL2 で Ollama + FastAPI バックエンドをバックグラウンド起動する。
# 既に起動済みの場合はスキップする。
# Electron の main.js から `wsl -- bash ~/projects/agent-team/scripts/start-backend.sh` で呼ばれる。

PROJECT_DIR="$HOME/projects/agent-team"
VENV="$PROJECT_DIR/.venv"
PYTHON="$VENV/bin/python"
LOG_DIR="$HOME/.local/log/voice-agent"
OLLAMA=/usr/local/bin/ollama

mkdir -p "$LOG_DIR"

# --- Ollama ---
if pgrep -x ollama > /dev/null; then
  echo "[backend] ollama: already running"
else
  nohup "$OLLAMA" serve > "$LOG_DIR/ollama.log" 2>&1 &
  echo "[backend] ollama: started (pid $!)"
fi

# --- FastAPI (uvicorn) ---
# ollama の起動待ちより前に開始し、セッション終了前に十分な時間を確保する
if pgrep -f "uvicorn main:app" > /dev/null; then
  echo "[backend] uvicorn: already running"
else
  cd "$PROJECT_DIR/backend"
  nohup "$PYTHON" -m uvicorn main:app --host 0.0.0.0 --port 8000 \
    > "$LOG_DIR/backend.log" 2>&1 &
  echo "[backend] uvicorn: started (pid $!)"
fi

# --- ollama の起動を待つ（最大60秒）---
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

# --- uvicorn の起動を待つ（最大90秒）---
# lifespan で STT/LLM/TTS モデルをロードするため時間がかかる
for i in $(seq 1 90); do
  if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
    echo "[backend] uvicorn: ready (${i}s)"
    break
  fi
  if [ "$i" -eq 90 ]; then
    echo "[backend] uvicorn: timed out waiting for ready"
  fi
  sleep 1
done
