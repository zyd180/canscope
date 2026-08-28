"""日志后台加载器:单遍扫描同时产出帧索引 + 统计(省去两次全扫)。
R2:经 log_reader 工厂支持 BLF/ASC/MF4;统计新增按通道 ID+DLC 清单。"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Signal

from core.log_reader import _file_obj, open_message_reader


def compute_index_and_stats(path, progress_cb=None) -> tuple:
    """单遍扫描日志:
    返回 (index, stats, n_frames)。
    - index 与 core.blf_cache._build_index 行格式完全一致(含错误帧);
    - stats 与 core.blf_parser.stats 输出结构/舍入一致(错误帧不入 by_id);
    - progress_cb(0~1):按文件读取位置回调(大文件进度)。
    """
    idx: dict = defaultdict(list)
    by_id: dict = {}
    ids_by_ch: dict = defaultdict(dict)
    channels: dict = {}
    total = fd = error = remote = 0
    first_ts = last_ts = None

    _path = Path(path)
    total_size = _path.stat().st_size or 1
    reader = open_message_reader(_path)
    fobj = _file_obj(reader)

    for m in reader:
        ts = m.timestamp
        if first_ts is None:
            first_ts = ts
        last_ts = ts
        total += 1

        ch = getattr(m, "channel", 0) or 0
        channels[ch] = channels.get(ch, 0) + 1

        if progress_cb and fobj is not None:
            try:
                progress_cb(min(0.99, fobj.tell() / total_size))
            except Exception:
                pass

        aid = m.arbitration_id
        # 索引行:所有帧都入缓存(与原 _build_index 一致)
        idx[aid].append((
            ts,
            ch,
            m.data,
            bool(getattr(m, "is_fd", False)),
            m.dlc,
        ))

        if getattr(m, "is_error_frame", False):
            error += 1
            continue
        if getattr(m, "is_fd", False):
            fd += 1
        if getattr(m, "is_remote_frame", False):
            remote += 1

        e = by_id.setdefault(aid, {"frame_id": aid, "count": 0,
                                   "first": ts, "last": ts, "dlc": 0})
        e["count"] += 1
        e["dlc"] = max(e["dlc"], getattr(m, "dlc", 0))
        if ts < e["first"]:
            e["first"] = ts
        if ts > e["last"]:
            e["last"] = ts

        d = ids_by_ch[ch]
        d[aid] = max(d.get(aid, 0), getattr(m, "dlc", 0))

    ids = sorted(by_id.values(), key=lambda x: -x["count"])
    for e in ids:
        span = e["last"] - e["first"]
        e["duration_s"] = round(span, 4)
        e["rate_hz"] = round(e["count"] / span, 2) if span > 0 else None

    stats = {
        "file": Path(path).name,
        "total_frames": total,
        "fd_frames": fd,
        "error_frames": error,
        "remote_frames": remote,
        "first_timestamp": first_ts,
        "last_timestamp": last_ts,
        "duration_s": round(last_ts - first_ts, 4) if first_ts is not None else 0.0,
        "unique_ids": len(ids),
        "channels": [{"channel": c, "frames": n} for c, n in sorted(channels.items())],
        "by_id": ids,
        "ids_by_channel": [
            {"channel": ch,
             "ids": [{"frame_id": fid, "dlc": dlc}
                     for fid, dlc in sorted(d.items())]}
            for ch, d in sorted(ids_by_ch.items())],
    }
    return dict(idx), stats, total


class _BlfLoadSignals(QObject):
    done = Signal(object)        # stats dict
    fail = Signal(str)
    progress = Signal(float)     # 0~1(按文件读取位置)


class BlfLoadTask(QRunnable):
    """后台任务:单遍建索引入缓存,回传统计与进度。"""

    def __init__(self, path):
        super().__init__()
        self.path = Path(path)
        self.sig = _BlfLoadSignals()

    def run(self) -> None:
        from core.blf_cache import store_index   # 延迟导入避免循环
        last_q = -1

        def throttled(p: float) -> None:
            """节流:0.5% 步进才发信号(大文件每帧回调,千万级发射会卡死 UI)。"""
            nonlocal last_q
            q = int(p * 200)
            if q != last_q:
                last_q = q
                self.sig.progress.emit(p)

        try:
            idx, stats, n = compute_index_and_stats(self.path,
                                                    progress_cb=throttled)
            store_index(self.path, idx, n)
            try:
                self.sig.done.emit(stats)
            except RuntimeError:
                pass   # 任务被更新的打开操作替换,sig 已销毁 → 静默丢弃
        except Exception as e:   # noqa: BLE001
            try:
                self.sig.fail.emit(f"日志解析失败: {e}")
            except RuntimeError:
                pass
