from __future__ import annotations

import os
import signal
import sys
import tomllib
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
        self._handle: Optional[Rsvg.Handle] = None
        self._area: Optional[Gtk.DrawingArea] = None

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
        handle.render_document(cr, viewport)


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

    clock = AnalogueClock(svg=svg_text)

    # Restore the default SIGINT handler so Ctrl+C in the terminal kills the
    # app even while the GLib main loop is idle.
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    app = ClockApp(clock, x, y, w, h, click_through, interval)
    sys.exit(app.run(None))


def main() -> None:
    typer.run(run)


if __name__ == "__main__":
    main()
