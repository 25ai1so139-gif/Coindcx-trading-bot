"""Durable MOCK-ONLY order journal, independent of the paper account database.

No network, signing, credentials or paper-account mutation. Internal mock account
projections assume quote-denominated fees; that is not a verified CoinDCX balance
or fee-currency contract. Unknown results block new drafts, never trigger resends.
"""

import hashlib
import json
import os
import re
import sqlite3
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from threading import RLock
from uuid import UUID, uuid4

from backtesting.costs import fixed_decimal
from config import Settings, decimal_value
from data.schema import SYMBOL, epoch_ms, milliseconds, utc
from exchange.contracts import ExchangeBlocked, TERMINAL, WIRE_STATUSES, require
from exchange.instruments import Instrument
from exchange.orders import preview_entry
from paper_trading.state import canonical, strict_json, _decode
from risk.audit import RiskAudit, RiskRecord
from risk.context import VerificationAccount
from risk.controls import RiskControls
from risk.sizing import PositionPlan

APP_ID = 0x43445852
FAILURES = {"TIMEOUT_AFTER_REQUEST", "AUTHENTICATION_OR_PERMISSION_ERROR", "RATE_LIMITED_RECONCILE_BEFORE_RETRY"}
FAULTS = {"ORDER_MISMATCH", "STATUS_REGRESSION", "ACCOUNT_MISMATCH", "EXECUTION_COST_OVERRUN", "UNEXPECTED_ORDER"}
UNKNOWN = FAILURES | {"UNKNOWN_ORDER_STATUS", "INVALID_STATUS_RESPONSE", "UNVERIFIED_PARTIAL_CANCELLATION"}
WIRE_FIELDS = {"id", "client_order_id", "market", "side", "order_type", "status", "total_quantity",
               "remaining_quantity", "avg_price", "price_per_unit", "fee_amount", "created_at", "updated_at"}


class JournalError(RuntimeError):
    pass


def _hash(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _fingerprint():
    root = Path(__file__).resolve().parents[1]
    names = ("exchange/contracts.py", "exchange/instruments.py", "exchange/orders.py", "exchange/reconciliation.py",
             "config.py", "risk/entry.py", "risk/controls.py", "risk/sizing.py", "risk/proposal.py", "risk/audit.py")
    return _hash(canonical({n: hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names}))


def _wire_request(value):
    # Nested wire JSON may have decimal numbers; never decode through floats.
    def pairs(items):
        result = {}
        for key, item in items:
            require(key not in result, "DUPLICATE_REQUEST_FIELD")
            result[key] = item
        return result
    def invalid(_):
        raise ExchangeBlocked("INVALID_REQUEST_NUMBER")
    return json.loads(value, parse_float=Decimal, parse_constant=invalid, object_pairs_hook=pairs)


def _number(value):
    try:
        number = decimal_value(value, "reported number")
        require(number >= 0 and len(number.as_tuple().digits) <= 32 and abs(number.as_tuple().exponent) <= 32,
                "INVALID_STATUS_RESPONSE")
        return number
    except (ValueError, TypeError, ArithmeticError):
        raise ExchangeBlocked("INVALID_STATUS_RESPONSE") from None


def normalize_status(raw, request, at):
    """Whitelist documented spot fields, ignoring arbitrary provider extras."""
    require(isinstance(raw, dict) and WIRE_FIELDS <= raw.keys(), "INVALID_STATUS_RESPONSE")
    require(isinstance(raw["status"], str) and raw["status"] in WIRE_STATUSES, "UNKNOWN_ORDER_STATUS")
    require(raw["status"] != "partially_cancelled", "UNVERIFIED_PARTIAL_CANCELLATION")
    identifier = raw["id"]
    require(type(identifier) in (str, int) and re.fullmatch(r"[1-9][0-9]{0,29}", str(identifier)), "INVALID_STATUS_RESPONSE")
    value = {name: raw[name] for name in WIRE_FIELDS}
    value["id"] = str(identifier)
    for name in ("client_order_id", "market", "side", "order_type"):
        require(value[name] == request[name], "ORDER_MISMATCH")
    for name in ("total_quantity", "remaining_quantity", "avg_price", "price_per_unit", "fee_amount"):
        value[name] = _number(value[name])
    require(value["total_quantity"] == request["total_quantity"] and value["price_per_unit"] == request["price_per_unit"], "ORDER_MISMATCH")
    for name in ("created_at", "updated_at"):
        require(type(value[name]) is int and 0 < value[name] <= epoch_ms(utc(at)), "INVALID_STATUS_RESPONSE")
    require(request["timestamp"] <= value["created_at"] <= value["updated_at"], "INVALID_STATUS_RESPONSE")
    total, remaining, average = value["total_quantity"], value["remaining_quantity"], value["avg_price"]
    require(0 <= remaining <= total, "INVALID_STATUS_RESPONSE")
    filled = total - remaining
    if value["status"] in {"init", "open", "rejected", "cancelled"}:
        # Cancellation remainder semantics are not inferred for filled orders.
        require(filled == 0 and average == 0 and value["fee_amount"] == 0, "INVALID_STATUS_RESPONSE")
    else:
        require(average > 0 and ((value["status"] == "filled" and filled == total)
                    or (value["status"] == "partially_filled" and 0 < filled < total)), "INVALID_STATUS_RESPONSE")
        require(average <= request["price_per_unit"], "ORDER_MISMATCH")
    return strict_json(canonical(value))


@dataclass(frozen=True)
class MockAccountReport:
    """Local synthetic model fields, NOT fields of a CoinDCX API response.

    cash_total includes locked INR and assumes fee_amount is paid in INR. No
    leverage, exit fills, funding or private balances are simulated here.
    """
    cash_total: Decimal
    asset_quantity: Decimal
    open_order_ids: tuple[str, ...]

    def __post_init__(self):
        object.__setattr__(self, "cash_total", _number(self.cash_total))
        object.__setattr__(self, "asset_quantity", _number(self.asset_quantity))
        require(type(self.open_order_ids) is tuple and len(set(self.open_order_ids)) == len(self.open_order_ids)
                and all(isinstance(i, str) and re.fullmatch(r"[1-9][0-9]{0,29}", i) for i in self.open_order_ids), "INVALID_MOCK_ACCOUNT_REPORT")


@dataclass(frozen=True)
class JournalSnapshot:
    revision: int
    chain: str
    state_json: str

    @property
    def state(self):
        return strict_json(self.state_json)


def expected_mock_account(state):
    cash, quantity, identifiers = Decimal(2000), Decimal(0), []
    for order in state["orders"].values():
        report = order["report"]
        if report is not None:
            filled = Decimal(report["total_quantity"]) - Decimal(report["remaining_quantity"])
            cash -= filled * Decimal(report["avg_price"]) + Decimal(report["fee_amount"])
            quantity += filled
            if report["status"] not in TERMINAL:
                identifiers.append(report["id"])
    return MockAccountReport(cash, quantity, tuple(sorted(identifiers)))


def blocked(state):
    return (state["emergency_halted"] or bool(state["faults"]) or not state["account_reconciled"]
            or any(o["local"] != "OBSERVED" or o["report"]["status"] not in TERMINAL for o in state["orders"].values())
            or known_position_quantity(state) > 0)


def known_position_quantity(state):
    return sum((Decimal(o["report"]["total_quantity"]) - Decimal(o["report"]["remaining_quantity"])
                for o in state["orders"].values() if o["report"] is not None), Decimal(0))


@fixed_decimal
def _reduce(previous, event, settings, symbol, fingerprint):
    require(type(event) is dict and isinstance(event.get("type"), str), "INVALID_JOURNAL_EVENT")
    at = utc(event["at"])
    require(at.isoformat() == event["at"] and at <= datetime.now(timezone.utc), "INVALID_JOURNAL_TIME")
    if previous is None:
        require(set(event) == {"type", "at", "settings", "symbol", "engine", "account_id", "label"}
                and event["type"] == "create" and event["settings"] == strict_json(canonical(settings))
                and event["symbol"] == symbol and event["engine"] == fingerprint and event["label"] == "SYNTHETIC_MOCK_ONLY"
                and str(UUID(event["account_id"])) == event["account_id"], "INCOMPATIBLE_MOCK_JOURNAL")
        return {"label": "SYNTHETIC_MOCK_ONLY", "at": event["at"], "orders": {}, "faults": [],
                "account_reconciled": True, "emergency_halted": False, "reviews": []}
    value = strict_json(canonical(previous))
    require(at >= utc(value["at"]), "JOURNAL_CLOCK_MOVED_BACKWARDS")
    value["at"] = event["at"]
    kind = event["type"]
    if kind == "review":
        require(set(event) == {"type", "at", "record"}, "INVALID_REVIEW_EVENT")
        record = _decode(event["record"], RiskRecord)
        require(not record.approved, "INVALID_REJECTION_RECORD")
        value["reviews"].append(event["record"])
    elif kind == "prepare":
        require(set(event) == {"type", "at", "client_id", "request", "record", "plan", "instrument"}, "INVALID_PREPARE_EVENT")
        require(not blocked(value), "UNRESOLVED_OR_OPEN_ORDER")
        request = _wire_request(event["request"])
        require(set(request) == {"side", "order_type", "market", "price_per_unit", "total_quantity", "timestamp", "client_order_id"}, "INVALID_REQUEST_FIELDS")
        identifier = event["client_id"]
        require(isinstance(identifier, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", identifier)
                and identifier == request["client_order_id"] and identifier not in value["orders"], "DUPLICATE_CLIENT_ORDER_ID")
        record = _decode(event["record"], RiskRecord)
        plan = _decode(event["plan"], PositionPlan)
        instrument = _decode(event["instrument"], Instrument)
        require(record.approved and record.reason == "APPROVED" and record.symbol == symbol and record.data_kind == "synthetic"
                and instrument.kind == "synthetic_fixture" and instrument.pair == symbol, "INVALID_MOCK_APPROVAL")
        require(record.margin == plan.margin == plan.notional and record.notional == plan.notional
                and record.leverage == 1 and record.entry_fill == plan.entry_price
                and record.planned_risk == plan.planned_stop_risk
                and 0 < plan.planned_stop_risk <= min(Decimal(20), settings.max_planned_risk, record.permitted_risk)
                and not record.daily_halted and not record.drawdown_halted and not record.emergency_halted
                and 0 <= record.entries_today < settings.max_trades_per_day, "INVALID_MOCK_RISK_PLAN")
        stop_fill = plan.stop_price * (1 - settings.slippage_rate)
        loss = plan.quantity * (plan.entry_price - stop_fill) + plan.entry_fee + plan.quantity * stop_fill * settings.fee_rate
        require(record.equity == settings.starting_capital and record.permitted_risk <= min(record.equity * settings.risk_per_trade, settings.max_planned_risk, Decimal(20))
                and plan.entry_fee == plan.notional * settings.fee_rate
                and plan.margin <= min(settings.margin_amount, record.equity * settings.max_margin_fraction)
                and plan.margin + plan.entry_fee <= record.equity
                and 0 < plan.stop_price == plan.entry_price * (1 - settings.stop_loss_fraction) < plan.entry_price
                and record.stop_price == plan.stop_price and record.estimated_stop_fill == stop_fill
                and 0 < loss <= record.permitted_risk and abs(loss - plan.planned_stop_risk) <= Decimal('1e-20'),
                "INCONSISTENT_MOCK_RISK_COSTS")
        require(request["side"] == "buy" and request["order_type"] == "limit_order" and request["market"] == instrument.market
                and request["timestamp"] == epoch_ms(at) and request["total_quantity"] == plan.quantity
                and request["price_per_unit"] == plan.entry_price and plan.notional == plan.quantity * plan.entry_price,
                "REQUEST_PLAN_MISMATCH")
        instrument.validate_size(plan.quantity, plan.entry_price)
        value["orders"][identifier] = {"request": event["request"], "plan": event["plan"], "record": event["record"],
                                      "local": "PREPARED", "report": None, "reason": "PREPARED_NOT_SENT"}
        value["account_reconciled"] = False
    elif kind in ("status", "unknown", "fault"):
        expected = {"type", "at", "client_id", "report"} if kind == "status" else {"type", "at", "client_id", "reason"}
        require(set(event) == expected and event["client_id"] in value["orders"], "UNKNOWN_LOCAL_ORDER")
        order = value["orders"][event["client_id"]]
        if kind == "status":
            report = normalize_status(event["report"], _wire_request(order["request"]), at)
            require(all(other is order or other["report"] is None or other["report"]["id"] != report["id"]
                        for other in value["orders"].values()), "ORDER_MISMATCH")
            prior = order["report"]
            if prior is not None:
                require(report["id"] == prior["id"] and report["created_at"] == prior["created_at"], "ORDER_MISMATCH")
                require(report["updated_at"] >= prior["updated_at"]
                        and Decimal(report["remaining_quantity"]) <= Decimal(prior["remaining_quantity"])
                        and Decimal(report["fee_amount"]) >= Decimal(prior["fee_amount"]), "STATUS_REGRESSION")
                old_filled = Decimal(prior["total_quantity"]) - Decimal(prior["remaining_quantity"])
                new_filled = Decimal(report["total_quantity"]) - Decimal(report["remaining_quantity"])
                require(new_filled * Decimal(report["avg_price"]) >= old_filled * Decimal(prior["avg_price"])
                        and (new_filled != old_filled or report["avg_price"] == prior["avg_price"]), "STATUS_REGRESSION")
                if report["updated_at"] == prior["updated_at"] or prior["status"] in TERMINAL:
                    require(report == prior, "STATUS_REGRESSION")
                if prior["status"] == "partially_filled":
                    require(report["status"] in ("partially_filled", "filled"), "STATUS_REGRESSION")
            order.update(local="OBSERVED", report=report, reason="MOCK_STATUS_OBSERVED")
            spend = (Decimal(report["total_quantity"]) - Decimal(report["remaining_quantity"])) * Decimal(report["avg_price"]) + Decimal(report["fee_amount"])
            if spend > Decimal(order["plan"]["notional"]) + Decimal(order["plan"]["entry_fee"]):
                value["faults"] = sorted(set(value["faults"]) | {"EXECUTION_COST_OVERRUN"})
        else:
            require(event["reason"] in (UNKNOWN if kind == "unknown" else FAULTS), "INVALID_FAILURE_CODE")
            order.update(local="UNKNOWN", reason=event["reason"])
            if kind == "fault":
                value["faults"] = sorted(set(value["faults"]) | {event["reason"]})
        value["account_reconciled"] = False
    elif kind == "global_fault":
        require(set(event) == {"type", "at", "reason"} and event["reason"] in {"UNEXPECTED_ORDER", "ACCOUNT_MISMATCH"},
                "INVALID_GLOBAL_MOCK_FAULT")
        value["faults"] = sorted(set(value["faults"]) | {event["reason"]})
        value["account_reconciled"] = False
    elif kind == "account":
        require(set(event) == {"type", "at", "report"}, "INVALID_MOCK_ACCOUNT_EVENT")
        raw = event["report"]
        require(type(raw) is dict and set(raw) == {"cash_total", "asset_quantity", "open_order_ids"}
                and type(raw["open_order_ids"]) is list, "INVALID_MOCK_ACCOUNT_REPORT")
        report = MockAccountReport(raw["cash_total"], raw["asset_quantity"], tuple(raw["open_order_ids"]))
        unresolved = any(order["local"] != "OBSERVED" for order in value["orders"].values())
        value["account_reconciled"] = not unresolved and report == expected_mock_account(value)
        if not unresolved and not value["account_reconciled"]:
            value["faults"] = sorted(set(value["faults"]) | {"ACCOUNT_MISMATCH"})
    elif kind == "emergency":
        require(set(event) == {"type", "at"}, "INVALID_EMERGENCY_EVENT")
        value["emergency_halted"] = True
    else:
        raise ExchangeBlocked("UNKNOWN_JOURNAL_EVENT")
    return value


class MockOrderJournal:
    def _configure(self, path, settings, symbol, allow_mock):
        require(allow_mock is True and settings.mode == "paper" and settings.starting_capital == 2000
                and settings.risk_per_trade <= Decimal("0.005") and settings.daily_loss_limit <= Decimal("0.02"), "EXPLICIT_MOCK_PHASE5_PROFILE_REQUIRED")
        Settings(**asdict(settings))
        require(isinstance(symbol, str) and SYMBOL.fullmatch(symbol), "INVALID_JOURNAL_SYMBOL")
        self.path, self.settings, self.symbol = Path(path).resolve(), settings, symbol
        self._fingerprint, self._lock, self._failed, self._busy, self._closed = _fingerprint(), RLock(), False, False, False
        self._pinned = None

    @classmethod
    def create(cls, path, settings, *, symbol, allow_mock=False, at=None):
        journal = cls.__new__(cls)
        journal._configure(path, settings, symbol, allow_mock)
        journal.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(journal.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(descriptor)
        event = dict(type="create", at=utc(at or datetime.now(timezone.utc)).isoformat(),
                     settings=strict_json(canonical(settings)), symbol=symbol, engine=journal._fingerprint,
                     account_id=str(uuid4()), label="SYNTHETIC_MOCK_ONLY")
        try:
            with journal._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute("CREATE TABLE events (revision INTEGER PRIMARY KEY, payload TEXT NOT NULL, digest TEXT NOT NULL, chain TEXT NOT NULL)")
                connection.execute("CREATE TABLE head (singleton INTEGER PRIMARY KEY CHECK(singleton=1), revision INTEGER NOT NULL REFERENCES events(revision), chain TEXT NOT NULL)")
                connection.execute(f"PRAGMA application_id={APP_ID}")
                connection.execute("PRAGMA user_version=1")
                payload = canonical(event)
                digest = _hash(payload)
                chain = _hash(canonical(["0" * 64, 0, digest]))
                connection.execute("INSERT INTO events VALUES (0,?,?,?)", (payload, digest, chain))
                connection.execute("INSERT INTO head VALUES (1,0,?)", (chain,))
                journal._read(connection)
                journal._commit(connection)
            journal.snapshot()
            return journal
        except BaseException:
            journal._failed = True
            raise JournalError("MOCK_JOURNAL_CREATION_FAILED_NO_RESET") from None

    @classmethod
    def open(cls, path, settings, *, symbol, allow_mock=False, expected_head=None):
        journal = cls.__new__(cls)
        journal._configure(path, settings, symbol, allow_mock)
        if expected_head is not None:
            require(isinstance(expected_head, JournalSnapshot), "TRUSTED_MOCK_CHECKPOINT_REQUIRED")
            journal._pinned = (expected_head.revision, expected_head.chain)
        journal.snapshot()
        return journal

    @contextmanager
    def _connection(self):
        connection = sqlite3.connect(self.path.as_uri() + "?mode=rw", uri=True, timeout=1, isolation_level=None)
        try:
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA trusted_schema=OFF")
            require(connection.execute("PRAGMA journal_mode").fetchone()[0] == "delete", "UNSUPPORTED_JOURNAL_MODE")
            yield connection
        finally:
            if connection.in_transaction:
                connection.rollback()
            connection.close()

    @staticmethod
    def _commit(connection):
        connection.commit()

    def _read(self, connection):
        require(connection.execute("PRAGMA quick_check").fetchall() == [("ok",)] and connection.execute("PRAGMA foreign_key_check").fetchall() == [], "CORRUPT_MOCK_JOURNAL")
        require(connection.execute("PRAGMA application_id").fetchone()[0] == APP_ID
                and connection.execute("PRAGMA user_version").fetchone()[0] == 1, "INCOMPATIBLE_MOCK_JOURNAL")
        objects = connection.execute("SELECT type,name FROM sqlite_master WHERE substr(name,1,7) != 'sqlite_'").fetchall()
        require(set(objects) == {("table", "events"), ("table", "head")}, "INCOMPATIBLE_MOCK_SCHEMA")
        for table, expected in (("events", ("revision", "payload", "digest", "chain")), ("head", ("singleton", "revision", "chain"))):
            columns = connection.execute(f"PRAGMA table_info({table})").fetchall()
            require(tuple(row[1] for row in columns) == expected, "INCOMPATIBLE_MOCK_SCHEMA")
            for index, name, affinity, not_null, default, primary in columns:
                require(affinity == ("INTEGER" if name in ("revision", "singleton") else "TEXT")
                        and not_null == int(index != 0) and primary == int(index == 0) and default is None, "INCOMPATIBLE_MOCK_SCHEMA")
            foreign = {(row[2], row[3], row[4]) for row in connection.execute(f"PRAGMA foreign_key_list({table})")}
            require(foreign == ({("events", "revision", "revision")} if table == "head" else set()), "INCOMPATIBLE_MOCK_SCHEMA")
        rows = connection.execute("SELECT * FROM events ORDER BY revision").fetchall()
        require(bool(rows), "MISSING_MOCK_HISTORY")
        value, chain, chains = None, "0" * 64, []
        for index, (revision, payload, digest, stored_chain) in enumerate(rows):
            require(type(revision) is int and revision == index and _hash(payload) == digest, "CORRUPT_MOCK_SEQUENCE")
            chain = _hash(canonical([chain, revision, digest]))
            require(chain == stored_chain, "CORRUPT_MOCK_CHAIN")
            event = strict_json(payload)
            require(canonical(event) == payload, "NONCANONICAL_MOCK_EVENT")
            value = _reduce(value, event, self.settings, self.symbol, self._fingerprint)
            chains.append(chain)
        require(connection.execute("SELECT * FROM head").fetchall() == [(1, rows[-1][0], chain)], "MOCK_HEAD_MISMATCH")
        if self._pinned is not None:
            require(self._pinned[0] < len(chains) and chains[self._pinned[0]] == self._pinned[1], "MOCK_JOURNAL_ROLLED_BACK")
        return JournalSnapshot(rows[-1][0], chain, canonical(value))

    @fixed_decimal
    def _run(self, action=None):
        with self._lock:
            if self._closed or self._failed or self._busy:
                self._failed = True
                raise JournalError("MOCK_HANDLE_UNAVAILABLE_REOPEN_REQUIRED")
            self._busy = True
            try:
                with self._connection() as connection:
                    connection.execute("BEGIN IMMEDIATE" if action else "BEGIN")
                    snapshot = self._read(connection)
                    if action:
                        event, result = action(snapshot.state)
                        if self._failed:
                            raise JournalError("REENTRANT_MOCK_OPERATION")
                        if event is not None:
                            _reduce(snapshot.state, strict_json(canonical(event)), self.settings, self.symbol, self._fingerprint)
                            revision, payload = snapshot.revision + 1, canonical(event)
                            digest = _hash(payload)
                            chain = _hash(canonical([snapshot.chain, revision, digest]))
                            connection.execute("INSERT INTO events VALUES (?,?,?,?)", (revision, payload, digest, chain))
                            connection.execute("UPDATE head SET revision=?,chain=?", (revision, chain))
                            snapshot = self._read(connection)
                            self._commit(connection)
                    self._pinned = (snapshot.revision, snapshot.chain)
                    return result if action else snapshot
            except BaseException:
                self._failed = True
                raise JournalError("MOCK_STATE_OR_OPERATION_FAILED_REOPEN_REQUIRED") from None
            finally:
                self._busy = False

    def snapshot(self):
        return self._run()

    def close(self):
        with self._lock:
            if self._busy:
                self._failed = True
                raise JournalError("CLOSE_DURING_MOCK_OPERATION")
            self._closed = True

    def prepare(self, client_id, account, proposal, instrument, *, at, audit):
        def action(value):
            # This journal has a fixed synthetic INR2,000 baseline and no exit
            # or deposit model. Do not import unexplained gains/other accounts.
            ready = (isinstance(client_id, str) and not blocked(value) and client_id not in value["orders"]
                     and isinstance(account, VerificationAccount) and account.kind == "synthetic"
                     and account.equity == self.settings.starting_capital)
            reviewed = account
            if isinstance(account, VerificationAccount) and isinstance(account.controls, RiskControls):
                controls = deepcopy(account.controls)
                controls.emergency_halted |= value["emergency_halted"]
                reviewed = replace(account, controls=controls, has_open_position=account.has_open_position
                                   or known_position_quantity(value) > 0)
            result = preview_entry(self.settings, reviewed, proposal, instrument, at=at,
                                   client_order_id=client_id, audit=audit, execution_ready=ready)
            if result.approved and (result.data_kind != "synthetic" or proposal.market.symbol != self.symbol):
                record = audit.record(at=at, approved=False, reason="MOCK_JOURNAL_REQUIRES_BOUND_SYNTHETIC_MARKET")
                result = replace(result, approved=False, reason=record.reason, request_json=None, plan=None, risk_record=record)
            if not result.approved:
                return dict(type="review", at=utc(at).isoformat(), record=asdict(result.risk_record)), result
            return dict(type="prepare", at=utc(at).isoformat(), client_id=client_id, request=result.request_json,
                        record=asdict(result.risk_record), plan=asdict(result.plan), instrument=asdict(instrument)), result
        return self._run(action)

    def record_mock_status(self, client_id, raw, *, at):
        def action(value):
            if not isinstance(client_id, str) or client_id not in value["orders"]:
                return dict(type="global_fault", at=utc(at).isoformat(), reason="UNEXPECTED_ORDER"), None
            order = value["orders"][client_id]
            try:
                report = normalize_status(raw, _wire_request(order["request"]), at)
                if order["local"] == "OBSERVED" and report == order["report"]:
                    return None, None
                event = dict(type="status", at=utc(at).isoformat(), client_id=client_id, report=report)
                _reduce(value, strict_json(canonical(event)), self.settings, self.symbol, self._fingerprint)
            except ExchangeBlocked as exc:
                code = str(exc)
                event = dict(type="fault" if code in FAULTS else "unknown", at=utc(at).isoformat(),
                             client_id=client_id, reason=code if code in FAULTS | UNKNOWN else "INVALID_STATUS_RESPONSE")
            return event, None
        self._run(action)
        return self.snapshot()

    def record_mock_failure(self, client_id, reason, *, at):
        require(reason in FAILURES, "INVALID_MOCK_FAILURE_CODE")
        def action(value):
            if not isinstance(client_id, str) or client_id not in value["orders"]:
                return dict(type="global_fault", at=utc(at).isoformat(), reason="UNEXPECTED_ORDER"), None
            return dict(type="unknown", at=utc(at).isoformat(), client_id=client_id, reason=reason), None
        self._run(action)
        return self.snapshot()

    def reconcile_mock_account(self, report, *, at):
        def action(value):
            if not isinstance(report, MockAccountReport):
                return dict(type="global_fault", at=utc(at).isoformat(), reason="ACCOUNT_MISMATCH"), None
            return dict(type="account", at=utc(at).isoformat(), report=asdict(report)), None
        self._run(action)
        return self.snapshot()

    def emergency_halt(self, *, at):
        self._run(lambda value: (dict(type="emergency", at=utc(at).isoformat()), None))
        return self.snapshot()
