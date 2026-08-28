"""GUI 冒烟测试(M4):回放模式 — 播放/暂停/seek/变速/播完/停止/信号变更自动停。

运行: python tests/smoke_m4.py(默认 offscreen)
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from gui.theme import QSS  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        fails.append(name)


def wait_for(cond_fn, timeout_ms=8000):
    loop = QEventLoop()
    t = QTimer()
    t.timeout.connect(lambda: cond_fn() and loop.quit())
    t.start(20)
    QTimer.singleShot(timeout_ms, loop.quit)
    loop.exec()
    t.stop()


def main() -> int:
    blf = ROOT / "data" / "test.blf"
    dbc = ROOT / "data" / "test.dbc"

    app = QApplication(sys.argv)
    app.setOrganizationName("canscope")
    app.setApplicationName("CANScope")
    app.setStyleSheet(QSS)

    from gui.main_window import MainWindow
    win = MainWindow()
    win.show()

    ready = {"ok": False}

    def on_channels(_i, _m):
        ready["ok"] = True

    win.state.channelsReady.connect(on_channels)
    win.settings.setValue(f"sel/{blf.as_posix()}", "@cleared")
    win.state.open_paths([blf, dbc])

    def run_steps():
        if not ready["ok"]:
            QTimer.singleShot(50, run_steps)
            return
        try:
            steps(win)
        except Exception as e:
            import traceback
            traceback.print_exc()
            fails.append(f"exception:{e}")
        finish(win, app)

    QTimer.singleShot(100, run_steps)
    return app.exec()


def steps(win):
    s = win.state
    st = win.scope_stack
    pbc = win.pbc
    pb = win.playbar
    ch = s.stats["channels"][0]["channel"]

    s.toggle_signal(291, ch, "EngineSpeed")
    s.toggle_signal(292, ch, "VehicleSpeed")
    wait_for(lambda: len(s.signals_list) == 2)
    check("前置:2信号", len(s.signals_list) == 2)
    check("播放条启用", pb.isEnabled())

    # 1) 10x 速播放
    pbc.set_rate(10.0)
    pbc.play()
    wait_for(lambda: pbc.mode == "playing")
    check("进入播放", pbc.mode == "playing")
    check("x锁定全量", st.play_lock and st.get_xrange() == (0.0, 9.99),
          f"({st.get_xrange()})")
    check("按钮⏸", pb.btn_play.text() == "⏸")

    # 2) 曲线生长 + 诊断
    key_es = f"291|{ch}|EngineSpeed"
    wait_for(lambda: _grown(st, key_es), timeout_ms=5000)
    curve = _curve(st, key_es)
    n1 = len(curve.xData) if curve is not None and curve.xData is not None else 0
    check("曲线生长", n1 >= 50, f"({n1} 点)")
    check("诊断输出", pb.lbl_diag.text() != "", f"({pb.lbl_diag.text()!r})")
    check("进度条走动", pb.slider.value() > 0, f"({pb.slider.value()})")

    # 3) 暂停
    pbc.pause()
    check("暂停", pbc.mode == "paused" and pb.btn_play.text() == "▶")
    t_paused = pbc.current_t()
    wait_for(lambda: False, timeout_ms=150)   # 等 150ms
    check("暂停时间冻结", abs(pbc.current_t() - t_paused) < 0.05,
          f"({pbc.current_t():.3f} vs {t_paused:.3f})")

    # 4) seek 到 8s 继续
    pbc.seek(8.0)
    check("seek清空累积", len(pbc._data) == 0 or all(
        len(v["times"]) == 0 for v in pbc._data.values()))
    pbc.play()
    wait_for(lambda: pbc.mode == "ended", timeout_ms=6000)
    check("播完ended", pbc.mode == "ended")
    # EngineSpeed 为值表信号 → 静态阶梯线 2N-1=1999 点;VehicleSpeed 1000 点
    key_vs = f"292|{ch}|VehicleSpeed"
    es_n = len(_curve(st, key_es).xData)
    vs_n = len(_curve(st, key_vs).xData)
    check("ended恢复静态", not st.play_lock and es_n == 1999 and vs_n == 1000,
          f"(ES={es_n}, VS={vs_n})")

    # 5) ended 后重播 → 从 0 开始
    pbc.play()
    wait_for(lambda: pbc.mode == "playing")
    check("重播从0", pbc.current_t() < 2.0, f"(t={pbc.current_t():.2f})")

    # 6) 播放中变更信号集 → 自动复位
    s.toggle_signal(291, ch, "CoolantTemp")
    wait_for(lambda: len(s.signals_list) == 3)
    check("变更自动停", pbc.mode == "idle" and not st.play_lock)

    # 7) 停止按钮恢复静态
    pbc.play()
    wait_for(lambda: pbc.mode == "playing")
    pb.stopRequested.emit()
    wait_for(lambda: pbc.mode == "idle")
    check("停止恢复", not st.play_lock and pb.slider.value() == 0
          and len(_curve(st, key_es).xData) == 1999)


def _curve(stack, key):
    for p in stack.plots:
        if key in p._curves:
            return p._curves[key][0]
    raise KeyError(key)

    # 播放中截图(供人工查看)
    pbc.play()
    wait_for(lambda: pbc.mode == "playing")
    wait_for(lambda: _grown(st, key_es), timeout_ms=4000)


def _grown(stack, key):
    try:
        curve = _curve(stack, key)
    except KeyError:
        return False
    return (curve.xData is not None and len(curve.xData) > 50)


def finish(win, app):
    try:
        png = ROOT / "tests" / "gui_smoke_m4.png"
        win.grab().save(str(png))
        print(f"[SAVE] {png}")
    except Exception as e:
        print(f"[WARN] screenshot failed: {e}")
    ok = not fails
    print(f"[{'PASS' if ok else 'FAIL'}] M4 GUI smoke: {len(fails)} failed {fails if fails else ''}")
    app.exit(0 if ok else 1)


if __name__ == "__main__":
    sys.exit(main())
