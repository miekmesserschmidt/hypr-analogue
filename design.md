hypr-analogue
==========

This app displays an analogue clock on hyprland.

The main.py should be a typer app for handling config parameters. 
The app should take an argument for a config toml file.
The app should take an argument for a clock svg file.

You may choose any appropriate python windowing toolkit. Choose the simplest that works.


The config toml defines the window position and width.
The clock svg is to be used in https://github.com/miekmesserschmidt/py-analogue-clock to render an svg of the clock face.

The app should display an always on top window, and render the clock and display the clock, respecting transparency of the svg. The svg should scale (maintaining aspect ratio) to the window size.

The window should respect the click_through variable in the config toml.

The app should update the svg according to the update_interval_seconds variable in the config toml.




