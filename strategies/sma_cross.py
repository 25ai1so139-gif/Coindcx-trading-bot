from dataclasses import dataclass
from decimal import Decimal
from typing import ClassVar, Sequence

from data.models import Candle
from strategies.base import Direction, ValidatedStrategy


@dataclass(frozen=True)
class SmaCross(ValidatedStrategy):
    name: ClassVar[str] = "sma_cross"
    fast: int = 5
    slow: int = 20

    def __post_init__(self) -> None:
        if type(self.fast) is not int or type(self.slow) is not int or not 1 <= self.fast < self.slow:
            raise ValueError("SMA windows require 1 <= fast < slow")

    @property
    def minimum_bars(self) -> int:
        return self.slow + 1

    def _calculate(self, candles: Sequence[Candle]):
        prices = [c.close for c in candles[-self.minimum_bars:]]

        def mean(values: list[Decimal]) -> Decimal:
            return sum(values, Decimal("0")) / len(values)

        previous_fast = mean(prices[-self.fast - 1:-1])
        previous_slow = mean(prices[-self.slow - 1:-1])
        current_fast = mean(prices[-self.fast:])
        current_slow = mean(prices[-self.slow:])
        indicators = {"previous_fast": previous_fast, "previous_slow": previous_slow,
                      "current_fast": current_fast, "current_slow": current_slow}
        if previous_fast <= previous_slow and current_fast > current_slow:
            return Direction.LONG, "BULLISH_CROSS", "Fast SMA crossed above slow SMA.", indicators
        if previous_fast >= previous_slow and current_fast < current_slow:
            return Direction.SHORT, "BEARISH_CROSS", "Fast SMA crossed below slow SMA.", indicators
        return Direction.NO_TRADE, "NO_CROSS", "No new SMA crossover on the last closed bar.", indicators
