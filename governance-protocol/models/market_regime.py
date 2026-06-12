"""
Market Regime Model — Fortress Edition PIOS
Classifies current market conditions to gate premium-selling activity.
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class Regime(Enum):
    PREMIUM_SELLING_FRIENDLY = "PREMIUM_SELLING_FRIENDLY"
    NEUTRAL                  = "NEUTRAL"
    DEFENSIVE                = "DEFENSIVE"
    EXTREME                  = "EXTREME"


class SessionMode(Enum):
    MODE_A = "MODE_A"   # Mon–Thu: Premium Yield vs. Fundamental Quality
    MODE_B = "MODE_B"   # Friday: End-of-Week Cash Deployment Audit


@dataclass
class RegimeSnapshot:
    vix: float
    spy_price: Optional[float]
    iwm_price: Optional[float]
    qqq_price: Optional[float]
    regime: Regime
    session_mode: SessionMode
    notes: str = ""

    @property
    def is_premium_friendly(self) -> bool:
        return self.regime in (Regime.PREMIUM_SELLING_FRIENDLY, Regime.NEUTRAL)


def classify_regime(
    vix: float,
    day_of_week: int,           # 0=Monday, 4=Friday
    spy_change_pct: float = 0.0,
    iwm_change_pct: float = 0.0,
) -> RegimeSnapshot:
    """
    Classify market regime and determine session mode.

    VIX bands:
        > 40   → EXTREME   (block all new entries)
        25–40  → PREMIUM_SELLING_FRIENDLY
        18–25  → NEUTRAL
        < 18   → DEFENSIVE
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

    # Gap-up warning
    if iwm_change_pct > 2.0:
        notes += f" [⚠️ IWM gapping +{iwm_change_pct:.1f}% — wait for open to settle before iron butterfly entry]"

    return RegimeSnapshot(
        vix=vix,
        spy_price=None,
        iwm_price=None,
        qqq_price=None,
        regime=regime,
        session_mode=session_mode,
        notes=notes,
    )
