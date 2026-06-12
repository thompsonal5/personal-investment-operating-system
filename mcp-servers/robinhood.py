"""
Robinhood MCP Server — Fortress Edition PIOS
Direct Robinhood connector (future native integration).
Currently routes through Trayd as the authenticated proxy.
Designed for drop-in replacement once a native Robinhood MCP is available.
"""

import logging
from typing import Any, Dict

from .base import MCPServer, MCPResponse
from .trayd import TraydMCP

logger = logging.getLogger(__name__)


class RobinhoodMCP(MCPServer):
    """
    Robinhood data connector.

    Architecture note: Robinhood does not publish a public MCP server.
    This class currently delegates all calls to TraydMCP, which acts as
    the authenticated Robinhood proxy. When a native Robinhood MCP becomes
    available in the Claude connector registry, swap the _delegate reference.

    Account IDs (from live session):
        Roth IRA:   821132974
        Brokerage:  662458413
        Agentic:    636778128
    """

    ROTH_IRA_ID   = "821132974"
    BROKERAGE_ID  = "662458413"
    AGENTIC_ID    = "636778128"

    # Strategy locks enforced at this layer
    ROTH_IRA_ALLOWED   = {"covered_call", "cash_secured_put", "equity_purchase"}
    BROKERAGE_ALLOWED  = {"covered_call", "cash_secured_put", "iron_butterfly", "equity_purchase"}

    def __init__(self, config: Dict[str, Any]):
        super().__init__("robinhood", config)
        # Delegate to Trayd until native connector exists
        self._delegate = TraydMCP(config)

    # ------------------------------------------------------------------
    # Core interface — delegate to Trayd
    # ------------------------------------------------------------------

    def connect(self) -> MCPResponse:
        result = self._delegate.connect()
        if result.success:
            self._connected = True
        return result

    def disconnect(self) -> None:
        self._delegate.disconnect()
        self._connected = False

    def health_check(self) -> MCPResponse:
        return self._delegate.health_check()

    def get_account_data(self, account_id: str) -> MCPResponse:
        return self._delegate.get_account_data(account_id)

    def get_positions(self, account_id: str) -> MCPResponse:
        return self._delegate.get_positions(account_id)

    def get_quote(self, ticker: str) -> MCPResponse:
        return self._delegate.get_quote(ticker)

    def get_options_chain(self, ticker: str, expiration: str) -> MCPResponse:
        return self._delegate.get_options_chain(ticker, expiration)

    # ------------------------------------------------------------------
    # Robinhood-specific helpers
    # ------------------------------------------------------------------

    def get_all_accounts(self) -> MCPResponse:
        """Return all accounts with equity, cash, and buying power."""
        return self._delegate.list_accounts()

    def get_roth_ira(self) -> MCPResponse:
        return self.get_account_data(self.ROTH_IRA_ID)

    def get_brokerage(self) -> MCPResponse:
        return self.get_account_data(self.BROKERAGE_ID)

    def validate_strategy(self, account_id: str, strategy: str) -> bool:
        """
        Enforce account-level strategy locks before order submission.
        Returns True if strategy is permitted for the given account.
        """
        strategy = strategy.lower().replace(" ", "_")
        if account_id == self.ROTH_IRA_ID:
            allowed = self.ROTH_IRA_ALLOWED
        elif account_id == self.BROKERAGE_ID:
            allowed = self.BROKERAGE_ALLOWED
        else:
            allowed = self.BROKERAGE_ALLOWED  # Agentic sandbox — permissive

        if strategy not in allowed:
            logger.error(
                f"[RISK VIOLATION] Strategy '{strategy}' is NOT permitted "
                f"for account {account_id}. Allowed: {allowed}"
            )
            return False
        return True
