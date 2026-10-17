"""Explicit SYNTHETIC Phase 7 fixtures; not real metadata or account evidence."""

from dataclasses import replace
from decimal import Decimal

from config import Settings
from exchange.instruments import Instrument
from exchange.reconciliation import _wire_request
from risk.context import VerificationAccount
from risk.controls import RiskControls
from tests.helpers import candle, synthetic_proposal

D = Decimal
SYMBOL = "SYNTHETIC-INR"


def fixture():
    settings = Settings(mode="paper", min_history_bars=200)
    at = candle(200).timestamp
    proposal = synthetic_proposal(settings, at)
    instrument = Instrument(SYMBOL, "SYNTHETICINR", "INR", "SYNTHETIC", 6, 4,
                            D(".0001"), D(1000), D(1), D(".0001"), D(1000000), D(".0001"), at,
                            "synthetic_fixture", limit_orders_supported=True)
    spec = replace(proposal.market.instrument, quantity_step=instrument.step,
                   minimum_quantity=instrument.min_quantity, minimum_notional=instrument.min_notional)
    proposal = replace(proposal, market=replace(proposal.market, instrument=spec))
    controls = RiskControls(settings)
    controls.observe(D(2000), at)
    account = VerificationAccount(at, D(2000), controls, False, "synthetic")
    return settings, at, proposal, instrument, account


def mock_response(request_json, *, status="open", order_id="12345", remaining=None, average=None,
                  fee="0", updated_at=None):
    request = _wire_request(request_json)
    quantity = request["total_quantity"]
    if remaining is None:
        remaining = 0 if status == "filled" else quantity / 2 if status in ("partially_filled", "partially_cancelled") else quantity
    if average is None:
        average = request["price_per_unit"] if status in ("filled", "partially_filled", "partially_cancelled") else 0
    return {"id": order_id, "client_order_id": request["client_order_id"], "market": request["market"],
            "side": request["side"], "order_type": request["order_type"], "status": status,
            "total_quantity": quantity, "remaining_quantity": D(remaining), "avg_price": D(average),
            "price_per_unit": request["price_per_unit"], "fee_amount": D(fee),
            "created_at": request["timestamp"], "updated_at": updated_at or request["timestamp"]}
