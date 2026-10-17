"""Non-mutating volume diagnostics, separate from trading authorization."""

from decimal import Decimal, InvalidOperation
from collections.abc import Mapping
from datetime import datetime, timezone
from fractions import Fraction

from data.schema import epoch_ms, milliseconds, utc


def invalid_volume_reason(row):
    """Return a static reason, never replace a missing/invalid value with zero."""
    if not isinstance(row, Mapping):
        return None
    if "volume" not in row or row["volume"] is None or row["volume"] == "":
        return "VOLUME_MISSING"
    try:
        value = Decimal(str(row["volume"]))
    except (InvalidOperation, ValueError, TypeError):
        return "VOLUME_MALFORMED"
    if not value.is_finite():
        return "VOLUME_NONFINITE"
    if value < 0:
        return "VOLUME_NEGATIVE"
    return None


def zero_volume_diagnostic(record, row):
    """Structural zero is not proof of a source failure or of genuine no trades.

    Both existing strategies still require strictly positive-volume, eligible
    trading history. Research retention never supplies liquidity or a fill.
    """
    if record.volume != 0:
        return None
    flat = record.open == record.high == record.low == record.close
    return {"row": row, "timestamp": record.timestamp.isoformat(),
            "code": "ZERO_VOLUME_FLAT" if flat else "ZERO_VOLUME_PRICE_RANGE",
            "structurally_valid": True, "source_activity": "UNVERIFIED",
            "disposition": "QUARANTINED_FOR_TRADING"}


def interval_volume_check(bar, minutes, *, as_of=None):
    """Compare 15 complete minute volumes with a same-pair 15m raw bar.

    Caller must bind instrument/request identity. A match is not evidence of
    authentic trades; a mismatch is retained, never repaired or rounded away.
    """
    result = {"status": "UNVERIFIED", "code": "INCOMPLETE_OR_INVALID_MINUTE_COVERAGE",
              "minute_count": 0, "source_volume": None, "minute_sum": None}
    try:
        stamp = epoch_ms(milliseconds(bar["time"]))
        if stamp % 900000:
            return result
        cutoff = epoch_ms(utc(as_of if as_of is not None else datetime.now(timezone.utc)))
        if stamp + 900000 > cutoff:
            result["code"] = "INCOMPLETE_OR_FUTURE_INTERVAL"
            return result
        selected = []
        for row in minutes:
            time = epoch_ms(milliseconds(row["time"]))
            if stamp <= time < stamp + 900000:
                selected.append((time, row))
        result["minute_count"] = len(selected)
        if len(selected) != 15 or {time for time, _ in selected} != {stamp + i * 60000 for i in range(15)}:
            return result
        values = [bar, *(row for _, row in selected)]
        if any(invalid_volume_reason(row) is not None for row in values):
            return result
        numbers = [Decimal(str(row["volume"])) for row in values]
        if any(len(number.as_tuple().digits) > 32 or abs(number.as_tuple().exponent) > 32 for number in numbers):
            result["code"] = "UNSUPPORTED_VOLUME_PRECISION"
            return result
        total = sum((Fraction(value) for value in numbers[1:]), Fraction(0))
        # Comparison is exact rational arithmetic; display retains an exact
        # rational if a caller's Decimal precision cannot represent the sum.
        display = Decimal(total.numerator) / Decimal(total.denominator)
        result.update(source_volume=str(numbers[0]), minute_sum=str(display) if Fraction(display) == total else str(total),
                      status="MATCH" if Fraction(numbers[0]) == total else "MISMATCH",
                      code="INTERVAL_VOLUME_MATCH" if Fraction(numbers[0]) == total else "CROSS_INTERVAL_VOLUME_MISMATCH")
    except (KeyError, ValueError, TypeError, ArithmeticError, OverflowError):
        pass
    return result
