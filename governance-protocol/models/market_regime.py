"""
Market Regime Model — Fortress Edition PIOS v9.1
Classifies current market conditions to gate premium-selling activity.

P1 sentiment signals (in order of authority):
    1. VIX — primary signal, sets the base regime band
    2. CNN Fear & Greed Index — 0-100 composite sentiment gauge (confirming/contradicting)
    3. CBOE Equity Put/Call Ratio — positioning gauge (confirming/contradicting)
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List

logger = logging.getLogger(__name__)


class Regime(Enum):
    PREMIUM_SELLING_FRIENDLY = "PREMIUM_SELLING_FRIENDLY"
    NEUTRAL                  = "NEUTRAL"
    DEFENSIVE                = "DEFENSIVE"
    EXTREME                  = "EXTREME"


class SessionMode(Enum):
    MODE_A = "MODE_A"   # Mon–Thu: Premium Yield vs. Fundamental Quality
    MODE_B = "MODE_B"   # Friday: End-of-Week Cash Deployment Audit + Step 8 Equity Deployment


class FearGreedZone(Enum):
    EXTREME_FEAR  = "EXTREME_FEAR"   # 0-25
    FEAR          = "FEAR"           # 25-45
    NEUTRAL       = "NEUTRAL"        # 45-55
    GREED         = "GREED"          # 55-75
    EXTREME_GREED = "EXTREME_GREED"  # 75-100


class PutCallSignal(Enum):
    ELEVATED_HEDGING = "ELEVATED_HEDGING"   # ratio > 1.0 — favors CSP premium
    NORMAL           = "NORMAL"             # 0.7-1.0
    COMPLACENT       = "COMPLACENT"         # < 0.7 — favors CC premium, caution on CSPs


# Fear & Greed band thresholds
FEAR_GREED_BANDS = {
    (0, 25):   FearGreedZone.EXTREME_FEAR,
    (25, 45):  FearGreedZone.FEAR,
    (45, 55):  FearGreedZone.NEUTRAL,
    (55, 75):  FearGreedZone.GREED,
    (75, 101): FearGreedZone.EXTREME_GREED,
}

# Put/Call ratio thresholds
PUT_CALL_ELEVATED_THRESHOLD   = 1.0
PUT_CALL_COMPLACENT_THRESHOLD = 0.7


@dataclass
class RegimeSnapshot:
    vix: float
    fear_greed_index: Optional[int]
    put_call_ratio: Optional[float]
    spy_price: Optional[float]
    iwm_price: Optional[float]
    qqq_price: Optional[float]
    regime: Regime
    session_mode: SessionMode
    fear_greed_zone: Optional[FearGreedZone] = None
    put_call_signal: Optional[PutCallSignal] = None
    divergence_flags: List[str] = field(default_factory=list)
    notes: str = ""

    @property
    def is_premium_friendly(self) -> bool:
        return self.regime in (Regime.PREMIUM_SELLING_FRIENDLY, Regime.NEUTRAL)


def classify_fear_greed(index_value: int) -> FearGreedZone:
    """Map a 0-100 CNN Fear & Greed Index value to its zone."""
    for (low, high), zone in FEAR_GREED_BANDS.items():
        if low <= index_value < high:
            return zone
    return FearGreedZone.NEUTRAL


def classify_put_call(ratio: float) -> PutCallSignal:
    """Map a CBOE Equity Put/Call Ratio to its positioning signal."""
    if ratio > PUT_CALL_ELEVATED_THRESHOLD:
        return PutCallSignal.ELEVATED_HEDGING
    elif ratio < PUT_CALL_COMPLACENT_THRESHOLD:
        return PutCallSignal.COMPLACENT
    return PutCallSignal.NORMAL


def classify_regime(
    vix: float,
    day_of_week: int,           # 0=Monday, 4=Friday
    fear_greed_index: Optional[int] = None,
    put_call_ratio: Optional[float] = None,
    spy_change_pct: float = 0.0,
    iwm_change_pct: float = 0.0,
) -> RegimeSnapshot:
    """
    Classify market regime and determine session mode.

    VIX bands (primary signal):
        > 40   → EXTREME   (block all new entries)
        25–40  → PREMIUM_SELLING_FRIENDLY
        18–25  → NEUTRAL
        < 18   → DEFENSIVE

    Fear & Greed Index and Put/Call Ratio are confirming/contradicting
    signals layered on top of the VIX-based regime. Material divergence
    (e.g. VIX NEUTRAL but Extreme Greed + complacent Put/Call) is flagged
    and the classification leans toward the more conservative regime.
    """
    session_mode = SessionMode.MODE_B if day_of_week == 4 else SessionMode.MODE_A

    if vix > 40:
        regime = Regime.EXTREME
        notes = f"VIX {vix:.2f} — tail risk. No new entries."
    elif vix > 25:
        regime = Regime.PREMIUM_SELLING_FRIENDLY
        notes = f"VIX {vix:.2f} — elevated IV, full deployment authorized."
    elif vix >= 18:
        regime = Regime.NEUTRAL
        notes = f"VIX {vix:.2f} — neutral, selective premium selling."
    else:
        regime = Regime.DEFENSIVE
        notes = f"VIX {vix:.2f} — low IV, reduce size and widen strikes."

    # --- Secondary sentiment signals ---
    fg_zone: Optional[FearGreedZone] = None
    pc_signal: Optional[PutCallSignal] = None
    divergence_flags: List[str] = []

    if fear_greed_index is not None:
        fg_zone = classify_fear_greed(fear_greed_index)
        notes += f" | Fear & Greed: {fear_greed_index} ({fg_zone.value})."

    if put_call_ratio is not None:
        pc_signal = classify_put_call(put_call_ratio)
        notes += f" | Put/Call Ratio: {put_call_ratio:.2f} ({pc_signal.value})."

    # --- Divergence check ---
    # If VIX says NEUTRAL or better, but sentiment gauges both lean toward
    # complacency/euphoria (Extreme Greed + complacent Put/Call), flag it
    # and lean toward the more conservative (DEFENSIVE) classification.
    if regime in (Regime.NEUTRAL, Regime.PREMIUM_SELLING_FRIENDLY):
        if fg_zone == FearGreedZone.EXTREME_GREED and pc_signal == PutCallSignal.COMPLACENT:
            divergence_flags.append(
                f"[⚠️ SENTIMENT_DIVERGENCE] VIX regime is {regime.value} but Fear & Greed "
                f"is EXTREME_GREED and Put/Call Ratio is COMPLACENT — leaning conservative."
            )
            regime = Regime.DEFENSIVE
            notes += " [Regime downgraded to DEFENSIVE due to sentiment divergence.]"

    # Extreme Fear + elevated Put/Call alongside a HOSTILE/DEFENSIVE VIX regime
    # can indicate capitulation — often a favorable premium-selling environment
    # for CSPs specifically, even if overall regime stays cautious. Flag only.
    if fg_zone == FearGreedZone.EXTREME_FEAR and pc_signal == PutCallSignal.ELEVATED_HEDGING:
        divergence_flags.append(
            "[ℹ️ CAPITULATION_SIGNAL] Extreme Fear + elevated Put/Call Ratio — "
            "premium on CSPs may be unusually rich; consider selectively."
        )

    # Gap-up warning
    if iwm_change_pct > 2.0:
        notes += f" [⚠️ IWM gapping +{iwm_change_pct:.1f}% — wait for open to settle before iron butterfly entry]"

    return RegimeSnapshot(
        vix=vix,
        fear_greed_index=fear_greed_index,
        put_call_ratio=put_call_ratio,
        spy_price=None,
        iwm_price=None,
        qqq_price=None,
        regime=regime,
        session_mode=session_mode,
        fear_greed_zone=fg_zone,
        put_call_signal=pc_signal,
        divergence_flags=divergence_flags,
        notes=notes,
    )
