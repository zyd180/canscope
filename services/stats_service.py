"""统计分析服务:信号数值统计 / 周期抖动 / Trace 分页 / 总线负载 / 区间框选统计。
算法自 Web 版 api/blf.py 抽离,去 HTTP 化(ValueError 报错),供 GUI 直接调用。"""
from __future__ import annotations

from collections import defaultdict
from typing import Optional

import numpy as np

from core.blf_cache import get_frames as cache_get_frames
from core.blf_cache import get_frames_index as cache_index
from core.decoder import to_plain


def _require_msg(db, frame_id: int):
    try:
        return db.get_message_by_frame_id(frame_id)
    except KeyError:
        raise ValueError(f"DBC 中无报文 {hex(frame_id)}") from None


def frames_page(blf_path, db, frame_id: int, channel: Optional[int] = None,
                start: Optional[float] = None, end: Optional[float] = None,
                limit: int = 200, offset: int = 0,
                decode: bool = False,
                sig_filter: Optional[str] = None,
                sig_value: Optional[str] = None) -> dict:
    """Trace 帧列表:分页返回该报文的原始帧;支持按信号值过滤(sig_filter+sig_value)。"""
    msg = _require_msg(db, frame_id)

    if sig_filter is not None and not any(s.name == sig_filter for s in msg.signals):
        raise ValueError(f"报文 {hex(frame_id)} 无信号 {sig_filter}")

    def _sig_match(decoded) -> bool:
        """按信号值过滤:数值按容差匹配,值表按状态名或原始值匹配。"""
        if sig_filter is None or sig_value is None:
            return True
        v = decoded.get(sig_filter)
        if v is None:
            return False
        name = getattr(v, "name", None)
        val = getattr(v, "value", v)   # NamedSignalValue → 值表状态
        if name is not None:
            return str(name) == sig_value or str(val) == sig_value
        if isinstance(val, (int, float)):
            try:
                return abs(val - float(sig_value)) < 1e-6
            except ValueError:
                return False
        return str(val) == sig_value

    frames = []
    skipped = 0
    for ts, ch, data, is_fd, dlc in cache_get_frames(blf_path, frame_id,
                                                     channel=channel, start=start, end=end):
        if sig_filter is not None:
            try:
                dec = to_plain_dict(db.decode_message(frame_id, data))
            except Exception:
                continue
            if not _sig_match(dec):
                continue
        if skipped < offset:
            skipped += 1
            continue
        if len(frames) >= limit:
            break
        row = {
            "timestamp": round(ts, 6),
            "id": frame_id,
            "id_hex": hex(frame_id),
            "name": msg.name,
            "dlc": dlc,
            "data": data.hex(" ").upper() if data else "",
            "is_fd": is_fd,
            "channel": ch,
        }
        if decode:
            try:
                row["decoded"] = to_plain_dict(db.decode_message(frame_id, data))
            except Exception:
                row["decoded"] = None
        frames.append(row)
    return {"name": msg.name, "channel": channel, "offset": offset,
            "limit": limit, "returned": len(frames), "frames": frames,
            "filter": {"signal": sig_filter, "value": sig_value}}


def to_plain_dict(decoded: dict) -> dict:
    """解码结果整体转纯值(NamedSignalValue → {name, value} 形式保留状态名)。"""
    out = {}
    for k, v in decoded.items():
        if hasattr(v, "value"):
            out[k] = {"name": str(v.name), "value": v.value}
        else:
            out[k] = v
    return out


def signal_stats(blf_path, db, frame_id: int, signal_name: str,
                 channel: Optional[int] = None,
                 start: Optional[float] = None, end: Optional[float] = None) -> dict:
    """信号数值统计:count / min / max / mean / std / 最后值 / 值表分布(走帧缓存)。"""
    msg = _require_msg(db, frame_id)
    try:
        sig = msg.get_signal_by_name(signal_name)
    except KeyError:
        raise ValueError(f"报文 {hex(frame_id)} 无信号 {signal_name}") from None

    values = []
    for _ts, _ch, data, _is_fd, _dlc in cache_get_frames(blf_path, frame_id,
                                                         channel=channel, start=start, end=end):
        try:
            v = db.decode_message(frame_id, data).get(signal_name)
        except Exception:
            continue
        if v is not None:
            values.append(to_plain(v))

    out = {"frame_id": frame_id, "frame_id_hex": hex(frame_id), "signal": signal_name,
           "channel": channel, "count": len(values)}
    numeric = [v for v in values if isinstance(v, (int, float))]
    if numeric:
        n = len(numeric)
        mean = sum(numeric) / n
        var = sum((x - mean) ** 2 for x in numeric) / n
        out.update({
            "min": round(min(numeric), 6),
            "max": round(max(numeric), 6),
            "mean": round(mean, 6),
            "std": round(var ** 0.5, 6),
            "last": numeric[-1],
        })
    # 值表信号:各状态分布
    if getattr(sig, "choices", None):
        dist = {}
        for v in values:
            key = str(getattr(v, "name", v))
            dist[key] = dist.get(key, 0) + 1
        out["choices_dist"] = dist
    # 超范围检测:对比 DBC 定义的 min/max
    if numeric and (sig.minimum is not None or sig.maximum is not None):
        oor = sum(1 for v in numeric
                  if (sig.minimum is not None and v < sig.minimum) or
                     (sig.maximum is not None and v > sig.maximum))
        out["out_of_range"] = oor
        out["range_min"] = sig.minimum
        out["range_max"] = sig.maximum
    return out


def cycle_stats(blf_path, db, frame_id: int, channel: Optional[int] = None,
                start: Optional[float] = None, end: Optional[float] = None) -> dict:
    """报文周期/抖动/丢帧:相邻帧时间间隔统计,期望周期取自 DBC cycle_time。"""
    msg = _require_msg(db, frame_id)

    rows = cache_get_frames(blf_path, frame_id, channel=channel, start=start, end=end)
    times = sorted(ts for ts, *_ in rows)
    expected_ms = msg.cycle_time
    expected_s = expected_ms / 1000.0 if expected_ms else None

    out = {"frame_id": frame_id, "frame_id_hex": hex(frame_id), "name": msg.name,
           "channel": channel, "count": len(times),
           "expected_ms": expected_ms, "expected_s": expected_s}
    if len(times) >= 2:
        ivs = [times[i + 1] - times[i] for i in range(len(times) - 1)]
        max_i = ivs.index(max(ivs))
        min_i = ivs.index(min(ivs))
        out.update({
            "avg_ms": round(sum(ivs) / len(ivs) * 1000, 3),
            "min_ms": round(min(ivs) * 1000, 3),
            "max_ms": round(max(ivs) * 1000, 3),
            "jitter_ms": round((max(ivs) - min(ivs)) * 1000, 3),   # 峰峰抖动
            # 抖动峰值出现的时间点(间隔起始帧时间,绝对时间戳,展示层转相对)
            "jitter_max_at": times[max_i],
            "jitter_min_at": times[min_i],
        })
        if expected_s:
            # 丢帧:间隔超过期望 1.5 倍视为缺帧,按比例推算丢帧数
            lost = 0
            for iv in ivs:
                if iv > expected_s * 1.5:
                    lost += max(1, round(iv / expected_s) - 1)
            out["lost_frames"] = lost
            out["lost_pct"] = round(lost / len(times) * 100, 2)
    return out


def local_range_stats(items, t_start: float, t_end: float) -> dict:
    """区间框选统计(R1):对已解码的 SignalItem 列表在 [t_start, t_end](相对秒)
    内做数值聚合。同步执行、走内存数组(≤20 万点/信号),不触碰帧缓存。

    返回 {"dt_s": 区间宽度, "rows": [{key,name,color,unit,count,min,max,mean,std,choices_dist}]}
    """
    rows = []
    for it in items:
        times = np.asarray(it.times, dtype=float)
        if times.size == 0:
            continue
        mask = (times >= t_start) & (times <= t_end)
        n = int(mask.sum())
        row = {
            "key": it.key, "name": it.name, "color": it.color,
            "unit": it.unit or "", "count": n,
            "min": None, "max": None, "mean": None, "std": None,
            "choices_dist": None,
        }
        vals_raw = it.values
        # 数值统计
        try:
            vals = np.asarray(vals_raw, dtype=float)
        except (TypeError, ValueError):
            vals = None
        if vals is not None and n > 0:
            seg = vals[mask]
            finite = seg[np.isfinite(seg)]
            if finite.size:
                row.update({
                    "min": round(float(finite.min()), 6),
                    "max": round(float(finite.max()), 6),
                    "mean": round(float(finite.mean()), 6),
                    "std": round(float(finite.std()), 6),
                })
        # 值表状态分布(优先呈现,数值仅作补充)
        choices = getattr(it, "choices", None)
        if choices and n > 0 and vals is not None:
            seg = vals[mask]
            dist: dict = {}
            for v in seg:
                v_int = int(v) if np.isfinite(v) else None
                name = choices.get(v_int)
                dist[name if name is not None else str(v)] = \
                    dist.get(name if name is not None else str(v), 0) + 1
            row["choices_dist"] = dist
        rows.append(row)
    return {"dt_s": max(0.0, t_end - t_start), "rows": rows}


def _frame_bits(dlc: int, is_fd: bool) -> tuple:
    """帧位宽近似(不含位填充):经典 CAN 47+8*DLC(含 IFS);
    CAN FD 仲裁段 20(SOF+ID+控制+DLC),数据段 8*DLC+28(CRC+DEL+ACK+EOF+IFS 近似)。"""
    if is_fd:
        return 20, 8 * dlc + 28
    return 47 + 8 * dlc, 0


def bus_load(blf_path, baudrate_arb: int, baudrate_data: int,
             bus_type: str = "canfd", channel: Optional[int] = None) -> dict:
    """总线负载率:按配置的波特率估算每通道占用率(近似,不含位填充)。"""
    chan_time: dict = defaultdict(float)
    chan_frames: dict = defaultdict(int)
    first_ts: dict = {}
    last_ts: dict = {}

    idx = cache_index(blf_path)
    for fid, rows in idx.items():
        for ts, ch, _data, is_fd, dlc in rows:
            if channel is not None and ch != channel:
                continue
            ab, db_ = _frame_bits(dlc, is_fd)
            chan_time[ch] += ab / baudrate_arb + db_ / baudrate_data
            chan_frames[ch] += 1
            first_ts.setdefault(ch, ts)
            last_ts[ch] = ts

    out = {}
    for ch in sorted(chan_time):
        dur = last_ts[ch] - first_ts[ch]
        out[str(ch)] = {
            "frames": chan_frames[ch],
            "bus_time_s": round(chan_time[ch], 4),
            "duration_s": round(dur, 4),
            "bus_load_pct": round(chan_time[ch] / dur * 100, 2) if dur > 0 else 0.0,
        }
    return {"arbitration_baudrate": baudrate_arb, "data_baudrate": baudrate_data,
            "bus_type": bus_type, "channels": out}
