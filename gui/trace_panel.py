"""Trace 报文流:报文下拉 → 原始帧表格,支持信号值搜索 / 区间过滤 / 分页。"""
from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QPushButton, QTableView, QVBoxLayout,
                               QWidget)

PAGE = 200   # 与 Web 版一致

GOLD = QColor("#c9a86a")
GREEN = QColor("#5ad47a")
DIM = QColor("#8a93a3")


class TraceModel(QAbstractTableModel):
    HEAD = ["时间 (s)", "ID", "报文", "DLC", "CH", "数据 (hex)"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows: list = []

    def update_rows(self, rows: list) -> None:
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return len(self.HEAD)

    def headerData(self, sec, orient, role=Qt.DisplayRole):
        if orient == Qt.Horizontal and role == Qt.DisplayRole:
            return self.HEAD[sec]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        r = self.rows[index.row()]
        c = index.column()
        if role == Qt.DisplayRole:
            if c == 0:
                return f"{r['ts_rel']:.3f}"
            if c == 1:
                return r["id_hex"]
            if c == 2:
                return r["name"]
            if c == 3:
                return str(r["dlc"]) + ("  FD" if r["is_fd"] else "")
            if c == 4:
                return str(r["channel"])
            if c == 5:
                return r["data"]
        if role == Qt.ForegroundRole:
            if c == 5:
                return QBrush(GOLD)
            if c == 3 and r["is_fd"]:
                return QBrush(GREEN)
            if c == 1:
                return QBrush(QColor("#4da3ff"))
        if role == Qt.FontRole and c in (0, 1, 5):
            f = QFont("Consolas")
            f.setStyleHint(QFont.Monospace)
            return f
        return None


class TracePanel(QWidget):
    """Trace 报文流页签。"""

    def __init__(self, state, stack, parent=None):
        super().__init__(parent)
        self.state = state
        self.stack = stack
        self._offset = 0
        self._filter_sig = None
        self._filter_val = None
        self._range = None          # (abs_start, abs_end) 或 None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 8)
        lay.setSpacing(6)

        # ---- 工具栏 ----
        bar = QHBoxLayout()
        bar.setSpacing(6)
        self.cmb_msg = QComboBox()
        self.cmb_msg.setMinimumWidth(220)
        self.cmb_msg.currentIndexChanged.connect(self._on_msg_changed)
        self.cmb_sig = QComboBox()
        self.cmb_sig.setMinimumWidth(140)
        self.ed_val = QLineEdit()
        self.ed_val.setPlaceholderText("信号值(数值/状态名)")
        self.ed_val.setFixedWidth(150)
        self.ed_val.returnPressed.connect(self.on_search)

        btn_search = QPushButton("搜索")
        btn_search.setObjectName("primary")
        btn_search.clicked.connect(self.on_search)
        btn_clear_search = QPushButton("清除搜索")
        btn_clear_search.clicked.connect(self.on_clear_search)
        btn_range = QPushButton("按当前缩放过滤")
        btn_range.setToolTip("以示波器当前时间范围为过滤区间")
        btn_range.clicked.connect(self.on_apply_range)
        btn_clear_range = QPushButton("清除区间")
        btn_clear_range.clicked.connect(self.on_clear_range)
        # R2:全量导出(当前报文+过滤+区间,一次拉平全部分页)
        btn_export = QPushButton("导出全部 CSV")
        btn_export.setToolTip("导出当前报文在相同过滤条件下的全部帧(不受分页限制)")
        btn_export.clicked.connect(self.on_export_all)

        self.btn_prev = QPushButton("◀ 上一页")
        self.btn_prev.clicked.connect(lambda: self.reload(self._offset - PAGE))
        self.btn_next = QPushButton("下一页 ▶")
        self.btn_next.clicked.connect(lambda: self.reload(self._offset + PAGE))
        self.lbl_info = QLabel("")
        self.lbl_info.setStyleSheet("color:#8a93a3;")

        for w in (self.cmb_msg, self.cmb_sig, self.ed_val, btn_search,
                  btn_clear_search, btn_range, btn_clear_range, btn_export,
                  self.btn_prev, self.btn_next, self.lbl_info):
            bar.addWidget(w)
        bar.addStretch(1)
        lay.addLayout(bar)

        # ---- 表格 ----
        self.model = TraceModel()
        table = QTableView()
        table.setModel(self.model)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(24)
        table.setShowGrid(False)
        table.setSelectionBehavior(QTableView.SelectRows)
        table.setEditTriggers(QTableView.NoEditTriggers)
        hh = table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.Fixed)
        hh.setStretchLastSection(True)
        for c, w in enumerate((110, 80, 150, 70, 46, 420)):
            table.setColumnWidth(c, w)
        self.table = table
        lay.addWidget(table, 1)

    # ---------------- 数据 ----------------

    def populate(self) -> None:
        """按当前工程填充报文下拉(channelsReady 后调用)。"""
        self.cmb_msg.blockSignals(True)
        self.cmb_msg.clear()
        for ch, dbc in self.state.channel_dbc.items():
            try:
                from core import dbc_parser
                db = dbc_parser.load_database(dbc)
                msgs = dbc_parser.messages_summary(db)
            except Exception:
                continue
            for m in msgs:
                label = f"{m['frame_id_hex']}  {m['name']}  · CH{ch}"
                self.cmb_msg.addItem(label, (m["frame_id"], ch))
        self.cmb_msg.blockSignals(False)
        if self.cmb_msg.count():
            self.cmb_msg.currentIndexChanged.emit(self.cmb_msg.currentIndex())
        else:
            self.model.update_rows([])
            self.lbl_info.setText("未配置 DBC")

    def _on_msg_changed(self, _idx: int) -> None:
        self._fill_sig_combo()
        self.on_clear_search()

    def _fill_sig_combo(self) -> None:
        self.cmb_sig.clear()
        self.cmb_sig.addItem("(不过滤)", None)
        fid, ch = self._current_msg()
        if fid is None:
            return
        for msgs in self.state.messages_by_channel.get(ch, []):
            if msgs["frame_id"] == fid:
                for s in msgs["signals"]:
                    self.cmb_sig.addItem(s, s)
                break

    def _current_msg(self):
        d = self.cmb_msg.currentData()
        return d if d else (None, None)

    # ---------------- 动作 ----------------

    def on_search(self) -> None:
        sig = self.cmb_sig.currentData()
        val = self.ed_val.text().strip()
        self._filter_sig = sig if (sig and val) else None
        self._filter_val = val if self._filter_sig else None
        self.reload(0)

    def on_clear_search(self) -> None:
        self._filter_sig = self._filter_val = None
        self.ed_val.clear()
        self.reload(0)

    def on_apply_range(self) -> None:
        """以示波器当前缩放范围(相对时间)为区间 → 转绝对时间戳。"""
        rx0, rx1 = self.stack.get_xrange()
        t0 = self.state.t0
        self._range = (t0 + rx0, t0 + rx1)
        self.reload(0)

    def on_clear_range(self) -> None:
        self._range = None
        self.reload(0)

    def on_export_all(self) -> None:
        """R2:导出当前报文全量帧 CSV(相同过滤/区间)。"""
        from pathlib import Path as _Path

        from PySide6.QtWidgets import QFileDialog as _Dlg

        fid, ch = self._current_msg()
        if fid is None or self.state.blf_path is None:
            return
        default = f"trace_{hex(fid)}" + (f"_ch{ch}" if ch is not None else "") + ".csv"
        out, _sel = _Dlg.getSaveFileName(self, "导出 Trace 全量 CSV", default,
                                         "CSV (*.csv)")
        if not out:
            return
        start, end = self._range if self._range else (None, None)
        self.lbl_info.setText("导出中 …")
        self.state.export_trace_async(
            fid, ch, _Path(out), self._export_done,
            sig_filter=self._filter_sig, sig_value=self._filter_val,
            start=start, end=end)

    def _export_done(self, result) -> None:
        n, path = result
        extra = []
        if self._filter_sig:
            extra.append(f"{self._filter_sig}={self._filter_val}")
        if self._range:
            extra.append("时间区间")
        tag = f"({'+'.join(extra)})" if extra else ""
        self.lbl_info.setText(f"已导出 {n:,} 行 {tag} → {path}")

    def reload(self, offset: int = 0) -> None:
        fid, ch = self._current_msg()
        if fid is None or self.state.blf_path is None:
            self.model.update_rows([])
            self.lbl_info.setText("—")
            return
        self._offset = max(0, offset)
        start, end = self._range if self._range else (None, None)
        self.lbl_info.setText("加载中 …")
        self.state.fetch_trace(
            fid, ch, self._apply,
            sig_filter=self._filter_sig, sig_value=self._filter_val,
            start=start, end=end, offset=self._offset, limit=PAGE)

    def _apply(self, result: dict) -> None:
        t0 = self.state.t0
        rows = result["frames"]
        for r in rows:
            r["ts_rel"] = r["timestamp"] - t0
        self.model.update_rows(rows)
        n = result["returned"]
        lo = self._offset + (1 if n else 0)
        hi = self._offset + n
        extra = []
        if self._filter_sig:
            extra.append(f"过滤 {self._filter_sig}={self._filter_val}")
        if self._range:
            extra.append(f"区间 {self._range[0]-t0:.2f}~{self._range[1]-t0:.2f}s")
        self.lbl_info.setText(f"第 {lo}-{hi} 帧(offset {self._offset})"
                              + (" · " + " · ".join(extra) if extra else ""))
        self.btn_prev.setEnabled(self._offset > 0)
        self.btn_next.setEnabled(n >= PAGE)
