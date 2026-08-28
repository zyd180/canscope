"""通用后台任务执行器:QThreadPool + QRunnable,回调固定在主线程执行。"""
from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import QObject, QRunnable, Signal, QThreadPool


class _TaskSignals(QObject):
    done = Signal(object)
    fail = Signal(str)


class _Relay(QObject):
    """主线程中继:worker 信号 → 队列投递,保证 on_done/on_fail 在主线程跑。"""

    done = Signal(object)
    fail = Signal(str)


class FnTask(QRunnable):
    """在线程池中执行 fn(),经信号把结果/异常送回主线程。"""

    def __init__(self, fn: Callable):
        super().__init__()
        self.fn = fn
        self.sig = _TaskSignals()

    def run(self) -> None:
        try:
            result = self.fn()
            self.sig.done.emit(result)
        except Exception as e:   # noqa: BLE001 后台任务兜底
            self.sig.fail.emit(str(e))


class TaskRunner(QObject):
    """任务调度:保持任务强引用直至回调送达,防止跨线程 GC 崩溃。"""

    def __init__(self, on_error: Callable[[str], None], parent: Optional[QObject] = None):
        super().__init__(parent)
        self._on_error = on_error
        self._pool = QThreadPool.globalInstance()
        self._tasks: dict = {}

    def run(self, fn: Callable, on_done: Callable, on_fail: Optional[Callable] = None) -> None:
        task = FnTask(fn)
        relay = _Relay(self)          # 亲和主线程
        tid = id(task)
        self._tasks[tid] = (task, relay)

        def _done(result):
            self._tasks.pop(tid, None)
            on_done(result)

        def _fail(msg):
            self._tasks.pop(tid, None)
            (on_fail or self._on_error)(msg)

        task.sig.done.connect(relay.done)   # worker 发射 → 队列到主线程
        task.sig.fail.connect(relay.fail)
        relay.done.connect(_done)
        relay.fail.connect(_fail)
        self._pool.start(task)
