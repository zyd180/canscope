"""验证:树面板 minH 与中央分割器 maxH 的关系。"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "windows")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import (QApplication, QLabel, QMainWindow, QSplitter,
                               QStatusBar, QToolBar, QToolButton)  # noqa: E402

from gui.theme import QSS  # noqa: E402
from gui.message_tree import MessageTree  # noqa: E402

app = QApplication(sys.argv)
app.setStyleSheet(QSS)

for min_h in (None, 300, 500):
    win = QMainWindow()
    tb = QToolBar()
    tb.addAction("A")
    win.addToolBar(tb)
    sp = QSplitter(Qt.Horizontal)
    strip = QToolButton()
    strip.setFixedWidth(14)
    tree = MessageTree()
    if min_h:
        tree.setMinimumHeight(min_h)
    sp.addWidget(tree)
    sp.addWidget(strip)
    sp.addWidget(QLabel("right"))
    win.setCentralWidget(sp)
    win.setStatusBar(QStatusBar())
    win.resize(1500, 900)
    win.show()
    print(f"tree minH={min_h}: sp h={sp.height()} sp maxH={sp.maximumHeight()} "
          f"tree minSizeHint={tree.minimumSizeHint().height()}")
    win.close()

print("done")
