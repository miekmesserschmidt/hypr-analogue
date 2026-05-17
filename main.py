from __future__ import annotations

import sys
import tomllib
from datetime import datetime
from pathlib import Path

import typer
from analogue_clock import AnalogueClock
from PyQt6.QtCore import QByteArray, QRectF, Qt, QTimer
from PyQt6.QtGui import QPainter
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QApplication, QWidget


class ClockWindow(QWidget):
    def __init__(
        self,
        clock: AnalogueClock,
        x: int,
        y: int,
        w: int,
        h: int,
        click_through: bool,
        update_interval_seconds: float,
    ) -> None:
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        if click_through:
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self.setGeometry(x, y, w, h)
        self.setFixedSize(w, h)

        self._clock = clock
        self._renderer = QSvgRenderer(self)
        self._refresh()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(max(1, int(update_interval_seconds * 1000)))

    def _refresh(self) -> None:
        svg = self._clock.generate(datetime.now().time())
        self._renderer.load(QByteArray(svg.encode("utf-8")))
        self.update()

    def paintEvent(self, event) -> None:  # noqa: ARG002
        if not self._renderer.isValid():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        size = self._renderer.defaultSize()
        sw, sh = size.width(), size.height()
        if sw <= 0 or sh <= 0:
            return

        ww, wh = self.width(), self.height()
        scale = min(ww / sw, wh / sh)
        dw, dh = sw * scale, sh * scale
        dx = (ww - dw) / 2
        dy = (wh - dh) / 2
        self._renderer.render(painter, QRectF(dx, dy, dw, dh))


def run(
    config: Path = typer.Argument(
        ..., exists=True, dir_okay=False, readable=True, help="Path to TOML config file."
    ),
    svg: Path = typer.Argument(
        ..., exists=True, dir_okay=False, readable=True, help="Path to clock face SVG file."
    ),
) -> None:
    """Display an always-on-top analogue clock on Hyprland."""
    with config.open("rb") as f:
        cfg = tomllib.load(f)

    window_cfg = cfg.get("window", {})
    x = int(window_cfg.get("x", 0))
    y = int(window_cfg.get("y", 0))
    w = int(window_cfg.get("w", 200))
    h = int(window_cfg.get("h", 200))
    click_through = bool(
        window_cfg.get("click_through", cfg.get("click_through", False))
    )
    interval = float(
        window_cfg.get(
            "update_interval_seconds",
            cfg.get("update_interval_seconds", 1.0),
        )
    )

    clock = AnalogueClock(svg=svg.read_text())

    qt_app = QApplication(sys.argv[:1])
    window = ClockWindow(clock, x, y, w, h, click_through, interval)
    window.show()
    sys.exit(qt_app.exec())


def main() -> None:
    typer.run(run)


if __name__ == "__main__":
    main()
