"""复现实验:windowed(PyInstaller)下 sys.stdout/stderr=None 时的自动选信号。"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

# 模拟 PyInstaller --windowed:无控制台
sys.stdout = None
sys.stderr = None

from PySide6.QtCore import QEventLoop, QSettings, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from gui.theme import QSS  # noqa: E402

qs_dir = str(__import__("pathlib").Path(__file__).resolve().parent / "qsettings_rep")
app = QApplication(sys.argv)
app.setOrganizationName("canscope")
app.setApplicationName("CANScope")
QSettings.setDefaultFormat(QSettings.IniFormat)
QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, qs_dir)
app.setStyleSheet(QSS)

from gui.main_window import MainWindow  # noqa: E402
from pathlib import Path  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
win = MainWindow()
win.show()

blf = ROOT / "data" / "test.blf"
dbc = ROOT / "data" / "test.dbc"
win.settings.setValue(f"sel/{blf.as_posix()}", "")   # 模拟无记录 → 自动选

loop = QEventLoop()
log = []


def on_ch(_i, _m):
    log.append(f"channelsReady, auto={win.state.first_auto_selection()}")
    QTimer.singleShot(2500, loop.quit)


def on_sigchg():
    log.append(f"signalsChanged n={len(win.state.signals_list)}")


def on_err(e):
    log.append(f"ERROR {e}")


win.state.channelsReady.connect(on_ch)
win.state.signalsChanged.connect(on_sigchg)
win.state.errorRaised.connect(on_err)
win.state.open_paths([blf, dbc])
QTimer.singleShot(10000, loop.quit)
loop.exec()
log.append(f"FINAL signals={len(win.state.signals_list)}")
with open(ROOT / "tests" / "repro_result.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(log))
sys.exit(0)
