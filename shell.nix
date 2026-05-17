{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  packages = with pkgs; [
    uv
    python314
  ];

  buildInputs = with pkgs; [
    glib
    dbus
    fontconfig
    freetype
    libxkbcommon
    xorg.libX11
    xorg.libXext
    xorg.libXrender
    xorg.libxcb
    xorg.xcbutil
    xorg.xcbutilimage
    xorg.xcbutilkeysyms
    xorg.xcbutilrenderutil
    xorg.xcbutilwm
    xorg.xcbutilcursor
    wayland
    libGL
    zlib
    stdenv.cc.cc.lib
  ];

  shellHook = ''
    export LD_LIBRARY_PATH="${pkgs.lib.makeLibraryPath (with pkgs; [
      glib
      dbus
      fontconfig
      freetype
      libxkbcommon
      xorg.libX11
      xorg.libXext
      xorg.libXrender
      xorg.libxcb
      xorg.xcbutil
      xorg.xcbutilimage
      xorg.xcbutilkeysyms
      xorg.xcbutilrenderutil
      xorg.xcbutilwm
      xorg.xcbutilcursor
      wayland
      libGL
      zlib
      stdenv.cc.cc.lib
    ])}:$LD_LIBRARY_PATH"

    # Let Qt find the Wayland platform plugin when available.
    export QT_QPA_PLATFORM="''${QT_QPA_PLATFORM:-wayland;xcb}"
  '';
}
