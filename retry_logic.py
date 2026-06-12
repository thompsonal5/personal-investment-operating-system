"""
Retry Logic — Fortress Edition PIOS
Handles [DATA_VOID_CRITICAL] scenarios with a site-agnostic fallback chain.
Referenced in AGENTS.md as a mandatory resilience component.
"""

import time
import logging
from typing import Callable, Any, Optional, List

logger = logging.getLogger(__name__)


class DataVoidError(Exception):
    """Raised when all providers in the fallback chain are exhausted."""
    pass


# Fallback search sequence for DATA_VOID_CRITICAL (site-agnostic)
FALLBACK_SOURCES = [
    "trayd_mcp",
    "fiscal_ai",
    "google_finance",
    "yahoo_finance",
    "barchart",
    "cache",
]


def retry_with_backoff(
    fn: Callable,
    *args,
    max_retries: int = 3,
    backoff_seconds: List[float] = None,
    exceptions: tuple = (Exception,),
    **kwargs,
) -> Any:
    """
    Execute fn with exponential backoff on specified exceptions.
    Raises the last exception if all retries are exhausted.
    """
    if backoff_seconds is None:
        backoff_seconds = [1.0, 2.0, 4.0]

    last_exc = None
    for attempt, delay in enumerate(backoff_seconds[:max_retries], start=1):
        try:
            return fn(*args, **kwargs)
        except exceptions as e:
            last_exc = e
            logger.warning(
                f"[retry] Attempt {attempt}/{max_retries} failed: {e}. "
                f"Retrying in {delay}s..."
            )
            time.sleep(delay)

    raise last_exc


def data_void_fallback(
    ticker: str,
    data_type: str,
    provider_chain: Optional[List[str]] = None,
    fetch_fn: Optional[Callable] = None,
) -> Any:
    """
    [DATA_VOID_CRITICAL] handler.
    Iterates through the fallback chain until data is retrieved.

    Args:
        ticker:         The ticker symbol requiring data.
        data_type:      What we need (e.g. 'quote', 'iv_rank', 'options_chain').
        provider_chain: Ordered list of providers to try (defaults to FALLBACK_SOURCES).
        fetch_fn:       Callable(provider, ticker, data_type) → data | None.

    Returns:
        Data from the first successful provider.
    Raises:
        DataVoidError if all providers fail.
    """
    chain = provider_chain or FALLBACK_SOURCES

    for provider in chain:
        logger.info(f"[DATA_VOID] Trying {provider} for {ticker}/{data_type}...")
        try:
            if fetch_fn is not None:
                result = fetch_fn(provider, ticker, data_type)
                if result is not None:
                    logger.info(f"[DATA_VOID] Resolved via {provider}.")
                    return result
        except Exception as e:
            logger.warning(f"[DATA_VOID] {provider} failed: {e}")
            continue

    raise DataVoidError(
        f"[DATA_VOID_CRITICAL] All providers exhausted for {ticker}/{data_type}. "
        f"Chain tried: {chain}"
    )


class ResilienceWrapper:
    """
    Wraps any data-fetching call with retry + DATA_VOID fallback.
    Drop-in decorator for MCP server methods.
    """

    def __init__(self, max_retries: int = 3, fallback_chain: List[str] = None):
        self.max_retries = max_retries
        self.fallback_chain = fallback_chain or FALLBACK_SOURCES

    def __call__(self, fn: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            try:
                return retry_with_backoff(fn, *args, max_retries=self.max_retries, **kwargs)
            except Exception as e:
                logger.error(f"[ResilienceWrapper] All retries failed for {fn.__name__}: {e}")
                raise DataVoidError(
                    f"[DATA_VOID_CRITICAL] {fn.__name__} exhausted after "
                    f"{self.max_retries} retries: {e}"
                )
        wrapper.__name__ = fn.__name__
        return wrapper
