"""诊断:侧栏✕ / chip✕ / −按钮 / +信号 四个流程。"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from gui.theme import QSS  # noqa: E402

app = QApplication(sys.argv)
app.setOrganizationName("canscope")
app.setApplicationName("CANScope")
app.setStyleSheet(QSS)

from gui.main_window import MainWindow  # noqa: E402

win = MainWindow()
win.show()

blf = ROOT / "data" / "test.blf"
dbc = ROOT / "data" / "test.dbc"
win.settings.setValue(f"sel/{blf.as_posix()}", "CLEARED")

loop = QEventLoop()
state = {"step": 0}


def on_ch(_i, _m):
    win.state.channelsReady.disconnect(on_ch)
    ch = win.state.stats["channels"][0]["channel"]
    win.state.toggle_signal(291, ch, "EngineSpeed")
    win.state.toggle_signal(292, ch, "VehicleSpeed")

    def t1():
        print(f"[1] 初始: signals={len(win.state.signals_list)} "
              f"plots={len(win.scope_stack.plots)} "
              f"plot_ids={[s.plot_id for s in win.state.signals_list]}")
        # 流程1: 侧栏✕移除 VehicleSpeed
        key_vs = f"292|{ch}|VehicleSpeed"
        win.state.remove_signal(key_vs)
        print(f"[1] 侧栏✕后: signals={len(win.state.signals_list)} "
              f"plot0_curves={len(win.scope_stack.plots[0]._curves)} "
              f"plot1_curves={len(win.scope_stack.plots[1]._curves)}")
        # 流程2: chip✕ 移除 EngineSpeed(plot 0)
        win.state.itemRemoveRequested = win.scope_stack.itemRemoveRequested
        win.scope_stack.itemRemoveRequested.emit(f"291|{ch}|EngineSpeed", 0)
        print(f"[2] chip✕后: signals={len(win.state.signals_list)} "
              f"curves={[len(p._curves) for p in win.scope_stack.plots]}")
        # 流程3: − 删除最后一个示波器
        win.state.add_plot_window()   # 2 窗
        win.state.toggle_signal(291, ch, "EngineSpeed")   # 落到空窗1
        def t3():
            print(f"[3] −前: signals={len(win.state.signals_list)} "
                  f"plot_count={win.state.plot_count} "
                  f"plots={len(win.scope_stack.plots)}")
            win.state.remove_last_plot()
            print(f"[3] −后: signals={len(win.state.signals_list)} "
                  f"plot_count={win.state.plot_count} "
                  f"plots={len(win.scope_stack.plots)} "
                  f"plot_ids={[s.plot_id for s in win.state.signals_list]}")
        # 流程4: +信号 复制到指定窗(模拟 _on_add_menu 的 emit,plot_id 0 基)
        win.state.itemCopyRequested = win.scope_stack.itemCopyRequested
        win.scope_stack.itemCopyRequested.emit(f"292|{ch}|VehicleSpeed", 0)
        print(f"[4] 复制到窗0后: "
              f"plot0={[s.name for s in win.state.signals_list if s.plot_id == 0]} "
              f"plot_ids={[s.plot_id for s in win.state.signals_list]}")
        print(f"[4] plot_id 与位置对应: "
              f"{[(p.plot_id, p.index) for p in win.scope_stack.plots]}")
        # 流程5: 关闭中间窗口 → 紧凑重编号
        win.state.add_plot_window()   # 3 窗
        win.state.toggle_signal(291, ch, "CoolantTemp")   # 落到窗2
        def t5():
            print(f"[5] 关闭前: plot_count={win.state.plot_count} "
                  f"plot_ids={sorted(s.plot_id for s in win.state.signals_list)} "
                  f"labels={[p.index for p in win.scope_stack.plots]}")
            win.scope_stack.closePlotRequested.emit(1)   # 关闭中间窗
            print(f"[5] 关闭窗1后: plot_count={win.state.plot_count} "
                  f"plot_ids={sorted(s.plot_id for s in win.state.signals_list)} "
                  f"labels={[p.index for p in win.scope_stack.plots]} "
                  f"curves={[len(p._curves) for p in win.scope_stack.plots]}")
            loop.quit()
        QTimer.singleShot(300, t5)
        QTimer.singleShot(300, t3)
    QTimer.singleShot(300, t1)


win.state.channelsReady.connect(on_ch)
win.state.open_paths([blf, dbc])
QTimer.singleShot(15000, loop.quit)
loop.exec()
print("done")
