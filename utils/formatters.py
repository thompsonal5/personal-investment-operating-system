"""
Data formatting utilities - Consistent output formatting across PIOS
"""

from typing import Union
from datetime import datetime
import locale


def format_currency(value: Union[int, float], decimal_places: int = 2, include_symbol: bool = True) -> str:
    """Format numeric value as currency"""
    try:
        locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
    except locale.Error:
        pass
    
    symbol = "$" if include_symbol else ""
    formatted = locale.currency(value, grouping=True, symbol=symbol)
    return formatted


def format_percentage(value: float, decimal_places: int = 2, include_symbol: bool = True) -> str:
    """Format numeric value as percentage"""
    pct_value = value * 100
    symbol = "%" if include_symbol else ""
    return f"{pct_value:.{decimal_places}f}{symbol}"


def format_timestamp(timestamp: Union[datetime, float, str], format_str: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Format timestamp for display"""
    if isinstance(timestamp, float):
        timestamp = datetime.fromtimestamp(timestamp)
    elif isinstance(timestamp, str):
        timestamp = datetime.fromisoformat(timestamp)
    elif not isinstance(timestamp, datetime):
        raise TypeError(f"Unsupported timestamp type: {type(timestamp)}")
    
    return timestamp.strftime(format_str)


def format_number(value: Union[int, float], decimal_places: int = 2, thousands_sep: bool = True) -> str:
    """Format numeric value with optional thousands separator"""
    if thousands_sep:
        return f"{value:,.{decimal_places}f}"
    else:
        return f"{value:.{decimal_places}f}"


def format_bps(value: float, decimal_places: int = 0) -> str:
    """Format value as basis points"""
    bps_value = value * 10000
    return f"{bps_value:.{decimal_places}f} bps"


def format_ratio(numerator: float, denominator: float, decimal_places: int = 2) -> str:
    """Format ratio as x:1"""
    if denominator == 0:
        return "N/A"
    
    ratio = numerator / denominator
    return f"{ratio:.{decimal_places}f}x"


class FormatterChain:
    """Chain multiple formatters for complex output"""
    
    def __init__(self):
        self.formatters = []
    
    def add(self, formatter_func, *args, **kwargs):
        """Add formatter to chain"""
        self.formatters.append((formatter_func, args, kwargs))
        return self
    
    def format(self, value):
        """Apply formatters in sequence"""
        result = value
        for formatter_func, args, kwargs in self.formatters:
            result = formatter_func(result, *args, **kwargs)
        return result