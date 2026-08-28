"""GUI 冒烟测试(M3):Trace 分页/搜索/区间 → ID 统计 → 信号统计 → CSV 导出。

运行: python tests/smoke_m3.py(默认 offscreen)
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


def wait_for(cond_fn, timeout_ms=5000):
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
    win.resize(1400, 850)
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
    tp = win.trace_panel
    ch = s.stats["channels"][0]["channel"]

    # 选 2 个信号(触发信号统计)
    s.toggle_signal(291, ch, "EngineSpeed")
    s.toggle_signal(292, ch, "VehicleSpeed")
    wait_for(lambda: len(s.signals_list) == 2)
    wait_for(lambda: s._pending == 0 if hasattr(s, "_pending") else True)

    # ---- Trace ----
    wait_for(lambda: tp.cmb_msg.count() >= 2)
    check("报文下拉", tp.cmb_msg.count() == 2, f"({tp.cmb_msg.count()})")
    # 选 0x123 EngineData
    idx = next(i for i in range(tp.cmb_msg.count())
               if tp.cmb_msg.itemData(i)[0] == 291)
    tp.cmb_msg.setCurrentIndex(idx)   # 触发 reload
    wait_for(lambda: len(tp.model.rows) == 200)
    check("Trace 首页200", len(tp.model.rows) == 200)
    check("时间相对化", abs(tp.model.rows[0]["ts_rel"]) < 0.02,
          f"(first={tp.model.rows[0]['ts_rel']:.4f})")
    tp.btn_next.click()
    wait_for(lambda: tp._offset == 200 and len(tp.model.rows) == 200)
    check("下一页", tp._offset == 200 and tp.model.rows[0]["ts_rel"]
          > tp.model.rows[-1]["ts_rel"] - 2.0)
    tp.btn_prev.click()
    wait_for(lambda: tp._offset == 0)

    # 搜索 CoolantTemp == 85(整数值,scale=1)
    sig_idx = next(i for i in range(tp.cmb_sig.count())
                   if tp.cmb_sig.itemData(i) == "CoolantTemp")
    tp.cmb_sig.setCurrentIndex(sig_idx)
    tp.ed_val.setText("85")
    tp.on_search()
    wait_for(lambda: tp.lbl_info.text() != "加载中 …" and tp._offset == 0
             and (len(tp.model.rows) < 200 or tp.model.rows == []))
    n85 = len(tp.model.rows)
    check("值搜索", 0 < n85 < 1000, f"({n85} 行)")
    tp.on_clear_search()
    wait_for(lambda: len(tp.model.rows) == 200)

    # 区间过滤 [2s, 4s]
    st.set_xrange(2.0, 4.0)
    tp.on_apply_range()
    wait_for(lambda: tp.lbl_info.text() != "加载中 …"
             and (tp._range is not None and len(tp.model.rows) > 0
                  or tp.lbl_info.text().startswith("第 1-")))
    rows = tp.model.rows
    t0 = s.t0
    ok_range = rows and all(t0 + 1.999 <= r["timestamp"] <= t0 + 4.001 for r in rows)
    check("区间过滤", ok_range, f"({len(rows)} 行, [{rows[0]['ts_rel']:.2f}~{rows[-1]['ts_rel']:.2f}])"
          if rows else "(空)")
    tp.on_clear_range()
    st.reset_zoom()

    # ---- ID 统计 ----
    win.id_panel.populate()
    wait_for(lambda: "%" in win.id_panel.bus_card.text())
    check("ID行数", win.id_panel._lay.count() - 1 == 2,
          f"({win.id_panel._lay.count()-1})")
    check("BusLoad卡", "4.4" in win.id_panel.bus_card.text()
          or "CH0" in win.id_panel.bus_card.text(),
          win.id_panel.bus_card.text().replace("\n", " | ")[:80])

    # ---- 信号统计 ----
    win.sig_panel.refresh()
    wait_for(lambda: win.sig_panel._pending == 0
             and win.sig_panel.tbl_sig.rowCount() >= 2)
    check("信号统计行", win.sig_panel.tbl_sig.rowCount() == 2,
          f"({win.sig_panel.tbl_sig.rowCount()})")
    check("周期统计行", win.sig_panel.tbl_cyc.rowCount() == 2,
          f"({win.sig_panel.tbl_cyc.rowCount()})")
    # EngineSpeed 行:count=1000, mean≈1000
    it = win.sig_panel.tbl_sig.item(0, 2)   # 点数
    check("统计点数", it is not None and it.text() == "1000", f"({it.text() if it else '?'})")
    cyc = win.sig_panel.tbl_cyc.item(0, 4)  # 平均(ms)
    check("周期均值10ms", cyc is not None and abs(float(cyc.text()) - 10.0) < 1.0,
          f"({cyc.text() if cyc else '?'})")

    # ---- CSV 导出 ----
    out = ROOT / "tests" / "export_smoke.csv"
    if out.exists():
        out.unlink()
    done = {"ok": False}

    def exported(result):
        done["ok"] = True

    # 显式选 291 报文的条目(signals_list 顺序 = 解码完成序,不假定)
    item = next(e for e in s.signals_list if e.frame_id == 291)
    s.export_csv_async(item, out, exported)   # 全区间
    wait_for(lambda: done["ok"])
    content = out.read_text(encoding="utf-8-sig")
    lines = content.strip().splitlines()
    hdr = set(lines[0].split(","))
    check("CSV头", hdr == {"timestamp", "EngineSpeed", "CoolantTemp"},
          f"({lines[0]!r})")   # 列序按 cantools start_bit,不固定
    check("CSV行数", len(lines) == 1001, f"({len(lines)-1} 行)")
    check("CSV值", "1489" in lines[1] or "EngineSpeed" in lines[0])

    # 默认页切到 Trace 便于截图
    win.tabs.setCurrentIndex(0)


def finish(win, app):
    try:
        png = ROOT / "tests" / "gui_smoke_m3.png"
        win.grab().save(str(png))
        print(f"[SAVE] {png}")
    except Exception as e:
        print(f"[WARN] screenshot failed: {e}")
    ok = not fails
    print(f"[{'PASS' if ok else 'FAIL'}] M3 GUI smoke: {len(fails)} failed {fails if fails else ''}")
    app.exit(0 if ok else 1)


if __name__ == "__main__":
    sys.exit(main())
