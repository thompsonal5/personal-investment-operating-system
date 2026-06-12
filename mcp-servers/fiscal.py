"""
Fiscal.ai MCP Server — Fortress Edition PIOS
Provides fundamental data, IV rank, earnings dates, and dividend data
via the Fiscal.ai API (connected MCP: https://api.fiscal.ai/mcp/sse).
"""

import logging
import requests
from typing import Any, Dict, Optional

from .base import MCPServer, MCPResponse

logger = logging.getLogger(__name__)

FISCAL_BASE_URL = "https://api.fiscal.ai/mcp/sse"


class FiscalMCP(MCPServer):
    """
    Fiscal.ai data connector — tertiary provider in the PIOS chain.

    Primary use cases:
        - IV Rank / IV Percentile for P2 quality scoring
        - Earnings date confirmation (earnings risk gate)
        - Dividend ex-date lookup (assignment risk gate)
        - Fundamental quality scores (P/E, FCF, revenue growth)
        - Options chain data when Trayd/Robinhood cannot supply it
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__("fiscal", config)
        self._api_key: Optional[str] = config.get("api_key", "")
        self._headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}" if self._api_key else "",
        }

    # ------------------------------------------------------------------
    # Core interface
    # ------------------------------------------------------------------

    def connect(self) -> MCPResponse:
        return self.health_check()

    def disconnect(self) -> None:
        self._connected = False
        logger.info("[fiscal] Session closed.")

    def health_check(self) -> MCPResponse:
        try:
            resp = requests.get(FISCAL_BASE_URL, headers=self._headers, timeout=5)
            ok = resp.status_code < 500
            return MCPResponse(success=ok, data={"status": resp.status_code},
                               provider=self.provider_name)
        except Exception as e:
            return MCPResponse(success=False, error=str(e), error_code="CONNECTION_ERROR",
                               provider=self.provider_name)

    def get_account_data(self, account_id: str) -> MCPResponse:
        return MCPResponse(success=False, error="Not applicable for Fiscal.ai",
                           error_code="UNSUPPORTED_OPERATION", provider=self.provider_name)

    def get_positions(self, account_id: str) -> MCPResponse:
        return MCPResponse(success=False, error="Not applicable for Fiscal.ai",
                           error_code="UNSUPPORTED_OPERATION", provider=self.provider_name)

    def get_quote(self, ticker: str) -> MCPResponse:
        return self.call_with_retry(self._fetch_quote, ticker)

    def get_options_chain(self, ticker: str, expiration: str) -> MCPResponse:
        return self.call_with_retry(self._fetch_options_chain, ticker, expiration)

    # ------------------------------------------------------------------
    # Fiscal-specific methods
    # ------------------------------------------------------------------

    def get_iv_rank(self, ticker: str) -> MCPResponse:
        """Return IV rank and IV percentile for P2 quality scoring."""
        return self.call_with_retry(self._fetch_iv_rank, ticker)

    def get_earnings_date(self, ticker: str) -> MCPResponse:
        """Return next confirmed earnings date — used as earnings risk gate."""
        return self.call_with_retry(self._fetch_earnings_date, ticker)

    def get_dividend_data(self, ticker: str) -> MCPResponse:
        """Return next ex-dividend date and amount — used as assignment risk gate."""
        return self.call_with_retry(self._fetch_dividend_data, ticker)

    def get_fundamental_score(self, ticker: str) -> MCPResponse:
        """Return composite fundamental quality score for P2 evaluation."""
        return self.call_with_retry(self._fetch_fundamentals, ticker)

    # ------------------------------------------------------------------
    # Private implementation
    # ------------------------------------------------------------------

    def _execute_code(self, code: str) -> Dict:
        """Execute JavaScript via Fiscal.ai execute_code tool."""
        resp = requests.post(
            FISCAL_BASE_URL,
            headers=self._headers,
            json={"tool": "execute_code", "input": {"code": code}},
            timeout=15,
        )
        return resp.json()

    def _fetch_quote(self, ticker: str) -> MCPResponse:
        try:
            code = f"""
            const data = await fiscal.getQuote('{ticker}');
            return JSON.stringify(data);
            """
            result = self._execute_code(code)
            return MCPResponse(success=True, data=result, provider=self.provider_name)
        except Exception as e:
            return MCPResponse(success=False, error=str(e), error_code="FETCH_ERROR",
                               provider=self.provider_name)

    def _fetch_iv_rank(self, ticker: str) -> MCPResponse:
        try:
            code = f"""
            const data = await fiscal.getIVRank('{ticker}');
            return JSON.stringify({{ iv_rank: data.iv_rank, iv_percentile: data.iv_percentile }});
            """
            result = self._execute_code(code)
            return MCPResponse(success=True, data=result, provider=self.provider_name)
        except Exception as e:
            return MCPResponse(success=False, error=str(e), error_code="FETCH_ERROR",
                               provider=self.provider_name)

    def _fetch_earnings_date(self, ticker: str) -> MCPResponse:
        try:
            code = f"""
            const data = await fiscal.getEarningsCalendar('{ticker}');
            return JSON.stringify({{ next_earnings: data.next_earnings_date, confirmed: data.confirmed }});
            """
            result = self._execute_code(code)
            return MCPResponse(success=True, data=result, provider=self.provider_name)
        except Exception as e:
            return MCPResponse(success=False, error=str(e), error_code="FETCH_ERROR",
                               provider=self.provider_name)

    def _fetch_dividend_data(self, ticker: str) -> MCPResponse:
        try:
            code = f"""
            const data = await fiscal.getDividendData('{ticker}');
            return JSON.stringify({{ ex_date: data.ex_dividend_date, amount: data.dividend_amount }});
            """
            result = self._execute_code(code)
            return MCPResponse(success=True, data=result, provider=self.provider_name)
        except Exception as e:
            return MCPResponse(success=False, error=str(e), error_code="FETCH_ERROR",
                               provider=self.provider_name)

    def _fetch_options_chain(self, ticker: str, expiration: str) -> MCPResponse:
        try:
            code = f"""
            const data = await fiscal.getOptionsChain('{ticker}', '{expiration}');
            return JSON.stringify(data);
            """
            result = self._execute_code(code)
            return MCPResponse(success=True, data=result, provider=self.provider_name)
        except Exception as e:
            return MCPResponse(success=False, error=str(e), error_code="FETCH_ERROR",
                               provider=self.provider_name)

    def _fetch_fundamentals(self, ticker: str) -> MCPResponse:
        try:
            code = f"""
            const data = await fiscal.getFundamentals('{ticker}');
            return JSON.stringify(data);
            """
            result = self._execute_code(code)
            return MCPResponse(success=True, data=result, provider=self.provider_name)
        except Exception as e:
            return MCPResponse(success=False, error=str(e), error_code="FETCH_ERROR",
                               provider=self.provider_name)
