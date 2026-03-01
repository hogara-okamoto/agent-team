#!/usr/bin/env bash
# voice-chatbot 起動スクリプト
# 使い方: ./run.sh [--config config.yaml]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_SITE="${SCRIPT_DIR}/.venv/lib/python3.11/site-packages"

export LD_LIBRARY_PATH="${VENV_SITE}/nvidia/cublas/lib:${VENV_SITE}/nvidia/cudnn/lib:${LD_LIBRARY_PATH:-}"

cd "${SCRIPT_DIR}"
source "${SCRIPT_DIR}/.venv/bin/activate"
exec python3 "${SCRIPT_DIR}/main.py" "$@"
