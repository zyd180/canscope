"""缩略导航条(R1):全时长信号轮廓概览 + 当前视窗框。

- 每条已选信号画一条重度降采样(≤600 点)的细轮廓线,颜色同示波器;
- 当前视窗以半透明蓝高亮,两侧边缘条可拖拽改变跨度;
- 中部拖动 = 平移视窗,滚轮 = 以鼠标为中心缩放(与主图同一钳制链路);
- 范围变更一律经 ScopeStack.apply_range_edit 发起(尊重播放锁),再由
  xRangeChanged 回流刷新,保证单一数据源。
"""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from gui.scope_plot import MIN_WINDOW_S, ZOOM_FACTOR

EDGE_GRAB_PX = 6      # 视窗左右边缘的可抓取宽度
PROFILE_POINTS = 600  # 单信号轮廓最大点数


class MinimapBar(QWidget):
    spanRequested = Signal(float, float)   # 用户在导航条上拖出的新 (x0, x1)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(52)
        self.setMouseTracking(True)
        self.setToolTip("缩略导航:拖动平移 · 拖两侧边缘改跨度 · 滚轮缩放")

        self.duration: float = 0.0
        self._xr = [0.0, 1.0]
        self._series: list = []        # [(color, np_times, np_vals)]
        self._vmin = 0.0
        self._vmax = 1.0
        self._drag = None              # ("move", grab_dx) / ("edge_l"|"edge_r", fixed_t)

    # ---------------- 数据接口 ----------------

    def set_duration(self, dur: float) -> None:
        self.duration = max(0.0, float(dur or 0.0))
        self._xr = [0.0, self.duration if self.duration > 0 else 1.0]
        self.update()

    def set_viewport(self, x0: float, x1: float) -> None:
        self._xr = [float(x0), float(x1)]
        self.update()

    def refresh_from(self, items) -> None:
        """依据全部已选信号重建轮廓(去重、逐条 ≤600 点)。"""
        seen: set = set()
        series = []
        g_min, g_max = np.inf, -np.inf
        for it in items or []:
            if it.key in seen or not it.times:
                continue
            seen.add(it.key)
            ts = np.asarray(it.times, dtype=float)
            vs = np.asarray(it.values, dtype=float)   # 解码后均为数值/状态 int
            if ts.size > PROFILE_POINTS:
                idx = np.unique(np.linspace(0, ts.size - 1,
                                            PROFILE_POINTS).astype(int))
                ts, vs = ts[idx], vs[idx]
            series.append((it.color, ts, vs))
            finite_v = vs[np.isfinite(vs)]
            if finite_v.size:
                g_min = min(g_min, float(finite_v.min()))
                g_max = max(g_max, float(finite_v.max()))
        self._series = series
        if not np.isfinite(g_min) or not np.isfinite(g_max):
            g_min, g_max = 0.0, 1.0
        if g_max - g_min < 1e-12:
            pad = max(1.0, abs(g_min) * 0.1)
            g_min -= pad
            g_max += pad
        else:
            pad = (g_max - g_min) * 0.08
            g_min -= pad
            g_max += pad
        self._vmin, self._vmax = g_min, g_max
        self.update()

    # ---------------- 绘制 ----------------

    def _plot_rect(self) -> QRectF:
        return QRectF(8.0, 6.0, max(10.0, self.width() - 16.0),
                      max(10.0, self.height() - 12.0))

    def _t_to_px(self, t: float, rect: QRectF | None = None) -> float:
        r = rect or self._plot_rect()
        span = (self._xr[1] - self._xr[0]) or 1e-9
        return r.left() + (float(t) - self._xr[0]) / span * r.width()

    def _px_to_t(self, px: float, rect: QRectF | None = None) -> float:
        r = rect or self._plot_rect()
        span = (self._xr[1] - self._xr[0]) or 1e-9
        return self._xr[0] + (float(px) - r.left()) / max(r.width(), 1e-9) * span

    def paintEvent(self, ev) -> None:
        p = QPainter(self)
        try:
            p.fillRect(self.rect(), QColor("#16181d"))
            r = self._plot_rect()
            if self.duration <= 0 or not self._series:
                p.setPen(QColor("#5c6472"))
                p.drawText(r, Qt.AlignCenter, "打开日志并选择信号后显示时长概览")
                return

            p.setRenderHint(QPainter.Antialiasing, True)
            span_t = (self._xr[1] - self._xr[0]) or 1e-9

            # 只绘制与当前 x 轴有交集的部分(时间轴即全量,直接裁剪到条带)
            for color, ts, vs in self._series:
                m_lo = ts >= self._xr[0] - span_t * 0.02
                m_hi = ts <= self._xr[1] + span_t * 0.02
                seg_t, seg_v = ts[m_lo & m_hi], vs[m_lo & m_hi]
                if seg_t.size == 0:
                    continue
                xs = [self._t_to_px(t, r) for t in seg_t]
                ys = [r.bottom() - (float(v) - self._vmin)
                      / (self._vmax - self._vmin) * r.height()
                      for v in seg_v]
                pen = QPen(QColor(color))
                pen.setWidthF(1.2)
                p.setPen(pen)
                for i in range(len(xs) - 1):
                    p.drawLine(QPointF(xs[i], ys[i]), QPointF(xs[i + 1], ys[i + 1]))

            # 非视窗区压暗 + 视窗高亮
            view_l = self._t_to_px(self._xr[0], r)
            view_r = self._t_to_px(self._xr[1], r)
            dim = QColor(22, 24, 29, 150)
            if view_l > r.left():
                p.fillRect(QRectF(r.left(), r.top(),
                                  min(view_l, r.right()) - r.left(), r.height()), dim)
            if view_r < r.right():
                p.fillRect(QRectF(view_r, r.top(), r.right() - view_r, r.height()),
                           dim)
            hl = QColor("#4da3ff")
            band = QColor(hl)
            band.setAlpha(36)
            p.fillRect(QRectF(view_l, r.top(), view_r - view_l, r.height()), band)
            edge_pen = QPen(hl)
            edge_pen.setWidthF(2.0)
            p.setPen(edge_pen)
            p.drawLine(QPointF(view_l, r.top()), QPointF(view_l, r.bottom()))
            p.drawLine(QPointF(view_r, r.top()), QPointF(view_r, r.bottom()))
        finally:
            p.end()

    # ---------------- 交互 ----------------

    def _hit_mode(self, px: float) -> str:
        l = self._t_to_px(self._xr[0])
        rr = self._t_to_px(self._xr[1])
        if abs(px - l) <= EDGE_GRAB_PX:
            return "edge_l"
        if abs(px - rr) <= EDGE_GRAB_PX:
            return "edge_r"
        return "move"

    def mousePressEvent(self, ev) -> None:
        if ev.button() != Qt.LeftButton or self.duration <= 0:
            return
        rect = self._plot_rect()
        px = ev.position().x()
        mode = self._hit_mode(px)
        t = self._px_to_t(px, rect)
        if mode == "move":
            grab = t - self._xr[0]
            span = self._xr[1] - self._xr[0]
            # 越界保护:指针超出条带时按比例夹回
            grab = min(max(grab, 0.0), span)
            self._drag = ("move", grab)
        else:
            fixed = self._xr[1] if mode == "edge_l" else self._xr[0]
            self._drag = (mode, fixed)
        self.setCursor(Qt.ClosedHandCursor if mode == "move"
                       else Qt.SizeHorCursor)

    def mouseMoveEvent(self, ev) -> None:
        rect = self._plot_rect()
        px = ev.position().x()
        if self._drag is None:
            self.setCursor({"edge_l": Qt.SizeHorCursor,
                            "edge_r": Qt.SizeHorCursor}
                           .get(self._hit_mode(px), Qt.ArrowCursor))
            return
        t = self._px_to_t(px, rect)
        mode, ref = self._drag
        if mode == "move":
            span = self._xr[1] - self._xr[0]
            nx0 = t - ref
            self.spanRequested.emit(nx0, nx0 + span)
        elif mode == "edge_l":
            self.spanRequested.emit(min(t, ref - MIN_WINDOW_S), ref)
        else:
            self.spanRequested.emit(ref, max(t, ref + MIN_WINDOW_S))

    def mouseReleaseEvent(self, ev) -> None:
        self._drag = None
        self.unsetCursor()

    def wheelEvent(self, ev) -> None:
        """以鼠标为中心缩放(factor 与主图一致)。"""
        rect = self._plot_rect()
        mx = self._px_to_t(ev.position().x(), rect)
        factor = 1.0 / ZOOM_FACTOR if ev.angleDelta().y() > 0 else ZOOM_FACTOR
        x0, x1 = self._xr
        span = (x1 - x0) or 1e-9
        new_span = span * factor
        ratio = (mx - x0) / span
        nx0 = mx - ratio * new_span
        self.spanRequested.emit(nx0, nx0 + new_span)
