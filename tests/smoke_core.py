"""core/services 层无 GUI 冒烟测试(不依赖 Qt 主循环)。

运行: python tests/smoke_core.py
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import blf_cache, dbc_parser  # noqa: E402
from core.decoder import decode_signal, to_plain  # noqa: E402
from core.frame_source import BlfReplaySource  # noqa: E402
from core.playback import PlaybackEngine, SignalSub  # noqa: E402
from services import stats_service  # noqa: E402

DATA = ROOT / "data"
BLF = DATA / "test.blf"
DBC = DATA / "test.dbc"

fails = []


def check(name, cond, extra=""):
    tag = "[PASS]" if cond else "[FAIL]"
    print(f"{tag} {name} {extra}")
    if not cond:
        fails.append(name)


def main():
    assert BLF.is_file() and DBC.is_file(), "请先运行 scripts/make_test_data.py"

    # ---- 单遍加载(索引+统计) ----
    from workers.blf_loader import compute_index_and_stats
    t = time.perf_counter()
    idx, stats, n = compute_index_and_stats(BLF)
    dt = time.perf_counter() - t
    blf_cache.store_index(BLF, idx, n)
    check("index+stats", n == 2000 and stats["total_frames"] == 2000,
          f"({n} 帧, {dt*1000:.0f} ms)")

    check("stats.by_id", {e["frame_id"] for e in stats["by_id"]} == {291, 292})
    CH = stats["channels"][0]["channel"]   # BLF 回读的实际通道号
    check("stats.channels", len(stats["channels"]) == 1
          and stats["channels"][0]["frames"] == 2000,
          f"(ch={CH})")
    check("stats.duration", abs(stats["duration_s"] - 10.0) < 0.05,
          f"(dur={stats['duration_s']})")

    # 与原版 blf_parser.stats 输出一致性对比
    from core.blf_parser import stats as ref_stats
    ref = ref_stats(BLF)
    same = all(ref[k] == stats[k] for k in
               ("total_frames", "fd_frames", "error_frames", "remote_frames",
                "duration_s", "unique_ids", "by_id"))
    check("stats==blf_parser.stats", same)

    # ---- DBC ----
    db = dbc_parser.load_database(DBC)
    msgs = dbc_parser.messages_summary(db)
    check("dbc.messages", [m["frame_id"] for m in msgs] == [291, 292])
    detail = dbc_parser.message_detail(db, 291)
    es = next(s for s in detail["signals"] if s["name"] == "EngineSpeed")
    check("dbc.choices", bool(es["choices"]), f"({es['choices']})")

    # ---- 通道 DBC 自动适配 ----
    from core.dbc_parser import match_channels_to_dbcs
    matched = match_channels_to_dbcs(stats, [DBC])
    ch_match = matched["channels"][CH]
    check("dbc.auto_match", ch_match["selected"] == str(DBC)
          and ch_match["matched"] == 2 and ch_match["coverage"] == 1.0)

    # ---- 解码 + 缓存命中耗时 ----
    t = time.perf_counter()
    res = decode_signal(BLF, db, 291, "EngineSpeed", max_points=200000)
    dt = time.perf_counter() - t
    check("decode.EngineSpeed", res["points"] == 1000 and len(res["values"]) == 1000,
          f"({res['points']} 点, {dt*1000:.1f} ms)")
    check("decode.range", 400 < min(res["values"]) and max(res["values"]) < 1600)

    # ---- 统计服务 ----
    ss = stats_service.signal_stats(BLF, db, 291, "EngineSpeed")
    check("signal_stats", ss["count"] == 1000 and "min" in ss and "std" in ss,
          f"(min={ss.get('min')} max={ss.get('max')})")
    cs = stats_service.cycle_stats(BLF, db, 291)
    check("cycle_stats", cs["count"] == 1000 and abs(cs["avg_ms"] - 10.0) < 1.0,
          f"(avg={cs.get('avg_ms')}ms jitter={cs.get('jitter_ms')}ms)")
    fp = stats_service.frames_page(BLF, db, 292, limit=50, offset=10)
    check("frames_page", fp["returned"] == 50 and fp["frames"][0]["id_hex"] == "0x124")
    bl = stats_service.bus_load(BLF, 500000, 2000000, "canfd")
    check("bus_load", str(CH) in bl["channels"]
          and 0 < bl["channels"][str(CH)]["bus_load_pct"] < 100,
          f"(load={bl['channels'][str(CH)]['bus_load_pct']}%)")

    # ---- 回放引擎 ----
    src = BlfReplaySource(BLF)
    eng = PlaybackEngine(src, {CH: db}, [
        SignalSub(frame_id=291, channel=CH, signal="EngineSpeed", dbc="test.dbc"),
        SignalSub(frame_id=292, channel=CH, signal="VehicleSpeed", dbc="test.dbc"),
    ])
    total_pts = 0
    batches = 0
    while True:
        b = eng.advance_to(999.0)
        if b is None:
            break
        total_pts += sum(len(v["times"]) for v in b["signals"].values())
        batches += 1
    check("playback.full", eng.ended and total_pts == 2000,
          f"({batches} 批次, {total_pts} 点)")
    eng.seek(5.0)
    b = eng.advance_to(5.05)
    check("playback.seek", b is not None and all(
        5.0 <= t <= 5.06 for v in b["signals"].values() for t in v["times"]))
    lo, hi = src.time_range
    check("source.range", abs(lo) < 1e-6 and abs(hi - 9.99) < 0.01, f"({lo:.2f},{hi:.2f})")

    print()
    if fails:
        print(f"FAILED: {len(fails)} -> {fails}")
        return 1
    print("ALL CORE TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
