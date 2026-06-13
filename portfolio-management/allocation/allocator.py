"""
Portfolio Allocator — Fortress Edition PIOS
Manages capital deployment across accounts, position sizing,
and Wheel strategy assignment tracking.

Core responsibilities:
    - Enforce per-position max allocation (20% of account equity)
    - Track collateral consumed vs. available buying power
    - Identify covered call opportunities from existing long positions
    - Surface rolling candidates (positions near expiry or in profit)
    - Generate deployment recommendations by account
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from datetime import datetime, date

logger = logging.getLogger(__name__)

# ============================================================================
# Constants (from Fortress Edition OCC)
# ============================================================================

MAX_SINGLE_POSITION_PCT  = 0.20   # 20% of account equity per position
CC_ELIGIBLE_MIN_SHARES   = 100    # Must hold ≥100 shares for 1 CC contract
ROLL_PROFIT_THRESHOLD    = 0.80   # Roll when position at 80%+ of max profit
ROLL_DTE_THRESHOLD       = 7      # Roll when ≤7 DTE remains

# Robinhood-specific
STRIKE_INCREMENT_UNDER_3 = 0.50
STRIKE_INCREMENT_OVER_3  = 0.50
MIN_PREMIUM_ABSOLUTE     = 0.05   # Don't chase < $5 premium per contract


# ============================================================================
# Data structures
# ============================================================================

@dataclass
class AccountSnapshot:
    account_id:    str
    label:         str
    equity:        float
    cash:          float
    buying_power:  float
    positions:     List[Dict] = field(default_factory=list)

    @property
    def collateral_consumed(self) -> float:
        """Cash minus buying power = collateral held for open short options."""
        delta = self.cash - self.buying_power
        return max(0.0, delta)

    @property
    def free_capital(self) -> float:
        return self.buying_power

    @property
    def cc_eligible(self) -> List[Dict]:
        """Positions with ≥100 shares (covered call candidates)."""
        return [
            p for p in self.positions
            if float(p.get("quantity", 0)) >= CC_ELIGIBLE_MIN_SHARES
            and float(p.get("average_price", 0)) >= 1.0   # options must exist
        ]

    @property
    def cc_contracts_available(self) -> Dict[str, int]:
        """Map of ticker → number of CC contracts available."""
        return {
            p["ticker"]: int(float(p["quantity"]) // 100)
            for p in self.cc_eligible
        }


@dataclass
class AllocationRecommendation:
    account_id:    str
    ticker:        str
    strategy:      str
    contracts:     int
    collateral:    float
    max_risk:      float
    pct_of_equity: float
    rationale:     str
    warnings:      List[str] = field(default_factory=list)

    @property
    def is_within_limits(self) -> bool:
        return self.pct_of_equity <= MAX_SINGLE_POSITION_PCT


@dataclass
class RollCandidate:
    account_id: str
    ticker:     str
    strategy:   str
    strike:     float
    expiration: str
    dte:        int
    current_value: float
    original_credit: float
    profit_pct:    float
    roll_reason:   str       # "PROFIT_TARGET" | "DTE_THRESHOLD" | "MANUAL"


# ============================================================================
# Allocator
# ============================================================================

class PortfolioAllocator:
    """
    Capital deployment engine for the Fortress Edition Wheel strategy.

    Typical session flow:
        1. Load account snapshots from Trayd
        2. allocator.analyze(snapshots) → recommendations + roll candidates
        3. Pass recommendations through P1/P2/P3 chain before execution
    """

    def __init__(self):
        self._snapshots: Dict[str, AccountSnapshot] = {}
        self._history: List[Dict] = []

    def load_snapshot(self, snapshot: AccountSnapshot) -> None:
        self._snapshots[snapshot.account_id] = snapshot
        logger.info(
            f"[Allocator] Loaded {snapshot.label}: "
            f"equity=${snapshot.equity:,.2f}, BP=${snapshot.buying_power:,.2f}, "
            f"collateral_consumed=${snapshot.collateral_consumed:,.2f}"
        )

    # ------------------------------------------------------------------
    # Primary analysis entry point
    # ------------------------------------------------------------------

    def analyze(self) -> Tuple[List[AllocationRecommendation], List[RollCandidate]]:
        """
        Run full deployment analysis across all loaded accounts.
        Returns (recommendations, roll_candidates).
        """
        recommendations: List[AllocationRecommendation] = []
        roll_candidates: List[RollCandidate] = []

        for account_id, snap in self._snapshots.items():
            recs  = self._analyze_account(snap)
            rolls = self._find_roll_candidates(snap)
            recommendations.extend(recs)
            roll_candidates.extend(rolls)

        # Sort recommendations by collateral efficiency (ROI proxy)
        recommendations.sort(key=lambda r: r.pct_of_equity)
        return recommendations, roll_candidates

    # ------------------------------------------------------------------
    # Account-level analysis
    # ------------------------------------------------------------------

    def _analyze_account(self, snap: AccountSnapshot) -> List[AllocationRecommendation]:
        recs = []

        # 1. Covered call opportunities (no capital required)
        for ticker, contracts in snap.cc_contracts_available.items():
            position = next(p for p in snap.cc_eligible if p["ticker"] == ticker)
            price = float(position.get("current_price", position.get("average_price", 0)))
            if price < 1.0:
                continue

            rec = AllocationRecommendation(
                account_id=snap.account_id,
                ticker=ticker,
                strategy="covered_call",
                contracts=contracts,
                collateral=0.0,            # No new capital needed — shares are collateral
                max_risk=0.0,
                pct_of_equity=0.0,
                rationale=(
                    f"{contracts} contract(s) available from {int(contracts*100)} shares. "
                    f"Current price ~${price:.2f}. No buying power consumed."
                ),
            )
            recs.append(rec)

        # 2. CSP opportunities (requires buying power)
        if snap.free_capital >= 300:
            recs.extend(self._build_csp_recommendations(snap))

        # 3. Iron butterfly (brokerage only — enforced upstream by strategy_validator)
        if snap.free_capital >= 200:
            recs.extend(self._build_iron_butterfly_recommendations(snap))

        return recs

    def _build_csp_recommendations(
        self, snap: AccountSnapshot
    ) -> List[AllocationRecommendation]:
        """
        Surface CSP opportunities given available buying power.
        Applies the 1%-of-budget strike cap formula.
        """
        recs = []
        bp = snap.free_capital

        # 1% strike cap: strike ≤ bp * 0.01
        # e.g., $814 BP → max strike $8.14 → NIO $5 is viable, F $14 is not
        max_strike = bp * 0.01

        # NIO at ~$5.30 — viable if bp ≥ $500
        if bp >= 500:
            collateral = 500.0   # $5 strike × 100
            pct = collateral / snap.equity if snap.equity > 0 else 1.0
            recs.append(AllocationRecommendation(
                account_id=snap.account_id,
                ticker="NIO",
                strategy="cash_secured_put",
                contracts=1,
                collateral=collateral,
                max_risk=collateral,
                pct_of_equity=pct,
                rationale=(
                    f"NIO $5 CSP: $500 collateral, {pct:.1%} of equity. "
                    f"1% strike cap: max strike ${max_strike:.2f} — $5 qualifies."
                ),
                warnings=(
                    ["[⚠️ DoD Chinese military designation Jun 9, 2026]"]
                    if True else []  # flag always active until rescinded
                ),
            ))

        return recs

    def _build_iron_butterfly_recommendations(
        self, snap: AccountSnapshot
    ) -> List[AllocationRecommendation]:
        """Surface IWM iron butterfly sizing given available capital."""
        recs = []
        bp = snap.free_capital

        # IWM iron butterfly — $339 max risk per contract at $292 ATM, $10 wings
        max_risk_per_contract = 339.0
        max_contracts = int(bp * 0.20 / max_risk_per_contract)   # 20% of BP max
        if max_contracts < 1:
            return recs

        contracts = min(max_contracts, 5)   # cap at 5 for concentration risk
        total_risk = contracts * max_risk_per_contract
        pct = total_risk / snap.equity if snap.equity > 0 else 1.0

        recs.append(AllocationRecommendation(
            account_id=snap.account_id,
            ticker="IWM",
            strategy="iron_butterfly",
            contracts=contracts,
            collateral=total_risk,
            max_risk=total_risk,
            pct_of_equity=pct,
            rationale=(
                f"IWM iron butterfly: {contracts} contracts × ${max_risk_per_contract:.0f} max risk "
                f"= ${total_risk:,.0f} total at risk ({pct:.1%} of equity). "
                f"Jun 30 $282/$292/$292/$302, ~$6.61 net credit."
            ),
            warnings=["[⚠️ Gap-up day — wait 30–60 min after open before entering]"],
        ))

        return recs

    # ------------------------------------------------------------------
    # Roll candidate identification
    # ------------------------------------------------------------------

    def _find_roll_candidates(self, snap: AccountSnapshot) -> List[RollCandidate]:
        """
        Identify open short option positions that should be rolled.
        Criteria: profit ≥ 80% of max OR DTE ≤ 7.
        """
        candidates = []
        today = date.today()

        for pos in snap.positions:
            if pos.get("instrument_type") not in ("option", "put", "call"):
                continue

            try:
                expiration = datetime.strptime(pos["expiration_date"], "%Y-%m-%d").date()
                dte = (expiration - today).days
                strike = float(pos.get("strike_price", 0))
                current_value = float(pos.get("market_value", 0))
                original_credit = float(pos.get("average_price", 0)) * 100 * abs(float(pos.get("quantity", 1)))
                profit_pct = 1 - (abs(current_value) / original_credit) if original_credit else 0

                reasons = []
                if profit_pct >= ROLL_PROFIT_THRESHOLD:
                    reasons.append("PROFIT_TARGET")
                if dte <= ROLL_DTE_THRESHOLD:
                    reasons.append("DTE_THRESHOLD")

                if reasons:
                    candidates.append(RollCandidate(
                        account_id=snap.account_id,
                        ticker=pos.get("ticker", ""),
                        strategy=pos.get("option_type", "put"),
                        strike=strike,
                        expiration=pos.get("expiration_date", ""),
                        dte=dte,
                        current_value=current_value,
                        original_credit=original_credit,
                        profit_pct=profit_pct,
                        roll_reason=" + ".join(reasons),
                    ))
            except (KeyError, ValueError, TypeError):
                continue

        return candidates

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def deployment_summary(self) -> str:
        """Human-readable capital deployment summary for session output."""
        lines = []
        for snap in self._snapshots.values():
            lines.append(
                f"\n{'='*60}\n"
                f"{snap.label} ({snap.account_id})\n"
                f"  Equity:            ${snap.equity:>12,.2f}\n"
                f"  Cash:              ${snap.cash:>12,.2f}\n"
                f"  Buying Power:      ${snap.buying_power:>12,.2f}\n"
                f"  Collateral in use: ${snap.collateral_consumed:>12,.2f}\n"
                f"  CC-eligible tickers: {list(snap.cc_contracts_available.keys())}"
            )
        return "\n".join(lines)

    def max_new_position_size(self, account_id: str) -> float:
        """Max collateral for a single new position (20% of equity)."""
        snap = self._snapshots.get(account_id)
        if not snap:
            return 0.0
        return min(snap.free_capital, snap.equity * MAX_SINGLE_POSITION_PCT)
