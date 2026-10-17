"""Whitelisted structured decision records; deliberately no free-form payloads."""

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal

from config import decimal_value
from data.schema import SYMBOL, utc

LOGGER = logging.getLogger("coindcx.risk")


def safe_number(value):
    try:
        return decimal_value(value, "audit_number")
    except (ValueError, TypeError, ArithmeticError):
        return None


def safe_name(value):
    return value if isinstance(value, str) and SYMBOL.fullmatch(value) else None


@dataclass(frozen=True, slots=True)
class RiskRecord:
    timestamp: datetime
    symbol: str | None
    strategy: str | None
    approved: bool
    reason: str
    signal_timestamp: datetime | None
    data_kind: str | None
    entry_reference: Decimal | None
    stop_reference: Decimal | None
    planned_risk: Decimal | None
    permitted_risk: Decimal | None
    margin: Decimal | None
    notional: Decimal | None
    leverage: Decimal | None
    estimated_fees: Decimal | None
    estimated_slippage: Decimal | None
    equity: Decimal | None
    daily_start_equity: Decimal | None
    daily_loss_budget: Decimal | None
    entries_today: int | None
    daily_halted: bool | None
    drawdown_halted: bool | None
    emergency_halted: bool | None
    entry_fill: Decimal | None
    stop_price: Decimal | None
    estimated_stop_fill: Decimal | None
    effective_leverage: Decimal | None = None


class RiskAudit:
    """Session records plus standard logging; durable storage belongs to Phase 6."""

    def __init__(self):
        self.records: list[RiskRecord] = []

    def record(self, *, at, approved, reason, proposal=None, equity=None,
               controls=None, plan=None, permitted_risk=None, settings=None) -> RiskRecord:
        try:
            stamp = utc(at)
            if stamp > datetime.now(timezone.utc):
                stamp = datetime.now(timezone.utc)
        except (ValueError, TypeError, OverflowError):
            stamp = datetime.now(timezone.utc)
        decision = getattr(proposal, "decision", None)
        market = getattr(proposal, "market", None)
        try:
            signal_stamp = utc(getattr(decision, "timestamp", None))
        except (ValueError, TypeError, OverflowError):
            signal_stamp = None
        daily_start = safe_number(getattr(controls, "day_start_equity", None))
        daily_budget = None
        percentage = safe_number(getattr(settings, "daily_loss_limit", None))
        amount = safe_number(getattr(settings, "daily_loss_amount", None))
        if daily_start is not None and percentage is not None and amount is not None:
            try:
                daily_budget = min(daily_start * min(percentage, Decimal("0.02")), amount, Decimal("40"))
            except ArithmeticError:
                daily_budget = None
        fee = slippage = fill = None
        values = [safe_number(getattr(plan, name, None)) for name in ("stop_price", "quantity", "entry_fee", "entry_price")]
        rates = [safe_number(getattr(settings, name, None)) for name in ("slippage_rate", "fee_rate")]
        reference = safe_number(getattr(proposal, "reference_price", None))
        if all(value is not None for value in (*values, *rates, reference)):
            try:
                stop, quantity, entry_fee, entry = values
                slip, rate = rates
                fill = stop * (1 - slip)
                fee = entry_fee + quantity * fill * rate
                slippage = quantity * (entry - reference + stop - fill)
            except ArithmeticError:
                fee = slippage = fill = None
        def flag(name):
            value = getattr(controls, name, None)
            return value if type(value) is bool else None
        entries = getattr(controls, "entries_today", None)
        notional = safe_number(getattr(plan, "notional", None))
        account_equity = safe_number(equity)
        effective_leverage = None
        if notional is not None and account_equity is not None and account_equity > 0:
            try:
                # Proposed exposure / current account equity, before entry costs.
                effective_leverage = safe_number(notional / account_equity)
            except ArithmeticError:
                pass
        kind = getattr(market, "kind", None)
        kind = kind if isinstance(kind, str) and kind in {"synthetic", "historical"} else None
        record = RiskRecord(stamp, safe_name(getattr(market, "symbol", None)) or safe_name(getattr(decision, "symbol", None)),
                            safe_name(getattr(proposal, "strategy", None)), approved, reason, signal_stamp,
                            kind,
                            safe_number(getattr(proposal, "reference_price", None)),
                            safe_number(getattr(decision, "stop_loss_reference", None)),
                            safe_number(getattr(plan, "planned_stop_risk", None)), safe_number(permitted_risk),
                            safe_number(getattr(plan, "margin", None)), safe_number(getattr(plan, "notional", None)),
                            safe_number(getattr(settings, "leverage", None)), fee, slippage, safe_number(equity),
                            daily_start, daily_budget, entries if type(entries) is int else None,
                            flag("daily_halted"), flag("drawdown_halted"), flag("emergency_halted"),
                            safe_number(getattr(plan, "entry_price", None)),
                            safe_number(getattr(plan, "stop_price", None)), fill, effective_leverage)
        LOGGER.info(json.dumps(asdict(record), sort_keys=True, default=str, allow_nan=False))
        self.records.append(record)
        return record
