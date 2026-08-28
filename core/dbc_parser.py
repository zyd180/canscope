"""DBC 解析:基于 cantools。"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Union

import cantools


def _detect_encoding(raw: bytes) -> str:
    """检测 DBC 文本编码:UTF-8 → GBK → GB18030 → latin-1。

    不能靠 cantools 抛错回退(GBK 字节可能被宽松解码成乱码而不报错),
    须用 strict 解码主动检测:GBK 双字节中文字符序列必然无法通过 UTF-8 严格校验。
    """
    for enc in ("utf-8", "gbk", "gb18030", "latin-1"):
        try:
            raw.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    return "utf-8"


@lru_cache(maxsize=32)
def _load_cached(path_str: str, encoding: str):
    return cantools.database.load_file(path_str, encoding=encoding)


def load_database(path: Union[str, Path]):
    """加载 DBC 数据库,自动检测编码(支持 UTF-8 / GBK / GB18030),带缓存。"""
    p = Path(path)
    try:
        enc = _detect_encoding(p.read_bytes())
        return _load_cached(str(p), enc)
    except Exception as e:
        raise ValueError(f"DBC 解析失败: {e}") from e


def messages_summary(db) -> list[dict]:
    """所有报文及其信号摘要(按 ID 排序)。"""
    out = []
    for msg in sorted(db.messages, key=lambda m: m.frame_id):
        out.append({
            "frame_id": msg.frame_id,
            "frame_id_hex": hex(msg.frame_id),
            "name": msg.name,
            "length": msg.length,
            "cycle_time": msg.cycle_time,
            "is_extended": msg.is_extended_frame,
            "senders": list(getattr(msg, "senders", []) or []),
            "signals": [s.name for s in msg.signals],
            "signal_count": len(msg.signals),
        })
    return out


def message_detail(db, frame_id: int) -> "dict | None":
    """单个报文的信号详情(起始位/长度/缩放/偏移/单位/值表)。"""
    for msg in db.messages:
        if msg.frame_id == frame_id:
            return {
                "frame_id": msg.frame_id,
                "frame_id_hex": hex(msg.frame_id),
                "name": msg.name,
                "length": msg.length,
                "cycle_time": msg.cycle_time,
                "is_extended": msg.is_extended_frame,
                "senders": list(getattr(msg, "senders", []) or []),
                "signals": [
                    {
                        "name": s.name,
                        "start_bit": s.start,
                        "length_bits": s.length,
                        "byte_order": s.byte_order,
                        "scale": s.scale,
                        "offset": s.offset,
                        "minimum": s.minimum,
                        "maximum": s.maximum,
                        "unit": s.unit,
                        "comment": getattr(s, "comment", None),
                        "choices": s.choices,
                    }
                    for s in msg.signals
                ],
            }
    return None


def match_channels_to_dbcs(stats: dict, dbc_paths: list) -> dict:
    """按通道观测到的 (报文 ID, DLC) 为候选 DBC 评分。

    返回每个通道的最佳候选、覆盖率和并列候选；解析失败的 DBC 会记录在
    ``errors`` 中而不是阻断其它候选的匹配。
    """
    candidates = []
    errors = []
    for path in dbc_paths:
        path = str(path)
        try:
            db = load_database(path)
            frames = {(m.frame_id, m.length) for m in db.messages}
            candidates.append((path, frames))
        except (OSError, ValueError) as exc:
            errors.append({"path": path, "error": str(exc)})

    result = {"channels": {}, "errors": errors}
    for entry in stats.get("ids_by_channel", []):
        channel = entry["channel"]
        observed = {(item["frame_id"], item["dlc"])
                    for item in entry.get("ids", [])}
        total = len(observed)
        scores = []
        for path, frames in candidates:
            matched = len(observed & frames)
            scores.append({
                "path": path,
                "matched": matched,
                "total": total,
                "coverage": matched / total if total else 0.0,
            })
        scores.sort(key=lambda item: (item["matched"], item["coverage"]),
                    reverse=True)
        best_score = (scores[0]["matched"], scores[0]["coverage"]) if scores else (0, 0.0)
        best = [item for item in scores
                if (item["matched"], item["coverage"]) == best_score
                and item["matched"] > 0]
        result["channels"][channel] = {
            "selected": best[0]["path"] if len(best) == 1 else None,
            "matched": best[0]["matched"] if best else 0,
            "total": total,
            "coverage": best[0]["coverage"] if best else 0.0,
            "ambiguous": [item["path"] for item in best] if len(best) > 1 else [],
            "scores": scores,
        }
    return result
