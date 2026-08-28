"""已选信号侧栏:色点 + 名称 + 光标处当前值 + 单位 + ✕(移除全部窗口中的该信号)。

标题栏按钮:+ 新建示波器 / − 删除最后一个示波器 / 清空。
"""
from __future__ import annotations

import bisect

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPushButton, QScrollArea,
                               QToolButton, QVBoxLayout, QWidget)


def _fmt_value(item) -> str:
    """格式化最后值(无光标时)。"""
    if not item.values:
        return "-"
    return _format(item.values[-1], item)


def _format(v, item) -> str:
    if item.choices and isinstance(v, (int, float)):
        name = item.choices.get(int(v))
        if name is not None:
            return f"{name}({v:g})"
    if isinstance(v, float):
        s = f"{v:.4f}".rstrip("0").rstrip(".")
        return s
    return str(v)


class _Row(QWidget):
    def __init__(self, item, on_remove):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 3, 6, 3)
        lay.setSpacing(6)
        dot = QLabel("●")
        dot.setFixedWidth(12)
        dot.setAlignment(Qt.AlignCenter)
        dot.setStyleSheet(f"color:{item.color};font-size:11px;background:transparent;")
        name = QLabel(item.name)
        name.setToolTip(f"{item.name}\n报文 {hex(item.frame_id)} · 通道 {item.channel}"
                        + (f"\n单位: {item.unit}" if item.unit else ""))
        self.lbl_anchor = QLabel("-")
        self.lbl_anchor.setToolTip("锚点时刻值(Shift+单击图区设锚点)")
        self.lbl_cursor = QLabel("-")
        self.lbl_cursor.setToolTip("光标时刻值(悬停示波器)")
        for lbl in (self.lbl_anchor, self.lbl_cursor):
            lbl.setFixedWidth(64)
            lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            lbl.setStyleSheet("color:#e8ecf2;font-family:Consolas,monospace;")
        rm = QToolButton()
        rm.setText("✕")
        rm.setFixedSize(18, 18)
        rm.setStyleSheet(
            "QToolButton{background:transparent;border:none;color:#5c6472;"
            "font-size:11px;padding:0;}"
            "QToolButton:hover{color:#ff6b6b;}")
        rm.clicked.connect(lambda: on_remove(item.key))
        lay.addWidget(dot)
        lay.addWidget(name, 1)
        lay.addWidget(self.lbl_anchor, 0)
        lay.addWidget(self.lbl_cursor, 0)
        lay.addWidget(rm)
        self.item = item

    def _nearest(self, t):
        it = self.item
        if not it.times:
            return None
        if t is None:
            return it.values[-1]
        i = bisect.bisect_left(it.times, t)
        cand = []
        if i > 0:
            cand.append(i - 1)
        if i < len(it.times):
            cand.append(i)
        best = min(cand, key=lambda j: abs(it.times[j] - t))
        return it.values[best]

    def update_values(self, t, anchor_t=None) -> None:
        it = self.item
        va = self._nearest(anchor_t) if anchor_t is not None else None
        vc = self._nearest(t)
        # 单位不进值列(收窄列宽),悬停 tooltip 可见
        self.lbl_anchor.setText(_format(va, it) if va is not None else "-")
        self.lbl_cursor.setText(_format(vc, it) if vc is not None else "-")


class SignalSidebar(QWidget):
    removeRequested = Signal(str)        # key(全部窗口)
    addPlotRequested = Signal()
    removePlotRequested = Signal()
    clearRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(260)
        self.setMaximumWidth(360)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        head = QWidget()
        head.setStyleSheet("background:#1a1d23;border-bottom:1px solid #2b2f38;")
        hv = QVBoxLayout(head)
        hv.setContentsMargins(8, 4, 6, 4)
        hv.setSpacing(2)
        # 行 A:标题 + 窗口操作按钮
        row_a = QHBoxLayout()
        row_a.setSpacing(6)
        title = QLabel("已选信号")
        title.setStyleSheet("color:#e8ecf2;font-weight:bold;background:transparent;")
        row_a.addWidget(title)
        for text, tip, cb in (("+", "新建示波器窗口", self.addPlotRequested),
                              ("−", "删除最后一个示波器", self.removePlotRequested),
                              ("清", "清空全部已选信号", self.clearRequested)):
            b = QPushButton(text)
            b.setFixedSize(26, 22)
            b.setToolTip(tip)
            b.setStyleSheet(
                "QPushButton{background:transparent;border:1px solid #2c323d;"
                "border-radius:3px;color:#8a93a3;font-size:13px;padding:0;}"
                "QPushButton:hover{color:#4da3ff;border-color:#4da3ff;}")
            b.clicked.connect(cb.emit)
            row_a.addWidget(b)
        row_a.addStretch(1)
        hv.addLayout(row_a)
        # 行 B:纯固定列标签(与数据行右侧结构逐像素一致)
        row_b = QHBoxLayout()
        row_b.setSpacing(6)
        row_b.addStretch(1)
        self.lbl_a = QLabel("锚点")
        self.lbl_a.setFixedWidth(64)
        self.lbl_a.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.lbl_a.setStyleSheet("color:#ff6b6b;font-size:11px;background:transparent;")
        self.lbl_c = QLabel("光标")
        self.lbl_c.setFixedWidth(64)
        self.lbl_c.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.lbl_c.setStyleSheet("color:#7dd3fc;font-size:11px;background:transparent;")
        row_b.addWidget(self.lbl_a)
        row_b.addWidget(self.lbl_c)
        spacer = QWidget()          # 对应数据行的 ✕ 按钮位
        spacer.setFixedWidth(18)
        row_b.addWidget(spacer)
        hv.addLayout(row_b)
        lay.addWidget(head)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet("QScrollArea{background:#16181d;border:none;}")
        inner = QWidget()
        self._rows_lay = QVBoxLayout(inner)
        self._rows_lay.setContentsMargins(0, 2, 0, 2)
        self._rows_lay.setSpacing(1)
        self._rows_lay.addStretch(1)
        self._scroll.setWidget(inner)
        lay.addWidget(self._scroll, 1)

        self._rows: list = []
        self._anchor_t = None

    # ---------------- 数据 ----------------

    def set_anchor(self, t) -> None:
        """锚点时间变化 → 刷新锚点值列。"""
        self._anchor_t = t
        self.update_values(None)

    def rebuild(self, items: list) -> None:
        for r in self._rows:
            r.hide()              # 立即隐藏,deleteLater 延迟到事件循环
            r.deleteLater()
        self._rows = []
        for it in items:
            row = _Row(it, self.removeRequested.emit)
            row.update_values(None, self._anchor_t)   # 立即显示最后值/锚点值
            self._rows_lay.insertWidget(self._rows_lay.count() - 1, row)
            self._rows.append(row)

    def update_values(self, t) -> None:
        for r in self._rows:
            r.update_values(t, self._anchor_t)
