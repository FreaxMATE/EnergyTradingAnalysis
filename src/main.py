import sys
from datamanager import DataManager
from plot import run_dash_app

def main():
    if len(sys.argv) < 2:
        print("Usage: python main.py [download|analyze|plot]")
        sys.exit(1)

    mode = sys.argv[1].lower()

    if mode == "download":
        dm = DataManager()
        dm.download()
    elif mode == "analyze":
        dm = DataManager(read_mode='data')
        dm.analysis()
    elif mode == "plot":
        run_dash_app()
    else:
        print("Unknown mode. Use one of: download, analyze, plot")

if __name__ == "__main__":
    main()