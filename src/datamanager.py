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
from backtest import walk_forward
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
        self.__exog: Optional[Dict] = self.__read_exogenous() if read_mode in ('data', 'feature') else None
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
    def exogenous(self) -> Dict[str, pd.DataFrame]:
        """Per-country exogenous regressors: load forecast + renewables forecast,
        joined on time. Empty dict if no exogenous data has been downloaded."""
        return self.__exog if self.__exog else {}

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

    def __read_exogenous(self) -> Dict[str, pd.DataFrame]:
        """Read and merge load forecast + renewables forecast per country.

        Output column names: ``load_forecast``, ``solar_forecast``,
        ``wind_onshore_forecast``, ``wind_offshore_forecast`` (subset depending
        on what each TSO publishes). Missing files are silently skipped, so
        zones without exogenous data simply fall back to autoregressive
        features in the model layer.
        """
        out: Dict[str, pd.DataFrame] = {}
        column_renames = {
            'Solar': 'solar_forecast',
            'Wind Onshore': 'wind_onshore_forecast',
            'Wind Offshore': 'wind_offshore_forecast',
        }
        for country_code in self.__country_codes:
            cdir = self.__directory / country_code
            frames = []
            try:
                load_fp = cdir / f"{country_code}_load_forecast.csv"
                if load_fp.exists() and load_fp.stat().st_size > 0:
                    df = pd.read_csv(load_fp, index_col=0)
                    df.index = pd.to_datetime(df.index, utc=True)
                    # entsoe-py returns either "Forecasted Load" or a single
                    # unnamed column; normalize to "load_forecast".
                    if df.shape[1] == 1:
                        df.columns = ['load_forecast']
                    else:
                        df = df.rename(columns={df.columns[0]: 'load_forecast'})
                        df = df[['load_forecast']]
                    frames.append(df)

                ren_fp = cdir / f"{country_code}_renewables_forecast.csv"
                if ren_fp.exists() and ren_fp.stat().st_size > 0:
                    df = pd.read_csv(ren_fp, index_col=0)
                    df.index = pd.to_datetime(df.index, utc=True)
                    df = df.rename(columns=column_renames)
                    frames.append(df)

                if not frames:
                    continue
                merged = pd.concat(frames, axis=1)
                merged = merged[~merged.index.duplicated(keep='last')].sort_index()
                merged.index.name = 'time'
                out[country_code] = merged.reset_index()
            except Exception as e:
                logger.warning(f"Could not load exogenous data for {country_code}: {e}")
        return out

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
                            if df.empty: continue
                            if 'time' in df.columns:
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
        """Run analysis: Moving Average + Combined Forecasts + Backtest."""
        try:
            if self.__data is None: raise ValueError("Data not loaded")
            df = self.__data[country_code]
            if df.empty: return

            exog = self.exogenous.get(country_code)

            # 1. Moving Average
            ma_runner = AnalysisRunner()
            ma_runner.add_analyzer(MovingAverageAnalyzer())
            ma_results = ma_runner.run_all(df)
            if 'MovingAverageAnalyzer' in ma_results:
                self.save_analysis(country_code, ma_results['MovingAverageAnalyzer'], feature='ma')

            # 2. Combined Forecasts (Naive + HW + LGB[q] + RF) -> forecasts.csv
            fc_runner = AnalysisRunner()
            fc_runner.add_analyzer(CombinedForecastAnalyzer(
                horizon_hours=24, zone_code=country_code, exog=exog))

            fc_results = fc_runner.run_all(df)
            if 'CombinedForecastAnalyzer' in fc_results:
                res = fc_results['CombinedForecastAnalyzer']
                if not res.empty:
                    self.save_analysis(country_code, res, feature='forecasts')

            # 3. Walk-forward backtest -> backtest.csv + metrics.csv
            try:
                predictions, metrics = walk_forward(
                    df, backtest_days=30, horizon_hours=24,
                    zone_code=country_code, exog=exog)
                if not predictions.empty:
                    self.save_analysis(country_code, predictions, feature='backtest')
                if not metrics.empty:
                    self.save_analysis(country_code, metrics.reset_index(), feature='metrics')
            except Exception as e:
                logger.error(f"Backtest failed for {country_code}: {e}")

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
            pd.DataFrame({'ma': [], 'forecasts': [], 'backtest': [], 'metrics': []}
                         ).to_csv(features_file, index=False)
        except Exception as e:
            logger.error(f"Error updating features file: {e}")

    def download(self) -> None:
        try:
            client = EntsoePandasClient(api_key=ENTSOE_API_KEY)
            start_date = DATA_START_DATE
            now = pd.Timestamp.now(tz=DEFAULT_TIMEZONE).round(freq='h')
            # Prices + actual generation: ask up to "now" only — querying into
            # the future raises NoMatchingDataError. Forecasts: ask +2 days
            # so we capture tomorrow's published TSO forecast.
            spot_end = now
            forecast_end = now + pd.Timedelta(days=2)
            logger.info(f"Starting download from {start_date} (spot to {spot_end}, forecasts to {forecast_end})")
            for i, country_code in enumerate(self.__country_codes, 1):
                logger.info(f"[{i}/{len(self.__country_codes)}] Downloading {country_code}...")
                self.download_by_country_code(client, country_code, start_date, spot_end)
                self.download_generation_by_country_code(client, country_code, start_date, spot_end)
                self.download_load_forecast(client, country_code, start_date, forecast_end)
                self.download_renewables_forecast(client, country_code, start_date, forecast_end)
            logger.info("Download completed successfully")
        except Exception as e:
            logger.error(f"Download failed: {e}")
            raise DownloadException(f"Download failed: {e}")

    def _resume_start(self, filepath: Path, default_start: pd.Timestamp
                      ) -> Optional[pd.Timestamp]:
        """Return the next timestamp to query, or None if no resume info."""
        if not filepath.exists():
            return default_start
        try:
            last_line = utils.read_last_csv_line(str(filepath))
            if not last_line or ',' not in last_line:
                return default_start
            last_saved_time = pd.Timestamp(last_line.strip().split(',')[0],
                                           tz=DEFAULT_TIMEZONE)
            step = (pd.Timedelta(minutes=15)
                    if last_saved_time > START_OF_15_MIN_SPOT_PRICE
                    else pd.Timedelta(hours=1))
            return last_saved_time + step
        except Exception as e:
            logger.warning(f"Could not parse {filepath} for resume: {e}")
            return default_start

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

    def download_load_forecast(self, client, country_code, start_date, end_date) -> None:
        """Day-ahead load forecast (process_type=A01)."""
        directory = self.__directory / country_code
        filepath = directory / f"{country_code}_load_forecast.csv"
        try:
            resume = self._resume_start(filepath, start_date)
            if resume is None or resume >= end_date:
                return
            df = client.query_load_forecast(country_code=country_code,
                                             start=resume, end=end_date)
            if isinstance(df, pd.Series):
                df = df.to_frame("load_forecast")
            elif isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            directory.mkdir(parents=True, exist_ok=True)
            append = filepath.exists()
            if not append:
                df.to_csv(filepath)
            else:
                existing_cols = pd.read_csv(filepath, nrows=0, index_col=0).columns
                df = df.reindex(columns=existing_cols)
                df.to_csv(filepath, mode='a', header=False)
        except Exception as e:
            logger.error(f"Error downloading load forecast for {country_code}: {e}")

    def download_renewables_forecast(self, client, country_code, start_date, end_date) -> None:
        """Day-ahead wind + solar forecast (process_type=A01)."""
        directory = self.__directory / country_code
        filepath = directory / f"{country_code}_renewables_forecast.csv"
        try:
            resume = self._resume_start(filepath, start_date)
            if resume is None or resume >= end_date:
                return
            df = client.query_wind_and_solar_forecast(country_code=country_code,
                                                       start=resume, end=end_date,
                                                       psr_type=None)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            directory.mkdir(parents=True, exist_ok=True)
            append = filepath.exists()
            if not append:
                df.to_csv(filepath)
            else:
                existing_cols = pd.read_csv(filepath, nrows=0, index_col=0).columns
                df = df.reindex(columns=existing_cols)
                df.to_csv(filepath, mode='a', header=False)
        except Exception as e:
            logger.error(f"Error downloading renewables forecast for {country_code}: {e}")

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