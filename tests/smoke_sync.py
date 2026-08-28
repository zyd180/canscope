"""同步冒烟测试(Web 版 v113 同步:内容识别文件类型 + 大文件进度回调)。

运行: python tests/smoke_sync.py
真实大文件(449MB BLF)验证: $env:SYNC_REALDATA=1 后运行(较慢)。
"""
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.file_types import detect_kind  # noqa: E402

DATA = ROOT / "data"
fails = []


def check(name, cond, extra=""):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        fails.append(name)


def main() -> int:
    blf, dbc = DATA / "test.blf", DATA / "test.dbc"
    assert blf.is_file() and dbc.is_file(), "请先运行 scripts/make_test_data.py"

    # ---- 1) 按内容识别文件类型 ----
    check("识别BLF", detect_kind(blf) == ".blf")
    check("识别DBC", detect_kind(dbc) == ".dbc")
    tmp = Path(tempfile.mkdtemp())
    try:
        fake_log = tmp / "renamed.log"
        shutil.copy(blf, fake_log)
        check("改名.log仍是BLF", detect_kind(fake_log) == ".blf")
        fake_txt = tmp / "renamed.txt"
        shutil.copy(dbc, fake_txt)
        check("改名.txt仍是DBC", detect_kind(fake_txt) == ".dbc")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # ---- 2) 解析进度回调 ----
    from workers.blf_loader import compute_index_and_stats
    prog = []
    t = time.perf_counter()
    idx, stats, n = compute_index_and_stats(blf, progress_cb=prog.append)
    dt = time.perf_counter() - t
    check("进度有回调", len(prog) > 10, f"({len(prog)} 次, {dt*1000:.0f} ms)")
    check("进度单调递增", all(a <= b for a, b in zip(prog, prog[1:])))
    check("进度范围", prog[0] >= 0 and prog[-1] <= 0.99, f"(last={prog[-1]:.3f})")
    check("结果不变", n == 2000 and stats["total_frames"] == 2000)

    # ---- 3) 真实大文件(可选,SYNC_REALDATA=1) ----
    if os.environ.get("SYNC_REALDATA"):
        up = Path(r"F:\TestPrj\blf-dbc-web-main\data\uploads")
        real_blf = next((p for p in up.glob("*_L003.blf")), None)
        real_dbc = next((p for p in up.glob("EEA*.dbc")), None)
        if real_blf is not None and real_dbc is not None and real_blf.is_file():
            from core import dbc_parser
            from core.decoder import decode_signal
            prog2 = []
            t = time.perf_counter()
            idx2, st2, n2 = compute_index_and_stats(real_blf,
                                                    progress_cb=prog2.append)
            dt2 = time.perf_counter() - t
            print(f"[INFO] 真实BLF: {n2:,} 帧, {dt2:.1f}s, "
                  f"进度回调 {len(prog2)} 次, last={prog2[-1]:.3f}")
            check("真实BLF解析", n2 > 0 and len(prog2) > 100)
            check("真实BLF进度", prog2[-1] > 0.9, f"(last={prog2[-1]:.3f})")
            db = dbc_parser.load_database(real_dbc)
            msgs = dbc_parser.messages_summary(db)
            print(f"[INFO] 真实DBC: {len(msgs)} 报文 / "
                  f"{sum(m['signal_count'] for m in msgs)} 信号")
            check("真实DBC加载", len(msgs) > 0)
            # 找一个 DBC 与日志都有的报文,解码第一个信号
            by_id = {e["frame_id"] for e in st2["by_id"]}
            hit = next((m for m in msgs if m["frame_id"] in by_id), None)
            check("DBC∩BLF报文", hit is not None,
                  f"({len(by_id & {m['frame_id'] for m in msgs})} 个交集)")
            if hit:
                ch = st2["channels"][0]["channel"]
                sig = hit["signals"][0]
                t = time.perf_counter()
                res = decode_signal(real_blf, db, hit["frame_id"], sig,
                                    max_points=200000, channel=ch)
                print(f"[INFO] 解码 {hex(hit['frame_id'])}/{sig}: "
                      f"{res['points']:,} 点, {time.perf_counter()-t:.2f}s")
                check("真实信号解码", res["points"] > 0)

    print()
    if fails:
        print(f"FAILED: {len(fails)} -> {fails}")
        return 1
    print("ALL SYNC TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
