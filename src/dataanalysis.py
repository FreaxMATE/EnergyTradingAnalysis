"""Data analysis functions."""

from typing import Optional
import pandas as pd
from logger import setup_logger
from exceptions import AnalysisException

logger = setup_logger(__name__)


def ma(df: pd.DataFrame, window: str = '24h', min_periods: int = 1, center: bool = True) -> pd.DataFrame:
    """
    Compute moving average for the 'price' column.
    
    Args:
        df (pd.DataFrame): DataFrame with 'price' column and time column
        window (str): Window size for moving average (e.g., '24h', '7d')
        min_periods (int): Minimum number of observations in window required
        center (bool): Whether to center the window
    
    Returns:
        pd.DataFrame: DataFrame with new 'ma' column
    
    Raises:
        AnalysisException: If DataFrame is invalid or operation fails
    """
    try:
        if df.empty:
            logger.warning("Input DataFrame is empty")
            raise AnalysisException("Input DataFrame is empty")
        
        if 'price' not in df.columns:
            logger.error("'price' column not found in DataFrame")
            raise AnalysisException("'price' column not found in DataFrame")
        
        df_copy = df.copy()
        
        # Ensure the first column is datetime and set as index
        time_col = df_copy.columns[0]
        
        # Parse as UTC to avoid mixed timezone issues
        df_copy[time_col] = pd.to_datetime(df_copy[time_col], utc=True)
        df_copy = df_copy.set_index(time_col)
        
        # Compute rolling mean
        df_copy['ma'] = df_copy['price'].rolling(
            window=window, 
            min_periods=min_periods, 
            center=center
        ).mean()
        
        df_copy = df_copy.reset_index()
        logger.debug(f"Computed moving average with window={window}")
        return df_copy
    except AnalysisException:
        raise
    except Exception as e:
        logger.error(f"Error computing moving average: {e}")
        raise AnalysisException(f"Error computing moving average: {e}")

