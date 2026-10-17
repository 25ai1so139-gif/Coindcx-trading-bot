"""Deterministic JSON, CSV and Markdown exports; never overwrite user reports."""

import csv
import json
import shutil
from dataclasses import fields
from pathlib import Path

from paper_trading.broker import EquityObservation, RiskEvent, Trade
from risk.audit import RiskRecord


def _variants(report):
    for period in report["periods"]:
        yield "baseline", period
    for period in report["cost_stress"]["periods"]:
        yield "cost_stress", period
    for index, candidate in enumerate(report["parameter_sensitivity"]):
        for period in candidate["periods"]:
            yield f"parameter_{index + 1}_development_only", period


def markdown_report(report: dict) -> str:
    lines = ["# Phase 4 chronological backtest report", "", f"Status: **{report['status']}**",
             f"Run ID: {report['run_id']}", "",
             f"Data kind: **{report['data']['kind']}** / {report['data']['source_class']}",
             f"Source: {report['data']['source']}",
             f"CSV SHA-256: {report['data']['csv_sha256']}; source SHA-256: {report['reproducibility']['source_sha256']}",
             f"Quality: {report['data']['quality']['status']}; liquidity: {report['data']['quality']['liquidity']}",
             f"Symbol: {report['symbol']}; timeframe: {report['timeframe']}",
             f"Strategy: {report['strategy']}; parameters: {json.dumps(report['strategy_parameters'], default=str, sort_keys=True)}",
             f"Configuration: {json.dumps(report['configuration'], default=str, sort_keys=True)}", "",
             report["boundary_policy"], report["test_policy"], "",
             "## Separate period results", "",
             "| Variant | Period | Start (inclusive UTC) | End (exclusive UTC) | Bars | Final INR | Net INR | Fees INR | Slippage INR | Drawdown % | Daily halts |",
             "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for variant, period in _variants(report):
        metric = period["metrics"]
        values = (variant, period["name"], period["start_inclusive"], period["end_exclusive"],
                  period["sample_bars"], metric["final_equity_inr"], metric["net_pnl_inr"], metric["fees_inr"],
                  metric["slippage_inr"], metric["max_drawdown_percent"], metric["daily_loss_limit_activations"])
        lines.append("| " + " | ".join(str(value) for value in values) + " |")
    lines += ["", "## Baseline metrics and references", "",
              "| Period | Closed trades | Win % | Profit factor | Expectancy INR | Buy-and-hold net INR | Cash net INR |",
              "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for period in report["periods"]:
        metric = period["metrics"]
        values = (period["name"], metric["closed_trades"], metric["win_rate_percent"], metric["profit_factor"],
                  metric["expectancy_per_trade_inr"], period["benchmarks"]["buy_and_hold"]["net_pnl_inr"],
                  period["benchmarks"]["cash_only"]["net_pnl_inr"])
        lines.append("| " + " | ".join("undefined" if value is None else str(value) for value in values) + " |")
    for period in report["periods"]:
        metric = period["metrics"]
        lines.extend(["", f"{period['name']} warmup: {period['warmup_bars']} bars from {period['warmup_start']}; activations: {json.dumps(metric['risk_activation_counts'], sort_keys=True)}", ""])
    lines += ["", "All trade, equity and activation records are in JSON and CSV. Undefined metrics are JSON null / empty CSV cells.",
              "Cash and buy-and-hold benchmarks use the same period and modeled costs; buy-and-hold has different risk exposure.", "",
              "## Cost assumptions", "", json.dumps(report["periods"][0]["simulation"]["cost_assumptions"], default=str, indent=2),
              "", f"Cost-stress assumptions (multiplier {report['cost_stress']['multiplier']}):",
              json.dumps(report["cost_stress"]["assumptions"], default=str, indent=2), "",
              "Development-only parameter scenarios: " + json.dumps([item["parameters"] for item in report["parameter_sensitivity"]], default=str, sort_keys=True),
              "", "## Limitations", ""]
    lines.extend(f"- {item}" for item in report["limitations"])
    lines += ["", "No real orders. No short entries. No claim of future profitability.", ""]
    return "\n".join(lines)


def write_report(output: str | Path, report: dict) -> None:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir()  # Exclusive creation; an existing directory is never reused.
    try:
        (output / "results.json").write_text(json.dumps(report, indent=2, sort_keys=True, default=str,
                                                        allow_nan=False) + "\n", encoding="utf-8")
        (output / "report.md").write_text(markdown_report(report), encoding="utf-8")
        records = {"metrics": [], "trades": [], "equity": [], "risk_events": [], "risk_decisions": []}
        for variant, period in _variants(report):
            label = {"run_id": report["run_id"], "data_kind": report["data"]["kind"], "symbol": report["symbol"],
                     "timeframe": report["timeframe"], "variant": variant, "period": period["name"]}
            records["metrics"].append({**label, "start_inclusive": period["start_inclusive"],
                                       "end_exclusive": period["end_exclusive"], "sample_bars": period["sample_bars"],
                                       **period["metrics"]})
            for name, source in (("trades", "trades"), ("equity", "equity_observations"),
                                 ("risk_events", "risk_events"), ("risk_decisions", "risk_decisions")):
                records[name].extend({**item, **label} for item in period["simulation"][source])
        for name, rows in records.items():
            columns = list(rows[0]) if rows else ["run_id", "data_kind", "symbol", "timeframe", "variant", "period"]
            if not rows and name != "metrics":
                columns += [field.name for field in fields({"trades": Trade, "equity": EquityObservation,
                                                           "risk_events": RiskEvent, "risk_decisions": RiskRecord}[name])
                            if field.name not in columns]
            with (output / f"{name}.csv").open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
                writer.writeheader()
                writer.writerows({key: json.dumps(value, sort_keys=True, default=str) if isinstance(value, (dict, list))
                                 else value for key, value in row.items()} for row in rows)
    except BaseException:
        shutil.rmtree(output)
        raise
