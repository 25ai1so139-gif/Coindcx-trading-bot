from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal

from config import Settings, decimal_value


@dataclass
class RiskControls:
    settings: Settings

    def __post_init__(self) -> None:
        self.peak_equity = self.settings.starting_capital
        self.last_equity = self.settings.starting_capital
        self.day_start_equity = self.settings.starting_capital
        self.day: date | None = None
        self.daily_halted = False
        self.drawdown_halted = False
        self.emergency_halted = False
        self.entries_today = 0
        self.max_observed_drawdown = Decimal("0")

    @property
    def halt_reason(self) -> str | None:
        if self.emergency_halted:
            return "emergency_shutdown"
        if self.drawdown_halted:
            return "max_drawdown"
        if self.daily_halted:
            return "daily_loss_limit"
        return None

    @property
    def entry_block_reason(self) -> str | None:
        if self.halt_reason:
            return self.halt_reason
        if self.entries_today >= self.settings.max_trades_per_day:
            return "daily_trade_limit"
        return None

    def record_entry(self) -> None:
        if self.day is None or self.entry_block_reason:
            raise ValueError("risk controls do not permit a new entry")
        self.entries_today += 1

    @property
    def daily_loss_budget(self) -> Decimal:
        return min(self.day_start_equity * self.settings.daily_loss_limit,
                   self.settings.daily_loss_amount)

    @property
    def equity_floor(self) -> tuple[Decimal, str]:
        daily = self.day_start_equity - self.daily_loss_budget
        drawdown = self.peak_equity * (1 - self.settings.max_drawdown)
        return (daily, "daily_loss_limit") if daily >= drawdown else (drawdown, "max_drawdown")

    def observe(self, equity: Decimal, timestamp: datetime) -> None:
        equity = decimal_value(equity, "equity")
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("risk observations need a timezone-aware timestamp")
        day = timestamp.astimezone(timezone.utc).date()
        if self.day is not None and day < self.day:
            raise ValueError("risk observations cannot move backwards in date")
        if day != self.day:
            self.day = day
            # Include overnight gap P&L against the last observed account equity.
            self.day_start_equity = self.last_equity
            self.daily_halted = False
            self.entries_today = 0
        self.peak_equity = max(self.peak_equity, equity)
        drawdown = (self.peak_equity - equity) / self.peak_equity
        self.max_observed_drawdown = max(self.max_observed_drawdown, drawdown)
        self.drawdown_halted |= drawdown >= self.settings.max_drawdown
        self.daily_halted |= equity <= self.day_start_equity - self.daily_loss_budget
        self.last_equity = equity
