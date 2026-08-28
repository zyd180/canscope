"""运行诊断:最近操作记录与未捕获异常留痕。"""
from __future__ import annotations

from collections import deque
from datetime import datetime
import sys
import traceback

from services.project_config import app_root

_operations = deque(maxlen=50)


def record_operation(operation: str) -> None:
    """记录最近用户/后台操作,供崩溃报告定位现场。"""
    _operations.append(
        f"{datetime.now().isoformat(timespec='seconds')} {operation}")


def recent_operations() -> list[str]:
    return list(_operations)


def write_crash_report(exc_type, exc_value, exc_tb) -> None:
    """追加崩溃报告;日志失败不能反过来阻断异常处理。"""
    try:
        from gui.main_window import VERSION
        version = VERSION
    except Exception:
        version = "unknown"
    try:
        path = app_root() / "logs" / "crash.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write("\n=== CANScope crash ===\n")
            f.write(f"time: {datetime.now().isoformat(timespec='seconds')}\n")
            f.write(f"version: {version}\n")
            f.write(f"python: {sys.version}\n")
            f.write("recent operations:\n")
            f.writelines(f"- {item}\n" for item in recent_operations())
            f.write("traceback:\n")
            traceback.print_exception(exc_type, exc_value, exc_tb, file=f)
    except Exception:
        pass


def install_exception_hook() -> None:
    previous = sys.excepthook

    def hook(exc_type, exc_value, exc_tb):
        write_crash_report(exc_type, exc_value, exc_tb)
        previous(exc_type, exc_value, exc_tb)

    sys.excepthook = hook
