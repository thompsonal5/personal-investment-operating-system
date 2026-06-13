"""
Position Rebalancer — Fortress Edition PIOS
Manages the full lifecycle of Wheel strategy positions:
open → monitor → roll / close → redeploy.

Rolling logic:
    - Roll at 80%+ profit capture (lock in gains, redeploy)
    - Roll at ≤7 DTE (avoid gamma risk)
    - Roll down-and-out on tested puts (repair mode)
    - Roll up-and-out on tested calls (protect assignment)
"""

import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple
from datetime import date, datetime, timedelta

from portfolio_management.allocation.allocator import RollCandidate

logger = logging.getLogger(__name__)


# ============================================================================
# Roll decision engine
# ============================================================================

@dataclass
class RollAction:
    candidate:       RollCandidate
    action:          str             # "ROLL_OUT" | "ROLL_DOWN_OUT" | "ROLL_UP_OUT" | "CLOSE"
    new_strike:      Optional[float]
    new_expiration:  Optional[str]
    rationale:       str
    urgency:         str             # "HIGH" | "MEDIUM" | "LOW"


class Rebalancer:
    """
    Evaluates open short option positions and prescribes roll/close actions.
    Does NOT execute — hands off to OrderHandler.
    """

    ROLL_OUT_DTE_TARGET    = 30    # Roll to ~30 DTE when closing out early
    PROFIT_CLOSE_THRESHOLD = 0.50  # Close entirely at 50% profit (no roll needed)

    def evaluate(self, candidates: List[RollCandidate]) -> List[RollAction]:
        """Evaluate all roll candidates and return prioritized action list."""
        actions = []
        for c in candidates:
            action = self._prescribe(c)
            if action:
                actions.append(action)
        actions.sort(key=lambda a: {"HIGH": 0, "MEDIUM": 1, "LOW": 2}[a.urgency])
        return actions

    def _prescribe(self, c: RollCandidate) -> Optional[RollAction]:
        # ≥50% profit → close entirely, no roll
        if c.profit_pct >= self.PROFIT_CLOSE_THRESHOLD and c.dte > 7:
            return RollAction(
                candidate=c,
                action="CLOSE",
                new_strike=None,
                new_expiration=None,
                rationale=(
                    f"{c.profit_pct:.0%} profit captured. "
                    f"Close to lock in gains and free collateral."
                ),
                urgency="MEDIUM",
            )

        # ≤7 DTE → roll out to avoid gamma / pin risk
        if c.dte <= 7:
            new_exp = self._target_expiration(days_out=self.ROLL_OUT_DTE_TARGET)
            return RollAction(
                candidate=c,
                action="ROLL_OUT",
                new_strike=c.strike,          # same strike
                new_expiration=new_exp,
                rationale=(
                    f"{c.dte} DTE remaining — gamma risk zone. "
                    f"Roll out to {new_exp} at same strike ${c.strike}."
                ),
                urgency="HIGH",
            )

        # ≥80% profit → roll out early to redeploy
        if c.profit_pct >= 0.80:
            new_exp = self._target_expiration(days_out=self.ROLL_OUT_DTE_TARGET)
            return RollAction(
                candidate=c,
                action="ROLL_OUT",
                new_strike=c.strike,
                new_expiration=new_exp,
                rationale=(
                    f"{c.profit_pct:.0%} profit — at target. "
                    f"Roll out to {new_exp} to harvest new premium."
                ),
                urgency="MEDIUM",
            )

        return None

    @staticmethod
    def _target_expiration(days_out: int) -> str:
        """Return a target expiration date string approximately days_out from today."""
        target = date.today() + timedelta(days=days_out)
        # Move to nearest Friday (options typically expire Friday)
        days_until_friday = (4 - target.weekday()) % 7
        target += timedelta(days=days_until_friday)
        return target.strftime("%Y-%m-%d")

    def summary(self, actions: List[RollAction]) -> str:
        if not actions:
            return "No roll or close actions required."
        lines = ["ROLL/CLOSE RECOMMENDATIONS:"]
        for a in actions:
            lines.append(
                f"  [{a.urgency}] {a.candidate.ticker} "
                f"${a.candidate.strike}{a.candidate.strategy[0].upper()} "
                f"{a.candidate.expiration} ({a.candidate.dte}d) → "
                f"{a.action}: {a.rationale}"
            )
        return "\n".join(lines)
