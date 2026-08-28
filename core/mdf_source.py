"""MF4/MDF4 CAN 总线日志适配(R2,可选依赖 asammdf)。

统一产出 can.Message 迭代流,经 core.log_reader 工厂接入与 BLF 完全同一条
索引/统计/解码链路。asammdf 缺失时抛带安装指引的 RuntimeError。

兼容性说明(基于 asammdf 8.x 实测):
- 仅解析 CAN_DataFrame 总线日志组(经典 CAN / CAN FD 帧记录);
- DataBytes 支持两种存储:uint8 二维数组(Vector CANoe 风格,字节无损,首选)
  与 'S' 定长字符串行(部分工具导出;注意 NumPy 对 NUL 的截断语义,尽力而为);
- IDE 通道缺失时,以 ID>0x7FF 判定扩展帧;
- BusChannel/IDE/DLC/BRS/EDL 均为可选通道,缺失时取安全默认值。
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

import can


def iter_mdf_messages(path: Path, progress_cb: Optional[Callable] = None):
    """迭代 MDF4 文件中的 CAN 帧,产出 can.Message(时间戳取自 ID 通道主时基)。"""
    try:
        from asammdf import MDF
    except ImportError as e:
        raise RuntimeError(
            "MF4 支持需要可选依赖 asammdf(当前未安装)。\n"
            "请执行: pip install asammdf,然后重新打开文件。") from e

    mdf = MDF(str(path))
    try:
        found = False
        for gi, _gp in enumerate(mdf.groups):
            names = {c.name for c in mdf.groups[gi].channels}
            root = "CAN_DataFrame"
            if not any(n == root or n.startswith(root + ".") for n in names):
                continue

            def cand(base: str):
                for c in (f"{root}.{base}", base):
                    if c in names:
                        return c
                return None

            id_ch = cand("ID")
            if id_ch is None:
                continue
            s_id = mdf.get(id_ch, group=gi, raw=True)
            ts, ids = s_id.timestamps, s_id.samples

            ide_ch = cand("IDE")
            ide = mdf.get(ide_ch, group=gi, raw=True).samples if ide_ch else None
            bus_ch = cand("BusChannel") or cand("Channel")
            bus = mdf.get(bus_ch, group=gi, raw=True).samples if bus_ch else None
            dlc_ch = cand("DLC")
            dlc_v = mdf.get(dlc_ch, group=gi, raw=True).samples if dlc_ch else None
            fd_ch = cand("BRS") or cand("EDL")
            fd_v = mdf.get(fd_ch, group=gi, raw=True).samples if fd_ch else None

            rows = None
            data_ch = cand("DataBytes")
            if data_ch:
                arr = mdf.get(data_ch, group=gi, raw=True).samples
                if getattr(arr, "ndim", 1) == 2:
                    rows = (bytes(r) for r in arr)
                elif arr.dtype.kind == "S" or arr.dtype == object:
                    rows = (bytes(s) for s in arr)
                else:
                    rows = (bytes([int(v)]) for v in arr)

            found = True
            for i in range(len(ids)):
                fid = int(ids[i])
                data = next(rows) if rows is not None else b""
                if ide is not None:
                    is_ext = bool(ide[i])
                else:
                    is_ext = fid > 0x7FF
                if fd_v is not None:
                    is_fd = bool(fd_v[i])
                elif dlc_v is not None and int(dlc_v[i]) > 8:
                    is_fd = True
                else:
                    is_fd = len(data) > 8
                ch_i = int(bus[i]) if bus is not None else 0
                yield can.Message(
                    timestamp=float(ts[i]), arbitration_id=fid, data=data,
                    is_extended_id=is_ext, is_fd=is_fd, channel=ch_i)
            if progress_cb:
                try:
                    progress_cb(0.99)
                except Exception:
                    pass
        if not found:
            raise RuntimeError("MF4 中未找到 CAN_DataFrame 总线日志组")
    finally:
        try:
            mdf.close()
        except Exception:
            pass
