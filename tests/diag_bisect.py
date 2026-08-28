"""二分定位:哪个构造步骤给中央分割器设了 maxH=378。"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "windows")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)
app.setOrganizationName("canscope")
app.setApplicationName("CANScope")

import gui.main_window as mw  # noqa: E402

ORIG_WIRE = mw.MainWindow._wire
ORIG_BODY = mw.MainWindow._build_body
ORIG_STATUS = mw.MainWindow._build_statusbar


def build(skip):
    mw.MainWindow._wire = (lambda self: None) if "wire" in skip else ORIG_WIRE
    mw.MainWindow._build_body = (lambda self: None) if "body" in skip else ORIG_BODY
    mw.MainWindow._build_statusbar = (lambda self: None) if "status" in skip else ORIG_STATUS
    win = mw.MainWindow()
    win.resize(1500, 900)
    win.show()
    mw.MainWindow._wire = ORIG_WIRE
    mw.MainWindow._build_body = ORIG_BODY
    mw.MainWindow._build_statusbar = ORIG_STATUS
    sp = getattr(win, "_central_splitter", None)
    h = sp.maximumHeight() if sp else None
    win.close()
    return h


for skip in ([], ["wire"], ["status"], ["wire", "status"], ["body"]):
    print(f"skip={skip}: maxH={build(skip)}")
