from __future__ import annotations

import json
import os
import subprocess
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


WM_CLASS = "hypr-analogue"


def hyprctl(*args: str) -> str:
    """Run hyprctl with the given args, returning stdout (empty on failure)."""
    try:
        result = subprocess.run(
            ["hyprctl", *args],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout
    except FileNotFoundError:
        return ""


def hypr_batch(commands: list[str]) -> None:
    if not commands:
        return
    payload = ";".join(f"dispatch {c}" if not c.startswith(("dispatch ", "keyword ", "setprop ")) else c for c in commands)
    hyprctl("--batch", payload)


def find_window_address(pid: int) -> str | None:
    out = hyprctl("clients", "-j")
    if not out:
        return None
    try:
        clients = json.loads(out)
    except json.JSONDecodeError:
        return None
    for c in clients:
        if c.get("pid") == pid:
            return c.get("address")
    return None


def apply_hyprland_rules(
    x: int,
    y: int,
    w: int,
    h: int,
    click_through: bool,
    attempts: int = 20,
    delay_ms: int = 100,
) -> None:
    """Locate our just-mapped window via PID and apply float/pin/move/size."""
    pid = os.getpid()

    def try_apply(remaining: int) -> None:
        addr = find_window_address(pid)
        if not addr:
            if remaining > 0:
                QTimer.singleShot(delay_ms, lambda: try_apply(remaining - 1))
            return

        ref = f"address:{addr}"
        cmds = [
            f"dispatch setfloating {ref}",
            f"dispatch resizewindowpixel exact {w} {h},{ref}",
            f"dispatch movewindowpixel exact {x} {y},{ref}",
            f"dispatch pin {ref}",
        ]
        if click_through:
            # nofocus prevents the window from ever taking keyboard focus;
            # combined with Qt's WA_TransparentForMouseEvents (XShape input
            # region) this gives true click-through under XWayland.
            cmds.append(f"setprop {ref} nofocus 1")
        hyprctl("--batch", ";".join(cmds))

    QTimer.singleShot(delay_ms, lambda: try_apply(attempts))


class ClockWindow(QWidget):
    def __init__(
        self,
        clock: AnalogueClock,
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

        self.resize(w, h)
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

    # Force XWayland under Hyprland: needed for absolute positioning via
    # hyprctl movewindowpixel and for click-through via XShape.
    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")

    qt_app = QApplication(sys.argv[:1])
    qt_app.setApplicationName(WM_CLASS)
    qt_app.setDesktopFileName(WM_CLASS)

    window = ClockWindow(clock, w, h, click_through, interval)
    window.setWindowTitle(WM_CLASS)
    window.setProperty("_q_styleSheetWindowClass", WM_CLASS)
    window.show()

    apply_hyprland_rules(x, y, w, h, click_through)

    sys.exit(qt_app.exec())


def main() -> None:
    typer.run(run)


if __name__ == "__main__":
    main()
