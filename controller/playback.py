"""回放控制器:QTimer 泵驱动 PlaybackEngine(替代 Web 版 WebSocket 网关)。

时序语义与 Web 版 ws.py 一致:
- 墙钟推算播放头:play_t += Δwall × rate
- 每 TICK(20ms)调 engine.advance_to(play_t),批次追加进累积缓冲
- 播完 → ended;seek 清空累积(曲线从新起点向右生长)
"""
from __future__ import annotations

import time
from typing import Optional

from PySide6.QtCore import QObject, QTimer, Signal

from core import dbc_parser
from core.frame_source import BlfReplaySource
from core.playback import PlaybackEngine, SignalSub

TICK_MS = 20        # 推送节拍(与 Web 版一致)
BATCH_MAX = 8192


class PlaybackController(QObject):
    stateChanged = Signal(str)     # 'idle' | 'building' | 'playing' | 'paused' | 'ended'
    progress = Signal(float)       # 当前播放头(相对秒,取自批次 t1)
    renderData = Signal(object)    # 累积数据 {key: {times, values}} → 示波器增量绘制
    diagnostics = Signal(str)
    ended = Signal()

    def __init__(self, state, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.state = state
        self._timer = QTimer(self)
        self._timer.setInterval(TICK_MS)
        self._timer.timeout.connect(self._tick)

        self._engine: Optional[PlaybackEngine] = None
        self._building = False
        self._mode = "idle"
        self._rate = 1.0
        self._play_t = 0.0
        self._wall: Optional[float] = None   # monotonic 时间基准
        self._data: dict = {}

        # 诊断计数
        self._n_frames = 0
        self._n_pts = 0
        self._diag_at = 0.0
        self._t_play_ms = 0.0
        self._t_draw_ms = 0.0

    # ---------------- 状态 ----------------

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def rate(self) -> float:
        return self._rate

    def current_t(self) -> float:
        """当前播放头(播放中按墙钟推算)。"""
        if self._mode == "playing" and self._wall is not None:
            return self._play_t + (time.monotonic() - self._wall) * self._rate
        return self._play_t

    # ---------------- 控制 API ----------------

    def toggle_play(self) -> None:
        if self._mode == "playing":
            self.pause()
        else:
            self.play()

    def play(self, rate: Optional[float] = None) -> None:
        if rate is not None:
            self._rate = float(rate)
        if self._mode == "ended" and self._engine is not None:
            # 重播:回到起点
            self._engine.seek(0.0)
            self._play_t = 0.0
            self._data = {}
        if self._engine is None:
            if not self._building:
                self._build()
            return
        self._start_playing()

    def _start_playing(self) -> None:
        if self._engine is None:
            return
        self._mode = "playing"
        self._wall = time.monotonic()
        self._timer.start()
        self.stateChanged.emit(self._mode)

    def _build(self) -> None:
        """后台构建 BlfReplaySource + PlaybackEngine(索引已缓存,毫秒级)。"""
        s = self.state
        subs: list = []
        seen = set()
        for it in s.signals_list:
            k = (it.frame_id, it.channel, it.name)
            if k in seen:
                continue
            seen.add(k)
            subs.append(SignalSub(it.frame_id, it.channel, it.name, it.dbc_path))
        if not subs:
            return
        self._building = True
        self._mode = "building"
        self.stateChanged.emit(self._mode)
        blf = s.blf_path
        dbc_by_ch = dict(s.channel_dbc)

        def work():
            dbs = {ch: dbc_parser.load_database(p) for ch, p in dbc_by_ch.items()}
            src = BlfReplaySource(blf)
            return PlaybackEngine(src, dbs, subs)

        def done(eng):
            self._building = False
            self._engine = eng
            self._engine.seek(0.0)
            self._start_playing()

        def fail(msg):
            self._building = False
            self._mode = "idle"
            self.stateChanged.emit(self._mode)
            s.errorRaised.emit(f"回放初始化失败: {msg}")

        s.runner.run(work, done, fail)

    def pause(self) -> None:
        if self._mode != "playing":
            return
        self._play_t = self.current_t()
        self._wall = None
        self._mode = "paused"
        self._timer.stop()
        self.stateChanged.emit(self._mode)

    def stop(self) -> None:
        """停止:回起点、清累积(UI 恢复静态由主窗口处理)。"""
        self._mode = "idle"
        self._timer.stop()
        self._wall = None
        self._play_t = 0.0
        if self._engine is not None:
            self._engine.seek(0.0)
        self._data = {}
        self.stateChanged.emit(self._mode)

    def seek(self, t: float) -> None:
        dur = self.state.duration or 0.0
        t = min(max(float(t), 0.0), dur)
        self._play_t = t
        if self._mode == "playing":
            self._wall = time.monotonic()
        if self._engine is not None:
            self._engine.seek(t)
        self._data = {}   # 从新起点重新生长
        self.progress.emit(t)

    def set_rate(self, rate: float) -> None:
        if self._mode == "playing":
            self._play_t = self.current_t()
            self._wall = time.monotonic()
        self._rate = float(rate)

    def teardown(self) -> None:
        """信号集/文件变更:完全复位(与 Web 版"播放中变更自动暂停"一致)。"""
        was_active = self._mode in ("playing", "paused", "building")
        self._timer.stop()
        self._engine = None
        self._building = False
        self._mode = "idle"
        self._play_t = 0.0
        self._wall = None
        self._data = {}
        self.stateChanged.emit(self._mode)
        return was_active

    # ---------------- 泵 ----------------

    def _tick(self) -> None:
        if self._engine is None:
            return
        t0 = time.perf_counter()
        play_t = self.current_t()
        batch = self._engine.advance_to(play_t, BATCH_MAX)
        t1 = time.perf_counter()
        if batch is None:
            self._mode = "ended"
            self._timer.stop()
            self._wall = None
            self.stateChanged.emit(self._mode)
            self.ended.emit()
            return

        for key, d in batch["signals"].items():
            acc = self._data.setdefault(key, {"times": [], "values": []})
            acc["times"].extend(d["times"])
            acc["values"].extend(d["values"])
        self._n_frames += batch["frames"]
        self._n_pts += sum(len(v["times"]) for v in batch["signals"].values())
        self._t_play_ms = (t1 - t0) * 1000

        t2 = time.perf_counter()
        self.renderData.emit(self._data)
        self._t_draw_ms = (time.perf_counter() - t2) * 1000

        self.progress.emit(batch["t1"])

        now = time.monotonic()
        if now - self._diag_at > 0.8:
            self._diag_at = now
            self.diagnostics.emit(
                f"收:{self._n_frames:,}帧 · 点:{self._n_pts:,} · "
                f"t:{batch['t1']:.2f}s · play:{self._t_play_ms:.1f}ms · "
                f"draw:{self._t_draw_ms:.1f}ms")
