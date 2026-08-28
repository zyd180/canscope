"""数据导出:CSV(BOM)/ BLF 片段 / Trace 全量 / DBC 骨架(R2)。"""
from __future__ import annotations

import csv
import heapq
from pathlib import Path
from typing import Optional

import can

from core.blf_cache import get_frames as cache_get_frames
from core.blf_cache import get_frames_index as cache_index
from services.stats_service import to_plain_dict


def export_csv(blf_path, db, frame_id: int, signals: list,
               out_path: Path, channel: Optional[int] = None,
               start: Optional[float] = None, end: Optional[float] = None) -> int:
    """导出 CSV:时间 + 指定报文的一个/全部信号(同报文信号共享时间戳)。返回行数。"""
    try:
        msg = db.get_message_by_frame_id(frame_id)
    except KeyError:
        raise ValueError(f"DBC 中无报文 {hex(frame_id)}") from None

    cols = signals or [s.name for s in msg.signals]
    count = 0
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:   # utf-8-sig 写 BOM
        writer = csv.writer(f)
        writer.writerow(["timestamp"] + cols)
        for ts, _ch, data, _is_fd, _dlc in cache_get_frames(blf_path, frame_id,
                                                            channel=channel, start=start, end=end):
            try:
                dec = to_plain_dict(db.decode_message(frame_id, data))
            except Exception:
                continue
            row = [f"{ts:.6f}"]
            for s in cols:
                v = dec.get(s)
                if isinstance(v, dict) and "name" in v:
                    v = v["name"]   # 值表信号导出状态名
                row.append(v if v is not None else "")
            writer.writerow(row)
            count += 1
    return count


# ---------------- R2:BLF 片段导出 ----------------

def export_blf_segment(blf_path, out_path: Path,
                       start: Optional[float] = None,
                       end: Optional[float] = None) -> int:
    """按时间区间裁剪出独立 BLF(供 CANoe 等工具复现问题片段)。

    走帧缓存索引;各报文行本身按时间有序,用堆合并恢复全局时序,内存 O(报文数)。
    时间轴语义:BLFWriter 以首个消息时刻为新基准,片段内部相对时序与原日志一致
    (绝对墙钟起点会归零,属预期行为)。返回写出的帧数。
    """
    idx = cache_index(Path(blf_path))

    def gen(fid: int):
        for ts, ch, data, is_fd, dlc in idx.get(fid, []):
            if start is not None and ts < start:
                continue
            if end is not None and ts > end:
                continue
            yield ts, fid, ch, data, is_fd, dlc

    gens = [gen(fid) for fid, rows in idx.items() if rows]
    n = 0
    with can.BLFWriter(str(out_path)) as writer:
        for ts, fid, ch, data, is_fd, _dlc in heapq.merge(*gens, key=lambda r: r[0]):
            try:
                m = can.Message(timestamp=float(ts), arbitration_id=fid,
                                data=data, channel=ch,
                                is_extended_id=fid > 0x7FF, is_fd=is_fd)
            except (ValueError, TypeError):
                continue   # 个别构造失败帧(如特殊帧)跳过不中断
            writer.on_message_received(m)
            n += 1
    return n


# ---------------- R2:Trace 全量 CSV ----------------

_TRACE_HEAD = ["时间(s)", "ID", "报文", "DLC", "CH", "数据(hex)"]


def _frame_sig_match(db, frame_id: int, data: bytes,
                     sig_filter: Optional[str], sig_value: Optional[str]) -> bool:
    """按信号值过滤:数值容差匹配 / 值表状态名或原始值匹配(Trace 同款语义)。"""
    if sig_filter is None or sig_value is None:
        return True
    try:
        dec = to_plain_dict(db.decode_message(frame_id, data))
    except Exception:
        return False
    v = dec.get(sig_filter)
    if v is None:
        return False
    if isinstance(v, dict) and "name" in v:
        return str(v["name"]) == sig_value or str(v["value"]) == sig_value
    if isinstance(v, (int, float)):
        try:
            return abs(v - float(sig_value)) < 1e-6
        except ValueError:
            return False
    return str(v) == sig_value


def export_trace_csv(blf_path, db, frame_id: int, out_path: Path,
                     channel: Optional[int] = None,
                     start: Optional[float] = None, end: Optional[float] = None,
                     sig_filter: Optional[str] = None,
                     sig_value: Optional[str] = None) -> int:
    """导出 Trace 全部帧(应用与页面相同的过滤条件),列与 Trace 表一致。返回行数。"""
    try:
        msg = db.get_message_by_frame_id(frame_id)
    except KeyError:
        raise ValueError(f"DBC 中无报文 {hex(frame_id)}") from None
    if sig_filter is not None and not any(s.name == sig_filter for s in msg.signals):
        raise ValueError(f"报文 {hex(frame_id)} 无信号 {sig_filter}")

    count = 0
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(_TRACE_HEAD)
        for ts, ch, data, is_fd, dlc in cache_get_frames(
                blf_path, frame_id, channel=channel, start=start, end=end):
            if not _frame_sig_match(db, frame_id, data, sig_filter, sig_value):
                continue
            writer.writerow([
                f"{ts:.6f}", hex(frame_id), msg.name,
                str(dlc) + ("  FD" if is_fd else ""), ch,
                data.hex(" ").upper() if data else "",
            ])
            count += 1
    return count


# ---------------- R2:DBC 骨架生成 ----------------

_DBC_SKELETON = '''VERSION ""

NS_ :
    NS_DESC_
    CM_
    BA_DEF_
    BA_
    VAL_
    CAT_DEF_
    CAT_
    FILTER
    BA_DEF_DEF_
    EV_DATA_
    ENVVAR_DATA_
    SGTYPE_
    SGTYPE_VAL_
    BA_DEF_SGTYPE_
    BA_SGTYPE_
    SIG_TYPE_REF_
    VAL_TABLE_
    SIG_GROUP_
    SIG_VALTYPE_
    SIGTYPE_VALTYPE_
    BO_TX_BU_
    BA_DEF_REL_
    BA_REL_
    BA_DEF_DEF_REL_
    BU_SG_REL_
    BU_EV_REL_
    BU_BO_REL_
    SG_MUL_VAL_

BS_:

BU_: Vector__XXX

'''


def export_dbc_skeleton(ids_dlc: list, out_path: Path) -> int:
    """从观测到的 (frame_id, dlc) 列表生成 DBC 骨架(未知报文分析起步器)。

    每个报文形如 `BO_ {id} Unknown_{id:X}: {dlc} Vector__XXX`,无信号定义,
    cantools 可直接加载;编辑补全信号后即可在「配置」中映射使用。
    返回生成的报文数。
    """
    lines = [_DBC_SKELETON]
    for fid, dlc in sorted(ids_dlc):
        fid = int(fid)
        # DBC 扩展帧采用 bit31 标志位约定(原始 Vector 形式,
        # cantools 与主流工具均按 frame_id_dbc & 0x80000000 识别)
        fid_dbc = fid | 0x80000000 if fid > 0x7FF else fid
        lines.append(f"BO_ {fid_dbc} Unknown_{fid:X}: {int(dlc)} Vector__XXX\n")
    out_path = Path(out_path)
    out_path.write_text("".join(lines), encoding="utf-8")
    return len(ids_dlc)


def default_csv_name(blf_name: str, frame_id: int, channel: Optional[int],
                     signal_count: int) -> str:
    stem = Path(blf_name).stem
    ch_tag = f"_ch{channel}" if channel is not None else ""
    return f"{stem}{ch_tag}_{hex(frame_id)}_{signal_count}sig.csv"
