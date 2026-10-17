from datetime import datetime, timedelta, timezone
from decimal import Decimal

from data.models import Candle

START = datetime(2024, 1, 1, tzinfo=timezone.utc)


def candle(index: int = 0, open: str = "100", high: str = "100",
           low: str = "100", close: str = "100") -> Candle:
    return Candle(START + timedelta(minutes=15 * index), Decimal(open), Decimal(high),
                  Decimal(low), Decimal(close), Decimal("1000"))
