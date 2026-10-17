from dataclasses import dataclass
from decimal import Decimal
from typing import ClassVar, Sequence

from config import decimal_value
from data.models import Candle
from strategies.base import Direction, ValidatedStrategy


@dataclass(frozen=True)
class Momentum(ValidatedStrategy):
    name: ClassVar[str] = "momentum"
    lookback: int = 12
    threshold: Decimal = Decimal("0.01")

    def __post_init__(self) -> None:
        object.__setattr__(self, "threshold", decimal_value(self.threshold, "threshold"))
        if type(self.lookback) is not int or self.lookback < 1 or not 0 < self.threshold < 1:
            raise ValueError("momentum requires a positive lookback and threshold between 0 and 1")

    @property
    def minimum_bars(self) -> int:
        return self.lookback + 1

    def _calculate(self, candles: Sequence[Candle]):
        change = candles[-1].close / candles[-self.minimum_bars].close - 1
        indicators = {"return_fraction": change, "threshold": self.threshold}
        if change >= self.threshold:
            return Direction.LONG, "POSITIVE_MOMENTUM", "Return meets the positive threshold.", indicators
        if change <= -self.threshold:
            return Direction.SHORT, "NEGATIVE_MOMENTUM", "Return meets the negative threshold.", indicators
        return Direction.NO_TRADE, "BELOW_THRESHOLD", "Return is inside the momentum thresholds.", indicators
