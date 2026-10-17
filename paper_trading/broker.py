from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from config import Settings
from data.models import Candle
from risk.controls import RiskControls
from risk.sizing import PositionPlan, size_position
from risk.stops import long_stop_reference
from strategies.base import Signal


@dataclass(frozen=True, slots=True)
class Position:
    plan: PositionPlan
    opened_at: datetime


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


class PaperBroker:
    """One long position; reserved margin is not counted as a cash expense.

    Signals supplied to process_bar must have been computed on earlier candles.
    The replay engine enforces that sequencing. All prices and balances are INR.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.cash = settings.starting_capital
        self.position: Position | None = None
        self.risk = RiskControls(settings)
        self.trades: list[Trade] = []
        self.last_bar: datetime | None = None
        self.last_candle: Candle | None = None

    def equity(self, mark_price: Decimal) -> Decimal:
        if self.position is None:
            return self.cash
        plan = self.position.plan
        return self.cash + plan.margin + plan.quantity * (mark_price - plan.entry_price)

    def _open(self, reference_price: Decimal, timestamp: datetime) -> None:
        if self.position is not None:
            raise ValueError("only one simulated position is permitted")
        floor, _ = self.risk.equity_floor
        plan = size_position(self.settings, self.cash, reference_price,
                             remaining_risk_budget=self.cash - floor)
        self.risk.record_entry()
        self.cash -= plan.margin + plan.entry_fee
        self.position = Position(plan, timestamp)

    def _close(self, reference_price: Decimal, timestamp: datetime, reason: str) -> None:
        if self.position is None:
            return
        position = self.position
        plan = position.plan
        fill = reference_price * (1 - self.settings.slippage_rate)
        gross = plan.quantity * (fill - plan.entry_price)
        exit_fee = plan.quantity * fill * self.settings.fee_rate
        self.cash += plan.margin + gross - exit_fee
        fees = plan.entry_fee + exit_fee
        self.trades.append(Trade(position.opened_at, timestamp, plan.quantity, plan.margin,
                                 self.settings.leverage, plan.entry_price, fill,
                                 gross, fees, gross - fees, reason))
        self.position = None
        self.risk.observe(self.cash, timestamp)

    def process_bar(self, candle: Candle, signal: Signal = Signal.HOLD) -> None:
        if not isinstance(signal, Signal):
            raise ValueError("signal must be a Signal enum")
        if self.last_bar is not None and candle.timestamp <= self.last_bar:
            raise ValueError("paper broker requires strictly increasing candles")
        self.last_bar = candle.timestamp
        self.last_candle = candle
        self.risk.observe(self.equity(candle.open), candle.timestamp)
        if self.position is not None and self.risk.halt_reason:
            self._close(candle.open, candle.timestamp, self.risk.halt_reason)
        if signal == Signal.SELL and self.position is not None:
            self._close(candle.open, candle.timestamp, "strategy_exit")
        elif signal == Signal.BUY and self.position is None and not self.risk.entry_block_reason:
            self._open(candle.open, candle.timestamp)
            self.risk.observe(self.equity(candle.open), candle.timestamp)
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
                    self.risk.daily_halted = True
                elif reason == "max_drawdown":
                    self.risk.drawdown_halted = True
            else:
                self.risk.observe(self.equity(candle.low), candle.timestamp)
        # Attribute intrabar observations to the UTC day the candle opened.
        self.risk.observe(self.equity(candle.close), candle.timestamp)

    def emergency_shutdown(self) -> None:
        """Latch entries off and flatten once at the last available candle close.

        This is offline simulation cleanup, not an exchange kill switch.
        """
        self.risk.emergency_halted = True
        if self.last_candle is not None:
            self._close(self.last_candle.close, self.last_candle.closed_at, "emergency_shutdown")

    def finish(self, candle: Candle) -> None:
        """Realize remaining P&L and exit costs at the end of a replay."""
        if self.last_bar != candle.timestamp:
            raise ValueError("finish requires the last processed candle")
        self._close(candle.close, candle.closed_at, "end_of_data")
