"""Deterministic eligibility decisions, with explicit omissions and warnings."""

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Mapping, Sequence

from config import decimal_value
from data.schema import CandleRecord, INTERVAL, SYMBOL, normalize, utc
from data.diagnostics import invalid_volume_reason, zero_volume_diagnostic


@dataclass(frozen=True, slots=True)
class DataPolicy:
    min_history_bars: int = 2880
    min_completeness: Decimal = Decimal("1")
    max_staleness_minutes: int = 30
    max_zero_volume_fraction: Decimal = Decimal("0")
    min_quote_volume_per_bar: Decimal | None = None
    require_verified_liquidity: bool = True

    def __post_init__(self) -> None:
        if type(self.min_history_bars) is not int or self.min_history_bars < 200:
            raise ValueError("min_history_bars must be an integer of at least 200")
        if type(self.max_staleness_minutes) is not int or self.max_staleness_minutes < 0:
            raise ValueError("max_staleness_minutes must be a nonnegative integer")
        for name in ("min_completeness", "max_zero_volume_fraction", "min_quote_volume_per_bar"):
            raw = getattr(self, name)
            if name == "min_quote_volume_per_bar" and raw is None:
                continue
            object.__setattr__(self, name, decimal_value(raw, name))
        if not 0 < self.min_completeness <= 1:
            raise ValueError("min_completeness must be in (0, 1]")
        if not 0 <= self.max_zero_volume_fraction < 1:
            raise ValueError("max_zero_volume_fraction must be in [0, 1)")
        if self.min_quote_volume_per_bar is not None and self.min_quote_volume_per_bar <= 0:
            raise ValueError("min_quote_volume_per_bar must be positive when set")
        if type(self.require_verified_liquidity) is not bool:
            raise ValueError("require_verified_liquidity must be a boolean")


@dataclass(frozen=True, slots=True)
class QualityIssue:
    code: str
    row: int | None
    detail: str


@dataclass(frozen=True, slots=True)
class Assessment:
    report: dict
    completed: tuple[CandleRecord, ...]


def assess(rows: Sequence[Mapping[str, object]], metadata: Mapping[str, object],
           policy: DataPolicy, as_of: datetime) -> Assessment:
    as_of = utc(as_of)
    symbol = metadata.get("symbol", "")
    issues: list[QualityIssue] = []
    warnings: list[str] = []
    reasons: list[str] = []
    parsed: list[CandleRecord] = []
    completed: list[CandleRecord] = []
    volume_diagnostics: list[dict] = []
    invalid_rows = 0
    # Normalized exports can omit rejected source rows. Reassessing those rows
    # must not erase the original decision; repair/reassess the archived source.
    if metadata.get("schema_version") == 2 and metadata.get("ingestion_eligible") is not True:
        reasons.append("SOURCE_INGESTION_REJECTED")
    if not isinstance(symbol, str) or not SYMBOL.fullmatch(symbol):
        reasons.append("INVALID_SYMBOL")
    if metadata.get("market_status") != "active":
        reasons.append("MARKET_NOT_CONFIRMED_ACTIVE")
    if metadata.get("quote_currency") != "INR":
        reasons.append("UNSUPPORTED_ACCOUNT_CURRENCY")
    if metadata.get("source_order_valid") is False:
        reasons.append("OUT_OF_ORDER")
    for field in ("quote_volume_verified", "source_order_valid"):
        if field in metadata and type(metadata[field]) is not bool:
            raise ValueError(f"{field} must be a boolean")
    source_warnings = metadata.get("ingestion_warnings", [])
    if not isinstance(source_warnings, list) or any(not isinstance(value, str) for value in source_warnings):
        raise ValueError("ingestion_warnings must be an array of strings")
    warnings.extend(source_warnings)
    if any(code in source_warnings for code in ("CROSS_INTERVAL_VOLUME_MISMATCH", "CROSS_INTERVAL_CANDLE_MISMATCH")):
        reasons.append("SOURCE_INTERVAL_MISMATCH")
    if metadata.get("kind") == "synthetic":
        warnings.append("SYNTHETIC_DATA_NOT_MARKET_EVIDENCE")
    for index, row in enumerate(rows, 1):
        try:
            record = normalize(row, symbol, metadata.get("timeframe", "15m"))
        except (ValueError, TypeError, OverflowError) as exc:
            invalid_rows += 1
            issues.append(QualityIssue("INVALID_RECORD", index, str(exc)))
            volume_reason = invalid_volume_reason(row)
            if volume_reason is not None:
                volume_diagnostics.append({"row": index, "timestamp": None, "code": volume_reason,
                                           "structurally_valid": False, "disposition": "REJECTED_INVALID_RECORD"})
            continue
        parsed.append(record)
        if record.timestamp > as_of:
            issues.append(QualityIssue("FUTURE_CANDLE", index, record.timestamp.isoformat()))
        elif record.closed_at > as_of:
            issues.append(QualityIssue("INCOMPLETE_CANDLE", index, record.timestamp.isoformat()))
        else:
            completed.append(record)
            diagnostic = zero_volume_diagnostic(record, index)
            if diagnostic is not None:
                volume_diagnostics.append(diagnostic)
    times = [record.timestamp for record in parsed]
    duplicates = len(times) - len(set(times))
    out_of_order = any(right < left for left, right in zip(times, times[1:]))
    if invalid_rows:
        reasons.append("INVALID_DATA")
    if duplicates:
        reasons.append("DUPLICATE_TIMESTAMPS")
    if out_of_order:
        if "OUT_OF_ORDER" not in reasons:
            reasons.append("OUT_OF_ORDER")
    if any(issue.code == "FUTURE_CANDLE" for issue in issues):
        reasons.append("FUTURE_DATA")
    if any(issue.code == "INCOMPLETE_CANDLE" for issue in issues):
        warnings.append("INCOMPLETE_CANDLES_EXCLUDED")
    unique = sorted({record.timestamp for record in completed})
    start = utc(metadata["requested_start"]) if metadata.get("requested_start") else (unique[0] if unique else None)
    end = utc(metadata["requested_end"]) if metadata.get("requested_end") else (unique[-1] + INTERVAL if unique else None)
    if not metadata.get("requested_start") or not metadata.get("requested_end"):
        warnings.append("COVERAGE_EDGES_NOT_SPECIFIED")
    if end:
        end = min(end, as_of)
        end = end.replace(minute=(end.minute // 15) * 15, second=0, microsecond=0)
    expected = max(0, (end - start) // INTERVAL) if start and end else 0
    inside = [time for time in unique if start <= time < end] if start and end else []
    if len(inside) != len(unique):
        reasons.append("OUTSIDE_REQUESTED_RANGE")
    missing = max(0, expected - len(inside))
    completeness = Decimal(len(inside)) / expected if expected else Decimal("0")
    if len(inside) < policy.min_history_bars:
        reasons.append("INSUFFICIENT_HISTORY")
    if completeness < policy.min_completeness:
        reasons.append("INCOMPLETE_HISTORY")
    if missing:
        warnings.append("MISSING_INTERVALS_NOT_FILLED")
    zero = sum(record.volume == 0 for record in completed)
    zero_fraction = Decimal(zero) / len(completed) if completed else Decimal("0")
    if zero_fraction > policy.max_zero_volume_fraction:
        reasons.append("ZERO_VOLUME")
    if not unique or as_of - (unique[-1] + INTERVAL) > timedelta(minutes=policy.max_staleness_minutes):
        reasons.append("STALE_DATA")
    reliable = metadata.get("quote_volume_verified") is True and all(
        record.quote_volume is not None for record in completed) and bool(completed)
    liquidity = "NOT_ASSESSED"
    if policy.min_quote_volume_per_bar is not None and reliable:
        liquidity = "BELOW_CONFIGURED_THRESHOLD" if any(
            record.quote_volume < policy.min_quote_volume_per_bar for record in completed) else "MEETS_CONFIGURED_THRESHOLD"
        if liquidity == "BELOW_CONFIGURED_THRESHOLD":
            reasons.append("ILLIQUID")
    else:
        warnings.append("QUOTE_LIQUIDITY_NOT_VERIFIED")
        if policy.require_verified_liquidity:
            reasons.append("LIQUIDITY_REVIEW_REQUIRED")
    priority = ("SOURCE_INGESTION_REJECTED", "SOURCE_INTERVAL_MISMATCH", "INVALID_SYMBOL", "MARKET_NOT_CONFIRMED_ACTIVE", "INVALID_DATA",
                "DUPLICATE_TIMESTAMPS", "OUT_OF_ORDER", "FUTURE_DATA", "INSUFFICIENT_HISTORY",
                "INCOMPLETE_HISTORY", "OUTSIDE_REQUESTED_RANGE", "ZERO_VOLUME", "ILLIQUID",
                "STALE_DATA", "UNSUPPORTED_ACCOUNT_CURRENCY", "LIQUIDITY_REVIEW_REQUIRED")
    status = next((reason for reason in priority if reason in reasons), "ELIGIBLE")
    report = {
        "symbol": symbol, "timeframe": metadata.get("timeframe"), "quote_currency": metadata.get("quote_currency"),
        "data_kind": metadata.get("kind"), "as_of": as_of.isoformat(), "status": status,
        "eligible": not reasons, "reasons": reasons, "warnings": warnings,
        "input_rows": len(rows), "invalid_rows": invalid_rows, "completed_rows": len(completed),
        "excluded_rows": [asdict(issue) for issue in issues], "duplicate_timestamps": duplicates,
        "out_of_order": out_of_order, "expected_bars": expected, "missing_bars": missing,
        "completeness": str(completeness), "zero_volume_bars": zero,
        "liquidity": liquidity, "policy": asdict(policy), "live_trading_enabled": False,
        "volume_diagnostics": volume_diagnostics,
        "eligibility_scope": "DATA_POLICY_SCREEN_NOT_ENTRY_APPROVAL",
    }
    return Assessment(report, tuple(completed))
