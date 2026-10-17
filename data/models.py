from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from config import decimal_value


@dataclass(frozen=True, slots=True)
class Candle:
    """timestamp is the UTC opening time of a completed 15-minute candle."""

    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("candle timestamp must include a timezone")
        object.__setattr__(self, "timestamp", self.timestamp.astimezone(timezone.utc))
        if (self.timestamp.minute % 15 or self.timestamp.second
                or self.timestamp.microsecond):
            raise ValueError("candles must align to 15-minute boundaries")
        for name in ("open", "high", "low", "close", "volume"):
            value = decimal_value(getattr(self, name), name)
            if value <= 0:
                raise ValueError(f"{name} must be positive")
            object.__setattr__(self, name, value)
        if not self.low <= min(self.open, self.close) <= max(self.open, self.close) <= self.high:
            raise ValueError("invalid OHLC range")

    @property
    def closed_at(self) -> datetime:
        return self.timestamp + timedelta(minutes=15)
