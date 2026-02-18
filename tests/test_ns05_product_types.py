"""NS5b tests — ReturnTerms, TerminationProvision, CalculationAgent,
and enriched EconomicTerms aligned to CDM Rosetta product-template.
"""

from __future__ import annotations

from datetime import date

import pytest

from attestor.core.money import NonEmptyStr
from attestor.core.types import BusinessDayAdjustments
from attestor.instrument.derivative_types import (
    CalculationAgent,
    ReturnTerms,
    TerminationProvision,
)
from attestor.instrument.types import (
    EconomicTerms,
    EquityPayoutSpec,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _equity_payout() -> EquityPayoutSpec:
    return EquityPayoutSpec(
        instrument_id=NonEmptyStr(value="AAPL"),
        currency=NonEmptyStr(value="USD"),
        exchange=NonEmptyStr(value="XNAS"),
    )


def _bda() -> BusinessDayAdjustments:
    return BusinessDayAdjustments(
        convention="ModifiedFollowing",
        business_centers=frozenset({"USNY"}),
    )


# ---------------------------------------------------------------------------
# ReturnTerms
# ---------------------------------------------------------------------------


class TestReturnTerms:
    def test_price_return(self) -> None:
        rt = ReturnTerms(price_return=True)
        assert rt.price_return is True
        assert rt.dividend_return is False

    def test_total_return(self) -> None:
        rt = ReturnTerms(price_return=True, dividend_return=True)
        assert rt.price_return is True
        assert rt.dividend_return is True

    def test_variance_return(self) -> None:
        rt = ReturnTerms(variance_return=True)
        assert rt.variance_return is True

    def test_volatility_return(self) -> None:
        rt = ReturnTerms(volatility_return=True)
        assert rt.volatility_return is True

    def test_correlation_return(self) -> None:
        rt = ReturnTerms(correlation_return=True)
        assert rt.correlation_return is True

    def test_no_return_rejected(self) -> None:
        with pytest.raises(TypeError, match="at least one return type"):
            ReturnTerms()

    def test_all_false_rejected(self) -> None:
        with pytest.raises(TypeError, match="at least one return type"):
            ReturnTerms(
                price_return=False, dividend_return=False,
                variance_return=False, volatility_return=False,
                correlation_return=False,
            )

    def test_frozen(self) -> None:
        rt = ReturnTerms(price_return=True)
        with pytest.raises(AttributeError):
            rt.price_return = False  # type: ignore[misc]

    def test_non_bool_rejected(self) -> None:
        with pytest.raises(TypeError, match="must be bool"):
            ReturnTerms(price_return=1)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# CalculationAgent
# ---------------------------------------------------------------------------


class TestCalculationAgent:
    def test_default(self) -> None:
        ca = CalculationAgent()
        assert ca.calculation_agent_party is None

    def test_with_party(self) -> None:
        ca = CalculationAgent(
            calculation_agent_party=NonEmptyStr(value="AGENT_A"),
        )
        assert ca.calculation_agent_party is not None

    def test_with_center(self) -> None:
        ca = CalculationAgent(
            calculation_agent_business_center=NonEmptyStr(value="USNY"),
        )
        assert ca.calculation_agent_business_center is not None

    def test_invalid_type_rejected(self) -> None:
        with pytest.raises(TypeError, match="NonEmptyStr or None"):
            CalculationAgent(
                calculation_agent_party="raw_string",  # type: ignore[arg-type]
            )

    def test_frozen(self) -> None:
        ca = CalculationAgent()
        with pytest.raises(AttributeError):
            ca.calculation_agent_party = None  # type: ignore[misc]


# ---------------------------------------------------------------------------
# TerminationProvision
# ---------------------------------------------------------------------------


class TestTerminationProvision:
    def test_cancelable(self) -> None:
        tp = TerminationProvision(cancelable=True)
        assert tp.cancelable is True
        assert tp.early_termination is False

    def test_early_termination(self) -> None:
        tp = TerminationProvision(early_termination=True)
        assert tp.early_termination is True

    def test_evergreen(self) -> None:
        tp = TerminationProvision(evergreen=True)
        assert tp.evergreen is True

    def test_extendible(self) -> None:
        tp = TerminationProvision(extendible=True)
        assert tp.extendible is True

    def test_recallable(self) -> None:
        tp = TerminationProvision(recallable=True)
        assert tp.recallable is True

    def test_multiple_provisions(self) -> None:
        tp = TerminationProvision(cancelable=True, extendible=True)
        assert tp.cancelable is True
        assert tp.extendible is True

    def test_no_provision_rejected(self) -> None:
        with pytest.raises(TypeError, match="at least one provision"):
            TerminationProvision()

    def test_all_false_rejected(self) -> None:
        with pytest.raises(TypeError, match="at least one provision"):
            TerminationProvision(
                cancelable=False, early_termination=False,
                evergreen=False, extendible=False, recallable=False,
            )

    def test_frozen(self) -> None:
        tp = TerminationProvision(cancelable=True)
        with pytest.raises(AttributeError):
            tp.cancelable = False  # type: ignore[misc]

    def test_non_bool_rejected(self) -> None:
        with pytest.raises(TypeError, match="must be bool"):
            TerminationProvision(cancelable=1)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# EconomicTerms enrichment
# ---------------------------------------------------------------------------


class TestEconomicTermsEnriched:
    def test_basic_unchanged(self) -> None:
        """Existing constructor still works with no new fields."""
        et = EconomicTerms(
            payouts=(_equity_payout(),),
            effective_date=date(2025, 1, 1),
            termination_date=None,
        )
        assert et.date_adjustments is None
        assert et.termination_provision is None
        assert et.calculation_agent is None
        assert et.non_standardised_terms is None

    def test_with_date_adjustments(self) -> None:
        bda = _bda()
        et = EconomicTerms(
            payouts=(_equity_payout(),),
            effective_date=date(2025, 1, 1),
            termination_date=date(2026, 1, 1),
            date_adjustments=bda,
        )
        assert et.date_adjustments is bda

    def test_with_termination_provision(self) -> None:
        tp = TerminationProvision(cancelable=True)
        et = EconomicTerms(
            payouts=(_equity_payout(),),
            effective_date=date(2025, 1, 1),
            termination_date=date(2026, 1, 1),
            termination_provision=tp,
        )
        assert et.termination_provision is tp

    def test_with_calculation_agent(self) -> None:
        ca = CalculationAgent(
            calculation_agent_party=NonEmptyStr(value="AGENT_A"),
        )
        et = EconomicTerms(
            payouts=(_equity_payout(),),
            effective_date=date(2025, 1, 1),
            termination_date=None,
            calculation_agent=ca,
        )
        assert et.calculation_agent is ca

    def test_with_non_standardised_terms(self) -> None:
        et = EconomicTerms(
            payouts=(_equity_payout(),),
            effective_date=date(2025, 1, 1),
            termination_date=None,
            non_standardised_terms=True,
        )
        assert et.non_standardised_terms is True

    def test_all_new_fields(self) -> None:
        et = EconomicTerms(
            payouts=(_equity_payout(),),
            effective_date=date(2025, 1, 1),
            termination_date=date(2026, 1, 1),
            date_adjustments=_bda(),
            termination_provision=TerminationProvision(
                early_termination=True,
            ),
            calculation_agent=CalculationAgent(),
            non_standardised_terms=False,
        )
        assert et.date_adjustments is not None
        assert et.termination_provision is not None
        assert et.calculation_agent is not None
        assert et.non_standardised_terms is False

    def test_invalid_date_adjustments_rejected(self) -> None:
        with pytest.raises(TypeError, match="BusinessDayAdjustments"):
            EconomicTerms(
                payouts=(_equity_payout(),),
                effective_date=date(2025, 1, 1),
                termination_date=None,
                date_adjustments="invalid",  # type: ignore[arg-type]
            )

    def test_invalid_termination_provision_rejected(self) -> None:
        with pytest.raises(TypeError, match="TerminationProvision"):
            EconomicTerms(
                payouts=(_equity_payout(),),
                effective_date=date(2025, 1, 1),
                termination_date=None,
                termination_provision="invalid",  # type: ignore[arg-type]
            )

    def test_invalid_calculation_agent_rejected(self) -> None:
        with pytest.raises(TypeError, match="CalculationAgent"):
            EconomicTerms(
                payouts=(_equity_payout(),),
                effective_date=date(2025, 1, 1),
                termination_date=None,
                calculation_agent="invalid",  # type: ignore[arg-type]
            )

    def test_invalid_non_standardised_terms_rejected(self) -> None:
        with pytest.raises(TypeError, match="bool or None"):
            EconomicTerms(
                payouts=(_equity_payout(),),
                effective_date=date(2025, 1, 1),
                termination_date=None,
                non_standardised_terms=1,  # type: ignore[arg-type]
            )

    def test_frozen(self) -> None:
        et = EconomicTerms(
            payouts=(_equity_payout(),),
            effective_date=date(2025, 1, 1),
            termination_date=None,
        )
        with pytest.raises(AttributeError):
            et.date_adjustments = _bda()  # type: ignore[misc]
