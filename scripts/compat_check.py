"""依赖与核心导入兼容性检查入口。

运行: python scripts/compat_check.py
在 Python 3.10/3.11 虚拟环境中分别执行此脚本和 smoke 套件。
"""
from __future__ import annotations

import sys


def main() -> int:
    from importlib.metadata import version
    import PySide6
    import can
    import cantools  # noqa: F401
    import pyqtgraph

    print(f"Python: {sys.version.split()[0]}")
    print(f"PySide6: {version('PySide6')}")
    print(f"python-can: {version('python-can')}")
    print(f"cantools: {version('cantools')}")
    print(f"pyqtgraph: {version('pyqtgraph')}")
    print("COMPAT IMPORTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
