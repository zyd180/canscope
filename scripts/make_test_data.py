"""生成测试数据:test.dbc + test.blf 到项目 data/ 目录。

运行: python scripts/make_test_data.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.demo_data import generate  # noqa: E402
from services.project_config import DATA_DIR  # noqa: E402


def main():
    d, b = generate(DATA_DIR)
    print(f"[OK] {d} ({d.stat().st_size} B)")
    print(f"[OK] {b} ({b.stat().st_size} B)")


if __name__ == "__main__":
    main()
