"""ID 统计页签:Bus Load 概览卡 + 每 ID 帧数/频率横向条形列表。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QScrollArea, QVBoxLayout,
                               QWidget)

BAR_MAX = 460   # 条形区最大像素宽


class IdStatsPanel(QWidget):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 6, 8, 8)
        outer.setSpacing(6)

        # ---- Bus Load 概览卡 ----
        self.bus_card = QLabel("Bus Load:—")
        self.bus_card.setStyleSheet(
            "background:#1a1d23;border:1px solid #2b2f38;border-radius:6px;"
            "padding:8px 12px;color:#c9ced6;")
        self.bus_card.setTextFormat(Qt.RichText)
        self.bus_card.setWordWrap(True)
        outer.addWidget(self.bus_card)

        # ---- ID 列表(滚动) ----
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        self._lay = QVBoxLayout(inner)
        self._lay.setContentsMargins(0, 2, 0, 2)
        self._lay.setSpacing(3)
        self._lay.addStretch(1)
        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)

    # ---------------- 数据 ----------------

    def populate(self) -> None:
        """statsReady 后调用:重建 ID 列表。"""
        stats = self.state.stats
        while self._lay.count() > 1:
            it = self._lay.takeAt(0)
            w = it.widget()
            if w is not None:
                w.hide()
                w.deleteLater()
        if not stats:
            return
        by_id = stats.get("by_id", [])
        max_count = max((e["count"] for e in by_id), default=1) or 1
        # frame_id → 报文名(取自已加载 DBC)
        name_map = {}
        for msgs in self.state.messages_by_channel.values():
            for m in msgs:
                name_map.setdefault(m["frame_id"], m["name"])
        for e in by_id:
            self._lay.insertWidget(self._lay.count() - 1,
                                   self._make_row(e, max_count,
                                                  name_map.get(e["frame_id"])))
        self.refresh_bus_load()

    def refresh_bus_load(self) -> None:
        self.bus_card.setText("Bus Load:计算中 …")
        self.state.fetch_bus_load(self._apply_bus_load)

    def _apply_bus_load(self, info: dict) -> None:
        bt = "CAN FD" if info.get("bus_type") == "canfd" else "CAN 经典"
        arb = info.get("arbitration_baudrate", 0) // 1000
        lines = [f"<b>{bt}</b> · 仲裁 {arb} kbps"
                 + (f" / 数据 {info.get('data_baudrate', 0)//1000} kbps"
                    if bt == "CAN FD" else "")]
        for ch, d in sorted(info.get("channels", {}).items(),
                            key=lambda kv: int(kv[0])):
            load = d["bus_load_pct"]
            color = "#5ad47a" if load < 50 else ("#ffb84d" if load < 80 else "#ff6b6b")
            lines.append(
                f"<span style='color:#4da3ff;'>CH{ch}</span>:"
                f"<b style='color:{color};'>{load:.2f}%</b>"
                f"<span style='color:#8a93a3;'> · {d['frames']:,} 帧 · "
                f"占用 {d['bus_time_s']:.3f}s / {d['duration_s']:.2f}s</span>")
        self.bus_card.setText("<br>".join(lines))

    def _make_row(self, e: dict, max_count: int, name) -> QWidget:
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(4, 1, 4, 1)
        lay.setSpacing(10)

        lbl_id = QLabel(hex(e["frame_id"]))
        lbl_id.setFixedWidth(80)
        lbl_id.setStyleSheet("color:#4da3ff;font-family:Consolas,monospace;")
        lbl_name = QLabel(name or "")
        lbl_name.setFixedWidth(150)
        lbl_name.setStyleSheet("color:#8a93a3;")

        # 条形:外槽 + 内条(渐变)
        slot = QWidget()
        slot.setFixedHeight(14)
        slot.setFixedWidth(BAR_MAX)
        slot.setStyleSheet("background:#232730;border-radius:7px;")
        slot_lay = QHBoxLayout(slot)
        slot_lay.setContentsMargins(2, 2, 2, 2)
        bar = QWidget()
        pct = max(0.02, e["count"] / max_count)
        bar.setFixedHeight(10)
        bar.setFixedWidth(max(8, int((BAR_MAX - 4) * pct)))
        bar.setStyleSheet(
            "background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #2563eb, stop:1 #4da3ff);border-radius:5px;")
        slot_lay.addWidget(bar)
        slot_lay.addStretch(1)

        lbl_count = QLabel(f"{e['count']:,}")
        lbl_count.setFixedWidth(80)
        lbl_count.setStyleSheet("color:#e8ecf2;font-family:Consolas,monospace;")
        rate = e.get("rate_hz")
        lbl_rate = QLabel(f"{rate:.1f} Hz" if rate else "-")
        lbl_rate.setFixedWidth(80)
        lbl_rate.setStyleSheet("color:#8a93a3;")

        tip = (f"首帧 {e['first']:.3f} · 末帧 {e['last']:.3f}\n"
               f"持续 {e.get('duration_s', 0):.3f}s · 最大 DLC {e['dlc']}")
        for w in (lbl_id, lbl_name, lbl_count, lbl_rate):
            w.setToolTip(tip)
        slot.setToolTip(tip)

        lay.addWidget(lbl_id)
        lay.addWidget(lbl_name)
        lay.addWidget(slot)
        lay.addWidget(lbl_count)
        lay.addWidget(lbl_rate)
        lay.addStretch(1)
        return row
