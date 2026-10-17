from enum import Enum
from typing import Protocol, Sequence

from data.models import Candle


class Signal(str, Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


class Strategy(Protocol):
    minimum_bars: int

    def signal(self, candles: Sequence[Candle]) -> Signal: ...
