"""Simulation and public-data commands. There is no live-order command."""

import argparse
import json
import sys
from dataclasses import asdict, replace
from decimal import DecimalException
from pathlib import Path
from typing import Sequence
from datetime import datetime, timezone

from backtesting.engine import simulate
from backtesting.datasets import BacktestBlocked, load_eligible
from backtesting.experiment import run_experiment
from backtesting.metrics import calculate_metrics
from backtesting.reporting import write_report
from backtesting.splits import SplitPlan
from config import Settings, decimal_value
from data.schema import utc
from data.loader import load_csv
from data.commands import add_data_commands, load_policy, run_data_command
from strategies import STRATEGIES, create_strategy
from strategies.verification import verify_file
from risk.audit import RiskAudit


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="CoinDCX offline backtesting and paper simulation only")
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser("strategies", help="list available strategies")
    commands.add_parser("exchange", help="public instrument inspection; execution unavailable")
    add_data_commands(commands)
    for name in ("backtest", "paper", "verify", "evaluate"):
        command = commands.add_parser(name, aliases=["manual"] if name == "verify" else [])
        if name == "paper":
            command.description = "CSV replay; durable public-data sessions use: paper start/status/stop --help"
        command.add_argument("--data", required=True, help="CSV with a same-stem JSON sidecar")
        command.add_argument("--strategy", choices=sorted(STRATEGIES))
        command.add_argument("--margin-amount", type=lambda v: decimal_value(v, "margin_amount"),
                             help="requested INR margin, not notional")
        command.add_argument("--leverage", type=lambda v: decimal_value(v, "leverage"))
        command.add_argument("--allow-synthetic", action="store_true", help="explicitly allow demo data")
        command.add_argument("--fast", "--fast-period", dest="fast", type=int, help="SMA fast period")
        command.add_argument("--slow", "--slow-period", dest="slow", type=int, help="SMA slow period")
        command.add_argument("--lookback", type=int, help="momentum lookback")
        command.add_argument("--threshold", help="momentum fractional threshold")
        if name != "verify":
            command.add_argument("--fee-rate", type=lambda v: decimal_value(v, "fee_rate"), help="unverified assumed fee fraction on each fill")
            command.add_argument("--slippage-rate", type=lambda v: decimal_value(v, "slippage_rate"), help="unverified adverse fraction on each fill")
            command.add_argument("--data-policy", type=Path, help="Phase 2 policy; real-data liquidity cannot be bypassed")
            command.add_argument("--data-as-of", type=utc, help="historical freshness cutoff; defaults to dataset end, not current freshness")
        if name == "evaluate":
            command.add_argument("--plan", required=True, type=Path, help="JSON chronological SplitPlan")
            command.add_argument("--output", required=True, type=Path, help="new report directory; never overwritten")
            command.add_argument("--sensitivity", type=Path, help="JSON list of strategy parameter objects, train/validation only")
            command.add_argument("--stress-multiplier", default="2", type=lambda v: decimal_value(v, "stress_multiplier"), help="multiply both modeled cost rates, default 2; must exceed 1")
        if name == "verify":
            command.add_argument("--symbol", help="native symbol; must match dataset metadata")
            command.add_argument("--timeframe", default="15m")
            command.add_argument("--as-of", type=utc, help="explicit historical UTC evaluation time; otherwise now")
            command.add_argument("--risk-state", help="read-only simulated-account JSON snapshot; never assumes a fresh account")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] == "exchange":
        from exchange.commands import main as exchange_command
        return exchange_command(arguments[1:])
    if len(arguments) >= 2 and arguments[0] == "paper" and arguments[1] in ("start", "status", "stop"):
        from paper_trading.commands import main as paper_command
        return paper_command(arguments[1:])
    args = parser().parse_args(arguments)
    if args.command == "manual":
        args.command = "verify"
    try:
        settings = Settings.from_env()
        if args.command == "data":
            return run_data_command(args)
        if args.command == "strategies":
            print("\n".join(sorted(STRATEGIES)))
            return 0
        overrides = {name: getattr(args, name) for name in ("strategy", "margin_amount", "leverage", "fee_rate", "slippage_rate")
                     if getattr(args, name, None) is not None}
        if args.command != "verify":
            overrides["mode"] = "paper" if args.command == "paper" else "backtest"
        settings = replace(settings, **overrides)
        strategy = create_strategy(settings.strategy, **{key: getattr(args, key)
                                   for key in ("fast", "slow", "lookback", "threshold")})
        if args.command == "verify":
            output = verify_file(args.data, settings, strategy, as_of=args.as_of,
                                 symbol=args.symbol, timeframe=args.timeframe,
                                 allow_synthetic=args.allow_synthetic, risk_state=args.risk_state)
            print(json.dumps(output, indent=2, default=str))
            return 0  # A completed NO_TRADE review is a normal result; inspect signal/reasons.
        market = load_csv(args.data, settings.min_history_bars, args.allow_synthetic)
        dataset = load_eligible(args.data, settings, allow_synthetic=args.allow_synthetic,
                                as_of=args.data_as_of, loaded_market=market,
                                policy=load_policy(args.data_policy) if args.data_policy else None)
        if args.command == "evaluate":
            plan = json.loads(args.plan.read_text(encoding="utf-8"))
            if not isinstance(plan, dict):
                raise ValueError("plan must be a JSON object")
            try:
                split = SplitPlan(**plan)
            except TypeError as exc:
                raise ValueError("invalid split plan fields") from exc
            sensitivity = json.loads(args.sensitivity.read_text(encoding="utf-8")) if args.sensitivity else []
            if not isinstance(sensitivity, list) or any(not isinstance(item, dict) for item in sensitivity):
                raise ValueError("sensitivity must be a list of strategy parameter objects")
            report = run_experiment(dataset, settings, strategy, split, parameter_sensitivity=tuple(sensitivity),
                                    stress_multiplier=args.stress_multiplier)
            write_report(args.output, report)
            print(json.dumps({"status": report["status"], "run_id": report["run_id"], "output": str(args.output),
                              "data_kind": market.kind, "orders_submitted": 0, "live_trading_enabled": False}))
            return 0
        status = 0
        if len(market.candles) < strategy.minimum_bars:
            raise ValueError("dataset does not meet strategy warmup requirements")
        result = simulate(settings, market, strategy, risk_context=dataset.risk_context)
        output = asdict(result)
        status = 130 if result.interrupted else 0
        output["trade_count"] = len(output["trades"])
        output["strategy"] = settings.strategy
        output["strategy_parameters"] = asdict(strategy) if hasattr(strategy, "__dataclass_fields__") else {}
        output["currency"] = "INR"
        output["configuration"] = asdict(settings)
        output["data"] = dataset.evidence
        output["date_range"] = {"start_inclusive": market.candles[0].timestamp, "end_exclusive": market.candles[-1].closed_at}
        output["metrics"] = calculate_metrics(result)
        output["live_trading_enabled"] = False
        if market.kind == "synthetic":
            output["warning"] = "Synthetic demo data; results are not evidence of market performance."
        print(json.dumps(output, indent=2, default=str))
        return status
    except KeyboardInterrupt:
        print("Interrupted before a complete result; real-money trading remains disabled.", file=sys.stderr)
        return 130
    except (OSError, ValueError, DecimalException) as exc:
        if args.command == "evaluate" or isinstance(exc, BacktestBlocked):
            print(json.dumps({"status": "BLOCKED", "reason": str(exc), "orders_submitted": 0, "live_trading_enabled": False}))
        if args.command == "verify":
            audit = RiskAudit()
            record = audit.record(at=datetime.now(timezone.utc), approved=False, reason="INVALID_CONFIGURATION")
            print(json.dumps({"command": "verify", "signal": "NO_TRADE",
                              "reasons": ["INVALID_CONFIGURATION", str(exc)],
                              "entry_candidate": False, "risk_preview": None,
                              "orders_submitted": 0, "live_trading_enabled": False,
                              "risk_decisions": [asdict(record)]}, default=str))
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
