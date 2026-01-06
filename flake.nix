{
  description = "Python Template";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-25.05";
  };

  outputs = { self , nixpkgs ,... }:
  let
    system = "x86_64-linux";
  in {
    devShells."${system}".default =
    let
      pkgs = import nixpkgs {
        inherit system;
      };
      
      entsoe-py = pkgs.python312Packages.buildPythonPackage rec {
        pname = "entsoe-py";
        version = "0.7.8";
        src = pkgs.fetchurl {
          url = "https://files.pythonhosted.org/packages/17/89/e6f18b055a7ffb7c27d046f9a0a0dd60e8bcf62cb97cfe3de91e7cfec1ed/entsoe_py-0.7.8.tar.gz";
          sha256 = "sha256-efmZH+nylDfqIYw9cJdSyemV/tmKbHb5naR7iAwvoAk=";
        };
        propagatedBuildInputs = with pkgs.python312Packages; [
          pandas
          requests
          beautifulsoup4
          pytz
        ];
        doCheck = false;
      };
      
    in pkgs.mkShell {
      packages = with pkgs; [
        python312Packages.python
        python312Packages.pyqt6
        python312Packages.jupyter
        python312Packages.notebook
        python312Packages.scipy
        python312Packages.numpy
        python312Packages.torch
        python312Packages.matplotlib
        python312Packages.pandas
        python312Packages.plotly
        python312Packages.dash
        python312Packages.flask
        python312Packages.gunicorn
        python312Packages.python-dotenv
        python312Packages.statsmodels
        python312Packages.pyecharts
        python312Packages.panel
        python312Packages.bokeh
        python312Packages.markdown-it-py
        python312Packages.mdit-py-plugins
        python312Packages.linkify-it-py
        entsoe-py
        
        # JS Stack
        nodejs_22
      ];
    };
  };
}
