#!/usr/bin/env python3
"""
TTS デバッグスクリプト
使い方: python3 debug_tts.py
出力:  debug_output.wav（正常なら「あいうえお」の音声）

このスクリプトは main.py や他のコードに一切依存しません。
piper バイナリを絶対パスで直接呼び出します。
"""

import os
import subprocess
import sys
from pathlib import Path

# ────────────────────────────────────────────
# 絶対パス（このスクリプトの場所から計算）
# ────────────────────────────────────────────
SCRIPT_DIR  = Path(__file__).resolve().parent          # voice-chatbot/
BIN_DIR     = SCRIPT_DIR / "models" / "piper-bin"
PIPER_BIN   = BIN_DIR / "piper"
MODEL_ONNX  = SCRIPT_DIR / "models" / "tts" / "ja_JP-test-medium.onnx"
OUTPUT_WAV  = SCRIPT_DIR / "debug_output.wav"
TEST_TEXT   = "あいうえお"

# ────────────────────────────────────────────
# 事前チェック
# ────────────────────────────────────────────
print("=" * 60)
print("  TTS デバッグスクリプト")
print("=" * 60)
print(f"[パス] スクリプト dir : {SCRIPT_DIR}")
print(f"[パス] piper バイナリ : {PIPER_BIN}")
print(f"[パス] ONNX モデル    : {MODEL_ONNX}")
print(f"[パス] 出力 WAV       : {OUTPUT_WAV}")
print()

errors = []
if not PIPER_BIN.exists():
    errors.append(f"  ✗ piper バイナリが見つかりません: {PIPER_BIN}")
if not MODEL_ONNX.exists():
    errors.append(f"  ✗ ONNX モデルが見つかりません: {MODEL_ONNX}")
if not os.access(str(PIPER_BIN), os.X_OK):
    errors.append(f"  ✗ piper バイナリに実行権限がありません: {PIPER_BIN}")

if errors:
    print("[ERROR] 以下のファイルが不足しています:")
    for e in errors:
        print(e)
    sys.exit(1)

print("[OK] 必要なファイルの存在を確認しました。")

# ────────────────────────────────────────────
# 環境変数（piper が必要とする .so を BIN_DIR から読む）
# ────────────────────────────────────────────
env = {
    **os.environ,
    "LD_LIBRARY_PATH": str(BIN_DIR),
    "ESPEAK_DATA_PATH": str(BIN_DIR / "espeak-ng-data"),
}

# ────────────────────────────────────────────
# コマンド構築（絶対パスのみ）
# ────────────────────────────────────────────
cmd = [
    str(PIPER_BIN),
    "--model",       str(MODEL_ONNX),
    "--output_file", str(OUTPUT_WAV),
    "--length_scale", "1.0",
]

print()
print("[実行コマンド]")
print("  " + " ".join(cmd))
print()
print(f"[環境変数]")
print(f"  LD_LIBRARY_PATH={env['LD_LIBRARY_PATH']}")
print(f"  ESPEAK_DATA_PATH={env['ESPEAK_DATA_PATH']}")
print()
print(f"[入力テキスト] 「{TEST_TEXT}」")
print()

# ────────────────────────────────────────────
# 実行
# ────────────────────────────────────────────
result = subprocess.run(
    cmd,
    input=TEST_TEXT.encode("utf-8"),
    capture_output=True,
    env=env,
)

print("[piper stdout]")
print(result.stdout.decode(errors="replace") or "  (なし)")
print("[piper stderr]")
print(result.stderr.decode(errors="replace") or "  (なし)")
print(f"[終了コード] {result.returncode}")
print()

if result.returncode != 0:
    print("[FAILED] piper がエラーを返しました。上記の stderr を確認してください。")
    sys.exit(1)

if not OUTPUT_WAV.exists():
    print("[FAILED] WAV ファイルが生成されませんでした。")
    sys.exit(1)

wav_size = OUTPUT_WAV.stat().st_size
print(f"[OK] WAV ファイル生成成功: {OUTPUT_WAV}")
print(f"     サイズ: {wav_size:,} bytes ({wav_size // 1024} KB)")

if wav_size < 1000:
    print("[WARNING] ファイルサイズが極端に小さいです。ノイズの可能性があります。")
else:
    print("[SUCCESS] 正常に生成されました。Ubuntu で再生して確認してください。")
    print(f"  aplay {OUTPUT_WAV}   # または")
    print(f"  ffplay {OUTPUT_WAV}")
