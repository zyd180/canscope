"""工程配置持久化:data/config.json(总线类型/波特率/最近打开的 BLF/通道 DBC 映射)。

与 Web 版结构兼容,但 blf/dbc/channels 存绝对路径(桌面无 uploads 概念)。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# 默认配置:总线类型 / 波特率(CAN FD 双速率)/ 通道→DBC 映射
DEFAULT_CONFIG = {
    "bus_type": "canfd",          # can | canfd
    "baudrate_arb": 500000,       # 仲裁段波特率
    "baudrate_data": 2000000,     # 数据段波特率(CAN FD)
    "blf": None,                  # 当前 BLF 文件(绝对路径)
    "dbc": None,                  # 默认 DBC(兜底)
    "channels": {},               # {"<channel>": dbc 绝对路径}
}

VALID_BUS_TYPES = {"can", "canfd"}


def app_root() -> Path:
    """应用根目录:打包(PyInstaller)后取 exe 所在目录,开发时取仓库根。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


DATA_DIR = app_root() / "data"
CONFIG_FILE = DATA_DIR / "config.json"


def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_FILE.is_file():
        try:
            cfg.update(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            pass  # 配置损坏时回落默认
    return cfg


def save_config(cfg: dict) -> None:
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2),
                           encoding="utf-8")
