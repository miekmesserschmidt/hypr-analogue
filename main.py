from __future__ import annotations

import json
import math
import os
import signal
import subprocess
import sys
import threading
import tomllib
import importlib.metadata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")
gi.require_version("Rsvg", "2.0")

import cairo  # noqa: E402
import typer  # noqa: E402
from analogue_clock import AnalogueClock  # noqa: E402
from gi.repository import (  # noqa: E402
    Gdk,
    Gio,
    GLib,
    Gtk,
    Gtk4LayerShell as LayerShell,
    Rsvg,
)


# Namespace of the wlr-layer-shell surface. This is the name the clock shows
# up as in `hyprctl layers`, and what `layerrule`s can target.
LAYER_NAMESPACE = "hypr-analogue-clock"

APP_ID = "org.miek.hypr_analogue"
PROJECT_NAME = "hypr-analogue"

USER_CONFIG_DIR = Path.home() / ".config" / "hypr-analogue"
USER_CONFIG_PATH = USER_CONFIG_DIR / "config.toml"
USER_SVG_PATH = USER_CONFIG_DIR / "clock.svg"

# Built-in fallback config, matches example/hypr-analogue.toml.
BUILTIN_CONFIG: dict = {
    "window": {
        "x": 30,
        "y": 30,
        "w": 100,
        "h": 100,
        "click_through": True,
        "update_interval_seconds": 1,
    }
}


def _read_pyproject_version(path: Path) -> str | None:
    try:
        data = tomllib.loads(path.read_text())
    except (OSError, tomllib.TOMLDecodeError):
        return None
    project = data.get("project", {})
    if not isinstance(project, dict):
        return None
    version = project.get("version")
    if isinstance(version, str):
        return version
    return None


def get_version() -> str:
    env_version = os.environ.get("HYPR_ANALOGUE_VERSION")
    if env_version:
        return env_version
    try:
        return importlib.metadata.version(PROJECT_NAME)
    except importlib.metadata.PackageNotFoundError:
        pass
    return _read_pyproject_version(Path(__file__).with_name("pyproject.toml")) or "unknown"


def version_callback(value: bool) -> None:
    if value:
        typer.echo(get_version())
        raise typer.Exit()


def resolve_config(explicit: Optional[Path]) -> dict:
    """Resolve the config dict from CLI arg, user config dir, env, or builtin."""
    if explicit is not None:
        with explicit.open("rb") as f:
            return tomllib.load(f)
    if USER_CONFIG_PATH.is_file():
        with USER_CONFIG_PATH.open("rb") as f:
            return tomllib.load(f)
    env_path = os.environ.get("HYPR_ANALOGUE_DEFAULT_CONFIG")
    if env_path and Path(env_path).is_file():
        with Path(env_path).open("rb") as f:
            return tomllib.load(f)
    return BUILTIN_CONFIG


def resolve_svg(explicit: Optional[Path]) -> str:
    """Resolve the clock SVG content from CLI arg, user config dir, or env."""
    if explicit is not None:
        return explicit.read_text()
    if USER_SVG_PATH.is_file():
        return USER_SVG_PATH.read_text()
    env_path = os.environ.get("HYPR_ANALOGUE_DEFAULT_SVG")
    if env_path and Path(env_path).is_file():
        return Path(env_path).read_text()
    raise typer.BadParameter(
        "No SVG provided. Pass --svg, place one at "
        f"{USER_SVG_PATH}, or set HYPR_ANALOGUE_DEFAULT_SVG."
    )


@dataclass(frozen=True)
class CursorTransparency:
    """Settings for fading the clock as the cursor nears its centre."""

    enabled: bool = False
    opacity: float = 1.0
    inner_radius: float = 0.0
    outer_radius: float = 0.0
    polling_interval_seconds: float = 0.2

    def opacity_for_distance(self, distance: float) -> float:
        """Opacity for a cursor `distance` (px) from the clock centre.

        Beyond `outer_radius` the clock is fully opaque; within `inner_radius`
        it is at `opacity`; in between it scales linearly.
        """
        if distance >= self.outer_radius:
            return 1.0
        if distance <= self.inner_radius:
            return self.opacity
        span = self.outer_radius - self.inner_radius
        if span <= 0:
            return self.opacity
        # 0 at the inner edge, 1 at the outer edge.
        t = (distance - self.inner_radius) / span
        return self.opacity + t * (1.0 - self.opacity)


def hyprctl_json(*args: str) -> object | None:
    """Run `hyprctl <args> -j` and parse its JSON output (None on failure)."""
    try:
        result = subprocess.run(
            ["hyprctl", *args, "-j"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def get_cursor_pos() -> tuple[float, float] | None:
    """Return the global cursor position in layout pixels."""
    data = hyprctl_json("cursorpos")
    if not isinstance(data, dict):
        return None
    try:
        return float(data["x"]), float(data["y"])
    except (KeyError, TypeError, ValueError):
        return None


def find_layer_rect(namespace: str) -> tuple[float, float, float, float] | None:
    """Return (x, y, w, h) of our layer surface in global layout pixels.

    `hyprctl layers` reports surface coordinates relative to their monitor, so
    the monitor's layout offset is added to match `hyprctl cursorpos` (which is
    global).
    """
    data = hyprctl_json("layers")
    if not isinstance(data, dict):
        return None
    monitor_offsets = get_monitor_offsets()
    for monitor_name, monitor in data.items():
        if not isinstance(monitor, dict):
            continue
        levels = monitor.get("levels", {})
        if not isinstance(levels, dict):
            continue
        ox, oy = monitor_offsets.get(monitor_name, (0.0, 0.0))
        for surfaces in levels.values():
            for surface in surfaces:
                if surface.get("namespace") == namespace:
                    try:
                        return (
                            float(surface["x"]) + ox,
                            float(surface["y"]) + oy,
                            float(surface["w"]),
                            float(surface["h"]),
                        )
                    except (KeyError, TypeError, ValueError):
                        return None
    return None


def get_monitor_offsets() -> dict[str, tuple[float, float]]:
    """Map each monitor name to its (x, y) layout offset in global pixels."""
    data = hyprctl_json("monitors")
    offsets: dict[str, tuple[float, float]] = {}
    if not isinstance(data, list):
        return offsets
    for monitor in data:
        if not isinstance(monitor, dict):
            continue
        name = monitor.get("name")
        if name is None:
            continue
        try:
            offsets[name] = (float(monitor["x"]), float(monitor["y"]))
        except (KeyError, TypeError, ValueError):
            continue
    return offsets


def _apply_transparent_background() -> None:
    """Make GTK windows transparent so only the SVG's own alpha is visible."""
    display = Gdk.Display.get_default()
    if display is None:
        return
    provider = Gtk.CssProvider()
    css = "window { background: none; }"
    try:
        provider.load_from_string(css)  # GTK >= 4.12
    except (AttributeError, TypeError):
        provider.load_from_data(css.encode("utf-8"))
    Gtk.StyleContext.add_provider_for_display(
        display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )


class ClockApp(Gtk.Application):
    # Refresh the cached layer rectangle every N cursor polls (so the effect
    # survives the surface moving between monitors without querying the layer
    # geometry on every single poll).
    RECT_REFRESH_TICKS = 30

    def __init__(
        self,
        clock: AnalogueClock,
        x: int,
        y: int,
        w: int,
        h: int,
        click_through: bool,
        update_interval_seconds: float,
        cursor_transparency: CursorTransparency,
    ) -> None:
        super().__init__(
            application_id=APP_ID, flags=Gio.ApplicationFlags.NON_UNIQUE
        )
        self._clock = clock
        self._x = x
        self._y = y
        self._w = w
        self._h = h
        self._click_through = click_through
        self._interval = update_interval_seconds
        self._cursor_transparency = cursor_transparency
        self._handle: Optional[Rsvg.Handle] = None
        self._area: Optional[Gtk.DrawingArea] = None
        self._opacity: float = 1.0
        self._rect: Optional[tuple[float, float, float, float]] = None
        self._rect_age: int = 0
        self._poll_stop = threading.Event()
        self._poll_thread: Optional[threading.Thread] = None

    def do_activate(self) -> None:  # GObject vfunc
        _apply_transparent_background()

        window = Gtk.ApplicationWindow(application=self)
        window.set_decorated(False)

        # Turn the window into a wlr-layer-shell surface on the overlay layer
        # (always on top), named so it appears as its own Hyprland layer.
        LayerShell.init_for_window(window)
        LayerShell.set_namespace(window, LAYER_NAMESPACE)
        LayerShell.set_layer(window, LayerShell.Layer.OVERLAY)
        LayerShell.set_keyboard_mode(window, LayerShell.KeyboardMode.NONE)
        self._anchor(window)

        area = Gtk.DrawingArea()
        area.set_content_width(self._w)
        area.set_content_height(self._h)
        area.set_draw_func(self._draw, None)
        window.set_child(area)
        self._area = area

        if self._click_through:
            window.connect("realize", self._make_click_through)

        self._render_current()
        window.present()

        GLib.timeout_add(max(1, int(self._interval * 1000)), self._tick)

        if self._cursor_transparency.enabled:
            # Poll hyprctl on a background thread: the subprocess calls are
            # blocking and would otherwise stall the GLib main loop (starving
            # the per-second clock redraw). Opacity changes are marshalled
            # back to the main thread via GLib.idle_add.
            self._poll_thread = threading.Thread(
                target=self._poll_cursor_loop, daemon=True
            )
            self._poll_thread.start()
            self.connect("shutdown", lambda _app: self._poll_stop.set())

    def _anchor(self, window: Gtk.Window) -> None:
        """Anchor to an edge per sign of x/y; negative wraps to the far edge."""
        if self._x >= 0:
            LayerShell.set_anchor(window, LayerShell.Edge.LEFT, True)
            LayerShell.set_margin(window, LayerShell.Edge.LEFT, self._x)
        else:
            LayerShell.set_anchor(window, LayerShell.Edge.RIGHT, True)
            LayerShell.set_margin(window, LayerShell.Edge.RIGHT, -self._x)
        if self._y >= 0:
            LayerShell.set_anchor(window, LayerShell.Edge.TOP, True)
            LayerShell.set_margin(window, LayerShell.Edge.TOP, self._y)
        else:
            LayerShell.set_anchor(window, LayerShell.Edge.BOTTOM, True)
            LayerShell.set_margin(window, LayerShell.Edge.BOTTOM, -self._y)

    def _make_click_through(self, window: Gtk.Window) -> None:
        """Give the surface an empty input region so clicks pass through."""
        surface = window.get_surface()
        if surface is not None:
            surface.set_input_region(cairo.Region())

    def _render_current(self) -> None:
        svg = self._clock.generate(datetime.now().time())
        stream = Gio.MemoryInputStream.new_from_bytes(
            GLib.Bytes.new(svg.encode("utf-8"))
        )
        try:
            self._handle = Rsvg.Handle.new_from_stream_sync(
                stream, None, Rsvg.HandleFlags.FLAGS_NONE, None
            )
        except GLib.Error:
            self._handle = None
        if self._area is not None:
            self._area.queue_draw()

    def _tick(self) -> bool:
        self._render_current()
        return GLib.SOURCE_CONTINUE

    def _poll_cursor_loop(self) -> None:
        """Background thread: poll hyprctl and push opacity to the main loop."""
        while not self._poll_stop.is_set():
            # Refresh the cached layer rectangle periodically (and until
            # found), so the effect survives the surface moving monitors.
            if self._rect is None or self._rect_age >= self.RECT_REFRESH_TICKS:
                self._rect = find_layer_rect(LAYER_NAMESPACE)
                self._rect_age = 0
            else:
                self._rect_age += 1

            opacity = 1.0
            cursor = get_cursor_pos()
            if self._rect is not None and cursor is not None:
                rx, ry, rw, rh = self._rect
                cx, cy = rx + rw / 2.0, ry + rh / 2.0
                distance = math.hypot(cursor[0] - cx, cursor[1] - cy)
                opacity = self._cursor_transparency.opacity_for_distance(
                    distance
                )

            GLib.idle_add(self._set_opacity, opacity)
            self._poll_stop.wait(
                max(0.01, self._cursor_transparency.polling_interval_seconds)
            )

    def _set_opacity(self, opacity: float) -> bool:
        """Apply a new opacity on the main thread, redrawing if it changed."""
        if opacity != self._opacity:
            self._opacity = opacity
            if self._area is not None:
                self._area.queue_draw()
        return GLib.SOURCE_REMOVE

    def _draw(
        self,
        area: Gtk.DrawingArea,
        cr: cairo.Context,
        width: int,
        height: int,
        user_data: object,
    ) -> None:
        handle = self._handle
        if handle is None or width <= 0 or height <= 0:
            return

        has_size, sw, sh = handle.get_intrinsic_size_in_pixels()
        if not has_size or sw <= 0 or sh <= 0:
            sw, sh = float(width), float(height)

        scale = min(width / sw, height / sh)
        dw, dh = sw * scale, sh * scale
        dx = (width - dw) / 2
        dy = (height - dh) / 2

        viewport = Rsvg.Rectangle()
        viewport.x = dx
        viewport.y = dy
        viewport.width = dw
        viewport.height = dh

        if self._opacity >= 1.0:
            handle.render_document(cr, viewport)
            return

        # Composite the clock through a temporary group at the reduced
        # opacity. This multiplies into the SVG's own alpha in the same cairo
        # buffer that the compositor already honours for SVG transparency, so
        # it is the only reliable way to fade a layer surface (Hyprland has no
        # layer-opacity rule, and GTK's widget set_opacity may be ignored when
        # the surface advertises an opaque region).
        cr.push_group()
        handle.render_document(cr, viewport)
        cr.pop_group_to_source()
        cr.paint_with_alpha(self._opacity)


def run(
    config: Optional[Path] = typer.Option(
        None,
        "--config",
        "-c",
        exists=True,
        dir_okay=False,
        readable=True,
        help=(
            "Path to TOML config file. Defaults to "
            "~/.config/hypr-analogue/config.toml, then a built-in fallback."
        ),
    ),
    svg: Optional[Path] = typer.Option(
        None,
        "--svg",
        "-s",
        exists=True,
        dir_okay=False,
        readable=True,
        help=(
            "Path to clock face SVG file. Defaults to "
            "~/.config/hypr-analogue/clock.svg, then the SVG installed with "
            "this package."
        ),
    ),
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        callback=version_callback,
        is_eager=True,
        help="Show the version and exit.",
    ),
) -> None:
    """Display an always-on-top analogue clock on its own Hyprland layer."""
    cfg = resolve_config(config)
    svg_text = resolve_svg(svg)

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

    ct_cfg = cfg.get("cursor-transparency", {})
    cursor_transparency = CursorTransparency(
        enabled=bool(ct_cfg.get("enabled", False)),
        opacity=float(ct_cfg.get("opacity", 1.0)),
        inner_radius=float(ct_cfg.get("inner_radius", 0.0)),
        outer_radius=float(ct_cfg.get("outer_radius", 0.0)),
        polling_interval_seconds=float(
            ct_cfg.get("polling_interval_seconds", 0.2)
        ),
    )

    clock = AnalogueClock(svg=svg_text)

    # Restore the default SIGINT handler so Ctrl+C in the terminal kills the
    # app even while the GLib main loop is idle.
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    app = ClockApp(
        clock, x, y, w, h, click_through, interval, cursor_transparency
    )
    sys.exit(app.run(None))


def main() -> None:
    typer.run(run)


if __name__ == "__main__":
    main()
