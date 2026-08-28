"""示波器窗口操作回归:侧栏✕/chip✕/−按钮/+信号复制/关闭任意窗重编号。

运行: python tests/smoke_scope_ops.py
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import pyqtgraph as pg  # noqa: E402

from gui.theme import QSS  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        fails.append(name)


def scene_curves(plot) -> int:
    """场景中真实的 PlotDataItem 数量(抓图形泄漏,字典长度不可靠)。"""
    return sum(1 for it in plot.plot.plotItem.items
               if isinstance(it, pg.PlotDataItem))


def wait_for(cond_fn, timeout_ms=6000):
    loop = QEventLoop()
    t = QTimer()
    t.timeout.connect(lambda: cond_fn() and loop.quit())
    t.start(20)
    QTimer.singleShot(timeout_ms, loop.quit)
    loop.exec()
    t.stop()


def main() -> int:
    blf = ROOT / "data" / "test.blf"
    dbc = ROOT / "data" / "test.dbc"

    app = QApplication(sys.argv)
    app.setOrganizationName("canscope")
    app.setApplicationName("CANScope")
    app.setStyleSheet(QSS)

    from gui.main_window import MainWindow
    win = MainWindow()
    win.show()

    loop = QEventLoop()

    def on_ch(_i, _m):
        win.state.channelsReady.disconnect(on_ch)
        ch = win.state.stats["channels"][0]["channel"]
        s, st = win.state, win.scope_stack

        # 初始:两个信号 → 两个窗口(0 基)
        s.toggle_signal(291, ch, "EngineSpeed")
        s.toggle_signal(292, ch, "VehicleSpeed")
        wait_for(lambda: len(s.signals_list) == 2)
        check("初始2窗", len(s.signals_list) == 2 and len(st.plots) == 2)
        check("plot_id 0基", [(p.plot_id, p.index) for p in st.plots] ==
              [(0, 1), (1, 2)],
              f"{[(p.plot_id, p.index) for p in st.plots]}")
        # 轴像素对齐:两窗绘图区左缘偏差必须为 0(Y 轴标签宽度不同也不行)
        x0 = st.plots[0].getViewBox().sceneBoundingRect().x()
        x1 = st.plots[1].getViewBox().sceneBoundingRect().x()
        check("多窗轴对齐", abs(x0 - x1) < 0.5,
              f"x0={x0:.1f} x1={x1:.1f}")

        # 1) 侧栏✕:整信号移除(所有窗)
        key_vs = f"292|{ch}|VehicleSpeed"
        s.remove_signal(key_vs)
        check("侧栏✕移除", len(s.signals_list) == 1
              and len(st.plots[1]._curves) == 0
              and scene_curves(st.plots[1]) == 0,
              f"dict={[len(p._curves) for p in st.plots]} "
              f"scene={[scene_curves(p) for p in st.plots]}")

        # 2) chip✕:单窗移除
        s.toggle_signal(292, ch, "VehicleSpeed")   # 复用空窗 1
        wait_for(lambda: len(s.signals_list) == 2)
        st.itemRemoveRequested.emit(f"291|{ch}|EngineSpeed", 0)
        check("chip✕单窗移除", len(s.signals_list) == 1
              and len(st.plots[0]._curves) == 0
              and scene_curves(st.plots[0]) == 0
              and len(st.plots[1]._curves) == 1
              and scene_curves(st.plots[1]) == 1,
              f"dict={[len(p._curves) for p in st.plots]} "
              f"scene={[scene_curves(p) for p in st.plots]}")

        # 3) +信号 复制到指定窗(plot_id 0 基):把窗 1 的 VS 复制到空窗 0
        st.itemCopyRequested.emit(key_vs, 0)
        check("+信号复制到指定窗", len(st.plots[0]._curves) == 1
              and scene_curves(st.plots[0]) == 1,
              f"curves={[len(p._curves) for p in st.plots]}")

        # 4) − 删除最后一个窗
        s.remove_last_plot()
        check("−删末窗", s.plot_count == 1 and len(st.plots) == 1
              and len(s.signals_list) == 1)

        # 5) 多窗 + 关闭中间窗 → 紧凑重编号
        s.add_plot_window()                          # 2 窗
        s.toggle_signal(291, ch, "CoolantTemp")      # 落到窗 1
        wait_for(lambda: len(s.signals_list) == 2)
        s.add_plot_window()                          # 3 窗
        s.toggle_signal(291, ch, "EngineSpeed")      # 落到窗 2(新逻辑信号)
        wait_for(lambda: len(s.signals_list) == 3)
        st.closePlotRequested.emit(1)                # 关闭中间窗
        pids = sorted(x.plot_id for x in s.signals_list)
        check("关闭中间窗重编号", s.plot_count == 2
              and pids == [0, 1]
              and [p.index for p in st.plots] == [1, 2]
              and len(st.plots[0]._curves) == 1
              and scene_curves(st.plots[0]) == 1
              and len(st.plots[1]._curves) == 1
              and scene_curves(st.plots[1]) == 1,
              f"pids={pids} labels={[p.index for p in st.plots]} "
              f"scene={[scene_curves(p) for p in st.plots]}")

        loop.quit()

    win.state.channelsReady.connect(on_ch)
    win.state.errorRaised.connect(lambda e: print("[ERROR]", e))
    win.settings.setValue(f"sel/{blf.as_posix()}", "CLEARED")   # 屏蔽三态恢复
    win.state.open_paths([blf, dbc])
    QTimer.singleShot(30000, loop.quit)
    loop.exec()

    print()
    if fails:
        print(f"FAILED: {fails}")
        return 1
    print("ALL SCOPE-OPS TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
