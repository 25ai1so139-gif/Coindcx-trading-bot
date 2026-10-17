"""SQLite-owned paper session leases and controls; no network or order API."""

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
from pathlib import Path
import sqlite3

from data.models import Candle
from data.schema import INTERVAL, utc
from paper_trading import state
from paper_trading.persistence import (CandleConflict, CorruptState, PersistenceError,
                                       Update, _hash, _require)
from strategies import create_strategy
from strategies.base import Signal

LEASE_SECONDS = 300
HEALTH = {"STARTING", "WAITING", "OK", "NO_TRADE", "DATA_BLOCKED", "NETWORK_ERROR", "STOPPED"}
KEYS = {"format", "configuration", "owner", "lease_until", "updated_at", "entry_after",
        "stop_requested", "health", "last_success", "reason", "events"}
REASONS = {"STARTING", "COMPLETED", "NO_NEW_CANDLE", "UNQUALIFIED_MARKET", "INVALID_DATA",
           "MISSING_INTERVALS", "STALE_DATA", "INSUFFICIENT_HISTORY", "PUBLIC_API_ERROR",
           "STOP_REQUESTED", "SIGNAL_NO_TRADE", "RISK_HALTED", "ZERO_VOLUME", "DUPLICATE_TIMESTAMPS",
           "OUT_OF_ORDER", "FUTURE_DATA", "UNSUPPORTED_ACCOUNT_CURRENCY", "MARKET_NOT_CONFIRMED_ACTIVE",
           "OUTSIDE_REQUESTED_RANGE", "SOURCE_INGESTION_REJECTED", "ILLIQUID", "INVALID_SYMBOL"}


class SessionError(PersistenceError):
    pass


class SessionStopped(SessionError):
    """A validated, durable operator stop; normal worker shutdown."""


def boundary(at):
    at = utc(at)
    return at.replace(minute=at.minute // 15 * 15, second=0, microsecond=0)


def configuration(settings, strategy, poll_seconds=30):
    if type(poll_seconds) is not int or not 1 <= poll_seconds <= 120:
        raise ValueError("POLL_SECONDS_MUST_BE_1_TO_120")
    if strategy.name != settings.strategy or strategy.minimum_bars > settings.min_history_bars:
        raise ValueError("STRATEGY_MUST_MATCH_ACCOUNT_AND_HISTORY_WINDOW")
    root = Path(__file__).resolve().parents[1]
    engine = _hash(state.canonical({name: _hash((root / name).read_text(encoding="utf-8")) for name in
                  ("paper_trading/continuous.py", "paper_trading/session.py", "strategies/sma_cross.py", "strategies/momentum.py")}))
    return state.strict_json(state.canonical({"strategy": strategy.name, "parameters": asdict(strategy), "engine": engine,
                                             "poll_seconds": poll_seconds, "contract": "public-15m-v1"}))


def _stamp(value):
    return isinstance(value, str) and utc(value).isoformat() == value


def validate_runtime(value, broker, settings):
    _require(isinstance(value, dict) and set(value) == KEYS and type(value["format"]) is int and value["format"] == 1, "INVALID_SESSION_FORMAT")
    config = value["configuration"]
    _require(isinstance(config, dict) and set(config) == {"strategy", "parameters", "engine", "poll_seconds", "contract"},
             "INVALID_SESSION_CONFIGURATION")
    strategy = create_strategy(config["strategy"], **config["parameters"])
    _require(configuration(settings, strategy, config["poll_seconds"]) == config, "SESSION_CONFIGURATION_MISMATCH")
    _require(_stamp(value["updated_at"]) and _stamp(value["entry_after"]), "INVALID_SESSION_TIME")
    _require(utc(value["entry_after"]) == boundary(value["entry_after"]), "INVALID_ENTRY_BOUNDARY")
    _require(type(value["stop_requested"]) is bool and value["health"] in HEALTH and value["reason"] in REASONS)
    _require((value["owner"] is None) == (value["lease_until"] is None), "INVALID_SESSION_OWNER")
    if value["owner"] is not None:
        _require(isinstance(value["owner"], str) and str(UUID(value["owner"])) == value["owner"])
        _require(_stamp(value["lease_until"]) and timedelta(0) <= utc(value["lease_until"]) - utc(value["updated_at"]) <= timedelta(seconds=LEASE_SECONDS))
    if value["last_success"] is not None:
        _require(_stamp(value["last_success"]) and utc(value["last_success"]) <= utc(value["updated_at"]))
    _require(isinstance(value["events"], list) and len(value["events"]) <= 256)
    previous = None
    for event in value["events"]:
        _require(isinstance(event, dict) and set(event) == {"at", "health", "reason"} and _stamp(event["at"])
                 and event["health"] in HEALTH and event["reason"] in REASONS)
        _require(previous is None or utc(event["at"]) >= previous, "SESSION_CLOCK_MOVED_BACKWARDS")
        previous = utc(event["at"])
    _require(bool(value["events"]) and value["events"][-1] == {
        "at": value["updated_at"], "health": value["health"], "reason": value["reason"]})
    if value["stop_requested"]:
        _require(broker.risk.emergency_halted and value["owner"] is None and value["health"] == "STOPPED",
                 "STOP_WITHOUT_PERSISTENT_EMERGENCY_HALT")


def note(runtime, now, health, reason, *, success=False):
    now = utc(now)
    if now < utc(runtime["updated_at"]):
        raise SessionError("SESSION_CLOCK_MOVED_BACKWARDS")
    if health not in HEALTH or reason not in REASONS:
        raise SessionError("INVALID_HEALTH_EVENT")
    runtime.update(updated_at=now.isoformat(), health=health, reason=reason)
    if success:
        runtime["last_success"] = now.isoformat()
    if runtime["owner"] is not None:
        runtime["lease_until"] = (now + timedelta(seconds=LEASE_SECONDS)).isoformat()
    runtime["events"] = (runtime["events"] + [{"at": now.isoformat(), "health": health, "reason": reason}])[-256:]


def stop_runtime(runtime, now):
    runtime.update(stop_requested=True, owner=None, lease_until=None)
    note(runtime, now, "STOPPED", "STOP_REQUESTED")


def write_runtime(connection, runtime):
    payload = state.canonical(runtime)
    connection.execute("UPDATE runtime SET payload=?,digest=? WHERE singleton=1", (payload, _hash(payload)))


def _transaction(account, action):
    """Candidate financial state and session state commit together, or neither does."""
    with account._lock:
        if account._closed or account._failed or account._busy:
            account._failed = True
            raise SessionError("ACCOUNT_HANDLE_UNAVAILABLE")
        account._busy = True
        try:
            with account._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                meta, broker, snapshot, processed, _, version = account._read(connection)
                result = action(connection, broker, snapshot, processed, version)
                operation, candle, runtime = result
                if account._failed:
                    raise SessionError("REENTRANT_SESSION_ABORTED")
                payload = state._dump(broker)
                applied = payload != snapshot.state_json
                if applied:
                    account._append(connection, meta, snapshot, payload, operation, candle)
                write_runtime(connection, runtime)
                _, _, after, _, _, _ = account._read(connection)
                account._commit(connection)
                account._pinned = after.checkpoint
                return Update(applied, after)
        except BaseException as exc:
            if isinstance(exc, SessionStopped):
                raise
            account._failed = True
            if isinstance(exc, sqlite3.Error):
                raise PersistenceError("SESSION_STORAGE_FAILED_REOPEN_REQUIRED") from None
            if isinstance(exc, (ValueError, TypeError, ArithmeticError, AttributeError, KeyError)):
                raise CorruptState("SESSION_VALIDATION_FAILED") from None
            raise
        finally:
            account._busy = False


def enable(account, config, now):
    """Explicit atomic v2 -> v3 extension; existing financial checkpoints unchanged."""
    now = utc(now)
    def action(connection, broker, snapshot, processed, version):
        if broker.risk.emergency_halted:
            raise SessionError("EMERGENCY_HALTED_ACCOUNT_CANNOT_START")
        if version == 2:
            connection.execute("CREATE TABLE runtime (singleton INTEGER PRIMARY KEY CHECK(singleton=1), payload TEXT NOT NULL, digest TEXT NOT NULL)")
            runtime = dict(format=1, configuration=config, owner=None, lease_until=None,
                           updated_at=now.isoformat(), entry_after=boundary(now).isoformat(),
                           stop_requested=False, health="STARTING", last_success=None, reason="STARTING", events=[])
            note(runtime, now, "STARTING", "STARTING")
            payload = state.canonical(runtime)
            connection.execute("INSERT INTO runtime VALUES (1,?,?)", (payload, _hash(payload)))
            connection.execute("PRAGMA user_version=3")
        else:
            runtime = snapshot.runtime
            if runtime["configuration"] != config:
                raise SessionError("SESSION_CONFIGURATION_MISMATCH")
        return None, None, runtime
    return _transaction(account, action).snapshot


def _owned(runtime, owner, now):
    if runtime is not None and runtime["stop_requested"]:
        raise SessionStopped("DURABLE_STOP_REQUESTED")
    if (runtime is None or runtime["stop_requested"] or runtime["owner"] != owner
            or utc(now) >= utc(runtime["lease_until"])):
        raise SessionError("SESSION_STOPPED_OR_LEASE_LOST")


def claim(account, now):
    owner = str(uuid4())
    now = utc(now)
    def action(connection, broker, snapshot, processed, version):
        runtime = snapshot.runtime
        if runtime is None or runtime["stop_requested"] or broker.risk.emergency_halted:
            raise SessionError("SESSION_NOT_STARTABLE")
        if runtime["owner"] is not None and now < utc(runtime["lease_until"]):
            raise SessionError("SESSION_ALREADY_OWNED")
        runtime.update(owner=owner, lease_until=(now + timedelta(seconds=LEASE_SECONDS)).isoformat(),
                       entry_after=boundary(now).isoformat())
        note(runtime, now, "STARTING", "STARTING")
        return None, None, runtime
    _transaction(account, action)
    return owner


def heartbeat(account, owner, now, health="WAITING", reason="NO_NEW_CANDLE", *, success=False):
    def action(connection, broker, snapshot, processed, version):
        runtime = snapshot.runtime
        _owned(runtime, owner, now)
        note(runtime, now, health, reason, success=success)
        return None, None, runtime
    return _transaction(account, action).snapshot


def process(account, owner, now, candle, signal=Signal.HOLD, *, entry=None):
    now = utc(now)
    def action(connection, broker, snapshot, processed, version):
        runtime = snapshot.runtime
        _owned(runtime, owner, now)
        checked = Candle(candle.timestamp, candle.open, candle.high, candle.low, candle.close, candle.volume)
        if checked.closed_at > now:
            raise SessionError("INCOMPLETE_SESSION_CANDLE")
        stored = processed.get(checked.timestamp.isoformat())
        if stored is not None:
            if state._decode(state.strict_json(stored), Candle) != checked:
                raise CandleConflict("CONFLICTING_PROCESSED_CANDLE")
            return None, None, runtime
        if broker.last_bar is not None and checked.timestamp != broker.last_bar + INTERVAL:
            raise SessionError("MISSING_SESSION_INTERVALS")
        if signal != Signal.HOLD:
            if (broker.last_bar is None or checked.timestamp < utc(runtime["entry_after"])
                    or checked.timestamp != boundary(now) - INTERVAL):
                raise SessionError("STARTUP_OR_CATCHUP_ENTRY_FORBIDDEN")
        if signal == Signal.BUY and (entry is None or not entry.candles or entry.candles[-1].closed_at != checked.timestamp):
            raise SessionError("ENTRY_REQUIRES_PRIOR_COMPLETED_HISTORY")
        if entry is not None:
            for bar in entry.candles:
                stored_bar = processed.get(bar.timestamp.isoformat())
                if stored_bar is not None and state._decode(state.strict_json(stored_bar), Candle) != bar:
                    raise CandleConflict("REVISED_PROCESSED_HISTORY")
        broker.process_bar(checked, signal, entry=entry)
        note(runtime, now, "OK", "COMPLETED", success=True)
        return "bar", checked, runtime
    return _transaction(account, action)


def stop(account, now=None):
    now = utc(now or datetime.now(timezone.utc))
    def action(connection, broker, snapshot, processed, version):
        runtime = snapshot.runtime
        if runtime is None:
            raise SessionError("NO_CONTINUOUS_SESSION")
        broker.emergency_shutdown()
        stop_runtime(runtime, now)
        return "emergency", None, runtime
    return _transaction(account, action).snapshot
