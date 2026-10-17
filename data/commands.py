"""Data commands are independent of brokers, positions, strategies, and credentials."""

import argparse
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from data.cache import ResponseCache
from data.coindcx import PublicClient, PublicDataError, ROUTES
from data.quality import DataPolicy, assess
from data.schema import utc
from data.storage import read_csv, write_dataset


def add_data_commands(commands) -> None:
    data = commands.add_parser("data", help="public market data and offline dataset quality")
    actions = data.add_subparsers(dest="data_action", required=True)
    markets = actions.add_parser("markets", help="discover public markets without authentication")
    markets.add_argument("--cache", type=Path, default=Path("data/local/cache"))
    for name in ("import", "validate", "fetch"):
        command = actions.add_parser(name)
        command.add_argument("--policy", type=Path, help="JSON DataPolicy overrides; no secrets")
        if name != "fetch":
            command.add_argument("--input", required=True, type=Path, help="CSV with same-stem JSON sidecar")
            command.add_argument("--as-of", type=utc, help="UTC evaluation time; defaults to the current time")
        if name != "validate":
            command.add_argument("--output", required=True, type=Path, help="new normalized CSV; never overwritten")
        if name == "fetch":
            command.add_argument("--pair", required=True, help="exact pair returned by data markets")
            command.add_argument("--start", required=True, type=utc)
            command.add_argument("--end", required=True, type=utc, help="exclusive end; quality is evaluated relative to this historical endpoint")
            command.add_argument("--cache", type=Path, default=Path("data/local/cache"))


def load_policy(path: Path | None) -> DataPolicy:
    if path is None:
        return DataPolicy()
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("policy file must contain a JSON object")
    try:
        return DataPolicy(**value)
    except TypeError as exc:
        raise ValueError("policy file contains unknown fields or invalid types") from exc


def run_data_command(args) -> int:
    try:
        if args.data_action == "markets":
            markets = PublicClient(ResponseCache(args.cache)).discover()
            result = {"markets": [asdict(market) for market in markets], "live_trading_enabled": False}
        else:
            policy = load_policy(args.policy)
            now = datetime.now(timezone.utc)
            if args.data_action == "fetch":
                history = PublicClient(ResponseCache(args.cache)).history(args.pair, args.start, args.end)
                metadata = {"symbol": history.market.pair, "timeframe": "15m", "kind": "historical",
                            "quote_currency": history.market.quote_currency,
                            "source": ROUTES["candles"], "market_status": history.market.status,
                            "quote_volume_verified": False, "source_order_valid": history.source_order_valid,
                            "ingestion_warnings": list(history.warnings),
                            "requested_start": args.start.isoformat(), "requested_end": args.end.isoformat()}
                assessment = assess(history.rows, metadata, policy, min(args.end, now))
                raw = json.dumps({"pages_utf8": [page.decode("utf-8") for page in history.raw_pages]},
                                 sort_keys=True).encode("utf-8")
                write_dataset(args.output, assessment, metadata, raw, "json")
            else:
                imported = read_csv(args.input)
                metadata = imported.metadata
                assessment = assess(imported.rows, metadata, policy, args.as_of or now)
                if args.data_action == "import":
                    write_dataset(args.output, assessment, metadata, imported.raw)
            result = assessment.report
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
        return 0 if result.get("eligible", True) else 2
    except PublicDataError as exc:
        print(json.dumps({"status": "API_FAILURE", "reason": exc.code, "http_status": exc.status,
                          "detail": str(exc), "live_trading_enabled": False}, sort_keys=True))
        return 2
