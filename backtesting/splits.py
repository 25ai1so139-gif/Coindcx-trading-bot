"""Explicit chronological ranges with read-only past warmup and flat boundaries."""

from dataclasses import dataclass
from datetime import datetime

from config import Settings
from data.loader import MarketData
from data.schema import INTERVAL, utc


@dataclass(frozen=True, slots=True)
class SplitPlan:
    train_start: datetime
    validation_start: datetime
    test_start: datetime
    test_end: datetime
    min_evaluation_bars: int = 2880

    def __post_init__(self) -> None:
        for name in ("train_start", "validation_start", "test_start", "test_end"):
            stamp = utc(getattr(self, name))
            if stamp.minute % 15 or stamp.second or stamp.microsecond:
                raise ValueError("split boundaries must align to 15-minute UTC candles")
            object.__setattr__(self, name, stamp)
        if not self.train_start < self.validation_start < self.test_start < self.test_end:
            raise ValueError("require train_start < validation_start < test_start < test_end")
        if type(self.min_evaluation_bars) is not int or self.min_evaluation_bars < 200:
            raise ValueError("min_evaluation_bars must be an integer of at least 200")


@dataclass(frozen=True, slots=True)
class Period:
    name: str
    start: datetime
    end: datetime
    warmup_bars: int
    market: MarketData


def chronological_periods(market: MarketData, settings: Settings, strategy_minimum: int,
                          plan: SplitPlan) -> tuple[Period, ...]:
    if not market.candles:
        raise ValueError("insufficient evidence: no candles")
    required = max(settings.min_history_bars, strategy_minimum)
    first = market.candles[0].timestamp
    final = market.candles[-1].closed_at
    periods = []
    bounds = (plan.train_start, plan.validation_start, plan.test_start, plan.test_end)
    for name, start, end in zip(("train", "validation", "test"), bounds, bounds[1:]):
        index = (start - first) // INTERVAL
        count = (end - start) // INTERVAL
        if start < first or end > final or index < required:
            raise ValueError(f"insufficient evidence: {name} lacks requested coverage or preceding warmup")
        if count < plan.min_evaluation_bars:
            raise ValueError(f"insufficient evidence: {name} has {count} bars; need {plan.min_evaluation_bars}")
        candles = market.candles[index - required:index + count]
        if len(candles) != required + count or candles[required].timestamp != start or candles[-1].closed_at != end:
            raise ValueError("split coverage is not exact; data must be validated, ordered and gap-free")
        periods.append(Period(name, start, end, required,
                              MarketData(market.symbol, market.quote_currency, market.kind, market.source, candles)))
    return tuple(periods)
