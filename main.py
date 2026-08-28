"""CANScope(CAN 总线分析仪)入口:python main.py

打包冒烟测试: CANScope.exe --smoke
(自动打开演示数据 → 6 秒后截图 smoke_screenshot.png → 以 0/1 退出)
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from gui.theme import QSS


def _migrate_legacy_settings(config_dir: Path) -> None:
    """产品更名(CAN Analyzer → CANScope)一次性迁移旧界面偏好。

    新旧 QSettings 均为 INI 后端且键结构一致,整文件搬移即可:
      config/blf-dbc-desktop/CAN Analyzer.ini → config/canscope/CANScope.ini
    仅当新文件不存在且旧文件存在时执行,天然幂等。
    """
    legacy_dir = config_dir / "blf-dbc-desktop"
    src = legacy_dir / "CAN Analyzer.ini"
    dst_dir = config_dir / "canscope"
    dst = dst_dir / "CANScope.ini"
    if not (src.is_file() and not dst.exists()):
        return
    try:
        dst_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
    except OSError:
        return   # 迁移失败不阻塞启动(按无偏好运行)
    try:
        if next(legacy_dir.iterdir(), None) is None:
            legacy_dir.rmdir()
    except OSError:
        pass


def main() -> int:
    from services.diagnostics import install_exception_hook, record_operation
    install_exception_hook()
    record_operation("应用启动")
    app = QApplication(sys.argv)
    app.setApplicationName("CANScope")
    app.setOrganizationName("canscope")

    # QSettings 用 INI 文件(便携,随应用目录):注册表原生格式对含盘符冒号
    # 的键存在写读不一致问题(setValue 后 value 返回旧值)
    from PySide6.QtCore import QSettings
    from services.project_config import app_root
    config_dir = app_root() / "config"
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope,
                      str(config_dir))
    _migrate_legacy_settings(config_dir)

    app.setStyleSheet(QSS)

    from gui.main_window import MainWindow
    from gui.theme import apply_dark_title_bar
    win = MainWindow()
    apply_dark_title_bar(win)   # Windows 深色标题栏/边框(匹配主题)
    win.showMaximized()         # 启动默认最大化

    if "--smoke" in sys.argv:
        return _run_smoke(app, win)
    return app.exec()


def _run_smoke(app: QApplication, win) -> int:
    """打包冒烟:打开演示数据 → 截图 → 按校验结果退出。
    结果写 smoke_log.txt(--windowed 下 stdout 不可用)。"""
    from pathlib import Path

    from services.project_config import app_root

    log_path = app_root() / "smoke_log.txt"
    lines: list = []

    def log(msg: str) -> None:
        lines.append(msg)
        try:
            log_path.write_text("\n".join(lines), encoding="utf-8")
        except OSError:
            pass

    def start():
        try:
            # 冒烟每次验证"首次打开自动选信号":覆写为无记录状态
            # (remove() 对含盘符冒号的注册表键不可靠,改用强制覆写)
            win.settings.setValue(win._sel_key(), "")
            data = app_root() / "data"
            blf, dbc = data / "test.blf", data / "test.dbc"
            log(f"blf={blf} exists={blf.is_file()} dbc={dbc} exists={dbc.is_file()}")
            log(f"sel_value={win.settings.value(win._sel_key(), '<none>', type=str)!r}")
            if blf.is_file() and dbc.is_file():
                win.state.open_paths([blf, dbc])
                log(f"after open_paths value={win.settings.value(win._sel_key(), '<none>', type=str)!r}")
            win.state.channelsReady.connect(
                lambda i, m: log(f"channelsReady: ch={len(i)} "
                                 f"msgs={sum(len(v) for v in m.values())} value="
                                 f"{win.settings.value(win._sel_key(), '<none>', type=str)!r}"))
            win.state.errorRaised.connect(lambda e: log(f"ERROR: {e}"))
            win.state.signalsChanged.connect(
                lambda: log(f"signalsChanged n={len(win.state.signals_list)} "
                            f"value={win.settings.value(win._sel_key(), '<none>', type=str)!r}"))
            orig_rs = win._restore_selection

            def _rs():
                log("restore called")
                s = win.state
                log(f"auto={s.first_auto_selection()} "
                    f"has_data={sorted(s.has_data)} "
                    f"ch_dbc={s.channel_dbc} "
                    f"ch_info={[(c['channel'], c['dbc']) for c in s.channels_info]}")
                orig_rs()
                log(f"restore done pending={win._restore_pending} "
                    f"restoring={win._restoring}")

            win._restore_selection = _rs
        except Exception as e:
            log(f"start error: {e}")

    def finish():
        code = 1
        try:
            ok = win.state.stats is not None and len(win.state.signals_list) >= 1
            png = app_root() / "smoke_screenshot.png"
            win.grab().save(str(png))
            log(f"stats={'OK' if win.state.stats else 'NONE'} "
                f"signals={len(win.state.signals_list)} png={png.name} "
                f"final_value={win.settings.value(win._sel_key(), '<none>', type=str)!r}")
            code = 0 if ok else 1
        except Exception as e:
            log(f"finish error: {e}")
        log(f"exit={code}")
        app.exit(code)

    QTimer.singleShot(300, start)
    QTimer.singleShot(6000, finish)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
