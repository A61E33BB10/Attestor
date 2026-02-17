"""attestor.oracle — Attestation, Confidence types, and market data ingest."""

# Phase 3: Arbitrage gates
from attestor.oracle.arbitrage_gates import (
    ArbitrageCheckResult as ArbitrageCheckResult,
)
from attestor.oracle.arbitrage_gates import (
    ArbitrageCheckType as ArbitrageCheckType,
)
from attestor.oracle.arbitrage_gates import CheckSeverity as CheckSeverity

# Phase 4: Arbitrage gates
from attestor.oracle.arbitrage_gates import (
    check_credit_curve_arbitrage_freedom as check_credit_curve_arbitrage_freedom,
)
from attestor.oracle.arbitrage_gates import (
    check_fx_spot_forward_consistency as check_fx_spot_forward_consistency,
)
from attestor.oracle.arbitrage_gates import (
    check_fx_triangular_arbitrage as check_fx_triangular_arbitrage,
)
from attestor.oracle.arbitrage_gates import (
    check_vol_surface_arbitrage_freedom as check_vol_surface_arbitrage_freedom,
)
from attestor.oracle.arbitrage_gates import (
    check_yield_curve_arbitrage_freedom as check_yield_curve_arbitrage_freedom,
)
from attestor.oracle.attestation import Attestation as Attestation
from attestor.oracle.attestation import Confidence as Confidence
from attestor.oracle.attestation import DerivedConfidence as DerivedConfidence
from attestor.oracle.attestation import FirmConfidence as FirmConfidence
from attestor.oracle.attestation import QuoteCondition as QuoteCondition
from attestor.oracle.attestation import QuotedConfidence as QuotedConfidence
from attestor.oracle.attestation import create_attestation as create_attestation

# Phase 3: Calibration
from attestor.oracle.calibration import CalibrationResult as CalibrationResult
from attestor.oracle.calibration import (
    FailedCalibrationRecord as FailedCalibrationRecord,
)
from attestor.oracle.calibration import ModelConfig as ModelConfig
from attestor.oracle.calibration import RateInstrument as RateInstrument
from attestor.oracle.calibration import YieldCurve as YieldCurve
from attestor.oracle.calibration import bootstrap_curve as bootstrap_curve
from attestor.oracle.calibration import discount_factor as discount_factor
from attestor.oracle.calibration import forward_rate as forward_rate
from attestor.oracle.calibration import (
    handle_calibration_failure as handle_calibration_failure,
)

# Phase 4: Credit curve
from attestor.oracle.credit_curve import CDSQuote as CDSQuote
from attestor.oracle.credit_curve import CreditCurve as CreditCurve
from attestor.oracle.credit_curve import bootstrap_credit_curve as bootstrap_credit_curve
from attestor.oracle.credit_curve import hazard_rate as hazard_rate
from attestor.oracle.credit_curve import survival_probability as survival_probability

# Phase 4: Credit ingest
from attestor.oracle.credit_ingest import AuctionResult as AuctionResult
from attestor.oracle.credit_ingest import CDSSpreadQuote as CDSSpreadQuote
from attestor.oracle.credit_ingest import CreditEventRecord as CreditEventRecord
from attestor.oracle.credit_ingest import ingest_auction_result as ingest_auction_result
from attestor.oracle.credit_ingest import ingest_cds_spread as ingest_cds_spread
from attestor.oracle.credit_ingest import ingest_credit_event as ingest_credit_event

# Phase 3: FX/IRS oracle types
from attestor.oracle.fx_ingest import FXRate as FXRate
from attestor.oracle.fx_ingest import RateFixing as RateFixing
from attestor.oracle.fx_ingest import ingest_fx_rate as ingest_fx_rate
from attestor.oracle.fx_ingest import ingest_fx_rate_firm as ingest_fx_rate_firm
from attestor.oracle.fx_ingest import ingest_rate_fixing as ingest_rate_fixing
from attestor.oracle.ingest import MarketDataPoint as MarketDataPoint
from attestor.oracle.ingest import ingest_equity_fill as ingest_equity_fill
from attestor.oracle.ingest import ingest_equity_quote as ingest_equity_quote

# Phase B: Observable and Index Taxonomy
from attestor.oracle.observable import CalculationMethodEnum as CalculationMethodEnum
from attestor.oracle.observable import CreditIndex as CreditIndex
from attestor.oracle.observable import EquityIndex as EquityIndex
from attestor.oracle.observable import (
    FloatingRateCalculationParameters as FloatingRateCalculationParameters,
)
from attestor.oracle.observable import FloatingRateIndex as FloatingRateIndex
from attestor.oracle.observable import FloatingRateIndexEnum as FloatingRateIndexEnum
from attestor.oracle.observable import FXRateIndex as FXRateIndex
from attestor.oracle.observable import ObservationIdentifier as ObservationIdentifier
from attestor.oracle.observable import Price as Price
from attestor.oracle.observable import PriceExpressionEnum as PriceExpressionEnum
from attestor.oracle.observable import PriceQuantity as PriceQuantity
from attestor.oracle.observable import PriceTypeEnum as PriceTypeEnum
from attestor.oracle.observable import ResetDates as ResetDates

# Phase 4: Vol surface
from attestor.oracle.vol_surface import SVIParameters as SVIParameters
from attestor.oracle.vol_surface import VolSurface as VolSurface
from attestor.oracle.vol_surface import implied_vol as implied_vol
from attestor.oracle.vol_surface import svi_first_derivative as svi_first_derivative
from attestor.oracle.vol_surface import svi_second_derivative as svi_second_derivative
from attestor.oracle.vol_surface import svi_total_variance as svi_total_variance
