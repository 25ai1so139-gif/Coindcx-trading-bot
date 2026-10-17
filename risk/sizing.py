from dataclasses import dataclass
from decimal import Decimal

from config import Settings, decimal_value
from backtesting.costs import CostModel


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
                  remaining_risk_budget: Decimal | None = None, *,
                  quantity_step: Decimal = Decimal("0.00000001"),
                  minimum_quantity: Decimal = Decimal("0"),
                  minimum_notional: Decimal = Decimal("0")) -> PositionPlan:
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
    costs = CostModel.from_settings(settings)
    entry = costs.entry_fill(reference_price)
    stop = entry * (1 - settings.stop_loss_fraction)
    if not stop.is_finite() or not 0 < stop < entry:
        raise ValueError("stop must remain strictly below entry at current Decimal precision")
    stop_fill = costs.exit_fill(stop)
    if not stop_fill.is_finite() or stop_fill <= 0:
        raise ValueError("stop fill must remain positive and finite")
    risk_per_unit = entry - stop_fill + settings.fee_rate * (entry + stop_fill)
    if not risk_per_unit.is_finite() or risk_per_unit <= 0:
        raise ValueError("planned stop risk per unit must be positive and finite")
    margin_budget = min(settings.margin_amount, equity * settings.max_margin_fraction)
    step = decimal_value(quantity_step, "quantity_step")
    min_qty = decimal_value(minimum_quantity, "minimum_quantity")
    min_notional = decimal_value(minimum_notional, "minimum_notional")
    if step <= 0 or min_qty < 0 or min_notional < 0:
        raise ValueError("invalid instrument size constraints")
    maximum_quantity = min(
        margin_budget * settings.leverage / entry,
        risk_budget / risk_per_unit,
        equity / (entry / settings.leverage + entry * settings.fee_rate),
    )
    # Decimal '/' can round the lot count before truncation. Integer division
    # truncates directly and rejects a quotient that exceeds working precision.
    quantity = (maximum_quantity // step) * step
    if quantity <= 0:
        raise ValueError("risk budget is too small for a simulated position")
    if quantity > maximum_quantity or quantity % step != 0:
        raise ValueError("instrument step cannot be represented safely")
    notional = quantity * entry
    if quantity < min_qty or notional < min_notional:
        raise ValueError("position is below instrument minimum; never increase risk to fit")
    return PositionPlan(quantity, entry, stop, notional / settings.leverage,
                        notional, notional * settings.fee_rate, quantity * risk_per_unit)
