"""GUI 冒烟测试(M2):打开文件→选信号→多示波器→缩放钳制→光标读数→锚点→截图。

运行(需先有 data/test.blf): python tests/smoke_gui.py
默认 offscreen;真实平台: $env:QT_QPA_PLATFORM='windows'
退出码 0=通过。
"""
import bisect
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


def wait_for(cond_fn, timeout_ms=4000):
    """轮询等待异步解码/刷新完成(QEventLoop 处理信号投递)。"""
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
    assert blf.is_file() and dbc.is_file(), "请先运行 scripts/make_test_data.py"

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
    # 禁用三态自动选择,保证测试自身管理选中集
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
    ch = s.stats["channels"][0]["channel"]

    # 1) 三个信号 → 三个示波器(无空窗可复用,逐个新建)
    for fid, name in ((291, "EngineSpeed"), (291, "CoolantTemp"), (292, "VehicleSpeed")):
        s.toggle_signal(fid, ch, name)
    wait_for(lambda: len(s.signals_list) == 3)
    check("3信号3窗口", len(s.signals_list) == 3 and len(st.plots) == 3
          and s.plot_count == 3,
          f"(entries={len(s.signals_list)} plots={len(st.plots)})")
    check("每窗1曲线", all(len(p._curves) == 1 for p in st.plots))
    check("侧栏3行", len(win.sidebar._rows) == 3)
    key_es = f"291|{ch}|EngineSpeed"
    pid_es0 = next(e.plot_id for e in s.signals_list if e.key == key_es)

    # 2) 复制 EngineSpeed 到另一窗(复用已解码数据)
    other_pid = next(p for p in range(s.plot_count) if p != pid_es0)
    s.copy_to_plot(key_es, other_pid)
    check("复制到它窗", len(s.signals_list) == 4
          and len(st.plots[other_pid]._curves) == 2)

    # 3) 从原窗移除(chip ✕ 行为)
    s.remove_from_plot(key_es, pid_es0)
    check("单窗移除", len(s.signals_list) == 3
          and not any(e.key == key_es and e.plot_id == pid_es0
                      for e in s.signals_list))

    # 4) 缩放同步 + 钳制
    st.reset_zoom()
    check("初始范围", st._xr == [0.0, 9.99], f"({st._xr})")
    st.plots[0].zoom_at(5.0, 1 / 1.25)          # 放大 1.25x
    span = st._xr[1] - st._xr[0]
    check("缩放同步", abs(span - 9.99 / 1.25) < 0.01, f"(span={span:.3f})")
    check("全窗同步", all(abs(p.get_xrange()[0] - st._xr[0]) < 1e-6 for p in st.plots))
    for _ in range(30):                          # 连续放大 → 触底 0.5s
        st.plots[0].zoom_at(st._xr[0] + 0.1, 1 / 1.25)
    check("最小窗0.5s", abs((st._xr[1] - st._xr[0]) - 0.5) < 1e-6,
          f"(span={st._xr[1]-st._xr[0]:.4f})")
    st.plots[0].pan_by(100)                      # 右移越界 → 右缘钳制
    check("平移右钳制", abs(st._xr[1] - 9.99) < 1e-6, f"({st._xr})")
    st.plots[0].pan_by(-100)                     # 左移越界 → 左缘钳制
    check("平移左钳制", st._xr[0] == 0.0, f"({st._xr})")
    st.plots[0].zoom_at(5.0, 1e9)                # 缩小到极限 → 全量
    check("最大窗全量", st._xr == [0.0, 9.99], f"({st._xr})")

    # 5) 光标读数 + 同步竖线
    st._on_cursor(2.5)
    vals = [r.lbl_cursor.text() for r in win.sidebar._rows]
    check("光标值更新", all(v not in ("", "-") for v in vals), f"({vals})")
    check("竖线显示", all(p.cursor_line.isVisible() for p in st.plots))
    es = next(e for e in s.signals_list if e.key == key_es)
    i = bisect.bisect_left(es.times, 2.5)
    if i > 0 and (i >= len(es.times)
                  or abs(es.times[i - 1] - 2.5) < abs(es.times[i] - 2.5)):
        i -= 1
    expect = f"{es.values[i]:.4f}".rstrip("0").rstrip(".")
    row_es = next(r for r in win.sidebar._rows if r.item.key == key_es)
    check("最近邻取值", row_es.lbl_cursor.text().startswith(expect),
          f"(got={row_es.lbl_cursor.text()!r} expect~{expect})")

    # 6) 锚点测量 + 锚点值列
    st.toggle_anchor(2.0)
    win.sidebar.set_anchor(2.0)
    check("锚点设置", st.anchor == 2.0
          and all(p.anchor_line.isVisible() for p in st.plots))
    ja = min(bisect.bisect_left(es.times, 2.0), len(es.times) - 1)
    exp_a = f"{es.values[ja]:.4f}".rstrip("0").rstrip(".")
    check("锚点值列", row_es.lbl_anchor.text().startswith(exp_a),
          f"(got={row_es.lbl_anchor.text()!r} expect~{exp_a})")
    win._update_anchor_text(2.5)
    txt = win.lbl_anchor.text()
    check("Δ读数", "Δ0.500s" in txt and "Hz" in txt, f"({txt!r})")
    st.toggle_anchor(2.0)                        # 再击清除
    check("锚点清除", st.anchor is None and win.lbl_anchor.text() == "")

    # 7) 重置缩放按钮
    win.act_reset.trigger()
    check("重置缩放", st._xr == [0.0, 9.99])

    # 8) 清空(窗口保留)
    s.clear_all_signals()
    check("清空", len(s.signals_list) == 0 and len(win.sidebar._rows) == 0
          and all(len(p._curves) == 0 for p in st.plots))

    # 9) 清空后再选 → 复用空窗 0
    s.toggle_signal(291, ch, "EngineSpeed")
    s.toggle_signal(292, ch, "VehicleSpeed")
    wait_for(lambda: len(s.signals_list) == 2)
    pids = sorted(e.plot_id for e in s.signals_list)
    check("清空后复用空窗", pids == [0, 1], f"(pids={pids})")
    st.reset_zoom()


def finish(win, app):
    try:
        png = ROOT / "tests" / "gui_smoke.png"
        win.grab().save(str(png))
        print(f"[SAVE] {png}")
    except Exception as e:
        print(f"[WARN] screenshot failed: {e}")
    ok = not fails
    print(f"[{'PASS' if ok else 'FAIL'}] M2 GUI smoke: {len(fails)} failed {fails if fails else ''}")
    app.exit(0 if ok else 1)


if __name__ == "__main__":
    sys.exit(main())
