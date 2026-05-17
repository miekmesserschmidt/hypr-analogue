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
          p.pyqt6
          p.typer
          py-analogue-clock
        ]);

        hypr-analogue = pkgs.stdenv.mkDerivation {
          pname = "hypr-analogue";
          version = "0.1.0";
          src = ./.;

          nativeBuildInputs = [
            pkgs.makeWrapper
            pkgs.qt6.wrapQtAppsHook
          ];

          buildInputs = [
            pythonEnv
            pkgs.qt6.qtbase
            pkgs.qt6.qtsvg
          ];

          dontConfigure = true;
          dontBuild = true;

          installPhase = ''
            runHook preInstall

            mkdir -p $out/share/hypr-analogue $out/bin
            install -Dm644 main.py $out/share/hypr-analogue/main.py
            cp -r example $out/share/hypr-analogue/

            makeWrapper ${pythonEnv}/bin/python $out/bin/hypr-analogue \
              --add-flags "$out/share/hypr-analogue/main.py" \
              --set-default HYPR_ANALOGUE_DEFAULT_CONFIG \
                "$out/share/hypr-analogue/example/hypr-analogue.toml" \
              --set-default HYPR_ANALOGUE_DEFAULT_SVG \
                "$out/share/hypr-analogue/example/light2.svg" \
              --set-default QT_QPA_PLATFORM xcb

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
          packages = [ pythonEnv pkgs.uv ];
          shellHook = ''
            export QT_QPA_PLATFORM=xcb
          '';
        };
      });
}
