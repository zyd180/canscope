"""回放引擎:播放状态机 + 帧源推进 + 订阅信号解码。

引擎本身不调度时间 —— 由 GUI 定时器按真实时间 × 速率驱动:
每 tick 调 advance_to(play_time),引擎把源推进到该播放时间,
解码订阅帧并返回本窗口的帧批次(渲染层增量追加)。
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Optional

from core.frame_source import FrameSource
from core.decoder import to_plain


@dataclass
class SignalSub:
    """订阅:一个已选信号(报文+通道+信号名+所属DBC)。"""
    frame_id: int
    channel: int
    signal: str
    dbc: str = ""   # 该信号所属通道的 DBC 文件名


class PlaybackEngine:
    """单会话回放引擎:持有一个帧源 + 按通道 DBC 映射 + 订阅列表。"""

    def __init__(self, source: FrameSource, dbs: dict, subs: list):
        self.source = source
        self.dbs = dbs                       # {channel: cantools 数据库对象}
        self.subs = subs
        # (frame_id, channel) -> [(signal, dbc), ...] 快速匹配
        self._subs_by_frame: dict = defaultdict(list)
        for s in subs:
            self._subs_by_frame[(s.frame_id, s.channel)].append((s.signal, s.dbc))
        self._seq = 0
        self._ended = False

    # ---- 控制 ----

    def seek(self, t: float) -> None:
        """定位到相对时间 t,重置批次序号与结束标记。"""
        self.source.seek(t)
        self._seq = 0
        self._ended = False

    @property
    def ended(self) -> bool:
        return self._ended

    # ---- 数据推进 ----

    def advance_to(self, play_time: float, max_frames: int = 8192) -> Optional[dict]:
        """把源推进到 play_time(相对时间),返回本窗口帧批次。

        返回 None 表示数据已播完(结束)。批次结构:
        {type, seq, t1, frames, signals: {f"{frame_id}|{channel}|{signal}": {times, values}}}
        """
        frames = self.source.next_batch(max_frames, end_t=play_time)
        if not frames:
            self._ended = True
            return None

        sig_data: dict = defaultdict(lambda: {"times": [], "values": []})
        for f in frames:
            sub_list = self._subs_by_frame.get((f.frame_id, f.channel))
            if not sub_list:
                continue
            db = self.dbs.get(f.channel)
            if db is None:
                continue
            try:
                decoded = db.decode_message(f.frame_id, f.data)
            except Exception:
                continue
            for name, _dbc in sub_list:
                if name in decoded:
                    val = to_plain(decoded[name])
                    key = f"{f.frame_id}|{f.channel}|{name}"
                    sig_data[key]["times"].append(round(f.ts, 6))
                    sig_data[key]["values"].append(val)

        self._seq += 1
        return {
            "type": "batch",
            "seq": self._seq,
            "t1": round(frames[-1].ts, 6),
            "frames": len(frames),
            "signals": {k: v for k, v in sig_data.items() if v["times"]},
        }
