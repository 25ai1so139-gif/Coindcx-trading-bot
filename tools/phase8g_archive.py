"""Audit original public ZIP bytes independently; quarantine without repairing.

No network, strategy calculation, broker, backtest or account mutation. Source
math is plain Decimal/Fraction, then compared with the existing production path.
"""

import argparse
import csv
import hashlib
import io
import json
import platform
import sqlite3
import zipfile
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, Context, localcontext
from fractions import Fraction
from pathlib import Path, PurePosixPath
from urllib.parse import parse_qs, urlencode, urlparse

from config import Settings
from data.coindcx import HttpResponse, PublicClient, ROUTES
from data.quality import DataPolicy, assess
from data.schema import normalize
from data.storage import read_csv, write_dataset
from exchange.diagnostics import minimum_order_diagnostic
from exchange.instruments import Instrument
from tools.phase8b_history import save

HISTORY = "reports/phase8e-history/"
TRACE = "reports/phase8e-trace/"
FIELDS = ("open", "high", "low", "close", "volume")
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def sha(body):
    return hashlib.sha256(body).hexdigest()


def decoded(body):
    def invalid(value):
        raise ValueError("NONFINITE_JSON_CONSTANT")
    return json.loads(body, parse_float=Decimal, parse_constant=invalid)


def stamp(milliseconds):
    number = Decimal(str(milliseconds))
    require(number.is_finite() and number == number.to_integral_value(), "INTEGER_MS_REQUIRED")
    return EPOCH + timedelta(milliseconds=int(number))


def numbers(row):
    values = {key: Decimal(str(row[key])) for key in FIELDS}
    require(all(value.is_finite() for value in values.values()), "NONFINITE_OHLCV")
    require(all(values[key] > 0 for key in FIELDS[:-1]) and values["volume"] >= 0, "INVALID_OHLCV_SIGN")
    require(values["low"] <= min(values["open"], values["close"])
            <= max(values["open"], values["close"]) <= values["high"], "INVALID_OHLC_RANGE")
    return values


def decimal_text(value):
    with localcontext(Context(prec=100)):
        return str(Decimal(value.numerator) / Decimal(value.denominator))


def run(archive, output):
    parent = json.loads(Path("docs/examples/phase8f-evidence.json").read_text())
    original = archive.read_bytes()
    require(sha(original) == parent["public_replay_package"]["sha256"], "ORIGINAL_ZIP_HASH_CHANGED")
    frozen = json.loads(Path("docs/examples/phase8f-rules.json").read_text())
    for name, expected in frozen["source_sha256"].items():
        require(sha(Path(name).read_bytes()) == expected, "FROZEN_RULE_CHANGED: " + name)
    output.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(io.BytesIO(original)) as source:
        manifest = decoded(source.read("phase8f-public-input-manifest.json"))
        require(len(manifest) == 85 and len(source.namelist()) == 86, "UNEXPECTED_ARCHIVE_CONTENTS")
        for name, item in manifest.items():
            path = PurePosixPath(name)
            require(not path.is_absolute() and ".." not in path.parts, "UNSAFE_ARCHIVE_PATH")
            body = source.read(name)
            require(len(body) == item["bytes"] and sha(body) == item["sha256"], "ARCHIVE_ENTRY_CHANGED")
        history = decoded(source.read(HISTORY + "evidence.json"))
        trace = decoded(source.read(TRACE + "evidence.json"))
        requests = trace["request_manifest"]

        def query(name):
            item = trace["queries"][name]
            url = ROUTES["candles"] + "?" + urlencode(sorted(item["params"].items()))
            request = next(row for row in requests if row["url"] == url and row["sha256"] == item["sha256"])
            body = source.read(TRACE + request["file"])
            require(sha(body) == request["sha256"] and request["http"] == 200, "QUERY_EVIDENCE_CHANGED")
            return decoded(body)

        raw = query("15m-limit1")[0]
        opened = stamp(raw["time"])
        closing = opened + timedelta(minutes=15)
        context = query("1m-context")
        require(all(left["time"] - right["time"] == 60000 for left, right in zip(context, context[1:])),
                "CONTEXT_NOT_DESCENDING_AND_GAP_FREE")
        minutes = sorted(context, key=lambda row: row["time"])
        selected = [row for row in minutes if raw["time"] <= row["time"] < raw["time"] + 900000]
        times = [row["time"] for row in selected]
        require(len(times) == len(set(times)) == 15
                and set(times) == {raw["time"] + i * 60000 for i in range(15)}, "BAD_TARGET_MINUTE_COVERAGE")
        require(closing <= datetime.fromisoformat(trace["captured_at_utc"]), "INCOMPLETE_SOURCE_INTERVAL")
        direct, minute_values = numbers(raw), [numbers(row) for row in selected]
        total = sum((Fraction(row["volume"]) for row in minute_values), Fraction(0))
        aggregate = {"open": minute_values[0]["open"], "high": max(row["high"] for row in minute_values),
                     "low": min(row["low"] for row in minute_values), "close": minute_values[-1]["close"], "volume": total}
        differences = [key for key in FIELDS if Fraction(direct[key]) != Fraction(aggregate[key])]
        require(query("15m-limit1000") == [raw], "DIRECT_LIMIT_RESPONSES_DIFFER")
        require(sorted(query("1m-exact"), key=lambda row: row["time"]) == selected, "EXACT_CONTEXT_MINUTES_DIFFER")
        shifts = []
        for index in range(len(minutes) - 14):
            rows = minutes[index:index+15]
            if any(right["time"] - left["time"] != 60000 for left, right in zip(rows, rows[1:])):
                continue
            value = sum((Fraction(numbers(row)["volume"]) for row in rows), Fraction(0))
            shifts.append({"offset_minutes": (rows[0]["time"] - raw["time"]) // 60000,
                           "volume_sum": decimal_text(value), "matches_source_volume": value == Fraction(direct["volume"])})

        # Exercise production discovery/parser/time mapping with the original
        # three HTTP responses in memory; no filesystem pointers to loose copies.
        queue = list(requests[:3])
        replayed = []
        def transport(url, timeout):
            request = queue.pop(0)
            require(url == request["url"], "PRODUCTION_REPLAY_REQUEST_CHANGED")
            body = source.read(TRACE + request["file"])
            require(sha(body) == request["sha256"], "PRODUCTION_RAW_HASH_CHANGED")
            replayed.append(url)
            return HttpResponse(request["http"], body, {})
        replay = PublicClient(transport=transport, request_interval=0).history("I-ETH_INR", opened, closing, max_pages=2)
        require(not queue and len(replay.rows) == 1, "PRODUCTION_REPLAY_COUNT_CHANGED")
        require(replay.market.active_confirmed and replay.market.asset_currency == "ETH"
                and replay.market.quote_currency == "INR", "WRONG_ETH_INSTRUMENT_IDENTITY")
        record = normalize(replay.rows[0], "I-ETH_INR")
        require(record.timestamp == opened and all(getattr(record, key) == direct[key] for key in FIELDS),
                "PRODUCTION_NORMALIZATION_MISMATCH")
        trace_result = {"independent_math": "STDLIB_JSON_DECIMAL_AND_EXACT_FRACTION_FROM_ZIP_RAW_BODIES",
             "pair": "I-ETH_INR", "open_time_ms": raw["time"], "open_utc": opened, "close_utc": closing,
             "raw_15m": raw, "production_normalized": record.row(),
             "minute_derived": {key: decimal_text(value) if isinstance(value, Fraction) else str(value) for key, value in aggregate.items()},
             "mismatched_fields": differences, "difference_eth": decimal_text(Fraction(direct["volume"]) - total),
             "source_volume_units": "TARGET_ASSET_ETH_PER_DOCUMENTATION_NO_CLIENT_SCALING",
             "minute_ledger": [{"time_ms": row["time"], "open_utc": stamp(row["time"]), "raw_volume_eth": row["volume"]} for row in selected],
             "aligned_minutes": 15, "duplicate_minutes": 0, "missing_minutes": 0, "incomplete_minutes": 0,
             "sliding_window_checks": shifts, "production_replay_requests": replayed,
             "network_requests": 0, "provider_mechanism_verified": False,
             "classification": "SOURCE_RESPONSE_VOLUME_DIFFERENCE_NO_LOCAL_FIELD_OR_TIME_CONVERSION_DEFECT_PROVEN"}
        save(output / "eth-trace.json", trace_result)

        assessments = []
        for item in history["markets"]:
            pair = item["market"]["pair"]
            csv_body = source.read(HISTORY + item["csv"])
            meta = decoded(source.read(HISTORY + item["csv"].replace(".csv", ".json")))
            require(sha(csv_body) == meta["sha256"] == item["csv_sha256"], "CSV_HASH_CHANGED")
            source_raw = source.read(HISTORY + meta["raw_file"])
            require(sha(source_raw) == meta["raw_sha256"] == item["raw_archive_sha256"], "RAW_PAGE_ARCHIVE_CHANGED")
            rows = list(csv.DictReader(io.StringIO(csv_body.decode("utf-8-sig"))))
            stored = {datetime.fromisoformat(row["timestamp"]): row for row in rows}
            require(len(stored) == len(rows), "DUPLICATE_CSV_TIMESTAMP")
            matched = 0
            for request in history["request_manifest"]:
                url = urlparse(request["url"])
                params = parse_qs(url.query)
                if url.path != "/market_data/candles" or params.get("pair") != [pair]:
                    continue
                require(params.get("interval") == ["15m"] and request["http"] == 200, "WRONG_HISTORY_REQUEST")
                page_body = source.read(HISTORY + request["file"])
                require(sha(page_body) == request["sha256"], "HISTORY_PAGE_CHANGED")
                page = decoded(page_body)
                require(all(left["time"] > right["time"] for left, right in zip(page, page[1:])), "RAW_PAGE_NOT_STRICTLY_DESCENDING")
                for value in page:
                    require(int(params["startTime"][0]) <= value["time"] <= int(params["endTime"][0]), "RAW_PAGE_OUTSIDE_REQUEST_BOUNDS")
                    time = stamp(value["time"])
                    row = stored.get(time)
                    require(row is not None and time.tzinfo is not None and time.minute % 15 == 0
                            and time.second == time.microsecond == 0, "BAD_HISTORY_TIME")
                    raw_values, csv_values = numbers(value), numbers(row)
                    require(raw_values == csv_values and row["symbol"] == pair and row["timeframe"] == "15m", "RAW_CSV_FIELD_MISMATCH")
                    matched += 1
            require(matched == len(rows), "RAW_CSV_COUNT_MISMATCH")
            metadata = {**meta, "ingestion_warnings": list(meta.get("ingestion_warnings", []))}
            if pair == "I-ETH_INR" and differences:
                metadata["ingestion_warnings"].append("CROSS_INTERVAL_VOLUME_MISMATCH" if differences == ["volume"] else "CROSS_INTERVAL_CANDLE_MISMATCH")
                metadata["source_quarantine"] = {"source_zip_sha256": sha(original), "affected_open_time_ms": raw["time"],
                    "reason": "UNRESOLVED_SOURCE_INTERVAL_SEMANTICS", "comparison_file": str(output / "eth-trace.json"),
                    "comparison_path_base": "repository working directory at audit"}
            as_of = datetime.fromisoformat(history["requested_end_exclusive"])
            assessment = assess(rows, metadata, DataPolicy(), as_of)
            instrument = Instrument(**item["public_instrument"])
            sizing = minimum_order_diagnostic(Settings(), instrument, item["price_observation"]["price"])
            result = {"pair": pair, "source": item["source"], "timeframe": "15m", "first_open_utc": min(stored),
                      "end_exclusive_utc": max(stored) + timedelta(minutes=15), "records": matched,
                      "csv_sha256": sha(csv_body), "raw_archive_sha256": sha(source_raw),
                      "eligible_strategy_observations": 0 if not assessment.report["eligible"] else None,
                      "positive_volume_shape_only": sum(row.volume > 0 for row in assessment.completed),
                      "quality": {key: value for key, value in assessment.report.items() if key != "volume_diagnostics"},
                      "quote_volume_observations": sum(row.quote_volume is not None for row in assessment.completed),
                      "archived_instrument_observation": asdict(instrument), "size_diagnostic_not_order": sizing}
            if pair == "I-ETH_INR" and differences:
                target = output / "quarantine" / (pair + ".csv")
                write_dataset(target, assessment, metadata, source_raw, "json")
                require(target.read_bytes() == csv_body, "QUARANTINE_CSV_VALUES_CHANGED")
                imported = read_csv(target)
                check = assess(imported.rows, imported.metadata, DataPolicy(), as_of)
                require(not check.report["eligible"] and "SOURCE_INTERVAL_MISMATCH" in check.report["reasons"], "QUARANTINE_REIMPORT_LOST_REJECTION")
                result["quarantine_copy"] = {"csv": str(target), "csv_byte_identical_to_original": True,
                    "source_raw_byte_identical": sha(source_raw) == imported.metadata["raw_sha256"],
                    "quality_reviewed": imported.metadata["quality_reviewed"], "ingestion_eligible": imported.metadata["ingestion_eligible"],
                    "reimport_reasons": check.report["reasons"]}
            assessments.append(result)
        evidence = {"phase": "8G", "label": "ORIGINAL_ARCHIVE_AUDIT_NO_REPLACEMENT_DATA_OR_MARKET_PERFORMANCE",
                    "audited_at_utc": datetime.now(timezone.utc), "source_zip": str(archive), "source_zip_sha256": sha(original),
                    "verified_source_files": len(manifest), "eth_trace": trace_result, "datasets": assessments,
                    "environment": {"platform": platform.platform(), "python": platform.python_version(), "sqlite": sqlite3.sqlite_version},
                    "network_requests": 0, "private_requests": 0, "orders_submitted": 0, "backtests_run": 0,
                    "performance": None, "live_trading_enabled": False, "status": "BLOCKED"}
        save(output / "evidence.json", evidence)
        print(json.dumps({"status": "BLOCKED", "archive_files_verified": len(manifest),
                          "raw_normalized_matches": sum(row["records"] for row in assessments),
                          "eth_mismatched_fields": differences, "shifted_volume_matches": sum(row["matches_source_volume"] for row in shifts),
                          "network_requests": 0, "orders_submitted": 0, "backtests_run": 0}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=Path("reports/phase8f-replay-inputs.zip"))
    parser.add_argument("--output", type=Path, required=True, help="NEW evidence/quarantine directory")
    args = parser.parse_args()
    run(args.archive, args.output)


if __name__ == "__main__":
    main()
