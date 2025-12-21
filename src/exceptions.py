"""Custom exceptions for the Energy Trading Analysis application."""


class EnergyTradingException(Exception):
    """Base exception for the application."""
    pass


class DataException(EnergyTradingException):
    """Raised when data operations fail."""
    pass


class ConfigException(EnergyTradingException):
    """Raised when configuration is invalid."""
    pass


class DownloadException(EnergyTradingException):
    """Raised when data download fails."""
    pass


class AnalysisException(EnergyTradingException):
    """Raised when analysis operations fail."""
    pass
