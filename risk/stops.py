from decimal import Decimal

from config import decimal_value
from data.models import Candle


def long_stop_reference(candle: Candle, trigger: Decimal) -> Decimal | None:
    """Return the pre-slippage exit price; gaps cannot fill at a better trigger."""
    trigger = decimal_value(trigger, "stop trigger")
    if trigger <= 0:
        raise ValueError("stop trigger must be positive")
    return min(candle.open, trigger) if candle.low <= trigger else None
