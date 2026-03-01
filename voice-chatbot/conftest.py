import sys
from pathlib import Path

# プロジェクトルートを PYTHONPATH に追加（pip install -e . なしでテスト可能）
sys.path.insert(0, str(Path(__file__).parent))
