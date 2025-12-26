"""Main entry point for the Energy Trading Analysis application."""

import sys
from logger import setup_logger
from datamanager import DataManager
from plot import run_dash_app
from exceptions import EnergyTradingException

logger = setup_logger(__name__)


def main() -> None:
    """Main entry point with CLI argument handling."""
    if len(sys.argv) < 2:
        print("Usage: python main.py [download|analyze]")
        sys.exit(1)

    mode = sys.argv[1].lower()

    try:
        if mode == "download":
            logger.info("Starting download mode...")
            dm = DataManager()
            dm.download()
            logger.info("Download completed successfully")
        elif mode == "analyze":
            logger.info("Starting analysis mode...")
            dm = DataManager(read_mode='data')
            dm.analysis()
            logger.info("Analysis completed successfully")
        else:
            print("Unknown mode. Use one of: download, analyze, plot")
            sys.exit(1)
    except EnergyTradingException as e:
        logger.error(f"Application error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()