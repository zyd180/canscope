"""真实 449MB 数据 GUI 全流程验证(临时脚本)。"""
import os
import sys
import time
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
win.resize(1400, 850)
win.show()

up = Path(r"F:\TestPrj\blf-dbc-web-main\data\uploads")
blf = next(p for p in up.glob("*_L003.blf"))
dbc = next(p for p in up.glob("EEA*.dbc"))
progress_log = []
win.state.busyProgress.connect(lambda p: progress_log.append(p))
win.settings.setValue("sel/" + blf.as_posix(), "@cleared")

loop = QEventLoop()
t0 = time.perf_counter()


def on_ch(i, m):
    dt = time.perf_counter() - t0
    print(f"[LOAD] 完成: {dt:.1f}s, "
          f"通道={[(c['channel'], c['frames']) for c in i]}, "
          f"DBC报文={sum(len(v) for v in m.values())}")
    if progress_log:
        print(f"[PROGRESS] 回调 {len(progress_log)} 次, "
              f"first={progress_log[0]:.2f}, last={progress_log[-1]:.2f}")
    print(f"[BUSYBAR] visible={win.busy_bar.isVisible()} "
          f"value={win.busy_bar.value()}")
    ch = win.state.stats["channels"][0]["channel"]
    win.state.toggle_signal(0x21, ch, "ACU_3_CRC1")
    QTimer.singleShot(8000, loop.quit)


win.state.channelsReady.connect(on_ch)
win.state.open_paths([blf, dbc])
QTimer.singleShot(600000, loop.quit)
loop.exec()

es = win.state.signals_list[0] if win.state.signals_list else None
print(f"[SIGNAL] {es.key if es else None}: {len(es.times) if es else 0} 点")
win.grab().save(str(ROOT / "tests" / "gui_realdata.png"))
print("[SAVE] tests/gui_realdata.png")
