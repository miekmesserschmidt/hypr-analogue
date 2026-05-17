# hypr-analogue

Always-on-top analogue clock for Hyprland.

The app runs as a tiny transparent Qt window and is positioned with `hyprctl`.

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

- `x`, `y`: window top-left position in logical pixels
- `w`, `h`: window size in pixels
- negative `x`/`y` values are resolved against the focused monitor size

For example, `x = -150` means the effective x-position is `monitor_width - 150`.

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

- Requires Hyprland (`hyprctl` must be available).
- The app forces `QT_QPA_PLATFORM=xcb` for XWayland behavior used by positioning/click-through logic.
