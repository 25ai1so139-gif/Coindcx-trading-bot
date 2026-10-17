"""Explicit inputs to offline entry approval; no exchange or credential fields."""

from dataclasses import dataclass, replace
from decimal import Decimal

from config import Settings
from data.models import Candle
from strategies.base import StrategyDecision


@dataclass(frozen=True, slots=True)
class InstrumentSpec:
    product: str
    quantity_step: Decimal
    minimum_quantity: Decimal
    minimum_notional: Decimal
    max_leverage: Decimal
    verified: bool
    symbol: str


@dataclass(frozen=True, slots=True)
class CostAssumptions:
    fee_rate: Decimal
    slippage_rate: Decimal
    declared: bool


@dataclass(frozen=True, slots=True)
class MarketContext:
    symbol: str
    timeframe: str
    quote_currency: str
    kind: str
    eligible: bool
    quality_reviewed: bool
    liquidity_verified: bool
    instrument: InstrumentSpec | None
    costs: CostAssumptions | None
    max_staleness_minutes: int = 30

    @classmethod
    def synthetic(cls, symbol: str, settings: Settings, *, allow_synthetic: bool) -> "MarketContext":
        if allow_synthetic is not True:
            raise ValueError("synthetic risk context requires explicit opt-in")
        return cls(symbol, "15m", "INR", "synthetic", True, False, False,
                   InstrumentSpec("abstract_synthetic", Decimal("0.00000001"), Decimal("0"),
                                  Decimal("0"), Decimal("3"), False, symbol),
                   CostAssumptions(settings.fee_rate, settings.slippage_rate, True))

    @classmethod
    def reviewed(cls, metadata: dict, quality: dict, settings: Settings) -> "MarketContext":
        if metadata.get("kind") == "synthetic":
            context = cls.synthetic(metadata["symbol"], settings, allow_synthetic=True)
            return replace(context, eligible=quality.get("eligible") is True,
                           max_staleness_minutes=min(30, quality["policy"]["max_staleness_minutes"]))
        instrument = metadata.get("instrument")
        costs = metadata.get("execution_assumptions")
        return cls(metadata["symbol"], metadata["timeframe"], metadata["quote_currency"], metadata["kind"],
                   quality.get("eligible") is True, metadata.get("quality_reviewed") is True,
                   quality.get("liquidity") == "MEETS_CONFIGURED_THRESHOLD",
                   InstrumentSpec(**instrument) if isinstance(instrument, dict) else None,
                   CostAssumptions(**costs) if isinstance(costs, dict) else None,
                   min(30, quality["policy"]["max_staleness_minutes"]))


@dataclass(frozen=True, slots=True)
class EntryProposal:
    strategy: str
    decision: StrategyDecision
    candles: tuple[Candle, ...]
    market: MarketContext | None
    reference_price: Decimal
