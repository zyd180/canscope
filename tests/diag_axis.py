"""轴对齐验证:多窗绘图区左缘像素偏差。"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "windows")
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
win.resize(1500, 900)
win.show()
loop = QEventLoop()


def on_ch(_i, _m):
    ch = win.state.stats["channels"][0]["channel"]
    win.state.toggle_signal(291, ch, "EngineSpeed")
    win.state.toggle_signal(292, ch, "VehicleSpeed")

    def check():
        st = win.scope_stack
        # 强制两窗 y 范围差异大(模拟用户场景:窄标签 vs 宽标签)
        xs = [p.getViewBox().sceneBoundingRect().x() for p in st.plots]
        widths = [int(p.plot.getAxis("left").width()) for p in st.plots]
        print(f"绘图区左缘 x={['%.1f' % x for x in xs]} 偏差={abs(xs[0]-xs[1]):.2f}px")
        print(f"左轴固定宽={widths}")
        win.grab().save(str(ROOT / "tests" / "axis_align.png"))
        print("saved axis_align.png")
        loop.quit()

    QTimer.singleShot(2500, check)


win.state.channelsReady.connect(on_ch)
win.settings.setValue(
    "sel/" + (ROOT / "data" / "test.blf").resolve().as_posix(), "CLEARED")
win.state.open_paths([ROOT / "data" / "test.blf", ROOT / "data" / "test.dbc"])
QTimer.singleShot(15000, loop.quit)
loop.exec()
print("done")
