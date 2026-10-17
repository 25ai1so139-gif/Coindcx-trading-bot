"""Bounded public-history evidence capture; never qualifies liquidity or trades.

Fixed sample chosen before fetching: BTC, ETH, SOL and DOGE, INR only. Reuses
the production discovery, normalization, strict quality and immutable CSV export.
Public responses are genuine; no synthetic candles, interpolation or backtest.
"""

import argparse
import hashlib
import json
import platform
import sqlite3
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from config import Settings
from data.cache import ResponseCache
from data.coindcx import PublicClient, PublicDataError, ROUTES, unsigned_get
from data.quality import DataPolicy, assess
from data.schema import INTERVAL, utc
from data.storage import write_dataset
from exchange.contracts import ExchangeBlocked
from exchange.instruments import discover_instrument

ASSETS = ("BTC", "ETH", "SOL", "DOGE")


def save(path, value):
    path.write_text(json.dumps(value, indent=2, default=str) + "\n", encoding="utf-8")


def run(output, end=None):
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    began, as_of = time.monotonic(), datetime.now(timezone.utc)
    end = utc(end) if end else as_of.replace(minute=as_of.minute // 15 * 15, second=0, microsecond=0)
    if end > as_of or end.minute % 15 or end.second or end.microsecond:
        raise ValueError("end must be an already completed 15m UTC boundary")
    settings = Settings()
    start = end - INTERVAL * (settings.min_history_bars + 2)
    manifest = []

    def transport(url, timeout):
        response = unsigned_get(url, timeout)
        name = f"public-{len(manifest) + 1:04d}.json"
        (output / name).write_bytes(response.body)
        manifest.append({"at": datetime.now(timezone.utc).isoformat(), "method": "GET", "url": url,
                         "http": response.status, "file": name,
                         "sha256": hashlib.sha256(response.body).hexdigest()})
        save(output / "requests.json", manifest)
        return response

    client = PublicClient(ResponseCache(output / "cache"), transport=transport, timeout=5,
                          attempts=2, request_interval=0.5, max_retry_delay=5)
    markets = client.discover()
    selected = []
    for asset in ASSETS:
        choices = [m for m in markets if m.active_confirmed and m.quote_currency == "INR" and m.asset_currency == asset]
        if len(choices) != 1:
            selected.append({"asset": asset, "status": "BLOCKED", "reason": "NO_UNIQUE_CONFIRMED_ACTIVE_INR_PAIR"})
            continue
        market = choices[0]
        row = {"asset": asset, "market": asdict(market), "kind": "historical",
               "source": ROUTES["candles"], "historical_listing_identity_verified": False}
        try:
            history = client.history(market.pair, start, end, max_pages=4)
            metadata = {"symbol": market.pair, "timeframe": "15m", "quote_currency": "INR",
                        "kind": "historical", "source": ROUTES["candles"], "market_status": market.status,
                        "source_order_valid": history.source_order_valid, "ingestion_warnings": list(history.warnings),
                        "requested_start": start.isoformat(), "requested_end": end.isoformat(),
                        "quote_volume_verified": False, "quality_reviewed": False}
            assessment = assess(history.rows, metadata, DataPolicy(), end)
            path = output / (market.pair + ".csv")
            original = json.dumps({"pages_utf8": [raw.decode("utf-8") for raw in history.raw_pages]}, sort_keys=True).encode()
            write_dataset(path, assessment, metadata, original, "json")
            row.update(status="PASS" if assessment.report["eligible"] else "BLOCKED", quality=assessment.report,
                       csv=path.name, csv_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                       first_returned_open=history.rows[0]["timestamp"] if history.rows else None,
                       last_returned_open=history.rows[-1]["timestamp"] if history.rows else None,
                       symbol_bound_by="exact public pair query and current active discovery; no per-candle identity field",
                       history_pages_sha256=[hashlib.sha256(raw).hexdigest() for raw in history.raw_pages])
            try:
                row["public_instrument"] = asdict(discover_instrument(client, market.pair))
            except (ExchangeBlocked, PublicDataError) as exc:
                row["instrument_status"] = exc.code if isinstance(exc, PublicDataError) else str(exc)
        except PublicDataError as exc:
            row.update(status="BLOCKED", reason=exc.code, http_status=exc.status)
        selected.append(row)
        save(output / "markets.json", selected)
        print(json.dumps({"asset": asset, "pair": market.pair, "status": row["status"],
                          "reasons": row.get("quality", {}).get("reasons", [row.get("reason")]),
                          "rows": row.get("quality", {}).get("input_rows")}), flush=True)
    result = {"phase": "8B", "label": "ACTUAL_PUBLIC_COINDCX_HISTORY_NOT_QUALIFIED_MARKET_PERFORMANCE",
              "captured_at": as_of.isoformat(), "historical_quality_cutoff": end.isoformat(),
              "requested_start": start.isoformat(), "requested_end": end.isoformat(),
              "actual_seconds": time.monotonic() - began, "fixed_assets_before_fetch": ASSETS,
              "environment": {"system": platform.system(), "python": platform.python_version(), "sqlite": sqlite3.sqlite_version},
              "markets": selected, "request_manifest": manifest, "private_requests": 0, "orders_submitted": 0,
              "live_trading_enabled": False, "backtests_run": 0, "out_of_sample_tests_run": 0,
              "limitations": ["Fixed four-asset INR sample, not an exhaustive exchange or listing-history survey.",
                              "Current active status does not authenticate historical listing identity or avoid survivorship bias.",
                              "Asset volume is not verified quote liquidity; no threshold or verification flag is invented.",
                              "No real-data performance is calculated; CSVs keep original rejection and raw provenance.",
                              "A 30-day warmup window alone cannot supply three 30-day evaluation periods."]}
    save(output / "evidence.json", result)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="NEW directory, normally under ignored reports/")
    parser.add_argument("--end", type=utc, help="optional explicit historical end, exclusive; defaults to latest completed boundary")
    args = parser.parse_args()
    return run(args.output, args.end)


if __name__ == "__main__":
    raise SystemExit(main())
