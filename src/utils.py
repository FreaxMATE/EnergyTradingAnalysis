"""Utility functions for data processing."""

from typing import Optional
from pathlib import Path
import pandas as pd
from logger import setup_logger
from exceptions import DataException

logger = setup_logger(__name__)


def read_last_csv_line(filepath: str) -> str:
    """
    Read the last line of a CSV file efficiently.
    
    Args:
        filepath (str): Path to the CSV file
    
    Returns:
        str: The last line of the file
    
    Raises:
        DataException: If file cannot be read
    """
    try:
        with open(filepath, 'rb') as f:
            f.seek(0, 2)
            file_size = f.tell()
            
            if file_size == 0:
                logger.warning(f"File is empty: {filepath}")
                return ''
            
            buffer_size = 8192
            position = file_size
            lines = []
            
            while position > 0:
                position = max(0, position - buffer_size)
                f.seek(position)
                chunk = f.read(min(buffer_size, file_size - position))
                lines = chunk.split(b'\n')
                
                if len(lines) > 1 and lines[-1] == b'':
                    return lines[-2].decode('utf-8')
                elif len(lines) > 0 and lines[-1] != b'':
                    return lines[-1].decode('utf-8')
            
            return lines[0].decode('utf-8') if lines else ''
    except FileNotFoundError:
        logger.error(f"File not found: {filepath}")
        raise DataException(f"File not found: {filepath}")
    except Exception as e:
        logger.error(f"Error reading file {filepath}: {e}")
        raise DataException(f"Error reading file {filepath}: {e}")


def extract_last(data: pd.DataFrame, timedelta: pd.Timedelta) -> pd.DataFrame:
    """
    Extract the last N time period from a DataFrame.
    
    Args:
        data (pd.DataFrame): DataFrame with 'time' column
        timedelta (pd.Timedelta): Time period to extract
    
    Returns:
        pd.DataFrame: Filtered DataFrame containing only the last period
    
    Raises:
        DataException: If DataFrame is invalid or processing fails
    """
    try:
        if data.empty:
            logger.warning("Data is empty, returning empty DataFrame")
            return data.copy()
        
        if 'time' not in data.columns:
            logger.error("'time' column not found in DataFrame")
            raise DataException("'time' column not found in DataFrame")
        
        last_timestamp = pd.to_datetime(data['time'].iloc[-1], utc=True)
        cutoff_time = last_timestamp - timedelta
        
        data_copy = data.copy()
        data_copy['time'] = pd.to_datetime(data_copy['time'], utc=True)
        filtered_data = data_copy[data_copy['time'] >= cutoff_time]
        
        logger.debug(f"Extracted {len(filtered_data)} rows for timedelta {timedelta}")
        return filtered_data
    except DataException:
        raise
    except Exception as e:
        logger.error(f"Error extracting data: {e}")
        raise DataException(f"Error extracting data: {e}")