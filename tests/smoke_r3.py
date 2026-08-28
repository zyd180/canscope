"""R3 诊断、基准与兼容性入口冒烟测试。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services import diagnostics  # noqa: E402
from gui.main_window import VERSION, build_time  # noqa: E402


def main() -> int:
    diagnostics.record_operation("R3 smoke")
    try:
        raise RuntimeError("R3 smoke exception")
    except RuntimeError:
        diagnostics.write_crash_report(*sys.exc_info())

    log = ROOT / "logs" / "crash.log"
    text = log.read_text(encoding="utf-8") if log.is_file() else ""
    checks = {
        "crash log exists": log.is_file(),
        "version recorded": f"version: {VERSION}" in text,
        "operation recorded": "R3 smoke" in text,
        "traceback recorded": "RuntimeError: R3 smoke exception" in text,
        "build time available": bool(build_time()),
    }
    for name, ok in checks.items():
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
