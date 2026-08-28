"""诊断:主窗口各区域几何尺寸(定位底部空白)。"""
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
out = []


def dump():
    sp = win._central_splitter
    out.append(f"window={win.width()}x{win.height()}")
    out.append(f"central is sp: {win.centralWidget() is sp}")
    out.append(f"sp geo={sp.geometry()} sizeHint={sp.sizeHint()} "
               f"maxH={sp.maximumHeight()} "
               f"vPolicy={sp.sizePolicy().verticalPolicy()}")
    out.append(f"central_splitter geo={sp.geometry()} sizes={sp.sizes()}")
    right = sp.widget(2)
    out.append(f"right geo={right.geometry()} sizes={right.sizes()} "
               f"vPolicy={right.sizePolicy().verticalPolicy()}")
    cw = right.widget(0)
    tabs = right.widget(1)
    out.append(f"chart_wrap geo={cw.geometry()}")
    out.append(f"tabs geo={tabs.geometry()}")
    out.append(f"tree geo={win.tree_panel.geometry()} visible={win.tree_panel.isVisible()}")
    loop.quit()


win.state.channelsReady.connect(lambda _i, _m: QTimer.singleShot(800, dump))
win.settings.setValue(
    "sel/" + (ROOT / "data" / "test.blf").resolve().as_posix(), "CLEARED")
win.state.open_paths([ROOT / "data" / "test.blf", ROOT / "data" / "test.dbc"])
QTimer.singleShot(15000, loop.quit)
loop.exec()

p = ROOT / "tests" / "geo_result.txt"
p.write_text("\n".join(out), encoding="utf-8")
print("DONE")
