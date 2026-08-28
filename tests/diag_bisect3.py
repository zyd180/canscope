"""二分:真实控件组合 × 中央分割器 maxH。"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "windows")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import (QApplication, QLabel, QMainWindow, QSplitter,
                               QStatusBar, QTabWidget, QToolBar, QToolButton,
                               QVBoxLayout, QWidget)  # noqa: E402

from gui.theme import QSS  # noqa: E402
from gui.message_tree import MessageTree  # noqa: E402
from gui.scope_stack import ScopeStack  # noqa: E402
from gui.signal_sidebar import SignalSidebar  # noqa: E402
from gui.playbar import PlayBar  # noqa: E402

app = QApplication(sys.argv)
app.setOrganizationName("canscope")
app.setApplicationName("CANScope")
app.setStyleSheet(QSS)

results = []


def build(name, tree_real, right_real):
    win = QMainWindow()
    tb = QToolBar()
    tb.addAction("A")
    win.addToolBar(tb)
    sp = QSplitter(Qt.Horizontal)
    strip = QToolButton()
    strip.setFixedWidth(14)
    sp.addWidget(strip)
    left = MessageTree() if tree_real else QLabel("tree")
    sp.addWidget(left)
    sp.addWidget(strip)
    right = QSplitter(Qt.Vertical)
    if right_real:
        sidebar = SignalSidebar()
        scope = ScopeStack()
        ca = QSplitter(Qt.Horizontal)
        ca.addWidget(sidebar)
        ca.addWidget(scope)
        cw = QWidget()
        cl = QVBoxLayout(cw)
        cl.setContentsMargins(0, 0, 0, 0)
        pb = PlayBar()
        pb.setMaximumHeight(40)
        cl.addWidget(pb)
        cl.addWidget(ca, 1)
        right.addWidget(cw)
        tabs = QTabWidget()
        tp = QLabel("trace")
        tabs.addTab(tp, "T")
        right.addWidget(tabs)
    else:
        right.addWidget(QLabel("right"))
    sp.addWidget(right)
    sp.setSizes([360, 14, 1040])
    win.setCentralWidget(sp)
    win.setStatusBar(QStatusBar())
    win.resize(1500, 900)
    win.show()
    results.append(f"{name}: maxH={sp.maximumHeight()} h={sp.height()}")
    win.close()


build("真实树+哑右", 1, 0)
build("哑树+真实右", 0, 1)
build("全真实", 1, 1)

p = ROOT / "tests" / "bisect3_result.txt"
p.write_text("\n".join(results), encoding="utf-8")
print("DONE")
