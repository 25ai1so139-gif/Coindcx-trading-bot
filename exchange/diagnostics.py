"""Read-only minimum-size explanations. No approval, order, or state mutation."""

from dataclasses import asdict
from decimal import Decimal
from fractions import Fraction

from backtesting.costs import CostModel, fixed_decimal
from config import Settings, decimal_value
from exchange.instruments import Instrument
from risk.sizing import size_position


def _ceil(value):
    return -(-value.numerator // value.denominator)


def _exact_decimal(value):
    number = Decimal(value.numerator) / Decimal(value.denominator)
    if Fraction(number) != value:
        raise ValueError("MINIMUM_DIAGNOSTIC_NOT_REPRESENTABLE")
    return number


@fixed_decimal
def minimum_order_diagnostic(settings, instrument, reference_price):
    """Describe current sizing and theoretical stepped minima; never resize.

    Estimated adverse entry includes configured slippage. It is not a validated
    exchange limit price, price tick, actual fill, or recommendation to increase
    margin. Only the existing central gate can approve an entry.
    """
    if not isinstance(settings, Settings) or not isinstance(instrument, Instrument):
        raise ValueError("VALIDATED_SETTINGS_AND_INSTRUMENT_REQUIRED")
    Settings(**asdict(settings))
    Instrument(**asdict(instrument))
    reference = decimal_value(reference_price, "reference_price")
    if reference <= 0 or len(reference.as_tuple().digits) > 32 or abs(reference.as_tuple().exponent) > 32:
        raise ValueError("POSITIVE_REFERENCE_REQUIRED")
    result = {"label": "HYPOTHETICAL_SIZE_DIAGNOSTIC_NOT_ENTRY_APPROVAL",
              "symbol": instrument.pair, "quote_currency": instrument.quote,
              "instrument_observed_at": instrument.observed_at.isoformat(), "instrument_kind": instrument.kind,
              "configured_capital": settings.starting_capital, "configured_margin": settings.margin_amount,
              "configured_leverage": settings.leverage, "amount_type": settings.amount_type,
              "reference_price": reference, "quantity_step": instrument.step,
              "minimum_quantity": instrument.min_quantity, "minimum_notional": instrument.min_notional,
              "risk_approved": False, "orders_submitted": 0, "live_trading_enabled": False,
              "fee_slippage_verified": False, "price_tick_server_verified": False,
              "status": "NO_TRADE", "candidate": None, "theoretical_minimum": None}
    if (settings.starting_capital != 2000 or settings.risk_per_trade > Decimal("0.005")
            or settings.daily_loss_limit > Decimal("0.02")):
        result["reason"] = "PHASE5_PROFILE_REQUIRED"
        return result
    if instrument.kind == "public_metadata" and settings.leverage != 1:
        result["reason"] = "SPOT_ORDER_LEVERAGE_UNSUPPORTED"
        return result
    try:
        entry = CostModel.from_settings(settings).entry_fill(reference)
        lots = max(_ceil(Fraction(instrument.min_quantity) / Fraction(instrument.step)),
                   _ceil(Fraction(instrument.min_notional) / (Fraction(instrument.step) * Fraction(entry))))
        minimum_qty = _exact_decimal(Fraction(lots) * Fraction(instrument.step))
        notional = _exact_decimal(Fraction(minimum_qty) * Fraction(entry))
        result["estimated_entry"] = entry
        result["theoretical_minimum"] = {"quantity": minimum_qty, "notional": notional,
             "margin": _exact_decimal(Fraction(notional) / Fraction(settings.leverage)),
             "note": "Arithmetic lower bound only, not a new configuration or permission; excludes margin-plus-fee cash and other gate checks."}
        # Show the existing down-rounded candidate without pretending it meets
        # the exchange minima. This pure calculation cannot open a position.
        candidate = size_position(settings, settings.starting_capital, reference, quantity_step=instrument.step)
        result["candidate"] = asdict(candidate)
        plan = size_position(settings, settings.starting_capital, reference, quantity_step=instrument.step,
                             minimum_quantity=instrument.min_quantity, minimum_notional=instrument.min_notional)
        if plan.quantity > instrument.max_quantity:
            raise ValueError("QUANTITY_ABOVE_PUBLIC_MAXIMUM")
        result.update(status="SIZE_ONLY_NOT_APPROVED", reason="ALL_ENTRY_AND_MARKET_CHECKS_STILL_REQUIRED")
    except (ValueError, ArithmeticError):
        result["reason"] = "CONFIGURED_SIZE_CANNOT_SAFELY_MEET_PUBLIC_MINIMUMS"
    return result
