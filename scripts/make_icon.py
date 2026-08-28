"""生成应用图标 assets/icon.ico(PySide6 绘制,无需额外依赖)。"""
import sys
from pathlib import Path

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication


def make_icon(size: int = 256) -> QImage:
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)

    # 深色圆角底
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#16181d"))
    p.drawRoundedRect(8, 8, size - 16, size - 16, 48, 48)
    p.setPen(QPen(QColor("#2b2f38"), 4))
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(10, 10, size - 20, size - 20, 46, 46)

    # 示波器正弦波
    import math
    pen = QPen(QColor("#4da3ff"), size * 0.035)
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    pts = []
    cy = size * 0.52
    amp = size * 0.16
    for i in range(0, 101):
        x = size * 0.14 + (size * 0.72) * i / 100
        y = cy - amp * math.sin(2 * math.pi * 2 * i / 100)
        pts.append(QPoint(int(x), int(y)))
    for a, b in zip(pts, pts[1:]):
        p.drawLine(a, b)

    # CAN 文本
    p.setPen(QColor("#5ad47a"))
    f = QFont("Arial", int(size * 0.16))
    f.setBold(True)
    p.setFont(f)
    p.drawText(img.rect(), Qt.AlignBottom | Qt.AlignHCenter, "CAN")
    p.end()
    return img


def main():
    app = QApplication(sys.argv)
    out = Path(__file__).resolve().parent.parent / "assets" / "icon.ico"
    out.parent.mkdir(parents=True, exist_ok=True)
    img = make_icon(256)
    if not img.save(str(out)):
        raise SystemExit("ico 保存失败")
    print(f"[OK] {out} ({out.stat().st_size} B)")


if __name__ == "__main__":
    main()
