"""Validated simulated-account snapshots; verification never mutates counters."""

from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Mapping

from config import Settings, decimal_value
from data.schema import utc
from risk.controls import RiskControls


@dataclass(frozen=True, slots=True)
class VerificationAccount:
    as_of: datetime
    equity: Decimal
    controls: RiskControls
    has_open_position: bool
    kind: str

    @classmethod
    def from_mapping(cls, settings: Settings, value: Mapping) -> "VerificationAccount":
        required = {"schema_version", "account_mode", "kind", "as_of", "starting_capital",
                    "equity", "peak_equity", "day_start_equity", "day", "entries_today",
                    "has_open_position", "daily_halted", "drawdown_halted", "emergency_halted"}
        if (not isinstance(value, Mapping) or required - value.keys()
                or value.keys() - required - {"label"}):
            raise ValueError("invalid_risk_state_schema")
        if (type(value["schema_version"]) is not int or value["schema_version"] != 1
                or value["account_mode"] not in {"paper", "backtest"}
                or value["kind"] not in {"synthetic", "paper"}):
            raise ValueError("invalid_simulated_account")
        if decimal_value(value["starting_capital"], "starting_capital") != settings.starting_capital:
            raise ValueError("account_capital_mismatch")
        for key in ("has_open_position", "daily_halted", "drawdown_halted", "emergency_halted"):
            if type(value[key]) is not bool:
                raise ValueError(f"{key}_must_be_boolean")
        if type(value["entries_today"]) is not int or not 0 <= value["entries_today"] <= settings.max_trades_per_day:
            raise ValueError("invalid_entry_count")
        controls = RiskControls(settings)
        controls.peak_equity = decimal_value(value["peak_equity"], "peak_equity")
        controls.day_start_equity = decimal_value(value["day_start_equity"], "day_start_equity")
        equity = decimal_value(value["equity"], "equity")
        if (controls.day_start_equity <= 0
                or controls.peak_equity < max(settings.starting_capital, controls.day_start_equity, equity)):
            raise ValueError("inconsistent_account_equity")
        controls.last_equity = equity
        controls.day = date.fromisoformat(value["day"])
        controls.entries_today = value["entries_today"]
        for key in ("daily_halted", "drawdown_halted", "emergency_halted"):
            setattr(controls, key, value[key])
        return cls(utc(value["as_of"]), equity, controls, value["has_open_position"], value["kind"])

    def reviewed_controls(self, settings: Settings, as_of: datetime,
                          max_age: timedelta) -> RiskControls:
        as_of, snapshot_time = utc(as_of), utc(self.as_of)
        if not isinstance(self.controls, RiskControls) or self.kind not in {"synthetic", "paper"}:
            raise ValueError("invalid_simulated_account")
        if snapshot_time > as_of:
            raise ValueError("future_risk_state")
        if as_of - snapshot_time > max_age:
            raise ValueError("stale_risk_state")
        if self.controls.day != as_of.date() or snapshot_time.date() != as_of.date():
            raise ValueError("risk_state_day_mismatch")
        if self.controls.settings != settings:
            raise ValueError("risk_settings_mismatch")
        if type(self.has_open_position) is not bool:
            raise ValueError("invalid_position_state")
        # Observe a copy: existing loss/drawdown logic detects current breaches
        # while retaining every supplied halt latch, without resetting the day.
        controls = deepcopy(self.controls)
        equity = decimal_value(self.equity, "equity")
        for key in ("peak_equity", "day_start_equity", "last_equity"):
            setattr(controls, key, decimal_value(getattr(controls, key), key))
        if (controls.day_start_equity <= 0 or controls.peak_equity
                < max(settings.starting_capital, controls.day_start_equity, equity)):
            raise ValueError("inconsistent_account_equity")
        if type(controls.entries_today) is not int or not 0 <= controls.entries_today <= settings.max_trades_per_day:
            raise ValueError("invalid_entry_count")
        for key in ("daily_halted", "drawdown_halted", "emergency_halted"):
            if type(getattr(controls, key)) is not bool:
                raise ValueError(f"{key}_must_be_boolean")
        controls.observe(equity, as_of)
        return controls
