"""单示波器窗口:pyqtgraph 封装。

交互(移植 Web 版 app.js 并按桌面习惯调整,R1 增补):
- 滚轮 / Ctrl+滚轮:以鼠标为中心缩放时间轴(factor 1.25,最小窗 0.5s,钳制 [0, duration])
- Shift+滚轮:滚动页面
- 左键拖拽:平移时间轴
- Ctrl+左键拖拽:框选时间区间 → 区间统计浮层(RubberBand 预览)
- 双击:Y 轴 自动适应 ↔ 手动锁定(锁定值取当前视图范围)
- Shift+左键单击(位移<4px):切换测量锚点
- 点击窗口内信号图名(chip):临时隐藏/恢复该曲线(不重新解码)
- 悬停:跨窗光标读数(同步竖线 + 侧栏当前值)
- 右键:全中文上下文菜单(含 导出本窗图像 PNG / 区间统计应用与清除)
"""
from __future__ import annotations

import os

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QCursor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPushButton, QRubberBand,
                               QVBoxLayout, QWidget)

from services.stats_service import local_range_stats

pg.setConfigOptions(antialias=False)   # 大数据量性能优先

BG = "#14171d"
AXIS_COLOR = "#8a93a3"
MIN_WINDOW_S = 0.5        # 最小缩放窗口(与 Web 版一致)
ZOOM_FACTOR = 1.25
MAX_WINDOW_S = 1e6

SYNC_LINE_COLOR = (125, 211, 252, 220)   # 光标同步竖线(浅蓝虚线)
ANCHOR_LINE_COLOR = (255, 77, 77, 255)   # 锚点红线
REGION_BRUSH = (125, 211, 252, 34)       # 框选统计区间底色

STATS_ROWS_MAX = 10      # 统计浮层最多完整展示的信号行数


class ScopePlotWidget(pg.PlotWidget):
    """PlotWidget 兜底补丁。

    PySide6 下 ViewBox.addItem → scene.addItem 会同步触发 itemChange,
    此时 item 尚无父节点,pyqtgraph 的 getViewBox() 会临时缓存 QGraphicsView
    (即本类)并调用 ViewBox 才有的方法,导致 AttributeError。
    这里把两个被探测的方法转发给真正的 ViewBox,仅在瞬时窗口期被调用;
    正常挂载后 item 直接持有 ViewBox,不会经过此路径。
    """

    def autoRangeEnabled(self):
        vb = self.plotItem.getViewBox()
        return vb.autoRangeEnabled() if vb is not None else (False, False)

    def viewRange(self):
        vb = self.plotItem.getViewBox()
        return vb.viewRange() if vb is not None else [[0.0, 1.0], [0.0, 1.0]]


def _stepped(xs, ys):
    """左阶梯(值保持到下一采样):与 Web 版 stepped:'before' 一致。"""
    x = np.asarray(xs, dtype=float)
    y = np.asarray(ys, dtype=float)
    if len(x) < 2:
        return x, y
    sx = np.repeat(x, 2)[1:-1]           # [t0,t1,t1,...,t(n-1)]
    sy = np.repeat(y, 2)[:len(sx)]       # [v0,v0,v1,v1,...]
    return (np.append(sx, x[-1]), np.append(sy, y[-1]))


class ScopePlot(QWidget):
    """一个示波器:标题栏(chip 行 + 「+信号」+ 关闭) + PlotWidget。"""

    cursorHovered = Signal(object)          # float t(可能超界,由 stack 钳制)
    cursorLeft = Signal()
    anchorToggled = Signal(float)
    xRangeEdited = Signal(float, float)     # 本窗发起的新 (x0, x1),由 stack 同步
    wheelScroll = Signal(int)               # 非 Ctrl 滚轮 → 外层滚动
    addSignalRequested = Signal(int)        # plot_id(0 基)
    closeRequested = Signal(int)            # plot_id(0 基,关闭本窗)
    contextMenuRequested = Signal(object)   # QPoint(全局坐标)
    regionChanged = Signal(bool)            # 本窗是否持有框选统计区间(菜单可用性驱动)
    curveVisibilityChanged = Signal(str, bool)   # (key, hidden) chip 样式回写

    def __init__(self, index: int, parent=None):
        super().__init__(parent)
        self.index = index
        self.plot_id = index - 1            # 0 基窗口 id(与 SignalItem.plot_id 对应)

        # ---- 标题栏 ----
        bar = QWidget()
        bar.setFixedHeight(26)
        bar.setStyleSheet("background:#1a1d23;border-bottom:1px solid #2b2f38;")
        bar_lay = QHBoxLayout(bar)
        bar_lay.setContentsMargins(6, 0, 6, 0)
        bar_lay.setSpacing(4)
        self.label = QLabel(f"▎示波器 {index}")
        self.label.setStyleSheet("color:#4da3ff;font-weight:bold;border:none;background:transparent;")
        self.chips = QHBoxLayout()
        self.chips.setSpacing(4)
        btn_add = QPushButton("+ 信号")
        btn_add.setStyleSheet(
            "QPushButton{background:transparent;border:1px solid #2c323d;"
            "border-radius:3px;color:#8a93a3;padding:1px 8px;font-size:11px;}"
            "QPushButton:hover{color:#4da3ff;border-color:#4da3ff;}")
        btn_add.clicked.connect(lambda: self.addSignalRequested.emit(self.plot_id))
        btn_close = QPushButton("✕")
        btn_close.setFixedSize(18, 18)
        btn_close.setToolTip("关闭本示波器(窗口内信号一并移除)")
        btn_close.setStyleSheet(
            "QPushButton{background:transparent;border:none;color:#5c6472;"
            "font-size:11px;padding:0;}"
            "QPushButton:hover{color:#ff6b6b;}")
        btn_close.clicked.connect(lambda: self.closeRequested.emit(self.plot_id))
        bar_lay.addWidget(self.label)
        bar_lay.addLayout(self.chips)
        bar_lay.addStretch(1)
        bar_lay.addWidget(btn_add)
        bar_lay.addWidget(btn_close)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(bar)

        # ---- 绘图区 ----
        self.plot = ScopePlotWidget(background=BG)
        self.plot.showGrid(x=True, y=True, alpha=0.15)
        self.plot.setLabel("bottom", "时间", units="s", color=AXIS_COLOR)
        for axis in ("bottom", "left"):
            self.plot.getAxis(axis).setPen(pg.mkPen("#3a4150"))
            self.plot.getAxis(axis).setTextPen(pg.mkPen(AXIS_COLOR))
        # 固定轴宽/高:多窗时间轴像素级对齐
        # (Y 轴宽度随刻度文字自适应会导致绘图区左缘错位,跨窗读数困难)
        if os.environ.get("NO_AXIS_FIX") != "1":
            self.plot.getAxis("left").setWidth(72)
            self.plot.getAxis("bottom").setHeight(46)
        vb = self.getViewBox()
        vb.setMouseEnabled(x=False, y=False)   # 全部交互自定义
        vb.enableAutoRange(x=False, y=True)
        self.plot.setMenuEnabled(False)        # 禁用 pyqtgraph 默认英文菜单
        lay.addWidget(self.plot, 1)

        # 光标同步竖线 / 锚点线
        self.cursor_line = pg.InfiniteLine(
            angle=90, movable=False, pen=pg.mkPen(SYNC_LINE_COLOR, width=1,
                                                  style=Qt.DashLine))
        self.cursor_line.hide()
        self.plot.addItem(self.cursor_line)
        self.anchor_line = pg.InfiniteLine(
            angle=90, movable=False, pen=pg.mkPen(ANCHOR_LINE_COLOR, width=1))
        self.anchor_line.hide()
        self.plot.addItem(self.anchor_line)

        self._curves: dict = {}   # key -> (PlotDataItem, is_choices)
        self._legend = None
        self._items: list = []          # 本窗信号(供抖动标记匹配报文)
        self._mark_items: list = []     # 抖动峰值标记图形

        # ---- R1 状态 ----
        self._y_auto = True             # Y 轴模式(True=自动适应 / False=手动锁定)
        self._y_lock = None             # 锁定范围 (lo, hi)
        self._hidden_keys: set = set()  # 临时隐藏的信号 key(chip 点击切换)
        self._chip_btns: dict = {}      # key -> 图名按钮(显隐状态回写样式)
        self._hint_text = ""            # set_hint 存根(合成 Y 锁徽标用)
        self._rubber: QRubberBand | None = None   # Ctrl 拖拽框选预览
        self._box_active = False        # 本次按压是否为框选(按 press 修饰键判定)
        self._box_x0 = None             # 框选起点像素 x
        self._region = None             # pg.LinearRegionItem(已提交区间可视化)
        self._stats_text = None         # pg.TextItem(区间统计浮层)
        self._region_range = None       # (t0, t1) 相对秒

        self._press = None          # (x_pixel, y_pixel)
        self._press_xr = None
        self._press_ctrl = False
        self._dragging = False

        self.plot.viewport().installEventFilter(self)

    # ------------- 公共 API -------------

    def getViewBox(self):
        return self.plot.getViewBox()

    def set_signals(self, items: list) -> None:
        self._items = list(items)
        # _curves 值为 (PlotDataItem, is_choices) 元组——必须解包后再移除,
        # 否则 removeItem(元组) 被 pyqtgraph 静默跳过,图形对象泄漏在场景里
        for curve, stepped in self._curves.values():
            self.plot.removeItem(curve)
        self._curves.clear()
        self._clear_legend()

        for it in items:
            xs = list(it.times)
            ys = list(it.values)
            if it.is_choices:
                sx, sy = _stepped(xs, ys)
                curve = pg.PlotDataItem(
                    x=sx, y=sy, pen=pg.mkPen(it.color, width=1),
                    connect="finite", skipFiniteCheck=True)
            else:
                curve = pg.PlotDataItem(
                    x=xs, y=ys, pen=pg.mkPen(it.color, width=2),
                    connect="finite", skipFiniteCheck=True)
            curve.setDownsampling(auto=True, method="peak")
            curve.setClipToView(True)
            curve.setVisible(it.key not in self._hidden_keys)
            self.plot.addItem(curve)
            self._curves[it.key] = (curve, it.is_choices)

        if len(items) > 1:
            self._legend = self.plot.addLegend(offset=(10, 10), labelTextSize="9pt")
            for it in items:
                if it.key in self._hidden_keys:
                    continue   # 隐藏曲线不进图例(图例只描述"看得见"的线)
                name = f"{it.name} ({it.unit})" if it.unit else it.name
                self._legend.addItem(self._curves[it.key][0], name)

        self._apply_y_mode()
        self.set_hint("" if items else "点击左侧信号或「+ 信号」添加曲线")

    def set_hint(self, text: str) -> None:
        self._hint_text = text
        base = f"▎示波器 {self.index}" + (f"  {text}" if text else "")
        if not self._y_auto and self._y_lock is not None:
            lo, hi = self._y_lock
            base += f"   [Y锁定 {lo:.4g}~{hi:.4g}]"
        self.label.setText(base)

    def renumber(self, plot_id: int) -> None:
        """窗口重编号(删除中间窗口后保持连续)。"""
        self.plot_id = plot_id
        self.index = plot_id + 1

    def set_xrange(self, x0: float, x1: float) -> None:
        self.getViewBox().setXRange(x0, x1, padding=0)

    def get_xrange(self) -> tuple:
        return tuple(self.getViewBox().viewRange()[0])

    def set_cursor(self, t) -> None:
        if t is None:
            self.cursor_line.hide()
        else:
            self.cursor_line.setPos(float(t))
            self.cursor_line.show()

    def set_anchor(self, t) -> None:
        if t is None:
            self.anchor_line.hide()
        else:
            self.anchor_line.setPos(float(t))
            self.anchor_line.show()

    def set_play_data(self, data: dict) -> None:
        """回放模式:用累积数据替换曲线内容(x 固定全量,曲线向右生长)。"""
        for key, (curve, stepped) in self._curves.items():
            d = data.get(key)
            if d and d["times"]:
                if stepped:
                    xs, ys = _stepped(d["times"], d["values"])
                else:
                    xs, ys = d["times"], d["values"]
                curve.setData(x=xs, y=ys)
            else:
                curve.setData(x=[], y=[])
        self._apply_y_mode()

    def set_jitter_marks(self, marks: dict) -> None:
        """绘制抖动峰值标记:黄色顶部短竖线(span 限高)。marks: {(fid,ch): t_rel}"""
        for it in self._mark_items:
            self.plot.removeItem(it)
        self._mark_items = []
        if not marks:
            return
        pairs = {(i.frame_id, i.channel) for i in self._items}
        for (fid, ch), t in marks.items():
            if (fid, ch) not in pairs:
                continue
            line = pg.InfiniteLine(
                pos=float(t), angle=90, movable=False,
                span=(0.93, 1.0),
                pen=pg.mkPen("#fcd34d", width=2))
            line.setZValue(10)
            self.plot.addItem(line)
            self._mark_items.append(line)

    def _clear_legend(self) -> None:
        if self._legend is not None:
            try:
                self._legend.scene().removeItem(self._legend)
            except Exception:
                pass
            self._legend = None

    # ------------- R1:Y 轴量程模式 -------------

    def _apply_y_mode(self) -> None:
        vb = self.getViewBox()
        if self._y_auto:
            vb.enableAutoRange(axis="y")
        elif self._y_lock is not None:
            lo, hi = self._y_lock
            vb.enableAutoRange(axis="y", enable=False)
            vb.setYRange(lo, hi, padding=0)
        self.set_hint(self._hint_text)

    def toggle_y_lock(self) -> bool:
        """双击语义:自动 ↔ 锁定(锁定取当前视图范围)。返回是否处于锁定。"""
        if self._y_auto:
            lo, hi = self.getViewBox().viewRange()[1]
            self.set_y_mode(False, (float(lo), float(hi)))
        else:
            self.set_y_mode(True)
        return not self._y_auto

    def set_y_mode(self, auto: bool, rng=None) -> None:
        """显式设定 Y 轴模式。rng=(lo,hi) 仅在 auto=False 时生效。"""
        self._y_auto = bool(auto)
        self._y_lock = None if auto else (min(rng), max(rng))
        self._apply_y_mode()

    @property
    def y_locked(self) -> bool:
        return not self._y_auto

    # ------------- R1:曲线临时显隐 -------------

    @property
    def has_hidden(self) -> bool:
        return bool(self._hidden_keys)

    def register_chip(self, key: str, name_lbl, dot_lbl, color: str) -> None:
        """由 ScopeStack 创建 chip 时登记标签(显隐态样式回写用)。"""
        self._chip_btns[key] = (name_lbl, dot_lbl, color)

    def release_chips(self) -> None:
        self._chip_btns.clear()

    _CHIP_NAME_HIDDEN_TIP = "已临时隐藏(点击图名恢复)"

    def _restyle_chip(self, key: str) -> None:
        entry = self._chip_btns.get(key)
        if entry is None:
            return
        name_lbl, dot_lbl, color = entry
        hidden = key in self._hidden_keys
        dot_color = "#5c6472" if hidden else color
        dot_lbl.setStyleSheet(
            f"color:{dot_color};font-size:9px;border:none;background:transparent;")
        name_lbl.setStyleSheet(
            "color:" + ("#5c6472" if hidden else "#c9ced6")
            + ";font-size:11px;border:none;background:transparent;")
        name_lbl.setToolTip(self._CHIP_NAME_HIDDEN_TIP if hidden
                            else "点击图名可临时隐藏该曲线")

    def _set_curve_visibility(self, key: str, visible: bool) -> bool:
        pair = self._curves.get(key)
        if pair is None:
            return False
        pair[0].setVisible(visible)
        if visible:
            self._hidden_keys.discard(key)
        else:
            self._hidden_keys.add(key)
        self._restyle_chip(key)
        self.curveVisibilityChanged.emit(key, not visible)
        return True

    def toggle_visible(self, key: str) -> None:
        pair = self._curves.get(key)
        if pair is None:
            return
        self._set_curve_visibility(key, key in self._hidden_keys)

    def show_all_curves(self) -> int:
        n = len(self._hidden_keys)
        for key in tuple(self._hidden_keys):
            self._set_curve_visibility(key, True)
        return n

    # ------------- R1:框选统计区间 -------------

    def region_times(self):
        """当前框选区间 (t0, t1)(相对秒);无则 None。"""
        return self._region_range

    def commit_region(self, t0: float, t1: float, items=None) -> bool:
        """提交统计区间:可视化条带 + 统计浮层(同步计算,数据在内存)。"""
        dbg = None
        if os.environ.get("R1_TRACE"):
            def dbg(m):
                print(f"    cr:{m}", flush=True)
        dbg and dbg(f"args {t0:.3f}~{t1:.3f}")
        t0, t1 = min(float(t0), float(t1)), max(float(t0), float(t1))
        if t1 - t0 < 1e-9:
            return False
        self.clear_region()
        dbg and dbg("lri ctor")
        self._region = pg.LinearRegionItem(
            values=[t0, t1], orientation="vertical", movable=False,
            brush=pg.mkBrush(*REGION_BRUSH),
            hoverBrush=pg.mkBrush(*REGION_BRUSH))
        for ln in self._region.lines:
            ln.setPen(pg.mkPen(QColor(125, 211, 252, 120), width=1,
                               style=Qt.DashLine))
        self._region.setZValue(8)
        dbg and dbg("add region")
        self.plot.addItem(self._region)

        x_lo, x_hi = self.get_xrange()
        dbg and dbg("stats calc")
        res = local_range_stats(items if items is not None else self._items,
                                t0, t1)
        dbg and dbg(f"text html rows={len(res.get('rows', []))}")
        self._stats_text = pg.TextItem(
            html=self._format_stats_html(res), anchor=(0, 0),
            border=pg.mkPen("#2b2f38"), fill=pg.mkBrush(22, 24, 29, 210))
        top_y = self.getViewBox().viewRange()[1][1]
        pad = (x_hi - x_lo) * 0.01
        self._stats_text.setPos(min(t0, x_hi - (x_hi - x_lo) * 0.4), top_y)
        self._stats_text.setZValue(12)
        dbg and dbg("add text")
        self.plot.addItem(self._stats_text)

        self._region_range = (t0, t1)
        self.regionChanged.emit(True)
        dbg and dbg("committed")
        return True

    def clear_region(self) -> None:
        for it in (self._stats_text, self._region):
            if it is not None:
                try:
                    self.plot.removeItem(it)
                except Exception:
                    pass
        had = self._region_range is not None
        self._region = self._stats_text = None
        self._region_range = None
        if had:
            self.regionChanged.emit(False)

    def reset_transients(self) -> None:
        """进入回放等场景:撤销框选预览与统计浮层(锁定的 Y 轴保留)。"""
        self._box_active = False
        self._box_x0 = None
        if self._rubber is not None:
            self._rubber.hide()
        self.clear_region()

    @staticmethod
    def _fmt_num(v) -> str:
        if v is None:
            return "-"
        s = f"{v:.4f}".rstrip("0").rstrip(".")
        return s if s else "0"

    def _format_stats_html(self, res: dict) -> str:
        dt = res.get("dt_s") or 0.0
        rows = res.get("rows", [])
        r0, r1 = self._region_range if self._region_range else (0.0, 0.0)
        html = [f"<div style='color:#7dd3fc;'>"
                f"{r0:.3f}~{r1:.3f}s · Δ{dt:.3f}s</div>"]
        for r in rows[:STATS_ROWS_MAX]:
            bullet = f"<span style='color:{r['color']};'>●</span>"
            if r.get("choices_dist"):
                dist = " ".join(f"{k}×{v}" for k, v in r["choices_dist"].items())
                html.append(f"<div>{bullet} <b>{r['name']}</b>: {dist}"
                            f" <span style='color:#8a93a3;'>(n={r['count']})</span></div>")
            else:
                unit = f" {r['unit']}" if r["unit"] else ""
                html.append(
                    f"<div>{bullet} <b>{r['name']}</b>: "
                    f"{self._fmt_num(r['min'])}~{self._fmt_num(r['max'])}{unit} "
                    f"μ={self._fmt_num(r['mean'])} σ={self._fmt_num(r['std'])} "
                    f"<span style='color:#8a93a3;'>(n={r['count']})</span></div>")
        if len(rows) > STATS_ROWS_MAX:
            html.append(f"<div style='color:#8a93a3;'>… 共 {len(rows)} 条信号</div>")
        return "".join(html)

    # ------------- R1:导出 PNG -------------

    def render_png(self, path: str) -> bool:
        """抓取本窗(标题栏+绘图区)并附加信息水印后保存为 PNG。"""
        pm = self.grab()
        h_info = 26
        canvas = QPixmap(pm.width(), pm.height() + h_info)
        canvas.fill(QColor("#16181d"))
        p = QPainter(canvas)
        try:
            p.drawPixmap(0, 0, pm)
            p.setPen(QColor("#2b2f38"))
            p.drawLine(0, pm.height(), pm.width(), pm.height())
            p.setPen(QColor("#8a93a3"))
            x0, x1 = self.get_xrange()
            mode = "自动" if self._y_auto else "锁定"
            info = (f"CANScope · 视窗 {x0:.2f}~{x1:.2f}s · "
                    f"Y轴{mode} · 信号 {len(self._items)}")
            p.drawText(QRectF(8, pm.height() + 1, pm.width() - 16, h_info - 2),
                       Qt.AlignLeft | Qt.AlignVCenter, info)
        finally:
            p.end()
        return bool(canvas.save(path, "PNG"))

    # ------------- 缩放/平移 -------------

    def zoom_at(self, mx_data: float, factor: float) -> None:
        """以 mx_data 为中心缩放(发出新范围,由 stack 钳制并同步)。"""
        x0, x1 = self.get_xrange()
        span = max(x1 - x0, 1e-9)
        new_span = span * factor
        ratio = (mx_data - x0) / span
        nx0 = mx_data - ratio * new_span
        self.xRangeEdited.emit(nx0, nx0 + new_span)

    def pan_by(self, dt: float) -> None:
        x0, x1 = self.get_xrange()
        self.xRangeEdited.emit(x0 + dt, x1 + dt)

    # ------------- 事件过滤(滚轮/拖拽/点击/悬停) -------------

    def _ensure_rubber(self) -> QRubberBand:
        if self._rubber is None:
            self._rubber = QRubberBand(QRubberBand.Shape.Rectangle,
                                       self.plot.viewport())
        return self._rubber

    def _rubber_show(self, px_a: float, px_b: float) -> None:
        """全高竖向条带预览(限制在视口内)。"""
        vp = self.plot.viewport()
        w = vp.width()
        lo = min(max(0.0, px_a), w)
        hi = min(max(0.0, px_b), w)
        r = self._ensure_rubber()
        r.setGeometry(QRectF(min(lo, hi), 0, abs(hi - lo), vp.height())
                      .toAlignedRect())
        r.show()

    def _x_at_px(self, px: float) -> float:
        """视口像素 x → 数据时间(线性映射,越界也返回真实值)。"""
        vp = self.plot.viewport()
        # QGraphicsView.mapToScene 只收 QPoint/整型对(QPointF 会抛错并可能
        # 在事件派发栈内引发原生崩溃),与既有 _map_to_data 的 .toPoint() 一致
        y_mid = int(max(vp.height(), 1) / 2)
        scene_pos = self.plot.mapToScene(QPoint(int(px), y_mid))
        return float(self.getViewBox().mapSceneToView(scene_pos).x())

    def eventFilter(self, obj, ev) -> bool:
        et = ev.type()
        if et == ev.Type.Wheel:
            delta = ev.angleDelta().y()
            if ev.modifiers() & Qt.ShiftModifier:
                # Shift+滚轮:滚动页面(多窗纵向浏览)
                self.wheelScroll.emit(-delta)
                return True
            # 普通滚轮 / Ctrl+滚轮:以鼠标为中心缩放时间轴
            pos = self._map_to_data(ev.position())
            if pos is not None:
                factor = 1.0 / ZOOM_FACTOR if delta > 0 else ZOOM_FACTOR
                self.zoom_at(pos, factor)
                return True
            return False

        if et == ev.Type.MouseButtonPress:
            if ev.button() == Qt.LeftButton:
                self._press = (ev.position().x(), ev.position().y())
                self._press_xr = self.get_xrange()
                self._dragging = False
                self._press_ctrl = bool(ev.modifiers() & Qt.ControlModifier)
                if self._press_ctrl:
                    # Ctrl+左键按下:开始框选统计区间(RubberBand 预览)
                    self._box_active = True
                    self._box_x0 = ev.position().x()
                    self._rubber_show(self._box_x0, self._box_x0)
                return False
            if ev.button() == Qt.RightButton:
                # 自定义中文右键菜单(替代 pyqtgraph 默认英文菜单)
                self.contextMenuRequested.emit(ev.globalPosition().toPoint())
                return True

        if et == ev.Type.MouseButtonDblClick:
            if ev.button() == Qt.LeftButton:
                # 双击:Y 轴 自动适应 ↔ 手动锁定(取当前视图范围)
                self.toggle_y_lock()
                return True

        if et == ev.Type.MouseMove:
            t = self._map_to_data(ev.position())
            if t is not None:
                self.cursorHovered.emit(t)
            if self._press is None or not (ev.buttons() & Qt.LeftButton):
                return False
            dx = ev.position().x() - self._press[0]
            if self._box_active:
                self._rubber_show(self._box_x0, ev.position().x())
                return False
            if not self._dragging and abs(dx) > 4:
                self._dragging = True
            if self._dragging:
                x0, x1 = self._press_xr
                w = max(self.plot.viewport().width(), 1)
                dt = -(dx) * (x1 - x0) / w
                nx0 = x0 + dt
                self.xRangeEdited.emit(nx0, nx0 + (x1 - x0))
            return False

        if et == ev.Type.MouseButtonRelease and ev.button() == Qt.LeftButton:
            if self._box_active:
                # 松开:提交框选区间(px → 数据时间)
                self._box_active = False
                if self._rubber is not None:
                    g = self._rubber.geometry()
                    self._rubber.hide()
                else:
                    g = None
                if g is not None and g.width() >= 3:
                    ta, tb = self._x_at_px(g.left()), self._x_at_px(g.right())
                    self.commit_region(ta, tb)
            elif (self._press is not None and not self._dragging
                  and not self._press_ctrl):
                # Shift+单击:设/清测量锚点(避免与缩放拖拽/框选误触)
                if ev.modifiers() & Qt.ShiftModifier:
                    t = self._map_to_data(ev.position())
                    if t is not None:
                        self.anchorToggled.emit(t)
            self._press = None
            self._dragging = False
            self._press_ctrl = False
            return False

        if et == ev.Type.Leave:
            self.cursorLeft.emit()
            return False

        return super().eventFilter(obj, ev)

    def _map_to_data(self, pos) -> object:
        """视口坐标 → 数据时间(s);越界返回 None。"""
        try:
            vp = self.plot.viewport()
            if pos.x() < 0 or pos.y() < 0 or pos.x() > vp.width() or pos.y() > vp.height():
                return None
            scene_pos = self.plot.mapToScene(pos.toPoint())
            vb = self.getViewBox()
            if not vb.sceneBoundingRect().contains(scene_pos):
                # 允许水平方向略越界(光标贴近边缘),只取 x
                return vb.mapSceneToView(scene_pos).x()
            return vb.mapSceneToView(scene_pos).x()
        except Exception:
            return None
