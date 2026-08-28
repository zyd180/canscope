"""日志解析:流式统计,不把整个文件读入内存。
R2:经 log_reader 工厂支持 BLF/ASC/MF4;统计新增按通道的 ID+DLC 清单
(供报文树"未识别报文"分组与 DBC 骨架生成使用)。"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Union

from core.log_reader import _file_obj, open_message_reader


def stats(path: Union[str, Path], progress_cb=None) -> dict:
    """单遍扫描日志,返回帧数/时间范围/错误帧/按 ID 聚合统计/通道分布。
    progress_cb(0~1):按文件读取位置回调(大文件进度)。"""
    by_id: dict[int, dict] = {}
    ids_by_ch: dict[int, dict[int, int]] = defaultdict(dict)
    channels: dict[int, int] = {}
    total = fd = error = remote = 0
    first_ts = last_ts = None

    path = Path(path)
    total_size = path.stat().st_size or 1
    reader = open_message_reader(path)
    fobj = _file_obj(reader)

    for msg in reader:
        ts = msg.timestamp
        if first_ts is None:
            first_ts = ts
        last_ts = ts
        total += 1

        ch = getattr(msg, "channel", 0) or 0
        channels[ch] = channels.get(ch, 0) + 1

        if progress_cb and fobj is not None:
            try:
                progress_cb(min(0.99, fobj.tell() / total_size))
            except Exception:
                pass

        if getattr(msg, "is_error_frame", False):
            error += 1
            continue
        if getattr(msg, "is_fd", False):
            fd += 1
        if getattr(msg, "is_remote_frame", False):
            remote += 1

        aid = msg.arbitration_id
        e = by_id.setdefault(aid, {"frame_id": aid, "count": 0,
                                   "first": ts, "last": ts, "dlc": 0})
        e["count"] += 1
        e["dlc"] = max(e["dlc"], getattr(msg, "dlc", 0))
        if ts < e["first"]:
            e["first"] = ts
        if ts > e["last"]:
            e["last"] = ts

        d = ids_by_ch[ch]
        d[aid] = max(d.get(aid, 0), getattr(msg, "dlc", 0))

    ids = sorted(by_id.values(), key=lambda x: -x["count"])
    for e in ids:
        span = e["last"] - e["first"]
        e["duration_s"] = round(span, 4)
        e["rate_hz"] = round(e["count"] / span, 2) if span > 0 else None

    return {
        "file": Path(path).name,
        "total_frames": total,
        "fd_frames": fd,
        "error_frames": error,
        "remote_frames": remote,
        "first_timestamp": first_ts,
        "last_timestamp": last_ts,
        "duration_s": round(last_ts - first_ts, 4) if first_ts is not None else 0.0,
        "unique_ids": len(ids),
        "channels": [{"channel": ch, "frames": n} for ch, n in sorted(channels.items())],
        "by_id": ids,
        "ids_by_channel": [
            {"channel": ch,
             "ids": [{"frame_id": fid, "dlc": dlc}
                     for fid, dlc in sorted(d.items())]}
            for ch, d in sorted(ids_by_ch.items())],
    }
