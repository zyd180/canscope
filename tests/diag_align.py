"""验证:侧栏表头/值列对齐 + 树折叠/展开。"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "windows")
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
win.resize(1500, 900)
win.show()
loop = QEventLoop()
out = []


def on_ch(_i, _m):
    ch = win.state.stats["channels"][0]["channel"]
    win.state.toggle_signal(291, ch, "EngineSpeed")
    win.state.toggle_signal(292, ch, "VehicleSpeed")

    def check():
        sb = win.sidebar
        # 表头标签与第一行值列的 x 坐标对齐(右缘对齐即可)
        row0 = sb._rows[0]
        ha = sb.lbl_a.mapTo(sb, sb.lbl_a.rect().topRight()).x()
        va = row0.lbl_anchor.mapTo(sb, row0.lbl_anchor.rect().topRight()).x()
        hc = sb.lbl_c.mapTo(sb, sb.lbl_c.rect().topRight()).x()
        vc = row0.lbl_cursor.mapTo(sb, row0.lbl_cursor.rect().topRight()).x()
        out.append(f"表头锚点右缘={ha} 行锚点右缘={va} 偏差={abs(ha-va)}px")
        out.append(f"表头光标右缘={hc} 行光标右缘={vc} 偏差={abs(hc-vc)}px")
        # 折叠
        win._toggle_tree()
        out.append(f"折叠后: tree_visible={win.tree_panel.isVisible()} "
                   f"strip={win.tree_strip.text()!r} "
                   f"sizes={win._central_splitter.sizes()}")
        win.grab().save(str(ROOT / "tests" / "tree_collapsed.png"))
        # 展开
        win._toggle_tree()
        out.append(f"展开后: tree_visible={win.tree_panel.isVisible()} "
                   f"strip={win.tree_strip.text()!r} "
                   f"sizes={win._central_splitter.sizes()}")
        win.grab().save(str(ROOT / "tests" / "tree_expanded.png"))
        loop.quit()

    QTimer.singleShot(2500, check)


win.state.channelsReady.connect(on_ch)
win.settings.setValue(
    "sel/" + (ROOT / "data" / "test.blf").resolve().as_posix(), "CLEARED")
win.state.open_paths([ROOT / "data" / "test.blf", ROOT / "data" / "test.dbc"])
QTimer.singleShot(20000, loop.quit)
loop.exec()

p = ROOT / "tests" / "align_result.txt"
p.write_text("\n".join(out), encoding="utf-8")
print("DONE")
