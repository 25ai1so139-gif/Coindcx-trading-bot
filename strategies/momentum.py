from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence

from config import decimal_value
from data.models import Candle
from strategies.base import Signal


@dataclass(frozen=True)
class Momentum:
    lookback: int = 12
    threshold: Decimal = Decimal("0.01")

    def __post_init__(self) -> None:
        object.__setattr__(self, "threshold", decimal_value(self.threshold, "threshold"))
        if type(self.lookback) is not int or self.lookback < 1 or not 0 < self.threshold < 1:
            raise ValueError("momentum requires a positive lookback and threshold between 0 and 1")

    @property
    def minimum_bars(self) -> int:
        return self.lookback + 1

    def signal(self, candles: Sequence[Candle]) -> Signal:
        if len(candles) < self.minimum_bars:
            return Signal.HOLD
        change = candles[-1].close / candles[-self.minimum_bars].close - 1
        if change >= self.threshold:
            return Signal.BUY
        if change <= -self.threshold:
            return Signal.SELL
        return Signal.HOLD
