
{
  description = "USMS Development Environment Flake";

  inputs = {
    systems.url = "github:nix-systems/default";

    nixpkgs.url = "github:nixos/nixpkgs/nixpkgs-unstable";

    uv2nix = {
      url = "github:pyproject-nix/uv2nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = {
    self,
    systems,
    nixpkgs,
    uv2nix,
    ...
  }:
  let
    inherit (nixpkgs) lib;
    forEachSystem = f: nixpkgs.lib.genAttrs (import systems) (system: f { pkgs = import nixpkgs { inherit system; }; });
  in {
    devShells = forEachSystem (
      { pkgs }: {
        default =
        let
          # Use Python 3.12 from nixpkgs
          python = pkgs.python312;

        in pkgs.mkShellNoCC {
          packages = with pkgs; [
            # Set packages here
            git
            python
            uv

            # Set python packages here
            (python.withPackages (ps: with ps; [
              
            ]))
          ];

          env = {
            # Prevent uv from managing Python downloads
            #UV_PYTHON_DOWNLOADS = "never";

            # Force uv to use nixpkgs Python interpreter
            #UV_PYTHON = python.interpreter;

            # OPTIONAL: set username and password as environment variables here
            #USMS_USERNAME = "username";
            #USMS_PASSWORD = "password";
          }
          # IMPORTANT!
          # Fixes numpy and pandas
          // lib.optionalAttrs pkgs.stdenv.isLinux {
            # Python libraries often load native shared objects using dlopen(3).
            # Setting LD_LIBRARY_PATH makes the dynamic library loader aware of libraries without using RPATH for lookup.
            LD_LIBRARY_PATH = lib.makeLibraryPath pkgs.pythonManylinuxPackages.manylinux1;
          };
          # Additionally, use nix-ld by including the following in nixos config:
          # programs.nix-ld = {
          #   enable = true;
          #   libraries = options.programs.nix-ld.libraries.default;
          # };
          # Fixes ruff

          # Shell commands to run on activation
          shellHook = ''
            # Create and activate virtual environment
            uv venv
            source .venv/bin/activate
            
            # Install all project + dev dependencies
            uv sync --all-extras

            # Install the pre-commit hooks
            pre-commit install --install-hooks
          '';
          };

      }
    );
  };
}