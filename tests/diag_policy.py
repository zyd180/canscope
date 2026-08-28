"""验证 Expanding 策略修复中央分割器高度。"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "windows")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import (QApplication, QLabel, QMainWindow, QSizePolicy,
                               QSplitter, QStatusBar, QTabWidget, QToolBar,
                               QToolButton, QVBoxLayout, QWidget)  # noqa: E402

from gui.theme import QSS  # noqa: E402
from gui.message_tree import MessageTree  # noqa: E402

app = QApplication(sys.argv)
app.setStyleSheet(QSS)

win = QMainWindow()
tb = QToolBar()
tb.addAction("A")
win.addToolBar(tb)

sp = QSplitter(Qt.Horizontal)
strip = QToolButton()
strip.setFixedWidth(14)
sp.addWidget(MessageTree())
sp.addWidget(strip)
sp.addWidget(QLabel("right"))
sp.setSizes([360, 14, 1040])
sp.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
win.setCentralWidget(sp)
win.setStatusBar(QStatusBar())
win.resize(1500, 900)
win.show()

print(f"修复后: sp h = {sp.height()} maxH = {sp.maximumHeight()} "
      f"vPolicy = {sp.sizePolicy().verticalPolicy()}")
