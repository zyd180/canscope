"""检查 PyInstaller onedir 产物的必需文件。"""
from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("dist/CANScope")
    required = [root / "CANScope.exe", root / "data" / "test.blf",
                root / "data" / "test.dbc"]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        print("Missing package files:")
        print("\n".join(missing))
        return 1
    print(f"PACKAGE OK: {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
