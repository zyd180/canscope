"""诊断:树点击链路 + 保存按钮渲染。"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

out = []


def log(m):
    out.append(str(m))


from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from gui.theme import QSS  # noqa: E402

QMessageBox.warning = staticmethod(lambda *a, **k: log(f"[MODAL] {a[2] if len(a) > 2 else a}"))
QMessageBox.critical = staticmethod(lambda *a, **k: log(f"[MODAL] {a}"))

app = QApplication(sys.argv)
app.setOrganizationName("canscope")
app.setApplicationName("CANScope")
app.setStyleSheet(QSS)

from gui.main_window import MainWindow  # noqa: E402
from gui.message_tree import KIND_ROLE, FID_ROLE, CH_ROLE, NAME_ROLE  # noqa: E402

win = MainWindow()
win.resize(1500, 900)
win.show()

blf = ROOT / "data" / "test.blf"
dbc = ROOT / "data" / "test.dbc"
# 清掉记忆,自己管理选中
win.settings.setValue(f"sel/{blf.as_posix()}", "CLEARED")

loop = QEventLoop()


def on_ch(_i, _m):
    log("channelsReady")
    QTimer.singleShot(300, click_test)


def click_test():
    tree = win.tree_panel.tree
    target = None
    stack = [tree.invisibleRootItem()]
    while stack:
        it = stack.pop()
        if it.data(0, KIND_ROLE) == "signal" and it.data(0, NAME_ROLE) == "VehicleSpeed":
            target = it
            break
        for i in range(it.childCount()):
            stack.append(it.child(i))
    from PySide6.QtCore import Qt
    enabled = bool(target.flags() & Qt.ItemIsEnabled) if target else None
    log(f"target={target is not None} enabled={enabled}")
    if target:
        tree.itemClicked.emit(target, 0)   # 模拟点击
        QTimer.singleShot(1200, verify)
    else:
        verify()


def verify():
    ok1 = len(win.state.signals_list) == 1
    ok2 = len(win.sidebar._rows) == 1
    log(f"signals={[(s.name, s.channel) for s in win.state.signals_list]}")
    log(f"sidebar_rows={len(win.sidebar._rows)}")
    win.grab().save(str(ROOT / "tests" / "drawer_check.png"))
    log("saved drawer_check.png")
    loop.quit()
    globals()["FAIL"] = not (ok1 and ok2)


FAIL = False


def shot():
    from PySide6.QtWidgets import QDialog
    for d in win.findChildren(QDialog):
        d.close()   # 关闭配置弹窗,结束其嵌套事件循环
    app.processEvents()
    win.grab().save(str(ROOT / "tests" / "drawer_check.png"))
    log("saved drawer_check.png")
    loop.quit()


win.state.channelsReady.connect(on_ch)
win.state.errorRaised.connect(lambda e: log(f"ERROR {e}"))
win.state.open_paths([blf, dbc])
QTimer.singleShot(8000, loop.quit)
loop.exec()

p = ROOT / "tests" / "diag_result.txt"
p.write_text("\n".join(out), encoding="utf-8")
print(f"TREE-CLICK {'PASS' if not FAIL else 'FAIL'}")
sys.exit(1 if FAIL else 0)
