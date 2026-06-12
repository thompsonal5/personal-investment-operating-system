"""
Provider Chain — Fortress Edition PIOS
Implements the data provider fallback sequence:
Robinhood → Trayd → Fiscal → Google Finance → Yahoo Finance → Cache
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

PROVIDER_ORDER = ["robinhood", "trayd", "fiscal", "google", "yahoo", "cache"]


class ProviderChain:
    """
    Iterates through registered providers in priority order.
    Returns data from the first provider that responds successfully.
    Logs [DATA_VOID_CRITICAL] if all providers fail.
    """

    def __init__(self):
        self._providers: Dict[str, Any] = {}

    def register(self, name: str, provider: Any) -> None:
        """Register a data provider under its name."""
        self._providers[name] = provider
        logger.info(f"[ProviderChain] Registered: {name}")

    def get_quote(self, ticker: str) -> Optional[Dict]:
        for name in PROVIDER_ORDER:
            provider = self._providers.get(name)
            if provider is None:
                continue
            try:
                result = provider.get_quote(ticker)
                if result and getattr(result, "success", False):
                    logger.info(f"[ProviderChain] Quote for {ticker} resolved via {name}.")
                    return result.data
            except Exception as e:
                logger.warning(f"[ProviderChain] {name} failed for quote/{ticker}: {e}")
        logger.error(f"[DATA_VOID_CRITICAL] All providers failed for quote/{ticker}.")
        return None

    def get_options_chain(self, ticker: str, expiration: str) -> Optional[Dict]:
        for name in PROVIDER_ORDER:
            provider = self._providers.get(name)
            if provider is None:
                continue
            try:
                result = provider.get_options_chain(ticker, expiration)
                if result and getattr(result, "success", False):
                    logger.info(f"[ProviderChain] Options chain {ticker}/{expiration} via {name}.")
                    return result.data
            except Exception as e:
                logger.warning(f"[ProviderChain] {name} failed for options/{ticker}: {e}")
        logger.error(f"[DATA_VOID_CRITICAL] All providers failed for options/{ticker}/{expiration}.")
        return None

    def get_positions(self, account_id: str) -> Optional[List]:
        for name in ["robinhood", "trayd"]:
            provider = self._providers.get(name)
            if provider is None:
                continue
            try:
                result = provider.get_positions(account_id)
                if result and getattr(result, "success", False):
                    return result.data
            except Exception as e:
                logger.warning(f"[ProviderChain] {name} failed for positions/{account_id}: {e}")
        logger.error(f"[DATA_VOID_CRITICAL] All providers failed for positions/{account_id}.")
        return None

    def status(self) -> Dict[str, str]:
        """Return health status of all registered providers."""
        out = {}
        for name, provider in self._providers.items():
            try:
                result = provider.health_check()
                out[name] = "OK" if getattr(result, "success", False) else "DEGRADED"
            except Exception:
                out[name] = "OFFLINE"
        return out
