"""事件级诊断:向视口发送合成事件,验证缩放/平移/锚点链路。"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QEvent, QEventLoop, QPoint, QPointF, Qt, QTimer  # noqa: E402
from PySide6.QtGui import QMouseEvent, QWheelEvent  # noqa: E402
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

blf = ROOT / "data" / "test.blf"
dbc = ROOT / "data" / "test.dbc"
win.settings.setValue(f"sel/{blf.as_posix()}", "CLEARED")

loop = QEventLoop()
out = []


def on_ch(_i, _m):
    win.state.channelsReady.disconnect(on_ch)
    ch = win.state.stats["channels"][0]["channel"]
    win.state.toggle_signal(291, ch, "EngineSpeed")

    def go():
        st = win.scope_stack
        plot = st.plots[0]
        vp = plot.plot.viewport()
        st.set_xrange(0, 9.99)
        out.append(f"初始 xr={plot.get_xrange()}")

        # 1) 普通滚轮(新交互:缩放)
        ev = QWheelEvent(QPointF(300, 100), QPointF(win.mapToGlobal(QPoint(300, 100))),
                         QPoint(0, 120), QPoint(0, 120), Qt.NoButton,
                         Qt.NoModifier, Qt.NoScrollPhase, False)
        app.sendEvent(vp, ev)
        out.append(f"普通滚轮后 xr={plot.get_xrange()}(应缩小)")

        # 1b) Shift+滚轮(页面滚动,xr 不变)
        ev2 = QWheelEvent(QPointF(300, 100), QPointF(win.mapToGlobal(QPoint(300, 100))),
                          QPoint(0, 120), QPoint(0, 120), Qt.NoButton,
                          Qt.ShiftModifier, Qt.NoScrollPhase, False)
        app.sendEvent(vp, ev2)
        out.append(f"Shift滚轮后 xr={plot.get_xrange()}(应不变)")

        # 2) 拖拽平移:按下→向左移→释放(x0>0 才有位移空间)
        st.set_xrange(2.0, 7.0)
        out.append(f"拖拽前 xr={plot.get_xrange()}")
        pr = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(400, 100),
                         Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        app.sendEvent(vp, pr)
        for dx in (10, 20, 30):
            mv = QMouseEvent(QEvent.Type.MouseMove, QPointF(400 + dx, 100),
                             Qt.NoButton, Qt.LeftButton, Qt.NoModifier)
            app.sendEvent(vp, mv)
        rl = QMouseEvent(QEvent.Type.MouseButtonRelease, QPointF(430, 100),
                         Qt.LeftButton, Qt.NoButton, Qt.NoModifier)
        app.sendEvent(vp, rl)
        out.append(f"拖拽后 xr={plot.get_xrange()}")

        # 4) Shift+单击 → 锚点
        pr2 = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(200, 100),
                          Qt.LeftButton, Qt.LeftButton, Qt.ShiftModifier)
        app.sendEvent(vp, pr2)
        rl2 = QMouseEvent(QEvent.Type.MouseButtonRelease, QPointF(200, 100),
                          Qt.LeftButton, Qt.NoButton, Qt.ShiftModifier)
        app.sendEvent(vp, rl2)
        out.append(f"Shift单击后 anchor={st.anchor}")

        loop.quit()

    QTimer.singleShot(400, go)


win.state.channelsReady.connect(on_ch)
win.state.errorRaised.connect(lambda e: out.append(f"ERROR {e}"))
win.state.open_paths([blf, dbc])
QTimer.singleShot(15000, loop.quit)
loop.exec()

p = ROOT / "tests" / "event_diag.txt"
p.write_text("\n".join(out), encoding="utf-8")
print("DONE")
