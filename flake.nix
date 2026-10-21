{
  description = "context-efficiency-metrics: API-equivalent cost of Pi sessions by model, thinking effort and context size";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";

  outputs = { self, nixpkgs }:
    let
      # The script is plain Python 3 stdlib, so it runs wherever Nix and Pi run.
      systems = [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin" ];
      forAll = f: nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});
    in
    {
      # `nix run` starts meta.mainProgram of packages.default.
      packages = forAll (pkgs: {
        default = pkgs.stdenvNoCC.mkDerivation {
          pname = "context-efficiency-metrics";
          version = "0.1.0";
          dontUnpack = true;
          # python3 in buildInputs makes the fixup phase pin the script's shebang to the store.
          buildInputs = [ pkgs.python3 ];
          installPhase = "install -Dm755 ${./context-efficiency-metrics} $out/bin/context-efficiency-metrics";
          meta.mainProgram = "context-efficiency-metrics";
        };
      });
    };
}
