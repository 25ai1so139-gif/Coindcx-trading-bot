"""Read-only cross-interval diagnosis; never resample strategy/execution data."""

from collections.abc import Mapping, Sequence
from decimal import Context, Decimal, localcontext
from fractions import Fraction

from data.diagnostics import invalid_volume_reason
from data.schema import SYMBOL, epoch_ms, milliseconds, utc


class InvalidInterval(ValueError):
    pass


def _number(value):
    try:
        number = Decimal(str(value))
        if (not number.is_finite() or len(number.as_tuple().digits) > 32
                or abs(number.as_tuple().exponent) > 32):
            raise ValueError
        return number
    except (ValueError, TypeError, ArithmeticError):
        raise InvalidInterval("INVALID_INTERVAL_NUMBER") from None


def _record(row, interval_ms):
    if not isinstance(row, Mapping):
        raise InvalidInterval("INVALID_INTERVAL_RECORD")
    stamp = epoch_ms(milliseconds(row["time"]))
    if stamp % interval_ms:
        raise InvalidInterval("MISALIGNED_INTERVAL_TIMESTAMP")
    if invalid_volume_reason(row) is not None:
        raise InvalidInterval("INVALID_INTERVAL_VOLUME")
    values = {key: _number(row[key]) for key in ("open", "high", "low", "close", "volume")}
    if (any(values[key] <= 0 for key in ("open", "high", "low", "close"))
            or not values["low"] <= min(values["open"], values["close"])
            <= max(values["open"], values["close"]) <= values["high"]):
        raise InvalidInterval("INVALID_INTERVAL_OHLC")
    return stamp, values


def _text(value):
    if isinstance(value, Fraction):
        # Inputs are bounded decimals; 100 digits represents their 15-term sum
        # exactly and makes diagnostic output independent of caller precision.
        with localcontext(Context(prec=100)):
            return str(Decimal(value.numerator) / Decimal(value.denominator))
    return str(value)


def interval_candle_check(bar, minutes, *, pair, minute_pair, as_of):
    """Compare one raw 15m candle with exactly its 15 closed raw 1m candles.

    Caller binds each source pair to its request/manifest. Outside-window context
    is excluded; duplicates, gaps, bad prices/volumes and incomplete intervals
    cannot produce MATCH. Derived numbers are diagnostics, never replacement bars
    or independent proof of trades/liquidity. No policy is relaxed on a match.
    """
    result = {"scope": "DIAGNOSTIC_ONLY_NOT_STRATEGY_DATA_OR_ENTRY_APPROVAL",
              "status": "UNVERIFIED", "code": "INVALID_INTERVAL_EVIDENCE",
              "minute_count": 0, "source_open_utc": None, "source_close_utc": None,
              "source_values": None, "minute_derived_values": None, "mismatched_fields": [],
              "source_activity_verified": False, "liquidity_verified": False}
    try:
        if (not isinstance(pair, str) or not SYMBOL.fullmatch(pair) or pair != minute_pair):
            raise InvalidInterval("INTERVAL_SYMBOL_MISMATCH")
        cutoff = utc(as_of)
        stamp, original = _record(bar, 900000)
        closing = milliseconds(stamp + 900000)
        result.update(source_open_utc=milliseconds(stamp).isoformat(), source_close_utc=closing.isoformat())
        if closing > cutoff:
            raise InvalidInterval("INCOMPLETE_OR_FUTURE_INTERVAL")
        if not isinstance(minutes, Sequence) or isinstance(minutes, (str, bytes)):
            raise InvalidInterval("INVALID_MINUTE_SEQUENCE")
        selected = []
        for row in minutes:
            if not isinstance(row, Mapping):
                raise InvalidInterval("INVALID_INTERVAL_RECORD")
            time = epoch_ms(milliseconds(row["time"]))
            if stamp <= time < stamp + 900000:
                selected.append(_record(row, 60000))
        result["minute_count"] = len(selected)
        times = [time for time, _ in selected]
        if len(times) != len(set(times)):
            raise InvalidInterval("DUPLICATE_MINUTE_TIMESTAMP")
        if set(times) != {stamp + index * 60000 for index in range(15)}:
            raise InvalidInterval("MISSING_MINUTE_INTERVALS")
        # Raw API is descending; explicit ascending diagnostic inputs are also
        # accepted, but scrambled ordering is not silently hidden by sorting.
        if times != sorted(times) and times != sorted(times, reverse=True):
            raise InvalidInterval("OUT_OF_ORDER_MINUTES")
        ordered = sorted(selected)
        derived = {"open": ordered[0][1]["open"], "high": max(row["high"] for _, row in ordered),
                   "low": min(row["low"] for _, row in ordered), "close": ordered[-1][1]["close"],
                   "volume": sum((Fraction(row["volume"]) for _, row in ordered), Fraction(0))}
        differences = [key for key in original if Fraction(original[key]) != Fraction(derived[key])]
        code = ("CROSS_INTERVAL_VOLUME_MISMATCH" if differences == ["volume"] else
                "CROSS_INTERVAL_CANDLE_MISMATCH" if differences else "INTERVAL_CANDLE_MATCH")
        result.update(status="MISMATCH" if differences else "MATCH", code=code,
                      source_values={key: _text(value) for key, value in original.items()},
                      minute_derived_values={key: _text(value) for key, value in derived.items()},
                      mismatched_fields=differences)
    except InvalidInterval as exc:
        result["code"] = str(exc)
    except (KeyError, ValueError, TypeError, ArithmeticError, OverflowError):
        pass
    return result
