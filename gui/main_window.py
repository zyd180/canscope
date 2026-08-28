"""主窗口:工具栏 / 左侧报文树 / 中部示波器+页签 / 底部状态栏。"""
from __future__ import annotations

from pathlib import Path
import os

from PySide6.QtCore import QEvent, Qt, QSettings, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QLabel, QMainWindow,
                               QMessageBox, QProgressBar, QSizePolicy,
                               QSplitter, QTabWidget, QToolBar, QVBoxLayout,
                               QWidget)

from controller.app_state import AppState
from gui.id_stats_panel import IdStatsPanel
from gui.message_tree import MessageTree
from gui.scope_stack import ScopeStack
from gui.sig_stats_panel import SigStatsPanel
from gui.trace_panel import TracePanel

APP_TITLE = "CANScope · CAN 总线分析仪"
VERSION = "1.0.0"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1400, 850)

        self.state = AppState(self)
        self._build_toolbar()
        self._build_body()
        self._build_statusbar()
        self._wire()

        self._last_dir = str(Path.home())
        self.state.restore_last_project()

    # ---------------- UI 构建 ----------------

    def _build_toolbar(self) -> None:
        tb = QToolBar("main")
        tb.setMovable(False)
        self.addToolBar(tb)

        logo = QLabel("CANScope")
        logo.setObjectName("logo")
        tb.addWidget(logo)
        chip = QLabel(f"v{VERSION}")
        chip.setObjectName("versionChip")
        tb.addWidget(chip)
        tb.addSeparator()

        act_open = QAction("打开文件…", self)
        act_open.setShortcut(QKeySequence("Ctrl+O"))
        act_open.setToolTip("选择 .blf 与对应通道的 .dbc(可多选)")
        act_open.triggered.connect(self.on_open)
        tb.addAction(act_open)
        self.act_open = act_open

        act_demo = QAction("生成演示数据", self)
        act_demo.setToolTip("在 data/ 下生成 test.blf/test.dbc 并打开")
        act_demo.triggered.connect(self.on_make_demo)
        tb.addAction(act_demo)

        act_reset = QAction("重置缩放", self)
        act_reset.setToolTip("时间轴恢复全量范围 [0, 时长]")
        tb.addAction(act_reset)
        self.act_reset = act_reset

        act_export = QAction("导出 CSV", self)
        act_export.setToolTip("导出首个已选信号所属报文的全部信号(当前缩放区间)")
        act_export.setEnabled(False)
        act_export.triggered.connect(self.on_export_csv)
        tb.addAction(act_export)
        self.act_export = act_export

        act_blf = QAction("导出片段 BLF", self)
        act_blf.setToolTip("按当前缩放时间区间裁剪出独立 BLF(供 CANoe 复现)")
        act_blf.setEnabled(False)
        act_blf.triggered.connect(self.on_export_blf)
        tb.addAction(act_blf)
        self.act_blf = act_blf

        act_cfg = QAction("配置", self)
        act_cfg.setToolTip("总线参数 / 通道 DBC 映射 / 抖动标记")
        act_cfg.triggered.connect(self._open_config)
        tb.addAction(act_cfg)
        self.act_cfg = act_cfg

        from PySide6.QtWidgets import QSizePolicy, QWidget as _W
        spacer = _W()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(spacer)

    def _build_body(self) -> None:
        splitter = QSplitter(Qt.Horizontal)
        # 显式最小高度:Qt 会把分割器的 maximumHeight 同步提升到 min,
        # 否则其 max 被钳到 minimumSizeHint,中央区域被压扁、底部大片留白
        splitter.setMinimumHeight(760)

        # 左:报文树 + 折叠条(点击向左收起/展开,右侧界面随之扩展)
        self.tree_panel = MessageTree()
        splitter.addWidget(self.tree_panel)

        from PySide6.QtWidgets import QToolButton
        self.tree_strip = QToolButton()
        self.tree_strip.setFixedWidth(14)
        self.tree_strip.setText("◀")
        self.tree_strip.setToolTip("折叠/展开报文树")
        self.tree_strip.setStyleSheet(
            "QToolButton{background:#1a1d23;border:none;border-right:1px solid #2b2f38;"
            "color:#8a93a3;font-size:11px;padding:0;}"
            "QToolButton:hover{color:#4da3ff;background:#23262e;}")
        self.tree_strip.clicked.connect(self._toggle_tree)
        splitter.addWidget(self.tree_strip)

        # 右:播放条 + (信号侧栏 + 示波器堆叠) / 页签
        right = QSplitter(Qt.Vertical)

        from gui.playbar import PlayBar
        self.playbar = PlayBar()
        self.playbar.setMaximumHeight(40)

        chart_area = QSplitter(Qt.Horizontal)
        from gui.signal_sidebar import SignalSidebar
        self.sidebar = SignalSidebar()
        self.sidebar.setMinimumWidth(260)
        self.scope_stack = ScopeStack()
        chart_area.addWidget(self.sidebar)
        # R1:示波器列(多窗堆叠 + 底部缩略导航条)
        stack_col = QWidget()
        col_lay = QVBoxLayout(stack_col)
        col_lay.setContentsMargins(0, 0, 0, 0)
        col_lay.setSpacing(0)
        col_lay.addWidget(self.scope_stack, 1)
        from gui.minimap import MinimapBar
        self.minimap = MinimapBar()
        col_lay.addWidget(self.minimap)
        chart_area.addWidget(stack_col)
        chart_area.setSizes([290, 770])
        chart_area.setCollapsible(1, False)

        chart_wrap = QWidget()
        wrap_lay = QVBoxLayout(chart_wrap)
        wrap_lay.setContentsMargins(0, 0, 0, 0)
        wrap_lay.setSpacing(0)
        wrap_lay.addWidget(self.playbar)
        wrap_lay.addWidget(chart_area, 1)
        right.addWidget(chart_wrap)

        self.tabs = QTabWidget()
        self.trace_panel = TracePanel(self.state, self.scope_stack)
        self.id_panel = IdStatsPanel(self.state)
        self.sig_panel = SigStatsPanel(self.state)
        self.tabs.addTab(self.trace_panel, "Trace 报文流")
        self.tabs.addTab(self.id_panel, "ID 统计")
        self.tabs.addTab(self.sig_panel, "信号统计")
        right.addWidget(self.tabs)
        right.setSizes([560, 340])
        right.setCollapsible(0, False)

        splitter.addWidget(right)
        splitter.setSizes([360, 14, 1040])
        splitter.setStretchFactor(2, 1)
        splitter.setCollapsible(0, True)
        splitter.setCollapsible(1, False)
        splitter.setCollapsible(2, False)
        self._central_splitter = splitter
        self.setCentralWidget(splitter)

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        # 中央分割器最小高度跟随窗口,保证纵向撑满
        sp = getattr(self, "_central_splitter", None)
        if sp is not None:
            sp.setMinimumHeight(max(400, self.height() - 80))

    def _build_statusbar(self) -> None:
        sb = self.statusBar()
        self.lbl_total = QLabel("帧数 -")
        self.lbl_dur = QLabel("时长 -")
        self.lbl_ids = QLabel("报文数 -")
        self.lbl_anchor = QLabel("")
        self.lbl_anchor.setStyleSheet("color:#ff6b6b;")
        for w in (self.lbl_anchor, self.lbl_total, self.lbl_dur, self.lbl_ids):
            sb.addPermanentWidget(w)
        self.lbl_busy = QLabel("")
        self.lbl_busy.setObjectName("busyLabel")
        sb.addWidget(self.lbl_busy)
        # 大文件解析进度条(随 busy 消息显示/隐藏)
        self.busy_bar = QProgressBar()
        self.busy_bar.setFixedWidth(160)
        self.busy_bar.setRange(0, 100)
        self.busy_bar.setTextVisible(False)
        self.busy_bar.setVisible(False)
        sb.addWidget(self.busy_bar)
        self.lbl_hint = QLabel("提示:Ctrl+O 打开文件 · 滚轮缩放 · 拖拽平移 · "
                               "Ctrl+拖拽框选统计 · 双击锁定 Y 轴 · 点图名暂隐曲线 · "
                               "Shift+单击设锚点")
        sb.addWidget(self.lbl_hint)

    # ---------------- 状态接线 ----------------

    def _wire(self) -> None:
        s = self.state
        s.statsReady.connect(self._on_stats)
        s.channelsReady.connect(self._on_channels)
        s.signalsChanged.connect(self._refresh_views)
        s.errorRaised.connect(self._on_error)
        s.statusMessage.connect(lambda m: self.lbl_hint.setText(m))
        s.busyMessage.connect(self._on_busy)
        s.busyProgress.connect(self._on_busy_progress)
        self.tree_panel.signalToggled.connect(
            lambda fid, ch, name: s.toggle_signal(fid, ch, name))
        self.tree_panel.skeletonRequested.connect(self.on_gen_skeleton)

        st = self.scope_stack
        self.act_reset.triggered.connect(st.reset_zoom)
        st.itemRemoveRequested.connect(s.remove_from_plot)
        st.itemCopyRequested.connect(s.copy_to_plot)
        st.closePlotRequested.connect(s.remove_plot_window)
        st.clearPlotRequested.connect(s.clear_plot_signals)
        st.cursorMoved.connect(self._on_cursor_moved)
        st.cursorLeft.connect(lambda: self.sidebar.update_values(None))
        st.anchorChanged.connect(self._on_anchor_changed)
        # R1:缩略导航条 + 右键扩展动作
        st.xRangeChanged.connect(self.minimap.set_viewport)
        self.minimap.spanRequested.connect(st.apply_range_edit)
        st.statsRangeApplyRequested.connect(self._apply_stats_range)
        st.pngExportRequested.connect(self._export_plot_png)

        self.sidebar.removeRequested.connect(s.remove_signal)
        self.sidebar.addPlotRequested.connect(s.add_plot_window)
        self.sidebar.removePlotRequested.connect(s.remove_last_plot)
        self.sidebar.clearRequested.connect(s.clear_all_signals)

        # 页签联动
        s.statsReady.connect(lambda _st: self.id_panel.populate())
        s.channelsReady.connect(lambda _i, _m: self.trace_panel.populate())
        self._sig_refresh_timer = QTimer(self)
        self._sig_refresh_timer.setSingleShot(True)
        self._sig_refresh_timer.setInterval(300)
        self._sig_refresh_timer.timeout.connect(self.sig_panel.refresh)

        # ---- 回放 ----
        from controller.playback import PlaybackController
        self.pbc = PlaybackController(s, self)
        pb = self.playbar
        pb.playToggle.connect(self.pbc.toggle_play)
        pb.stopRequested.connect(self._on_play_stop)
        pb.rateChanged.connect(self.pbc.set_rate)
        pb.seekRequested.connect(self.pbc.seek)
        self.pbc.stateChanged.connect(self._on_play_state)
        self.pbc.progress.connect(pb.on_progress)
        self.pbc.renderData.connect(self.scope_stack.set_play_data)
        self.pbc.diagnostics.connect(pb.set_diag)
        self.pbc.ended.connect(lambda: self.scope_stack.exit_play_mode())

        # ---- 配置弹窗 ----
        self.settings = QSettings()
        self.scope_stack.show_jitter_marks(
            self.settings.value("ui/jitter_marks", "false") in ("true", True))
        self.sig_panel.cycleStatsReady.connect(self._on_cycle_stats)

        # ---- 选中信号三态记忆(QSettings,绑定 BLF 路径) ----
        s.channelsReady.connect(lambda _i, _m: QTimer.singleShot(0,
                                                                self._restore_selection))
        s.signalsChanged.connect(self._queue_save_selection)
        self._restoring = False
        self._restore_pending = 0
        self._sel_save_timer = QTimer(self)
        self._sel_save_timer.setSingleShot(True)
        self._sel_save_timer.setInterval(400)
        self._sel_save_timer.timeout.connect(self._save_selection)

    # ---------------- 配置弹窗 ----------------

    def _toggle_tree(self) -> None:
        """折叠/展开报文树:折叠时右侧界面整体向左扩展。"""
        sp = self._central_splitter
        if self.tree_panel.isVisible():
            self._tree_width = sp.sizes()[0]
            self.tree_panel.hide()
            self.tree_strip.setText("▶")
            total = sum(sp.sizes())
            sp.setSizes([0, 14, max(100, total - 14)])
        else:
            self.tree_panel.show()
            self.tree_strip.setText("◀")
            w = getattr(self, "_tree_width", 360) or 360
            total = sum(sp.sizes())
            sp.setSizes([w, 14, max(100, total - 14 - w)])

    def _open_config(self) -> None:
        from gui.config_drawer import ConfigDialog
        from gui.theme import apply_dark_title_bar
        dlg = ConfigDialog(self.state, self.settings, self)
        apply_dark_title_bar(dlg)
        dlg.mappingApplied.connect(self.state.apply_channel_mapping)
        dlg.configSaved.connect(lambda: self.id_panel.refresh_bus_load())
        dlg.jitterToggled.connect(self.scope_stack.show_jitter_marks)
        # 居中到主窗口(Windows 默认位置可能贴边)
        dlg.resize(480, min(560, int(self.height() * 0.85)))
        geo = self.geometry()
        dlg.move(geo.center().x() - dlg.width() // 2,
                 geo.center().y() - dlg.height() // 2)
        dlg.exec()

    # ---------------- 选中信号记忆 ----------------

    def _sel_key(self) -> str:
        p = self.state.blf_path
        return f"sel/{p.as_posix() if p else 'none'}"

    def _restore_selection(self) -> None:
        """三态:首次(无记录)自动选前两个信号;有记录恢复;用户清空过则保持空。"""
        s = self.state
        val = self.settings.value(self._sel_key(), "", type=str)
        # CLEARED:清空标记(不用 @ 开头,避开 QSettings 值转义);兼容历史 @cleared
        if val in ("CLEARED", "@cleared", "@@cleared"):
            return
        targets = []
        if val:
            for k in filter(None, val.split(";")):
                try:
                    fid, ch, name = k.split("|")
                    targets.append((int(fid), int(ch), name))
                except ValueError:
                    continue
            # 过滤已失效项(通道重映射/报文无数据)
            valid = set()
            for ch, msgs in s.messages_by_channel.items():
                for m in msgs:
                    for n in m["signals"]:
                        valid.add((m["frame_id"], ch, n))
            targets = [t for t in targets if t in valid]
        else:
            targets = s.first_auto_selection()
        if not targets:
            return
        self._restoring = True
        self._restore_pending = len(targets)
        for fid, ch, name in targets:
            s.toggle_signal(fid, ch, name)

    def _queue_save_selection(self) -> None:
        if self.state._loading:
            return   # 文件加载中的清空不写入记忆
        if self._restoring:
            if self._restore_pending > 0:
                self._restore_pending -= 1
                if self._restore_pending == 0:
                    self._restoring = False
            return
        self._sel_save_timer.start()

    def _save_selection(self) -> None:
        s = self.state
        if s._loading:
            return   # 定时器触发时可能已进入下一次加载
        seen, keys = set(), []
        for it in s.signals_list:
            if it.key not in seen:
                seen.add(it.key)
                keys.append(it.key)
        self.settings.setValue(self._sel_key(),
                               ";".join(keys) if keys else "CLEARED")

    # ---------------- 回放 ----------------

    def _on_play_state(self, mode: str) -> None:
        self.playbar.set_state(mode)
        if mode == "playing":
            self.scope_stack.enter_play_mode()
        elif mode in ("idle",):
            # 停止:恢复静态曲线(ended 的恢复在 ended 信号里做)
            self.scope_stack.exit_play_mode()
            self.playbar.on_progress(0.0)

    def _on_play_stop(self) -> None:
        self.pbc.stop()   # stateChanged('idle') → 恢复静态

    def _on_cycle_stats(self, results: dict) -> None:
        """周期统计完成 → 抖动峰值标记(转相对时间)。"""
        t0 = self.state.t0
        marks = {}
        for (fid, ch), r in results.items():
            j = r.get("jitter_max_at")
            if j is not None:
                marks[(fid, ch)] = j - t0
        self.scope_stack.set_jitter_marks(marks)

    # ---------------- 刷新 ----------------

    def _refresh_views(self) -> None:
        s = self.state
        # 播放中变更信号集 → 自动停止回放并恢复静态(Web 版行为)
        if hasattr(self, "pbc") and self.pbc.mode in ("playing", "paused", "building"):
            self.pbc.teardown()
            self.scope_stack.exit_play_mode()
        self.scope_stack.refresh(s.signals_list, s.plot_count)
        self.sidebar.rebuild(s.signals_list)
        self.tree_panel.refresh_selection(s.selected_colors())
        self.act_export.setEnabled(bool(s.signals_list))
        self.playbar.setEnabled(bool(s.signals_list))
        self.minimap.refresh_from(s.signals_list)
        if s.signals_list:
            self._sig_refresh_timer.start()   # 防抖刷新信号统计

    def _on_busy(self, text: str) -> None:
        self.lbl_busy.setText(text)
        self.busy_bar.setVisible(bool(text))

    def _on_busy_progress(self, p: float) -> None:
        self.busy_bar.setValue(int(p * 100))
        lp = self.state._loading_path
        if lp is not None:
            self.lbl_busy.setText(f"正在解析 {lp.name} … {int(p * 100)}%")

    def _on_cursor_moved(self, t: float) -> None:
        self.sidebar.update_values(t)
        self._update_anchor_text(t)

    def _on_anchor_changed(self, t) -> None:
        self.sidebar.set_anchor(t)   # 侧栏"锚点值"列随锚点刷新
        self._update_anchor_text(t)

    def _update_anchor_text(self, cursor_t) -> None:
        a = self.scope_stack.anchor
        if a is None:
            self.lbl_anchor.setText("")
            return
        if cursor_t is None:
            self.lbl_anchor.setText(f"锚点 {a:.3f}s")
        else:
            dt = abs(cursor_t - a)
            f_hz = 1.0 / dt if dt > 1e-9 else float("inf")
            self.lbl_anchor.setText(
                f"锚点 {a:.3f}s · Δ{dt:.3f}s ({f_hz:.1f} Hz)")

    def _on_stats(self, stats: dict) -> None:
        dur = stats.get("duration_s") or 0.0
        self.lbl_total.setText(f"帧数 {stats.get('total_frames', 0):,}")
        self.lbl_dur.setText(f"时长 {dur:.2f}s")
        self.lbl_ids.setText(f"报文数 {stats.get('unique_ids', 0)}")
        self.act_blf.setEnabled(True)
        if hasattr(self, "pbc"):
            self.pbc.teardown()
        self.scope_stack.set_anchor(None)
        self.scope_stack.set_duration(dur)
        self.playbar.set_duration(dur)
        # R1:导航条随时长重建(无信号时显示空态文案)
        self.minimap.setVisible(dur > 0)
        self.minimap.set_duration(dur)
        self.minimap.refresh_from(self.state.signals_list)

    def _on_channels(self, channels_info: list, messages: dict) -> None:
        self.tree_panel.rebuild(channels_info, messages,
                                self.state.has_data,
                                self.state.selected_colors())

    def _on_error(self, msg: str) -> None:
        self.statusBar().showMessage(msg, 8000)
        QMessageBox.warning(self, "CANScope", msg)

    # ---------------- 动作 ----------------

    def on_open(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "打开日志 / DBC(BLF、ASC、MF4;CAN FD 多通道请按通道顺序选 DBC)",
            self._last_dir,
            "CAN 文件 (*.blf *.asc *.mf4 *.dbc *.log *.txt);;"
            "BLF 日志 (*.blf *.log);;ASC 日志 (*.asc *.txt);;"
            "MF4 日志 (*.mf4);;DBC 数据库 (*.dbc)")
        if not paths:
            return
        if paths:
            self._last_dir = str(Path(paths[0]).parent)
        self.state.open_paths([Path(p) for p in paths])

    def on_make_demo(self) -> None:
        from services.demo_data import generate
        from services.project_config import DATA_DIR
        try:
            dbc_path, blf_path = generate(DATA_DIR)
        except Exception as e:
            self._on_error(f"生成演示数据失败: {e}")
            return
        self.state.open_paths([blf_path, dbc_path])

    def _apply_stats_range(self, plot_id: int) -> None:
        """R1:把某示波器框选的相对时间区间转绝对时间,写入信号统计页过滤。"""
        st = self.scope_stack
        if not (0 <= plot_id < len(st.plots)):
            return
        reg = st.plots[plot_id].region_times()
        if not reg:
            return
        t0 = self.state.t0
        self.sig_panel.set_range_filter(t0 + reg[0], t0 + reg[1])
        self.tabs.setCurrentWidget(self.sig_panel)

    def _export_plot_png(self, plot_id: int) -> None:
        """R1:导出指定示波器窗口为 PNG(附 CANScope 水印)。"""
        st = self.scope_stack
        if not (0 <= plot_id < len(st.plots)):
            return
        default = f"CANScope_scope{plot_id + 1}.png"
        out, _sel = QFileDialog.getSaveFileName(self, "导出本窗图像", default,
                                                "PNG (*.png)")
        if not out:
            return
        if st.plots[plot_id].render_png(out):
            self.lbl_hint.setText(f"已导出本窗图像 → {out}")
        else:
            self._on_error("导出 PNG 失败")

    def on_export_blf(self) -> None:
        """R2:按当前缩放区间导出 BLF 片段。"""
        s = self.state
        if s.blf_path is None or not s.stats:
            return
        rx0, rx1 = self.scope_stack.get_xrange()
        t0 = s.t0
        start = (t0 + rx0) if rx0 > 0 else None
        end = (t0 + rx1) if rx1 < s.duration else None
        stem = Path(s.blf_path).stem
        default = f"{stem}_{rx0:.1f}-{rx1:.1f}s.blf"
        out, _ = QFileDialog.getSaveFileName(self, "导出 BLF 片段", default,
                                             "BLF (*.blf)")
        if not out:
            return
        self.lbl_busy.setText("导出片段 …")

        def done(result):
            n, path = result
            self.lbl_busy.setText("")
            self.lbl_hint.setText(f"已导出片段 {n:,} 帧 → {path}")

        s.export_blf_segment_async(Path(out), done, start=start, end=end)

    def on_gen_skeleton(self, channel: int) -> None:
        """R2:为某通道"未识别报文"生成 DBC 骨架(起步器,不自动改映射)。"""
        s = self.state
        items = s.unknown_ids_for(channel)
        if not items:
            return
        stem = Path(s.blf_path).stem if s.blf_path else "log"
        default = f"skeleton_{stem}_ch{channel}.dbc"
        out, _ = QFileDialog.getSaveFileName(self, "生成 DBC 骨架", default,
                                             "DBC (*.dbc)")
        if not out:
            return
        try:
            from services import exporters
            n = exporters.export_dbc_skeleton(items, Path(out))
        except Exception as e:
            self._on_error(f"生成 DBC 骨架失败: {e}")
            return
        self.lbl_hint.setText(
            f"已生成 {n} 个报文骨架 → {out};编辑信号定义后可在「配置」中映射到 CH{channel}")

    def on_export_csv(self) -> None:
        s = self.state
        if not s.signals_list:
            return
        item = s.signals_list[0]
        rx0, rx1 = self.scope_stack.get_xrange()
        t0 = s.t0
        try:
            from core import dbc_parser
            db = dbc_parser.load_database(item.dbc_path)
            n_sig = len(db.get_message_by_frame_id(item.frame_id).signals)
        except Exception:
            n_sig = 1
        from services.exporters import default_csv_name
        default = default_csv_name(s.stats["file"] if s.stats else "log",
                                   item.frame_id, item.channel, n_sig)
        out, _ = QFileDialog.getSaveFileName(self, "导出 CSV", default,
                                             "CSV (*.csv)")
        if not out:
            return
        self.lbl_busy.setText("导出中 …")

        def done(result):
            n, path = result
            self.lbl_busy.setText("")
            self.lbl_hint.setText(f"已导出 {n} 行 → {path}")

        s.export_csv_async(item, Path(out), done,
                           start=(t0 + rx0) if rx0 > 0 else None,
                           end=(t0 + rx1) if rx1 < s.duration else None)
