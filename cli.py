"""Offline command interface. There is intentionally no live-order command."""

import argparse
import json
import sys
from dataclasses import asdict, replace
from decimal import DecimalException
from typing import Sequence

from backtesting.engine import simulate
from config import Settings, decimal_value
from data.loader import load_csv
from risk.sizing import size_position
from strategies import STRATEGIES
from strategies.base import Signal


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="CoinDCX offline backtesting and paper simulation only")
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser("strategies", help="list available strategies")
    for name in ("backtest", "paper", "verify"):
        command = commands.add_parser(name, aliases=["manual"] if name == "verify" else [])
        command.add_argument("--data", required=True, help="CSV with a same-stem JSON sidecar")
        command.add_argument("--strategy", choices=sorted(STRATEGIES))
        command.add_argument("--margin-amount", type=lambda v: decimal_value(v, "margin_amount"),
                             help="requested INR margin, not notional")
        command.add_argument("--leverage", type=lambda v: decimal_value(v, "leverage"))
        command.add_argument("--allow-synthetic", action="store_true", help="explicitly allow demo data")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "manual":
        args.command = "verify"
    try:
        settings = Settings.from_env()
        if args.command == "strategies":
            print("\n".join(sorted(STRATEGIES)))
            return 0
        overrides = {name: getattr(args, name) for name in ("strategy", "margin_amount", "leverage")
                     if getattr(args, name) is not None}
        if args.command != "verify":
            overrides["mode"] = "paper" if args.command == "paper" else "backtest"
        settings = replace(settings, **overrides)
        market = load_csv(args.data, settings.min_history_bars, args.allow_synthetic)
        strategy = STRATEGIES[settings.strategy]()
        status = 0
        if len(market.candles) < strategy.minimum_bars:
            raise ValueError("dataset does not meet strategy warmup requirements")
        if args.command == "verify":
            signal = strategy.signal(market.candles)
            plan = size_position(settings, settings.starting_capital, market.candles[-1].close)
            output = {
                "command": "verify", "symbol": market.symbol, "data_kind": market.kind,
                "strategy": settings.strategy, "signal": signal.value,
                "as_of": market.candles[-1].closed_at.isoformat(),
                "orders_submitted": 0,
                "entry_candidate": signal == Signal.BUY,
                "risk_preview": asdict(plan),
                "note": "Verification only; preview assumes a fresh simulated account and is not authorization to trade.",
            }
        else:
            result = simulate(settings, market, strategy)
            output = asdict(result)
            status = 130 if result.interrupted else 0
            output["trade_count"] = len(output["trades"])
            output["strategy"] = settings.strategy
        output["currency"] = "INR"
        output["live_trading_enabled"] = False
        if market.kind == "synthetic":
            output["warning"] = "Synthetic demo data; results are not evidence of market performance."
        print(json.dumps(output, indent=2, default=str))
        return status
    except KeyboardInterrupt:
        print("Interrupted before a complete result; real-money trading remains disabled.", file=sys.stderr)
        return 130
    except (OSError, ValueError, DecimalException) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
