"""验证:无 QSS 时 MessageTree 场景是否还有 maxH 钳制。"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "windows")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import (QApplication, QLabel, QMainWindow, QSplitter,
                               QStatusBar, QToolBar, QToolButton)  # noqa: E402

from gui.message_tree import MessageTree  # noqa: E402

use_qss = os.environ.get("USE_QSS") == "1"
app = QApplication(sys.argv)
if use_qss:
    from gui.theme import QSS  # noqa: E402
    app.setStyleSheet(QSS)

win = QMainWindow()
tb = QToolBar()
tb.addAction("A")
win.addToolBar(tb)
sp = QSplitter(Qt.Horizontal)
strip = QToolButton()
strip.setFixedWidth(14)
if os.environ.get("USE_SPLITTER") == "1":
    sp.addWidget(MessageTree())
    sp.addWidget(strip)
    sp.addWidget(QLabel("right"))
    win.setCentralWidget(sp)
else:
    win.setCentralWidget(MessageTree())   # 不经分割器,直接作中央部件
win.setStatusBar(QStatusBar())
win.resize(1500, 900)
win.show()
w = sp if os.environ.get("USE_SPLITTER") == "1" else win.centralWidget()
print(f"USE_QSS={use_qss} USE_SPLITTER={os.environ.get('USE_SPLITTER')}: "
      f"h = {w.height()} maxH = {w.maximumHeight()} "
      f"minSizeHint = {w.minimumSizeHint().height()}")
