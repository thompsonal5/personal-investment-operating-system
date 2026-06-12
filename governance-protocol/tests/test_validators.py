"""
Risk Guardrail Tests — Fortress Edition PIOS
These tests ARE the risk management system.
If any test fails, the CI/CD pipeline must block the build.
A failing test = a risk violation caught before it reaches a live account.
"""

import pytest
from governance_protocol.validators.strategy_validator import (
    validate_strategy,
    validate_buying_power,
    validate_position_size,
)
from governance_protocol.validators.p1_p2_p3_chain import (
    run_triangulation,
    SignalStrength,
    GateResult,
    evaluate_p1,
    evaluate_p2,
    evaluate_p3,
)

ROTH_IRA_ID  = "821132974"
BROKERAGE_ID = "662458413"
AGENTIC_ID   = "636778128"


# ============================================================================
# Account strategy restriction tests (must never be bypassed)
# ============================================================================

class TestRothIRARestrictions:
    """Iron Butterflies are NEVER permitted in the Roth IRA."""

    def test_iron_butterfly_blocked_in_roth_ira(self):
        valid, error = validate_strategy(ROTH_IRA_ID, "iron_butterfly")
        assert not valid, "Iron butterfly must be blocked in Roth IRA"
        assert "RISK VIOLATION" in error

    def test_covered_call_allowed_in_roth_ira(self):
        valid, error = validate_strategy(ROTH_IRA_ID, "covered_call")
        assert valid
        assert error is None

    def test_csp_allowed_in_roth_ira(self):
        valid, error = validate_strategy(ROTH_IRA_ID, "cash_secured_put")
        assert valid
        assert error is None


class TestBrokerageRestrictions:
    """All four strategies permitted in Brokerage."""

    def test_iron_butterfly_allowed_in_brokerage(self):
        valid, error = validate_strategy(BROKERAGE_ID, "iron_butterfly")
        assert valid
        assert error is None

    def test_covered_call_allowed_in_brokerage(self):
        valid, error = validate_strategy(BROKERAGE_ID, "covered_call")
        assert valid

    def test_csp_allowed_in_brokerage(self):
        valid, error = validate_strategy(BROKERAGE_ID, "cash_secured_put")
        assert valid


class TestUnknownAccount:
    def test_unknown_account_blocked(self):
        valid, error = validate_strategy("999999999", "covered_call")
        assert not valid
        assert "Unknown account" in error


# ============================================================================
# Buying power / collateral tests
# ============================================================================

class TestBuyingPower:

    def test_insufficient_buying_power_blocked(self):
        valid, error = validate_buying_power(
            available_bp=500.0,
            required_collateral=1400.0,
            account_id=ROTH_IRA_ID,
        )
        assert not valid
        assert "INSUFFICIENT FUNDS" in error

    def test_exact_buying_power_passes(self):
        valid, error = validate_buying_power(
            available_bp=1400.0,
            required_collateral=1400.0,
            account_id=ROTH_IRA_ID,
        )
        assert valid

    def test_ample_buying_power_passes(self):
        valid, error = validate_buying_power(
            available_bp=14741.0,
            required_collateral=339.0,
            account_id=BROKERAGE_ID,
        )
        assert valid


class TestPositionSizing:

    def test_oversized_position_blocked(self):
        valid, error = validate_position_size(
            collateral=10000.0,
            total_account_equity=20000.0,
            max_pct=0.20,
        )
        assert not valid  # 50% > 20% max
        assert "POSITION LIMIT" in error

    def test_appropriately_sized_position_passes(self):
        valid, error = validate_position_size(
            collateral=3000.0,
            total_account_equity=37340.0,
            max_pct=0.20,
        )
        assert valid  # ~8% < 20%


# ============================================================================
# P1 gate tests
# ============================================================================

class TestP1Gate:

    def test_extreme_vix_fails(self):
        result = evaluate_p1(vix=45.0)
        assert result.gate == GateResult.FAIL
        assert result.regime == "EXTREME"

    def test_premium_friendly_vix_passes(self):
        result = evaluate_p1(vix=28.0)
        assert result.gate == GateResult.PASS
        assert result.regime == "PREMIUM_SELLING_FRIENDLY"

    def test_neutral_vix_passes(self):
        result = evaluate_p1(vix=19.44)
        assert result.gate == GateResult.PASS
        assert result.regime == "NEUTRAL"

    def test_defensive_vix_warns(self):
        result = evaluate_p1(vix=14.0)
        assert result.gate == GateResult.WARN
        assert result.regime == "DEFENSIVE"


# ============================================================================
# P2 gate tests
# ============================================================================

class TestP2Gate:

    def test_earnings_blackout_fails(self):
        result = evaluate_p2("F", "HIGH", iv_rank=45.0, earnings_days_out=3,
                             dividend_days_out=30)
        assert result.gate == GateResult.FAIL
        assert any("EARNINGS BLACKOUT" in f for f in result.flags)

    def test_earnings_warning_warns(self):
        result = evaluate_p2("F", "HIGH", iv_rank=45.0, earnings_days_out=10,
                             dividend_days_out=30)
        assert result.gate == GateResult.WARN

    def test_dividend_blackout_fails(self):
        result = evaluate_p2("F", "HIGH", iv_rank=45.0, earnings_days_out=60,
                             dividend_days_out=3)
        assert result.gate == GateResult.FAIL

    def test_low_quality_fails(self):
        result = evaluate_p2("SRNE", "LOW", iv_rank=80.0, earnings_days_out=60,
                             dividend_days_out=None)
        assert result.gate == GateResult.FAIL

    def test_clean_underlying_passes(self):
        result = evaluate_p2("IWM", "HIGH", iv_rank=74.0, earnings_days_out=None,
                             dividend_days_out=None)
        assert result.gate == GateResult.PASS


# ============================================================================
# P3 gate tests
# ============================================================================

class TestP3Gate:

    def test_below_threshold_fails(self):
        # $5 premium on $1000 collateral for 365 DTE = 0.5% ROI, 0.5% ann
        result = evaluate_p3("covered_call", premium=5.0, collateral=1000.0, dte=365)
        assert result.gate == GateResult.FAIL

    def test_above_threshold_passes(self):
        # $82 premium on $1492 collateral for 35 DTE = 5.5% ROI, ~57% ann
        result = evaluate_p3("covered_call", premium=82.0, collateral=1492.0, dte=35)
        assert result.gate == GateResult.PASS
        assert result.ann_roi_pct > 20.0

    def test_iron_butterfly_threshold(self):
        # $6.61 credit on $3.39 max risk = 195% ROI on capital at risk
        result = evaluate_p3("iron_butterfly", premium=6.61, collateral=3.39, dte=18)
        assert result.gate == GateResult.PASS


# ============================================================================
# Full chain integration tests
# ============================================================================

class TestFullChain:

    def test_blocked_when_p1_fails(self):
        result = run_triangulation(
            ticker="IWM", strategy="iron_butterfly",
            vix=45.0,                              # EXTREME — P1 FAIL
            quality_tier="HIGH", iv_rank=74.0,
            earnings_days_out=None, dividend_days_out=None,
            premium=6.61, collateral=3.39, dte=18,
        )
        assert result.signal == SignalStrength.BLOCKED

    def test_blocked_when_p2_fails(self):
        result = run_triangulation(
            ticker="F", strategy="covered_call",
            vix=19.44,
            quality_tier="HIGH", iv_rank=42.0,
            earnings_days_out=3,                   # EARNINGS BLACKOUT — P2 FAIL
            dividend_days_out=60,
            premium=82.0, collateral=1492.0, dte=35,
        )
        assert result.signal == SignalStrength.BLOCKED

    def test_strong_signal_all_clear(self):
        result = run_triangulation(
            ticker="IWM", strategy="iron_butterfly",
            vix=19.44,
            quality_tier="HIGH", iv_rank=74.0,
            earnings_days_out=None, dividend_days_out=None,
            premium=661.0, collateral=339.0, dte=18,
        )
        assert result.signal == SignalStrength.STRONG
        assert result.is_valid

    def test_nio_with_dod_flag_warns(self):
        result = run_triangulation(
            ticker="NIO", strategy="covered_call",
            vix=19.44,
            quality_tier="MEDIUM", iv_rank=55.0,
            earnings_days_out=89,   # Sep 9 earnings — clear
            dividend_days_out=None,
            premium=252.0, collateral=3710.0, dte=35,
            custom_flags=["[⚠️ DoD Chinese military companies designation Jun 9, 2026]"],
        )
        assert result.is_valid   # Should pass (not blocked)
        assert result.signal in (SignalStrength.NORMAL, SignalStrength.STRONG)
