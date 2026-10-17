"""Offline stored-data/strategy preflight; no backtest, repair, tuning or orders.

Phase 8E archives are inspected as recorded, never refreshed or re-attested.
The existing eligibility loader decides whether evaluation may be considered.
All performance fields remain unavailable when no experiment was executed.
"""

import argparse
import hashlib
import io
import json
import platform
import sqlite3
from contextlib import redirect_stdout
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from backtesting.datasets import BacktestBlocked, load_eligible
from config import Settings
from data.schema import INTERVAL, normalize, utc
from data.storage import read_csv
from strategies import create_strategy
from tools.phase8b_history import save
from tools.phase8e_trace import inspect_history, replay


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(source, trace, rules, output):
    frozen = json.loads(rules.read_text())
    for name, expected in frozen["source_sha256"].items():
        require(digest(Path(name)) == expected, "RULE_OR_IMPLEMENTATION_CHANGED_AFTER_RECORDING: " + name)
    parent = json.loads(Path("docs/examples/phase8e-evidence.json").read_text())
    require(digest(source / "evidence.json") == parent["history_capture_sha256"], "HISTORY_PARENT_HASH_CHANGED")
    require(digest(trace / "evidence.json") == parent["eth_trace_sha256"], "ETH_PARENT_HASH_CHANGED")
    with redirect_stdout(io.StringIO()) as buffer:
        replay(trace)
    replay_result = json.loads(buffer.getvalue())
    trace_evidence = json.loads((trace / "evidence.json").read_text())
    comparison = trace_evidence["trace"]["exact_interval"]
    mismatch = comparison["code"] if comparison["status"] == "MISMATCH" else None
    reviews = inspect_history(source, mismatch)
    archive = json.loads((source / "evidence.json").read_text())
    settings = Settings(**frozen["settings"])
    plan = archive["predeclared_split_plan"]
    bounds = [utc(plan[name]) for name in ("warmup_start", "train_start", "validation_start", "test_start", "test_end_exclusive")]
    names = ("warmup", "train", "validation", "test")
    output.mkdir(parents=True, exist_ok=False)
    results, preflight = [], []
    for row in archive["markets"]:
        pair = row["market"]["pair"]
        imported = read_csv(source / row["csv"])
        raw_path = (source / imported.metadata["raw_file"]).resolve()
        require(raw_path.is_relative_to(source.resolve()), "RAW_ARCHIVE_PATH_OUTSIDE_SOURCE")
        require(digest(raw_path) == imported.metadata["raw_sha256"] == row["raw_archive_sha256"], "RAW_ARCHIVE_HASH_CHANGED")
        records = [normalize(record, pair) for record in imported.rows]
        review = next(item for item in reviews if item["pair"] == pair)
        periods = []
        for name, start, end in zip(names, bounds, bounds[1:]):
            selected = [record for record in records if start <= record.timestamp < end]
            periods.append({"name": name, "start_utc": start, "end_exclusive_utc": end,
                            "observed_bars": len(selected), "expected_bars": (end - start) // INTERVAL,
                            "zero_volume_bars": sum(record.volume == 0 for record in selected),
                            "positive_volume_shape_only": sum(record.volume > 0 for record in selected),
                            "eligible_strategy_bars": 0 if not review["quality"]["eligible"] else None,
                            "strategy_evaluated": False})
        results.append({"pair": pair, "source": row["source"], "kind": row["kind"], "timeframe": "15m",
                        "csv": str(source / row["csv"]), "csv_sha256": row["csv_sha256"],
                        "raw_archive_sha256": row["raw_archive_sha256"],
                        "raw_page_sha256": row["history_pages_sha256"],
                        "record_count": len(records), "first_open_utc": records[0].timestamp if records else None,
                        "last_open_utc": records[-1].timestamp if records else None,
                        "last_close_utc": records[-1].closed_at if records else None,
                        "stored_quote_volumes_available": sum(record.quote_volume is not None for record in records),
                        "metadata_quality_reviewed": imported.metadata.get("quality_reviewed"),
                        "metadata_ingestion_eligible": imported.metadata.get("ingestion_eligible"),
                        "period_quality_counts_not_performance": periods,
                        "eligibility_review": review, "captured_public_instrument": row["public_instrument"],
                        "captured_price_observation": row["price_observation"],
                        "hypothetical_size_not_historical_fill": row["hypothetical_size"]})
        for name, parameters in frozen["strategies"].items():
            strategy = create_strategy(name, **parameters)
            selected_settings = replace(settings, strategy=name)
            try:
                load_eligible(source / row["csv"], selected_settings, as_of=utc(archive["requested_end_exclusive"]))
            except BacktestBlocked as exc:
                status, reason = "BLOCKED", str(exc)
            else:
                status, reason = "ELIGIBILITY_PASSED_NO_EXPERIMENT_STARTED", "Full execution/feasibility review still required"
            preflight.append({"symbol": pair, "strategy": name, "parameters": parameters,
                              "indicator_minimum_bars": strategy.minimum_bars,
                              "engine_minimum_history": max(settings.min_history_bars, strategy.minimum_bars),
                              "status": status, "reason": reason,
                              "strategy_signals_generated": False, "backtest_executed": False,
                              "performance": {key: None for key in ("trade_count", "gross_fill_pnl_before_fees_inr",
                                  "reference_price_pnl_before_costs_inr", "net_pnl_inr", "win_rate_percent",
                                  "expectancy_inr", "profit_factor", "max_drawdown_inr", "max_drawdown_percent",
                                  "exposure_bar_fraction", "fees_inr", "slippage_inr", "benchmark_comparison")}})
    result = {"phase": "8F", "label": "ACTUAL_STORED_DATA_PREFLIGHT_NOT_MARKET_PERFORMANCE",
              "status": "BLOCKED" if all(row["status"] == "BLOCKED" for row in preflight) else "REVIEW_REQUIRED",
              "audited_at_utc": datetime.now(timezone.utc), "rules_recorded_at_utc": frozen["recorded_at_utc"],
              "rules_path": str(rules), "rules_sha256": digest(rules), "frozen_implementation": frozen,
              "source_history_capture": archive["captured_at_utc"], "source_history_archive": str(source),
              "source_history_sha256": digest(source / "evidence.json"),
              "eth_trace_archive": str(trace), "eth_trace_sha256": digest(trace / "evidence.json"),
              "eth_interval_consistency": trace_evidence["trace"], "offline_replay": replay_result,
              "data": results, "strategy_preflight": preflight,
              "methodology": {"existing_split_plan": plan, "funding": "UNMODELED_NO_SUPPORTED_DERIVATIVES_PRODUCT",
                  "baseline_fee_rate_each_side": settings.fee_rate, "baseline_slippage_each_side": settings.slippage_rate,
                  "cost_stress_multiplier": "2", "cost_sensitivity_performance": None,
                  "parameter_sensitivity_candidates": [], "robustness_performance": None,
                  "parameters_selected": False, "out_of_sample_evaluated": False},
              "environment": {"platform": platform.platform(), "python": platform.python_version(), "sqlite": sqlite3.sqlite_version},
              "network_requests": 0, "private_requests": 0, "orders_submitted": 0, "backtests_run": 0,
              "live_trading_enabled": False, "limitations": [
                  "Zero gaps or duplicates do not qualify source activity, quote liquidity or an executable market.",
                  "Positive-volume counts describe Candle shape only, not eligible observations or signals.",
                  "No period was repaired, sliced to remove zeros, tuned, or evaluated for returns.",
                  "Recorded public minimums/prices are snapshot observations, not verified historical execution constraints.",
                  "Unavailable performance is null, not a zero-trade strategy result or preserved final equity."]}
    save(output / "evidence.json", result)
    print(json.dumps({"status": result["status"], "datasets": len(results), "verified_records": replay_result["exact_raw_normalized_matches"],
                      "strategy_preflight_blocks": sum(row["status"] == "BLOCKED" for row in preflight),
                      "backtests_run": 0, "orders_submitted": 0, "network_requests": 0}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("reports/phase8e-history"))
    parser.add_argument("--trace", type=Path, default=Path("reports/phase8e-trace"))
    parser.add_argument("--rules", type=Path, default=Path("docs/examples/phase8f-rules.json"))
    parser.add_argument("--output", type=Path, required=True, help="NEW evidence directory; no existing files overwritten")
    args = parser.parse_args()
    run(args.source, args.trace, args.rules, args.output)


if __name__ == "__main__":
    main()
