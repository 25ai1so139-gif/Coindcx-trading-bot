"""Public, bounded diagnosis of archived zero-volume candles; no trading.

Compares exact archived bytes/CSV, direct 15m requests at different limits and
documented 1m data. Minute responses are diagnostic evidence, never strategy input.
"""

import argparse
import hashlib
import json
import time
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from data.cache import ResponseCache
from data.coindcx import PublicClient, PublicDataError, ROUTES, unsigned_get
from data.diagnostics import interval_volume_check
from data.schema import epoch_ms, milliseconds, normalize, utc
from data.storage import read_csv
from exchange.contracts import ExchangeBlocked
from exchange.instruments import discover_instrument


def save(path, value):
    path.write_text(json.dumps(value, indent=2, default=str) + "\n", encoding="utf-8")


def run(source, output):
    output.mkdir(parents=True, exist_ok=False)
    began = time.monotonic()
    previous = json.loads((source / "evidence.json").read_text())
    requests, results = [], []

    def transport(url, timeout):
        response = unsigned_get(url, timeout)
        name = f"public-{len(requests) + 1:04d}.json"
        (output / name).write_bytes(response.body)
        requests.append({"at": datetime.now(timezone.utc).isoformat(), "url": url, "method": "GET",
                         "http": response.status, "file": name,
                         "sha256": hashlib.sha256(response.body).hexdigest()})
        save(output / "requests.json", requests)
        return response

    client = PublicClient(ResponseCache(output / "cache"), transport=transport, timeout=5,
                          attempts=2, request_interval=0.5, max_retry_delay=5)
    active = client.discover()
    for market in previous["markets"]:
        pair = market["market"]["pair"]
        raw = []
        for item in previous["request_manifest"]:
            if "/candles?" not in item["url"] or "pair=" + pair not in item["url"]:
                continue
            body = (source / item["file"]).read_bytes()
            if hashlib.sha256(body).hexdigest() != item["sha256"]:
                raise ValueError("archived public response checksum mismatch")
            raw.extend(PublicClient._decode(body))
        imported = read_csv(source / market["csv"])
        normalized = {epoch_ms(utc(row["timestamp"])): row for row in imported.rows}
        equal = len(raw) == len(normalized)
        zeros = []
        for item in raw:
            record = normalize({"timestamp": milliseconds(item["time"]),
                               **{k: item[k] for k in ("open", "high", "low", "close", "volume")}}, pair)
            stored = normalized[item["time"]]
            equal &= all(Decimal(stored[k]) == getattr(record, k) for k in ("open", "high", "low", "close", "volume"))
            if record.volume == 0:
                prior = normalized.get(item["time"] - 900000)
                zeros.append({"raw": item, "normalized": stored,
                              "flat": record.open == record.high == record.low == record.close,
                              "equals_previous_close": prior is not None and Decimal(prior["close"]) == record.close})
        result = {"pair": pair, "archived_raw_rows": len(raw), "raw_normalized_equal": equal,
                  "archived_zero_count": len(zeros), "zero_examples": zeros,
                  "current_identity_confirmed": any(m.pair == pair and m.active_confirmed and m.quote_currency == "INR" for m in active),
                  "underlying_no_trade_cause_verified": False}
        if zeros and result["current_identity_confirmed"]:
            sample = max(zeros, key=lambda row: row["raw"]["time"])
            stamp = sample["raw"]["time"]

            def query(interval, start, end, limit):
                def array(value):
                    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
                        raise ValueError("unsupported public candle response")
                    return value
                params = dict(pair=pair, interval=interval, startTime=start, endTime=end, limit=limit)
                rows, _ = client._json("candles", params, array, timedelta(0))
                return {"params": params, "rows": rows}

            try:
                single = query("15m", stamp, stamp + 900000 - 1, 1)
                neighbors = query("15m", stamp - 900000, stamp + 1800000 - 1, 1000)
                minutes = query("1m", stamp - 900000, stamp + 1800000 - 1, 1000)
                inside = [r for r in minutes["rows"] if stamp <= r["time"] < stamp + 900000]
                matching = [r for r in neighbors["rows"] if r["time"] == stamp]
                result.update(sample_timestamp_utc=milliseconds(stamp), direct_single=single,
                              direct_neighbors=neighbors, diagnostic_minutes=minutes,
                              single_matches_archive=single["rows"] == [sample["raw"]],
                              neighbor_sample_matches_archive=matching == [sample["raw"]],
                              minute_sample_count=len(inside),
                              minute_sample_volume_sum=sum((Decimal(str(r["volume"])) for r in inside), Decimal(0)),
                              minute_sample_all_zero=bool(inside) and all(Decimal(str(r["volume"])) == 0 for r in inside))
                result["cross_interval_checks"] = [{"time": r["time"], **interval_volume_check(r, minutes["rows"])}
                                                   for r in neighbors["rows"]]
                result["public_instrument"] = asdict(discover_instrument(client, pair))
            except (PublicDataError, ExchangeBlocked) as exc:
                result["comparison_blocked"] = exc.code if isinstance(exc, PublicDataError) else str(exc)
        results.append(result)
        save(output / "markets.json", results)
        print(json.dumps({k: result.get(k) for k in ("pair", "archived_zero_count", "raw_normalized_equal",
                         "single_matches_archive", "neighbor_sample_matches_archive", "minute_sample_count",
                         "minute_sample_volume_sum", "comparison_blocked")}, default=str), flush=True)
    save(output / "evidence.json", {"phase": "8C", "label": "ACTUAL_PUBLIC_DIAGNOSTICS_NOT_MARKET_PERFORMANCE",
         "captured_at": datetime.now(timezone.utc), "actual_seconds": time.monotonic() - began,
         "source_archive": str(source), "markets": results, "request_manifest": requests,
         "orders_submitted": 0, "private_requests": 0, "live_trading_enabled": False,
         "limits": "Four archived symbols; most recent zero per symbol; 1m comparisons do not certify trade-history completeness."})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("reports/phase8b-history"))
    parser.add_argument("--output", type=Path, required=True, help="NEW ignored evidence directory")
    args = parser.parse_args()
    run(args.source, args.output)


if __name__ == "__main__":
    main()
