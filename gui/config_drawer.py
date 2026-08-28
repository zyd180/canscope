"""配置弹窗:总线类型/波特率/BLF 信息/通道 DBC 映射/抖动峰值开关 → data/config.json。

模态 QDialog(替代早期 QDockWidget 抽屉):固定宽度、标准按钮行,
无停靠面板的宽度/对齐/裁剪问题。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFileDialog,
                               QHBoxLayout, QLabel, QMessageBox, QPushButton,
                               QScrollArea, QVBoxLayout, QWidget)

BUS_TYPES = [("CAN FD", "canfd"), ("CAN 经典", "can")]
ARB_RATES = [125000, 250000, 500000, 1000000]
DATA_RATES = [1000000, 2000000, 5000000, 10000000]


def _rate_combo(rates: list, current: int) -> QComboBox:
    cmb = QComboBox()
    for r in rates:
        cmb.addItem(f"{r // 1000} kbps", r)
    idx = rates.index(current) if current in rates else rates.index(500000)
    cmb.setCurrentIndex(idx)
    return cmb


class ConfigDialog(QDialog):
    # object:PySide 的 dict 签名转 QVariantMap 要求字符串键,int 键会静默丢槽
    mappingApplied = Signal(object)     # {int ch: dbc path}
    jitterToggled = Signal(bool)
    configSaved = Signal()

    def __init__(self, state, settings, parent=None):
        super().__init__(parent)
        self.state = state
        self.settings = settings
        self.setWindowTitle("配置")
        self.setMinimumWidth(460)
        self.setMinimumHeight(420)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(8)

        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        # ---- 总线参数 ----
        t1 = QLabel("总线参数")
        t1.setStyleSheet("color:#e8ecf2;font-weight:bold;")
        lay.addWidget(t1)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("总线类型"))
        self.cmb_bus = QComboBox()
        for label, v in BUS_TYPES:
            self.cmb_bus.addItem(label, v)
        row1.addWidget(self.cmb_bus, 1)
        lay.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("仲裁段波特率"))
        cfg = state.config
        self.cmb_arb = _rate_combo(ARB_RATES, int(cfg.get("baudrate_arb", 500000)))
        row2.addWidget(self.cmb_arb, 1)
        lay.addLayout(row2)

        row3 = QHBoxLayout()
        row3.addWidget(QLabel("数据段波特率"))
        self.cmb_data = _rate_combo(DATA_RATES, int(cfg.get("baudrate_data", 2000000)))
        row3.addWidget(self.cmb_data, 1)
        lay.addLayout(row3)
        self.cmb_bus.currentIndexChanged.connect(self._on_bus_type)

        # ---- BLF 信息 ----
        t2 = QLabel("BLF 信息")
        t2.setStyleSheet("color:#e8ecf2;font-weight:bold;")
        lay.addWidget(t2)
        self.lbl_blf = QLabel("未打开")
        self.lbl_blf.setTextFormat(Qt.RichText)
        self.lbl_blf.setStyleSheet(
            "background:#14171d;border:1px solid #2b2f38;border-radius:6px;"
            "padding:8px;color:#c9ced6;")
        self.lbl_blf.setWordWrap(True)
        self.lbl_blf.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.lbl_blf.setMinimumHeight(96)
        lay.addWidget(self.lbl_blf)

        # ---- 通道 DBC 映射 ----
        t3 = QLabel("通道 → DBC 映射")
        t3.setStyleSheet("color:#e8ecf2;font-weight:bold;")
        lay.addWidget(t3)
        auto_row = QHBoxLayout()
        auto_row.setContentsMargins(0, 0, 0, 0)
        auto_row.addStretch(1)
        self.btn_auto = QPushButton("自动适配 DBC…")
        self.btn_auto.setFixedWidth(160)
        self.btn_auto.setToolTip("选择候选 DBC，按各通道实际报文 ID 和 DLC 自动匹配")
        self.btn_auto.clicked.connect(self._auto_match)
        auto_row.addWidget(self.btn_auto)
        auto_row.addStretch(1)
        lay.addLayout(auto_row)
        self.map_lay = QVBoxLayout()
        self.map_lay.setSpacing(4)
        lay.addLayout(self.map_lay)
        self._map_combos: dict = {}   # ch -> QComboBox

        # ---- 选项 ----
        self.chk_jitter = QCheckBox("在示波器上标记抖动峰值")
        jit = settings.value("ui/jitter_marks", "false") in ("true", True)
        self.chk_jitter.setChecked(jit)
        self.chk_jitter.toggled.connect(self._on_jitter)
        lay.addWidget(self.chk_jitter)

        lay.addStretch(1)

        # 多通道时映射行可能较多:仅纵向滚动
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(inner)
        root.addWidget(scroll, 1)

        # ---- 底部按钮行(标准对话框布局) ----
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        self.btn_save = QPushButton("保存配置")
        self.btn_save.setObjectName("primary")
        self.btn_save.setDefault(True)
        self.btn_save.clicked.connect(self._on_save_clicked)
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(self.btn_save)
        root.addLayout(btn_row)

        self.refresh()

    # ---------------- 刷新 ----------------

    def refresh(self) -> None:
        """打开时按当前工程/配置填充。"""
        cfg = self.state.config
        self.cmb_bus.setCurrentIndex(0 if cfg.get("bus_type", "canfd") == "canfd" else 1)
        self._select_rate(self.cmb_arb, int(cfg.get("baudrate_arb", 500000)))
        self._select_rate(self.cmb_data, int(cfg.get("baudrate_data", 2000000)))
        self._on_bus_type()
        self._refresh_blf_info()
        self._refresh_mapping()

    @staticmethod
    def _select_rate(cmb: QComboBox, rate: int) -> None:
        i = cmb.findData(rate)
        if i >= 0:
            cmb.setCurrentIndex(i)

    def _on_bus_type(self) -> None:
        is_fd = self.cmb_bus.currentData() == "canfd"
        self.cmb_data.setEnabled(is_fd)

    def _refresh_blf_info(self) -> None:
        s = self.state
        if not s.stats or not s.blf_path:
            self.lbl_blf.setText("未打开 BLF")
            return
        st = s.stats
        try:
            size = s.blf_path.stat().st_size
            size_txt = (f"{size / 1024 / 1024:.1f} MB" if size > 1024 * 1024
                        else f"{size / 1024:.0f} KB")
        except OSError:
            size_txt = "?"
        chans = " · ".join(f"CH{c['channel']}({c['frames']:,}帧)"
                           for c in st.get("channels", []))
        err = st.get("error_frames", 0)
        err_line = (f"<br><span style='color:#ff6b6b;'>⚠ 错误帧:{err:,}</span>"
                    if err else "")
        first = st.get("first_timestamp")
        import time as _time
        begin = (_time.strftime("%Y-%m-%d %H:%M:%S", _time.localtime(first))
                 if first and first > 1e6 else f"{first or 0:.3f}s")
        self.lbl_blf.setText(
            f"<b>{st['file']}</b> ({size_txt})<br>"
            f"总帧数:{st['total_frames']:,} · 时长:{st.get('duration_s', 0):.2f}s<br>"
            f"通道:{chans or '-'}{err_line}<br>"
            f"<span style='color:#8a93a3;'>开始:{begin}</span>")

    def _refresh_mapping(self) -> None:
        # 清空旧行
        while self.map_lay.count():
            it = self.map_lay.takeAt(0)
            w = it.widget()
            if w is not None:
                w.hide()
                w.deleteLater()
        self._map_combos.clear()

        for info in self.state.channels_info:
            ch = info["channel"]
            row = QWidget()
            h = QHBoxLayout(row)
            h.setContentsMargins(0, 0, 0, 0)
            lbl = QLabel(f"CH{ch}")
            lbl.setStyleSheet("color:#4da3ff;font-weight:bold;")
            lbl.setFixedWidth(36)
            frames = QLabel(f"{info['frames']:,}帧")
            frames.setStyleSheet("color:#8a93a3;")
            frames.setFixedWidth(80)
            cmb = QComboBox()
            for p in self.state.dbc_files:
                cmb.addItem(Path(p).name, p)
            cur = self.state.channel_dbc.get(ch)
            if cur:
                i = cmb.findData(cur)
                if i < 0:
                    cmb.addItem(Path(cur).name, cur)
                    i = cmb.count() - 1
                cmb.setCurrentIndex(i)
            btn = QPushButton("浏览…")
            btn.setFixedWidth(74)
            btn.clicked.connect(lambda _=False, c=cmb: self._browse(c))
            h.addWidget(lbl)
            h.addWidget(frames)
            h.addWidget(cmb, 1)
            h.addWidget(btn)
            self.map_lay.addWidget(row)
            self._map_combos[ch] = cmb

    def _browse(self, cmb: QComboBox) -> None:
        p, _ = QFileDialog.getOpenFileName(self, "选择 DBC", "",
                                           "DBC 数据库 (*.dbc)")
        if not p:
            return
        if p not in self.state.dbc_files:
            self.state.dbc_files.append(p)
            cmb.addItem(Path(p).name, p)
        cmb.setCurrentIndex(cmb.findData(p))

    def _auto_match(self) -> None:
        if not self.state.stats or not self.state.channels_info:
            QMessageBox.information(self, "自动适配 DBC", "请先打开日志文件。")
            return
        paths, _ = QFileDialog.getOpenFileNames(
            self, "选择用于自动适配的 DBC", "", "DBC 数据库 (*.dbc)")
        if not paths:
            return

        from core.dbc_parser import match_channels_to_dbcs
        result = match_channels_to_dbcs(self.state.stats, paths)
        lines = []
        for info in self.state.channels_info:
            ch = info["channel"]
            match = result["channels"].get(ch, {})
            selected = match.get("selected")
            ambiguous = match.get("ambiguous", [])
            if selected:
                lines.append(
                    f"CH{ch} → {Path(selected).name} "
                    f"({match['matched']}/{match['total']}，"
                    f"覆盖率 {match['coverage']:.1%})")
            elif ambiguous:
                names = ", ".join(Path(p).name for p in ambiguous)
                lines.append(f"CH{ch} → 并列，需手动选择: {names}")
            else:
                lines.append(f"CH{ch} → 无匹配，保持当前映射")
        for error in result["errors"]:
            lines.append(f"跳过 {Path(error['path']).name}: {error['error']}")

        box = QMessageBox(self)
        box.setWindowTitle("自动适配结果")
        box.setText("\n".join(lines))
        box.setInformativeText("确认后应用唯一最佳匹配；并列或无匹配项不自动猜测。")
        box.setStandardButtons(QMessageBox.StandardButton.Yes |
                               QMessageBox.StandardButton.No)
        box.setDefaultButton(QMessageBox.StandardButton.Yes)
        if box.exec() != QMessageBox.StandardButton.Yes:
            return
        for ch, match in result["channels"].items():
            if match.get("selected"):
                selected = match["selected"]
                if selected not in self.state.dbc_files:
                    self.state.dbc_files.append(selected)
        self._refresh_mapping()
        for ch, match in result["channels"].items():
            if match.get("selected"):
                self._map_combos[ch].setCurrentIndex(
                    self._map_combos[ch].findData(match["selected"]))

    def _on_jitter(self, on: bool) -> None:
        self.settings.setValue("ui/jitter_marks", "true" if on else "false")
        self.jitterToggled.emit(on)

    # ---------------- 保存 ----------------

    def _on_save_clicked(self) -> None:
        if self.on_save():
            self.accept()

    def on_save(self) -> bool:
        """应用并持久化配置;成功返回 True。"""
        cfg = self.state.config
        cfg["bus_type"] = self.cmb_bus.currentData()
        cfg["baudrate_arb"] = int(self.cmb_arb.currentData())
        cfg["baudrate_data"] = int(self.cmb_data.currentData())
        mapping = {ch: cmb.currentData() for ch, cmb in self._map_combos.items()}
        try:
            from services import project_config
            project_config.save_config(cfg)
        except OSError as e:
            self.state.errorRaised.emit(f"配置保存失败: {e}")
            return False
        self.mappingApplied.emit(mapping)
        self.configSaved.emit()
        self.state.statusMessage.emit("配置已保存")
        return True
