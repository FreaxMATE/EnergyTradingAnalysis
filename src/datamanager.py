"""Data management module for downloading and processing energy price data."""

from pathlib import Path
from typing import Optional, Dict
import pandas as pd
from entsoe import EntsoePandasClient

import utils
from analysis import AnalysisRunner, MovingAverageAnalyzer, ForecastAnalyzer
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
        """
        Initialize DataManager.
        
        Args:
            read_mode (str): '' for no data, 'data' to load data, 'feature' to load data and features
        
        Raises:
            ValueError: If read_mode is invalid
            DataException: If country codes cannot be loaded
        """
        if read_mode not in ('', 'data', 'feature'):
            raise ValueError(f"Invalid read_mode: {read_mode}. Must be '', 'data', or 'feature'")
        
        self.__directory = DATA_DIR
        self.__country_codes = self.__load_country_codes()
        self.__data: Optional[Dict] = self.__read_data() if read_mode in ('data', 'feature') else None
        self.__features: Optional[Dict] = self.__read_features() if read_mode == 'feature' else None
        logger.info(f"DataManager initialized with read_mode={read_mode}")

    def __load_country_codes(self) -> pd.Series:
        """
        Load country codes from CSV file.
        
        Returns:
            pd.Series: Series containing country codes
        
        Raises:
            DataException: If country codes file cannot be read
        """
        try:
            df = pd.read_csv(COUNTRY_CODES_FILE, dtype=str, delimiter=',', comment='#')
            logger.debug(f"Loaded {len(df)} country codes from {COUNTRY_CODES_FILE}")
            return df['code']
        except FileNotFoundError:
            logger.error(f"Country codes file not found: {COUNTRY_CODES_FILE}")
            raise DataException(f"Country codes file not found: {COUNTRY_CODES_FILE}")
        except Exception as e:
            logger.error(f"Error loading country codes: {e}")
            raise DataException(f"Error loading country codes: {e}")

    @property
    def data(self) -> Dict[str, pd.DataFrame]:
        """Get loaded price data."""
        if self.__data is None:
            raise ValueError("Data not loaded. Initialize with read_mode='data' or 'feature'")
        return self.__data

    @property
    def features(self) -> Dict[str, Dict[str, pd.DataFrame]]:
        """Get loaded feature data."""
        if self.__features is None:
            raise ValueError("Features not loaded. Initialize with read_mode='feature'")
        return self.__features

    @property
    def country_codes(self) -> pd.Series:
        """Get country codes."""
        return self.__country_codes

    def __read_data(self) -> Dict[str, pd.DataFrame]:
        """
        Read price data for all countries.
        
        Returns:
            Dict[str, pd.DataFrame]: Dictionary mapping country codes to price DataFrames
        """
        data = {}
        for country_code in self.__country_codes:
            try:
                filepath = self.__directory / country_code / f"{country_code}.csv"
                if not filepath.exists():
                    logger.warning(f"Data file not found for {country_code}: {filepath}")
                    continue
                
                df = pd.read_csv(
                    filepath,
                    delimiter=',',
                    names=['time', 'price'],
                    skiprows=1,
                    comment='#'
                )
                df['time'] = pd.to_datetime(df['time'], utc=True)
                data[country_code] = df
                logger.debug(f"Loaded data for {country_code}: {len(df)} rows")
            except Exception as e:
                logger.error(f"Error reading data for {country_code}: {e}")
        
        return data

    def __read_features(self) -> Dict[str, Dict[str, pd.DataFrame]]:
        """
        Read feature data for all countries.
        
        Returns:
            Dict[str, Dict[str, pd.DataFrame]]: Nested dictionary of features by country
        """
        features_file = self.__directory / "features.csv"
        
        if not features_file.exists():
            logger.warning(f"Features file not found: {features_file}")
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
                        df = pd.read_csv(feature_file, delimiter=',', comment='#')
                        features_data[country_code][feature] = df
            
            return features_data
        except Exception as e:
            logger.error(f"Error reading features: {e}")
            return {}

    def analysis(self) -> None:
        """
        Run analysis on all countries.
        
        Raises:
            ValueError: If data is not loaded
            Exception: If analysis fails for any country
        """
        if self.__data is None:
            raise ValueError("Data not loaded. Cannot run analysis.")
        
        try:
            for country_code in self.country_codes:
                self.analysis_by_country_code(country_code)
            self.__update_features_file()
            logger.info("Analysis completed successfully")
        except Exception as e:
            logger.error(f"Error during analysis: {e}")
            raise

    def analysis_by_country_code(self, country_code: str) -> None:
        """
        Run analysis for a specific country.
        
        Args:
            country_code (str): Country code
        """
        try:
            if self.__data is None:
                raise ValueError("Data not loaded")
            
            df = self.__data[country_code]

            # 1. Moving Average on full data
            ma_runner = AnalysisRunner()
            ma_runner.add_analyzer(MovingAverageAnalyzer())
            ma_results = ma_runner.run_all(df)
            
            if 'MovingAverageAnalyzer' in ma_results:
                self.save_analysis(country_code, ma_results['MovingAverageAnalyzer'], feature='ma')

            # 2. Forecast on subset (last 365 days)
            forecast_runner = AnalysisRunner()
            forecast_runner.add_analyzer(ForecastAnalyzer(forecast_horizon_days=2, backtest_days=3, step_hours=9))
            
            if not df.empty:
                last_time = df['time'].max()
                start_time = last_time - pd.Timedelta(days=365)
                df_subset = df[df['time'] >= start_time].copy()
                forecast_results = forecast_runner.run_all(df_subset)
            else:
                forecast_results = forecast_runner.run_all(df)
                
            if 'ForecastAnalyzer' in forecast_results:
                self.save_analysis(country_code, forecast_results['ForecastAnalyzer'], feature='forecast')
                
            logger.debug(f"Analysis completed for {country_code}")
        except Exception as e:
            logger.error(f"Error analyzing {country_code}: {e}")

    def save_analysis(self, country_code: str, df: pd.DataFrame, feature: str = 'ma') -> None:
        """
        Save analysis results to CSV.
        
        Args:
            country_code (str): Country code
            df (pd.DataFrame): DataFrame to save
            feature (str): Feature name for filename
        
        Raises:
            DataException: If save fails
        """
        try:
            directory = self.__directory / country_code
            directory.mkdir(parents=True, exist_ok=True)
            
            filename = f"{country_code}_{feature}.csv"
            filepath = directory / filename
            
            df.to_csv(filepath, index=False)
            logger.info(f"Saved analysis to {filepath}")
        except Exception as e:
            logger.error(f"Error saving analysis for {country_code}: {e}")
            raise DataException(f"Error saving analysis for {country_code}: {e}")

    def __update_features_file(self) -> None:
        """Update features.csv with new features."""
        features_file = self.__directory / "features.csv"
        try:
            # Always ensure 'ma' and 'forecast' are present
            pd.DataFrame({'ma': [], 'forecast': []}).to_csv(features_file, index=False)
            logger.debug("Features file updated")
        except Exception as e:
            logger.error(f"Error updating features file: {e}")

    def download(self) -> None:
        """
        Download price data from ENTSOE for all countries.
        
        Raises:
            DownloadException: If download fails
        """
        try:
            client = EntsoePandasClient(api_key=ENTSOE_API_KEY)
            start_date = DATA_START_DATE
            end_date = pd.Timestamp.now(tz=DEFAULT_TIMEZONE).round(freq='h')
            
            logger.info(f"Starting download from {start_date} to {end_date}")
            
            for i, country_code in enumerate(self.__country_codes, 1):
                logger.info(f"[{i}/{len(self.__country_codes)}] Downloading {country_code}...")
                self.download_by_country_code(client, country_code, start_date, end_date)
            
            logger.info("Download completed successfully")
        except Exception as e:
            logger.error(f"Download failed: {e}")
            raise DownloadException(f"Download failed: {e}")

    def download_by_country_code(
        self, 
        client: EntsoePandasClient, 
        country_code: str, 
        start_date: pd.Timestamp, 
        end_date: pd.Timestamp
    ) -> None:
        """
        Download data for a specific country.
        
        Args:
            client (EntsoePandasClient): ENTSOE API client
            country_code (str): Country code
            start_date (pd.Timestamp): Start date for download
            end_date (pd.Timestamp): End date for download
        
        Raises:
            DownloadException: If download fails
        """
        directory = self.__directory / country_code
        filepath = directory / f"{country_code}.csv"
        append = False
        
        try:
            if filepath.exists():
                logger.debug(f"Checking existing file for {country_code}...")
                last_line = utils.read_last_csv_line(str(filepath))
                last_saved_time = pd.Timestamp(
                    last_line.strip().split(',')[0],
                    tz=DEFAULT_TIMEZONE
                )
                
                if last_saved_time > START_OF_15_MIN_SPOT_PRICE:
                    start_date = last_saved_time + pd.Timedelta(minutes=15)
                else:
                    start_date = last_saved_time + pd.Timedelta(hours=1)
                append = True
                logger.debug(f"Resuming from {start_date}")
            
            if start_date >= end_date:
                logger.info(f"Data for {country_code} is already up to date.")
                return

            logger.debug(f"Fetching data from {start_date} to {end_date}...")
            day_ahead_prices = client.query_day_ahead_prices(country_code, start_date, end_date)
            
            directory.mkdir(parents=True, exist_ok=True)
            
            if not append:
                day_ahead_prices.to_csv(filepath)
            else:
                day_ahead_prices.to_csv(filepath, mode='a', header=False)
            
            logger.info(f"Successfully downloaded {country_code}: {len(day_ahead_prices)} rows")
        except Exception as e:
            logger.error(f"Error downloading {country_code}: {e}")
            raise DownloadException(f"Error downloading {country_code}: {e}")

if __name__ == '__main__':
    data_manager = DataManager()
    data_manager.download()
