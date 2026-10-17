from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN

from config import Settings, decimal_value


@dataclass(frozen=True, slots=True)
class PositionPlan:
    quantity: Decimal
    entry_price: Decimal
    stop_price: Decimal
    margin: Decimal
    notional: Decimal
    entry_fee: Decimal
    planned_stop_risk: Decimal


def size_position(settings: Settings, equity: Decimal, reference_price: Decimal,
                  remaining_risk_budget: Decimal | None = None) -> PositionPlan:
    """Cap margin, cash use, and stop risk including both fees and adverse fills.

    The risk budget assumes a stop fill without a market gap. Gaps can exceed it.
    """
    equity = decimal_value(equity, "equity")
    reference_price = decimal_value(reference_price, "reference_price")
    if equity <= 0 or reference_price <= 0:
        raise ValueError("equity and reference_price must be positive")
    risk_budget = min(equity * settings.risk_per_trade, settings.max_planned_risk)
    if remaining_risk_budget is not None:
        remaining = decimal_value(remaining_risk_budget, "remaining_risk_budget")
        if remaining <= 0:
            raise ValueError("remaining_risk_budget must be positive")
        risk_budget = min(risk_budget, remaining)
    entry = reference_price * (1 + settings.slippage_rate)
    stop = entry * (1 - settings.stop_loss_fraction)
    stop_fill = stop * (1 - settings.slippage_rate)
    risk_per_unit = entry - stop_fill + settings.fee_rate * (entry + stop_fill)
    margin_budget = min(settings.margin_amount, equity * settings.max_margin_fraction)
    quantity = min(
        margin_budget * settings.leverage / entry,
        risk_budget / risk_per_unit,
        equity / (entry / settings.leverage + entry * settings.fee_rate),
    ).quantize(Decimal("0.00000001"), rounding=ROUND_DOWN)
    if quantity <= 0:
        raise ValueError("risk budget is too small for a simulated position")
    notional = quantity * entry
    return PositionPlan(quantity, entry, stop, notional / settings.leverage,
                        notional, notional * settings.fee_rate, quantity * risk_per_unit)
