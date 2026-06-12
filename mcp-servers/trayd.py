"""
Trayd MCP Server — Fortress Edition PIOS
Wraps the live Trayd MCP integration (Robinhood proxy via mcp.trayd.ai)
with the standardized MCPServer interface.
"""

import logging
import requests
from typing import Any, Dict, Optional

from .base import MCPServer, MCPResponse, MCPStatus

logger = logging.getLogger(__name__)

TRAYD_BASE_URL = "https://mcp.trayd.ai/mcp"


class TraydMCP(MCPServer):
    """
    Trayd MCP connector — primary Robinhood data source.

    Trayd proxies Robinhood account data through its own MCP server
    hosted on AWS (Ashburn, VA). Session tokens expire and require
    re-authentication via phone push approval.

    Authentication flow:
        1. call link_robinhood(email, password)
        2. User approves push notification on phone
        3. call complete_robinhood_link()
        4. Session is live — all account tools available
    """

    TOOL_LIST_ACCOUNTS     = "list_accounts"
    TOOL_GET_PORTFOLIO     = "get_portfolio"
    TOOL_GET_POSITIONS     = "get_positions"
    TOOL_GET_QUOTE         = "get_quote"
    TOOL_GET_OPEN_ORDERS   = "get_open_orders"
    TOOL_PLACE_ORDER       = "place_order"
    TOOL_CHECK_LOGIN       = "check_login_status"
    TOOL_LINK_ROBINHOOD    = "link_robinhood"
    TOOL_COMPLETE_LINK     = "complete_robinhood_link"

    def __init__(self, config: Dict[str, Any]):
        super().__init__("trayd", config)
        self._api_key: Optional[str] = config.get("api_key", "")
        self._session_headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}" if self._api_key else "",
        }

    # ------------------------------------------------------------------
    # Core interface
    # ------------------------------------------------------------------

    def connect(self) -> MCPResponse:
        """Verify Robinhood session is active via check_login_status."""
        return self.call_with_retry(self._check_login)

    def disconnect(self) -> None:
        self._connected = False
        self._status = MCPStatus.OFFLINE
        logger.info("[trayd] Session closed.")

    def health_check(self) -> MCPResponse:
        return self._check_login()

    def get_account_data(self, account_id: str) -> MCPResponse:
        return self.call_with_retry(self._get_portfolio, account_id)

    def get_positions(self, account_id: str) -> MCPResponse:
        return self.call_with_retry(self._get_positions, account_id)

    def get_quote(self, ticker: str) -> MCPResponse:
        return self.call_with_retry(self._get_quote, ticker)

    def get_options_chain(self, ticker: str, expiration: str) -> MCPResponse:
        # Trayd does not expose a direct options chain endpoint.
        # Falls through to the provider chain (Fiscal → web search).
        return MCPResponse(
            success=False,
            error="Trayd does not support options chain queries. Use Fiscal or web search.",
            error_code="UNSUPPORTED_OPERATION",
            provider=self.provider_name,
        )

    # ------------------------------------------------------------------
    # Extended Trayd-specific methods
    # ------------------------------------------------------------------

    def list_accounts(self) -> MCPResponse:
        """Return all Robinhood accounts with balances."""
        return self.call_with_retry(self._list_accounts)

    def get_open_orders(self, account_id: str) -> MCPResponse:
        """Return all open/pending option and equity orders."""
        return self.call_with_retry(self._get_open_orders, account_id)

    def place_order(
        self,
        account_id: str,
        ticker: str,
        side: str,
        quantity: int,
        order_type: str = "market",
        limit_price: Optional[float] = None,
    ) -> MCPResponse:
        """Place an equity or options order. Requires user confirmation upstream."""
        return self.call_with_retry(
            self._place_order, account_id, ticker, side, quantity, order_type, limit_price
        )

    # ------------------------------------------------------------------
    # Private implementation stubs (wire to Trayd HTTP API)
    # ------------------------------------------------------------------

    def _check_login(self) -> MCPResponse:
        try:
            resp = requests.post(
                TRAYD_BASE_URL,
                headers=self._session_headers,
                json={"tool": self.TOOL_CHECK_LOGIN, "input": {}},
                timeout=10,
            )
            data = resp.json()
            linked = data.get("robinhood_linked", False)
            return MCPResponse(
                success=linked,
                data=data,
                error=None if linked else data.get("message", "Session expired"),
                error_code=None if linked else "AUTH_EXPIRED",
                provider=self.provider_name,
            )
        except Exception as e:
            return MCPResponse(success=False, error=str(e), error_code="CONNECTION_ERROR",
                               provider=self.provider_name)

    def _list_accounts(self) -> MCPResponse:
        try:
            resp = requests.post(
                TRAYD_BASE_URL,
                headers=self._session_headers,
                json={"tool": self.TOOL_LIST_ACCOUNTS, "input": {}},
                timeout=10,
            )
            data = resp.json()
            return MCPResponse(success=data.get("success", False), data=data.get("accounts"),
                               provider=self.provider_name)
        except Exception as e:
            return MCPResponse(success=False, error=str(e), error_code="CONNECTION_ERROR",
                               provider=self.provider_name)

    def _get_portfolio(self, account_id: str) -> MCPResponse:
        try:
            resp = requests.post(
                TRAYD_BASE_URL,
                headers=self._session_headers,
                json={"tool": self.TOOL_GET_PORTFOLIO, "input": {"account_number": account_id}},
                timeout=10,
            )
            data = resp.json()
            return MCPResponse(success=True, data=data, provider=self.provider_name)
        except Exception as e:
            return MCPResponse(success=False, error=str(e), error_code="CONNECTION_ERROR",
                               provider=self.provider_name)

    def _get_positions(self, account_id: str) -> MCPResponse:
        try:
            resp = requests.post(
                TRAYD_BASE_URL,
                headers=self._session_headers,
                json={"tool": self.TOOL_GET_POSITIONS, "input": {"account_number": account_id}},
                timeout=10,
            )
            data = resp.json()
            return MCPResponse(success=True, data=data.get("positions", []),
                               provider=self.provider_name)
        except Exception as e:
            return MCPResponse(success=False, error=str(e), error_code="CONNECTION_ERROR",
                               provider=self.provider_name)

    def _get_quote(self, ticker: str) -> MCPResponse:
        try:
            resp = requests.post(
                TRAYD_BASE_URL,
                headers=self._session_headers,
                json={"tool": self.TOOL_GET_QUOTE, "input": {"ticker": ticker}},
                timeout=10,
            )
            data = resp.json()
            return MCPResponse(success=True, data=data, provider=self.provider_name)
        except Exception as e:
            return MCPResponse(success=False, error=str(e), error_code="CONNECTION_ERROR",
                               provider=self.provider_name)

    def _get_open_orders(self, account_id: str) -> MCPResponse:
        try:
            resp = requests.post(
                TRAYD_BASE_URL,
                headers=self._session_headers,
                json={"tool": self.TOOL_GET_OPEN_ORDERS, "input": {"account_number": account_id}},
                timeout=10,
            )
            data = resp.json()
            return MCPResponse(success=data.get("success", False),
                               data=data.get("orders", []), provider=self.provider_name)
        except Exception as e:
            return MCPResponse(success=False, error=str(e), error_code="CONNECTION_ERROR",
                               provider=self.provider_name)

    def _place_order(self, account_id, ticker, side, quantity, order_type, limit_price):
        payload = {
            "account_number": account_id,
            "ticker": ticker,
            "side": side,
            "quantity": quantity,
            "order_type": order_type,
        }
        if limit_price:
            payload["limit_price"] = limit_price
        try:
            resp = requests.post(
                TRAYD_BASE_URL,
                headers=self._session_headers,
                json={"tool": self.TOOL_PLACE_ORDER, "input": payload},
                timeout=15,
            )
            data = resp.json()
            return MCPResponse(success=data.get("success", False), data=data,
                               provider=self.provider_name)
        except Exception as e:
            return MCPResponse(success=False, error=str(e), error_code="ORDER_FAILED",
                               provider=self.provider_name)
