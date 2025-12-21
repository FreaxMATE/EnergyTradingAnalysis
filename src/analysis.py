import pandas as pd
from abc import ABC, abstractmethod
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from logger import setup_logger
from config import START_OF_15_MIN_SPOT_PRICE

logger = setup_logger(__name__)

class Analyzer(ABC):
    """Base class for all analysis strategies."""
    
    @abstractmethod
    def analyze(self, df: pd.DataFrame) -> pd.DataFrame:
        pass

class BasicStatsAnalyzer(Analyzer):
    """Calculates basic descriptive statistics."""
    
    def analyze(self, df: pd.DataFrame) -> pd.DataFrame:
        logger.info("Running Basic Stats Analysis...")
        return df.describe()

class MovingAverageAnalyzer(Analyzer):
    """Calculates moving average."""
    
    def __init__(self, window: str = '24h', min_periods: int = 1, center: bool = True):
        self.window = window
        self.min_periods = min_periods
        self.center = center

    def analyze(self, df: pd.DataFrame) -> pd.DataFrame:
        logger.info(f"Running Moving Average Analysis (window={self.window})...")
        
        if df.empty:
            logger.warning("Input DataFrame is empty")
            return df
        
        # Check if 'price' column exists, if not try to find a suitable column or use the first one
        target_col = 'price'
        if target_col not in df.columns:
             # Fallback logic or raise error. For now, let's assume 'price' or try to find it.
             # If the dataframe has only 'time' and one other column, use that.
             cols = [c for c in df.columns if c != 'time']
             if len(cols) == 1:
                 target_col = cols[0]
             else:
                 logger.error("'price' column not found in DataFrame")
                 raise ValueError("'price' column not found in DataFrame")

        df_copy = df.copy()
        
        # Ensure the time column is datetime and set as index if it's not already
        if 'time' in df_copy.columns:
            df_copy['time'] = pd.to_datetime(df_copy['time'], utc=True)
            df_copy = df_copy.set_index('time')
        
        # Compute rolling mean
        df_copy['ma'] = df_copy[target_col].rolling(
            window=self.window, 
            min_periods=self.min_periods, 
            center=self.center
        ).mean()
        
        return df_copy.reset_index()

class ForecastAnalyzer(Analyzer):
    """Performs basic time series forecasting using Holt-Winters."""
    
    def __init__(self, target_col: str = 'price', forecast_horizon_days: int = 1, backtest_days: int = 0, step_hours: int = 24):
        """
        Initialize ForecastAnalyzer.
        
        Args:
            target_col (str): The column name to forecast (default: 'price')
            forecast_horizon_days (int): How many days into the future to forecast
            backtest_days (int): How many days of history to simulate forecasts for (0 = only future forecast)
            step_hours (int): The interval in hours between simulated forecasts during backtesting
        """
        self.target_col = target_col
        self.forecast_horizon_days = forecast_horizon_days
        self.backtest_days = backtest_days
        self.step_hours = step_hours

    def analyze(self, df: pd.DataFrame) -> pd.DataFrame:
        logger.info(f"Running Forecast Analysis on {self.target_col}...")
        
        df_copy = df.copy()
        
        # Ensure we have a datetime index
        if 'time' in df_copy.columns:
            df_copy['time'] = pd.to_datetime(df_copy['time'], utc=True)
            df_copy = df_copy.set_index('time')
            
        # Ensure the target column exists
        if self.target_col not in df_copy.columns:
             # Fallback: if only one numeric column exists, use it
             numeric_cols = df_copy.select_dtypes(include=['number']).columns
             if len(numeric_cols) > 0:
                 self.target_col = numeric_cols[0]
                 logger.warning(f"Target column not found, using {self.target_col} instead.")
             else:
                raise ValueError(f"Column {self.target_col} not found in DataFrame")
            
        # Handle duplicates and sorting
        df_copy = df_copy[~df_copy.index.duplicated(keep='first')]
        df_copy = df_copy.sort_index()

        # Attempt to infer and set frequency
        if df_copy.index.freq is None:
            freq = pd.infer_freq(df_copy.index)
            if freq:
                df_copy = df_copy.asfreq(freq)
            else:
                # Fallback: try to determine frequency from data or default to hourly
                if len(df_copy) > 1:
                    timedeltas = df_copy.index.to_series().diff().dropna()
                    mode_delta = timedeltas.mode()
                    if not mode_delta.empty:
                        # Use the most common time difference
                        df_copy = df_copy.asfreq(mode_delta[0])
                    else:
                         # Default based on START_OF_15_MIN_SPOT_PRICE
                         if df_copy.index[0] >= START_OF_15_MIN_SPOT_PRICE:
                             df_copy = df_copy.asfreq('15min')
                         else:
                             df_copy = df_copy.asfreq('h')
                else:
                     if df_copy.index[0] >= START_OF_15_MIN_SPOT_PRICE:
                         df_copy = df_copy.asfreq('15min')
                     else:
                         df_copy = df_copy.asfreq('h')

        # Simple imputation for missing values to avoid errors
        # Use ffill() and bfill() as fillna(method='ffill') is deprecated
        series = df_copy[self.target_col].ffill().bfill()
        
        # Fit model (Holt-Winters Exponential Smoothing)
        # Adjust seasonal_periods based on frequency if possible
        seasonal_periods = 24
        periods_per_day = 24
        
        if series.index.freqstr:
            if '15T' in series.index.freqstr or '15min' in series.index.freqstr:
                seasonal_periods = 96
                periods_per_day = 96
            elif 'h' in series.index.freqstr.lower():
                seasonal_periods = 24
                periods_per_day = 24

        forecast_steps = self.forecast_horizon_days * periods_per_day
        
        all_forecasts = {}
        
        # Determine cutoffs
        end_time = series.index[-1]
        cutoffs = [end_time]
        
        if self.backtest_days > 0:
            # Generate cutoffs going back in time
            # We want to start from end_time - backtest_days and step forward by step_hours
            start_backtest = end_time - pd.Timedelta(days=self.backtest_days)
            
            # Align start_backtest to the frequency to avoid issues
            # But simpler is just to use it as a comparison point
            
            current_cutoff = start_backtest
            cutoffs = []
            while current_cutoff <= end_time:
                cutoffs.append(current_cutoff)
                current_cutoff += pd.Timedelta(hours=self.step_hours)
            
            # Ensure the final future forecast is included if the loop didn't exactly hit end_time
            if cutoffs[-1] < end_time:
                cutoffs.append(end_time)

        for cutoff in cutoffs:
            # Train on data up to cutoff
            train = series[series.index <= cutoff]
            
            if len(train) < 2 * seasonal_periods:
                continue

            try:
                model = ExponentialSmoothing(
                    train, 
                    seasonal_periods=seasonal_periods, 
                    trend='add', 
                    seasonal='add', 
                    initialization_method="estimated"
                ).fit()
                
                forecast = model.forecast(forecast_steps)
                
                # Reconstruct index to be safe
                freq = train.index.freq
                if freq is None:
                     # Should not happen due to asfreq above, but fallback
                     freq = 'h' if periods_per_day == 24 else '15min'
                     
                start_pred = cutoff + pd.tseries.frequencies.to_offset(freq)
                pred_index = pd.date_range(start=start_pred, periods=forecast_steps, freq=freq)
                
                forecast_series = pd.Series(forecast.values, index=pred_index)
                all_forecasts[cutoff] = forecast_series
                
            except Exception as e:
                logger.warning(f"Forecasting failed at {cutoff}: {e}")

        if not all_forecasts:
            return pd.DataFrame()

        # Combine all forecasts into a DataFrame
        forecast_data = {}
        for cutoff, series in all_forecasts.items():
            col_name = f"forecast_{cutoff.strftime('%Y%m%d%H%M')}"
            forecast_data[col_name] = series
            
        forecast_df = pd.DataFrame(forecast_data)
        forecast_df.index.name = 'time'
        return forecast_df.reset_index()

class AnalysisRunner:
    """Registry and runner for analysis tasks."""
    
    def __init__(self):
        self.analyzers = []

    def add_analyzer(self, analyzer: Analyzer):
        self.analyzers.append(analyzer)

    def run_all(self, df: pd.DataFrame) -> dict:
        results = {}
        for analyzer in self.analyzers:
            name = analyzer.__class__.__name__
            try:
                results[name] = analyzer.analyze(df)
            except Exception as e:
                logger.error(f"Error running {name}: {e}")
        return results
