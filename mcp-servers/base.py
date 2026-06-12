"""
MCP Server Base Class - Fortress Edition PIOS
Abstract base for all data provider connectors with health-check heartbeat,
retry logic, and standardized response envelope.
"""

import time
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class MCPStatus(Enum):
    OK = "ok"
    DEGRADED = "degraded"
    OFFLINE = "offline"
    AUTH_EXPIRED = "auth_expired"


@dataclass
class MCPResponse:
    """Standardized response envelope for all MCP server calls."""
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    provider: Optional[str] = None
    latency_ms: Optional[float] = None
    timestamp: float = field(default_factory=time.time)

    @property
    def ok(self) -> bool:
        return self.success and self.data is not None

    def __repr__(self):
        status = "OK" if self.success else f"ERR({self.error_code})"
        return f"MCPResponse[{self.provider}:{status}]"


class MCPServer(ABC):
    """
    Abstract base class for all PIOS MCP data connectors.

    Subclasses must implement:
        - connect()
        - disconnect()
        - health_check()
        - get_account_data()
        - get_positions()
        - get_quote()
        - get_options_chain()
    """

    MAX_RETRIES = 3
    RETRY_BACKOFF = [1, 2, 4]  # seconds

    def __init__(self, provider_name: str, config: Dict[str, Any]):
        self.provider_name = provider_name
        self.config = config
        self._connected = False
        self._last_heartbeat: Optional[float] = None
        self._status = MCPStatus.OFFLINE
        logger.info(f"[{self.provider_name}] MCP Server initialized.")

    # ------------------------------------------------------------------
    # Abstract interface — all connectors must implement
    # ------------------------------------------------------------------

    @abstractmethod
    def connect(self) -> MCPResponse:
        """Establish authenticated session with the data provider."""

    @abstractmethod
    def disconnect(self) -> None:
        """Gracefully close the session."""

    @abstractmethod
    def health_check(self) -> MCPResponse:
        """Heartbeat probe — returns MCPStatus and latency."""

    @abstractmethod
    def get_account_data(self, account_id: str) -> MCPResponse:
        """Return equity, cash, buying power for an account."""

    @abstractmethod
    def get_positions(self, account_id: str) -> MCPResponse:
        """Return all open positions for an account."""

    @abstractmethod
    def get_quote(self, ticker: str) -> MCPResponse:
        """Return real-time quote for a single ticker."""

    @abstractmethod
    def get_options_chain(self, ticker: str, expiration: str) -> MCPResponse:
        """Return full options chain for ticker/expiration."""

    # ------------------------------------------------------------------
    # Shared retry wrapper
    # ------------------------------------------------------------------

    def call_with_retry(self, fn, *args, **kwargs) -> MCPResponse:
        """Execute fn with exponential-backoff retry on transient failures."""
        last_error = None
        for attempt, delay in enumerate(self.RETRY_BACKOFF, start=1):
            try:
                t0 = time.time()
                result: MCPResponse = fn(*args, **kwargs)
                result.latency_ms = (time.time() - t0) * 1000
                result.provider = self.provider_name
                if result.success:
                    return result
                last_error = result.error
            except Exception as exc:
                last_error = str(exc)
                logger.warning(
                    f"[{self.provider_name}] Attempt {attempt}/{self.MAX_RETRIES} "
                    f"failed: {last_error}. Retrying in {delay}s..."
                )
                time.sleep(delay)

        logger.error(f"[{self.provider_name}] All retries exhausted: {last_error}")
        return MCPResponse(
            success=False,
            error=last_error,
            error_code="MAX_RETRIES_EXCEEDED",
            provider=self.provider_name,
        )

    # ------------------------------------------------------------------
    # Heartbeat scheduler
    # ------------------------------------------------------------------

    def beat(self) -> MCPStatus:
        """Run health_check and cache status + timestamp."""
        response = self.health_check()
        self._last_heartbeat = time.time()
        self._status = MCPStatus.OK if response.success else MCPStatus.DEGRADED
        return self._status

    @property
    def is_alive(self) -> bool:
        return self._status in (MCPStatus.OK, MCPStatus.DEGRADED)

    @property
    def status(self) -> MCPStatus:
        return self._status
