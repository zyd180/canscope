"""深色主题:QSS 样式表(配色移植自 Web 版 style.css)+ Windows 深色标题栏。"""
from __future__ import annotations

import sys

DARK_BG = "#16181d"
PANEL_BG = "#1e2128"
SIDE_BG = "#1a1d23"
INPUT_BG = "#14171d"
BORDER = "#2b2f38"
TEXT = "#c9ced6"
TEXT_BRIGHT = "#e8ecf2"
TEXT_DIM = "#8a93a3"
ACCENT = "#4da3ff"
BTN_PRIMARY = "#2563eb"

QSS = f"""
* {{ outline: none; }}
QWidget {{
    background: {DARK_BG};
    color: {TEXT};
    font-size: 13px;
    font-family: "Microsoft YaHei UI", "PingFang SC", sans-serif;
}}

QToolBar {{
    background: {PANEL_BG};
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 4px 8px;
    spacing: 6px;
}}
QToolButton, QPushButton {{
    background: #23262e;
    border: 1px solid #2c323d;
    border-radius: 4px;
    padding: 5px 14px;
    color: {TEXT};
}}
QToolButton:hover, QPushButton:hover {{
    background: #343a46;
    border-color: {ACCENT};
    color: {TEXT_BRIGHT};
}}
QToolButton:pressed, QPushButton:pressed {{ background: {BTN_PRIMARY}; }}
QPushButton#primary {{ background: {BTN_PRIMARY}; border-color: {BTN_PRIMARY}; color: white; }}
QPushButton#primary:hover {{ background: #1d4ed8; }}
QPushButton:disabled, QToolButton:disabled {{ color: #5c6472; background: #1c1f26; }}

QLabel#logo {{ color: {TEXT_BRIGHT}; font-size: 14px; font-weight: bold; padding-right: 4px; }}
QLabel#versionChip {{
    background: rgba(90,212,122,.15); color: #5ad47a;
    border: 1px solid rgba(90,212,122,.4); border-radius: 9px;
    padding: 1px 10px; font-size: 11px;
}}
QLabel#busyLabel {{ color: #ffb84d; }}
QLabel#dimLabel {{ color: #5c6472; }}

QLineEdit {{
    background: {INPUT_BG};
    border: 1px solid #2c323d;
    border-radius: 4px;
    padding: 4px 8px;
    selection-background-color: {BTN_PRIMARY};
}}
QLineEdit:focus {{ border-color: {ACCENT}; }}

QTreeView {{
    background: {SIDE_BG};
    border: none;
    alternate-background-color: {SIDE_BG};
}}
QTreeView::item {{ padding: 2px 4px; }}
QTreeView::item:hover {{ background: #23262e; }}
QTreeView::item:selected {{ background: {BTN_PRIMARY}; color: white; }}
QTreeView::branch {{ background: {SIDE_BG}; }}

QTabWidget::pane {{ border-top: 1px solid {BORDER}; background: {DARK_BG}; }}
QTabBar::tab {{
    background: {SIDE_BG};
    color: {TEXT_DIM};
    padding: 6px 18px;
    border: none;
    border-top: 2px solid transparent;
}}
QTabBar::tab:selected {{ color: {TEXT_BRIGHT}; background: {PANEL_BG}; border-top: 2px solid {ACCENT}; }}
QTabBar::tab:hover {{ color: {TEXT}; }}

QTableView {{
    background: {DARK_BG};
    gridline-color: #232730;
    border: none;
    selection-background-color: #233a5c;
    selection-color: {TEXT_BRIGHT};
}}
QHeaderView::section {{
    background: {PANEL_BG};
    color: {TEXT_DIM};
    border: none;
    border-right: 1px solid {BORDER};
    border-bottom: 1px solid {BORDER};
    padding: 5px 8px;
}}

QStatusBar {{
    background: {PANEL_BG};
    color: {TEXT_DIM};
    border-top: 1px solid {BORDER};
}}
QStatusBar QLabel {{ padding: 0 8px; }}

QSplitter::handle {{ background: #232730; }}
QSplitter::handle:horizontal {{ width: 3px; }}
QSplitter::handle:vertical {{ height: 3px; }}

QScrollArea {{ border: none; background: {DARK_BG}; }}
QScrollBar:vertical {{ background: {SIDE_BG}; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: #2c323d; border-radius: 5px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: #3a4150; }}
QScrollBar:horizontal {{ background: {SIDE_BG}; height: 10px; margin: 0; }}
QScrollBar::handle:horizontal {{ background: #2c323d; border-radius: 5px; min-width: 30px; }}
QScrollBar::handle:horizontal:hover {{ background: #3a4150; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QMenu {{ background: {PANEL_BG}; border: 1px solid {BORDER}; padding: 4px; }}
QMenu::item {{ padding: 5px 24px; border-radius: 4px; }}
QMenu::item:selected {{ background: {BTN_PRIMARY}; color: white; }}
QToolTip {{
    background: rgba(22,24,29,.97); color: {TEXT};
    border: 1px solid #3a4150; padding: 6px;
}}

QDockWidget {{
    titlebar-close-icon: none;
    color: {TEXT_BRIGHT};
}}
QDockWidget::title {{
    background: {PANEL_BG};
    padding: 6px 12px;
    border-bottom: 1px solid {BORDER};
}}

QComboBox::drop-down {{ border: none; width: 18px; }}
QComboBox QAbstractItemView {{
    background: {PANEL_BG};
    border: 1px solid #3a4150;
    selection-background-color: {BTN_PRIMARY};
    selection-color: white;
    outline: none;
}}

QCheckBox {{ spacing: 6px; }}
QCheckBox::indicator {{
    width: 14px; height: 14px;
    border: 1px solid #2c323d; border-radius: 3px;
    background: {INPUT_BG};
}}
QCheckBox::indicator:checked {{ background: {BTN_PRIMARY}; border-color: {BTN_PRIMARY}; }}
QCheckBox::indicator:hover {{ border-color: {ACCENT}; }}

QSlider::groove:horizontal {{ height: 4px; background: #2c323d; border-radius: 2px; }}
QSlider::handle:horizontal {{
    width: 14px; height: 14px; margin: -6px 0;
    border-radius: 7px; background: {ACCENT};
}}
QSlider::handle:horizontal:hover {{ background: {TEXT_BRIGHT}; }}
QSlider::sub-page:horizontal {{ background: #2563eb; border-radius: 2px; }}

QGroupBox {{
    border: 1px solid {BORDER}; border-radius: 6px;
    margin-top: 10px; padding-top: 6px;
}}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; color: {TEXT_DIM}; }}
"""


def apply_dark_title_bar(widget) -> None:
    """Windows:标题栏深色化并匹配主题色。

    - 深色模式:Win10 19041+ / Win11(属性 20,旧 build 回退 19)
    - 标题栏/边框配色:Win11(属性 35/34),旧系统自动忽略
    - 其他平台或调用失败:静默忽略
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        hwnd = int(widget.winId())
        dwm = ctypes.windll.dwmapi
        dark = ctypes.c_int(1)
        for attr in (20, 19):   # DWMWA_USE_IMMERSIVE_DARK_MODE
            if dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(dark), 4) == 0:
                break

        def colorref(hex_str: str):
            r = int(hex_str[1:3], 16)
            g = int(hex_str[3:5], 16)
            b = int(hex_str[5:7], 16)
            return ctypes.c_uint((b << 16) | (g << 8) | r)

        cap = colorref(PANEL_BG)     # DWMWA_CAPTION_COLOR
        dwm.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(cap), 4)
        bor = colorref(BORDER)       # DWMWA_BORDER_COLOR
        dwm.DwmSetWindowAttribute(hwnd, 34, ctypes.byref(bor), 4)
    except Exception:
        pass
