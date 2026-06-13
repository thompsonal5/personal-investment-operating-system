"""
Data Processor — Fortress Edition PIOS
Normalizes raw data from multiple providers into a consistent schema.
Handles the impedance mismatch between Trayd, Fiscal, Yahoo, and Barchart.
"""

import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class NormalizedQuote:
    ticker:     str
    price:      float
    bid:        Optional[float]
    ask:        Optional[float]
    volume:     Optional[int]
    prev_close: Optional[float]
    change_pct: Optional[float]
    source:     str

    @property
    def mid(self) -> float:
        if self.bid and self.ask:
            return (self.bid + self.ask) / 2
        return self.price


@dataclass
class NormalizedOption:
    ticker:     str
    expiration: str
    strike:     float
    option_type: str      # "call" | "put"
    bid:        float
    ask:        float
    iv:         float
    delta:      Optional[float]
    volume:     Optional[int]
    open_interest: Optional[int]
    source:     str

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2


class DataProcessor:
    """
    Normalizes raw API responses from any provider into PIOS schema.
    """

    def normalize_trayd_quote(self, raw: Dict[str, Any], ticker: str) -> Optional[NormalizedQuote]:
        """Parse Trayd/Robinhood quote response."""
        try:
            price = float(raw.get("last_trade_price") or raw.get("last_extended_hours_trade_price") or 0)
            return NormalizedQuote(
                ticker=ticker,
                price=price,
                bid=float(raw.get("bid_price") or 0) or None,
                ask=float(raw.get("ask_price") or 0) or None,
                volume=int(float(raw.get("volume") or 0)) or None,
                prev_close=float(raw.get("previous_close") or 0) or None,
                change_pct=self._calc_change_pct(price, raw.get("previous_close")),
                source="trayd",
            )
        except (TypeError, ValueError) as e:
            logger.warning(f"[DataProcessor] Trayd quote parse error for {ticker}: {e}")
            return None

    def normalize_trayd_position(self, raw: Dict[str, Any]) -> Optional[Dict]:
        """Normalize a Trayd position dict to consistent keys."""
        try:
            qty = float(raw.get("quantity") or raw.get("shares_held_for_sells") or 0)
            avg = float(raw.get("average_buy_price") or 0)
            current = float(raw.get("current_price") or avg)
            ticker = (raw.get("symbol") or raw.get("ticker") or "").upper()
            return {
                "ticker": ticker,
                "quantity": qty,
                "average_price": avg,
                "current_price": current,
                "market_value": qty * current,
                "unrealized_pnl": (current - avg) * qty,
                "instrument_type": raw.get("type", "equity"),
                "source": "trayd",
            }
        except (TypeError, ValueError) as e:
            logger.warning(f"[DataProcessor] Position parse error: {e} | raw={raw}")
            return None

    def normalize_account(self, raw: Dict[str, Any], account_id: str) -> Dict:
        """Normalize account data from any provider."""
        return {
            "account_id": account_id,
            "equity": float(raw.get("equity") or raw.get("total_equity") or 0),
            "cash": float(raw.get("cash") or raw.get("cash_balance") or 0),
            "buying_power": float(raw.get("buying_power") or raw.get("bp") or 0),
        }

    def normalize_options_chain(
        self, raw_chain: List[Dict], ticker: str, source: str
    ) -> List[NormalizedOption]:
        """Normalize options chain from any provider."""
        options = []
        for row in raw_chain:
            try:
                opt = NormalizedOption(
                    ticker=ticker,
                    expiration=row.get("expiration_date", row.get("expiration", "")),
                    strike=float(row.get("strike_price", row.get("strike", 0))),
                    option_type=row.get("type", row.get("option_type", "")).lower(),
                    bid=float(row.get("bid_price", row.get("bid", 0))),
                    ask=float(row.get("ask_price", row.get("ask", 0))),
                    iv=float(row.get("implied_volatility", row.get("iv", 0))),
                    delta=float(row["delta"]) if "delta" in row else None,
                    volume=int(row["volume"]) if "volume" in row else None,
                    open_interest=int(row["open_interest"]) if "open_interest" in row else None,
                    source=source,
                )
                options.append(opt)
            except (TypeError, ValueError, KeyError):
                continue
        return options

    @staticmethod
    def _calc_change_pct(current: float, prev_close) -> Optional[float]:
        try:
            prev = float(prev_close)
            if prev > 0:
                return ((current - prev) / prev) * 100
        except (TypeError, ValueError):
            pass
        return None
