from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from functools import wraps
from threading import RLock

from config import Settings, decimal_value
from backtesting.costs import CostModel, fixed_decimal
from data.models import Candle
from data.schema import utc
from risk.controls import RiskControls
from risk import entry as risk_gate
from risk.audit import RiskAudit
from risk.proposal import EntryProposal
from risk.sizing import PositionPlan
from risk.stops import long_stop_reference
from strategies.base import Signal


def _serialized(function):
    calculate = fixed_decimal(function)
    @wraps(function)
    def wrapped(self, *args, **kwargs):
        with self._execution_lock:
            return calculate(self, *args, **kwargs)
    return wrapped


def _non_reentrant_bar(function):
    """Reject callback-driven candle changes while the instance lock is held."""
    @wraps(function)
    def wrapped(self, *args, **kwargs):
        if self._processing_bar:
            raise ValueError("reentrant bar processing is forbidden")
        self._processing_bar = True
        try:
            return function(self, *args, **kwargs)
        finally:
            self._processing_bar = False
    return wrapped


@dataclass(frozen=True, slots=True)
class Position:
    plan: PositionPlan
    opened_at: datetime
    entry_reference: Decimal


@dataclass(frozen=True, slots=True)
class Trade:
    opened_at: datetime
    closed_at: datetime
    quantity: Decimal
    margin: Decimal
    leverage: Decimal
    entry_price: Decimal
    exit_price: Decimal
    gross_pnl: Decimal
    fees: Decimal
    net_pnl: Decimal
    reason: str
    entry_reference: Decimal
    exit_reference: Decimal
    slippage: Decimal
    entry_notional: Decimal
    planned_stop_risk: Decimal


@dataclass(frozen=True, slots=True)
class EquityObservation:
    timestamp: datetime
    phase: str
    equity: Decimal
    cash: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    notional: Decimal
    margin: Decimal
    effective_leverage: Decimal | None


@dataclass(frozen=True, slots=True)
class RiskEvent:
    timestamp: datetime
    reason: str
    equity: Decimal


class PaperBroker:
    """One long position; reserved margin is not counted as a cash expense.

    Signals supplied to process_bar must have been computed on earlier candles.
    The replay engine enforces that sequencing. All prices and balances are INR.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.cash = settings.starting_capital
        self._position: Position | None = None
        self.risk = RiskControls(settings)
        self.trades: list[Trade] = []
        self.last_bar: datetime | None = None
        self.last_candle: Candle | None = None
        self.costs = CostModel.from_settings(settings)
        self.equity_observations: list[EquityObservation] = []
        self.risk_events: list[RiskEvent] = []
        self.exposed_bars = 0
        self.realized_pnl = Decimal("0")
        self.risk_audit = RiskAudit()
        self._execution_lock = RLock()
        self._processing_bar = False
        self.__entry_bar = None
        self.__opening = False

    @property
    def position(self) -> Position | None:
        return self._position

    def _observe(self, mark: Decimal, timestamp: datetime, phase: str) -> None:
        before_day = self.risk.day
        before_daily, before_drawdown = self.risk.daily_halted, self.risk.drawdown_halted
        equity = self.equity(mark)
        self.risk.observe(equity, timestamp)
        if self.risk.daily_halted and (not before_daily or before_day != self.risk.day):
            self.risk_events.append(RiskEvent(timestamp, "daily_loss_limit", equity))
        if self.risk.drawdown_halted and not before_drawdown:
            self.risk_events.append(RiskEvent(timestamp, "max_drawdown", equity))
        plan = self.position.plan if self.position is not None else None
        notional = plan.quantity * mark if plan else Decimal("0")
        realized = self.realized_pnl
        # Entry fees are already realized expenses while a position is open.
        realized -= plan.entry_fee if plan else Decimal("0")
        unrealized = plan.quantity * (mark - plan.entry_price) if plan else Decimal("0")
        self.equity_observations.append(EquityObservation(
            timestamp, phase, equity, self.cash, realized, unrealized, notional,
            plan.margin if plan else Decimal("0"), notional / equity if equity > 0 else None))

    def equity(self, mark_price: Decimal) -> Decimal:
        if self.position is None:
            return self.cash
        plan = self.position.plan
        return self.cash + plan.margin + plan.quantity * (mark_price - plan.entry_price)

    @_serialized
    def _open(self, reference_price: Decimal, timestamp: datetime,
              proposal: EntryProposal | None = None) -> bool:
        if isinstance(proposal, EntryProposal) and proposal.reference_price != reference_price:
            proposal = None
        if self.__opening:
            raise ValueError("reentrant entry approval is forbidden")
        ready = (self.__entry_bar is not None and self.__entry_bar is self.last_candle
                 and self.__entry_bar.timestamp == timestamp and self.__entry_bar.open == reference_price)
        self.__opening = True
        try:
            approval = risk_gate.approve_entry(self.settings, self.risk,
                                               self.cash if self.position is None else self.risk.last_equity, proposal,
                                               at=timestamp, has_open_position=self.position is not None,
                                               audit=self.risk_audit, execution_ready=ready)
        finally:
            self.__opening = False
        if not approval.approved:
            return False
        plan = approval.plan
        self.risk.record_entry()
        self.cash -= plan.margin + plan.entry_fee
        self._position = Position(plan, timestamp, reference_price)
        if self.risk.entries_today == self.settings.max_trades_per_day:
            self.risk_events.append(RiskEvent(timestamp, "daily_trade_limit", self.equity(reference_price)))
        return True

    @_serialized
    def _close(self, reference_price: Decimal, timestamp: datetime, reason: str) -> None:
        if self.position is None:
            return
        reference_price = decimal_value(reference_price, "exit_reference")
        timestamp = utc(timestamp)
        if (self.last_candle is None or not self.last_candle.low <= reference_price <= self.last_candle.high
                or not self.last_candle.timestamp <= timestamp <= self.last_candle.closed_at):
            raise ValueError("exit must use the current validated candle's prices and interval")
        position = self.position
        plan = position.plan
        fill = self.costs.exit_fill(reference_price)
        gross = plan.quantity * (fill - plan.entry_price)
        exit_fee = self.costs.fee(plan.quantity, fill)
        self.cash += plan.margin + gross - exit_fee
        fees = plan.entry_fee + exit_fee
        self.trades.append(Trade(position.opened_at, timestamp, plan.quantity, plan.margin,
                                 self.settings.leverage, plan.entry_price, fill,
                                 gross, fees, gross - fees, reason,
                                 position.entry_reference, reference_price,
                                 plan.quantity * (plan.entry_price - position.entry_reference + reference_price - fill),
                                 plan.notional, plan.planned_stop_risk))
        self._position = None
        self.realized_pnl += gross - fees
        self._observe(reference_price, timestamp, "exit")

    @_serialized
    @_non_reentrant_bar
    def process_bar(self, candle: Candle, signal: Signal = Signal.HOLD, *,
                    entry: EntryProposal | None = None) -> None:
        if not isinstance(signal, Signal):
            self.risk_audit.record(at=getattr(candle, "timestamp", None), approved=False, reason="INVALID_BROKER_SIGNAL",
                                   proposal=entry, equity=self.cash, controls=self.risk, settings=self.settings)
            raise ValueError("signal must be a Signal enum")
        try:
            if self.last_bar is not None and candle.timestamp <= self.last_bar:
                raise ValueError("paper broker requires strictly increasing candles")
            Candle(candle.timestamp, candle.open, candle.high, candle.low, candle.close, candle.volume)
            if candle.closed_at > datetime.now(timezone.utc):
                raise ValueError("paper replay requires completed candles")
        except (ValueError, TypeError, AttributeError, ArithmeticError):
            self.risk_audit.record(at=getattr(candle, "timestamp", None), approved=False, reason="INVALID_BROKER_CANDLE",
                                   proposal=entry, equity=self.cash, controls=self.risk, settings=self.settings)
            raise
        self.last_bar = candle.timestamp
        self.last_candle = candle
        exposed = self.position is not None
        self._observe(candle.open, candle.timestamp, "open")
        if self.position is not None and self.risk.halt_reason:
            self._close(candle.open, candle.timestamp, self.risk.halt_reason)
        if signal == Signal.SELL and self.position is not None:
            self._close(candle.open, candle.timestamp, "strategy_exit")
        elif signal == Signal.SELL and entry is not None:
            # Analytical SHORT with no long to exit is an attempted unsupported
            # entry, and receives the same logged central rejection.
            from strategies.base import Direction
            if isinstance(entry, EntryProposal) and getattr(entry.decision, "signal", None) == Direction.SHORT:
                risk_gate.approve_entry(self.settings, self.risk, self.cash, entry,
                                       at=candle.timestamp, has_open_position=False, audit=self.risk_audit)
            else:
                self.risk_audit.record(at=candle.timestamp, approved=False, reason="ACTION_SIGNAL_MISMATCH",
                                       proposal=entry, equity=self.cash, controls=self.risk, settings=self.settings)
        elif signal == Signal.BUY:
            self.__entry_bar = candle
            try:
                opened = self._open(candle.open, candle.timestamp, entry)
            finally:
                self.__entry_bar = None
            if opened:
                exposed = True
                self._observe(candle.open, candle.timestamp, "entry")
                if self.risk.halt_reason:
                    self._close(candle.open, candle.timestamp, self.risk.halt_reason)
        if self.position is not None:
            plan = self.position.plan
            floor, reason = self.risk.equity_floor
            # Solve for final cash AFTER exit slippage and the exit fee.
            risk_price = (floor - self.cash - plan.margin + plan.quantity * plan.entry_price) / (
                plan.quantity * (1 - self.settings.slippage_rate) * (1 - self.settings.fee_rate))
            trigger = max(plan.stop_price, risk_price)
            reason = "stop_loss" if plan.stop_price >= risk_price else reason
            reference = long_stop_reference(candle, trigger)
            if reference is not None:
                self._close(reference, candle.timestamp, reason)
                # A limit-triggered exit stays latched despite Decimal rounding at the boundary.
                if reason == "daily_loss_limit":
                    if not self.risk.daily_halted:
                        self.risk_events.append(RiskEvent(candle.timestamp, reason, self.cash))
                    self.risk.daily_halted = True
                elif reason == "max_drawdown":
                    if not self.risk.drawdown_halted:
                        self.risk_events.append(RiskEvent(candle.timestamp, reason, self.cash))
                    self.risk.drawdown_halted = True
            else:
                self._observe(candle.low, candle.timestamp, "intrabar_low_time_unknown")
        # Attribute intrabar observations to the UTC day the candle opened.
        self._observe(candle.close, candle.timestamp, "close")
        self.exposed_bars += int(exposed)

    @_serialized
    def emergency_shutdown(self) -> None:
        """Latch entries off and flatten once at the last available candle close.

        This is offline simulation cleanup, not an exchange kill switch.
        """
        if not self.risk.emergency_halted and self.last_candle is not None:
            self.risk_events.append(RiskEvent(self.last_candle.closed_at, "emergency_shutdown",
                                             self.equity(self.last_candle.close)))
        self.risk.emergency_halted = True
        if self.last_candle is not None:
            self._close(self.last_candle.close, self.last_candle.closed_at, "emergency_shutdown")

    @_serialized
    def finish(self, candle: Candle) -> None:
        """Realize remaining P&L and exit costs at the end of a replay."""
        if self.last_bar != candle.timestamp:
            raise ValueError("finish requires the last processed candle")
        self._close(candle.close, candle.closed_at, "end_of_data")
