"""可重复的解析/解码/负载基准。

运行: python scripts/benchmark.py [日志路径]
"""
from __future__ import annotations

import json
import sys
import time
import tracemalloc
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import blf_cache, dbc_parser  # noqa: E402
from core.decoder import decode_signal  # noqa: E402
from services.stats_service import bus_load  # noqa: E402
from workers.blf_loader import compute_index_and_stats  # noqa: E402


def run(path: Path, dbc_path: Path | None = None) -> dict:
    tracemalloc.start()
    started = time.perf_counter()
    index, stats, frame_count = compute_index_and_stats(path)
    parse_s = time.perf_counter() - started
    blf_cache.store_index(path, index, frame_count)

    decode_s = None
    bus_load_s = None
    if dbc_path and dbc_path.is_file():
        db = dbc_parser.load_database(dbc_path)
        frame_id = next(iter(index), None)
        if frame_id is not None:
            signal = db.get_message_by_frame_id(frame_id).signals
            if signal:
                started = time.perf_counter()
                decode_signal(path, db, frame_id, signal[0].name)
                decode_s = time.perf_counter() - started
        started = time.perf_counter()
        bus_load(path, 500000, 2000000, "canfd")
        bus_load_s = time.perf_counter() - started
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {
        "file": str(path),
        "frames": stats["total_frames"],
        "duration_s": stats.get("duration_s", 0.0),
        "parse_s": round(parse_s, 3),
        "decode_s": round(decode_s, 3) if decode_s is not None else None,
        "bus_load_s": round(bus_load_s, 3) if bus_load_s is not None else None,
        "peak_python_memory_mb": round(peak_bytes / 1024 / 1024, 1),
    }


if __name__ == "__main__":
    log = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "test.blf"
    dbc = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "data" / "test.dbc"
    print(json.dumps(run(log, dbc), ensure_ascii=False, indent=2))
