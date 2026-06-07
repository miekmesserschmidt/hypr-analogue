# hypr-analogue

Always-on-top analogue clock for Hyprland.

The app runs as a transparent Qt window and is positioned with `hyprctl`.
The the app uses the [py-analogue-clock](https://github.com/miekmesserschmidt/py-analogue-clock)
library to render a user defined svg clock face.


![hypr-analogue screenshot](docs/2026-05-17-163604_hyprshot.png)

## Install with Nix Flakes

### Run without installing

From this repository:

```bash
nix run .
```

From GitHub directly:

```bash
nix run github:miekmesserschmidt/hypr-analogue
```

### Install into your profile

From this repository:

```bash
nix profile install .
```

From GitHub directly:

```bash
nix profile install github:miekmesserschmidt/hypr-analogue
```

This installs a `hypr-analogue` command in your profile.

## Basic usage

```bash
hypr-analogue
```

By default, the wrapper uses:

- built-in example config as fallback
- built-in SVG from `example/light2.svg` as fallback

You can override both at runtime:

```bash
hypr-analogue --config /path/to/config.toml --svg /path/to/clockface.svg
```

## Configure window position and size

Create `~/.config/hypr-analogue/config.toml`:

```toml
[window]
x = -150
y = -430
w = 100
h = 100

click_through = true
update_interval_seconds = 1
```

Meaning of the position fields:

- `x`, `y`: margin of the clock from the anchored monitor edge, in pixels
- `w`, `h`: clock size in pixels
- a non-negative `x` anchors to the left edge; a negative `x` anchors to the
  right edge with margin `-x`. `y` works the same way for the top/bottom edges.

For example, `x = -150` anchors the clock to the right edge of the monitor,
150 pixels in from that edge.

## Fade the clock when the cursor is near

Optionally, the clock can fade out as the pointer approaches its centre (handy
when it sits on top of something you want to see). Add a
`[cursor-transparency]` section:

```toml
[cursor-transparency]
enabled = true
polling_interval_seconds = 0.2   # how often to poll the cursor position
opacity = 0.1        # opacity when the cursor is at/within inner_radius
inner_radius = 50    # px: at or below this distance, opacity = `opacity`
outer_radius = 400   # px: at or beyond this distance, fully opaque
```

Behaviour:

- cursor farther than `outer_radius` from the clock centre: fully opaque
  (no change).
- cursor closer than `inner_radius`: opacity is `opacity`.
- in between: opacity scales linearly from `1.0` down to `opacity`.

Distances are measured from the live cursor position to the centre of the
clock surface (queried via `hyprctl cursorpos` / `hyprctl layers`). The cursor
is polled every `polling_interval_seconds` on a background thread, so it never
blocks the per-second clock redraw.

## Set the clockface SVG

Place your SVG at:

```text
~/.config/hypr-analogue/clock.svg
```

or pass a specific file when launching:

```bash
hypr-analogue --svg /path/to/clockface.svg
```

Useful bundled SVG examples are in `example/`:

- `example/light.svg`
- `example/light2.svg`
- `example/test_clock.svg`

## Config/SVG resolution order

Config is loaded in this order:

1. `--config`
2. `~/.config/hypr-analogue/config.toml`
3. `HYPR_ANALOGUE_DEFAULT_CONFIG`
4. built-in fallback config

SVG is loaded in this order:

1. `--svg`
2. `~/.config/hypr-analogue/clock.svg`
3. `HYPR_ANALOGUE_DEFAULT_SVG`

## Notes

- Requires Hyprland (or another `wlr-layer-shell` compositor).
- The clock runs as its own `wlr-layer-shell` surface on the overlay layer,
  with the namespace `hypr-analogue-clock`. It therefore appears as its own
  Hyprland layer (see `hyprctl layers`), has no window border, and is not
  affected by inactive-window opacity/blur rules — the only transparency that
  shows is the SVG's own alpha channel.
- `click_through = true` gives the surface an empty input region, so pointer
  events pass through to whatever is below it.
