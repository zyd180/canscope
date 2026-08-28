"""二分:真实子控件组合 × 中央分割器 maxH。"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "windows")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import (QApplication, QLabel, QSplitter, QTabWidget,
                               QToolButton, QVBoxLayout, QWidget)  # noqa: E402

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


def build(name, with_tree, with_sidebar, with_scope, with_tabs, with_playbar):
    win = QWidget()
    win.resize(1500, 900)
    lay = QVBoxLayout(win)
    lay.setContentsMargins(0, 0, 0, 0)
    sp = QSplitter(Qt.Horizontal)
    if with_tree:
        sp.addWidget(MessageTree())
    strip = QToolButton()
    strip.setFixedWidth(14)
    sp.addWidget(strip)
    right = QSplitter(Qt.Vertical)
    cw = QWidget()
    cl = QVBoxLayout(cw)
    cl.setContentsMargins(0, 0, 0, 0)
    if with_playbar:
        pb = PlayBar()
        pb.setMaximumHeight(40)
        cl.addWidget(pb)
    if with_sidebar or with_scope:
        ca = QSplitter(Qt.Horizontal)
        if with_sidebar:
            ca.addWidget(SignalSidebar())
        if with_scope:
            ca.addWidget(ScopeStack())
        cl.addWidget(ca, 1)
    right.addWidget(cw)
    if with_tabs:
        tw = QTabWidget()
        tw.addTab(QLabel("trace page"), "Trace")
        right.addWidget(tw)
    sp.addWidget(right)
    lay.addWidget(sp)
    win.show()
    res = {"maxH": sp.maximumHeight()}


    def check():
        res["maxH"] = sp.maximumHeight()
        res["h"] = sp.height()
        loop.quit()

    QTimer.singleShot(600, check)
    loop2 = QEventLoop()
    loop = loop2
    QTimer.singleShot(5000, loop2.quit)
    loop2.exec()
    results.append(f"{name}: maxH={res['maxH']} h={res.get('h')}")


build("全组合", 1, 1, 1, 1, 1)
build("无树", 0, 1, 1, 1, 1)
build("无侧栏", 1, 0, 1, 1, 1)
build("无示波器", 1, 1, 0, 1, 1)
build("无页签", 1, 1, 1, 0, 1)
build("无播放条", 1, 1, 1, 1, 0)
build("仅树+页签", 1, 0, 0, 1, 0)
build("仅侧栏+示波器", 0, 1, 1, 0, 0)

p = ROOT / "tests" / "bisect2_result.txt"
p.write_text("\n".join(results), encoding="utf-8")
print("DONE")
