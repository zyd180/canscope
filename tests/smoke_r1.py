"""R1 图表与分析补强冒烟测试。

覆盖:
1.1 Y 轴量程控制     —— 双击锁定/恢复、菜单式锁定值跨刷新持久
1.2 区间框选统计     —— Ctrl+拖拽 RubberBand → LinearRegionItem + 统计浮层,
                        「应用本窗统计区间」写入统计页过滤
1.3 缩略导航条       —— 拖动平移、边缘改跨度、滚轮缩放、主图↔导航条双向同步
1.4 曲线临时显隐     —— chip 点击隐藏/恢复、样式变暗、跨刷新保持
1.5 示波器导出 PNG   —— pngExportRequested → 文件落盘且可加载

全部交互走真实事件路径(sendEvent 合成鼠标事件 / 真实请求信号),
遵循一期教训④:不直调内部渲染方法代替交互。
运行: python tests/smoke_r1.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import (QEvent, QEventLoop, QPoint, QPointF, QTimer,
                            Qt)  # noqa: E402
from PySide6.QtGui import QMouseEvent, QPixmap, QWheelEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

from gui.theme import QSS  # noqa: E402
from services.stats_service import local_range_stats  # noqa: E402

ZOOM_FACTOR_REF = 1.25

fails = []
win = None


def trace(m: str) -> None:
    if os.environ.get("R1_TRACE"):
        print(f"[trace] {m}", flush=True)


def check(name, cond, extra="", flush=False):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}", flush=True)
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


def proc_pending() -> None:
    """把排队的后台任务回调刷进来。"""
    for _ in range(30):
        QApplication.processEvents()


def _send_mouse(widget, ev_type: QEvent.Type, x, y, *, button=Qt.LeftButton,
                buttons=None, mods=Qt.KeyboardModifiers()) -> None:
    b = button if buttons is None else buttons
    ev = QMouseEvent(ev_type, QPointF(x, y), button, b, mods)
    QApplication.sendEvent(widget, ev)


def _vp_size(plot):
    vp = plot.plot.viewport()
    return int(vp.width()), int(vp.height())


def _dblclick(widget, x, y) -> None:
    _send_mouse(widget, QEvent.Type.MouseButtonDblClick, x, y)


def _find_chips(plot) -> dict:
    """{信号名: (chip_widget, name_label)}(排除色点 ● 与 ✕)。"""
    out: dict = {}
    for i in range(plot.chips.count()):
        it = plot.chips.itemAt(i)
        w = it.widget() if it else None
        if w is None:
            continue
        for lbl in w.findChildren(QLabel):
            if lbl.text() in ("●", "✕") or lbl.text().startswith("▎"):
                continue
            out.setdefault(lbl.text(), (w, lbl))
    return out


def _plot_of_key(key: str):
    for p in win.scope_stack.plots:
        if any(it.key == key and it.plot_id == p.plot_id
               for it in win.state.signals_list):
            return p
    return None


def main() -> int:
    blf = ROOT / "data" / "test.blf"
    dbc = ROOT / "data" / "test.dbc"
    assert blf.is_file() and dbc.is_file(), "请先运行 scripts/make_test_data.py"

    app = QApplication(sys.argv)
    app.setOrganizationName("canscope")
    app.setApplicationName("CANScope")
    app.setStyleSheet(QSS)

    from gui.main_window import MainWindow
    global win
    win = MainWindow()
    win.resize(1600, 900)
    win.show()

    def on_ch(_i, _m):
        win.state.channelsReady.disconnect(on_ch)
        ch = win.state.stats["channels"][0]["channel"]
        QTimer.singleShot(0, lambda: (run(ch), app.quit()))

    win.state.channelsReady.connect(on_ch)
    win.state.errorRaised.connect(lambda e: print("[ERROR]", e))
    win.settings.setValue(f"sel/{blf.as_posix()}", "CLEARED")   # 屏蔽三态恢复
    win.state.open_paths([blf, dbc])
    QTimer.singleShot(60000, app.quit)
    app.exec()
    return _finish()


def run(ch) -> None:
    s, st = win.state, win.scope_stack
    mini = win.minimap
    key_eng = f"291|{ch}|EngineSpeed"

    # ---------------- 前置 ----------------
    s.toggle_signal(291, ch, "EngineSpeed")
    s.toggle_signal(292, ch, "VehicleSpeed")
    wait_for(lambda: len(s.signals_list) == 2)
    check("前置:2信号", len(s.signals_list) == 2 and len(st.plots) == 2)
    check("前置:导航条就绪",
          mini.isVisibleTo(win) and abs(mini.duration - s.duration) < 1e-6,
          f"dur={mini.duration:.2f}")

    # ---------------- 1.1 Y 轴量程控制 ----------------
    p0 = st.plots[0]
    vw, vh = _vp_size(p0)
    _dblclick(p0.plot.viewport(), vw // 2, vh // 2)
    lock_rng = p0._y_lock
    check("双击→Y锁定", p0.y_locked and lock_rng is not None)
    check("锁定范围取自视图",
          lock_rng is not None and lock_rng[1] > lock_rng[0],
          f"{lock_rng[0]:.2f}~{lock_rng[1]:.2f}" if lock_rng else "-")
    _dblclick(p0.plot.viewport(), vw // 2, vh // 2)
    check("再双击→自动", not p0.y_locked)

    p0.set_y_mode(False, (100.0, 200.0))     # 菜单弹窗同款语义
    s.signalsChanged.emit()                  # 全量刷新重建曲线
    yr = p0.getViewBox().viewRange()[1]
    check("锁定跨刷新持久", abs(yr[0] - 100) < 1e-6 and abs(yr[1] - 200) < 1e-6,
          f"{yr[0]:.3f}~{yr[1]:.3f}")
    p0.set_y_mode(True)

    # ---------------- 1.4 chip 点击显隐 ----------------
    pe = _plot_of_key(key_eng)
    chips = _find_chips(pe)
    _chip_w, name_lbl = chips.get("EngineSpeed", (None, None))
    curve = pe._curves.get(key_eng)[0]
    check("chip 结构就绪", _chip_w is not None and name_lbl is not None)
    area_w = name_lbl.parentWidget()   # 「色点+图名」点击区(✕ 为平级兄弟)
    vis0 = bool(curve.isVisible())
    _send_mouse(area_w, QEvent.Type.MouseButtonPress, 5, 5)
    vis1 = bool(curve.isVisible())
    check("chip 点击→隐藏", vis0 and not vis1)
    check("隐藏样式变暗", "#5c6472" in name_lbl.styleSheet())
    _send_mouse(area_w, QEvent.Type.MouseButtonPress, 5, 5)
    check("再点→恢复显示", bool(curve.isVisible()))

    _send_mouse(area_w, QEvent.Type.MouseButtonPress, 5, 5)
    s.signalsChanged.emit()                  # 重建曲线 → 隐藏态必须保持
    proc_pending()
    check("隐藏跨刷新保持", not bool(curve.isVisible()))
    pe.show_all_curves()

    # ---------------- 1.2 区间框选统计 ----------------
    vp = p0.plot.viewport()
    xa, xb = int(vw * 0.35), int(vw * 0.65)
    ctrl = Qt.ControlModifier
    trace("press(ctrl)")
    _send_mouse(vp, QEvent.Type.MouseButtonPress, xa, vh // 2, mods=ctrl)
    trace("move1")
    _send_mouse(vp, QEvent.Type.MouseMove, int(vw * 0.42), vh // 2,
                buttons=Qt.LeftButton, mods=ctrl)
    trace("move2")
    _send_mouse(vp, QEvent.Type.MouseMove, xb, vh // 2,
                buttons=Qt.LeftButton, mods=ctrl)
    trace("release")
    _send_mouse(vp, QEvent.Type.MouseButtonRelease, xb, vh // 2,
                buttons=Qt.NoButton)
    trace("released")
    reg = p0.region_times()
    reg_ok = reg is not None and reg[1] > reg[0]
    check("框选生成区间", reg_ok,
          f"{tuple(round(v, 2) for v in reg) if reg else '-'}")
    html = p0._stats_text.toHtml() if p0._stats_text else ""
    check("统计浮层含信号名", "EngineSpeed" in html)

    win.tabs.setCurrentWidget(win.trace_panel)
    st.statsRangeApplyRequested.emit(st.plots.index(p0))   # 与右键菜单同一入口
    proc_pending()
    rng_txt = win.sig_panel.lbl_rng.text()
    btn_vis = win.sig_panel.btn_clear_rng.isVisibleTo(win.sig_panel)
    tab_is_stats = win.tabs.currentWidget() is win.sig_panel
    check("应用区间→统计页过滤", "仅统计" in rng_txt and btn_vis,
          f"{rng_txt} clear={btn_vis}")
    check("统计页已切前台", tab_is_stats)
    wait_for(lambda: win.sig_panel._pending <= 0
             and win.sig_panel.tbl_sig.rowCount() >= 1)
    check("过滤统计有结果", win.sig_panel.tbl_sig.rowCount() >= 1,
          f"rows={win.sig_panel.tbl_sig.rowCount()}")
    win.sig_panel.clear_range_filter()
    check("清除区间→恢复全量",
          not win.sig_panel.btn_clear_rng.isVisibleTo(win.sig_panel))

    p0.clear_region()
    check("清除统计浮层", p0.region_times() is None and p0._stats_text is None)

    # ---------------- 1.3 缩略导航条 ----------------
    mini.set_viewport(*st.get_xrange())
    rect = mini._plot_rect()
    cy = rect.center().y()

    def _mini_drag(x0_px: float, x1_px: float) -> None:
        _send_mouse(mini, QEvent.Type.MouseButtonPress, x0_px, cy)
        _send_mouse(mini, QEvent.Type.MouseMove, x1_px, cy,
                    buttons=Qt.LeftButton)
        _send_mouse(mini, QEvent.Type.MouseButtonRelease, x1_px, cy,
                    buttons=Qt.NoButton)

    def _mini_wheel(px_x: float) -> None:
        QApplication.sendEvent(mini, QWheelEvent(
            QPointF(px_x, cy),
            mini.mapToGlobal(QPoint(int(px_x), int(cy))),
            QPoint(0, 0), QPoint(0, 120), Qt.NoButton,
            Qt.KeyboardModifiers(),
            Qt.ScrollPhase.NoScrollPhase, False))

    xr0 = tuple(st.get_xrange())
    check("初始视口=全量", abs(xr0[0]) < 1e-6
          and abs(xr0[1] - s.duration) < 1e-6, f"{xr0[0]:.2f}~{xr0[1]:.2f}")

    # 先滚轮缩进局部窗口(全量窗口按语义不可平移/扩边)
    span_f = st.get_xrange()[1] - st.get_xrange()[0]
    _mini_wheel(rect.center().x())
    span_z = st.get_xrange()[1] - st.get_xrange()[0]
    check("滚轮缩放系数", abs(span_z * ZOOM_FACTOR_REF - span_f) < span_f * 0.08,
          f"{span_f:.2f}→{span_z:.2f}")

    # 局部窗口下:中部拖动平移
    _mini_drag(rect.center().x(), rect.center().x() + 45)
    xr1 = tuple(st.get_xrange())
    check("拖动平移视窗", xr1[0] > xr0[0] + 0.3
          and xr1[1] <= s.duration + 1e-6,
          f"x0 {xr0[0]:.2f}→{xr1[0]:.2f}")

    # 左缘抓取向左拖:跨度增大
    span_pre = xr1[1] - xr1[0]
    vl = mini._t_to_px(xr1[0])
    _mini_drag(vl + 3, vl - 24)
    xr2 = tuple(st.get_xrange())
    span_new = xr2[1] - xr2[0]
    check("边缘拖拽增跨度", span_new > span_pre + 0.1
          and xr2[0] < xr1[0],
          f"{span_pre:.2f}→{span_new:.2f}")

    st.reset_zoom()
    check("重置缩放双向同步", abs(mini._xr[0]) < 1e-6
          and abs(mini._xr[1] - s.duration) < 1e-6,
          f"{mini._xr[0]:.2f}~{mini._xr[1]:.2f}")

    item_eng = next((it for it in s.signals_list if it.key == key_eng), None)
    res = local_range_stats([item_eng], 0.0, float(s.duration))
    row0 = res["rows"][0] if res["rows"] else None
    check("local_range_stats 数值", row0 is not None and row0["count"] > 0
          and res["dt_s"] > 0, f"n={row0['count'] if row0 else '-'}")

    # ---------------- 1.5 导出 PNG ----------------
    png_path = Path(tempfile.gettempdir()) / "canscope_r1_export.png"
    if png_path.exists():
        png_path.unlink()
    import gui.main_window as mw_mod
    mw_mod.QFileDialog.getSaveFileName = staticmethod(
        lambda *a, **k: (str(png_path), "PNG (*.png)"))
    pid_e = list(st.plots).index(_plot_of_key(key_eng))
    st.pngExportRequested.emit(pid_e)
    proc_pending()
    pm_ok = png_path.exists() and png_path.stat().st_size > 2048
    pm = QPixmap(str(png_path)) if pm_ok else None
    check("导出 PNG 落盘可用", pm is not None and not pm.isNull(),
          f"size={png_path.stat().st_size if pm_ok else 0}B")


def _finish() -> int:
    print()
    if fails:
        print(f"FAILED: {fails}")
        return 1
    print("R1 SMOKE ALL PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
