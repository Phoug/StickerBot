{
  description = "StickerBot development tools (Linux, CPython 3.14 and Node 22)";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { nixpkgs, ... }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" ];
    in {
      devShells = builtins.listToAttrs (map (system:
        let pkgs = nixpkgs.legacyPackages.${system};
        in {
          name = system;
          value.default = pkgs.mkShell {
            packages = [ pkgs.python314 pkgs.nodejs_22 pkgs.ffmpeg ];
            shellHook = ''
              export PIP_CACHE_DIR="$PWD/.cache/pip"
              export npm_config_cache="$PWD/.cache/npm"
              export PYTHONDONTWRITEBYTECODE=1
            '';
          };
        }) systems);
    };
}
