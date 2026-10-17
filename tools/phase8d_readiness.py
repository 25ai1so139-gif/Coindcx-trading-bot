"""Bounded genuine-history and hypothetical-size audit; no trading or approval.

Fixed BTC/ETH/SOL/DOGE INR sample and 120-day window, chosen before fetching.
Reuses production normalization, strict quality, immutable CSV and sizing. No
data repair, reviewed-liquidity attestation, account, or backtest is created.
"""

import argparse
import hashlib
import json
import platform
import sqlite3
import time
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backtesting.costs import CostModel, fixed_decimal
from config import Settings
from data.cache import ResponseCache
from data.coindcx import PublicClient, PublicDataError, ROUTES, unsigned_get
from data.quality import DataPolicy, assess
from data.schema import utc
from data.storage import write_dataset
from exchange.contracts import ExchangeBlocked
from exchange.diagnostics import minimum_order_diagnostic
from exchange.instruments import discover_instrument
from tools.phase8b_history import ASSETS, save


@fixed_decimal
def cost_breakdown(settings, diagnostic):
    """Estimated costs at the modeled stop, including both sides; no fill."""
    plan = diagnostic.get("candidate")
    if plan is None:
        return None
    costs = CostModel.from_settings(settings)
    quantity = plan["quantity"]
    stop_fill = costs.exit_fill(plan["stop_price"])
    exit_fee = costs.fee(quantity, stop_fill)
    return {"label": "HYPOTHETICAL_NO_GAP_STOP_NOT_REALIZED_COST",
            "entry_fee": plan["entry_fee"], "exit_fee_at_stop": exit_fee,
            "round_trip_fees_at_stop": plan["entry_fee"] + exit_fee,
            "entry_slippage_cost": quantity * (plan["entry_price"] - diagnostic["reference_price"]),
            "stop_slippage_cost": quantity * (plan["stop_price"] - stop_fill),
            "modeled_stop_fill": stop_fill, "margin_plus_entry_fee": plan["margin"] + plan["entry_fee"],
            "planned_stop_risk": plan["planned_stop_risk"],
            "initial_risk_budget": min(settings.starting_capital * settings.risk_per_trade, settings.max_planned_risk),
            "absolute_risk_ceiling": settings.max_planned_risk,
            "assumptions": costs.assumptions()}


def run(output, end=None):
    as_of, began = datetime.now(timezone.utc), time.monotonic()
    end = utc(end) if end else as_of.replace(minute=as_of.minute // 15 * 15, second=0, microsecond=0)
    if end > as_of or end.minute % 15 or end.second or end.microsecond:
        raise ValueError("end must be an already completed 15m UTC boundary")
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    settings = Settings()  # Deliberately audited defaults, not environment overrides.
    start = end - timedelta(days=120)
    split = {"warmup_start": start, "train_start": start + timedelta(days=30),
             "validation_start": start + timedelta(days=60), "test_start": start + timedelta(days=90),
             "test_end_exclusive": end, "bars_per_period": 2880,
             "parameters_selected": False, "evaluation_executed": False}
    requests, selected = [], []
    save(output / "predeclared-plan.json", {"assets": ASSETS, "settings": asdict(settings),
         "split_plan": split, "created_at": as_of, "eligible_data_required": True})

    def transport(url, timeout):
        response = unsigned_get(url, timeout)
        name = f"public-{len(requests) + 1:04d}.json"
        (output / name).write_bytes(response.body)
        requests.append({"at": datetime.now(timezone.utc), "method": "GET", "url": url,
                         "http": response.status, "file": name,
                         "sha256": hashlib.sha256(response.body).hexdigest()})
        save(output / "requests.json", requests)
        return response

    client = PublicClient(ResponseCache(output / "cache"), transport=transport, timeout=5,
                          attempts=2, request_interval=0.5, max_retry_delay=5)
    discovery_error = None
    try:
        markets = client.discover()
    except PublicDataError as exc:
        markets, discovery_error = (), exc.code
    for asset in ASSETS:
        choices = [m for m in markets if m.active_confirmed and m.quote_currency == "INR" and m.asset_currency == asset]
        row = {"asset": asset, "status": "BLOCKED", "risk_approved": False, "decision": "NO_TRADE"}
        if len(choices) != 1:
            row["reason"] = discovery_error or "NO_UNIQUE_CONFIRMED_ACTIVE_INR_PAIR"
        else:
            market = choices[0]
            row.update(market=asdict(market), source=ROUTES["candles"], kind="historical",
                       historical_listing_identity_verified=False)
            try:
                history = client.history(market.pair, start, end, max_pages=13)
                metadata = {"symbol": market.pair, "timeframe": "15m", "quote_currency": "INR",
                            "kind": "historical", "source": ROUTES["candles"], "market_status": market.status,
                            "source_order_valid": history.source_order_valid,
                            "ingestion_warnings": list(history.warnings),
                            "requested_start": start.isoformat(), "requested_end": end.isoformat(),
                            "quote_volume_verified": False, "quality_reviewed": False}
                assessment = assess(history.rows, metadata, DataPolicy(), end)
                path = output / (market.pair + ".csv")
                original = json.dumps({"pages_utf8": [raw.decode("utf-8") for raw in history.raw_pages]}, sort_keys=True).encode()
                write_dataset(path, assessment, metadata, original, "json")
                row.update(quality=assessment.report, csv=path.name,
                           csv_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                           raw_archive_sha256=hashlib.sha256(original).hexdigest(),
                           history_pages_sha256=[hashlib.sha256(raw).hexdigest() for raw in history.raw_pages],
                           first_returned_open=history.rows[0]["timestamp"] if history.rows else None,
                           last_returned_open=history.rows[-1]["timestamp"] if history.rows else None,
                           chronological_plan_has_enough_rows=len(assessment.completed) >= 11520,
                           positive_volume_rows=sum(r.volume > 0 for r in assessment.completed),
                           symbol_bound_by="exact query pair and current active discovery; no per-row symbol or historical listing proof")
                # Last completed bar is an observation, never an executable quote.
                if assessment.completed:
                    reference = max(assessment.completed, key=lambda r: r.timestamp)
                    row["price_observation"] = {"price": reference.close, "candle_open_utc": reference.timestamp,
                         "candle_close_utc": reference.closed_at, "retrieved_by_utc": datetime.now(timezone.utc),
                         "label": "HISTORICAL_COMPLETED_CLOSE_NOT_EXECUTABLE_QUOTE",
                         "as_of_capture_age_seconds": str((as_of - reference.closed_at).total_seconds())}
                    try:
                        instrument = discover_instrument(client, market.pair)
                        diagnostic = minimum_order_diagnostic(settings, instrument, reference.close)
                        row.update(public_instrument=asdict(instrument), hypothetical_size=diagnostic,
                                   hypothetical_costs=cost_breakdown(settings, diagnostic))
                    except (ExchangeBlocked, PublicDataError) as exc:
                        row["instrument_error"] = exc.code if isinstance(exc, PublicDataError) else str(exc)
            except PublicDataError as exc:
                row.update(reason=exc.code, http_status=exc.status)
        selected.append(row)
        save(output / "markets.json", selected)
        print(json.dumps({"asset": asset, "status": row["status"],
                          "rows": row.get("quality", {}).get("input_rows"),
                          "reasons": row.get("quality", {}).get("reasons", [row.get("reason")]),
                          "size_status": row.get("hypothetical_size", {}).get("status")}), flush=True)
    result = {"phase": "8D", "label": "ACTUAL_PUBLIC_HISTORY_AND_HYPOTHETICAL_SIZE_NOT_MARKET_PERFORMANCE",
              "captured_at_utc": as_of, "completed_at_utc": datetime.now(timezone.utc),
              "actual_seconds": time.monotonic() - began, "requested_start": start, "requested_end_exclusive": end,
              "settings": asdict(settings), "predeclared_split_plan": split,
              "environment": {"system": platform.system(), "python": platform.python_version(), "sqlite": sqlite3.sqlite_version},
              "markets": selected, "request_manifest": requests, "orders_submitted": 0, "private_requests": 0,
              "live_trading_enabled": False, "backtests_run": 0, "out_of_sample_tests_run": 0,
              "performance_metrics": None, "backtest_status": "BLOCKED",
              "limitations": ["Diagnostic acquisition does not supply independently reviewed quote liquidity or listing identity.",
                   "No automatic qualification, settings increases, repairs, account mutations or backtest calls.",
                   "Current public metadata is not authenticated historical constraints; configured costs are estimates.",
                   "Real spot supports 1x only here; max 3x is a ceiling, not a product capability.",
                   "Size-only arithmetic omits current account/day/position/halts and cannot grant risk approval."]}
    save(output / "evidence.json", result)
    return 0  # Capture completed, NOT backtest qualification or order approval.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="NEW directory, normally under ignored reports/")
    parser.add_argument("--end", type=utc, help="explicit completed historical end, exclusive; default latest closed boundary")
    args = parser.parse_args()
    return run(args.output, args.end)


if __name__ == "__main__":
    raise SystemExit(main())
