"""Generate clearly labeled synthetic OHLCV data for local smoke checks."""

import argparse
import csv
import hashlib
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path


def generate(path: Path, bars: int = 3072) -> None:
    if bars < 200:
        raise ValueError("generate at least 200 bars")
    sidecar = path.with_suffix(".json")
    if path.exists() or sidecar.exists():
        raise ValueError("refusing to overwrite an existing dataset or sidecar")
    path.parent.mkdir(parents=True, exist_ok=True)
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    previous = 100.0
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])
        for index in range(bars):
            close = 100 + 4 * math.sin(index / 8)
            writer.writerow([(start + timedelta(minutes=15 * index)).isoformat(),
                             f"{previous:.6f}", f"{max(previous, close) + 0.1:.6f}",
                             f"{min(previous, close) - 0.1:.6f}", f"{close:.6f}", "1000"])
            previous = close
    metadata = {
        "symbol": "SYNTHETIC-INR", "quote_currency": "INR", "timeframe": "15m",
        "kind": "synthetic", "source": "generated mathematical waveform; not market data",
        "quality_reviewed": False, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    sidecar.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/local/sample.csv"))
    args = parser.parse_args()
    generate(args.output)
    print(f"Synthetic smoke-check dataset written to {args.output}")
