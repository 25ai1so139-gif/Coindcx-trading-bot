"""Closed-candle analytical decisions plus the original replay adapter."""

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from decimal import Decimal, DecimalException
from enum import Enum
from typing import ClassVar, Protocol, Sequence

from config import decimal_value
from data.models import Candle
from data.schema import INTERVAL, SYMBOL, utc


class Signal(str, Enum):
    """Legacy long-only replay actions: SELL exits a long, never opens a short."""

    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


class Direction(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    NO_TRADE = "NO_TRADE"


@dataclass(frozen=True, slots=True)
class StrategyDecision:
    signal: Direction
    timestamp: datetime | None
    strategy: str
    symbol: str
    timeframe: str
    entry_reference: Decimal | None
    stop_loss_reference: Decimal | None
    reason_code: str
    reason: str
    indicators: dict[str, Decimal] = field(default_factory=dict)


def replay_action(direction: Direction) -> Signal:
    """Preserve existing long-only fills and all existing broker risk controls."""
    return {Direction.LONG: Signal.BUY, Direction.SHORT: Signal.SELL,
            Direction.NO_TRADE: Signal.HOLD}[direction]


class InvalidHistory(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class InvalidDecision(ValueError):
    """A strategy result does not satisfy the closed-candle decision contract."""


def validate_decision(decision: StrategyDecision, *, strategy: str,
                      candles: Sequence[Candle], as_of: datetime, symbol: str,
                      timeframe: str, stop_loss_fraction: Decimal) -> StrategyDecision:
    """Validate results at the verifier/replay boundary, including custom strategies."""
    try:
        if not isinstance(decision, StrategyDecision) or not isinstance(decision.signal, Direction):
            raise InvalidDecision("decision must contain an explicit Direction")
        if (decision.strategy != strategy or decision.symbol != symbol or decision.timeframe != timeframe):
            raise InvalidDecision("decision strategy, symbol or timeframe does not match the request")
        if any(not isinstance(value, str) or not value.strip()
               for value in (decision.reason_code, decision.reason)):
            raise InvalidDecision("decision must explain its reason")
        if (not isinstance(decision.indicators, dict)
                or any(not isinstance(key, str) or not key for key in decision.indicators)):
            raise InvalidDecision("decision indicators must be named finite numbers")
        indicators = {key: decimal_value(value, key) for key, value in decision.indicators.items()}
        stamp = utc(decision.timestamp) if decision.timestamp is not None else None
        if stamp is not None and stamp > utc(as_of):
            raise InvalidDecision("decision timestamp is after the evaluation time")
        if decision.signal == Direction.NO_TRADE:
            if decision.entry_reference is not None or decision.stop_loss_reference is not None:
                raise InvalidDecision("a NO_TRADE decision cannot propose an entry or stop")
            return replace(decision, timestamp=stamp, indicators=indicators)
        if not candles or stamp is None or stamp != candles[-1].closed_at:
            raise InvalidDecision("decision timestamp must match the last completed candle")
        entry = decimal_value(decision.entry_reference, "decision entry")
        stop = decimal_value(decision.stop_loss_reference, "decision stop")
        fraction = decimal_value(stop_loss_fraction, "stop_loss_fraction")
        if not 0 < fraction < 1 or entry != candles[-1].close or entry <= 0:
            raise InvalidDecision("decision entry or stop fraction does not match the validated context")
        protective = 0 < stop < entry if decision.signal == Direction.LONG else stop > entry
        expected = entry * (1 - fraction if decision.signal == Direction.LONG else 1 + fraction)
        if not protective or stop != expected:
            raise InvalidDecision("decision stop must be protective and match the configured distance")
        return replace(decision, timestamp=stamp, entry_reference=entry,
                       stop_loss_reference=stop, indicators=indicators)
    except InvalidDecision:
        raise
    except (ValueError, TypeError, ArithmeticError, AttributeError) as exc:
        raise InvalidDecision(f"invalid strategy decision: {exc}") from exc


def validate_history(candles: Sequence[Candle], as_of: datetime) -> tuple[Candle, ...]:
    """Shared preflight for direct strategy and replay callers."""
    as_of = utc(as_of)
    if not isinstance(candles, Sequence) or isinstance(candles, (str, bytes)):
        raise InvalidHistory("INVALID_CANDLES", "Supply a sequence of validated Candle records.")
    checked_records, seen = [], set()
    previous = None
    for record in candles:
        if not isinstance(record, Candle):
            raise InvalidHistory("INVALID_CANDLES", "Missing fields or non-Candle records.")
        checked = Candle(record.timestamp, record.open, record.high, record.low, record.close, record.volume)
        if checked.timestamp > as_of:
            raise InvalidHistory("FUTURE_DATA", "A candle opens after the evaluation time.")
        if checked.closed_at > as_of:
            raise InvalidHistory("INCOMPLETE_CANDLE", "Every input candle must be closed.")
        if checked.timestamp in seen:
            raise InvalidHistory("DUPLICATE_TIMESTAMP", "Duplicate candle opening time.")
        seen.add(checked.timestamp)
        if previous is not None and checked.timestamp - previous != INTERVAL:
            raise InvalidHistory("INVALID_CANDLE_SEQUENCE", "Candles must be ordered and gap-free.")
        previous = checked.timestamp
        checked_records.append(checked)
    return tuple(checked_records)


class Strategy(Protocol):
    name: str
    minimum_bars: int

    def evaluate(self, candles: Sequence[Candle], *, as_of: datetime, symbol: str,
                 timeframe: str = "15m", stop_loss_fraction: Decimal = Decimal("0.02")) -> StrategyDecision: ...

    def signal(self, candles: Sequence[Candle]) -> Signal: ...


class ValidatedStrategy:
    name: ClassVar[str]

    def evaluate(self, candles: Sequence[Candle], *, as_of: datetime, symbol: str,
                 timeframe: str = "15m", stop_loss_fraction: Decimal = Decimal("0.02")) -> StrategyDecision:
        stamp = None

        def abstain(code: str, detail: str) -> StrategyDecision:
            return StrategyDecision(Direction.NO_TRADE, stamp, self.name, symbol, timeframe,
                                    None, None, code, detail)

        try:
            stamp = utc(as_of)
            if stamp > datetime.now(timezone.utc):
                return abstain("FUTURE_EVALUATION_TIME", "Evaluation time cannot be in the future.")
            if not isinstance(symbol, str) or not SYMBOL.fullmatch(symbol):
                return abstain("INVALID_SYMBOL", "A valid native market symbol is required.")
            if timeframe != "15m":
                return abstain("INVALID_TIMEFRAME", "Only 15m candles are supported.")
            fraction = decimal_value(stop_loss_fraction, "stop_loss_fraction")
            if not 0 < fraction < 1:
                return abstain("INVALID_STOP", "Stop fraction must be between zero and one.")
            candles = validate_history(candles, stamp)
            if len(candles) < self.minimum_bars:
                return abstain("INSUFFICIENT_DATA", f"Need at least {self.minimum_bars} completed candles.")
        except InvalidHistory as exc:
            return abstain(exc.code, str(exc))
        except (ValueError, TypeError, AttributeError, OverflowError, DecimalException) as exc:
            return abstain("INVALID_CANDLES", str(exc))
        try:
            direction, code, reason, indicators = self._calculate(candles)
            if not isinstance(direction, Direction):
                raise ValueError("unsupported indicator direction")
            indicators = {key: decimal_value(value, key) for key, value in indicators.items()}
            entry = candles[-1].close if direction != Direction.NO_TRADE else None
            stop = (entry * (1 - fraction if direction == Direction.LONG else 1 + fraction)
                    if entry is not None else None)
            if stop is not None:
                protective = 0 < stop < entry if direction == Direction.LONG else stop > entry
                if not stop.is_finite() or not protective:
                    raise ValueError("stop distance is not protective at current Decimal precision")
            return StrategyDecision(direction, candles[-1].closed_at, self.name, symbol, timeframe,
                                    entry, stop, code, reason, indicators)
        except (ValueError, TypeError, ArithmeticError, AttributeError) as exc:
            return abstain("INVALID_INDICATOR", str(exc))

    def signal(self, candles: Sequence[Candle]) -> Signal:
        """Compatibility for original callers; new callers should use evaluate."""
        return replay_action(self.evaluate(candles, as_of=datetime.now(timezone.utc),
                                           symbol="LEGACY").signal)
