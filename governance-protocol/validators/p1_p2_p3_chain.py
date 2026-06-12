"""
P1 → P2 → P3 Triangulation Chain — Fortress Edition PIOS
The three-gate validation system that every trade signal must pass.

P1 — Market Regime (macro gating)
P2 — Underlying Quality (fundamental + volatility gating)
P3 — Premium Yield (return threshold gating)

A signal is VALID only when all three gates return PASS.
Any single FAIL blocks the trade. The chain is deterministic.
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


# ============================================================================
# Data structures
# ============================================================================

class GateResult(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARN = "WARN"       # Passes but with a risk flag attached


class SignalStrength(Enum):
    STRONG  = "STRONG"   # All three gates PASS cleanly
    NORMAL  = "NORMAL"   # All PASS, at least one WARN
    BLOCKED = "BLOCKED"  # At least one FAIL


@dataclass
class P1Result:
    gate: GateResult
    vix: float
    regime: str
    notes: str = ""


@dataclass
class P2Result:
    gate: GateResult
    quality_tier: str          # HIGH / MEDIUM / LOW
    iv_rank: Optional[float]
    earnings_days_out: Optional[int]
    dividend_days_out: Optional[int]
    flags: list = None

    def __post_init__(self):
        if self.flags is None:
            self.flags = []


@dataclass
class P3Result:
    gate: GateResult
    roi_pct: float             # Return as % of collateral for the DTE
    ann_roi_pct: float         # Annualized ROI %
    dte: int
    premium: float
    collateral: float
    notes: str = ""


@dataclass
class ChainResult:
    ticker: str
    strategy: str
    p1: P1Result
    p2: P2Result
    p3: P3Result
    signal: SignalStrength
    signal_notes: str = ""

    @property
    def is_valid(self) -> bool:
        return self.signal != SignalStrength.BLOCKED

    def summary(self) -> str:
        gates = f"P1={self.p1.gate.value} | P2={self.p2.gate.value} | P3={self.p3.gate.value}"
        return (
            f"[{self.ticker}] {self.strategy.upper()} | {gates} | "
            f"Signal={self.signal.value} | Ann.ROI={self.p3.ann_roi_pct:.1f}%"
        )


# ============================================================================
# P1 — Market Regime Gate
# ============================================================================

# Thresholds from config.py REGIME_THRESHOLDS
VIX_PREMIUM_FRIENDLY   = 25.0   # VIX > 25 → PREMIUM_SELLING_FRIENDLY
VIX_NEUTRAL_LOWER      = 18.0   # 18 ≤ VIX ≤ 25 → NEUTRAL
VIX_DEFENSIVE          = 18.0   # VIX < 18 → DEFENSIVE (low premium, reduce size)
VIX_EXTREME            = 40.0   # VIX > 40 → block all new entries


def evaluate_p1(vix: float) -> P1Result:
    """
    Classify market regime from VIX.

    > 40  → BLOCKED (tail risk, no new positions)
    > 25  → PREMIUM_SELLING_FRIENDLY (PASS, elevated premium)
    18-25 → NEUTRAL (PASS, selective premium selling)
    < 18  → DEFENSIVE (WARN, thin premium, reduce contract count)
    """
    if vix > VIX_EXTREME:
        return P1Result(
            gate=GateResult.FAIL,
            vix=vix,
            regime="EXTREME",
            notes=f"VIX {vix:.2f} > {VIX_EXTREME} — tail-risk environment. No new entries.",
        )
    elif vix > VIX_PREMIUM_FRIENDLY:
        return P1Result(
            gate=GateResult.PASS,
            vix=vix,
            regime="PREMIUM_SELLING_FRIENDLY",
            notes=f"VIX {vix:.2f} — elevated IV, strong premium environment.",
        )
    elif vix >= VIX_NEUTRAL_LOWER:
        return P1Result(
            gate=GateResult.PASS,
            vix=vix,
            regime="NEUTRAL",
            notes=f"VIX {vix:.2f} — neutral regime, selective premium selling.",
        )
    else:
        return P1Result(
            gate=GateResult.WARN,
            vix=vix,
            regime="DEFENSIVE",
            notes=f"VIX {vix:.2f} < {VIX_DEFENSIVE} — thin premium. Reduce size, widen strikes.",
        )


# ============================================================================
# P2 — Underlying Quality Gate
# ============================================================================

EARNINGS_BLACKOUT_DAYS  = 7    # Block if earnings within 7 days
EARNINGS_WARNING_DAYS   = 14   # Warn if earnings within 14 days
DIVIDEND_BLACKOUT_DAYS  = 5    # Block if ex-div within 5 days (assignment risk)
IV_RANK_MIN             = 30.0 # Minimum IV rank for acceptable premium


def evaluate_p2(
    ticker: str,
    quality_tier: str,              # "HIGH" | "MEDIUM" | "LOW"
    iv_rank: Optional[float],
    earnings_days_out: Optional[int],
    dividend_days_out: Optional[int],
    custom_flags: Optional[list] = None,
) -> P2Result:
    """
    Gate on fundamental quality, IV environment, and event risk.

    FAIL conditions:
        - quality_tier == LOW
        - earnings within EARNINGS_BLACKOUT_DAYS
        - ex-dividend within DIVIDEND_BLACKOUT_DAYS
        - IV rank < IV_RANK_MIN (premium too thin regardless of yield)

    WARN conditions:
        - earnings within EARNINGS_WARNING_DAYS
        - custom_flags present (e.g. DoD designation, pending litigation)
    """
    flags = list(custom_flags or [])
    gate = GateResult.PASS

    # Quality tier gate
    if quality_tier == "LOW":
        flags.append("Quality tier LOW — fundamental risk unacceptable.")
        gate = GateResult.FAIL

    # Earnings blackout
    if earnings_days_out is not None:
        if earnings_days_out <= EARNINGS_BLACKOUT_DAYS:
            flags.append(f"[⚠️ EARNINGS BLACKOUT] Earnings in {earnings_days_out}d — blocked.")
            gate = GateResult.FAIL
        elif earnings_days_out <= EARNINGS_WARNING_DAYS:
            flags.append(f"[⚠️ EARNINGS WARNING] Earnings in {earnings_days_out}d — shorten DTE.")
            if gate == GateResult.PASS:
                gate = GateResult.WARN

    # Dividend assignment risk
    if dividend_days_out is not None and dividend_days_out <= DIVIDEND_BLACKOUT_DAYS:
        flags.append(f"[⚠️ DIVIDEND RISK] Ex-div in {dividend_days_out}d — assignment risk on calls.")
        gate = GateResult.FAIL

    # IV rank minimum
    if iv_rank is not None and iv_rank < IV_RANK_MIN:
        flags.append(f"IV rank {iv_rank:.1f} < {IV_RANK_MIN} minimum — premium too thin.")
        if gate == GateResult.PASS:
            gate = GateResult.WARN

    return P2Result(
        gate=gate,
        quality_tier=quality_tier,
        iv_rank=iv_rank,
        earnings_days_out=earnings_days_out,
        dividend_days_out=dividend_days_out,
        flags=flags,
    )


# ============================================================================
# P3 — Premium Yield Gate
# ============================================================================

# Minimum thresholds by strategy
P3_THRESHOLDS = {
    "covered_call":      {"min_roi_pct": 1.0,  "min_ann_roi_pct": 20.0},
    "cash_secured_put":  {"min_roi_pct": 1.0,  "min_ann_roi_pct": 20.0},
    "iron_butterfly":    {"min_roi_pct": 50.0, "min_ann_roi_pct": 100.0},  # % of max risk
}


def evaluate_p3(
    strategy: str,
    premium: float,
    collateral: float,
    dte: int,
) -> P3Result:
    """
    Gate on return thresholds.

    For covered_call / cash_secured_put:
        roi_pct    = premium / collateral
        ann_roi    = roi_pct * (365 / dte)

    For iron_butterfly:
        roi_pct    = net_credit / max_risk  (collateral = max_risk here)
        ann_roi    = roi_pct * (365 / dte)
    """
    if collateral <= 0 or dte <= 0:
        return P3Result(
            gate=GateResult.FAIL, roi_pct=0, ann_roi_pct=0,
            dte=dte, premium=premium, collateral=collateral,
            notes="Invalid collateral or DTE."
        )

    roi_pct = (premium / collateral) * 100
    ann_roi_pct = roi_pct * (365 / dte)

    thresholds = P3_THRESHOLDS.get(strategy, P3_THRESHOLDS["covered_call"])
    min_roi    = thresholds["min_roi_pct"]
    min_ann    = thresholds["min_ann_roi_pct"]

    if roi_pct < min_roi or ann_roi_pct < min_ann:
        return P3Result(
            gate=GateResult.FAIL,
            roi_pct=roi_pct, ann_roi_pct=ann_roi_pct,
            dte=dte, premium=premium, collateral=collateral,
            notes=(
                f"Yield below threshold: {roi_pct:.2f}% ROI (min {min_roi}%), "
                f"{ann_roi_pct:.1f}% ann. (min {min_ann}%)."
            ),
        )

    return P3Result(
        gate=GateResult.PASS,
        roi_pct=roi_pct, ann_roi_pct=ann_roi_pct,
        dte=dte, premium=premium, collateral=collateral,
        notes=f"{roi_pct:.2f}% ROI / {ann_roi_pct:.1f}% annualized over {dte} DTE.",
    )


# ============================================================================
# Full chain evaluator
# ============================================================================

def run_triangulation(
    ticker: str,
    strategy: str,
    vix: float,
    quality_tier: str,
    iv_rank: Optional[float],
    earnings_days_out: Optional[int],
    dividend_days_out: Optional[int],
    premium: float,
    collateral: float,
    dte: int,
    custom_flags: Optional[list] = None,
) -> ChainResult:
    """
    Execute the full P1 → P2 → P3 triangulation chain.
    Returns a ChainResult with the final signal and all gate details.
    """
    p1 = evaluate_p1(vix)
    p2 = evaluate_p2(ticker, quality_tier, iv_rank, earnings_days_out,
                     dividend_days_out, custom_flags)
    p3 = evaluate_p3(strategy, premium, collateral, dte)

    gates = [p1.gate, p2.gate, p3.gate]

    if GateResult.FAIL in gates:
        signal = SignalStrength.BLOCKED
        notes = "One or more gates FAILED — trade blocked."
    elif GateResult.WARN in gates:
        signal = SignalStrength.NORMAL
        notes = "All gates passed with warnings — proceed with reduced size."
    else:
        signal = SignalStrength.STRONG
        notes = "All gates passed cleanly."

    result = ChainResult(
        ticker=ticker, strategy=strategy,
        p1=p1, p2=p2, p3=p3,
        signal=signal, signal_notes=notes,
    )
    logger.info(result.summary())
    return result
