"""
Order Handler — Fortress Edition PIOS
Pre-flight validation → risk check → execution → confirmation.
Every order must clear all three gates before reaching the broker.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from governance_protocol.validators.strategy_validator import (
    validate_strategy, validate_buying_power, validate_position_size
)
from governance_protocol.validators.p1_p2_p3_chain import run_triangulation, SignalStrength

logger = logging.getLogger(__name__)


@dataclass
class OrderRequest:
    account_id: str
    ticker: str
    strategy: str
    side: str                    # "buy" | "sell"
    quantity: int
    strike: Optional[float]
    expiration: Optional[str]
    order_type: str = "limit"
    limit_price: Optional[float] = None
    collateral: float = 0.0
    available_bp: float = 0.0
    account_equity: float = 0.0


@dataclass
class OrderResult:
    approved: bool
    order_id: Optional[str] = None
    rejection_reason: Optional[str] = None
    warnings: list = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


class OrderHandler:
    """
    Orchestrates pre-flight checks and routes approved orders to the broker.
    Three-stage pipeline:
        1. Account compliance (strategy lock)
        2. Capital sufficiency (buying power + position size)
        3. Signal validity (P1/P2/P3 chain — must be pre-computed by caller)
    """

    def __init__(self, broker_interface):
        self.broker = broker_interface

    def submit(
        self,
        order: OrderRequest,
        chain_signal: Optional[SignalStrength] = None,
    ) -> OrderResult:
        """
        Full pre-flight + execution pipeline.
        chain_signal must be passed in from a completed P1/P2/P3 evaluation.
        """
        warnings = []

        # Stage 1 — Account compliance
        valid, error = validate_strategy(order.account_id, order.strategy)
        if not valid:
            logger.error(f"[OrderHandler] BLOCKED — compliance: {error}")
            return OrderResult(approved=False, rejection_reason=error)

        # Stage 2 — Capital sufficiency
        valid, error = validate_buying_power(
            order.available_bp, order.collateral, order.account_id
        )
        if not valid:
            logger.error(f"[OrderHandler] BLOCKED — capital: {error}")
            return OrderResult(approved=False, rejection_reason=error)

        if order.account_equity > 0:
            valid, error = validate_position_size(
                order.collateral, order.account_equity, max_pct=0.20
            )
            if not valid:
                logger.warning(f"[OrderHandler] WARN — position size: {error}")
                warnings.append(error)

        # Stage 3 — Signal check
        if chain_signal == SignalStrength.BLOCKED:
            msg = "P1/P2/P3 chain returned BLOCKED — trade not authorized."
            logger.error(f"[OrderHandler] BLOCKED — signal: {msg}")
            return OrderResult(approved=False, rejection_reason=msg)

        if chain_signal == SignalStrength.NORMAL:
            warnings.append("Trade approved with warnings — review flags before confirming.")

        # Execute
        logger.info(
            f"[OrderHandler] Submitting: {order.side.upper()} {order.quantity}x "
            f"{order.ticker} {order.strategy} @ {order.limit_price}"
        )
        try:
            result = self.broker.place_order(
                account_id=order.account_id,
                ticker=order.ticker,
                side=order.side,
                quantity=order.quantity,
                order_type=order.order_type,
                limit_price=order.limit_price,
            )
            if result.success:
                order_id = result.data.get("order_id", "N/A") if result.data else "N/A"
                logger.info(f"[OrderHandler] Order confirmed: {order_id}")
                return OrderResult(approved=True, order_id=order_id, warnings=warnings)
            else:
                return OrderResult(
                    approved=False,
                    rejection_reason=result.error or "Broker rejected order.",
                    warnings=warnings,
                )
        except Exception as e:
            logger.error(f"[OrderHandler] Execution error: {e}")
            return OrderResult(approved=False, rejection_reason=str(e), warnings=warnings)
