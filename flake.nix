{
  description = "Python dev environment for ACR122U NFC reader";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };

  outputs = { self, nixpkgs }:
    let
        system = "x86_64-linux";
        pkgs = import nixpkgs { inherit system; };
    in {
    devShells.${system}.default = pkgs.mkShell {
      buildInputs = [
        pkgs.python3
        pkgs.python3Packages.ndeflib
        pkgs.python3Packages.pyserial
        pkgs.python3Packages.pyscard
        pkgs.python3Packages.libusb1
        pkgs.libusb1
      ];
      shellHook = ''
        export LD_LIBRARY_PATH=${pkgs.pcsclite.lib}/lib:$LD_LIBRARY_PATH
        export NIX_LD_LIBRARY_PATH=${pkgs.pcsclite.lib}/lib:$NIX_LD_LIBRARY_PATH
        echo "🔹 NFC dev shell loaded."
        echo " - pcscd is required: run 'sudo systemctl start pcscd'"
        echo " - test with: pcsc_scan"
        echo " - You might have to blacklist kernel modules: pn533, pn533_usb, nfc"
      '';
    };
  };
}

