"""对照实验:定位 maxH 钳制的触发条件。"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "windows")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt, QTimer  # noqa: E402
from PySide6.QtWidgets import (QApplication, QLabel, QMainWindow, QSplitter,
                               QStatusBar, QToolBar, QTreeWidget)  # noqa: E402

app = QApplication(sys.argv)

results = []


def build(name, real_tree, with_toolbar, with_status):
    win = QMainWindow()
    if with_toolbar:
        tb = QToolBar()
        tb.addAction("A")
        win.addToolBar(tb)
    sp = QSplitter(Qt.Horizontal)
    if real_tree:
        left = QTreeWidget()
    else:
        left = QLabel("tree")
    sp.addWidget(left)
    sp.addWidget(QLabel("|"))
    right = QSplitter(Qt.Vertical)
    cw = QWidget()
    cl = QVBoxLayout(cw)
    cl.addWidget(QLabel("playbar"))
    cl.addWidget(QLabel("charts"))
    right.addWidget(cw)
    tabs = QTabWidget()
    tabs.addTab(QLabel("trace"), "T")
    right.addWidget(tabs)
    sp.addWidget(right)
    win.setCentralWidget(sp)
    if with_status:
        win.setStatusBar(QStatusBar())
    win.resize(1500, 900)
    win.show()

    def check():
        results.append(f"{name}: sp h={sp.height()} maxH={sp.maximumHeight()} "
                       f"minSizeHint={sp.minimumSizeHint().height()}")
        loop.quit()

    QTimer.singleShot(400, check)
    loop2 = QEventLoop()
    loop = loop2
    QTimer.singleShot(3000, loop2.quit)
    loop2.exec()
    win.close()


from PySide6.QtCore import QEventLoop  # noqa: E402

build("哑树+工具栏+状态栏", 0, 1, 1)
build("真树+工具栏+状态栏", 1, 1, 1)
build("真树+无工具栏+无状态栏", 1, 0, 0)
build("真树+仅状态栏", 1, 0, 1)
build("真树+仅工具栏", 1, 1, 0)

p = ROOT / "tests" / "bisect4_result.txt"
p.write_text("\n".join(results), encoding="utf-8")
print("DONE")
