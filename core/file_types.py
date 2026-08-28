"""文件类型按内容识别(R2 扩展:ASC / MF4)。

扩展名不可靠:Windows 上 .log/.txt 内容可能是 BLF/ASC/DBC。
BLF:文件头 "LOGG";MF4:文件头 "MDF";DBC:文本 VERSION/BO_/SG_ 特征;
ASC:文本 base hex / Triggerblock 特征。识别不出按扩展名兜底。
"""
from __future__ import annotations

from pathlib import Path

BLF_MAGIC = b"LOGG"
MDF_MAGIC = b"MDF"


def _asc_features(head: bytes) -> bool:
    low = head.lower()
    return (b"base hex" in low
            or b"begin triggerblock" in low
            or b"end triggerblock" in low)


def detect_kind(path: Path) -> str:
    """按内容识别文件类型,返回规范后缀('.blf'/'.asc'/'.mf4'/'.dbc')或原后缀兜底。"""
    try:
        with Path(path).open("rb") as f:
            head = f.read(256)
    except OSError:
        return Path(path).suffix.lower()
    if head[:4] == BLF_MAGIC:
        return ".blf"
    if head[:3] == MDF_MAGIC:
        return ".mf4"
    text = head.decode("utf-8", errors="ignore").lstrip("\ufeff \t")
    if text.startswith("VERSION") or b"BO_" in head or b"SG_ " in head:
        return ".dbc"
    if _asc_features(head):
        return ".asc"
    return Path(path).suffix.lower()


# 允许打开的扩展名(实际类型按内容魔数识别)
ALLOWED_EXTENSIONS = {".blf", ".asc", ".mf4", ".dbc", ".log", ".txt"}

# 可作为"分析日志"打开的类型(每次仅一个)
LOG_KINDS = {".blf", ".asc", ".mf4"}
