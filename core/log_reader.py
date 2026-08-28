"""日志读取器工厂(R2):按内容识别 BLF/ASC/MF4,统一产出 can.Message 流。

blf_cache / blf_parser / blf_loader 全部经由 open_message_reader 取数,
后续新增格式只需扩展 file_types.detect_kind + 此处分支。
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

import can

from core.file_types import detect_kind


def _file_obj(reader) -> object:
    """python-can Reader 的底层文件对象属性名不稳定,运行时探测。"""
    return (getattr(reader, "f", None) or getattr(reader, "_file", None)
            or getattr(reader, "file", None))


def open_message_reader(path: Path):
    """返回可迭代 can.Message 的读取器(BLFReader/ASCReader/MDF 适配器)。"""
    kind = detect_kind(Path(path))
    if kind == ".asc":
        return can.ASCReader(str(path))
    if kind == ".mf4":
        from core.mdf_source import iter_mdf_messages
        return iter_mdf_messages(Path(path))
    return can.BLFReader(str(path))


def reader_progress_ctx(reader, total_size: int):
    """返回 (fobj, progress_cb 工厂所需的 tell 探测对象)。"""
    return _file_obj(reader), max(1, total_size)


__all__ = ["open_message_reader", "_file_obj", "reader_progress_ctx"]
