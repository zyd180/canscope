"""BLF 帧缓存:首次全扫后缓存 {frame_id: [(ts, channel, data), ...]} 索引,
避免 decode/frames/export 每次全文件重扫。LRU 容量限制 + 文件 mtime/size 校验。
R2:经由 log_reader 工厂取数,索引同样可来自 ASC/MF4 日志。"""
from __future__ import annotations

import threading
from collections import OrderedDict, defaultdict
from pathlib import Path
from typing import Optional

from core.log_reader import _file_obj, open_message_reader

# 缓存上限:最多缓存 MAX_FILES 个文件 / MAX_FRAMES 总帧数(约 1GB 内存预算内的安全值)
MAX_FILES = 4
MAX_FRAMES = 2_000_000

_cache: "OrderedDict[str, tuple]" = OrderedDict()
# path -> (index, (size, mtime_ns), frames)
_lock = threading.Lock()


def _build_index(path: Path, progress_cb=None) -> tuple:
    """全扫日志,构建 {frame_id: [(ts, channel, data, is_fd, dlc), ...]}。
    progress_cb(0~1):按文件读取位置回调(大文件首次解码进度)。"""
    idx: dict = defaultdict(list)
    n = 0
    total_size = path.stat().st_size or 1
    reader = open_message_reader(path)
    fobj = _file_obj(reader)
    for m in reader:
        idx[m.arbitration_id].append((
            m.timestamp,
            getattr(m, "channel", 0),
            m.data,
            bool(getattr(m, "is_fd", False)),
            m.dlc,
        ))
        n += 1
        if progress_cb and fobj is not None:
            try:
                progress_cb(min(0.99, fobj.tell() / total_size))
            except Exception:
                pass
    return dict(idx), n


def _insert(key: str, sig: tuple, idx: dict, n: int) -> None:
    """写入缓存并执行 LRU 淘汰(调用方需已构建好索引)。"""
    with _lock:
        _cache[key] = (idx, sig, n)
        _cache.move_to_end(key)
        while len(_cache) > MAX_FILES:
            _cache.popitem(last=False)
        total = sum(v[2] for v in _cache.values())
        while total > MAX_FRAMES and len(_cache) > 1:
            _, (_, _, popped) = _cache.popitem(last=False)
            total -= popped


def store_index(path: Path, idx: dict, n: int) -> None:
    """把后台加载器单遍扫描得到的索引直接入缓存(省去重复全扫)。"""
    st = path.stat()
    _insert(str(path), (st.st_size, st.st_mtime_ns), idx, n)


def get_frames_index(path: Path, progress_cb=None) -> dict:
    """返回 {frame_id: [(ts, channel, data), ...]} 索引(命中缓存或全扫构建)。
    progress_cb:首次全扫构建时的进度回调(大文件)。"""
    key = str(path)
    st = path.stat()
    sig = (st.st_size, st.st_mtime_ns)

    with _lock:
        hit = _cache.get(key)
        if hit and hit[1] == sig:
            _cache.move_to_end(key)   # LRU 刷新
            return hit[0]

    idx, n = _build_index(path, progress_cb=progress_cb)
    _insert(key, sig, idx, n)
    return idx


def get_frames(path: Path, frame_id: int,
               channel: Optional[int] = None,
               start: Optional[float] = None,
               end: Optional[float] = None,
               progress_cb=None) -> list:
    """从缓存取某报文的帧列表,按通道/时间过滤。"""
    idx = get_frames_index(path, progress_cb=progress_cb)
    rows = idx.get(frame_id, [])
    if channel is None and start is None and end is None:
        return rows
    out = []
    for row in rows:
        ts, ch, data, is_fd, dlc = row
        if channel is not None and ch != channel:
            continue
        if start is not None and ts < start:
            continue
        if end is not None and ts > end:
            continue
        out.append(row)
    return out


def invalidate(path: Path):
    with _lock:
        _cache.pop(str(path), None)
