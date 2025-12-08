import pandas as pd

def ma(df: pd.DataFrame, window: int = 24) -> pd.DataFrame:
    """
    Compute moving average for the 'price' column.
    Args:
        df (pd.DataFrame): DataFrame with 'price' column
        window (int): Window size for moving average
    Returns:
        pd.DataFrame: DataFrame with new 'moving_average' column
    """
    df = df.copy()
    df['ma'] = df['price'].rolling(window=window, min_periods=1, center=True).mean()
    return df

