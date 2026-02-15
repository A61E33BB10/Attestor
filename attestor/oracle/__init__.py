"""attestor.oracle — Attestation, Confidence types, and market data ingest."""

# Phase 3: Arbitrage gates
from attestor.oracle.arbitrage_gates import (
    ArbitrageCheckResult as ArbitrageCheckResult,
)
from attestor.oracle.arbitrage_gates import (
    ArbitrageCheckType as ArbitrageCheckType,
)
from attestor.oracle.arbitrage_gates import CheckSeverity as CheckSeverity
from attestor.oracle.arbitrage_gates import (
    check_fx_spot_forward_consistency as check_fx_spot_forward_consistency,
)
from attestor.oracle.arbitrage_gates import (
    check_fx_triangular_arbitrage as check_fx_triangular_arbitrage,
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

# Phase 3: FX/IRS oracle types
from attestor.oracle.fx_ingest import FXRate as FXRate
from attestor.oracle.fx_ingest import RateFixing as RateFixing
from attestor.oracle.fx_ingest import ingest_fx_rate as ingest_fx_rate
from attestor.oracle.fx_ingest import ingest_fx_rate_firm as ingest_fx_rate_firm
from attestor.oracle.fx_ingest import ingest_rate_fixing as ingest_rate_fixing
from attestor.oracle.ingest import MarketDataPoint as MarketDataPoint
from attestor.oracle.ingest import ingest_equity_fill as ingest_equity_fill
from attestor.oracle.ingest import ingest_equity_quote as ingest_equity_quote
