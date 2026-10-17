"""Validated, simulation-only settings. No credentials or network configuration."""

import os
from dataclasses import dataclass, fields
from decimal import Decimal, InvalidOperation
from typing import Mapping

HARD_MAX_PLANNED_RISK = Decimal("20")
HARD_DAILY_LOSS_AMOUNT = Decimal("40")
HARD_MAX_TRADES_PER_DAY = 3


def decimal_value(value: object, name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not result.is_finite():
        raise ValueError(f"{name} must be a finite number")
    return result


@dataclass(frozen=True, slots=True)
class Settings:
    mode: str = "backtest"
    starting_capital: Decimal = Decimal("2000")
    account_currency: str = "INR"
    amount_type: str = "margin"
    margin_amount: Decimal = Decimal("100")
    leverage: Decimal = Decimal("1")
    max_leverage: Decimal = Decimal("3")
    timeframe: str = "15m"
    strategy: str = "sma_cross"
    risk_per_trade: Decimal = Decimal("0.005")
    max_planned_risk: Decimal = HARD_MAX_PLANNED_RISK
    stop_loss_fraction: Decimal = Decimal("0.02")
    daily_loss_limit: Decimal = Decimal("0.02")
    daily_loss_amount: Decimal = HARD_DAILY_LOSS_AMOUNT
    max_trades_per_day: int = HARD_MAX_TRADES_PER_DAY
    max_drawdown: Decimal = Decimal("0.05")
    max_margin_fraction: Decimal = Decimal("0.25")
    fee_rate: Decimal = Decimal("0.001")
    slippage_rate: Decimal = Decimal("0.001")
    min_history_bars: int = 2880

    def __post_init__(self) -> None:
        from strategies import STRATEGIES

        numeric = (
            "starting_capital", "margin_amount", "leverage", "max_leverage",
            "risk_per_trade", "stop_loss_fraction", "daily_loss_limit",
            "max_drawdown", "max_margin_fraction", "fee_rate", "slippage_rate",
            "max_planned_risk", "daily_loss_amount",
        )
        for name in numeric:
            object.__setattr__(self, name, decimal_value(getattr(self, name), name))
        if self.mode not in {"backtest", "paper"}:
            raise ValueError("mode must be backtest or paper; real-money trading is disabled")
        if self.account_currency != "INR":
            raise ValueError("account_currency must be INR; currency conversion is not implemented")
        if self.amount_type != "margin":
            raise ValueError("amount_type must be margin")
        if self.timeframe != "15m":
            raise ValueError("only the 15m timeframe is supported initially")
        if self.strategy not in STRATEGIES:
            raise ValueError(f"unknown strategy: {self.strategy}")
        if self.starting_capital <= 0 or self.margin_amount <= 0:
            raise ValueError("starting_capital and margin_amount must be positive")
        if not Decimal("1") <= self.leverage <= self.max_leverage <= Decimal("3"):
            raise ValueError("require 1 <= leverage <= max_leverage <= 3")
        for name in ("risk_per_trade", "stop_loss_fraction", "daily_loss_limit",
                     "max_drawdown", "max_margin_fraction"):
            if not Decimal("0") < getattr(self, name) < Decimal("1"):
                raise ValueError(f"{name} must be greater than 0 and less than 1")
        if self.risk_per_trade > self.daily_loss_limit:
            raise ValueError("risk_per_trade cannot exceed daily_loss_limit")
        if self.daily_loss_limit > self.max_drawdown:
            raise ValueError("daily_loss_limit cannot exceed max_drawdown")
        if not 0 < self.max_planned_risk <= HARD_MAX_PLANNED_RISK:
            raise ValueError("max_planned_risk must be positive and cannot exceed INR 20")
        if not 0 < self.daily_loss_amount <= HARD_DAILY_LOSS_AMOUNT:
            raise ValueError("daily_loss_amount must be positive and cannot exceed INR 40")
        if (type(self.max_trades_per_day) is not int
                or not 1 <= self.max_trades_per_day <= HARD_MAX_TRADES_PER_DAY):
            raise ValueError("max_trades_per_day must be an integer between 1 and 3")
        for name in ("fee_rate", "slippage_rate"):
            if not Decimal("0") <= getattr(self, name) <= Decimal("0.05"):
                raise ValueError(f"{name} must be between 0 and 0.05")
        if type(self.min_history_bars) is not int or self.min_history_bars < 200:
            raise ValueError("min_history_bars must be an integer of at least 200")

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "Settings":
        """Read explicit BOT_* variables; blank values are errors, not defaults."""
        env = os.environ if environ is None else environ
        values: dict[str, object] = {}
        for field in fields(cls):
            key = f"BOT_{field.name.upper()}"
            if key in env:
                value = env[key].strip()
                if not value:
                    raise ValueError(f"{key} is empty; unset it to use the default")
                values[field.name] = value
        for name in ("min_history_bars", "max_trades_per_day"):
            if name in values:
                try:
                    values[name] = int(str(values[name]))
                except ValueError as exc:
                    raise ValueError(f"BOT_{name.upper()} must be an integer") from exc
        return cls(**values)
