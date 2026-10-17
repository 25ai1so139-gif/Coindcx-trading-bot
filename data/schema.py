"""Normalized 15-minute records; zero volume is preserved for quality analysis."""

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import re
from typing import Mapping

from config import decimal_value

INTERVAL = timedelta(minutes=15)
SYMBOL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}\Z")
FIELDS = ("timestamp", "open", "high", "low", "close", "volume", "symbol", "timeframe")


def utc(value: datetime | str) -> datetime:
    result = datetime.fromisoformat(value) if isinstance(value, str) else value
    if not isinstance(result, datetime) or result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("timestamp must include a timezone")
    try:
        return result.astimezone(timezone.utc)
    except OverflowError as exc:
        raise ValueError("timestamp is outside the supported UTC date range") from exc


def milliseconds(value: object) -> datetime:
    number = decimal_value(value, "time")
    if number != number.to_integral_value():
        raise ValueError("time must be integer milliseconds")
    try:
        return datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(milliseconds=int(number))
    except OverflowError as exc:
        raise ValueError("timestamp is outside the supported date range") from exc


def epoch_ms(value: datetime) -> int:
    return (utc(value) - datetime(1970, 1, 1, tzinfo=timezone.utc)) // timedelta(milliseconds=1)


@dataclass(frozen=True, slots=True)
class CandleRecord:
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    symbol: str
    timeframe: str = "15m"
    quote_volume: Decimal | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "timestamp", utc(self.timestamp))
        if (self.timestamp.minute % 15 or self.timestamp.second or self.timestamp.microsecond):
            raise ValueError("timestamp is not aligned to 15 minutes")
        try:
            self.timestamp + INTERVAL
        except OverflowError as exc:
            raise ValueError("candle closing time is outside the supported date range") from exc
        if not isinstance(self.symbol, str) or not SYMBOL.fullmatch(self.symbol):
            raise ValueError("invalid symbol")
        if self.timeframe != "15m":
            raise ValueError("only 15m candles are supported")
        for field in ("open", "high", "low", "close", "volume", "quote_volume"):
            raw = getattr(self, field)
            if field == "quote_volume" and raw is None:
                continue
            value = decimal_value(raw, field)
            if value < 0 or (field not in {"volume", "quote_volume"} and value == 0):
                raise ValueError(f"invalid {field}: prices must be positive, volumes nonnegative")
            object.__setattr__(self, field, value)
        if not self.low <= min(self.open, self.close) <= max(self.open, self.close) <= self.high:
            raise ValueError("impossible OHLC relationship")

    @property
    def closed_at(self) -> datetime:
        return self.timestamp + INTERVAL

    def row(self) -> dict[str, str]:
        values = asdict(self)
        values["timestamp"] = self.timestamp.isoformat()
        return {key: "" if value is None else str(value) for key, value in values.items()}


def normalize(row: Mapping[str, object], symbol: str, timeframe: str = "15m") -> CandleRecord:
    values = dict(row)
    if None in values:
        raise ValueError("incorrect CSV column count")
    values.setdefault("symbol", symbol)
    values.setdefault("timeframe", timeframe)
    missing = [key for key in FIELDS if key not in values or values[key] in (None, "")]
    if missing:
        raise ValueError("missing required fields: " + ", ".join(missing))
    if values["symbol"] != symbol or values["timeframe"] != timeframe:
        raise ValueError("mixed symbol or timeframe")
    quote_volume = values.get("quote_volume")
    if quote_volume == "":
        quote_volume = None
    return CandleRecord(**{key: values[key] for key in FIELDS}, quote_volume=quote_volume)
