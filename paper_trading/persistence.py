"""Transactional, single-market paper accounts. No network or real orders.

SQLite owns serialization across processes. No mutable broker is published: a
candidate is recovered, executed through Phase 5, validated and committed before
an Update can be returned. Failed/ambiguous operations poison the current handle.
"""

import hashlib
import math
import os
import sqlite3
from dataclasses import dataclass, fields
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from threading import RLock
from uuid import UUID, uuid4

from config import Settings
from data.models import Candle
from data.schema import SYMBOL, utc
from paper_trading.broker import PaperBroker
from paper_trading import state
from risk.proposal import EntryProposal, MarketContext
from strategies.base import Signal

APPLICATION_ID = 0x43445850
SCHEMA_VERSION = 2
_META_KEYS = {"account_id", "symbol", "data_kind", "settings", "engine", "created_at"}
_SCHEMA_V1 = (
    "CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
    "CREATE TABLE checkpoints (revision INTEGER PRIMARY KEY, operation TEXT NOT NULL, payload TEXT NOT NULL, digest TEXT NOT NULL)",
    "CREATE TABLE processed (candle_id TEXT PRIMARY KEY, candle_json TEXT NOT NULL, revision INTEGER NOT NULL UNIQUE REFERENCES checkpoints(revision))",
    "CREATE TABLE head (singleton INTEGER PRIMARY KEY CHECK(singleton=1), revision INTEGER NOT NULL REFERENCES checkpoints(revision), digest TEXT NOT NULL)",
)
_COLUMNS_V1 = {"meta": ("key", "value"), "checkpoints": ("revision", "operation", "payload", "digest"),
               "processed": ("candle_id", "candle_json", "revision"), "head": ("singleton", "revision", "digest")}


class PersistenceError(RuntimeError):
    """Fail closed; discard this handle and explicitly reopen validated state."""


class CorruptState(PersistenceError):
    pass


class IncompatibleState(PersistenceError):
    pass


class CandleConflict(PersistenceError):
    pass


def _require(condition, reason="INVALID_DATABASE"):
    if not condition:
        raise CorruptState(reason)


def _hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _engine():
    root = Path(__file__).resolve().parents[1]
    # Storage upgrades use schema/format versions. Bind trading semantics rather
    # than storage source bytes so a schema-only migration can preserve accounts.
    paths = ("config.py", "data/models.py", "data/schema.py", "backtesting/costs.py", "risk/controls.py", "risk/stops.py",
             "risk/sizing.py", "risk/entry.py", "risk/audit.py", "risk/proposal.py",
             "strategies/base.py", "paper_trading/broker.py")
    return _hash(state.canonical({name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in paths}))


@dataclass(frozen=True, slots=True)
class Checkpoint:
    account_id: str
    revision: int
    chain: str


@dataclass(frozen=True, slots=True)
class Snapshot:
    checkpoint: Checkpoint
    state_json: str
    processed_candles: int
    symbol: str
    data_kind: str
    runtime_json: str | None = None

    @property
    def state(self):
        """Detached JSON values; modifying them cannot change an account."""
        return state.strict_json(self.state_json)

    @property
    def runtime(self):
        return state.strict_json(self.runtime_json) if self.runtime_json is not None else None


@dataclass(frozen=True, slots=True)
class Update:
    applied: bool
    snapshot: Snapshot


class PersistentPaperBroker:
    def _configure(self, path, settings, symbol, data_kind, allow_synthetic, timeout, expected_head=None):
        Settings(**{field.name: getattr(settings, field.name) for field in fields(Settings)})
        if (settings.mode != "paper" or settings.starting_capital != 2000
                or settings.risk_per_trade > Decimal("0.005") or settings.daily_loss_limit > Decimal("0.02")):
            raise ValueError("PAPER_ACCOUNT_REQUIRES_PHASE5_CONFIGURATION")
        if not isinstance(symbol, str) or not SYMBOL.fullmatch(symbol):
            raise ValueError("INVALID_ACCOUNT_SYMBOL")
        if data_kind not in ("historical", "synthetic") or (data_kind == "synthetic" and allow_synthetic is not True):
            raise ValueError("EXPLICIT_DATA_KIND_AND_SYNTHETIC_OPT_IN_REQUIRED")
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 <= timeout <= 30:
            raise ValueError("INVALID_SQLITE_TIMEOUT")
        if expected_head is not None and not isinstance(expected_head, Checkpoint):
            raise ValueError("INVALID_EXPECTED_CHECKPOINT")
        self._path = Path(path).resolve()
        self._settings, self._symbol, self._kind = settings, symbol, data_kind
        self._timeout, self._engine_hash = timeout, _engine()
        self._lock, self._busy, self._failed, self._closed = RLock(), False, False, False
        self._pinned = expected_head

    @classmethod
    def create(cls, path, settings, *, symbol, data_kind, allow_synthetic=False, timeout=1):
        account = cls.__new__(cls)
        account._configure(path, settings, symbol, data_kind, allow_synthetic, timeout)
        account._exclusive_file(account._path)
        try:
            with account._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                for sql in _SCHEMA_V1:
                    connection.execute(sql)
                connection.execute("ALTER TABLE checkpoints ADD COLUMN chain TEXT NOT NULL DEFAULT ''")
                connection.execute("ALTER TABLE head ADD COLUMN chain TEXT NOT NULL DEFAULT ''")
                connection.execute(f"PRAGMA application_id={APPLICATION_ID}")
                connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
                meta = {"account_id": str(uuid4()), "symbol": symbol, "data_kind": data_kind,
                        "settings": state.canonical(settings), "engine": account._engine_hash,
                        "created_at": datetime.now(timezone.utc).isoformat()}
                connection.executemany("INSERT INTO meta VALUES (?, ?)", sorted(meta.items()))
                payload = state._dump(PaperBroker(settings))
                digest = _hash(payload)
                chain = account._chain(meta, "0" * 64, 0, "create", digest)
                connection.execute("INSERT INTO checkpoints VALUES (0, 'create', ?, ?, ?)", (payload, digest, chain))
                connection.execute("INSERT INTO head VALUES (1, 0, ?, ?)", (digest, chain))
                account._read(connection)
                account._commit(connection)
            account.snapshot()
            return account
        except BaseException as exc:
            account._failed = True
            # Keep failed/partial files. Never silently reset or unlink an account.
            if isinstance(exc, (sqlite3.Error, OSError)):
                raise PersistenceError("ACCOUNT_CREATION_FAILED") from None
            raise

    @classmethod
    def open(cls, path, settings, *, symbol, data_kind, allow_synthetic=False, timeout=1, expected_head=None):
        account = cls.__new__(cls)
        account._configure(path, settings, symbol, data_kind, allow_synthetic, timeout, expected_head)
        account.snapshot()
        return account

    @staticmethod
    def _exclusive_file(path):
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(descriptor)

    def _connection(self):
        # mode=rw is essential: resume must never create a fresh zero-history DB.
        connection = sqlite3.connect(self._path.as_uri() + "?mode=rw", uri=True,
                                     timeout=self._timeout, isolation_level=None)
        try:
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA trusted_schema=OFF")
            _require(connection.execute("PRAGMA journal_mode").fetchone()[0] == "delete", "UNSUPPORTED_JOURNAL_MODE")
            return _ClosingConnection(connection)
        except BaseException:
            connection.close()
            raise

    @staticmethod
    def _commit(connection):
        connection.commit()

    @staticmethod
    def _chain(meta, previous, revision, operation, digest):
        return _hash(state.canonical([meta, previous, revision, operation, digest]))

    def _read(self, connection, *, allow_v1=False):
        _require(connection.execute("PRAGMA quick_check").fetchall() == [("ok",)], "SQLITE_INTEGRITY_FAILURE")
        _require(connection.execute("PRAGMA foreign_key_check").fetchall() == [], "FOREIGN_KEY_FAILURE")
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version not in (SCHEMA_VERSION, 3) and not (allow_v1 and version == 1):
            raise IncompatibleState("UNSUPPORTED_SCHEMA_VERSION")
        _require(connection.execute("PRAGMA application_id").fetchone()[0] == APPLICATION_ID, "WRONG_APPLICATION")
        objects = connection.execute("SELECT type, name FROM sqlite_master WHERE substr(name,1,7) != 'sqlite_'").fetchall()
        expected_columns = dict(_COLUMNS_V1)
        if version == 3:
            expected_columns["runtime"] = ("singleton", "payload", "digest")
        _require(set(objects) == {("table", name) for name in expected_columns}, "UNEXPECTED_DATABASE_OBJECTS")
        for name, expected in expected_columns.items():
            info = connection.execute(f"PRAGMA table_info({name})").fetchall()
            columns = tuple(row[1] for row in info)
            _require(columns == expected + (("chain",) if version >= 2 and name in ("head", "checkpoints") else ()),
                     "INCOMPATIBLE_TABLE_SCHEMA")
            primary = {"meta":"key", "checkpoints":"revision", "processed":"candle_id", "head":"singleton", "runtime":"singleton"}[name]
            for _, column, affinity, required, default, key in info:
                is_primary = column == primary
                _require(affinity == ("INTEGER" if column in ("revision","singleton") else "TEXT")
                         and required == int(not is_primary) and key == int(is_primary)
                         and default == ("''" if column == "chain" else None), "INCOMPATIBLE_COLUMN_CONSTRAINTS")
            unique = {tuple(item[0] for item in connection.execute("SELECT name FROM pragma_index_info(?) ORDER BY seqno", (row[1],)))
                      for row in connection.execute(f"PRAGMA index_list({name})") if row[2]}
            expected_unique = {("key",)} if name == "meta" else {("candle_id",),("revision",)} if name == "processed" else set()
            _require(unique == expected_unique, "INCOMPATIBLE_UNIQUE_CONSTRAINTS")
            foreign = {(row[2],row[3],row[4]) for row in connection.execute(f"PRAGMA foreign_key_list({name})")}
            _require(foreign == ({("checkpoints","revision","revision")} if name in ("head","processed") else set()),
                     "INCOMPATIBLE_FOREIGN_KEYS")
        meta_rows = connection.execute("SELECT key, value FROM meta").fetchall()
        meta = dict(meta_rows)
        _require(len(meta_rows) == len(meta) and set(meta) == _META_KEYS and all(type(item) is str for item in meta.values()),
                 "INVALID_ACCOUNT_METADATA")
        _require(str(UUID(meta["account_id"])) == meta["account_id"], "INVALID_ACCOUNT_ID")
        created = utc(meta["created_at"])
        _require(created.isoformat() == meta["created_at"] and created <= datetime.now(timezone.utc), "INVALID_CREATION_TIME")
        if (meta["settings"] != state.canonical(self._settings) or meta["symbol"] != self._symbol
                or meta["data_kind"] != self._kind or meta["engine"] != self._engine_hash):
            raise IncompatibleState("ACCOUNT_CONFIGURATION_OR_ENGINE_MISMATCH")
        processed_rows = connection.execute("SELECT candle_id, candle_json, revision FROM processed").fetchall()
        processed = {row[2]: row[:2] for row in processed_rows}
        _require(len(processed) == len(processed_rows), "DUPLICATE_PROCESSED_REVISION")
        rows = connection.execute("SELECT * FROM checkpoints ORDER BY revision").fetchall()
        _require(bool(rows), "MISSING_ACCOUNT_HISTORY")
        previous, chain, chains, seen, candles = None, "0" * 64, [], {}, {}
        for index, row in enumerate(rows):
            revision, operation, payload, digest = row[:4]
            _require(type(revision) is int and revision == index and type(payload) is str
                     and type(digest) is str and _hash(payload) == digest, "CHECKPOINT_CHECKSUM_OR_SEQUENCE")
            _require(operation == "create" if index == 0 else operation in ("bar", "finish", "emergency"), "INVALID_OPERATION")
            broker = state._load(payload, self._settings)
            data = state.strict_json(payload)
            _require(state.canonical(data) == payload, "NONCANONICAL_CHECKPOINT")
            if previous is None:
                _require(payload == state._dump(PaperBroker(self._settings)), "INVALID_GENESIS")
            else:
                state._transition(previous, data, operation)
            if operation == "bar":
                _require(broker.last_candle is not None and index in processed, "MISSING_PROCESSED_CANDLE")
                candle_id, candle_json = processed[index]
                _require(candle_id == broker.last_bar.isoformat() and candle_json == state.canonical(broker.last_candle)
                         and candle_id not in seen, "PROCESSED_CANDLE_MISMATCH")
                seen[candle_id] = candle_json
                candles[broker.last_bar] = broker.last_candle
            else:
                _require(index not in processed, "UNEXPECTED_PROCESSED_CANDLE")
            _require(broker.exposed_bars <= len(seen))
            for record in broker.risk_audit.records:
                if record.approved:
                    _require(record.symbol == self._symbol and record.data_kind == self._kind, "AUDIT_MARKET_MISMATCH")
            for trade in broker.trades:
                _require(trade.opened_at in candles and trade.entry_reference == candles[trade.opened_at].open,
                         "ENTRY_CANDLE_MISMATCH")
                at_close = trade.reason in ("emergency_shutdown", "end_of_data")
                exit_candle = candles.get(trade.closed_at - timedelta(minutes=15) if at_close else trade.closed_at)
                _require(exit_candle is not None and exit_candle.low <= trade.exit_reference <= exit_candle.high,
                         "EXIT_CANDLE_MISMATCH")
                if at_close:
                    _require(trade.exit_reference == exit_candle.close, "EXIT_CLOSE_MISMATCH")
                elif trade.reason == "strategy_exit":
                    _require(trade.exit_reference == exit_candle.open, "EXIT_OPEN_MISMATCH")
            if broker.position:
                _require(broker.position.opened_at in candles
                         and broker.position.entry_reference == candles[broker.position.opened_at].open, "POSITION_CANDLE_MISMATCH")
            chain = self._chain(meta, chain, revision, operation, digest)
            if version >= 2:
                _require(row[4] == chain, "CHECKPOINT_CHAIN_MISMATCH")
            chains.append(chain)
            previous = data
        _require(len(seen) == len(processed), "ORPHANED_PROCESSED_CANDLE")
        heads = connection.execute("SELECT * FROM head").fetchall()
        expected = (1, rows[-1][0], rows[-1][3]) + ((chain,) if version >= 2 else ())
        _require(heads == [expected], "HEAD_ANCHOR_MISMATCH")
        checkpoint = Checkpoint(meta["account_id"], rows[-1][0], chain)
        if self._pinned is not None:
            _require(self._pinned.account_id == checkpoint.account_id
                     and 0 <= self._pinned.revision < len(chains)
                     and chains[self._pinned.revision] == self._pinned.chain, "ACCOUNT_REPLACED_OR_ROLLED_BACK")
        runtime_json = None
        if version == 3:
            runtime_rows = connection.execute("SELECT * FROM runtime").fetchall()
            _require(len(runtime_rows) == 1 and runtime_rows[0][0] == 1, "MISSING_SESSION_STATE")
            _, runtime_json, digest = runtime_rows[0]
            _require(type(runtime_json) is str and _hash(runtime_json) == digest, "SESSION_CHECKSUM_FAILURE")
            _require(state.canonical(state.strict_json(runtime_json)) == runtime_json, "NONCANONICAL_SESSION_STATE")
            from paper_trading.session import validate_runtime
            validate_runtime(state.strict_json(runtime_json), broker, self._settings)
        return meta, broker, Snapshot(checkpoint, rows[-1][2], len(seen), meta["symbol"], meta["data_kind"], runtime_json), seen, chains, version

    def _append(self, connection, meta, snapshot, payload, operation, candle):
        revision = snapshot.checkpoint.revision + 1
        digest = _hash(payload)
        chain = self._chain(meta, snapshot.checkpoint.chain, revision, operation, digest)
        connection.execute("INSERT INTO checkpoints VALUES (?, ?, ?, ?, ?)", (revision, operation, payload, digest, chain))
        if operation == "bar":
            connection.execute("INSERT INTO processed VALUES (?, ?, ?)", (candle.timestamp.isoformat(), state.canonical(candle), revision))
        connection.execute("UPDATE head SET revision=?, digest=?, chain=? WHERE singleton=1", (revision, digest, chain))

    def _run(self, operation=None, candle=None, signal=Signal.HOLD, entry=None):
        with self._lock:
            if self._closed or self._failed:
                raise PersistenceError("HANDLE_CLOSED_OR_FAILED_REOPEN_REQUIRED")
            if self._busy:
                self._failed = True
                raise PersistenceError("REENTRANT_PERSISTENCE_OPERATION")
            self._busy = True
            try:
                with self._connection() as connection:
                    connection.execute("BEGIN IMMEDIATE" if operation else "BEGIN")
                    meta, broker, snapshot, processed, _, _ = self._read(connection)
                    if snapshot.runtime is not None and operation in ("bar", "finish"):
                        raise PersistenceError("MANAGED_ACCOUNT_REQUIRES_SESSION_INTERFACE")
                    if operation == "bar":
                        # Rebuild the public Candle to reject damaged instances.
                        checked = Candle(candle.timestamp, candle.open, candle.high, candle.low, candle.close, candle.volume)
                        if checked.timestamp.isoformat() in processed:
                            stored = state._decode(state.strict_json(processed[checked.timestamp.isoformat()]), Candle)
                            if stored != checked:
                                raise CandleConflict("CONFLICTING_PROCESSED_CANDLE")
                            self._pinned = snapshot.checkpoint
                            return Update(False, snapshot)
                        if isinstance(entry, EntryProposal) and isinstance(entry.market, MarketContext):
                            if (entry.market.symbol != self._symbol or entry.market.kind != self._kind):
                                raise ValueError("PERSISTENT_ACCOUNT_MARKET_MISMATCH")
                        broker.process_bar(checked, signal, entry=entry)
                        candle = checked
                    elif operation == "emergency":
                        broker.emergency_shutdown()
                        if snapshot.runtime is not None:
                            from paper_trading.session import stop_runtime, write_runtime
                            runtime = snapshot.runtime
                            stop_runtime(runtime, datetime.now(timezone.utc))
                            write_runtime(connection, runtime)
                    elif operation == "finish":
                        if candle != broker.last_candle:
                            raise ValueError("FINISH_REQUIRES_IDENTICAL_LAST_CANDLE")
                        broker.finish(candle)
                    if self._failed:
                        raise PersistenceError("REENTRANT_OPERATION_ABORTED_COMMIT")
                    payload = state._dump(broker)
                    applied = operation is not None and payload != snapshot.state_json
                    if applied:
                        self._append(connection, meta, snapshot, payload, operation, candle)
                        _, _, snapshot, _, _, _ = self._read(connection)
                        self._commit(connection)
                    self._pinned = snapshot.checkpoint
                    return Update(applied, snapshot) if operation else snapshot
            except BaseException as exc:
                self._failed = True
                if isinstance(exc, sqlite3.Error):
                    raise PersistenceError("SQLITE_OPERATION_FAILED_REOPEN_REQUIRED") from None
                if isinstance(exc, (ValueError, TypeError, ArithmeticError, AttributeError)):
                    raise CorruptState("STATE_OR_REQUEST_VALIDATION_FAILED") from None
                raise
            finally:
                self._busy = False

    def snapshot(self):
        return self._run()

    def process_bar(self, candle, signal=Signal.HOLD, *, entry=None):
        return self._run("bar", candle, signal, entry)

    def emergency_shutdown(self):
        return self._run("emergency")

    def finish(self, candle):
        return self._run("finish", candle)

    def close(self):
        with self._lock:
            if self._busy:
                self._failed = True
                raise PersistenceError("CLOSE_DURING_OPERATION")
            self._closed = True

    @classmethod
    def migrate(cls, path, settings, *, symbol, data_kind, allow_synthetic=False, timeout=1):
        account = cls.__new__(cls)
        account._configure(path, settings, symbol, data_kind, allow_synthetic, timeout)
        try:
            with account._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                _, _, snapshot, _, chains, version = account._read(connection, allow_v1=True)
                if version == 1:
                    connection.execute("ALTER TABLE checkpoints ADD COLUMN chain TEXT NOT NULL DEFAULT ''")
                    connection.execute("ALTER TABLE head ADD COLUMN chain TEXT NOT NULL DEFAULT ''")
                    connection.executemany("UPDATE checkpoints SET chain=? WHERE revision=?", ((chain, index) for index, chain in enumerate(chains)))
                    connection.execute("UPDATE head SET chain=?", (snapshot.checkpoint.chain,))
                    connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
                    account._read(connection)
                    account._commit(connection)
            account.snapshot()
            return account
        except BaseException as exc:
            account._failed = True
            if isinstance(exc, (sqlite3.Error, ValueError, TypeError, ArithmeticError)):
                raise CorruptState("MIGRATION_FAILED_NO_RESET") from None
            raise

    def backup(self, destination):
        """SQLite online backup under a stable source read transaction; no overwrite."""
        destination = Path(destination).resolve()
        with self._lock:
            if self._failed or self._closed or self._busy:
                raise PersistenceError("HANDLE_UNAVAILABLE_FOR_BACKUP")
            self._busy = True
            try:
                with self._connection() as source:
                    source.execute("BEGIN")
                    _, _, expected, _, _, _ = self._read(source)
                    self._exclusive_file(destination)
                    with _ClosingConnection(sqlite3.connect(destination, isolation_level=None)) as target:
                        target.execute("PRAGMA synchronous=FULL")
                        source.backup(target)
                        _, _, copied, _, _, _ = self._read(target)
                        _require(copied.checkpoint == expected.checkpoint, "BACKUP_CHECKPOINT_MISMATCH")
                    self._pinned = expected.checkpoint
                    return expected.checkpoint
            except BaseException as exc:
                self._failed = True
                if isinstance(exc, (sqlite3.Error, OSError)):
                    raise PersistenceError("BACKUP_FAILED_NO_OVERWRITE") from None
                raise
            finally:
                self._busy = False

    @classmethod
    def restore_backup(cls, source, destination, settings, *, expected_head, **identity):
        if not isinstance(expected_head, Checkpoint):
            raise ValueError("LAST_KNOWN_COMMITTED_CHECKPOINT_REQUIRED")
        backup = cls.open(source, settings, expected_head=expected_head, **identity)
        _require(backup.snapshot().checkpoint == expected_head, "BACKUP_IS_NOT_EXPECTED_LAST_STATE")
        backup.backup(destination)
        backup.close()
        return cls.open(destination, settings, expected_head=expected_head, **identity)


class _ClosingConnection:
    """sqlite3.Connection's built-in context manager does not close the handle."""
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self.connection

    def __exit__(self, *exc):
        try:
            if self.connection.in_transaction:
                self.connection.rollback()
        finally:
            self.connection.close()
