"""Data management module for downloading and processing energy price data."""

from pathlib import Path
from typing import Optional, Dict
import pandas as pd
import sys

try:
    import tzdata
except ImportError:
    print("Warning: tzdata not found.", file=sys.stderr)

from entsoe import EntsoePandasClient

import utils
from analysis import AnalysisRunner, MovingAverageAnalyzer, CombinedForecastAnalyzer
from logger import setup_logger
from config import (
    DATA_DIR,
    DEFAULT_TIMEZONE,
    START_OF_15_MIN_SPOT_PRICE,
    DATA_START_DATE,
    ENTSOE_API_KEY,
    COUNTRY_CODES_FILE
)
from exceptions import DataException, DownloadException

logger = setup_logger(__name__)


class DataManager:
    """Manages energy price data loading, downloading, and analysis."""

    def __init__(self, read_mode: str = '') -> None:
        if read_mode not in ('', 'data', 'feature'):
            raise ValueError(f"Invalid read_mode: {read_mode}")
        
        self.__directory = DATA_DIR
        self.__country_codes = self.__load_country_codes()
        self.__data: Optional[Dict] = self.__read_data() if read_mode in ('data', 'feature') else None
        self.__features: Optional[Dict] = self.__read_features() if read_mode == 'feature' else None
        self.__generation_data: Optional[Dict] = self.__read_generation_data() if read_mode in ('data', 'feature') else None
        logger.info(f"DataManager initialized with read_mode={read_mode}")

    def __load_country_codes(self) -> pd.Series:
        try:
            df = pd.read_csv(COUNTRY_CODES_FILE, dtype=str, delimiter=',', comment='#')
            return df['code']
        except Exception as e:
            raise DataException(f"Error loading country codes: {e}")

    @property
    def data(self) -> Dict[str, pd.DataFrame]:
        if self.__data is None: raise ValueError("Data not loaded")
        return self.__data

    @property
    def features(self) -> Dict[str, Dict[str, pd.DataFrame]]:
        if self.__features is None: raise ValueError("Features not loaded")
        return self.__features

    @property
    def generation_data(self) -> Dict[str, pd.DataFrame]:
        return self.__generation_data if self.__generation_data else {}

    @property
    def country_codes(self) -> pd.Series:
        return self.__country_codes

    def __read_data(self) -> Dict[str, pd.DataFrame]:
        data = {}
        for country_code in self.__country_codes:
            try:
                filepath = self.__directory / country_code / f"{country_code}.csv"
                if not filepath.exists() or filepath.stat().st_size == 0: continue
                
                df = pd.read_csv(filepath, delimiter=',', names=['time', 'price'], skiprows=1)
                df['time'] = pd.to_datetime(df['time'], utc=True)
                data[country_code] = df
            except Exception: pass
        return data

    def __read_generation_data(self) -> Dict[str, pd.DataFrame]:
        data = {}
        for country_code in self.__country_codes:
            try:
                filepath = self.__directory / country_code / f"{country_code}_generation.csv"
                if not filepath.exists() or filepath.stat().st_size == 0: continue
                
                df = pd.read_csv(filepath, index_col=0)
                df.index.name = 'time'
                df = df.reset_index()
                df['time'] = pd.to_datetime(df['time'], utc=True)
                data[country_code] = df
            except Exception: pass
        return data

    def __read_features(self) -> Dict[str, Dict[str, pd.DataFrame]]:
        """Robust feature reading."""
        features_file = self.__directory / "features.csv"
        
        if not features_file.exists() or features_file.stat().st_size == 0:
            return {}
        
        try:
            features = pd.read_csv(features_file, header=0)
            feature_names = features.columns.tolist()
            logger.info(f"Available features: {feature_names}")
            
            features_data = {}
            for country_code in self.__country_codes:
                features_data[country_code] = {}
                for feature in feature_names:
                    feature_file = self.__directory / country_code / f"{country_code}_{feature}.csv"
                    
                    if feature_file.exists():
                        try:
                            # Skip empty files
                            if feature_file.stat().st_size == 0:
                                logger.warning(f"Skipping empty feature file: {feature_file}")
                                continue
                                
                            df = pd.read_csv(feature_file, delimiter=',', comment='#')
                            if df.empty or 'time' not in df.columns: continue

                            df['time'] = pd.to_datetime(df['time'], utc=True)
                            features_data[country_code][feature] = df
                        except Exception as e:
                            logger.warning(f"Failed to read {feature} for {country_code}: {e}")
            return features_data
        except Exception as e:
            logger.error(f"Error reading features: {e}")
            return {}

    def analysis(self) -> None:
        if self.__data is None: raise ValueError("Data not loaded")
        try:
            for country_code in self.country_codes:
                self.analysis_by_country_code(country_code)
            self.__update_features_file()
            logger.info("Analysis completed successfully")
        except Exception as e:
            logger.error(f"Error during analysis: {e}")
            raise

    def analysis_by_country_code(self, country_code: str) -> None:
        """Run analysis: Moving Average + Combined Forecasts."""
        try:
            if self.__data is None: raise ValueError("Data not loaded")
            df = self.__data[country_code]
            if df.empty: return

            # 1. Moving Average
            ma_runner = AnalysisRunner()
            ma_runner.add_analyzer(MovingAverageAnalyzer())
            ma_results = ma_runner.run_all(df)
            if 'MovingAverageAnalyzer' in ma_results:
                self.save_analysis(country_code, ma_results['MovingAverageAnalyzer'], feature='ma')

            # 2. Combined Forecasts (HW + GB + RF) -> forecasts.csv
            fc_runner = AnalysisRunner()
            fc_runner.add_analyzer(CombinedForecastAnalyzer(horizon_hours=24))
            
            fc_results = fc_runner.run_all(df)
            if 'CombinedForecastAnalyzer' in fc_results:
                res = fc_results['CombinedForecastAnalyzer']
                if not res.empty:
                    self.save_analysis(country_code, res, feature='forecasts')

            logger.debug(f"Analysis completed for {country_code}")
        except Exception as e:
            logger.error(f"Error analyzing {country_code}: {e}")

    def save_analysis(self, country_code: str, df: pd.DataFrame, feature: str = 'ma') -> None:
        try:
            if df.empty: return
            directory = self.__directory / country_code
            directory.mkdir(parents=True, exist_ok=True)
            
            filename = f"{country_code}_{feature}.csv"
            df.to_csv(directory / filename, index=False)
            logger.info(f"Saved analysis to {filename}")
        except Exception as e:
            logger.error(f"Error saving analysis: {e}")

    def __update_features_file(self) -> None:
        """Update features.csv registry."""
        features_file = self.__directory / "features.csv"
        try:
            # We now only use 'ma' and 'forecasts' (plural)
            pd.DataFrame({'ma': [], 'forecasts': []}).to_csv(features_file, index=False)
        except Exception as e:
            logger.error(f"Error updating features file: {e}")

    def download(self) -> None:
        try:
            client = EntsoePandasClient(api_key=ENTSOE_API_KEY)
            start_date = DATA_START_DATE
            end_date = pd.Timestamp.now(tz=DEFAULT_TIMEZONE).round(freq='h')
            logger.info(f"Starting download from {start_date} to {end_date}")
            for i, country_code in enumerate(self.__country_codes, 1):
                logger.info(f"[{i}/{len(self.__country_codes)}] Downloading {country_code}...")
                self.download_by_country_code(client, country_code, start_date, end_date)
                self.download_generation_by_country_code(client, country_code, start_date, end_date)
            logger.info("Download completed successfully")
        except Exception as e:
            logger.error(f"Download failed: {e}")
            raise DownloadException(f"Download failed: {e}")

    def download_by_country_code(self, client, country_code, start_date, end_date) -> None:
        # (Same as before)
        directory = self.__directory / country_code
        filepath = directory / f"{country_code}.csv"
        append = False
        try:
            if filepath.exists():
                last_line = utils.read_last_csv_line(str(filepath))
                last_saved_time = pd.Timestamp(last_line.strip().split(',')[0], tz=DEFAULT_TIMEZONE)
                if last_saved_time > START_OF_15_MIN_SPOT_PRICE:
                    start_date = last_saved_time + pd.Timedelta(minutes=15)
                else:
                    start_date = last_saved_time + pd.Timedelta(hours=1)
                append = True
            
            if start_date >= end_date: return

            day_ahead_prices = client.query_day_ahead_prices(country_code, start_date, end_date)
            directory.mkdir(parents=True, exist_ok=True)
            
            if not append: day_ahead_prices.to_csv(filepath)
            else: day_ahead_prices.to_csv(filepath, mode='a', header=False)
        except Exception as e:
            logger.error(f"Error downloading {country_code}: {e}")

    def download_generation_by_country_code(self, client, country_code, start_date, end_date) -> None:
        # (Same as before)
        directory = self.__directory / country_code
        filepath = directory / f"{country_code}_generation.csv"
        append = False
        try:
            if filepath.exists():
                last_line = utils.read_last_csv_line(str(filepath))
                if last_line:
                    last_saved_time = pd.Timestamp(last_line.strip().split(',')[0], tz=DEFAULT_TIMEZONE)
                    if last_saved_time > START_OF_15_MIN_SPOT_PRICE:
                        start_date = last_saved_time + pd.Timedelta(minutes=15)
                    else:
                        start_date = last_saved_time + pd.Timedelta(hours=1)
                    append = True
            
            if start_date >= end_date: return

            df = client.query_generation(country_code, start=start_date, end=end_date, psr_type=None)
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
            directory.mkdir(parents=True, exist_ok=True)
            
            if not append: df.to_csv(filepath)
            else:
                existing_df = pd.read_csv(filepath, nrows=0, index_col=0)
                if not df.columns.is_unique:
                    # Deduplicate columns logic...
                    new_cols = []
                    col_counts = {}
                    for col in df.columns:
                        if col in col_counts:
                            col_counts[col] += 1
                            new_cols.append(f"{col}.{col_counts[col]}")
                        else:
                            col_counts[col] = 0
                            new_cols.append(col)
                    df.columns = new_cols
                df = df.reindex(columns=existing_df.columns)
                df.to_csv(filepath, mode='a', header=False)
        except Exception as e:
            logger.error(f"Error downloading generation for {country_code}: {e}")

if __name__ == '__main__':
    data_manager = DataManager()
    data_manager.download()