"""GUI 冒烟测试(M5):三态选中记忆 / 配置抽屉 / 通道重映射 / 抖动峰值标记。

运行: python tests/smoke_m5.py(默认 offscreen;使用独立 QSettings 目录)
"""
import os
import shutil
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QEventLoop, QSettings, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from gui.theme import QSS  # noqa: E402

QMessageBox.warning = staticmethod(lambda *a, **k: print("[MODAL]", a[2] if len(a) > 2 else a))
QMessageBox.critical = staticmethod(lambda *a, **k: print("[MODAL]", a))

fails = []


def check(name, cond, extra=""):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        fails.append(name)


def wait_for(cond_fn, timeout_ms=6000):
    loop = QEventLoop()
    t = QTimer()
    t.timeout.connect(lambda: cond_fn() and loop.quit())
    t.start(20)
    QTimer.singleShot(timeout_ms, loop.quit)
    loop.exec()
    t.stop()


def main() -> int:
    # 独立 QSettings(测试隔离)
    qs_dir = ROOT / "tests" / "qsettings"
    if qs_dir.exists():
        shutil.rmtree(qs_dir, ignore_errors=True)
    qs_dir.mkdir(parents=True, exist_ok=True)
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(qs_dir))

    blf = ROOT / "data" / "test.blf"
    dbc = ROOT / "data" / "test.dbc"

    app = QApplication(sys.argv)
    app.setOrganizationName("canscope")
    app.setApplicationName("CANScope")
    app.setStyleSheet(QSS)

    from gui.main_window import MainWindow
    win = MainWindow()
    win.show()

    ready = {"ok": False}

    def on_channels(_i, _m):
        ready["ok"] = True

    win.state.channelsReady.connect(on_channels)
    win.state.open_paths([blf, dbc])

    def run_steps():
        if not ready["ok"]:
            QTimer.singleShot(50, run_steps)
            return
        try:
            steps(win, qs_dir, blf, dbc)
        except Exception as e:
            import traceback
            traceback.print_exc()
            fails.append(f"exception:{e}")
        finish(win, app)

    QTimer.singleShot(100, run_steps)
    return app.exec()


def steps(win, qs_dir, blf, dbc):
    s = win.state
    st = win.scope_stack
    ch = s.stats["channels"][0]["channel"]

    # 1) 首次打开 → 自动选中 0x123 前两个信号
    wait_for(lambda: len(s.signals_list) == 2)
    keys = {e.key for e in s.signals_list}
    check("首次自动选2信号", keys == {f"291|{ch}|EngineSpeed", f"291|{ch}|CoolantTemp"},
          f"({keys})")

    # 2) 记忆写入
    wait_for(lambda: (qs_dir and any(qs_dir.rglob("*.ini"))), timeout_ms=3000)
    win._save_selection()
    val = win.settings.value(win._sel_key(), "", type=str)
    check("记忆已写入", "291|" in val, f"({val!r})")

    # 3) 清空 → CLEARED
    s.clear_all_signals()
    wait_for(lambda: not win._sel_save_timer.isActive())
    win._save_selection()
    val = win.settings.value(win._sel_key(), "", type=str)
    check("清空标记", val == "CLEARED", f"({val!r})")

    # 4) 重开工程 → 保持空(cleared 三态)
    s.open_paths([blf, dbc])
    wait_for(lambda: s.stats is not None and s.channels_info)
    wait_for(lambda: False, timeout_ms=1200)   # 观察窗口:不应自动选
    check("cleared保持空", len(s.signals_list) == 0,
          f"({len(s.signals_list)})")

    # 5) 手动选一个 → 记忆恢复为列表
    s.toggle_signal(292, ch, "VehicleSpeed")
    wait_for(lambda: len(s.signals_list) == 1)
    win._save_selection()
    val = win.settings.value(win._sel_key(), "", type=str)
    check("记忆更新", val == f"292|{ch}|VehicleSpeed", f"({val!r})")

    # 6) 配置弹窗
    from gui.config_drawer import ConfigDialog
    dlg = ConfigDialog(s, win.settings, win)
    # 主窗口在 _open_config 中接线;测试直构对话框需自行连接
    dlg.mappingApplied.connect(s.apply_channel_mapping)
    dlg.configSaved.connect(lambda: win.id_panel.refresh_bus_load())
    dlg.jitterToggled.connect(win.scope_stack.show_jitter_marks)
    dlg.show()
    wait_for(lambda: dlg.isVisible())
    check("弹窗打开", dlg.isVisible())
    check("总线类型", dlg.cmb_bus.currentData() == "canfd")
    check("仲裁波特率", dlg.cmb_arb.currentData() == 500000)
    check("BLF信息", "test.blf" in dlg.lbl_blf.text())
    check("映射行", 0 in dlg._map_combos)

    # 修改波特率 → 保存 → config.json 生效(弹窗应关闭)
    print("[STEP] 6b on_save")
    i = dlg.cmb_arb.findData(1000000)
    dlg.cmb_arb.setCurrentIndex(i)
    dlg.on_save()
    print("[STEP] 6c saved")
    import json
    cfg = json.loads((ROOT / "data" / "config.json").read_text(encoding="utf-8"))
    check("配置持久化", cfg["baudrate_arb"] == 1000000, f"({cfg['baudrate_arb']})")
    # 还原 500k
    i = dlg.cmb_arb.findData(500000)
    dlg.cmb_arb.setCurrentIndex(i)
    dlg.on_save()

    # 7) 通道重映射(映射到同一 DBC)→ 树重建
    remap = {0: s.dbc_files[0]}
    emitted = {"ok": False}
    s.channelsReady.connect(lambda _i, _m: emitted.__setitem__("ok", True))
    s.apply_channel_mapping(remap)
    wait_for(lambda: emitted["ok"])
    check("重映射生效", s.channel_dbc.get(0) is not None
          and s.messages_by_channel.get(0))

    # 8) 抖动峰值标记(经复选框,验证设置持久化)
    dlg.chk_jitter.setChecked(True)
    win.sig_panel.refresh()
    wait_for(lambda: win.sig_panel._pending == 0
             and win.sig_panel.tbl_cyc.rowCount() >= 1)
    marks_n = sum(len(p._mark_items) for p in st.plots)
    check("峰值标记显示", marks_n >= 1, f"({marks_n} 个)")
    dlg.chk_jitter.setChecked(False)
    marks_n = sum(len(p._mark_items) for p in st.plots)
    check("峰值标记隐藏", marks_n == 0, f"({marks_n} 个)")
    jit_val = win.settings.value("ui/jitter_marks", "", type=str)
    check("抖动开关记忆", jit_val == "false", f"({jit_val!r})")

    win.drawer_check = dlg   # 供映射步骤复用
    # 9) 通道映射修改端到端(回归:Signal(dict) int 键曾静默丢槽)
    dbc2 = ROOT / "tests" / "mapping_test.dbc"
    dbc2.write_text(
        'VERSION ""\n\nBS_:\n\nBU_: NAV\n\n'
        'BO_ 500 NavData: 8 NAV\n'
        ' SG_ NavStatus : 0|16@1+ (1,0) [0|65535] "" NAV\n',
        encoding="utf-8")
    if str(dbc2) not in s.dbc_files:
        s.dbc_files.append(str(dbc2))
    dlg._refresh_mapping()
    cmb0 = dlg._map_combos[ch]
    cmb0.setCurrentIndex(cmb0.findData(str(dbc2)))
    ready_n = {"n": 0}
    s.channelsReady.connect(lambda _i, _m: ready_n.__setitem__("n", ready_n["n"] + 1))
    dlg.on_save()
    wait_for(lambda: ready_n["n"] >= 1)
    check("映射修改生效", s.channel_dbc.get(ch) == str(dbc2),
          f"({s.channel_dbc.get(ch)})")
    check("新DBC报文入树", any(m["name"] == "NavData"
                              for m in s.messages_by_channel.get(ch, [])))
    # 还原为 test.dbc
    dlg._refresh_mapping()
    cmb0 = dlg._map_combos[ch]
    cmb0.setCurrentIndex(cmb0.findData(str(dbc)))
    dlg.on_save()
    wait_for(lambda: s.channel_dbc.get(ch) == str(dbc))
    check("映射还原", s.channel_dbc.get(ch) == str(dbc))
    dbc2.unlink()
    dlg.close()


def finish(win, app):
    try:
        png = ROOT / "tests" / "gui_smoke_m5.png"
        win.grab().save(str(png))
        print(f"[SAVE] {png}")
    except Exception as e:
        print(f"[WARN] screenshot failed: {e}")
    ok = not fails
    print(f"[{'PASS' if ok else 'FAIL'}] M5 GUI smoke: {len(fails)} failed {fails if fails else ''}")
    app.exit(0 if ok else 1)


if __name__ == "__main__":
    sys.exit(main())
