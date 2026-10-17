"""Completed-candle paper simulation with durable controls and unsigned data."""

import json
import logging
import signal
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from threading import Event, current_thread, main_thread

from data.coindcx import PublicClient, PublicDataError
from data.models import Candle
from data.quality import DataPolicy, assess
from data.schema import INTERVAL, utc
from paper_trading import session
from paper_trading.persistence import PersistenceError
from risk.proposal import EntryProposal, MarketContext
from strategies.base import Signal, replay_action

LOGGER = logging.getLogger("coindcx.paper")
MAX_CATCHUP = 96


class ShutdownRequested(Exception):
    pass


@dataclass(frozen=True)
class Batch:
    rows: tuple
    metadata: dict


class PublicFeed:
    """Only the existing whitelisted public GET client; no credential inputs."""
    def __init__(self, client=None):
        self.client = client or PublicClient(max_retry_delay=5)

    def fetch(self, symbol, start, end):
        history = self.client.history(symbol, start, end, max_pages=12)
        market = history.market
        return Batch(history.rows, {"symbol": market.pair, "timeframe": "15m", "kind": "historical",
                     "quote_currency": market.quote_currency, "market_status": market.status,
                     "source_order_valid": history.source_order_valid, "ingestion_warnings": list(history.warnings),
                     "requested_start": start.isoformat(), "requested_end": end.isoformat(),
                     "quote_volume_verified": False, "quality_reviewed": False})


def status(account, now=None):
    now = utc(now or datetime.now(timezone.utc))
    snapshot = account.snapshot()
    value, runtime = snapshot.state, snapshot.runtime
    risk = value["risk"]
    day = risk["day"]
    daily_known = day == now.date().isoformat()
    equity, start = Decimal(value["equity"]), Decimal(risk["day_start_equity"])
    observations = value["observations"]
    before_today = [row for row in observations if utc(row["timestamp"]).date() < now.date()]
    realized_start = Decimal(before_today[-1]["realized_pnl"]) if before_today else Decimal(0)
    realized_now = Decimal(observations[-1]["realized_pnl"]) if observations else Decimal(0)
    current = bool(runtime and runtime["owner"] is not None and now < utc(runtime["lease_until"]))
    last = utc(runtime["last_success"]) if runtime and runtime["last_success"] else None
    fresh = last is not None and timedelta(0) <= now - last <= timedelta(minutes=30)
    health = runtime["health"] if runtime else "NO_SESSION"
    if runtime and runtime["stop_requested"]:
        health = "STOPPED"
    elif runtime and (not current or not fresh):
        health = "STALE_OR_OFFLINE"
    return {"mode": "paper", "symbol": snapshot.symbol, "data_kind": snapshot.data_kind,
            "fills": "SIMULATED_ESTIMATES", "live_trading_enabled": False, "orders_submitted": 0,
            "health": health, "session": runtime, "revision": snapshot.checkpoint.revision,
            "equity": str(equity), "cash": value["cash"], "realized_pnl": value["realized_pnl"],
            "open_position": value["position"], "last_completed_candle": value["last_candle"],
            "last_successful_market_data_at": runtime["last_success"] if runtime else None,
            "risk": risk, "accounting_utc_day": day, "daily_summary_current": daily_known,
            "daily_marked_pnl": str(equity - start) if daily_known else None,
            "daily_realized_pnl": str(realized_now - realized_start) if daily_known else None,
            "equity_marked_at": (utc(value["last_candle"]["timestamp"]) + INTERVAL).isoformat() if value["last_candle"] else None,
            "closed_trades": len(value["trades"]), "processed_candles": snapshot.processed_candles}


class PaperLoop:
    def __init__(self, account, strategy, *, feed=None, poll_seconds=30, now=None, shutdown=None):
        self.account, self.strategy = account, strategy
        self.settings = account._settings
        self.config = session.configuration(self.settings, strategy, poll_seconds)
        if self.settings.min_history_bars > 10000:
            raise ValueError("CONTINUOUS_HISTORY_LIMIT_IS_10000")
        self.feed = feed or PublicFeed()
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.shutdown = shutdown or Event()
        self.owner = None
        self.last_report = None

    def start(self):
        session.enable(self.account, self.config, self.now())
        self.owner = session.claim(self.account, self.now())

    def _health(self, health, reason, *, success=False):
        result = session.heartbeat(self.account, self.owner, self.now(), health, reason, success=success)
        LOGGER.info(json.dumps({"at": utc(self.now()).isoformat(), "event": "paper_health",
                    "symbol": result.symbol, "data_kind": result.data_kind, "health": health,
                    "reason": reason, "orders_submitted": 0, "fills": "SIMULATED_ESTIMATES"}))
        return health

    def poll(self):
        if self.owner is None:
            raise session.SessionError("LOOP_NOT_STARTED")
        if self.shutdown.is_set():
            raise ShutdownRequested()
        session.heartbeat(self.account, self.owner, self.now())
        snapshot = self.account.snapshot()
        end = session.boundary(self.now())
        last = utc(snapshot.state["last_candle"]["timestamp"]) if snapshot.state["last_candle"] else None
        gap = (end - INTERVAL - last) // INTERVAL if last is not None else 0
        if gap > MAX_CATCHUP or gap < 0:
            return self._health("DATA_BLOCKED", "MISSING_INTERVALS")
        start = end - INTERVAL * (self.settings.min_history_bars + 2 + max(0, gap))
        try:
            batch = self.feed.fetch(snapshot.symbol, start, end)
        except PublicDataError:
            return self._health("NETWORK_ERROR", "PUBLIC_API_ERROR")
        except (OSError, TimeoutError):
            return self._health("NETWORK_ERROR", "PUBLIC_API_ERROR")
        if self.shutdown.is_set():
            raise ShutdownRequested()
        # Re-check lease/stop after network I/O, before any financial mutation.
        session.heartbeat(self.account, self.owner, self.now())
        metadata = dict(batch.metadata)
        if (metadata.get("symbol") != snapshot.symbol or metadata.get("kind") != snapshot.data_kind
                or metadata.get("timeframe") != "15m"):
            return self._health("DATA_BLOCKED", "INVALID_DATA")
        # The fetch contract owns the requested window; no shortened source range
        # may hide missing edges. Uncompleted rows are excluded by Phase 2.
        metadata.update(requested_start=start.isoformat(), requested_end=end.isoformat())
        policy = DataPolicy(min_history_bars=self.settings.min_history_bars,
                            require_verified_liquidity=snapshot.data_kind != "synthetic")
        try:
            assessment = assess(batch.rows, metadata, policy, self.now())
        except (ValueError, TypeError, OverflowError, KeyError):
            return self._health("DATA_BLOCKED", "INVALID_DATA")
        self.last_report = assessment.report
        unsafe = set(assessment.report["reasons"]) - {"LIQUIDITY_REVIEW_REQUIRED"}
        if unsafe:
            reason = ("STALE_DATA" if "STALE_DATA" in unsafe else "INSUFFICIENT_HISTORY"
                      if "INSUFFICIENT_HISTORY" in unsafe else "MISSING_INTERVALS"
                      if "INCOMPLETE_HISTORY" in unsafe else assessment.report["status"]
                      if assessment.report["status"] in session.REASONS else "INVALID_DATA")
            return self._health("DATA_BLOCKED", reason)
        candles = tuple(Candle(r.timestamp, r.open, r.high, r.low, r.close, r.volume) for r in assessment.completed)
        if not candles or candles[-1].timestamp != end - INTERVAL:
            return self._health("DATA_BLOCKED", "STALE_DATA")
        # Completed corrections must not silently change a previously used bar.
        if last is not None:
            prior = next((bar for bar in candles if bar.timestamp == last), None)
            if prior is None:
                return self._health("DATA_BLOCKED", "MISSING_INTERVALS")
            stored = snapshot.state["last_candle"]
            if any(str(getattr(prior, key)) != stored[key] and Decimal(str(getattr(prior, key))) != Decimal(stored[key])
                   for key in ("open", "high", "low", "close", "volume")):
                return self._health("DATA_BLOCKED", "INVALID_DATA")
        context = MarketContext.reviewed(metadata, assessment.report, self.settings)
        unqualified = not assessment.report["eligible"] or (snapshot.data_kind == "historical" and
                        (not context.quality_reviewed or not context.liquidity_verified or context.instrument is None))
        selected = [bar for bar in candles if last is None or bar.timestamp > last]
        if last is None:
            selected = [candles[-1]]  # Warmup never replays historical entries.
        for bar in selected:
            if self.shutdown.is_set():
                raise ShutdownRequested()
            visible = tuple(c for c in candles if c.closed_at <= bar.timestamp)[-self.settings.min_history_bars:]
            proposal, action = None, Signal.HOLD
            # Only the newest bar after this process claimed ownership can
            # attempt a new entry; catchup bars still enforce held-position stops.
            runtime = self.account.snapshot().runtime
            if (last is not None and gap <= 1 and bar.timestamp >= utc(runtime["entry_after"])
                    and bar.timestamp == session.boundary(self.now()) - INTERVAL):
                decision = self.strategy.evaluate(visible[-self.strategy.minimum_bars:], as_of=bar.timestamp,
                            symbol=snapshot.symbol, timeframe="15m", stop_loss_fraction=self.settings.stop_loss_fraction)
                action = replay_action(decision.signal)
                proposal = EntryProposal(self.strategy.name, decision, visible, context, bar.open)
            session.process(self.account, self.owner, self.now(), bar, action, entry=proposal)
        risk = self.account.snapshot().state["risk"]
        halted = any(risk[key] for key in ("daily_halted", "drawdown_halted", "emergency_halted")) or risk["entries_today"] >= self.settings.max_trades_per_day
        reason = "RISK_HALTED" if halted else "UNQUALIFIED_MARKET" if unqualified else "SIGNAL_NO_TRADE"
        return self._health("NO_TRADE" if unqualified or halted else "OK", reason, success=True)

    def run(self):
        handlers = {}
        if current_thread() is main_thread():
            for signum in (signal.SIGINT, signal.SIGTERM):
                handlers[signum] = signal.signal(signum, lambda *_: self.shutdown.set())
        try:
            self.start()
            while not self.shutdown.is_set():
                self.poll()
                if self.shutdown.wait(self.config["poll_seconds"]):
                    break
        except (KeyboardInterrupt, ShutdownRequested, session.SessionStopped):
            self.shutdown.set()
        except PersistenceError:
            # Never reopen/reset automatically following uncertain persistence.
            LOGGER.error(json.dumps({"at": utc(self.now()).isoformat(), "event": "paper_fail_closed",
                                     "reason": "PERSISTENCE_OR_SESSION_FAILURE", "orders_submitted": 0}))
            raise
        finally:
            for signum, handler in handlers.items():
                signal.signal(signum, handler)
            # A healthy handle can durably halt/flatten at the last known close.
            # A poisoned handle cannot acknowledge a stop; operator must reopen.
            if not self.account._failed:
                snapshot = self.account.snapshot()
                if snapshot.runtime is not None and self.owner is not None and snapshot.runtime["owner"] == self.owner:
                    session.stop(self.account, self.now())
