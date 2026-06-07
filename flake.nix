{
  description = "Always-on-top analogue clock for Hyprland";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
    py-analogue-clock-src = {
      url = "github:miekmesserschmidt/py-analogue-clock";
      flake = false;
    };
  };

  outputs =
    { self
    , nixpkgs
    , flake-utils
    , py-analogue-clock-src
    }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        python = pkgs.python314 or pkgs.python313 or pkgs.python3;
        ps = python.pkgs;

        py-analogue-clock = ps.buildPythonPackage {
          pname = "py-analogue-clock";
          version = "0.4.0";
          src = py-analogue-clock-src;
          format = "pyproject";
          # Upstream pyproject.toml omits [build-system]; inject one so nix
          # doesn't fall back to the unavailable setuptools legacy backend.
          postPatch = ''
            cat >> pyproject.toml <<'EOF'

            [build-system]
            requires = ["setuptools>=61", "wheel"]
            build-backend = "setuptools.build_meta"

            [tool.setuptools.packages.find]
            include = ["analogue_clock*"]
            EOF
          '';
          nativeBuildInputs = [ ps.setuptools ps.wheel ];
          propagatedBuildInputs = [ ps.svgwrite ps.typer ];
          doCheck = false;
          pythonImportsCheck = [ "analogue_clock" ];
        };

        pythonEnv = python.withPackages (p: [
          p.pygobject3
          p.pycairo
          p.typer
          py-analogue-clock
        ]);

        # Runtime GObject-introspection stack: GTK4, the wlr-layer-shell
        # binding and librsvg (for SVG rendering via Rsvg).
        giDeps = [
          pkgs.gtk4
          pkgs.gtk4-layer-shell
          pkgs.librsvg
          pkgs.glib
          pkgs.gobject-introspection
        ];

        hypr-analogue = pkgs.stdenv.mkDerivation {
          pname = "hypr-analogue";
          version = "0.1.0";
          src = ./.;

          nativeBuildInputs = [
            pkgs.makeWrapper
            pkgs.wrapGAppsHook4
            pkgs.gobject-introspection
          ];

          buildInputs = [
            pythonEnv
          ] ++ giDeps;

          dontConfigure = true;
          dontBuild = true;

          # We wrap the launcher ourselves below; let wrapGAppsHook4 only
          # collect the GApps wrapper args (GI_TYPELIB_PATH, GSettings, etc.).
          dontWrapGApps = true;

          installPhase = ''
            runHook preInstall

            mkdir -p $out/share/hypr-analogue $out/bin
            install -Dm644 main.py $out/share/hypr-analogue/main.py
            cp -r example $out/share/hypr-analogue/

            makeWrapper ${pythonEnv}/bin/python $out/bin/hypr-analogue \
              "''${gappsWrapperArgs[@]}" \
              --add-flags "$out/share/hypr-analogue/main.py" \
              --set-default HYPR_ANALOGUE_DEFAULT_CONFIG \
                "$out/share/hypr-analogue/example/hypr-analogue.toml" \
              --set-default HYPR_ANALOGUE_DEFAULT_SVG \
                "$out/share/hypr-analogue/example/light2.svg" \
              --prefix LD_PRELOAD : \
                "${pkgs.gtk4-layer-shell}/lib/libgtk4-layer-shell.so"

            runHook postInstall
          '';

          meta = with pkgs.lib; {
            description = "Always-on-top analogue clock for Hyprland";
            homepage = "https://github.com/miekmesserschmidt/hypr-analogue";
            license = licenses.mit;
            platforms = platforms.linux;
            mainProgram = "hypr-analogue";
          };
        };
      in
      {
        packages.default = hypr-analogue;
        packages.hypr-analogue = hypr-analogue;

        apps.default = {
          type = "app";
          program = "${hypr-analogue}/bin/hypr-analogue";
        };

        devShells.default = pkgs.mkShell {
          packages = [
            pythonEnv
            pkgs.uv
            # Only needed if you build pycairo/pygobject from source via uv;
            # the Nix pythonEnv above already ships them prebuilt.
            pkgs.pkg-config
            pkgs.cairo
          ] ++ giDeps;
          shellHook = ''
            export GI_TYPELIB_PATH="${pkgs.lib.makeSearchPath "lib/girepository-1.0" giDeps}''${GI_TYPELIB_PATH:+:$GI_TYPELIB_PATH}"
            export LD_LIBRARY_PATH="${pkgs.lib.makeLibraryPath (giDeps ++ [ pkgs.cairo ])}''${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
            # gtk4-layer-shell must be loaded before libwayland-client, so
            # preload it for the layer-shell surface to initialise correctly.
            export LD_PRELOAD="${pkgs.gtk4-layer-shell}/lib/libgtk4-layer-shell.so''${LD_PRELOAD:+:$LD_PRELOAD}"
            echo "hypr-analogue dev shell: run with the Nix Python directly:" >&2
            echo "  python main.py -c example/hypr-analogue.toml -s example/light2.svg" >&2
            echo "(avoid 'uv run' here - it rebuilds pygobject/pycairo from source)" >&2
          '';
        };
      });
}
