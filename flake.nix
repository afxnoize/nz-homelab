{
  description = "Host service management";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    disko = {
      url = "github:nix-community/disko";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    sops-nix = {
      url = "github:Mic92/sops-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    treefmt-nix = {
      url = "github:numtide/treefmt-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    quadlet-nix = {
      url = "github:SEIAROTg/quadlet-nix";
    };
  };

  outputs =
    {
      self,
      nixpkgs,
      disko,
      sops-nix,
      treefmt-nix,
      quadlet-nix,
    }:
    let
      pkgs = nixpkgs.legacyPackages.x86_64-linux;
      # nixpkgs installs the B2 CLI as backblaze-b2; expose it only as b2,
      # the name the upstream docs and the PreToolUse hook patterns expect.
      b2 = pkgs.runCommand "b2" { } ''
        mkdir -p $out/bin
        ln -s ${pkgs.backblaze-b2}/bin/backblaze-b2 $out/bin/b2
      '';
    in
    {
      devShells.x86_64-linux.default = pkgs.mkShell {
        packages = with pkgs; [
          kopia
          sops
          age
          yq-go
          just
          gomplate
          lefthook
          b2
        ];
      };

      nixosConfigurations.oci = nixpkgs.lib.nixosSystem {
        system = "aarch64-linux";
        modules = [
          disko.nixosModules.disko
          sops-nix.nixosModules.sops
          quadlet-nix.nixosModules.quadlet
          ./hosts/oci/configuration.nix
        ];
      };

      formatter.x86_64-linux = (treefmt-nix.lib.evalModule pkgs ./treefmt.nix).config.build.wrapper;

      packages.x86_64-linux.default = pkgs.kopia;
    };
}
