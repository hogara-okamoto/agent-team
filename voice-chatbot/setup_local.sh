#!/usr/bin/env bash
# =============================================================================
# voice-chatbot ローカルセットアップスクリプト
# 対象: WSL2 (Ubuntu/Debian) / ローカル Linux
# 確認済み環境: Ubuntu 22.04, RTX 3050 Ti, CUDA 13.1, Driver 591.74
#
# 使い方:
#   cd agent-team/voice-chatbot
#   bash setup_local.sh
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIPER_VERSION="2023.11.14-2"
PYTHON_VERSION="3.11.14"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()    { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }
section() { echo -e "\n${GREEN}===== $* =====${NC}"; }

# =============================================================================
section "1. システムパッケージ（apt）"
# =============================================================================
info "apt パッケージをインストールします..."
sudo apt-get update -qq
sudo apt-get install -y \
    libportaudio2 \
    portaudio19-dev \
    zstd \
    curl \
    git \
    build-essential \
    libssl-dev \
    zlib1g-dev \
    libbz2-dev \
    libreadline-dev \
    libsqlite3-dev \
    libffi-dev \
    liblzma-dev
info "apt パッケージのインストール完了"

# =============================================================================
section "2. pyenv と Python ${PYTHON_VERSION}"
# =============================================================================
if command -v pyenv &>/dev/null; then
    info "pyenv はインストール済みです: $(pyenv --version)"
else
    info "pyenv をインストールします..."
    curl -fsSL https://pyenv.run | bash

    # PATH の即時設定（このスクリプト内で使えるようにする）
    export PYENV_ROOT="$HOME/.pyenv"
    export PATH="$PYENV_ROOT/bin:$PATH"
    eval "$(pyenv init - bash)"

    # ~/.bashrc への追記（重複チェック付き）
    if ! grep -q 'PYENV_ROOT' ~/.bashrc; then
        cat >> ~/.bashrc << 'BASHRC'

# pyenv setup (added by voice-chatbot setup_local.sh)
export PYENV_ROOT="$HOME/.pyenv"
[[ -d $PYENV_ROOT/bin ]] && export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init - bash)"
eval "$(pyenv virtualenv-init -)"
BASHRC
        info "pyenv の設定を ~/.bashrc に追記しました"
    fi
fi

# pyenv PATH の確認
export PYENV_ROOT="${PYENV_ROOT:-$HOME/.pyenv}"
export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init - bash)" 2>/dev/null || true

# Python 3.11.14 のインストール
if pyenv versions --bare | grep -qx "${PYTHON_VERSION}"; then
    info "Python ${PYTHON_VERSION} はインストール済みです"
else
    info "Python ${PYTHON_VERSION} をインストールします（数分かかります）..."
    pyenv install "${PYTHON_VERSION}"
fi

pyenv global "${PYTHON_VERSION}"
PYTHON_BIN="$(pyenv prefix)/bin/python3"
info "Python: $("${PYTHON_BIN}" --version)"

# =============================================================================
section "3. 仮想環境と pip パッケージ"
# =============================================================================
VENV_DIR="${SCRIPT_DIR}/.venv"

if [[ -f "${VENV_DIR}/pyvenv.cfg" ]]; then
    # 既存 .venv の Python バージョン確認
    VENV_PYTHON_VER=$(grep "^version" "${VENV_DIR}/pyvenv.cfg" | cut -d= -f2 | tr -d ' ')
    if [[ "${VENV_PYTHON_VER}" == "${PYTHON_VERSION}" ]]; then
        info ".venv (Python ${PYTHON_VERSION}) はすでに存在します。再利用します。"
    else
        warn ".venv の Python バージョン (${VENV_PYTHON_VER}) が異なります。再作成します..."
        rm -rf "${VENV_DIR}"
        "${PYTHON_BIN}" -m venv "${VENV_DIR}"
    fi
else
    info ".venv を作成します..."
    "${PYTHON_BIN}" -m venv "${VENV_DIR}"
fi

info "pip パッケージをインストールします..."
source "${VENV_DIR}/bin/activate"
pip install --upgrade pip --quiet
pip install -r "${SCRIPT_DIR}/requirements.txt"
info "pip パッケージのインストール完了"

# =============================================================================
section "4. CUDA ライブラリパスの設定"
# =============================================================================
VENV_SITE="${VENV_DIR}/lib/python3.11/site-packages"
CUBLAS_LIB="${VENV_SITE}/nvidia/cublas/lib"
CUDNN_LIB="${VENV_SITE}/nvidia/cudnn/lib"

CUDA_LD_PATH_LINE="export LD_LIBRARY_PATH=\"${CUBLAS_LIB}:${CUDNN_LIB}:\${LD_LIBRARY_PATH:-}\""
CUDA_COMMENT="# voice-chatbot: CUDA ライブラリパス (added by setup_local.sh)"

if ! grep -q 'nvidia/cublas/lib' ~/.bashrc; then
    cat >> ~/.bashrc << BASHRC

${CUDA_COMMENT}
${CUDA_LD_PATH_LINE}
BASHRC
    info "CUDA LD_LIBRARY_PATH を ~/.bashrc に追記しました"
else
    info "CUDA LD_LIBRARY_PATH はすでに ~/.bashrc に設定されています"
fi

# 現在のセッションにも適用
export LD_LIBRARY_PATH="${CUBLAS_LIB}:${CUDNN_LIB}:${LD_LIBRARY_PATH:-}"

# =============================================================================
section "5. piper C++ バイナリ（openjtalk 対応 TTS）"
# =============================================================================
PIPER_BIN_DIR="${SCRIPT_DIR}/models/piper-bin"
PIPER_BIN="${PIPER_BIN_DIR}/piper"

if [[ -x "${PIPER_BIN}" ]]; then
    info "piper バイナリはすでに存在します: ${PIPER_BIN}"
else
    info "piper バイナリをダウンロードします..."
    mkdir -p "${PIPER_BIN_DIR}"
    PIPER_URL="https://github.com/rhasspy/piper/releases/download/${PIPER_VERSION}/piper_linux_x86_64.tar.gz"
    TMP_ARCHIVE="/tmp/piper_linux_x86_64.tar.gz"

    curl -L -o "${TMP_ARCHIVE}" "${PIPER_URL}"
    tar xzf "${TMP_ARCHIVE}" -C /tmp/

    cp /tmp/piper/piper             "${PIPER_BIN_DIR}/"
    cp /tmp/piper/*.so*             "${PIPER_BIN_DIR}/"
    cp -r /tmp/piper/espeak-ng-data "${PIPER_BIN_DIR}/"
    chmod +x "${PIPER_BIN}"

    rm -f "${TMP_ARCHIVE}"
    info "piper バイナリの配置完了: ${PIPER_BIN_DIR}/"
fi

# =============================================================================
section "6. Ollama のセットアップ"
# =============================================================================
if command -v ollama &>/dev/null; then
    info "Ollama はインストール済みです"
else
    info "Ollama をインストールします..."
    curl -fsSL https://ollama.com/install.sh | sh
fi

# Ollama サーバーが起動しているか確認
if curl -s http://localhost:11434/api/tags &>/dev/null; then
    info "Ollama サーバーはすでに起動しています"
else
    info "Ollama サーバーをバックグラウンドで起動します..."
    ollama serve > /tmp/ollama.log 2>&1 &
    OLLAMA_PID=$!
    sleep 3

    if curl -s http://localhost:11434/api/tags &>/dev/null; then
        info "Ollama サーバー起動完了 (PID: ${OLLAMA_PID})"
    else
        warn "Ollama サーバーの起動確認ができませんでした。/tmp/ollama.log を確認してください"
    fi
fi

# llama3.2:3b のダウンロード（未取得時のみ）
if ollama list 2>/dev/null | grep -q 'llama3.2:3b'; then
    info "llama3.2:3b はすでにダウンロード済みです"
else
    info "llama3.2:3b をダウンロードします（約 2GB、数分かかります）..."
    ollama pull llama3.2:3b
fi

# =============================================================================
section "7. GPU の確認"
# =============================================================================
if command -v nvidia-smi &>/dev/null; then
    info "GPU 確認:"
    nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader
else
    warn "nvidia-smi が見つかりません。CPU モードで動作します。"
    warn "config.yaml の stt.device を 'cpu'、compute_type を 'int8' に変更してください。"
fi

# =============================================================================
section "8. セットアップ完了"
# =============================================================================
echo ""
echo "  セットアップが完了しました！"
echo ""
echo "  起動方法:"
echo "    cd ${SCRIPT_DIR}"
echo "    ollama serve > /tmp/ollama.log 2>&1 &   # 別ターミナルまたはバックグラウンドで"
echo "    ./run.sh"
echo ""
echo "  マイクなし環境でのテスト:"
echo "    source .venv/bin/activate"
echo "    python3 smoke_test.py --text 'こんにちは'"
echo ""
echo "  注意: ~/.bashrc の変更を現在のシェルに反映するには以下を実行:"
echo "    source ~/.bashrc"
echo ""
