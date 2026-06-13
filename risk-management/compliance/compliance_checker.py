"""
Compliance Checker — Fortress Edition PIOS
Regulatory and platform-level compliance validation.
Runs BEFORE any order reaches the guardrails or execution layer.
"""

import logging
from typing import Tuple, Optional
from datetime import date

logger = logging.getLogger(__name__)

# Robinhood platform constraints
ROBINHOOD_MIN_PRICE_FOR_OPTIONS = 1.00    # Stocks under $1 have no options
ROBINHOOD_MIN_PREMIUM           = 0.05    # Minimum premium per contract
ROBINHOOD_LEVEL_2_REQUIRED      = True    # CSPs require Level 2 approval


def check_robinhood_constraints(
    ticker: str,
    stock_price: float,
    strike: float,
    premium: float,
    strategy: str,
    expiration: str,
) -> Tuple[bool, Optional[str]]:
    """
    Validate against known Robinhood platform constraints.
    Returns (passed, error_message).
    """
    # Stock price floor
    if stock_price < ROBINHOOD_MIN_PRICE_FOR_OPTIONS:
        return False, (
            f"{ticker} at ${stock_price:.2f} is below Robinhood's "
            f"${ROBINHOOD_MIN_PRICE_FOR_OPTIONS:.2f} minimum for listed options."
        )

    # Strike increment validation
    if stock_price < 3.00:
        increment = 0.50
    else:
        increment = 0.50
    remainder = round(strike % increment, 4)
    if remainder not in (0.0, increment):
        return False, (
            f"Strike ${strike} is not a valid increment "
            f"(${increment} increments required for ${stock_price:.2f} stocks)."
        )

    # Premium floor
    if 0 < premium < ROBINHOOD_MIN_PREMIUM:
        return False, (
            f"Premium ${premium:.2f} is below Robinhood minimum "
            f"${ROBINHOOD_MIN_PREMIUM:.2f} per contract."
        )

    # Expiration must be in the future
    try:
        exp_date = date.fromisoformat(expiration)
        if exp_date <= date.today():
            return False, f"Expiration {expiration} has already passed."
    except ValueError:
        return False, f"Invalid expiration format: {expiration} (expected YYYY-MM-DD)."

    return True, None


def check_wash_sale_risk(
    ticker: str,
    side: str,
    recent_transactions: list,
    lookback_days: int = 30,
) -> Tuple[bool, Optional[str]]:
    """
    Flag potential wash sale scenarios (sold at loss within 30 days).
    Returns (safe, warning_message). Non-blocking — returns warning, not error.
    """
    if side != "sell":
        return True, None

    recent_losses = [
        t for t in recent_transactions
        if t.get("ticker") == ticker
        and t.get("realized_pnl", 0) < 0
        and t.get("days_ago", 999) <= lookback_days
    ]

    if recent_losses:
        return True, (
            f"[⚠️ WASH SALE RISK] {ticker} had a loss transaction within "
            f"{lookback_days} days. Consult a tax advisor."
        )
    return True, None
