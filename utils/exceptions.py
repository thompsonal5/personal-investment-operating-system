"""
Custom exceptions for PIOS
Fortress Edition - Standardized error handling
"""


class PIOSException(Exception):
    """Base exception for all PIOS errors"""
    
    def __init__(self, message: str, error_code: str = None):
        self.message = message
        self.error_code = error_code or self.__class__.__name__
        super().__init__(self.message)


class ValidationError(PIOSException):
    """Raised when data validation fails"""
    pass


class ConfigurationError(PIOSException):
    """Raised when configuration is invalid"""
    pass


class DataError(PIOSException):
    """Raised when data retrieval or processing fails"""
    pass


class DataVoidError(DataError):
    """Raised when data void occurs"""
    pass


class MCPServerError(PIOSException):
    """Raised when MCP server communication fails"""
    pass


class OrderExecutionError(PIOSException):
    """Raised when order execution fails"""
    pass


class RiskViolationError(PIOSException):
    """Raised when risk guardrail is violated"""
    pass


class AccountComplianceError(PIOSException):
    """Raised when account restrictions are violated"""
    pass


class PortfolioError(PIOSException):
    """Raised when portfolio operations fail"""
    pass


class RebalancingError(PortfolioError):
    """Raised when rebalancing fails"""
    pass


class CacheError(PIOSException):
    """Raised when cache operations fail"""
    pass


class ReportingError(PIOSException):
    """Raised when report generation fails"""
    pass


class InsufficientFundsError(OrderExecutionError):
    """Raised when insufficient funds for order"""
    pass


class PositionLimitError(RiskViolationError):
    """Raised when position limit exceeded"""
    pass


class LeverageError(RiskViolationError):
    """Raised when leverage limit exceeded"""
    pass


class StrategyCombinationError(RiskViolationError):
    """Raised when incompatible strategies combined"""
    pass