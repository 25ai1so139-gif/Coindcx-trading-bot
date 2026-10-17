from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence

from data.models import Candle
from strategies.base import Signal


@dataclass(frozen=True)
class SmaCross:
    fast: int = 5
    slow: int = 20

    def __post_init__(self) -> None:
        if type(self.fast) is not int or type(self.slow) is not int or not 1 <= self.fast < self.slow:
            raise ValueError("SMA windows require 1 <= fast < slow")

    @property
    def minimum_bars(self) -> int:
        return self.slow + 1

    def signal(self, candles: Sequence[Candle]) -> Signal:
        if len(candles) < self.minimum_bars:
            return Signal.HOLD
        prices = [c.close for c in candles[-self.minimum_bars:]]

        def mean(values: list[Decimal]) -> Decimal:
            return sum(values, Decimal("0")) / len(values)

        previous_fast = mean(prices[-self.fast - 1:-1])
        previous_slow = mean(prices[-self.slow - 1:-1])
        current_fast = mean(prices[-self.fast:])
        current_slow = mean(prices[-self.slow:])
        if previous_fast <= previous_slow and current_fast > current_slow:
            return Signal.BUY
        if previous_fast >= previous_slow and current_fast < current_slow:
            return Signal.SELL
        return Signal.HOLD
