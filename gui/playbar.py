"""播放控制条:▶/⏸/⏹ + 进度条 + 时间 + 变速 + 诊断信息(CANoe 风格)。"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QPushButton,
                               QSlider, QWidget)

RATES = [("0.5x", 0.5), ("1x", 1.0), ("2x", 2.0), ("5x", 5.0), ("10x", 10.0)]

BTN_STYLE = """
QPushButton{background:#23262e;border:1px solid #2c323d;border-radius:4px;
color:#c9ced6;padding:3px 12px;font-size:14px;}
QPushButton:hover{border-color:#4da3ff;color:#e8ecf2;}
QPushButton#playBtn[state="playing"]{background:#2563eb;border-color:#2563eb;color:white;}
QPushButton:disabled{color:#5c6472;background:#1c1f26;}
"""


class PlayBar(QWidget):
    seekRequested = Signal(float)     # 相对秒
    playToggle = Signal()
    stopRequested = Signal()
    rateChanged = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(BTN_STYLE)
        self._dragging = False
        self._duration = 0.0
        self._mode = "idle"

        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 4, 8, 4)
        lay.setSpacing(8)

        self.btn_play = QPushButton("▶")
        self.btn_play.setObjectName("playBtn")
        self.btn_play.setFixedWidth(52)
        self.btn_play.clicked.connect(self.playToggle.emit)
        self.btn_stop = QPushButton("⏹")
        self.btn_stop.setFixedWidth(44)
        self.btn_stop.clicked.connect(self.stopRequested.emit)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 1000)
        self.slider.sliderPressed.connect(lambda: setattr(self, "_dragging", True))
        self.slider.sliderMoved.connect(self._on_moved)
        self.slider.sliderReleased.connect(self._on_released)

        self.lbl_time = QLabel("0.00 / 0.00 s")
        self.lbl_time.setStyleSheet(
            "font-family:Consolas,monospace;color:#e8ecf2;")

        self.cmb_rate = QComboBox()
        for label, r in RATES:
            self.cmb_rate.addItem(label, r)
        self.cmb_rate.setCurrentIndex(1)
        self.cmb_rate.currentIndexChanged.connect(
            lambda _i: self.rateChanged.emit(self.cmb_rate.currentData()))

        self.lbl_diag = QLabel("")
        self.lbl_diag.setStyleSheet("color:#5ad47a;font-family:Consolas,monospace;")

        lay.addWidget(self.btn_play)
        lay.addWidget(self.btn_stop)
        lay.addWidget(self.slider, 1)
        lay.addWidget(self.lbl_time)
        lay.addWidget(self.cmb_rate)
        lay.addWidget(self.lbl_diag)

        self.set_state("idle")

    # ---------------- 状态 ----------------

    def set_duration(self, dur: float) -> None:
        self._duration = max(0.0, dur)
        self._update_time_label(self._mode_pos())

    def set_state(self, mode: str) -> None:
        self._mode = mode
        playing = mode == "playing"
        self.btn_play.setText("⏸" if playing else "▶")
        self.btn_play.setProperty("state", "playing" if playing else "idle")
        self.btn_play.setStyle(self.btn_play.style())   # 刷新 QSS property
        self.btn_stop.setEnabled(mode in ("playing", "paused", "ended"))
        self.slider.setEnabled(bool(self._duration) and mode != "building")
        if mode in ("idle",):
            self.slider.setValue(0)
            self.lbl_diag.setText("")

    def set_diag(self, text: str) -> None:
        self.lbl_diag.setText(text)

    def _mode_pos(self) -> float:
        return self.slider.value() / 1000 * self._duration

    # ---------------- 进度 ----------------

    def on_progress(self, t: float) -> None:
        if not self._dragging:
            if self._duration > 0:
                self.slider.blockSignals(True)
                self.slider.setValue(int(t / self._duration * 1000))
                self.slider.blockSignals(False)
        self._update_time_label(t)

    def _on_moved(self, v: int) -> None:
        self._update_time_label(v / 1000 * self._duration)

    def _on_released(self) -> None:
        self._dragging = False
        t = self.slider.value() / 1000 * self._duration
        self.seekRequested.emit(t)

    def _update_time_label(self, t: float) -> None:
        self.lbl_time.setText(f"{t:,.2f} / {self._duration:,.2f} s")
