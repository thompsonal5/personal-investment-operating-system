"""
Strategy Validator — Fortress Edition PIOS
Account-level strategy compliance enforcement.
These checks run BEFORE any order is placed.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Account → allowed strategies map (mirrors config.py ACCOUNT_STRATEGY_MATRIX)
ACCOUNT_STRATEGY_MAP = {
    "821132974": {"covered_call", "cash_secured_put", "equity_purchase"},          # Roth IRA
    "662458413": {"covered_call", "cash_secured_put", "iron_butterfly", "equity_purchase"},  # Brokerage
    "636778128": {"covered_call", "cash_secured_put", "iron_butterfly", "equity_purchase"},  # Agentic
}

ACCOUNT_LABELS = {
    "821132974": "Roth IRA",
    "662458413": "Brokerage",
    "636778128": "Agentic Sandbox",
}


def validate_strategy(account_id: str, strategy: str) -> tuple[bool, Optional[str]]:
    """
    Returns (is_valid, error_message).
    If valid, error_message is None.
    """
    strategy = strategy.lower().replace(" ", "_")
    allowed = ACCOUNT_STRATEGY_MAP.get(account_id)

    if allowed is None:
        return False, f"Unknown account ID: {account_id}"

    if strategy not in allowed:
        label = ACCOUNT_LABELS.get(account_id, account_id)
        return False, (
            f"[RISK VIOLATION] '{strategy}' is NOT permitted in {label}. "
            f"Allowed: {', '.join(sorted(allowed))}"
        )

    return True, None


def validate_buying_power(
    available_bp: float,
    required_collateral: float,
    account_id: str,
) -> tuple[bool, Optional[str]]:
    """Confirm sufficient buying power before order submission."""
    if available_bp < required_collateral:
        label = ACCOUNT_LABELS.get(account_id, account_id)
        return False, (
            f"[INSUFFICIENT FUNDS] {label} has ${available_bp:,.2f} buying power "
            f"but trade requires ${required_collateral:,.2f} collateral."
        )
    return True, None


def validate_position_size(
    collateral: float,
    total_account_equity: float,
    max_pct: float = 0.20,
) -> tuple[bool, Optional[str]]:
    """Block if a single position exceeds max_pct of account equity."""
    if total_account_equity <= 0:
        return False, "Account equity is zero — cannot size position."
    pct = collateral / total_account_equity
    if pct > max_pct:
        return False, (
            f"[POSITION LIMIT] Trade represents {pct:.1%} of account equity "
            f"(max allowed: {max_pct:.1%})."
        )
    return True, None
