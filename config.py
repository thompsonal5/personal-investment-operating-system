"""
PIOS Configuration Module
Fortress Edition - Options Command Center Workspace Architect

All configuration is centralized here for easy deployment across
different environments (dev, staging, production).
"""

import os
from enum import Enum
from pathlib import Path
from typing import Dict, Any

# ============================================================================
# ENVIRONMENT & PATHS
# ============================================================================

PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
PORTFOLIO_DIR = PROJECT_ROOT / "portfolio"
WATCHLIST_DIR = PROJECT_ROOT / "watchlists"
REPORTS_DIR = PROJECT_ROOT / "reports"
MCP_SERVERS_DIR = PROJECT_ROOT / "mcp-servers"
CACHE_DIR = DATA_DIR / "cache"
LOGS_DIR = PROJECT_ROOT / "logs"

# Create directories if they don't exist
for directory in [DATA_DIR, PORTFOLIO_DIR, WATCHLIST_DIR, REPORTS_DIR, 
                   MCP_SERVERS_DIR, CACHE_DIR, LOGS_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# ============================================================================
# ACCOUNT CONFIGURATION
# ============================================================================

class AccountType(Enum):
    """Account type classifications"""
    ROTH_IRA = "roth_ira"
    BROKERAGE = "brokerage"
    AGENTIC = "agentic"


class StrategyType(Enum):
    """Allowed trading strategies"""
    COVERED_CALL = "covered_call"
    CASH_SECURED_PUT = "cash_secured_put"
    IRON_BUTTERFLY = "iron_butterfly"
    EQUITY_PURCHASE = "equity_purchase"
    CASH_HOLD = "cash_hold"


# Account-Strategy Restriction Matrix
ACCOUNT_STRATEGY_MATRIX = {
    AccountType.ROTH_IRA: {
        StrategyType.COVERED_CALL,
        StrategyType.CASH_SECURED_PUT,
        StrategyType.EQUITY_PURCHASE,
    },
    AccountType.BROKERAGE: {
        StrategyType.COVERED_CALL,
        StrategyType.CASH_SECURED_PUT,
        StrategyType.IRON_BUTTERFLY,
        StrategyType.EQUITY_PURCHASE,
    },
    AccountType.AGENTIC: {
        StrategyType.COVERED_CALL,
        StrategyType.CASH_SECURED_PUT,
        StrategyType.IRON_BUTTERFLY,
        StrategyType.EQUITY_PURCHASE,
    },
}

# ============================================================================
# DATA PROVIDER CONFIGURATION
# ============================================================================

class DataProviderConfig(Enum):
    """Data provider priority chain"""
    PRIMARY = "robinhood"      # Robinhood MCP (live account data)
    SECONDARY = "trayd"        # Trayd MCP (alternative broker data)
    TERTIARY = "fiscal"        # Fiscal.ai MCP (fundamental data)
    FALLBACK_1 = "google"      # Google Finance
    FALLBACK_2 = "yahoo"       # Yahoo Finance
    FALLBACK_3 = "cache"       # Local cached data


DATA_PROVIDER_CHAIN = [
    DataProviderConfig.PRIMARY,
    DataProviderConfig.SECONDARY,
    DataProviderConfig.TERTIARY,
    DataProviderConfig.FALLBACK_1,
    DataProviderConfig.FALLBACK_2,
    DataProviderConfig.FALLBACK_3,
]

# MCP Server endpoints
MCP_SERVERS = {
    "robinhood": {
        "host": os.getenv("ROBINHOOD_MCP_HOST", "localhost"),
        "port": int(os.getenv("ROBINHOOD_MCP_PORT", 8001)),
        "auth_token": os.getenv("ROBINHOOD_AUTH_TOKEN", ""),
    },
    "trayd": {
        "host": os.getenv("TRAYD_MCP_HOST", "localhost"),
        "port": int(os.getenv("TRAYD_MCP_PORT", 8002)),
        "api_key": os.getenv("TRAYD_API_KEY", ""),
    },
    "fiscal": {
        "host": os.getenv("FISCAL_MCP_HOST", "localhost"),
        "port": int(os.getenv("FISCAL_MCP_PORT", 8003)),
        "api_key": os.getenv("FISCAL_AI_KEY", ""),
    },
}

# ============================================================================
# PORTFOLIO CONFIGURATION
# ============================================================================

PORTFOLIO_CONFIG = {
    "holdings_file": PORTFOLIO_DIR / "holdings.csv",
    "watchlist_file": WATCHLIST_DIR / "watchlists.csv",
    "max_position_warning": 0.15,      # 15%
    "max_position_critical": 0.20,     # 20%
    "max_sector_warning": 0.30,        # 30%
}

# ============================================================================
# WATCHLIST CONFIGURATION
# ============================================================================

class WatchlistType(Enum):
    """Watchlist classifications"""
    CORE = "CORE"
    INCOME = "INCOME"
    CSP = "CSP"
    GROWTH = "GROWTH"
    AGENTIC = "AGENTIC"


# Scoring model weights (must sum to 100)
SCORING_WEIGHTS = {
    "valuation": 0.25,           # 25%
    "earnings_growth": 0.20,     # 20%
    "free_cash_flow": 0.15,      # 15%
    "dividend_quality": 0.15,    # 15%
    "relative_strength": 0.10,   # 10%
    "diversification": 0.15,     # 15%
}

# ============================================================================
# MARKET REGIME CONFIGURATION
# ============================================================================

class MarketRegime(Enum):
    """Market regime classifications"""
    PREMIUM_SELLING_FRIENDLY = "premium_selling_friendly"
    NEUTRAL = "neutral"
    DEFENSIVE = "defensive"


REGIME_THRESHOLDS = {
    "vix_premium_selling": 20,          # VIX > 20 is premium selling friendly
    "rsi_overbought": 70,               # RSI > 70 is overbought
    "rsi_oversold": 30,                 # RSI < 30 is oversold
    "drawdown_defensive": -0.10,        # -10% drawdown triggers defensive
}

# ============================================================================
# REPORTING CONFIGURATION
# ============================================================================

REPORTING_CONFIG = {
    "reports_dir": REPORTS_DIR,
    "html_template_dir": PROJECT_ROOT / "templates",
    "include_charts": True,
    "include_fundamentals": True,
    "timezone": "US/Eastern",
}

# Market times (US/Eastern)
MARKET_TIMES = {
    "morning_report_time": "06:30",     # 6:30 AM
    "friday_protocol_time": "07:00",    # 7:00 AM Friday
    "stewardship_report_day": 1,        # First trading day of month
}

# ============================================================================
# AGENTIC SANDBOX CONFIGURATION
# ============================================================================

AGENTIC_CONFIG = {
    "min_capital": 500,
    "max_capital": 2000,
    "track_file": DATA_DIR / "agentic_recommendations.csv",
}

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        },
        "simple": {
            "format": "%(levelname)s - %(message)s"
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "level": "INFO",
            "formatter": "simple",
        },
        "file": {
            "class": "logging.FileHandler",
            "level": "DEBUG",
            "formatter": "verbose",
            "filename": LOGS_DIR / "pios.log",
        },
    },
    "root": {
        "level": "DEBUG",
        "handlers": ["console", "file"],
    },
}

# ============================================================================
# CACHE CONFIGURATION
# ============================================================================

CACHE_CONFIG = {
    "cache_dir": CACHE_DIR,
    "market_data_ttl": 300,          # 5 minutes
    "fundamental_data_ttl": 86400,   # 24 hours
    "account_data_ttl": 60,          # 1 minute (real-time priority)
}

# ============================================================================
# RISK GUARDRAILS (Risk-as-Code)
# ============================================================================

RISK_GUARDRAILS = {
    "roth_ira_restricted_strategies": [
        StrategyType.IRON_BUTTERFLY,  # Not allowed in Roth IRA
    ],
    "max_leverage": 1.0,              # No margin/leverage
    "max_portfolio_cash": 0.50,       # Don't hold > 50% cash
    "min_position_size": 100,         # Minimum $100 per trade
}

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_mcp_server_config(provider: str) -> Dict[str, Any]:
    """Get MCP server configuration for a provider"""
    return MCP_SERVERS.get(provider, {})


def validate_strategy_for_account(
    account_type: AccountType,
    strategy_type: StrategyType
) -> bool:
    """Validate that a strategy is allowed for an account type"""
    return strategy_type in ACCOUNT_STRATEGY_MATRIX.get(account_type, set())


def is_production() -> bool:
    """Check if running in production mode"""
    return os.getenv("ENVIRONMENT", "development") == "production"


# ============================================================================
# ENVIRONMENT VARIABLES (with defaults)
# ============================================================================

ENV_CONFIG = {
    "ENVIRONMENT": os.getenv("ENVIRONMENT", "development"),
    "DEBUG": os.getenv("DEBUG", "False").lower() == "true",
    "LOG_LEVEL": os.getenv("LOG_LEVEL", "INFO"),
    "DATA_PROVIDER": os.getenv("DATA_PROVIDER", "robinhood"),
}
