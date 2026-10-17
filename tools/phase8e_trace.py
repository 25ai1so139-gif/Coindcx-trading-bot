"""Bounded public ETH trace and exact-byte offline replay; never trades or repairs.

Uses the existing Phase 8D-format history capture and unchanged sizing/settings.
Raw response hashes, UTC requests and derived reviews remain separate from the
original CSVs. Replaying uses archived bytes only and cannot open a socket.
"""

import argparse
import hashlib
import json
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from backtesting.costs import CostModel, fixed_decimal
from backtesting.datasets import BacktestBlocked, load_eligible
from config import Settings
from data.cache import ResponseCache
from data.coindcx import PublicClient, unsigned_get
from data.intervals import interval_candle_check
from data.quality import DataPolicy, assess
from data.schema import epoch_ms, normalize, utc
from data.storage import read_csv
from strategies import create_strategy
from strategies.verification import verify_file
from tools.phase8b_history import save

PAIR = "I-ETH_INR"
OPEN = datetime(2026, 10, 13, 23, 30, tzinfo=timezone.utc)


def require(value, reason):
    if not value:
        raise ValueError(reason)


@fixed_decimal
def inspect_history(source, mismatch_code):
    evidence = json.loads((source / "evidence.json").read_text())
    settings = Settings(**evidence["settings"])
    results = []
    for row in evidence["markets"]:
        pair = row["market"]["pair"]
        imported = read_csv(source / row["csv"])
        require(hashlib.sha256(imported.raw).hexdigest() == row["csv_sha256"], "CSV_EVIDENCE_HASH_CHANGED")
        stored = {epoch_ms(utc(item["timestamp"])): item for item in imported.rows}
        require(len(stored) == len(imported.rows), "DUPLICATE_ARCHIVED_CSV_TIMESTAMP")
        matches = 0
        for request in evidence["request_manifest"]:
            parsed = urlparse(request["url"])
            if parsed.path != "/market_data/candles" or parse_qs(parsed.query).get("pair") != [pair]:
                continue
            raw = (source / request["file"]).read_bytes()
            require(hashlib.sha256(raw).hexdigest() == request["sha256"], "RAW_EVIDENCE_HASH_CHANGED")
            for item in PublicClient._decode(raw):
                match = stored.get(item["time"])
                require(match is not None and all(Decimal(match[key]) == Decimal(str(item[key]))
                        for key in ("open", "high", "low", "close", "volume")), "RAW_NORMALIZED_VALUE_MISMATCH")
                matches += 1
        require(matches == len(imported.rows), "RAW_NORMALIZED_COUNT_MISMATCH")
        meta = {**imported.metadata, "ingestion_warnings": list(imported.metadata.get("ingestion_warnings", []))}
        if pair == PAIR and mismatch_code:
            meta["ingestion_warnings"].append(mismatch_code)
        assessment = assess(imported.rows, meta, DataPolicy(), utc(evidence["requested_end_exclusive"]))
        longest = run = 0
        for record in assessment.completed:
            run = run + 1 if record.volume > 0 else 0
            longest = max(longest, run)
        try:
            load_eligible(source / row["csv"], settings, as_of=utc(evidence["requested_end_exclusive"]))
        except BacktestBlocked as exc:
            loader = {"status": "BLOCKED", "reason": str(exc)}
        else:
            loader = {"status": "UNVERIFIED", "reason": "No backtest executed by diagnostic"}
        review = verify_file(source / row["csv"], settings, create_strategy(settings.strategy),
                             as_of=utc(evidence["requested_end_exclusive"]))
        require(review["signal"] == "NO_TRADE" and review["orders_submitted"] == 0, "UNEXPECTED_VERIFICATION_RESULT")
        size = row.get("hypothetical_size", {})
        minimum = size.get("theoretical_minimum")
        minimum_costs = None
        if minimum is not None and size.get("candidate"):
            quantity, entry = Decimal(minimum["quantity"]), Decimal(size["estimated_entry"])
            costs = CostModel.from_settings(settings)
            stop_fill = costs.exit_fill(entry * (1 - settings.stop_loss_fraction))
            entry_fee, exit_fee = costs.fee(quantity, entry), costs.fee(quantity, stop_fill)
            minimum_costs = {"label": "ARITHMETIC_STEPPED_MINIMUM_NOT_VALIDATED_ORDER_OR_RECOMMENDATION",
                 "quantity": quantity, "notional": minimum["notional"], "margin": minimum["margin"],
                 "entry_fee": entry_fee, "exit_fee_at_no_gap_stop": exit_fee,
                 "margin_plus_entry_fee": Decimal(minimum["margin"]) + entry_fee,
                 "planned_stop_risk": quantity * (entry - stop_fill) + entry_fee + exit_fee,
                 "risk_approved": False, "fee_schedule_verified": False}
        report = {key: value for key, value in assessment.report.items() if key != "volume_diagnostics"}
        results.append({"pair": pair, "raw_normalized_exact_matches": matches,
                        "longest_positive_volume_run_bars": longest, "quality": report,
                        "manual_verification": review, "backtest_loader": loader,
                        "minimum_estimated_costs": minimum_costs,
                        "csv_sha256": row["csv_sha256"], "original_artifacts_unchanged": True})
    return results


def analyze(queries, production_row, as_of):
    direct = queries["15m-limit1"]["rows"]
    require(len(direct) == 1, "EXACT_SINGLE_15M_BAR_UNAVAILABLE")
    record = normalize(production_row, PAIR)
    raw = direct[0]
    require(epoch_ms(record.timestamp) == raw["time"] and all(
            getattr(record, key) == Decimal(str(raw[key])) for key in ("open", "high", "low", "close", "volume")),
            "PRODUCTION_NORMALIZATION_DIFFERED_FROM_DIRECT_RESPONSE")
    exact = interval_candle_check(raw, queries["1m-exact"]["rows"], pair=PAIR, minute_pair=PAIR, as_of=as_of)
    context = interval_candle_check(raw, queries["1m-context"]["rows"], pair=PAIR, minute_pair=PAIR, as_of=as_of)
    return {"exact_interval": exact, "context_interval": context,
            "different_15m_limits_equal": queries["15m-limit1000"]["rows"] == direct,
            "production_normalized_record": record.row(),
            "production_path": "direct 15m API -> integer-ms UTC -> unchanged OHLCV -> strict quality/loader; no resampling",
            "neighbor_checks": [interval_candle_check(bar, queries["1m-context"]["rows"],
                 pair=PAIR, minute_pair=PAIR, as_of=as_of) for bar in queries["15m-neighbors"]["rows"]],
            "independent_trade_corroboration": False, "upstream_cause_verified": False}


def run(source, output):
    output.mkdir(parents=True, exist_ok=False)
    began, as_of = time.monotonic(), datetime.now(timezone.utc)
    requests = []
    def transport(url, timeout):
        response = unsigned_get(url, timeout)
        name = f"public-{len(requests)+1:04d}.json"
        (output / name).write_bytes(response.body)
        safe = {key: value for key, value in response.headers.items()
                if key in {"date", "age", "etag", "cache-control", "last-modified"}}
        requests.append({"url": url, "method": "GET", "at_utc": datetime.now(timezone.utc),
                         "file": name, "http": response.status, "sha256": hashlib.sha256(response.body).hexdigest(),
                         "public_cache_headers": safe})
        save(output / "requests.json", requests)
        return response
    client = PublicClient(ResponseCache(output / "cache"), transport=transport, timeout=5,
                          attempts=2, request_interval=.5, max_retry_delay=5)
    history = client.history(PAIR, OPEN, OPEN + timedelta(minutes=15), max_pages=2)
    require(history.market.asset_currency == "ETH" and history.market.quote_currency == "INR", "WRONG_INSTRUMENT")
    require(len(history.rows) == 1, "EXACT_PRODUCTION_HISTORY_UNAVAILABLE")
    stamp = epoch_ms(OPEN)
    queries = {}
    def query(name, interval, start, end, limit):
        def array(value):
            if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
                raise ValueError("candle array required")
            return value
        params = dict(pair=PAIR, interval=interval, startTime=start, endTime=end, limit=limit)
        values, body = client._json("candles", params, array, timedelta(0))
        queries[name] = {"params": params, "rows": values, "sha256": hashlib.sha256(body).hexdigest()}
    query("15m-limit1", "15m", stamp, stamp + 899999, 1)
    query("15m-limit1000", "15m", stamp, stamp + 899999, 1000)
    query("15m-neighbors", "15m", stamp - 900000, stamp + 1799999, 1000)
    query("1m-exact", "1m", stamp, stamp + 899999, 1000)
    query("1m-context", "1m", stamp - 900000, stamp + 1799999, 1000)
    trace = analyze(queries, history.rows[0], as_of)
    mismatch = trace["exact_interval"]["code"] if trace["exact_interval"]["status"] == "MISMATCH" else None
    results = inspect_history(source, mismatch)
    result = {"phase": "8E", "label": "ACTUAL_PUBLIC_SOURCE_DIAGNOSIS_NOT_MARKET_PERFORMANCE",
              "captured_at_utc": as_of, "actual_seconds": time.monotonic() - began,
              "history_archive": str(source), "history_evidence_sha256": hashlib.sha256((source / "evidence.json").read_bytes()).hexdigest(),
              "queries": queries, "request_manifest": requests, "trace": trace, "history_review": results,
              "source_production_row": history.rows[0], "original_artifacts_unchanged": True,
              "private_requests": 0, "orders_submitted": 0, "live_trading_enabled": False, "backtests_run": 0}
    save(output / "evidence.json", result)
    print(json.dumps({"trace": trace, "history_decisions": [{"pair": row["pair"], "reasons": row["quality"]["reasons"]} for row in results]}, default=str))


def replay(output):
    evidence = json.loads((output / "evidence.json").read_text())
    source = Path(evidence["history_archive"])
    require(hashlib.sha256((source / "evidence.json").read_bytes()).hexdigest() == evidence["history_evidence_sha256"], "HISTORY_EVIDENCE_CHANGED")
    queries = {}
    for name, query in evidence["queries"].items():
        captured = next(item for item in evidence["request_manifest"] if item["sha256"] == query["sha256"])
        body = (output / captured["file"]).read_bytes()
        require(hashlib.sha256(body).hexdigest() == query["sha256"], "PUBLIC_RESPONSE_CHANGED")
        queries[name] = {**query, "rows": PublicClient._decode(body)}
    trace = analyze(queries, evidence["source_production_row"], utc(evidence["captured_at_utc"]))
    require(trace == evidence["trace"], "TRACE_REPLAY_DIFFERED")
    mismatch = trace["exact_interval"]["code"] if trace["exact_interval"]["status"] == "MISMATCH" else None
    reviews = inspect_history(source, mismatch)
    # JSON normalizes Decimals and datetimes from the actual capture.
    require(json.loads(json.dumps(reviews, default=str)) == evidence["history_review"], "HISTORY_REPLAY_DIFFERED")
    print(json.dumps({"status": "PASS", "scope": "ARCHIVED_DIAGNOSTICS_NOT_EXECUTION", "network_requests": 0,
                      "exact_raw_normalized_matches": sum(row["raw_normalized_exact_matches"] for row in reviews),
                      "orders_submitted": 0, "trace_code": trace["exact_interval"]["code"]}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", type=Path, default=Path("reports/phase8e-history"))
    parser.add_argument("--output", type=Path, help="NEW ignored capture directory")
    parser.add_argument("--replay", type=Path, help="existing trace directory; offline, no files overwritten")
    args = parser.parse_args()
    if bool(args.output) == bool(args.replay):
        parser.error("provide exactly one of --output or --replay")
    if args.replay:
        replay(args.replay)
    else:
        run(args.history, args.output)


if __name__ == "__main__":
    main()
