{ pkgs ? import <nixpkgs> {} }:

let
  giDeps = with pkgs; [
    gtk4
    gtk4-layer-shell
    librsvg
    glib
    gobject-introspection
  ];
in
pkgs.mkShell {
  packages = with pkgs; [
    uv
    python314
    # Needed so uv/meson can build the pycairo and pygobject C extensions
    # against the Nix cairo / glib / gobject-introspection libraries.
    pkg-config
  ] ++ giDeps;

  buildInputs = with pkgs; [
    cairo
    pango
    gdk-pixbuf
    harfbuzz
    fontconfig
    freetype
    wayland
    libxkbcommon
    libGL
    zlib
    stdenv.cc.cc.lib
  ] ++ giDeps;

  shellHook = ''
    export LD_LIBRARY_PATH="${pkgs.lib.makeLibraryPath (with pkgs; [
      cairo
      pango
      gdk-pixbuf
      harfbuzz
      fontconfig
      freetype
      wayland
      libxkbcommon
      libGL
      zlib
      stdenv.cc.cc.lib
    ] ++ giDeps)}:$LD_LIBRARY_PATH"

    # Make the GTK4, layer-shell and Rsvg typelibs discoverable by PyGObject.
    export GI_TYPELIB_PATH="${pkgs.lib.makeSearchPath "lib/girepository-1.0" giDeps}''${GI_TYPELIB_PATH:+:$GI_TYPELIB_PATH}"

    # gtk4-layer-shell must be loaded before libwayland-client; preload it so
    # the layer-shell surface initialises correctly.
    export LD_PRELOAD="${pkgs.gtk4-layer-shell}/lib/libgtk4-layer-shell.so''${LD_PRELOAD:+:$LD_PRELOAD}"
  '';
}
