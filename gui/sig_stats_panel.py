"""信号统计页签:信号数值统计表 + 报文周期/抖动/丢帧表。"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QHBoxLayout, QHeaderView, QLabel, QPushButton,
                               QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget)

ORANGE = QColor("#ffb84d")
NORMAL = QColor("#c9ced6")
DIM = QColor("#8a93a3")


def _item(text, color=None, mono=False, tooltip=None):
    it = QTableWidgetItem(str(text))
    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
    if color is not None:
        it.setForeground(color)
    if mono:
        f = it.font()
        f.setFamily("Consolas")
        it.setFont(f)
    if tooltip:
        it.setToolTip(tooltip)
    return it


class SigStatsPanel(QWidget):
    cycleStatsReady = Signal(object)   # {(frame_id, channel): 周期统计结果}(tuple 键必须用 object)

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self._pending = 0
        self._gen = 0                     # 刷新代际(过期回调丢弃)
        self._abs_range: tuple | None = None   # 统计过滤区间(绝对时间戳)
        self._sig_results: dict = {}
        self._cyc_results: dict = {}

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 8)
        lay.setSpacing(6)

        bar = QHBoxLayout()
        title = QLabel("信号统计(全部已选信号)")
        title.setStyleSheet("color:#e8ecf2;font-weight:bold;")
        btn = QPushButton("刷新统计")
        btn.setObjectName("primary")
        btn.clicked.connect(self.refresh)
        self.lbl_state = QLabel("")
        self.lbl_state.setStyleSheet("color:#8a93a3;")
        # R1:统计时间区间过滤(来自示波器框选「应用本窗统计区间」)
        self.lbl_rng = QLabel("")
        self.lbl_rng.setStyleSheet("color:#7dd3fc;")
        self.btn_clear_rng = QPushButton("清除区间")
        self.btn_clear_rng.setToolTip("取消时间过滤,恢复全量统计")
        self.btn_clear_rng.clicked.connect(self.clear_range_filter)
        self.btn_clear_rng.setVisible(False)
        bar.addWidget(title)
        bar.addStretch(1)
        bar.addWidget(self.lbl_state)
        bar.addWidget(self.lbl_rng)
        bar.addWidget(self.btn_clear_rng)
        bar.addWidget(btn)
        lay.addLayout(bar)

        # ---- 表 1:信号统计 ----
        self.tbl_sig = QTableWidget(0, 9)
        self.tbl_sig.setHorizontalHeaderLabels(
            ["信号", "CH", "点数", "min", "max", "mean", "std", "最后值", "超范围"])
        self.tbl_sig.verticalHeader().setVisible(False)
        self.tbl_sig.setShowGrid(False)
        self.tbl_sig.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tbl_sig.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents)
        self.tbl_sig.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(self.tbl_sig, 5)

        # ---- 表 2:周期统计 ----
        title2 = QLabel("报文周期 / 抖动 / 丢帧(全部已选报文)")
        title2.setStyleSheet("color:#e8ecf2;font-weight:bold;")
        lay.addWidget(title2)
        self.tbl_cyc = QTableWidget(0, 9)
        self.tbl_cyc.setHorizontalHeaderLabels(
            ["报文", "CH", "帧数", "期望(ms)", "平均(ms)", "min(ms)",
             "max(ms)", "抖动峰峰(ms)", "丢帧"])
        self.tbl_cyc.verticalHeader().setVisible(False)
        self.tbl_cyc.setShowGrid(False)
        self.tbl_cyc.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tbl_cyc.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents)
        self.tbl_cyc.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(self.tbl_cyc, 4)

    # ---------------- 刷新 ----------------

    def set_range_filter(self, a: float, b: float) -> None:
        """R1:限定统计时间区间(绝对时间戳),并立即重算。"""
        a, b = (min(a, b), max(a, b))
        if b - a <= 0:
            return
        self._abs_range = (a, b)
        t0 = self.state.t0
        self.lbl_rng.setText(
            f"[仅统计 {a - t0:.2f}~{b - t0:.2f}s]")
        self.btn_clear_rng.setVisible(True)
        self.refresh()

    def clear_range_filter(self) -> None:
        self._abs_range = None
        self.lbl_rng.setText("")
        self.btn_clear_rng.setVisible(False)
        if self.state.signals_list:
            self.refresh()

    def refresh(self) -> None:
        """对全部已选信号(去重)与报文发起后台统计(区间过滤生效)。"""
        s = self.state
        self._gen += 1
        gen = self._gen
        start, end = self._abs_range if self._abs_range else (None, None)
        self._sig_results.clear()
        self._cyc_results.clear()
        seen_sig, seen_msg = set(), set()
        for it in s.signals_list:
            if it.key not in seen_sig:
                seen_sig.add(it.key)
                self._pending += 1
                s.fetch_signal_stats(it, lambda r, g=gen: self._on_sig_done(r, g),
                                     start=start, end=end)
            pair = (it.frame_id, it.channel)
            if pair not in seen_msg:
                seen_msg.add(pair)
                self._pending += 1
                s.fetch_cycle_stats(it.frame_id, it.channel,
                                    lambda r, g=gen: self._on_cyc_done(r, g),
                                    start=start, end=end)
        if not seen_sig:
            self.tbl_sig.setRowCount(0)
            self.tbl_cyc.setRowCount(0)
            self.lbl_state.setText("未选择信号")
        else:
            self.lbl_state.setText("统计中 …")

    def _maybe_render(self, gen: int) -> None:
        if gen != self._gen:
            return   # 过期回调丢弃
        self._pending -= 1
        self.lbl_state.setText("统计中 …" if self._pending > 0 else "")
        if self._pending <= 0:
            self._render()

    # ---------------- 信号统计 ----------------

    def _on_sig_done(self, r: dict, gen: int | None = None) -> None:
        if gen is not None and gen != self._gen:
            return
        self._sig_results[(r["frame_id"], r["channel"], r["signal"])] = r
        self._maybe_render(gen)

    # ---------------- 周期统计 ----------------

    def _on_cyc_done(self, r: dict, gen: int | None = None) -> None:
        if gen is not None and gen != self._gen:
            return
        self._cyc_results[(r["frame_id"], r["channel"])] = r
        self._maybe_render(gen)

    def _render_sig(self) -> None:
        rows = sorted(self._sig_results.values(),
                      key=lambda r: (r["frame_id"], r["signal"]))
        self.tbl_sig.setRowCount(0)
        for r in rows:
            item = next((i for i in self.state.signals_list
                         if i.frame_id == r["frame_id"]
                         and i.channel == r["channel"] and i.name == r["signal"]), None)
            unit = f" {item.unit}" if item and item.unit else ""
            row = self.tbl_sig.rowCount()
            self.tbl_sig.insertRow(row)
            name_tip = None
            if item and item.choices:
                dist = r.get("choices_dist")
                if dist:
                    name_tip = ("状态分布: " +
                                " · ".join(f"{k}×{v}" for k, v in dist.items()))
            self.tbl_sig.setItem(row, 0, _item(
                f"● {r['signal']}",
                QColor(item.color) if item else NORMAL,
                tooltip=name_tip))
            self.tbl_sig.setItem(row, 1, _item(r["channel"]))
            self.tbl_sig.setItem(row, 2, _item(r["count"], mono=True))
            self.tbl_sig.setItem(row, 3, _item(r.get("min", "-"), mono=True))
            self.tbl_sig.setItem(row, 4, _item(r.get("max", "-"), mono=True))
            self.tbl_sig.setItem(row, 5, _item(r.get("mean", "-"), mono=True))
            self.tbl_sig.setItem(row, 6, _item(r.get("std", "-"), mono=True))
            last = r.get("last", "-")
            self.tbl_sig.setItem(row, 7, _item(f"{last}{unit}", NORMAL, mono=True))
            oor = r.get("out_of_range", 0)
            oor_it = _item(f"{oor}" + (f" ({r.get('range_min')}~{r.get('range_max')})"
                                       if oor else ""),
                           ORANGE if oor > 0 else DIM, mono=True,
                           tooltip=f"DBC 定义范围 {r.get('range_min')}~{r.get('range_max')}"
                           if oor else None)
            self.tbl_sig.setItem(row, 8, oor_it)

    # ---------------- 表格渲染 ----------------

    def _render_cyc(self) -> None:
        rows = sorted(self._cyc_results.values(),
                      key=lambda r: (r["frame_id"], r["channel"] or 0))
        self.tbl_cyc.setRowCount(0)
        t0 = self.state.t0
        for r in rows:
            row = self.tbl_cyc.rowCount()
            self.tbl_cyc.insertRow(row)
            self.tbl_cyc.setItem(row, 0, _item(f"{r['frame_id_hex']} {r['name']}"))
            self.tbl_cyc.setItem(row, 1, _item(r["channel"]))
            self.tbl_cyc.setItem(row, 2, _item(r["count"], mono=True))
            exp = r.get("expected_ms")
            self.tbl_cyc.setItem(row, 3, _item(exp if exp else "-", DIM, mono=True))
            self.tbl_cyc.setItem(row, 4, _item(r.get("avg_ms", "-"), mono=True))
            self.tbl_cyc.setItem(row, 5, _item(r.get("min_ms", "-"), mono=True))
            self.tbl_cyc.setItem(row, 6, _item(r.get("max_ms", "-"), mono=True))
            jit = r.get("jitter_ms")
            jit_it = _item(jit if jit is not None else "-", mono=True)
            if jit is not None and exp:
                if jit > exp * 0.3:   # 超期望 30% → 橙色警示(与 Web 版一致)
                    jit_it.setForeground(ORANGE)
                    jmax = r.get("jitter_max_at")
                    if jmax is not None:
                        jit_it.setToolTip(f"峰值出现在 {jmax - t0:.3f}s")
            self.tbl_cyc.setItem(row, 7, jit_it)
            lost = r.get("lost_frames")
            if lost is None:
                self.tbl_cyc.setItem(row, 8, _item("-", DIM))
            else:
                pct = r.get("lost_pct", 0)
                self.tbl_cyc.setItem(
                    row, 8, _item(f"{lost} ({pct:.1f}%)",
                                  ORANGE if lost > 0 else DIM, mono=True))

    def _render(self) -> None:
        self._render_sig()
        self._render_cyc()
        self.cycleStatsReady.emit(dict(self._cyc_results))
