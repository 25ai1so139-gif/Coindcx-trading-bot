"""Public metadata inspection only; no authenticated or order commands."""

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from data.cache import ResponseCache
from data.coindcx import PublicClient, PublicDataError
from exchange.contracts import ExchangeBlocked
from exchange.instruments import discover_instrument


def main(argv):
    parser = argparse.ArgumentParser(prog="python -m cli exchange", description="Public instrument metadata; private transport and real execution unavailable.")
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("instrument")
    inspect.add_argument("--pair", required=True, help="exact confirmed pair from data markets")
    inspect.add_argument("--cache", type=Path, default=Path("data/local/cache"))
    args = parser.parse_args(argv)
    try:
        instrument = discover_instrument(PublicClient(ResponseCache(args.cache)), args.pair)
        result = {"status": "PUBLIC_METADATA_ONLY", "instrument": asdict(instrument),
                  "market_qualified": False, "price_tick_exchange_validated": False,
                  "orders_submitted": 0, "live_trading_enabled": False}
        print(json.dumps(result, default=str, indent=2))
        return 0
    except (PublicDataError, ExchangeBlocked, OSError):
        print(json.dumps({"status": "BLOCKED", "reason": "PUBLIC_INSTRUMENT_METADATA_UNAVAILABLE",
                          "orders_submitted": 0, "live_trading_enabled": False}))
        return 2
