{ pkgs, ... }:

{
  packages = with pkgs; [
    git
    curl
    jq
    docker
    ansible
    docker-compose

    actionlint
    zizmor
    pinact
    shellcheck
    nixfmt-rfc-style
  ];

  languages.python = {
    enable = true;
    package = pkgs.python314;

    directory = "./portal";

    venv.enable = true;

    uv = {
      enable = true;

      sync = {
        enable = true;
        arguments = [ "--locked" ];
      };
    };
  };

  enterTest = ''
    set -e

    echo "Checking GitHub workflows..."
    # TODO: drop the ignore once actionlint supports the $/ self-repository
    # syntax that zizmor requires (GitHub runner >= 2.336)
    actionlint \
      -ignore 'specifying action "\$/.+" in invalid format because ref is missing'

    echo "Checking GitHub Actions security..."
    zizmor .

    echo "Checking Nix formatting..."
    nixfmt --check devenv.nix

    echo "Checking Python dependencies..."
    cd portal
    uv lock --check

    echo "Pinact check..."
    pinact run --check
  '';
}
