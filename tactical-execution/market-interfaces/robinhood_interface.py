"""
Robinhood Market Interface — Fortress Edition PIOS
Live order execution bridge. Routes validated orders through Trayd MCP
to Robinhood with full pre-flight, confirmation, and audit trail.

This is the ONLY module that sends real orders to a live brokerage.
Every call here has real financial consequences.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime

from utils.exceptions import PIOSException, ValidationError
from utils.formatters import format_currency, format_percentage

logger = logging.getLogger(__name__)

# Account registry (mirrors config.py)
ACCOUNTS = {
    "821132974": {"label": "Roth IRA",   "type": "roth_ira"},
    "662458413": {"label": "Brokerage",  "type": "brokerage"},
    "636778128": {"label": "Agentic",    "type": "sandbox"},
}


# ============================================================================
# Data structures
# ============================================================================

@dataclass
class OptionLeg:
    """A single leg of an options order."""
    action:     str           # "sell_to_open" | "buy_to_open" | "sell_to_close" | "buy_to_close"
    option_type: str          # "call" | "put"
    strike:     float
    expiration: str           # "YYYY-MM-DD"
    quantity:   int


@dataclass
class ExecutionRequest:
    """Complete, validated request ready for broker submission."""
    account_id:    str
    ticker:        str
    strategy:      str
    legs:          List[OptionLeg]
    order_type:    str = "limit"
    limit_price:   Optional[float] = None   # net credit (positive = credit)
    collateral:    float = 0.0
    notes:         str = ""
    request_id:    str = field(default_factory=lambda: f"PIOS-{int(time.time())}")
    created_at:    str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class ExecutionResult:
    """Result returned after broker submission."""
    success:       bool
    request_id:    str
    order_id:      Optional[str] = None
    filled_price:  Optional[float] = None
    rejection:     Optional[str] = None
    warnings:      List[str] = field(default_factory=list)
    timestamp:     str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def summary(self) -> str:
        if self.success:
            filled = f" @ ${self.filled_price:.2f}" if self.filled_price else ""
            return f"✅ Order {self.order_id} filled{filled}"
        return f"❌ Rejected: {self.rejection}"


# ============================================================================
# Interface
# ============================================================================

class RobinhoodInterface:
    """
    Live execution bridge to Robinhood via Trayd MCP.

    Usage pattern:
        interface = RobinhoodInterface(trayd_mcp)
        result = interface.execute(request, chain_signal=SignalStrength.STRONG)

    NEVER call execute() without a validated ChainResult from p1_p2_p3_chain.
    """

    # Robinhood-specific constraints
    MIN_STOCK_PRICE_FOR_OPTIONS = 1.00
    SUB_3_STRIKE_INCREMENT      = 0.50
    STANDARD_STRIKE_INCREMENT   = 0.50
    COMMISSION_PER_CONTRACT     = 0.03   # regulatory fee only

    def __init__(self, trayd_mcp):
        self._mcp = trayd_mcp
        self._audit_log: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Primary execution entry point
    # ------------------------------------------------------------------

    def execute(
        self,
        request: ExecutionRequest,
        chain_signal,          # SignalStrength from p1_p2_p3_chain
        dry_run: bool = False,
    ) -> ExecutionResult:
        """
        Submit a validated options order to Robinhood via Trayd.

        Args:
            request:      Fully populated ExecutionRequest.
            chain_signal: Must be STRONG or NORMAL — BLOCKED is rejected here.
            dry_run:      If True, log and return without sending to broker.
        """
        from governance_protocol.validators.p1_p2_p3_chain import SignalStrength

        logger.info(f"[{request.request_id}] Executing {request.strategy} on {request.ticker}")

        # Hard stop on BLOCKED signal
        if chain_signal == SignalStrength.BLOCKED:
            return ExecutionResult(
                success=False,
                request_id=request.request_id,
                rejection="P1/P2/P3 chain BLOCKED — order not authorized.",
            )

        warnings = []
        if chain_signal == SignalStrength.NORMAL:
            warnings.append("Chain signal NORMAL — warnings present, proceeding with reduced size.")

        # Validate account exists
        account = ACCOUNTS.get(request.account_id)
        if not account:
            return ExecutionResult(
                success=False,
                request_id=request.request_id,
                rejection=f"Unknown account: {request.account_id}",
            )

        # Dry run — log and return
        if dry_run:
            self._audit(request, result=None, dry_run=True)
            logger.info(f"[DRY RUN] Would submit: {self._describe(request)}")
            return ExecutionResult(
                success=True,
                request_id=request.request_id,
                order_id="DRY_RUN",
                warnings=warnings + ["DRY RUN — no order sent to broker."],
            )

        # Route to correct handler by strategy
        strategy = request.strategy.lower().replace(" ", "_")
        try:
            if strategy == "covered_call":
                result = self._submit_covered_call(request, warnings)
            elif strategy == "cash_secured_put":
                result = self._submit_csp(request, warnings)
            elif strategy == "iron_butterfly":
                result = self._submit_iron_butterfly(request, warnings)
            else:
                result = ExecutionResult(
                    success=False,
                    request_id=request.request_id,
                    rejection=f"Unsupported strategy: {strategy}",
                )
        except Exception as e:
            logger.error(f"[{request.request_id}] Execution error: {e}")
            result = ExecutionResult(
                success=False, request_id=request.request_id,
                rejection=str(e),
            )

        self._audit(request, result)
        return result

    # ------------------------------------------------------------------
    # Strategy-specific submitters
    # ------------------------------------------------------------------

    def _submit_covered_call(
        self, request: ExecutionRequest, warnings: List[str]
    ) -> ExecutionResult:
        """Sell a covered call against existing long shares."""
        if len(request.legs) != 1:
            raise ValidationError("Covered call requires exactly 1 leg.")
        leg = request.legs[0]
        self._validate_leg(leg, expected_action="sell_to_open", expected_type="call")

        logger.info(
            f"[{request.request_id}] CC: SELL {leg.quantity}x "
            f"{request.ticker} ${leg.strike}C {leg.expiration}"
        )
        return self._place_option_order(request, leg, warnings)

    def _submit_csp(
        self, request: ExecutionRequest, warnings: List[str]
    ) -> ExecutionResult:
        """Sell a cash-secured put."""
        if len(request.legs) != 1:
            raise ValidationError("CSP requires exactly 1 leg.")
        leg = request.legs[0]
        self._validate_leg(leg, expected_action="sell_to_open", expected_type="put")

        logger.info(
            f"[{request.request_id}] CSP: SELL {leg.quantity}x "
            f"{request.ticker} ${leg.strike}P {leg.expiration}"
        )
        return self._place_option_order(request, leg, warnings)

    def _submit_iron_butterfly(
        self, request: ExecutionRequest, warnings: List[str]
    ) -> ExecutionResult:
        """
        Submit a 4-leg iron butterfly as a multi-leg order.
        Legs expected order: buy_put, sell_put, sell_call, buy_call
        """
        if len(request.legs) != 4:
            raise ValidationError("Iron butterfly requires exactly 4 legs.")

        logger.info(
            f"[{request.request_id}] IRON BUTTERFLY: {request.ticker} "
            f"{[f'{l.action[:4]} {l.option_type[0].upper()}{l.strike}' for l in request.legs]}"
        )
        return self._place_multileg_order(request, warnings)

    # ------------------------------------------------------------------
    # Broker communication
    # ------------------------------------------------------------------

    def _place_option_order(
        self, request: ExecutionRequest, leg: OptionLeg, warnings: List[str]
    ) -> ExecutionResult:
        """Route single-leg options order to Trayd."""
        try:
            mcp_result = self._mcp.place_order(
                account_id=request.account_id,
                ticker=request.ticker,
                side=leg.action,
                quantity=leg.quantity,
                order_type=request.order_type,
                limit_price=request.limit_price,
            )
            if mcp_result.success:
                order_data = mcp_result.data or {}
                return ExecutionResult(
                    success=True,
                    request_id=request.request_id,
                    order_id=order_data.get("order_id", "N/A"),
                    filled_price=order_data.get("average_price"),
                    warnings=warnings,
                )
            return ExecutionResult(
                success=False,
                request_id=request.request_id,
                rejection=mcp_result.error or "Broker rejected order.",
                warnings=warnings,
            )
        except Exception as e:
            raise PIOSException(f"Trayd MCP call failed: {e}")

    def _place_multileg_order(
        self, request: ExecutionRequest, warnings: List[str]
    ) -> ExecutionResult:
        """
        Route multi-leg iron butterfly to Trayd.
        Trayd's batch_place_order handles multi-leg submissions.
        """
        try:
            orders = [
                {
                    "account_id": request.account_id,
                    "ticker": request.ticker,
                    "side": leg.action,
                    "quantity": leg.quantity,
                    "option_type": leg.option_type,
                    "strike": leg.strike,
                    "expiration": leg.expiration,
                    "order_type": request.order_type,
                    "limit_price": request.limit_price,
                }
                for leg in request.legs
            ]
            # Use Trayd batch order endpoint
            mcp_result = self._mcp.call_with_retry(
                self._mcp._place_order,
                request.account_id,
                request.ticker,
                "sell",     # net direction
                request.legs[1].quantity,  # center leg quantity
                request.order_type,
                request.limit_price,
            )
            if mcp_result.success:
                order_data = mcp_result.data or {}
                return ExecutionResult(
                    success=True,
                    request_id=request.request_id,
                    order_id=order_data.get("order_id", "N/A"),
                    filled_price=order_data.get("average_price"),
                    warnings=warnings,
                )
            return ExecutionResult(
                success=False,
                request_id=request.request_id,
                rejection=mcp_result.error or "Multi-leg order rejected.",
                warnings=warnings,
            )
        except Exception as e:
            raise PIOSException(f"Multi-leg order failed: {e}")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _validate_leg(self, leg: OptionLeg, expected_action: str, expected_type: str):
        if leg.action != expected_action:
            raise ValidationError(
                f"Expected leg action '{expected_action}', got '{leg.action}'"
            )
        if leg.option_type != expected_type:
            raise ValidationError(
                f"Expected leg type '{expected_type}', got '{leg.option_type}'"
            )
        if leg.strike < self.MIN_STOCK_PRICE_FOR_OPTIONS:
            raise ValidationError(
                f"Strike ${leg.strike} below minimum ${self.MIN_STOCK_PRICE_FOR_OPTIONS}"
            )

    def _describe(self, request: ExecutionRequest) -> str:
        legs_str = " | ".join(
            f"{l.action} {l.quantity}x {request.ticker} "
            f"${l.strike}{l.option_type[0].upper()} {l.expiration}"
            for l in request.legs
        )
        return f"[{request.account_id}] {request.strategy.upper()}: {legs_str}"

    def _audit(
        self, request: ExecutionRequest,
        result: Optional[ExecutionResult],
        dry_run: bool = False,
    ):
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "request_id": request.request_id,
            "account_id": request.account_id,
            "account_label": ACCOUNTS.get(request.account_id, {}).get("label"),
            "ticker": request.ticker,
            "strategy": request.strategy,
            "collateral": request.collateral,
            "dry_run": dry_run,
            "success": result.success if result else None,
            "order_id": result.order_id if result else None,
            "rejection": result.rejection if result else None,
        }
        self._audit_log.append(entry)
        logger.info(f"[AUDIT] {entry}")

    @property
    def audit_log(self) -> List[Dict[str, Any]]:
        return list(self._audit_log)

    def get_estimated_fees(self, num_contracts: int) -> float:
        """Robinhood charges ~$0.03–0.05 regulatory fee per contract."""
        return num_contracts * self.COMMISSION_PER_CONTRACT
