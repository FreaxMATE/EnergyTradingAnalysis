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
    # Ensure the first column is datetime and set as index
    time_col = df.columns[0]
    # Parse as UTC to avoid mixed time zone issues
    df[time_col] = pd.to_datetime(df[time_col], utc=True)
    df = df.set_index(time_col)

    # Compute rolling mean with a 24-hour window
    df['ma'] = df['price'].rolling(window='24h', min_periods=1, center=True).mean()
    df = df.reset_index()  # Optional: reset index to restore original structure
    return df

