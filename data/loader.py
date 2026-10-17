"""Reject incomplete, unreviewed, mixed-currency, or structurally unreliable data."""

import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

from data.models import Candle


@dataclass(frozen=True, slots=True)
class MarketData:
    symbol: str
    quote_currency: str
    kind: str
    source: str
    candles: tuple[Candle, ...]


def load_csv(path: str | Path, min_history_bars: int = 2880,
             allow_synthetic: bool = False) -> MarketData:
    path = Path(path)
    if type(min_history_bars) is not int or min_history_bars < 200:
        raise ValueError("min_history_bars must be an integer of at least 200")
    # Sidecar provenance is an operator review, not independent provider verification.
    metadata = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
    if not isinstance(metadata, dict):
        raise ValueError("dataset metadata must be a JSON object")
    symbol = metadata.get("symbol")
    if not isinstance(symbol, str) or not symbol.strip():
        raise ValueError("dataset must specify a market symbol")
    if metadata.get("quote_currency") != "INR":
        raise ValueError("dataset prices must be INR; USDT is not interchangeable with INR")
    if metadata.get("timeframe") != "15m":
        raise ValueError("dataset timeframe must be 15m")
    kind = metadata.get("kind")
    source = metadata.get("source")
    if not isinstance(source, str) or not source:
        raise ValueError("dataset source is required")
    if kind == "synthetic":
        if not allow_synthetic:
            raise ValueError("synthetic data requires --allow-synthetic and is for smoke checks only")
    elif kind == "historical":
        origin = urlparse(source)
        if origin.scheme != "https" or not origin.hostname or origin.username or origin.password:
            raise ValueError("historical source must be a public HTTPS provenance URL without credentials")
        if metadata.get("quality_reviewed") is not True:
            raise ValueError("historical data needs an explicit quality review before use")
    else:
        raise ValueError("dataset kind must be historical or synthetic")
    if hashlib.sha256(path.read_bytes()).hexdigest() != metadata.get("sha256"):
        raise ValueError("dataset SHA-256 does not match reviewed metadata")
    version_two = metadata.get("schema_version") == 2
    if version_two and metadata.get("ingestion_eligible") is not True:
        raise ValueError("dataset failed ingestion eligibility; repair the source and re-import it")
    candles: list[Candle] = []
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        expected = {"timestamp", "open", "high", "low", "close", "volume"}
        actual = set(reader.fieldnames or [])
        extended = expected | {"symbol", "timeframe"}
        valid_header = (actual in (extended, extended | {"quote_volume"}) if version_two else actual == expected)
        if reader.fieldnames is None or not valid_header or len(actual) != len(reader.fieldnames):
            columns = "timestamp,open,high,low,close,volume"
            if version_two:
                columns += ",symbol,timeframe with optional quote_volume"
            raise ValueError(f"CSV requires exactly {columns}")
        for line, row in enumerate(reader, 2):
            try:
                if None in row or any(value is None for value in row.values()):
                    raise ValueError("incorrect column count")
                if version_two and (row["symbol"] != metadata["symbol"] or row["timeframe"] != "15m"):
                    raise ValueError("mixed symbol or timeframe")
                candle = Candle(datetime.fromisoformat(row["timestamp"]),
                                **{key: row[key] for key in expected - {"timestamp"}})
                if candle.closed_at > datetime.now(timezone.utc):
                    raise ValueError("only completed historical candles are accepted")
                if candles and candle.timestamp - candles[-1].timestamp != timedelta(minutes=15):
                    raise ValueError("timestamps must be sorted, unique, and gap-free at 15m")
                candles.append(candle)
            except (ValueError, TypeError) as exc:
                raise ValueError(f"CSV line {line}: {exc}") from exc
    if len(candles) < min_history_bars:
        raise ValueError(f"insufficient history: {len(candles)} bars; need {min_history_bars}")
    if version_two:
        from data.quality import DataPolicy
        from data.storage import inspect_csv
        try:
            policy = DataPolicy(**metadata.get("data_policy", {}))
        except TypeError as exc:
            raise ValueError("invalid dataset data_policy") from exc
        result = inspect_csv(path, policy, candles[-1].closed_at)
        if not result.report["eligible"]:
            raise ValueError("dataset quality recheck failed: " + ", ".join(result.report["reasons"]))
    return MarketData(symbol.strip(), "INR", kind, source, tuple(candles))
