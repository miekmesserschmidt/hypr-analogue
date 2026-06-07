hypr-analogue
==========

This app displays an analogue clock on hyprland.

The main.py should be a typer app (already installed) for handling config parameters. 
The app should take an argument for a config toml file.
The app should take an argument for a clock svg file.

You may choose any appropriate python windowing toolkit. Choose the simplest that works.

The clock is rendered as a `wlr-layer-shell` surface (namespace
`hypr-analogue-clock`) on the overlay layer, using GTK4 + gtk4-layer-shell via
PyGObject, with the SVG drawn through librsvg (Rsvg). This makes it a real
Hyprland layer: no window border, and unaffected by inactive-window
opacity/blur rules, so only the SVG's own alpha is shown.


The config toml defines the window position and width.
The clock svg is to be used in https://github.com/miekmesserschmidt/py-analogue-clock  (already installed) to render an svg of the clock face.

The app should display an always on top window, and render the clock and display the clock, respecting transparency of the svg. The svg should scale (maintaining aspect ratio) to the window size.

The window should respect the click_through variable in the config toml.

The app should update the svg according to the update_interval_seconds variable in the config toml.


transparency on hover over
-----------------------
if enabled then the clock should turn transparent depending on how close the cursor is to the center of the clock.

if the cursor is outside of the outer radius, then there should be no change to the window opacity.

as the cursor gets closer, between the outer-radius and the inner radius, then the window opacity should scale linearly from 100% opacity to the given opacity (quite transparent).

```
[cursor-transparency]
enabled = true
polling_interval_seconds = 0.2 # how often to poll the cursor position
opacity = 0.1 # 0.0 is fully transparent, 1.0 is fully opaque
inner_radius = 50 # if the cursor is within this radius, the clock will have opacity given
outer_radius = 400 # if the cursor is further than this radius, the clock will be fully opaque
```

Implementation notes:

- Hyprland 0.55.2 has no way to set a layer surface's opacity (`hyprctl
  setprop` targets windows/clients, not layers; there is no `alpha`
  `layerrule`). So the fade is rendered client-side: the clock SVG is
  composited with `cairo`'s `paint_with_alpha`, multiplying into the SVG's own
  alpha in the same buffer the compositor honours for transparency.
- The cursor position and clock-centre are read from `hyprctl cursorpos` and
  `hyprctl layers` (offset by the monitor's layout position). These blocking
  `hyprctl` calls run on a background thread polled every
  `polling_interval_seconds`; computed opacity is marshalled back to the GTK
  main loop, so cursor polling never stalls the per-second clock redraw.