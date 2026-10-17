"""Paper session CLI; status/stop are local database operations only."""

import argparse
import json
import logging
import sqlite3
import sys
from dataclasses import replace
from pathlib import Path
from threading import Event

from config import Settings, decimal_value
from data.coindcx import PublicClient
from paper_trading import session, state
from paper_trading.continuous import PaperLoop, PublicFeed, ShutdownRequested, status
from paper_trading.persistence import PersistentPaperBroker, PersistenceError
from strategies import STRATEGIES, create_strategy


def open_account(path):
    """Read identity as untrusted input, then validate the complete database."""
    path = Path(path).resolve()
    try:
        connection = sqlite3.connect(path.as_uri() + "?mode=rw", uri=True)
        try:
            rows = dict(connection.execute("SELECT key,value FROM meta"))
        finally:
            connection.close()
        settings = Settings(**state.strict_json(rows["settings"]))
        return PersistentPaperBroker.open(path, settings, symbol=rows["symbol"], data_kind=rows["data_kind"],
                                          allow_synthetic=rows["data_kind"] == "synthetic")
    except (sqlite3.Error, KeyError, TypeError, ValueError):
        raise PersistenceError("CANNOT_OPEN_VALIDATED_PAPER_ACCOUNT") from None


def command_parser():
    parser = argparse.ArgumentParser(prog="python -m cli paper", description="Public-data paper sessions; all fills are simulated estimates.")
    subs = parser.add_subparsers(dest="action", required=True)
    for action in ("start", "status", "stop"):
        command = subs.add_parser(action)
        command.add_argument("--db", type=Path, required=True, help="local durable SQLite account (never automatically reset)")
        if action == "start":
            command.add_argument("--create", action="store_true", help="explicitly create a NEW historical-data account; refuses existing files")
            command.add_argument("--symbol", help="exact INR native pair returned by public market discovery; required with --create")
            command.add_argument("--strategy", choices=sorted(STRATEGIES))
            command.add_argument("--poll-seconds", type=int)
            command.add_argument("--fast", type=int)
            command.add_argument("--slow", type=int)
            command.add_argument("--lookback", type=int)
            command.add_argument("--threshold")
            for name in ("margin-amount", "leverage", "fee-rate", "slippage-rate"):
                command.add_argument("--" + name, type=lambda v: decimal_value(v, "paper setting"))
    return parser


def main(argv):
    args = command_parser().parse_args(argv)
    account = None
    logging_state = []
    try:
        if args.action == "start":
            configured = Settings.from_env()  # Invalid/live start settings never silently ignored.
            overrides = {key: getattr(args, key) for key in ("strategy", "margin_amount", "leverage", "fee_rate", "slippage_rate")
                         if getattr(args, key) is not None}
            if args.create:
                if not args.symbol:
                    raise ValueError("--symbol is required with --create")
                settings = replace(configured, mode="paper", **overrides)
                strategy = create_strategy(settings.strategy, **{key: getattr(args, key) for key in ("fast", "slow", "lookback", "threshold")})
                session.configuration(settings, strategy, args.poll_seconds if args.poll_seconds is not None else 30)
                account = PersistentPaperBroker.create(args.db, settings, symbol=args.symbol, data_kind="historical")
            else:
                account = open_account(args.db)
                settings = account._settings
                if overrides and replace(settings, **overrides) != settings:
                    raise ValueError("resume must preserve the saved account settings")
                if args.symbol is not None and args.symbol != account.snapshot().symbol:
                    raise ValueError("resume symbol must match the saved account")
                runtime = account.snapshot().runtime
                parameters = dict(runtime["configuration"]["parameters"]) if runtime else {}
                parameters.update({key: getattr(args, key) for key in ("fast", "slow", "lookback", "threshold") if getattr(args, key) is not None})
                strategy = create_strategy(settings.strategy, **parameters)
            if account.snapshot().data_kind != "historical":
                raise ValueError("public-data sessions require a historical-data account")
            runtime = account.snapshot().runtime
            poll_seconds = args.poll_seconds if args.poll_seconds is not None else runtime["configuration"]["poll_seconds"] if runtime else 30
            shutdown = Event()
            def interruptible_wait(seconds):
                if shutdown.wait(seconds):
                    raise ShutdownRequested()
            client = PublicClient(sleep=interruptible_wait, max_retry_delay=5)
            # JSON lines to stderr; no provider response bodies, credentials or arbitrary exception text.
            for name in ("coindcx.paper", "coindcx.risk"):
                logger = logging.getLogger(name)
                previous = (logger, logger.level, logger.propagate, None)
                logger.setLevel(logging.INFO)
                if not logger.handlers:
                    handler = logging.StreamHandler(sys.stderr)
                    logger.addHandler(handler)
                    previous = (*previous[:3], handler)
                logger.propagate = False
                logging_state.append(previous)
            PaperLoop(account, strategy, feed=PublicFeed(client), poll_seconds=poll_seconds, shutdown=shutdown).run()
        else:
            account = open_account(args.db)
            if args.action == "stop":
                session.stop(account)
        print(json.dumps(status(account), default=str))
        return 0
    except (OSError, ValueError, PersistenceError, ArithmeticError):
        print(json.dumps({"status": "BLOCKED", "reason": "PAPER_SESSION_FAILED_CLOSED",
                          "orders_submitted": 0, "live_trading_enabled": False}), file=sys.stderr)
        return 2
    finally:
        for logger, level, propagate, handler in logging_state:
            if handler is not None:
                logger.removeHandler(handler)
                handler.close()
            logger.setLevel(level)
            logger.propagate = propagate
        if account is not None:
            account.close()
