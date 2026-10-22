{
  description = "context-efficiency-metrics: API-equivalent cost of Pi sessions by model, thinking effort and context size";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";

  outputs = { self, nixpkgs }:
    let
      # Plain Python 3 stdlib, so it runs wherever Nix and Pi run.
      systems = [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin" ];
      forAll = f: nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});
      fs = nixpkgs.lib.fileset;
      isTest = f: nixpkgs.lib.hasPrefix "test_" f.name;
      # Only runtime files, so README or test edits do not rebuild the package.
      runtime = fs.toSource {
        root = ./.;
        fileset = fs.unions [
          ./context-efficiency-metrics
          (fs.fileFilter (f: f.hasExt "py" && !isTest f) ./.)
        ];
      };
      tests = fs.toSource { root = ./.; fileset = fs.fileFilter (f: f.hasExt "py") ./.; };
    in
    {
      # `nix run` starts meta.mainProgram of packages.default.
      packages = forAll (pkgs: {
        default = pkgs.stdenvNoCC.mkDerivation {
          pname = "context-efficiency-metrics";
          version = "0.2.0";
          src = runtime;
          # python3 in buildInputs makes the fixup phase pin the script's shebang to the store.
          buildInputs = [ pkgs.python3 ];
          # The entry script imports its sibling modules; Python resolves the bin symlink
          # to libexec, so sys.path[0] is the module directory.
          installPhase = ''
            mkdir -p $out/libexec/context-efficiency-metrics $out/bin
            cp -r . $out/libexec/context-efficiency-metrics/
            ln -s ../libexec/context-efficiency-metrics/context-efficiency-metrics $out/bin/
          '';
          meta.mainProgram = "context-efficiency-metrics";
        };
      });

      checks = forAll (pkgs: {
        unittest = pkgs.runCommand "context-efficiency-metrics-tests" { } ''
          cd ${tests} && ${pkgs.python3}/bin/python3 -B -m unittest -q && touch $out
        '';
      });
    };
}
