"""
PIOS Main — Fortress Edition Options Command Center
Session orchestrator. Runs the full 7-step OCC workflow.

Usage:
    python main.py --mode A          # Mon–Thu: yield vs quality
    python main.py --mode B          # Friday: cash deployment audit
    python main.py --mode A --dry-run
"""

import argparse
import logging
import sys
from datetime import date

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("PIOS.main")


def parse_args():
    parser = argparse.ArgumentParser(description="PIOS Fortress Edition OCC")
    parser.add_argument("--mode", choices=["A", "B"], default=None,
                        help="Session mode (A=Mon-Thu, B=Friday). Auto-detected if omitted.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Run full analysis without placing orders.")
    parser.add_argument("--account", default=None,
                        help="Restrict to a single account ID.")
    return parser.parse_args()


def detect_mode() -> str:
    """Auto-detect session mode from day of week."""
    return "B" if date.today().weekday() == 4 else "A"


def main():
    args = parse_args()
    mode = args.mode or detect_mode()
    dry_run = args.dry_run

    logger.info(f"{'='*60}")
    logger.info(f"PIOS Fortress Edition — Mode {mode} | {'DRY RUN' if dry_run else 'LIVE'}")
    logger.info(f"{'='*60}")

    try:
        # Step 1 — Initialize MCP connections
        from mcp_servers.robinhood import RobinhoodMCP
        from mcp_servers.fiscal import FiscalMCP
        from data_ingestion.providers.provider_chain import ProviderChain
        from data_ingestion.etl.data_processor import DataProcessor
        from portfolio_management.allocation.allocator import PortfolioAllocator, AccountSnapshot
        from portfolio_management.rebalancing.rebalancer import Rebalancer
        from governance_protocol.models.market_regime import classify_regime
        from tactical_execution.market_interfaces.robinhood_interface import RobinhoodInterface
        from config import ACCOUNTS as ACCOUNT_CONFIG, TRAYD_CONFIG, FISCAL_CONFIG

        logger.info("Step 1 — Initializing MCP connections...")
        robinhood_mcp = RobinhoodMCP(TRAYD_CONFIG)
        fiscal_mcp    = FiscalMCP(FISCAL_CONFIG)

        chain = ProviderChain()
        chain.register("robinhood", robinhood_mcp)
        chain.register("fiscal", fiscal_mcp)

        connect_result = robinhood_mcp.connect()
        if not connect_result.success:
            logger.error(f"Robinhood session expired: {connect_result.error}")
            logger.error("Re-link via Trayd MCP (thompsonal@aol.com) and approve push notification.")
            sys.exit(1)

        logger.info("✅ Robinhood connected.")

        # Step 2 — Load account data
        logger.info("Step 2 — Loading account snapshots...")
        processor  = PortfolioAllocator()
        dp         = DataProcessor()
        accounts   = robinhood_mcp.get_all_accounts()

        for acct in (accounts.data or []):
            acct_id = acct["account_number"]
            if args.account and acct_id != args.account:
                continue

            portfolio = robinhood_mcp.get_account_data(acct_id)
            positions = robinhood_mcp.get_positions(acct_id)

            norm_account  = dp.normalize_account(portfolio.data or {}, acct_id)
            norm_positions = [
                dp.normalize_trayd_position(p)
                for p in (positions.data or [])
                if p
            ]
            norm_positions = [p for p in norm_positions if p]

            snap = AccountSnapshot(
                account_id=acct_id,
                label=ACCOUNT_CONFIG.get(acct_id, {}).get("label", acct_id),
                equity=norm_account["equity"],
                cash=norm_account["cash"],
                buying_power=norm_account["buying_power"],
                positions=norm_positions,
            )
            processor.load_snapshot(snap)

        print(processor.deployment_summary())

        # Step 3 — Market regime (P1)
        logger.info("Step 3 — Classifying market regime...")
        vix_quote = chain.get_quote("VIX")
        vix = float((vix_quote or {}).get("last_trade_price", 20.0))
        iwm_quote = chain.get_quote("IWM")
        iwm_change = float((iwm_quote or {}).get("change_pct", 0.0))

        # P1 secondary sentiment signals — sourced via web search (no direct
        # MCP feed for CNN Fear & Greed Index or CBOE Equity Put/Call Ratio)
        fear_greed_index = None   # populate via web search: "CNN Fear and Greed Index"
        put_call_ratio   = None   # populate via web search: "CBOE Equity Put Call Ratio"

        regime = classify_regime(
            vix=vix,
            day_of_week=date.today().weekday(),
            fear_greed_index=fear_greed_index,
            put_call_ratio=put_call_ratio,
            iwm_change_pct=iwm_change,
        )
        logger.info(f"P1 Regime: {regime.regime.value} | VIX={vix:.2f} | Mode={regime.session_mode.value}")
        print(f"\nP1 REGIME: {regime.regime.value} — {regime.notes}")
        for flag in regime.divergence_flags:
            print(f"  {flag}")

        if not regime.is_premium_friendly:
            logger.warning("DEFENSIVE regime — reduce size or stand aside.")

        # Step 4–7 — Run allocator + print recommendations
        logger.info("Steps 4–7 — Running allocation analysis and roll checks...")
        recommendations, roll_candidates = processor.analyze()

        rebalancer = Rebalancer()
        roll_actions = rebalancer.evaluate(roll_candidates)

        print(f"\n{'='*60}\nDEPLOYMENT RECOMMENDATIONS ({len(recommendations)} total)\n{'='*60}")
        for rec in recommendations:
            status = "✅" if rec.is_within_limits else "⚠️"
            print(
                f"{status} [{rec.account_id}] {rec.strategy.upper()} "
                f"{rec.ticker} × {rec.contracts} | "
                f"Collateral: ${rec.collateral:,.0f} ({rec.pct_of_equity:.1%}) | "
                f"{rec.rationale[:80]}"
            )
            for w in rec.warnings:
                print(f"   {w}")

        if roll_actions:
            print(f"\n{rebalancer.summary(roll_actions)}")
        else:
            print("\nNo roll or close actions required.")

        if dry_run:
            print("\n[DRY RUN COMPLETE — No orders placed]")
        else:
            print("\nReady to execute. Pass recommendations to OrderHandler.")

    except KeyboardInterrupt:
        logger.info("Session terminated by user.")
    except Exception as e:
        logger.error(f"Session error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
