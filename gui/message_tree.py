"""报文/信号树:通道分组 → 报文(ECU 彩签/无数据灰标)→ 信号(色点+单位),
支持按 ID/报文名/ECU/信号名实时过滤。
R2:日志中出现但 DBC 未定义的 ID 以「未识别报文」灰组展示,右键可生成 DBC 骨架。
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QIcon, QPainter, QPen,
                           QPixmap)
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QLineEdit, QMenu,
                               QToolButton, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget)

from gui.palette import node_color

KIND_ROLE = Qt.UserRole          # 'channel' | 'message' | 'signal'
KEY_ROLE = Qt.UserRole + 1       # signal key
FID_ROLE = Qt.UserRole + 2
CH_ROLE = Qt.UserRole + 3
NAME_ROLE = Qt.UserRole + 4
DLC_ROLE = Qt.UserRole + 5       # unknown 报文的 DLC(R2)

_COLOR_NORMAL = QColor("#c9ced6")
_COLOR_DIM = QColor("#5c6472")
_COLOR_SELECTED = QColor("#4da3ff")


def _dot_icon(color: str, size: int = 11) -> QIcon:
    """圆形色点图标。"""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor(color).darker(130), 1))
    p.setBrush(QColor(color))
    p.drawEllipse(1, 1, size - 3, size - 3)
    p.end()
    return QIcon(pm)


class MessageTree(QWidget):
    """左侧报文/信号树面板。"""
    signalToggled = Signal(int, int, str)   # frame_id, channel, signal_name
    skeletonRequested = Signal(int)         # channel(右键"未识别报文"生成 DBC 骨架)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 0, 6)
        lay.setSpacing(6)

        head = QHBoxLayout()
        head.setContentsMargins(2, 0, 0, 0)
        t = QLabel("报文 / 信号")
        t.setStyleSheet("color:#e8ecf2;font-weight:bold;")
        self._sort_hint = QLabel("")
        self._sort_hint.setStyleSheet("color:#5c6472;")
        head.addWidget(t)
        head.addStretch(1)
        head.addWidget(self._sort_hint)
        lay.addLayout(head)

        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索 ID / 报文 / 信号 / ECU")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._apply_filter)
        lay.addWidget(self.search)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(14)
        self.tree.itemClicked.connect(self._on_clicked)
        self.tree.setColumnWidth(0, 210)
        # R2:右键"未识别报文"分组/条目 → 生成 DBC 骨架
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_tree_menu)
        lay.addWidget(self.tree, 1)

        # key -> [TreeWidgetItem,...] 用于选中态刷新
        self._signal_items: dict = {}
        self._selected_keys: set = set()

    # ---------------- 构建 ----------------

    def rebuild(self, channels_info: list, messages_by_channel: dict,
                has_data: set, selected_colors: dict) -> None:
        """全量重建树。channels_info: [{channel,frames,dbc}];selected_colors: {key: color}。"""
        selected_colors = selected_colors or {}
        self.tree.blockSignals(True)
        self.tree.clear()
        self._signal_items.clear()
        self._selected_keys = set(selected_colors)

        bold = QFont()
        bold.setBold(True)

        for ch_info in channels_info:
            ch = ch_info["channel"]
            dbc_name = ch_info.get("dbc")

            ch_item = QTreeWidgetItem([f"通道 {ch}", f"{ch_info['frames']:,} 帧"])
            ch_item.setData(0, KIND_ROLE, "channel")
            f = QFont()
            f.setBold(True)
            ch_item.setFont(0, f)
            ch_item.setForeground(0, QBrush(QColor("#e8ecf2")))
            ch_item.setForeground(1, QBrush(_COLOR_DIM))
            if dbc_name:
                ch_item.setToolTip(1, dbc_name)
                sub = QTreeWidgetItem([dbc_name, ""])
                sub.setData(0, KIND_ROLE, "dbcfile")
                sub.setForeground(0, QBrush(_COLOR_DIM))
                itf = QFont()
                itf.setPointSizeF(bold.pointSizeF() * 0.92)
                sub.setFont(0, itf)
                ch_item.addChild(sub)
            self.tree.addTopLevelItem(ch_item)

            for msg in messages_by_channel.get(ch, []):
                has = msg["frame_id"] in has_data
                senders = ",".join(msg.get("senders") or []) or "-"
                label = f"{msg['frame_id_hex']}  {msg['name']}"
                info = f"{senders} · {msg['signal_count']} 信号"
                m_item = QTreeWidgetItem([label, info])
                m_item.setData(0, KIND_ROLE, "message")
                ecu = (msg.get("senders") or ["-"])[0]
                m_item.setIcon(0, _dot_icon(node_color(ecu)))
                m_item.setToolTip(0, f"ECU: {senders}\nDLC: {msg['length']}"
                                     f"\n周期: {msg['cycle_time'] or '-'} ms")
                if has:
                    m_item.setForeground(0, QBrush(_COLOR_NORMAL))
                    m_item.setForeground(1, QBrush(_COLOR_DIM))
                else:
                    gray = QBrush(_COLOR_DIM)
                    m_item.setForeground(0, gray)
                    m_item.setForeground(1, gray)
                    fo = m_item.font(0)
                    fo.setStrikeOut(True)
                    m_item.setFont(0, fo)
                    m_item.setDisabled(True)
                    m_item.setToolTip(0, (m_item.toolTip(0) + "\n[日志中无此报文数据]").strip())

                for sig_name in msg["signals"]:
                    key = f"{msg['frame_id']}|{ch}|{sig_name}"
                    s_item = QTreeWidgetItem([sig_name, ""])
                    s_item.setData(0, KIND_ROLE, "signal")
                    s_item.setData(0, KEY_ROLE, key)
                    s_item.setData(0, FID_ROLE, msg["frame_id"])
                    s_item.setData(0, CH_ROLE, ch)
                    s_item.setData(0, NAME_ROLE, sig_name)
                    color = selected_colors.get(key, "#5c6472")
                    s_item.setIcon(0, _dot_icon(color))
                    s_item.setForeground(0, QBrush(
                        _COLOR_SELECTED if key in selected_colors else _COLOR_NORMAL))
                    m_item.addChild(s_item)
                    self._signal_items.setdefault(key, []).append(s_item)

                ch_item.addChild(m_item)

            # R2:未识别报文灰组(日志有数据、DBC 未定义)
            unknown = ch_info.get("unknown") or []
            if unknown:
                u_grp = QTreeWidgetItem([f"未识别报文 ({len(unknown)})", ""])
                u_grp.setData(0, KIND_ROLE, "unknown_group")
                u_grp.setData(0, CH_ROLE, ch)
                u_grp.setForeground(0, QBrush(_COLOR_DIM))
                u_grp.setForeground(1, QBrush(_COLOR_DIM))
                u_grp.setToolTip(0, "DBC 未定义这些 ID;\n右键可生成 DBC 骨架(起步器)")
                for fid, dlc in unknown:
                    u_it = QTreeWidgetItem([hex(fid), f"{dlc} B"])
                    u_it.setData(0, KIND_ROLE, "unknown")
                    u_it.setData(0, FID_ROLE, int(fid))
                    u_it.setData(0, DLC_ROLE, int(dlc))
                    u_it.setData(0, CH_ROLE, ch)
                    u_it.setForeground(0, QBrush(_COLOR_DIM))
                    u_it.setForeground(1, QBrush(_COLOR_DIM))
                    u_grp.addChild(u_it)
                ch_item.addChild(u_grp)
            ch_item.setExpanded(True)

        self.tree.blockSignals(False)
        self.refresh_selection(selected_colors)
        self._expand_selected()
        self._apply_filter(self.search.text())

    def _expand_selected(self) -> None:
        """展开包含已选信号的报文节点。"""
        for key, items in self._signal_items.items():
            if key in self._selected_keys:
                for it in items:
                    p = it.parent()
                    if p is not None:
                        p.setExpanded(True)
                        gp = p.parent()
                        if gp is not None:
                            gp.setExpanded(True)

    def set_unit_map(self, units: dict):
        """可选:为信号项补充单位显示 {key: unit}。"""
        for key, items in self._signal_items.items():
            unit = units.get(key)
            if unit:
                for it in items:
                    it.setText(1, unit)

    def refresh_selection(self, selected_colors: dict) -> None:
        """刷新信号项选中高亮与色点颜色。selected_colors: {key: color}。"""
        selected_keys = set(selected_colors or ())
        self._selected_keys = selected_keys
        for key, items in self._signal_items.items():
            sel = key in selected_keys
            color = selected_colors.get(key, "#5c6472") if sel else "#5c6472"
            for it in items:
                it.setIcon(0, _dot_icon(color))
                it.setForeground(0, QBrush(_COLOR_SELECTED if sel else _COLOR_NORMAL))

    # ---------------- 交互 ----------------

    def _on_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        if item.data(0, KIND_ROLE) != "signal":
            return
        # 注意:QTreeWidgetItem 没有 isEnabled()(PySide6 无此方法,调用会抛
        # AttributeError 且被 Qt 静默吞掉),禁用态须用 flags 判断
        if not (item.flags() & Qt.ItemIsEnabled):
            return
        self.signalToggled.emit(item.data(0, FID_ROLE),
                                item.data(0, CH_ROLE),
                                item.data(0, NAME_ROLE))

    def _on_tree_menu(self, pos) -> None:
        """右键菜单:未识别报文 → 生成 DBC 骨架(R2)。"""
        item = self.tree.itemAt(pos)
        if item is None:
            return
        kind = item.data(0, KIND_ROLE)
        if kind not in ("unknown_group", "unknown"):
            return
        ch = item.data(0, CH_ROLE)
        menu = QMenu(self)
        act = menu.addAction("生成 DBC 骨架…")
        act.setToolTip("按观测到的 ID+DLC 生成无信号定义的 DBC,编辑后即可映射使用")
        if menu.exec(self.tree.viewport().mapToGlobal(pos)) == act:
            self.skeletonRequested.emit(int(ch))

    def _apply_filter(self, text: str) -> None:
        text = (text or "").strip().lower()
        root = self.tree.invisibleRootItem()

        def walk(item) -> bool:
            """返回该子树是否可见内容。"""
            any_visible = False
            for i in range(item.childCount()):
                if walk(item.child(i)):
                    any_visible = True
            own = True
            if text:
                own = text in item.text(0).lower() or text in item.text(1).lower()
                if item.data(0, KIND_ROLE) == "signal":
                    parent = item.parent()
                    own = own or text in parent.text(0).lower() or \
                        text in (parent.toolTip(0) or "").lower()
            visible = own or any_visible
            item.setHidden(not visible)
            return visible

        for i in range(root.childCount()):
            walk(root.child(i))
