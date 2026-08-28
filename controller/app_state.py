"""中央状态模型:持有全局状态,连接 GUI 与 core/services,后台任务调度。

移植自 Web 版前端 state{}/playState{} 与 API 路由胶水层;
GUI 组件只订阅这里的信号,不直接触碰 core。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import QObject, Signal

from core import blf_cache, dbc_parser
from core.decoder import decode_signal
from core.file_types import ALLOWED_EXTENSIONS, LOG_KINDS, detect_kind
from gui.palette import alloc_color
from services import exporters, project_config, stats_service
from services.stats_service import cycle_stats, signal_stats  # noqa: F401 便捷导出
from workers.blf_loader import BlfLoadTask, compute_index_and_stats
from workers.task_runner import TaskRunner

MAX_POINTS = 200_000   # 静态解码降采样上限(与 Web 版一致)
MAX_SIGNALS = 64       # 已选信号上限


@dataclass
class SignalItem:
    """一个已选信号:定义信息 + 解码后的时间序列。"""
    frame_id: int
    channel: int
    name: str
    dbc_path: str
    plot_id: int = 0                      # 所属示波器窗口(M1 全为 0)
    color: str = "#4da3ff"                # 曲线颜色
    unit: str = ""
    comment: Optional[str] = None
    senders: list = field(default_factory=list)
    choices: Optional[dict] = None        # {int 值: 状态名}
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    detail: dict = field(default_factory=dict)   # message_detail 中该信号条目
    times: list = field(default_factory=list)    # 相对时间(s)
    values: list = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.frame_id}|{self.channel}|{self.name}"

    @property
    def is_choices(self) -> bool:
        return bool(self.choices)


class AppState(QObject):
    # 注意:容器参数一律用 object(PySide6 的 dict/list 签名会转 QVariantMap,
    # 要求字符串键;int 键字典会转换失败且槽不触发)
    statsReady = Signal(object)            # BLF 统计
    channelsReady = Signal(object, object)   # (channels_info, messages_by_channel)
    signalAdded = Signal(object)         # SignalItem
    signalRemoved = Signal(str)          # key
    signalsCleared = Signal()
    signalsChanged = Signal()            # 条目集合变化(侧栏/示波器/树全量刷新)
    errorRaised = Signal(str)
    statusMessage = Signal(str)
    busyMessage = Signal(str)            # "" 表示清除忙碌提示
    busyProgress = Signal(float)         # 大文件解析进度 0~1

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.config = project_config.load_config()
        self.runner = TaskRunner(on_error=self.errorRaised.emit, parent=self)

        self.blf_path: Optional[Path] = None
        self.stats: Optional[dict] = None
        self.t0: float = 0.0             # 相对时间基准(首个帧时间戳)
        self.duration: float = 0.0
        self.channel_dbc: dict = {}      # {int channel: dbc 路径 str}
        self.has_data: set = set()       # 日志中出现过的 frame_id
        self.signals_list: list = []     # list[SignalItem](同一逻辑信号可在多个示波器)
        self.plot_count: int = 1         # 示波器窗口数
        self.channels_info: list = []            # [{channel,frames,dbc}]
        self.messages_by_channel: dict = {}      # {channel: [报文摘要]}
        self.dbc_files: list = []                # 打开过的 DBC 路径(映射下拉候选)

        self._pending_dbcs: list = []    # 打开文件时随行的 DBC 列表
        self._loading_path: Optional[Path] = None
        self._loading: bool = False      # 加载中(抑制选中记忆误写)
        self._blf_tasks: set = set()     # 在飞任务强引用(防 GC 崩溃)
        self._load_seq: int = 0          # 打开代际号(丢弃过期加载结果)

    # ---------------- 文件打开 / 工程恢复 ----------------

    def open_paths(self, paths) -> None:
        """打开用户选择的文件集合:取第一个日志文件,DBC 按选择顺序映射到各通道。

        文件类型按内容识别(扩展名不可靠:.log/.txt 可能是 BLF/ASC/DBC;
        R2 起支持 BLF/ASC/MF4 三类日志)。
        """
        logs, dbcs, rejected = [], [], []
        for p in paths:
            kind = detect_kind(p)
            if kind in LOG_KINDS:
                logs.append(p)
            elif kind == ".dbc":
                dbcs.append(p)
            elif p.suffix.lower() in ALLOWED_EXTENSIONS:
                rejected.append(p)
        if rejected:
            self.statusMessage.emit(
                "已跳过无法识别的文件: " + ", ".join(p.name for p in rejected))
        if not logs:
            self.errorRaised.emit("未选择日志文件(BLF/ASC/MF4)")
            return
        log = logs[0]
        if not log.is_file():
            self.errorRaised.emit(f"日志文件不存在: {log}")
            return
        dbcs = [d for d in dbcs if d.is_file()]
        for d in dbcs:
            if str(d) not in self.dbc_files:
                self.dbc_files.append(str(d))
        if len(logs) > 1:
            self.statusMessage.emit(f"一次仅分析一个日志,已选用 {log.name}")

        # 先置加载标志再清信号:清空引发的 signalsChanged 不得写入选中记忆
        self._loading = True
        self._clear_signals()
        self.stats = None
        self.blf_path = log
        self._pending_dbcs = dbcs
        self._loading_path = log
        self._load_seq += 1
        seq = self._load_seq

        self.busyMessage.emit(f"正在解析 {log.name} …")
        self.busyProgress.emit(0.0)
        task = BlfLoadTask(log)
        self._blf_tasks.add(task)
        task.sig.progress.connect(self.busyProgress.emit)
        task.sig.done.connect(lambda stats, t=task, q=seq:
                              (self._blf_tasks.discard(t), self._on_blf_loaded(q, stats)))
        task.sig.fail.connect(lambda msg, t=task, q=seq:
                              (self._blf_tasks.discard(t), self._on_load_fail(q, msg)))
        from PySide6.QtCore import QThreadPool
        QThreadPool.globalInstance().start(task)

    def restore_last_project(self) -> bool:
        """启动时尝试恢复上次工程;成功返回 True。"""
        cfg = self.config
        blf = cfg.get("blf")
        if not blf or not Path(blf).is_file():
            return False
        ch_map = cfg.get("channels") or {}
        try:
            dbcs = [Path(v) for _, v in sorted(ch_map.items(), key=lambda kv: int(kv[0]))]
        except ValueError:
            dbcs = []
        dbcs = [d for d in dbcs if d.is_file()]
        self.open_paths([Path(blf)] + dbcs)
        return True

    def _on_load_fail(self, seq: int, msg: str) -> None:
        self._loading = False
        if seq != self._load_seq:
            return   # 过期加载结果,丢弃
        self.busyMessage.emit("")
        self.errorRaised.emit(msg)

    def _on_blf_loaded(self, seq: int, stats: dict) -> None:
        self._loading = False
        if seq != self._load_seq:
            return   # 过期加载结果,丢弃
        self.stats = stats
        first = stats.get("first_timestamp")
        self.t0 = first if first is not None else 0.0
        self.duration = stats.get("duration_s") or 0.0
        self.has_data = {e["frame_id"] for e in stats.get("by_id", [])}

        channels = [c["channel"] for c in stats.get("channels", [])]
        frames_by_ch = {c["channel"]: c["frames"] for c in stats.get("channels", [])}

        # DBC 按选择顺序映射到升序通道
        mapping: dict = {}
        for i, ch in enumerate(sorted(channels)):
            if i < len(self._pending_dbcs):
                mapping[ch] = str(self._pending_dbcs[i])
        self.channel_dbc = mapping
        self._rebuild_channels(mapping)

        self._save_project(mapping)
        self.busyMessage.emit("")
        self.statsReady.emit(stats)
        self.statusMessage.emit(
            f"已载入 {stats['file']}:总帧数 {stats['total_frames']:,} · "
            f"时长 {stats.get('duration_s') or 0.0:.1f}s · 报文数 {stats['unique_ids']}")

    def _rebuild_channels(self, mapping: dict) -> None:
        """按映射重建通道信息与报文摘要,并广播 channelsReady。

        R2:同时装配"未识别报文"清单(日志中出现但 DBC 未定义的 ID+DLC),
        供报文树灰组展示与 DBC 骨架生成。
        """
        if not self.stats:
            return
        frames_by_ch = {c["channel"]: c["frames"] for c in self.stats.get("channels", [])}
        ids_by_ch = {e["channel"]: e.get("ids", [])
                     for e in self.stats.get("ids_by_channel", [])}
        info, messages = [], {}
        for ch in [c["channel"] for c in self.stats.get("channels", [])]:
            dbc = mapping.get(ch)
            msgs = []
            if dbc:
                try:
                    db = dbc_parser.load_database(dbc)
                    msgs = dbc_parser.messages_summary(db)
                except Exception as e:
                    self.errorRaised.emit(f"加载 DBC 失败({Path(dbc).name}): {e}")
            known = {m["frame_id"] for m in msgs}
            unknown = [(i["frame_id"], i["dlc"])
                       for i in ids_by_ch.get(ch, []) if i["frame_id"] not in known]
            info.append({"channel": ch,
                         "frames": frames_by_ch.get(ch, 0),
                         "dbc": Path(dbc).name if dbc else None,
                         "unknown": unknown})
            messages[ch] = msgs
        self.channel_dbc = mapping
        self.channels_info = info
        self.messages_by_channel = messages
        self.channelsReady.emit(info, messages)

    def unknown_ids_for(self, channel: int) -> list:
        """某通道的未识别 (frame_id, dlc) 列表(R2 DBC 骨架生成数据源)。"""
        for info in self.channels_info:
            if info["channel"] == channel:
                return list(info.get("unknown") or [])
        return []

    def apply_channel_mapping(self, mapping: dict) -> None:
        """配置抽屉保存通道映射:重建树并持久化(不重新解析 BLF)。"""
        cleaned = {int(c): p for c, p in mapping.items() if p}
        self._rebuild_channels(cleaned)
        self._save_project(cleaned)

    def first_auto_selection(self) -> list:
        """三态恢复之"首次":首个有数据通道 → 首个有数据报文 → 前两个信号。"""
        for info in sorted(self.channels_info, key=lambda x: x["channel"]):
            ch = info["channel"]
            if not self.channel_dbc.get(ch):
                continue
            for m in self.messages_by_channel.get(ch, []):
                if m["frame_id"] in self.has_data and m["signals"]:
                    return [(m["frame_id"], ch, n) for n in m["signals"][:2]]
        return []

    def _save_project(self, mapping: dict) -> None:
        cfg = self.config
        cfg["blf"] = str(self._loading_path) if self._loading_path else None
        cfg["dbc"] = next(iter(mapping.values()), None)
        cfg["channels"] = {str(c): p for c, p in mapping.items()}
        try:
            project_config.save_config(cfg)
        except OSError as e:
            self.errorRaised.emit(f"配置保存失败: {e}")

    # ---------------- 报文树数据辅助 ----------------

    def channel_frames(self, ch: int) -> int:
        if not self.stats:
            return 0
        for c in self.stats.get("channels", []):
            if c["channel"] == ch:
                return c["frames"]
        return 0

    # ---------------- 信号增删 ----------------

    def toggle_signal(self, frame_id: int, channel: int, name: str) -> None:
        """点击树中信号:已选中则全部移除,否则解码并添加(优先复用空示波器)。"""
        key = f"{frame_id}|{channel}|{name}"
        if any(s.key == key for s in self.signals_list):
            self.remove_signal(key)
            return
        if len(self.signals_list) >= MAX_SIGNALS:
            self.errorRaised.emit(f"最多同时显示 {MAX_SIGNALS} 个信号")
            return
        if self.blf_path is None:
            self.errorRaised.emit("请先打开 BLF 文件")
            return

        dbc_path = self.channel_dbc.get(channel)
        if not dbc_path:
            self.errorRaised.emit(f"通道 {channel} 未配置 DBC")
            return
        try:
            db = dbc_parser.load_database(dbc_path)
            msg = db.get_message_by_frame_id(frame_id)
            sig = msg.get_signal_by_name(name)
        except KeyError as e:
            self.errorRaised.emit(f"DBC 中无对应报文/信号: {e}")
            return
        except ValueError as e:
            self.errorRaised.emit(str(e))
            return

        meta = {
            "unit": sig.unit or "",
            "comment": getattr(sig, "comment", None),
            "senders": list(getattr(msg, "senders", []) or []),
            "minimum": sig.minimum,
            "maximum": sig.maximum,
            "choices": ({int(k): str(v) for k, v in sig.choices.items()}
                        if getattr(sig, "choices", None) else None),
        }
        blf_path, t0 = self.blf_path, self.t0

        def work():
            res = decode_signal(blf_path, db, frame_id, name,
                                max_points=MAX_POINTS, channel=channel)
            times = [round(t - t0, 6) for t in res["times"]]
            return res, times, meta, str(dbc_path)

        self.busyMessage.emit(f"解码 {name} …")
        self.runner.run(work, lambda r: self._on_signal_decoded(frame_id, channel, name, r))

    def _on_signal_decoded(self, frame_id: int, channel: int, name: str, result) -> None:
        res, times, meta, dbc_path = result
        item = SignalItem(
            frame_id=frame_id, channel=channel, name=name, dbc_path=dbc_path,
            plot_id=self._alloc_plot(),
            color=alloc_color([s.color for s in self.signals_list]),
            unit=meta["unit"], comment=meta["comment"], senders=meta["senders"],
            choices=meta["choices"], minimum=meta["minimum"], maximum=meta["maximum"],
            times=times, values=res["values"],
        )
        self.signals_list.append(item)
        self.busyMessage.emit("")
        if not times:
            self.statusMessage.emit(f"{name}:日志中无该报文数据(DBC 有定义但日志没发)")
        self.signalAdded.emit(item)
        self.signalsChanged.emit()

    # ---------------- 示波器窗口管理 ----------------

    def _alloc_plot(self) -> int:
        """新信号落窗:优先复用空示波器,无空窗则新建(与 Web 版一致)。"""
        used = {s.plot_id for s in self.signals_list}
        for pid in range(self.plot_count):
            if pid not in used:
                return pid
        pid = self.plot_count
        self.plot_count += 1
        return pid

    def add_plot_window(self) -> None:
        self.plot_count += 1
        self.signalsChanged.emit()

    def remove_last_plot(self) -> None:
        """删除最后一个示波器窗口(连同其中的信号)。"""
        if self.plot_count <= 1:
            return
        self.remove_plot_window(self.plot_count - 1)

    def remove_plot_window(self, plot_id: int) -> None:
        """关闭指定示波器:移除其中信号并紧凑重编号;最后一个窗口仅清空信号。"""
        removed = [s for s in self.signals_list if s.plot_id == plot_id]
        if not removed and self.plot_count <= 1:
            return
        self.signals_list = [s for s in self.signals_list if s.plot_id != plot_id]
        if self.plot_count > 1:
            self.plot_count -= 1
            # 紧凑重编号,保持窗口 id 连续
            remap = {old: new for new, old in
                     enumerate(sorted({s.plot_id for s in self.signals_list}))}
            for s in self.signals_list:
                s.plot_id = remap[s.plot_id]
        self.signalsChanged.emit()

    def remove_from_plot(self, key: str, plot_id: int) -> None:
        """从单个示波器移除信号(chip ✕)。"""
        before = len(self.signals_list)
        self.signals_list = [s for s in self.signals_list
                             if not (s.key == key and s.plot_id == plot_id)]
        if len(self.signals_list) != before:
            self.signalsChanged.emit()

    def clear_plot_signals(self, plot_id: int) -> None:
        """清空指定示波器的全部信号(窗口保留)。"""
        before = len(self.signals_list)
        self.signals_list = [s for s in self.signals_list if s.plot_id != plot_id]
        if len(self.signals_list) != before:
            self.signalsChanged.emit()

    def copy_to_plot(self, key: str, plot_id: int) -> None:
        """把已选信号复制到另一示波器(复用已解码数据,不重新解码)。"""
        if any(s.key == key and s.plot_id == plot_id for s in self.signals_list):
            return
        src = self.find_signal(key)
        if src is None:
            return
        if len(self.signals_list) >= MAX_SIGNALS:
            self.errorRaised.emit(f"最多同时显示 {MAX_SIGNALS} 个信号")
            return
        import dataclasses
        clone = dataclasses.replace(src, plot_id=plot_id)
        self.signals_list.append(clone)
        self.signalsChanged.emit()

    def clear_all_signals(self) -> None:
        """清空全部已选信号(窗口保留)。"""
        self._clear_signals()
        self.signalsChanged.emit()

    def remove_signal(self, key: str) -> None:
        before = len(self.signals_list)
        self.signals_list = [s for s in self.signals_list if s.key != key]
        if len(self.signals_list) != before:
            self.signalRemoved.emit(key)
            self.statusMessage.emit(f"已移除信号 {key.split('|')[-1]}")
            self.signalsChanged.emit()

    def _clear_signals(self) -> None:
        had = bool(self.signals_list)
        self.signals_list = []
        if had:
            self.signalsCleared.emit()
            self.signalsChanged.emit()

    # ---------------- 数据服务(GUI 直调,均走帧缓存) ----------------

    def signal_statistics(self, item: SignalItem,
                          start=None, end=None) -> dict:
        db = dbc_parser.load_database(item.dbc_path)
        return signal_stats(self.blf_path, db, item.frame_id, item.name,
                            channel=item.channel, start=start, end=end)

    def cycle_statistics(self, frame_id: int, channel: int,
                         start=None, end=None) -> dict:
        dbc_path = self.channel_dbc.get(channel)
        db = dbc_parser.load_database(dbc_path)
        return cycle_stats(self.blf_path, db, frame_id,
                           channel=channel, start=start, end=end)

    def bus_load_info(self, channel: Optional[int] = None) -> dict:
        cfg = self.config
        from services.stats_service import bus_load
        return bus_load(self.blf_path,
                        int(cfg.get("baudrate_arb", 500000)),
                        int(cfg.get("baudrate_data", 2000000)),
                        cfg.get("bus_type", "canfd"), channel=channel)

    # ---------------- 后台取数(回调在主线程执行) ----------------

    def fetch_trace(self, frame_id: int, channel: int, callback: Callable,
                    sig_filter=None, sig_value=None,
                    start=None, end=None, offset: int = 0, limit: int = 200) -> None:
        """Trace 分页帧列表(start/end 为绝对时间戳)。"""
        dbc_path = self.channel_dbc.get(channel)

        def work():
            db = dbc_parser.load_database(dbc_path)
            return stats_service.frames_page(
                self.blf_path, db, frame_id, channel=channel,
                start=start, end=end, limit=limit, offset=offset,
                sig_filter=sig_filter, sig_value=sig_value)

        self.runner.run(work, callback)

    def fetch_bus_load(self, callback: Callable) -> None:
        def work():
            return self.bus_load_info()
        self.runner.run(work, callback)

    def fetch_signal_stats(self, item: SignalItem, callback: Callable,
                           start=None, end=None) -> None:
        def work():
            return self.signal_statistics(item, start, end)
        self.runner.run(work, callback)

    def fetch_cycle_stats(self, frame_id: int, channel: int, callback: Callable,
                          start=None, end=None) -> None:
        def work():
            return self.cycle_statistics(frame_id, channel, start, end)
        self.runner.run(work, callback)

    def export_csv_async(self, item: SignalItem, out_path: Path,
                         callback: Callable, start=None, end=None) -> None:
        """导出该信号所属报文的全部信号(start/end 为绝对时间戳)。"""
        dbc_path = item.dbc_path
        blf_path = self.blf_path
        frame_id = item.frame_id
        channel = item.channel

        def work():
            db = dbc_parser.load_database(dbc_path)
            n = exporters.export_csv(blf_path, db, frame_id, None,
                                     out_path, channel=channel,
                                     start=start, end=end)
            return n, str(out_path)

        self.runner.run(work, callback)

    def export_blf_segment_async(self, out_path: Path, callback: Callable,
                                 start=None, end=None) -> None:
        """R2:按时间区间裁剪出独立 BLF 片段(走帧缓存,堆合并恢复时序)。"""
        blf_path = self.blf_path

        def work():
            n = exporters.export_blf_segment(blf_path, out_path,
                                             start=start, end=end)
            return n, str(out_path)

        self.runner.run(work, callback)

    def export_trace_async(self, frame_id: int, channel: int, out_path: Path,
                           callback: Callable, sig_filter=None,
                           sig_value=None, start=None, end=None) -> None:
        """R2:Trace 全量 CSV(应用当前报文/信号值过滤与时间区间)。"""
        dbc_path = self.channel_dbc.get(channel)
        blf_path = self.blf_path

        def work():
            db = dbc_parser.load_database(dbc_path)
            n = exporters.export_trace_csv(
                blf_path, db, frame_id, out_path, channel=channel,
                start=start, end=end, sig_filter=sig_filter,
                sig_value=sig_value)
            return n, str(out_path)

        self.runner.run(work, callback)

    def selected_keys(self) -> set:
        return {s.key for s in self.signals_list}

    def selected_colors(self) -> dict:
        """{key: color} 供树高亮与色点着色。"""
        return {s.key: s.color for s in self.signals_list}

    def find_signal(self, key: str) -> Optional[SignalItem]:
        for s in self.signals_list:
            if s.key == key:
                return s
        return None
