"""R2 数据互通与导出扩展冒烟测试。

覆盖:
2.1 ASC 输入     —— BLF→ASC 往返:内容识别(含改名文件)、帧数一致、索引一致、
                    解码结果一致
2.2 MF4 输入     —— asammdf 门控:合成 MF4→适配器读回→完整 stats 链路
2.3 BLF 片段导出 —— 时间区间裁剪、全局时序、回读帧数/范围校验
2.4 Trace 全量导出—— 全量行数、信号值过滤、BOM 与表头
2.5 DBC 骨架     —— (fid,dlc)→DBC 文件、cantools 可加载、ID/DLC/零信号正确
2.6 树未识别分组 —— 无 DBC 通道灰组+条目、右键骨架请求→文件落盘并合法

运行: python tests/smoke_r2.py(asammdf 未安装时 MF4 段自动门控跳过)
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import can  # noqa: E402

from core import blf_cache, dbc_parser  # noqa: E402
from core.blf_parser import stats as log_stats  # noqa: E402
from core.decoder import decode_signal  # noqa: E402
from core.file_types import detect_kind  # noqa: E402
from services import exporters  # noqa: E402

DATA = ROOT / "data"
BLF = DATA / "test.blf"
DBC = DATA / "test.dbc"

TMP = Path(tempfile.gettempdir())
fails = []


def check(name, cond, extra=""):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}", flush=True)
    if not cond:
        fails.append(name)


def wait_file_gone(p: Path) -> None:
    try:
        p.unlink()
    except OSError:
        pass


def make_asc_from_blf(dst: Path) -> None:
    with can.ASCWriter(str(dst)) as w:
        for m in can.BLFReader(str(BLF)):
            w.on_message_received(can.Message(
                timestamp=m.timestamp, arbitration_id=m.arbitration_id,
                data=m.data, is_extended_id=m.is_extended_id, channel=1))


def make_mf4_corpus(dst: Path, n: int = 40) -> None:
    import numpy as np
    from asammdf import MDF
    from asammdf.signal import Signal
    t = np.arange(n, dtype=np.float64) * 0.01
    half = n // 2
    ids = np.array([0x123] * half + [0x18FF0102] * (n - half), dtype=np.uint32)
    ide = np.array([0] * half + [1] * (n - half), dtype=np.uint8)
    data = np.array([[i & 0xFF, 2, 3, 4, 5, 6, 7, 8] for i in range(n)],
                    dtype=np.uint8)
    m = MDF(version="4.10")
    m.append([
        Signal(samples=np.ones(n, np.uint8), timestamps=t,
               name="CAN_DataFrame.BusChannel"),
        Signal(samples=ids, timestamps=t, name="CAN_DataFrame.ID"),
        Signal(samples=ide, timestamps=t, name="CAN_DataFrame.IDE"),
        Signal(samples=data, timestamps=t, name="CAN_DataFrame.DataBytes"),
    ], common_timebase=True)
    m.save(str(dst), overwrite=True)
    m.close()


def main() -> int:
    assert BLF.is_file() and DBC.is_file(), "请先运行 scripts/make_test_data.py"
    db = dbc_parser.load_database(DBC)

    asc = TMP / "r2_roundtrip.asc"
    asc_txt = TMP / "r2_roundtrip.txt"   # 改名文件同样按内容识别
    seg = TMP / "r2_segment.blf"
    seg_full = TMP / "r2_segment_all.blf"
    trace_all = TMP / "r2_trace_all.csv"
    trace_flt = TMP / "r2_trace_flt.csv"
    skel = TMP / "r2_skeleton.dbc"
    mf4 = TMP / "r2_corpus.mf4"
    for p in (asc, asc_txt, seg, seg_full, trace_all, trace_flt, skel, mf4):
        wait_file_gone(p)

    try:
        # ---------------- 2.1 ASC 输入 ----------------
        make_asc_from_blf(asc)
        check("ASC 内容识别", detect_kind(asc) == ".asc")
        asc_txt.write_bytes(asc.read_bytes())
        check("ASC 改名识别(.txt)", detect_kind(asc_txt) == ".asc")

        st_blf = log_stats(BLF)
        st_asc = log_stats(asc)
        diff = abs(st_asc["total_frames"] - st_blf["total_frames"])
        check("ASC 帧数一致(±1)", diff <= 1,
              f"blf={st_blf['total_frames']} asc={st_asc['total_frames']}")
        idx_asc = blf_cache.get_frames_index(asc)
        n_rows = sum(len(v) for v in idx_asc.values())
        check("ASC 索引一致(±1)", abs(n_rows - st_blf["total_frames"]) <= 1,
              f"rows={n_rows}")
        res_asc = decode_signal(asc, db, 291, "EngineSpeed")
        res_blf = decode_signal(BLF, db, 291, "EngineSpeed")
        same = (abs(res_asc["points"] - res_blf["points"]) <= 1
                and res_asc["values"][:5] == res_blf["values"][:5])
        check("ASC 解码一致", same,
              f"pts {res_blf['points']}→{res_asc['points']}")

        # ---------------- 2.2 MF4 输入(asammdf 门控) ----------------
        try:
            import asammdf  # noqa: F401
            has_mdf = True
        except ImportError:
            has_mdf = False
        if has_mdf:
            make_mf4_corpus(mf4)
            check("MF4 内容识别", detect_kind(mf4) == ".mf4")
            st_mf4 = log_stats(mf4)
            ids_ch = {e["channel"]: {i["frame_id"] for i in e["ids"]}
                      for e in st_mf4["ids_by_channel"]}
            ch1 = next(iter(ids_ch), None)
            got = ids_ch.get(1, set())
            check("MF4 帧与ID", st_mf4["total_frames"] == 40
                  and got == {0x123, 0x18FF0102},
                  f"n={st_mf4['total_frames']} ids={sorted(hex(i) for i in got)}")
        else:
            check("MF4 门控跳过(未安装 asammdf)", True, "gated")

        # ---------------- 2.3 BLF 片段导出 ----------------
        idx_blf = blf_cache.get_frames_index(BLF)
        expect = sum(1 for rows in idx_blf.values() for r in rows
                     if 1.0 <= r[0] <= 5.0)
        n_seg = exporters.export_blf_segment(BLF, seg, start=1.0, end=5.0)
        check("片段帧数", n_seg == expect,
              f"export={n_seg} expect={expect}")
        back = [(m.timestamp, m.arbitration_id) for m in can.BLFReader(str(seg))]
        ts_sorted = all(back[i][0] <= back[i + 1][0] + 1e-9
                        for i in range(len(back) - 1))
        # BLFWriter 以首个消息为新时间基准:相对时序保持,起点归零
        rel_ok = (len(back) == n_seg and ts_sorted
                  and abs(back[0][0]) < 0.02
                  and abs((back[-1][0] - back[0][0]) - 4.0) < 0.02)
        check("片段回读相对时序保持", rel_ok,
              f"n={len(back)} span={back[-1][0]-back[0][0]:.3f}s")
        st_seg = log_stats(seg)
        check("片段可再解析", st_seg["total_frames"] == n_seg)
        n_all = exporters.export_blf_segment(BLF, seg_full)
        check("全量区间导出", n_all == st_blf["total_frames"], f"n={n_all}")

        # ---------------- 2.4 Trace 全量 CSV ----------------
        n_all_csv = exporters.export_trace_csv(BLF, db, 291, trace_all)
        check("Trace 全量行数", n_all_csv == 1000, f"rows={n_all_csv}")
        head = trace_all.read_text(encoding="utf-8-sig").splitlines()[0]
        check("Trace 表头", head == "时间(s),ID,报文,DLC,CH,数据(hex)", head)
        raw_head = trace_all.read_bytes()[:3]
        check("CSV BOM", raw_head == b"\xef\xbb\xbf")
        n_flt = exporters.export_trace_csv(BLF, db, 292, trace_flt,
                                           sig_filter="VehicleSpeed",
                                           sig_value="50")
        # 0.2Hz 正弦在 t=0/2.5/5.0/7.5s 过零,均为精确 50.00 → 恰 4 帧
        check("Trace 信号值过滤", n_flt == 4, f"rows={n_flt}(VehicleSpeed=50)")

        # ---------------- 2.5 DBC 骨架 ----------------
        ids_dlc = [(0x18FF0102, 12), (0x1F4, 8)]
        n_skel = exporters.export_dbc_skeleton(ids_dlc, skel)
        import cantools
        skel_db = cantools.database.load_file(str(skel))
        skel_ids = {m.frame_id: m for m in skel_db.messages}
        check("骨架报文数与命名", n_skel == 2
              and skel_ids[0x1F4].name == "Unknown_1F4")
        check("骨架 DLC/零信号", skel_ids[0x18FF0102].length == 12
              and len(skel_ids[0x18FF0102].signals) == 0)

        # ---------------- 2.6 树未识别分组(真实 GUI 路径) ----------------
        _run_gui_skeleton_check()

        print()
        if fails:
            print(f"FAILED: {fails}")
            return 1
        print("R2 SMOKE ALL PASSED")
        return 0
    finally:
        for p in (asc, asc_txt, seg, seg_full, trace_all, trace_flt, skel, mf4):
            wait_file_gone(p)


def _run_gui_skeleton_check() -> None:
    import json

    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication

    from gui.message_tree import KIND_ROLE
    from gui.theme import QSS

    # 固定工程基线:备份并覆写 config.json,避免外部状态(用户手动打开过
    # 的日志/遗留临时文件)影响启动恢复;结束后原样还原。
    cfg_path = ROOT / "data" / "config.json"
    cfg_backup = cfg_path.read_text(encoding="utf-8") if cfg_path.is_file() else None
    cfg_path.write_text(json.dumps({
        "bus_type": "canfd",
        "baudrate_arb": 500000,
        "baudrate_data": 2000000,
        "blf": str(BLF),
        "dbc": str(DBC),
        "channels": {"1": str(DBC)},
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    app = QApplication.instance() or QApplication(sys.argv)
    app.setOrganizationName("canscope")
    app.setApplicationName("CANScope")
    app.setStyleSheet(QSS)

    from gui.main_window import MainWindow
    win = MainWindow()
    win.resize(1500, 900)
    win.show()

    def wait_for(cond_fn, timeout_ms=10000):
        loop = QEventLoop()
        t = QTimer()
        t.timeout.connect(lambda: cond_fn() and loop.quit())
        t.start(20)
        QTimer.singleShot(timeout_ms, loop.quit)
        loop.exec()
        t.stop()

    unk_blf = TMP / "r2_unknown.blf"
    skel_out = TMP / "r2_tree_skeleton.dbc"
    wait_file_gone(unk_blf)
    wait_file_gone(skel_out)

    with can.BLFWriter(str(unk_blf)) as w:
        for i in range(20):
            w.on_message_received(can.Message(
                timestamp=i * 0.01, arbitration_id=0x999, data=b"\x00" * 8,
                is_extended_id=False))
        for i in range(10):
            w.on_message_received(can.Message(
                timestamp=0.5 + i * 0.01, arbitration_id=0x18FF0102,
                data=b"\x01\x02\x03\x04\x05\x06\x07\x08",
                is_extended_id=True))

    import gui.main_window as mw_mod
    mw_mod.QFileDialog.getSaveFileName = staticmethod(
        lambda *a, **k: (str(skel_out), "DBC (*.dbc)"))

    try:
        def run_flow() -> None:
            s, tree_panel = win.state, win.tree_panel

            # 等 demo 工程异步加载完成
            wait_for(lambda: s.stats is not None and bool(s.channels_info))
            ch = s.stats["channels"][0]["channel"]
            u0 = s.unknown_ids_for(ch)
            check("demo 未识别为空", u0 == [], f"{u0}")

            # 打开无 DBC 的新日志 → 两个未知 ID(注意:用新加载的通道号)
            s.open_paths([unk_blf])
            wait_for(lambda: s.stats is not None
                     and s.stats.get("file") == "r2_unknown.blf"
                     and s.channels_info
                     and s.channels_info[0].get("unknown") is not None)
            ch2 = s.stats["channels"][0]["channel"]

            unk = s.unknown_ids_for(ch2)
            ids = sorted(f for f, _d in unk)
            check("未知 ID 清单", ids == sorted([0x999, 0x18FF0102]),
                  f"{[(hex(f), d) for f, d in unk]}")

            # 树中灰组与条目
            groups = []
            stack = [tree_panel.tree.invisibleRootItem()]
            while stack:
                it = stack.pop()
                if it.data(0, KIND_ROLE) == "unknown_group":
                    groups.append(it)
                for c in range(it.childCount()):
                    stack.append(it.child(c))
            check("树出现未识别分组", len(groups) >= 1
                  and groups[0].childCount() == 2,
                  f"groups={len(groups)} "
                  f"children={groups[0].childCount() if groups else 0}")

            # 右键骨架请求 → 文件生成且合法
            tree_panel.skeletonRequested.emit(ch2)
            ok = skel_out.is_file()
            loaded = None
            if ok:
                import cantools
                loaded = cantools.database.load_file(str(skel_out))
            check("右键生成骨架落盘且合法",
                  ok and loaded is not None
                  and {m.frame_id for m in loaded.messages}
                  == {0x999, 0x18FF0102})
            app.quit()

        QTimer.singleShot(300, run_flow)
        QTimer.singleShot(60000, app.quit)
        app.exec()
    finally:
        if cfg_backup is None:
            wait_file_gone(cfg_path)
        else:
            cfg_path.write_text(cfg_backup, encoding="utf-8")
        wait_file_gone(unk_blf)
        wait_file_gone(skel_out)


if __name__ == "__main__":
    sys.exit(main())
