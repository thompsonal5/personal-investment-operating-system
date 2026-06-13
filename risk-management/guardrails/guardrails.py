"""
Risk Guardrails — Fortress Edition PIOS
Hard limits that can never be bypassed at runtime.
These are the last line of defense before order submission.
"""

import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Hard limits
MAX_CONTRACTS_PER_TICKER       = 20     # Never more than 20 contracts on one ticker
MAX_ACCOUNT_UTILIZATION_PCT    = 0.80   # Never deploy > 80% of account BP
MIN_BUYING_POWER_RESERVE       = 200.0  # Always keep $200 in reserve
MAX_SINGLE_POSITION_PCT        = 0.20   # 20% of equity per position
VIX_HARD_STOP                  = 40.0   # No new entries when VIX > 40


def check_all(
    account_id: str,
    ticker: str,
    contracts: int,
    collateral: float,
    account_equity: float,
    account_bp: float,
    vix: float,
    strategy: str,
) -> Tuple[bool, Optional[str]]:
    """
    Run all guardrail checks in sequence.
    Returns (passed, error_message). First failure blocks the trade.
    """
    checks = [
        lambda: _check_vix(vix),
        lambda: _check_contract_limit(ticker, contracts),
        lambda: _check_bp_reserve(account_bp, collateral),
        lambda: _check_account_utilization(account_bp, collateral, account_equity),
        lambda: _check_position_concentration(collateral, account_equity),
    ]

    for check in checks:
        passed, msg = check()
        if not passed:
            logger.error(f"[GUARDRAIL BLOCKED] {account_id}/{ticker}: {msg}")
            return False, msg

    return True, None


def _check_vix(vix: float) -> Tuple[bool, Optional[str]]:
    if vix > VIX_HARD_STOP:
        return False, f"VIX {vix:.1f} exceeds hard stop {VIX_HARD_STOP} — no new entries."
    return True, None


def _check_contract_limit(ticker: str, contracts: int) -> Tuple[bool, Optional[str]]:
    if contracts > MAX_CONTRACTS_PER_TICKER:
        return False, (
            f"{contracts} contracts on {ticker} exceeds max "
            f"{MAX_CONTRACTS_PER_TICKER} per ticker."
        )
    return True, None


def _check_bp_reserve(account_bp: float, collateral: float) -> Tuple[bool, Optional[str]]:
    remaining = account_bp - collateral
    if remaining < MIN_BUYING_POWER_RESERVE:
        return False, (
            f"Trade would leave ${remaining:.2f} BP — below minimum "
            f"reserve ${MIN_BUYING_POWER_RESERVE:.2f}."
        )
    return True, None


def _check_account_utilization(
    account_bp: float, collateral: float, equity: float
) -> Tuple[bool, Optional[str]]:
    if equity <= 0:
        return True, None
    utilization = (equity * MAX_ACCOUNT_UTILIZATION_PCT - account_bp + collateral) / equity
    if account_bp > 0 and (collateral / account_bp) > MAX_ACCOUNT_UTILIZATION_PCT:
        return False, (
            f"Trade would utilize {(collateral/account_bp):.0%} of buying power "
            f"(max {MAX_ACCOUNT_UTILIZATION_PCT:.0%})."
        )
    return True, None


def _check_position_concentration(
    collateral: float, equity: float
) -> Tuple[bool, Optional[str]]:
    if equity <= 0:
        return True, None
    pct = collateral / equity
    if pct > MAX_SINGLE_POSITION_PCT:
        return False, (
            f"Position is {pct:.1%} of account equity "
            f"(max {MAX_SINGLE_POSITION_PCT:.0%})."
        )
    return True, None
