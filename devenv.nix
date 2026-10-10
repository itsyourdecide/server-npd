{ pkgs, ... }:

{
  packages = with pkgs; [
    git
    curl
    jq
    docker
    ansible
    postgresql
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

}