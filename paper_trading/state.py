"""Strict, credential-free checkpoint codec and accounting reconciliation.

Private recovery helpers; only persistence.py may publish a recovered account
after checking the complete SQLite history, metadata and head anchor.
"""

import json
from dataclasses import fields, is_dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from types import UnionType
from typing import get_args, get_origin, get_type_hints

from backtesting.costs import fixed_decimal
from config import Settings
from data.models import Candle
from data.schema import utc
from paper_trading.broker import EquityObservation, PaperBroker, Position, RiskEvent, Trade
from risk.audit import RiskRecord
from risk.controls import RiskControls

RISK_FIELDS = {"peak_equity": Decimal, "last_equity": Decimal, "day_start_equity": Decimal,
               "day": date | None, "daily_halted": bool, "drawdown_halted": bool,
               "emergency_halted": bool, "entries_today": int, "max_observed_drawdown": Decimal}
STATE_KEYS = {"format", "cash", "equity", "realized_pnl", "position", "risk", "last_candle",
              "trades", "observations", "events", "audit", "exposed_bars"}
EXIT_REASONS = {"strategy_exit", "stop_loss", "daily_loss_limit", "max_drawdown",
                "emergency_shutdown", "end_of_data"}


def _require(condition, reason="INCONSISTENT_STATE"):
    if not condition:
        raise ValueError(reason)


def _json_value(value):
    if isinstance(value, Decimal):
        _require(value.is_finite(), "NONFINITE_STATE")
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if is_dataclass(value):
        return {field.name: _json_value(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    _require(value is None or type(value) in (str, bool, int), "UNSUPPORTED_STATE_VALUE")
    return value


def canonical(value):
    return json.dumps(_json_value(value), sort_keys=True, separators=(",", ":"), allow_nan=False)


def strict_json(payload):
    def pairs(items):
        result = {}
        for key, value in items:
            _require(key not in result, "DUPLICATE_JSON_KEY")
            result[key] = value
        return result
    def invalid(value):
        raise ValueError("NONCANONICAL_JSON_NUMBER")
    return json.loads(payload, object_pairs_hook=pairs, parse_float=invalid, parse_constant=invalid)


def _decode(value, hint):
    if get_origin(hint) is UnionType:
        if value is None and type(None) in get_args(hint):
            return None
        choices = [item for item in get_args(hint) if item is not type(None)]
        _require(len(choices) == 1)
        return _decode(value, choices[0])
    if hint is Decimal:
        _require(type(value) is str, "DECIMAL_MUST_BE_TEXT")
        number = Decimal(value)
        _require(number.is_finite(), "NONFINITE_STATE")
        return number
    if hint is datetime:
        _require(type(value) is str)
        stamp = utc(value)
        _require(stamp.isoformat() == value and stamp <= datetime.now(timezone.utc), "INVALID_STATE_TIME")
        return stamp
    if hint is date:
        _require(type(value) is str)
        return date.fromisoformat(value)
    if is_dataclass(hint):
        _require(type(value) is dict and set(value) == {field.name for field in fields(hint)}, "INVALID_RECORD_SCHEMA")
        hints = get_type_hints(hint)
        return hint(**{name: _decode(item, hints[name]) for name, item in value.items()})
    _require(type(value) is hint, "INVALID_STATE_TYPE")
    return value


@fixed_decimal
def _dump(broker):
    return canonical({"format": 1, "cash": broker.cash,
                      "equity": broker.equity(broker.last_candle.close) if broker.last_candle else broker.cash,
                      "realized_pnl": broker.realized_pnl, "position": broker.position,
                      "risk": {name: getattr(broker.risk, name) for name in RISK_FIELDS},
                      "last_candle": broker.last_candle, "trades": broker.trades,
                      "observations": broker.equity_observations, "events": broker.risk_events,
                      "audit": broker.risk_audit.records, "exposed_bars": broker.exposed_bars})


def _records(value, cls):
    _require(type(value) is list, "INVALID_HISTORY")
    return [_decode(item, cls) for item in value]


def _close_enough(left, right):
    # Representation-only reconciliation; the entry gate's risk comparisons
    # remain strict. No monetary safety limit is increased by this tolerance.
    return abs(left - right) <= Decimal("1e-20")


@fixed_decimal
def _load(payload, settings):
    value = strict_json(payload)
    _require(type(value) is dict and set(value) == STATE_KEYS, "INVALID_STATE_SCHEMA")
    _require(type(value["format"]) is int and value["format"] == 1, "INCOMPATIBLE_STATE_FORMAT")
    broker = PaperBroker(settings)
    broker.cash = _decode(value["cash"], Decimal)
    broker.realized_pnl = _decode(value["realized_pnl"], Decimal)
    broker._position = _decode(value["position"], Position | None)
    broker.last_candle = _decode(value["last_candle"], Candle | None)
    broker.last_bar = broker.last_candle.timestamp if broker.last_candle else None
    broker.trades = _records(value["trades"], Trade)
    broker.equity_observations = _records(value["observations"], EquityObservation)
    broker.risk_events = _records(value["events"], RiskEvent)
    broker.risk_audit.records = _records(value["audit"], RiskRecord)
    broker.exposed_bars = _decode(value["exposed_bars"], int)
    _require(broker.exposed_bars >= 0)
    risk = value["risk"]
    _require(type(risk) is dict and set(risk) == set(RISK_FIELDS), "INVALID_RISK_SCHEMA")
    for name, hint in RISK_FIELDS.items():
        setattr(broker.risk, name, _decode(risk[name], hint))

    cash, realized, fills = settings.starting_capital, Decimal(0), []
    previous_exit = None
    for trade in broker.trades:
        _require(trade.reason in EXIT_REASONS and trade.opened_at <= trade.closed_at)
        _require(previous_exit is None or previous_exit <= trade.opened_at, "OVERLAPPING_POSITIONS")
        _require(all(getattr(trade, name) > 0 for name in
                     ("quantity", "margin", "entry_price", "exit_price", "entry_reference", "exit_reference")))
        _require(trade.leverage == settings.leverage)
        _require(trade.entry_notional == trade.quantity * trade.entry_price)
        _require(trade.margin == trade.entry_notional / settings.leverage)
        _require(trade.entry_price == broker.costs.entry_fill(trade.entry_reference))
        _require(trade.exit_price == broker.costs.exit_fill(trade.exit_reference))
        entry_fee = trade.entry_notional * settings.fee_rate
        exit_fee = broker.costs.fee(trade.quantity, trade.exit_price)
        gross = trade.quantity * (trade.exit_price - trade.entry_price)
        _require(trade.gross_pnl == gross and trade.fees == entry_fee + exit_fee
                 and trade.net_pnl == gross - trade.fees, "TRADE_RECONCILIATION")
        _require(trade.slippage == trade.quantity * (trade.entry_price - trade.entry_reference
                                                    + trade.exit_reference - trade.exit_price))
        modeled_stop = trade.entry_price * (1 - settings.stop_loss_fraction)
        modeled_exit = broker.costs.exit_fill(modeled_stop)
        modeled_loss = trade.quantity * (trade.entry_price - modeled_exit) + entry_fee + trade.quantity * modeled_exit * settings.fee_rate
        _require(_close_enough(modeled_loss, trade.planned_stop_risk), "CLOSED_TRADE_RISK_MISMATCH")
        available_equity = cash
        cash -= trade.margin + entry_fee
        cash += trade.margin + gross - exit_fee
        realized += trade.net_pnl
        fills.append((trade.opened_at, trade.margin, trade.entry_notional, trade.entry_price,
                      trade.planned_stop_risk, available_equity))
        previous_exit = trade.closed_at
    if broker.position:
        position, plan = broker.position, broker.position.plan
        _require(previous_exit is None or previous_exit <= position.opened_at, "OVERLAPPING_POSITIONS")
        _require(all(getattr(plan, field.name) >= 0 if field.name == "entry_fee"
                     else getattr(plan, field.name) > 0 for field in fields(plan)))
        _require(plan.entry_price == broker.costs.entry_fill(position.entry_reference))
        _require(plan.notional == plan.quantity * plan.entry_price and plan.margin == plan.notional / settings.leverage)
        _require(plan.entry_fee == plan.notional * settings.fee_rate)
        _require(plan.stop_price == plan.entry_price * (1 - settings.stop_loss_fraction)
                 and 0 < plan.stop_price < plan.entry_price)
        stop_fill = broker.costs.exit_fill(plan.stop_price)
        loss = plan.quantity * (plan.entry_price - stop_fill) + plan.entry_fee + plan.quantity * stop_fill * settings.fee_rate
        _require(_close_enough(loss, plan.planned_stop_risk), "POSITION_RISK_RECONCILIATION")
        available_equity = cash
        cash -= plan.margin + plan.entry_fee
        fills.append((position.opened_at, plan.margin, plan.notional, plan.entry_price, plan.planned_stop_risk, available_equity))
    _require(cash == broker.cash and realized == broker.realized_pnl, "CASH_RECONCILIATION")
    equity = broker.equity(broker.last_candle.close) if broker.last_candle else broker.cash
    _require(_decode(value["equity"], Decimal) == equity == broker.risk.last_equity, "EQUITY_RECONCILIATION")
    _require(len({fill[0] for fill in fills}) == len(fills), "DUPLICATE_ENTRY")
    approvals = [record for record in broker.risk_audit.records if record.approved]
    _require(len(approvals) == len(fills), "ENTRY_APPROVAL_HISTORY_MISMATCH")
    for index, (record, (stamp, margin, notional, entry, loss, available_equity)) in enumerate(zip(approvals, fills)):
        _require(record.reason == "APPROVED" and record.timestamp == stamp
                 and record.margin == margin and record.notional == notional
                 and record.entry_fill == entry and record.planned_risk == loss, "ENTRY_APPROVAL_MISMATCH")
        _require(record.permitted_risk is not None and 0 < loss <= record.permitted_risk <= 20
                 and record.equity is not None and record.permitted_risk <= record.equity * settings.risk_per_trade)
        _require(record.leverage == settings.leverage <= 3)
        _require(record.equity == available_equity and margin <= min(settings.margin_amount, available_equity * settings.max_margin_fraction)
                 and margin + notional * settings.fee_rate <= available_equity, "ENTRY_ACCOUNT_RECONCILIATION")
        _require(record.entries_today == sum(previous[0].date() == stamp.date() for previous in fills[:index])
                 and record.entries_today < settings.max_trades_per_day)
        _require(record.daily_start_equity is not None and record.daily_start_equity > 0
                 and record.daily_loss_budget == min(record.daily_start_equity * settings.daily_loss_limit, settings.daily_loss_amount))
        _require(loss <= available_equity - record.daily_start_equity + record.daily_loss_budget, "ENTRY_DAILY_HEADROOM")
        _require(record.emergency_halted is False and record.daily_halted is False and record.drawdown_halted is False)
    _require(0 <= broker.risk.entries_today <= settings.max_trades_per_day)
    _require(broker.risk.entries_today == sum(stamp.date() == broker.risk.day for stamp, *_ in fills),
             "DAILY_ENTRY_COUNT_MISMATCH")

    replay = RiskControls(settings)
    for observation in broker.equity_observations:
        _require(observation.phase in {"open", "entry", "exit", "intrabar_low_time_unknown", "close"}, "INVALID_OBSERVATION_PHASE")
        _require(_close_enough(observation.cash + observation.margin + observation.unrealized_pnl, observation.equity),
                 "OBSERVATION_RECONCILIATION")
        _require(_close_enough(settings.starting_capital + observation.realized_pnl
                              + observation.unrealized_pnl, observation.equity), "PNL_RECONCILIATION")
        replay.observe(observation.equity, observation.timestamp)
    _require(all(event.reason in {"daily_loss_limit", "max_drawdown", "daily_trade_limit", "emergency_shutdown"}
                 for event in broker.risk_events), "INVALID_RISK_EVENT")
    for name in ("day", "day_start_equity", "peak_equity", "last_equity", "max_observed_drawdown"):
        _require(getattr(replay, name) == getattr(broker.risk, name), "RISK_OBSERVATION_MISMATCH")
    daily_event = any(event.reason == "daily_loss_limit" and event.timestamp.date() == replay.day
                      for event in broker.risk_events)
    drawdown_event = any(event.reason == "max_drawdown" for event in broker.risk_events)
    _require(broker.risk.daily_halted == (replay.daily_halted or daily_event), "DAILY_HALT_MISMATCH")
    _require(broker.risk.drawdown_halted == (replay.drawdown_halted or drawdown_event), "DRAWDOWN_HALT_MISMATCH")
    _require(not broker.position or not broker.risk.halt_reason, "HALTED_OPEN_POSITION")
    if broker.last_candle is None:
        _require(not fills and not broker.equity_observations and not broker.risk_audit.records and broker.exposed_bars == 0)
    else:
        _require(bool(broker.equity_observations))
        _require(all(stamp <= broker.last_candle.closed_at for stamp, *_ in fills))
    return broker


def _transition(previous, current, operation):
    """Append-only history and monotonic risk state, independent of checksums."""
    for key in ("trades", "observations", "events", "audit"):
        _require(current[key][:len(previous[key])] == previous[key], "HISTORY_REWRITTEN")
    old, new = previous["risk"], current["risk"]
    _require(new["emergency_halted"] == (old["emergency_halted"] or operation == "emergency"), "EMERGENCY_HALT_RESET")
    _require(not old["drawdown_halted"] or new["drawdown_halted"], "DRAWDOWN_HALT_RESET")
    if old["day"] == new["day"]:
        _require(not old["daily_halted"] or new["daily_halted"], "DAILY_HALT_RESET")
        _require(new["entries_today"] >= old["entries_today"], "ENTRY_COUNTER_RESET")
    if operation != "bar":
        _require(current["last_candle"] == previous["last_candle"])
        _require(len(current["trades"]) + int(current["position"] is not None)
                 == len(previous["trades"]) + int(previous["position"] is not None), "ENTRY_OUTSIDE_BAR")
    elif previous["last_candle"] is not None:
        _require(current["last_candle"]["timestamp"] > previous["last_candle"]["timestamp"], "CANDLE_ORDER")
    delta = current["exposed_bars"] - previous["exposed_bars"]
    _require(delta in (0, 1) if operation == "bar" else delta == 0)
