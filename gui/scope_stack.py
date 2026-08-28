"""多示波器纵向堆叠容器:窗口生命周期 / x 轴范围同步 / 光标与锚点中继 / chip。

R1 增补:
- chip 点击(除 ✕)切换本窗曲线临时显隐
- 右键菜单扩展:显示全部曲线 / 锁定·恢复 Y 轴 / 统计区间应用与清除 / 导出 PNG
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QDoubleSpinBox,
                               QHBoxLayout, QLabel, QMenu, QPushButton,
                               QScrollArea, QVBoxLayout, QWidget)

from gui.scope_plot import (MAX_WINDOW_S, MIN_WINDOW_S, ZOOM_FACTOR, ScopePlot)

PLOT_H = 200   # 与 Web 版 .plot-item 高度一致


class _ChipNameClick(QObject):
    """「色点+图名」子容器点击过滤:左键按下即切换该曲线显隐。

    过滤器只安装在这一小块容器上(✕ 按钮是平级兄弟),不依赖任何
    子控件实时几何,重建/未刷布局时也判得准。
    """

    def __init__(self, plot: ScopePlot, key: str):
        super().__init__()
        self._plot = plot
        self._key = key

    def eventFilter(self, obj, ev) -> bool:
        if ev.type() == QEvent.Type.MouseButtonPress \
                and ev.button() == Qt.LeftButton:
            self._plot.toggle_visible(self._key)
            return True
        return False


class ScopeStack(QScrollArea):
    cursorMoved = Signal(float)          # 光标时间(已钳制)
    cursorLeft = Signal()
    anchorChanged = Signal(object)       # float | None
    xRangeChanged = Signal(float, float)
    itemRemoveRequested = Signal(str, int)   # (key, plot_id)
    itemCopyRequested = Signal(str, int)
    closePlotRequested = Signal(int)         # plot_id
    clearPlotRequested = Signal(int)         # plot_id(清空本窗信号)
    statsRangeApplyRequested = Signal(int)   # plot_id(把该窗统计区间写入统计页)
    pngExportRequested = Signal(int)         # plot_id(导出本窗 PNG,由主窗落盘)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)

        inner = QWidget()
        inner.setStyleSheet("background:#16181d;")
        self._lay = QVBoxLayout(inner)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(6)
        self._lay.addStretch(1)
        self.setWidget(inner)

        self.plots: list = []
        self.items: list = []
        self.duration: float = 0.0
        self._xr: list = [0.0, 1.0]
        self.anchor: float | None = None
        self.play_lock = False   # 播放中锁定 x 轴(固定全量范围)
        self.show_jitter = False
        self.jitter_marks: dict = {}    # {(frame_id, channel): 相对时间}
        self.ensure_plots(1)

    # ---------------- 窗口生命周期 ----------------

    def ensure_plots(self, n: int) -> None:
        while len(self.plots) < n:
            plot = ScopePlot(len(self.plots) + 1)
            plot.plot_id = len(self.plots)
            plot.setMinimumHeight(PLOT_H)
            plot.cursorHovered.connect(self._on_cursor)
            plot.cursorLeft.connect(self._on_cursor_left)
            plot.anchorToggled.connect(self.toggle_anchor)
            plot.xRangeEdited.connect(self._on_range_edited)
            plot.wheelScroll.connect(self._on_wheel_scroll)
            plot.addSignalRequested.connect(self._on_add_menu)
            plot.closeRequested.connect(self.closePlotRequested.emit)
            plot.contextMenuRequested.connect(
                lambda gp, p=plot: self._on_context_menu(gp, p))
            self.plots.append(plot)
            self._lay.insertWidget(self._lay.count() - 1, plot)

    def _prune_plots(self, keep: int) -> None:
        keep = max(1, keep)
        while len(self.plots) > keep:
            p = self.plots.pop()
            p.setParent(None)
            p.deleteLater()

    # ---------------- 数据刷新 ----------------

    def refresh(self, items: list, plot_count: int) -> None:
        """全量刷新(由 AppState.signalsChanged 驱动)。"""
        self.items = items or []
        groups: dict = {}
        for s in self.items:
            groups.setdefault(s.plot_id, []).append(s)
        needed = max(1, plot_count,
                     (max(groups) + 1) if groups else 1)
        self.ensure_plots(needed)
        self._prune_plots(needed)

        for idx, plot in enumerate(self.plots):
            plot.renumber(idx)   # 删除中间窗口后保持"示波器 N"连续
            its = groups.get(idx, [])
            plot.set_signals(its)
            # pyqtgraph 刷新曲线后可能重新计算轴宽,需在动态窗口刷新后再固定。
            if plot.plot.getAxis("left").width() != 72:
                plot.plot.getAxis("left").setWidth(72)
            plot.set_xrange(*self._xr)
            self._rebuild_chips(plot, idx, its)
        self._apply_jitter_marks()

    def _rebuild_chips(self, plot: ScopePlot, plot_id: int, its: list) -> None:
        plot.release_chips()   # 旧 chip 的标签登记一并作废
        while plot.chips.count():
            it = plot.chips.takeAt(0)
            w = it.widget()
            if w is not None:
                w.hide()          # 立即隐藏,deleteLater 延迟到事件循环
                w.deleteLater()
        for s in its:
            plot.chips.addWidget(self._make_chip(s, plot_id, plot))

    def _make_chip(self, s, plot_id: int, plot: ScopePlot) -> QWidget:
        chip = QWidget()
        chip.setStyleSheet(
            "QWidget{background:#23262e;border:1px solid #2c323d;border-radius:9px;}"
            "QLabel{background:transparent;border:none;}")
        lay = QHBoxLayout(chip)
        lay.setContentsMargins(7, 0, 4, 0)
        lay.setSpacing(4)

        # R1:「色点+图名」独立子容器承载点击显隐(✕ 是平级兄弟,互不干扰)
        name_area = QWidget()
        name_area.setCursor(Qt.PointingHandCursor)
        name_area.setStyleSheet("background:transparent;")
        area_lay = QHBoxLayout(name_area)
        area_lay.setContentsMargins(0, 0, 0, 0)
        area_lay.setSpacing(4)
        dot = QLabel("●")
        dot.setStyleSheet(f"color:{s.color};font-size:9px;border:none;background:transparent;")
        name = QLabel(s.name)
        name.setStyleSheet("color:#c9ced6;font-size:11px;border:none;background:transparent;")
        name.setToolTip("点击图名可临时隐藏该曲线")
        area_lay.addWidget(dot)
        area_lay.addWidget(name)

        x = QPushButton("✕")
        x.setFixedSize(16, 16)
        x.setToolTip("从本示波器移除")
        x.setStyleSheet(
            "QPushButton{background:transparent;border:none;color:#5c6472;"
            "font-size:10px;padding:0;}"
            "QPushButton:hover{color:#ff6b6b;}")
        x.clicked.connect(lambda _=False, k=s.key, p=plot_id:
                          self.itemRemoveRequested.emit(k, p))

        # 登记标签供 plot 回写显隐样式
        plot.register_chip(s.key, name, dot, s.color)
        plot._restyle_chip(s.key)
        filt = _ChipNameClick(plot, s.key)
        filt.setParent(name_area)   # 随 chip 销毁,重建不累积
        name_area.installEventFilter(filt)

        lay.addWidget(name_area)
        lay.addWidget(x)
        return chip

    def _on_add_menu(self, plot_id: int) -> None:
        """「+信号」:从已选信号复制到该窗(复用已解码数据)。"""
        in_plot = {s.key for s in self.items if s.plot_id == plot_id}
        candidates = []
        seen = set()
        for s in self.items:
            if s.key not in in_plot and s.key not in seen:
                candidates.append(s)
                seen.add(s.key)
        if not candidates:
            return
        menu = QMenu(self)
        for s in candidates:
            act = menu.addAction(f"● {s.name}")
            act.setData((s.key, plot_id))
        act = menu.exec(QCursor.pos())
        if act is not None:
            key, pid = act.data()
            self.itemCopyRequested.emit(key, pid)

    def _build_context_menu(self, plot: ScopePlot) -> QMenu:
        """构建示波器右键菜单(全中文,R1 扩展)。"""
        pid = plot.plot_id
        its = [s for s in self.items if s.plot_id == pid]
        menu = QMenu(self)
        act_add = menu.addAction("添加信号…")
        act_showall = menu.addAction("显示全部曲线")
        act_showall.setEnabled(plot.has_hidden)
        menu.addSeparator()
        if plot.y_locked:
            act_y = menu.addAction("恢复自动 Y 轴")
        else:
            act_y = menu.addAction("锁定 Y 轴…")
        menu.addSeparator()
        act_anchor = menu.addAction("清除测量锚点")
        act_reset = menu.addAction("重置缩放(全部窗口)")
        menu.addSeparator()
        reg = plot.region_times()
        act_apply_rng = menu.addAction("应用本窗统计区间 → 统计页")
        act_apply_rng.setEnabled(reg is not None)
        act_clear_rng = menu.addAction("清除本窗统计区间")
        act_clear_rng.setEnabled(reg is not None)
        act_png = menu.addAction("导出本窗图像 PNG…")
        menu.addSeparator()
        act_clear = menu.addAction("清除本窗信号")
        act_clear.setEnabled(bool(its))
        act_close = menu.addAction("关闭本示波器")
        act_close.setEnabled(len(self.plots) > 1)
        # 接线
        act_add.triggered.connect(lambda: self._on_add_menu(pid))
        act_showall.triggered.connect(plot.show_all_curves)
        act_y.triggered.connect(
            (lambda: plot.set_y_mode(True)) if plot.y_locked
            else (lambda: self._open_y_lock_dialog(plot)))
        act_anchor.triggered.connect(lambda: self.set_anchor(None))
        act_reset.triggered.connect(self.reset_zoom)
        act_apply_rng.triggered.connect(
            lambda: self.statsRangeApplyRequested.emit(pid))
        act_clear_rng.triggered.connect(plot.clear_region)
        act_png.triggered.connect(lambda: self.pngExportRequested.emit(pid))
        act_clear.triggered.connect(lambda: self.clearPlotRequested.emit(pid))
        act_close.triggered.connect(lambda: self.closePlotRequested.emit(pid))
        return menu

    def _open_y_lock_dialog(self, plot: ScopePlot) -> None:
        """手动锁定 Y 轴:预填当前锁定值/视图范围,确认后每窗独立生效。"""
        from PySide6.QtWidgets import QMessageBox
        cur_lo, cur_hi = plot.getViewBox().viewRange()[1]
        prefill = plot._y_lock if plot._y_lock else (cur_lo, cur_hi)

        dlg = QDialog(self)
        dlg.setWindowTitle(f"锁定 Y 轴 · 示波器 {plot.index}")
        lay = QVBoxLayout(dlg)
        lay.setSpacing(8)
        note = QLabel(f"对「示波器 {plot.index}」启用固定量程;\n"
                      "双击绘图区可随时在 自动 ↔ 锁定 间切换。")
        note.setStyleSheet("color:#8a93a3;")
        lay.addWidget(note)
        row_lo = QHBoxLayout(); row_lo.addWidget(QLabel("最小值"))
        sp_lo = QDoubleSpinBox(); sp_lo.setDecimals(6); sp_lo.setRange(-1e12, 1e12)
        sp_lo.setValue(float(prefill[0])); sp_lo.setMinimumWidth(140)
        row_lo.addWidget(sp_lo); lay.addLayout(row_lo)
        row_hi = QHBoxLayout(); row_hi.addWidget(QLabel("最大值"))
        sp_hi = QDoubleSpinBox(); sp_hi.setDecimals(6); sp_hi.setRange(-1e12, 1e12)
        sp_hi.setValue(float(prefill[1])); sp_hi.setMinimumWidth(140)
        row_hi.addWidget(sp_hi); lay.addLayout(row_hi)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText("锁定")
        btns.button(QDialogButtonBox.Cancel).setText("取消")
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)

        def _apply() -> None:
            lo, hi = float(sp_lo.value()), float(sp_hi.value())
            if hi - lo <= 1e-12:
                QMessageBox.warning(dlg, "CANScope", "最大值必须大于最小值")
                return
            plot.set_y_mode(False, (lo, hi))
            dlg.accept()

        btns.accepted.connect(_apply)
        dlg.exec()

    def _on_context_menu(self, gp, plot: ScopePlot) -> None:
        """示波器右键:弹出全中文菜单。"""
        self._build_context_menu(plot).exec(gp)

    # ---------------- x 轴范围(全局同步) ----------------

    def set_duration(self, dur: float) -> None:
        self.duration = max(0.0, float(dur or 0.0))
        self.set_xrange(0.0, self.duration if self.duration > 0 else 1.0)

    def set_xrange(self, x0: float, x1: float, clamp: bool = True) -> None:
        if clamp:
            x0, x1 = self._clamp(x0, x1)
        self._xr = [x0, x1]
        for p in self.plots:
            p.set_xrange(x0, x1)
        self.xRangeChanged.emit(x0, x1)

    def _clamp(self, x0: float, x1: float) -> tuple:
        dur = self.duration if self.duration > 0 else 1.0
        span = x1 - x0
        if span > dur or x0 < 0 or x1 > dur or span <= 0:
            if span >= dur:
                return 0.0, dur
        span = min(max(span, MIN_WINDOW_S), min(dur, MAX_WINDOW_S))
        x0 = min(max(x0, 0.0), dur - span)
        x1 = x0 + span
        return round(x0, 6), round(x1, 6)

    def apply_range_edit(self, x0: float, x1: float) -> None:
        """外部(示波器/缩略导航条)发起的范围编辑;播放锁定时忽略。"""
        if self.play_lock:
            return   # 播放中 x 固定全量范围(与 Web 版一致)
        self.set_xrange(x0, x1)

    def _on_range_edited(self, x0: float, x1: float) -> None:
        self.apply_range_edit(x0, x1)

    def reset_zoom(self) -> None:
        self.set_xrange(0.0, self.duration if self.duration > 0 else 1.0)

    def get_xrange(self) -> tuple:
        return tuple(self._xr)

    # ---------------- 回放模式 ----------------

    def set_play_data(self, data: dict) -> None:
        for p in self.plots:
            p.set_play_data(data)

    def enter_play_mode(self) -> None:
        """播放开始:x 固定全量范围,清锚点/光标/统计浮层,曲线等待数据生长。"""
        self.play_lock = True
        self.set_anchor(None)
        for p in self.plots:
            p.reset_transients()
            p.set_cursor(None)
        self.set_xrange(0.0, self.duration if self.duration > 0 else 1.0)

    def exit_play_mode(self) -> None:
        """播放结束/停止:恢复静态全量曲线 + 全量 x 范围。"""
        self.play_lock = False
        groups: dict = {}
        for s in self.items:
            groups.setdefault(s.plot_id, []).append(s)
        for idx, plot in enumerate(self.plots):
            plot.set_signals(groups.get(idx, []))
            plot.set_xrange(*self._xr)
        self._apply_jitter_marks()

    # ---------------- 抖动峰值标记 ----------------

    def set_jitter_marks(self, marks: dict) -> None:
        """{(frame_id, channel): 峰值相对时间}。"""
        self.jitter_marks = marks or {}
        self._apply_jitter_marks()

    def show_jitter_marks(self, on: bool) -> None:
        self.show_jitter = bool(on)
        self._apply_jitter_marks()

    def _apply_jitter_marks(self) -> None:
        for plot in self.plots:
            plot.set_jitter_marks(
                self.jitter_marks if self.show_jitter else {})

    def _on_wheel_scroll(self, delta: int) -> None:
        bar = self.verticalScrollBar()
        step = int(delta / 120 * 40)
        bar.setValue(bar.value() + step)

    # ---------------- 光标 / 锚点 ----------------

    def _on_cursor(self, t: float) -> None:
        t = min(max(float(t), 0.0), self.duration if self.duration else t)
        for p in self.plots:
            p.set_cursor(t)
        self.cursorMoved.emit(t)

    def _on_cursor_left(self) -> None:
        for p in self.plots:
            p.set_cursor(None)
        self.cursorLeft.emit()

    def toggle_anchor(self, t: float) -> None:
        """单击设锚点,再击清除(与 Web 版一致)。"""
        self.set_anchor(None if self.anchor is not None else t)

    def set_anchor(self, t) -> None:
        self.anchor = t
        for p in self.plots:
            p.set_anchor(t)
        self.anchorChanged.emit(t)
