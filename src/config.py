"""Application configuration and settings."""

import os
from pathlib import Path
import pandas as pd
from dotenv import load_dotenv
from exceptions import ConfigException

# Load environment variables
load_dotenv()

# ============================================================================
# PATHS
# ============================================================================
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / 'data'
OUTPUT_DIR = BASE_DIR / 'output'
LOGS_DIR = BASE_DIR / 'logs'
SCRIPTS_DIR = BASE_DIR / 'scripts'

# Ensure directories exist
for directory in [DATA_DIR, OUTPUT_DIR, LOGS_DIR]:
    directory.mkdir(exist_ok=True)

# ============================================================================
# ENVIRONMENT
# ============================================================================
DEBUG = os.getenv('DEBUG', 'True').lower() == 'true'
LOG_LEVEL = 'DEBUG' if DEBUG else 'INFO'

# ============================================================================
# API CONFIGURATION
# ============================================================================
ENTSOE_API_KEY: str = os.getenv('ENTSOE_API_KEY', '')
if not ENTSOE_API_KEY:
    raise ConfigException(
        "ENTSOE_API_KEY not found in environment variables. "
        "Please set it in .env file or as an environment variable."
    )

# ============================================================================
# DATA CONFIGURATION
# ============================================================================
DEFAULT_TIMEZONE = 'Europe/Brussels'
START_OF_15_MIN_SPOT_PRICE = pd.Timestamp('20251001', tz=DEFAULT_TIMEZONE)
DATA_START_DATE = pd.Timestamp('20250101', tz=DEFAULT_TIMEZONE)
COUNTRY_CODES_FILE = Path(__file__).parent / 'country_codes.csv'

# ============================================================================
# ANALYSIS CONFIGURATION
# ============================================================================
MA_WINDOW = 24  # hours

# ============================================================================
# DASH CONFIGURATION
# ============================================================================
DASH_HOST = '0.0.0.0'
DASH_PORT = int(os.getenv('DASH_PORT', 8050))
DASH_DEBUG = DEBUG

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

# ============================================================================
# DATA DOWNLOAD CONFIGURATION
# ============================================================================
DOWNLOAD_BATCH_SIZE = 365  # days
