"""벡터 원본에서 프로그램용 PNG·ICO를 생성한다."""

from __future__ import annotations

from pathlib import Path

from PIL import Image
from PySide6.QtCore import QByteArray, QSize
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets" / "arterial-analysis-icon-simple.svg"


def main() -> None:
    QApplication.instance() or QApplication([])
    renderer = QSvgRenderer(QByteArray(SOURCE.read_bytes()))
    if not renderer.isValid():
        raise ValueError(f"SVG를 읽을 수 없습니다: {SOURCE}")
    image = QImage(QSize(1024, 1024), QImage.Format_RGBA8888)
    image.fill(0)
    painter = QPainter(image)
    renderer.render(painter)
    painter.end()
    canvas = Image.frombytes("RGBA", (1024, 1024), bytes(image.constBits()))
    canvas.save(ROOT / "assets" / "arterial-analysis-icon.png", "PNG", optimize=True)
    canvas.save(
        ROOT / "assets" / "arterial-analysis-icon.ico",
        format="ICO",
        sizes=[(16, 16), (20, 20), (24, 24), (32, 32), (40, 40), (48, 48), (64, 64), (128, 128), (256, 256)],
    )


if __name__ == "__main__":
    main()
