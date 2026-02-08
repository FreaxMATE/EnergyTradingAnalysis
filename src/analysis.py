import pandas as pd
import numpy as np
from abc import ABC, abstractmethod
from statsmodels.tsa.holtwinters import ExponentialSmoothing

# Machine Learning Imports
try:
    from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
    from sklearn.multioutput import MultiOutputRegressor
except ImportError:
    import sys
    print("Warning: scikit-learn not installed. ML analysis will fail.", file=sys.stderr)

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
            return pd.DataFrame()
        
        target_col = 'price'
        if target_col not in df.columns:
             cols = [c for c in df.columns if c != 'time']
             if len(cols) == 1:
                 target_col = cols[0]
             else:
                 logger.error("'price' column not found in DataFrame")
                 raise ValueError("'price' column not found in DataFrame")

        df_copy = df.copy()
        if 'time' in df_copy.columns:
            df_copy['time'] = pd.to_datetime(df_copy['time'], utc=True)
            df_copy = df_copy.set_index('time')
        
        df_copy['ma'] = df_copy[target_col].rolling(
            window=self.window, 
            min_periods=self.min_periods, 
            center=self.center
        ).mean()
        
        return df_copy.reset_index()

class CombinedForecastAnalyzer(Analyzer):
    """
    Runs ALL forecasting models (Holt-Winters, Gradient Boosting, Random Forest)
    and returns a SINGLE DataFrame with all forecast columns.
    """
    
    def __init__(self, horizon_hours: int = 24):
        self.horizon_hours = horizon_hours
        
    def analyze(self, df: pd.DataFrame) -> pd.DataFrame:
        logger.info("Running Combined Forecast Analysis (HW + GB + RF)...")
        if df.empty: return pd.DataFrame()

        # 1. Prepare Data (Force 15-min resampling)
        df_clean = df.copy()
        if 'time' in df_clean.columns:
            df_clean['time'] = pd.to_datetime(df_clean['time'], utc=True)
            df_clean = df_clean.set_index('time')
        
        df_clean = df_clean.sort_index()
        df_15min = df_clean.resample('15min').ffill().dropna()
        
        # 2. Run Models
        hw_forecast = self._run_holt_winters(df_15min)
        gb_forecast = self._run_ml_model(df_15min, model_type='gb')
        rf_forecast = self._run_ml_model(df_15min, model_type='rf')
        
        # 3. Merge Results
        # Start with whichever DataFrame is not empty
        if not gb_forecast.empty:
            result = gb_forecast
        elif not hw_forecast.empty:
            result = hw_forecast
        elif not rf_forecast.empty:
            result = rf_forecast
        else:
            return pd.DataFrame()
            
        # Merge others on 'time'
        if not hw_forecast.empty and result is not hw_forecast:
            result = pd.merge(result, hw_forecast, on='time', how='outer')
            
        if not rf_forecast.empty and result is not rf_forecast:
            result = pd.merge(result, rf_forecast, on='time', how='outer')
            
        return result

    def _run_ml_model(self, df, model_type='gb'):
        """Helper to run ML models (GB or RF)."""
        try:
            prices = df['price'].values
            times = df.index
            
            steps_per_day = 96
            steps_per_week = 96 * 7
            horizon = self.horizon_hours * 4
            
            # Limit training history for speed (last 180 days)
            limit_rows = 96 * 180
            start_idx = max(steps_per_week, len(prices) - limit_rows)
            end_idx = len(prices) - horizon
            
            if len(prices) < steps_per_week + horizon:
                return pd.DataFrame()

            # Create Features
            X_train, y_train = self._create_features(
                prices, times, start_idx, end_idx, horizon, steps_per_day, steps_per_week
            )
            
            # Train
            if model_type == 'rf':
                model = RandomForestRegressor(
                    n_estimators=30, max_depth=10, max_samples=0.2, 
                    n_jobs=-1, random_state=42
                )
            else:
                model = MultiOutputRegressor(HistGradientBoostingRegressor(
                    max_iter=100, max_depth=5, learning_rate=0.1, random_state=42
                ))
            
            model.fit(X_train, y_train)
            
            # Predict Next 24h
            last_idx = len(prices)
            lag_day = prices[last_idx - steps_per_day : last_idx]
            lag_week = prices[last_idx - steps_per_week : last_idx - steps_per_week + steps_per_day]
            next_time = times[-1] + pd.Timedelta(minutes=15)
            
            X_curr = np.concatenate([
                lag_day, lag_week, 
                [next_time.hour, next_time.dayofweek]
            ]).reshape(1, -1)
            
            forecast_values = model.predict(X_curr)[0]
            
            # Create Result DF
            forecast_index = pd.date_range(start=next_time, periods=horizon, freq='15min')
            return pd.DataFrame({'time': forecast_index, f'forecast_{model_type}': forecast_values})
            
        except Exception as e:
            logger.error(f"ML {model_type} failed: {e}")
            return pd.DataFrame()

    def _create_features(self, prices, times, start_idx, end_idx, horizon, steps_per_day, steps_per_week):
        """Vectorized feature creation."""
        X, y = [], []
        for i in range(start_idx, end_idx):
            target = prices[i : i + horizon]
            lag_day = prices[i - steps_per_day : i]
            lag_week = prices[i - steps_per_week : i - steps_per_week + steps_per_day]
            t = times[i]
            row = np.concatenate([lag_day, lag_week, [t.hour, t.dayofweek]])
            X.append(row)
            y.append(target)
        return np.array(X), np.array(y)

    def _run_holt_winters(self, df):
        """Helper to run classical Holt-Winters forecast."""
        try:
            # Train on last 60 days to ensure stability & speed
            start_hw = df.index[-1] - pd.Timedelta(days=60)
            subset = df[df.index >= start_hw]['price'].asfreq('15min').ffill()
            
            model = ExponentialSmoothing(
                subset, 
                seasonal_periods=96, 
                trend='add', 
                seasonal='add', 
                initialization_method="estimated"
            ).fit()
            
            forecast = model.forecast(96) # 24h
            return pd.DataFrame({'time': forecast.index, 'forecast_hw': forecast.values})
        except Exception:
            return pd.DataFrame()

class AnalysisRunner:
    """Registry and runner for analysis tasks."""
    def __init__(self):
        self.analyzers = []
    def add_analyzer(self, analyzer: Analyzer):
        self.analyzers.append(analyzer)
    def run_all(self, df: pd.DataFrame) -> dict:
        results = {}
        for analyzer in self.analyzers:
            try:
                results[analyzer.__class__.__name__] = analyzer.analyze(df)
            except Exception as e:
                logger.error(f"Error running analyzer: {e}")
        return results