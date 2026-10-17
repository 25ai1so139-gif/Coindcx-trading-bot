"""All records in this module are synthetic, not historical market observations."""

import csv
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

START = datetime(2024, 1, 1, tzinfo=timezone.utc)
SYMBOL = "I-SYNTHETIC_INR"


def rows(count=200):
    return [{"timestamp": (START + timedelta(minutes=15 * index)).isoformat(),
             "open": "100", "high": "102", "low": "99", "close": "101", "volume": "10",
             "symbol": SYMBOL, "timeframe": "15m", "quote_volume": "1000"}
            for index in range(count)]


def metadata():
    return {"symbol": SYMBOL, "quote_currency": "INR", "timeframe": "15m", "kind": "synthetic",
            "source": "synthetic offline test fixture", "market_status": "active",
            "quote_volume_verified": True, "quality_reviewed": False}


def end(count=200):
    return START + timedelta(minutes=15 * count)


def csv_fixture(path: Path, records=None):
    records = rows() if records is None else records
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows(1)[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)
    meta = metadata()
    meta["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    path.with_suffix(".json").write_text(json.dumps(meta), encoding="utf-8")
