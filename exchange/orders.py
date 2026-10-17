"""Offline spot BUY/limit request construction; a preview is never a fill."""

import json
import re
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from backtesting.costs import fixed_decimal
from data.schema import epoch_ms, utc
from exchange.contracts import ExchangeBlocked, require
from exchange.instruments import Instrument
from risk import entry as risk_gate
from risk.audit import RiskAudit
from risk.context import VerificationAccount


@dataclass(frozen=True)
class OrderPreview:
    approved: bool
    reason: str
    request_json: str | None
    plan: object | None
    risk_record: object
    data_kind: str | None
    orders_submitted: int = 0
    live_trading_enabled: bool = False


def _wire_json(payload):
    """Exact JSON numbers without routing Decimal through binary floats."""
    return "{" + ",".join(json.dumps(key) + ":" + (format(value, "f") if isinstance(value, Decimal)
                         else json.dumps(value, separators=(",", ":"))) for key, value in payload.items()) + "}"


@fixed_decimal
def preview_entry(settings, account, proposal, instrument, *, at, client_order_id,
                  audit, execution_ready=True):
    """Call the shared gate on every review. Never accept a precomputed plan.

    Base-currency price precision is a conservative metadata check, not verified
    exchange price-tick behavior. No rounding of a risk-approved plan is allowed.
    Real-market liquidity and reviewed instrument flags are never upgraded here.
    """
    if not isinstance(audit, RiskAudit):
        raise ValueError("RISK_AUDIT_REQUIRED")
    controls, equity, has_position = None, None, False
    try:
        require(isinstance(account, VerificationAccount), "SIMULATED_ACCOUNT_REQUIRED")
        controls = account.reviewed_controls(settings, utc(at), timedelta(minutes=30))
        equity, has_position = account.equity, account.has_open_position
    except (ValueError, TypeError, ArithmeticError, AttributeError):
        pass  # Gate rejects the missing/untrustworthy account, and logs it.
    result = risk_gate.approve_entry(settings, controls, equity, proposal, at=at,
             has_open_position=has_position, audit=audit, execution_ready=execution_ready)
    kind = getattr(getattr(proposal, "market", None), "kind", None)
    if not result.approved:
        return OrderPreview(False, result.reason, None, None, result.record, kind)
    try:
        at = utc(at)
        require(isinstance(instrument, Instrument), "INSTRUMENT_METADATA_REQUIRED")
        # Reconstruct immutable-looking input in case its attributes were damaged.
        from dataclasses import asdict
        Instrument(**asdict(instrument))
        require(timedelta(0) <= at - instrument.observed_at <= timedelta(minutes=5), "STALE_INSTRUMENT_METADATA")
        require(instrument.pair == proposal.market.symbol, "INSTRUMENT_PAIR_MISMATCH")
        require((kind == "synthetic") == (instrument.kind == "synthetic_fixture"), "INSTRUMENT_PROVENANCE_MISMATCH")
        require(settings.leverage == 1, "SPOT_ORDER_LEVERAGE_UNSUPPORTED")
        spec = proposal.market.instrument
        require(spec.quantity_step == instrument.step and spec.minimum_quantity == instrument.min_quantity
                and spec.minimum_notional == instrument.min_notional, "RISK_AND_ORDER_CONSTRAINTS_MISMATCH")
        require(isinstance(client_order_id, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", client_order_id),
                "INVALID_CLIENT_ORDER_ID")
        plan = result.plan
        instrument.validate_size(plan.quantity, plan.entry_price)
        payload = dict(side="buy", order_type="limit_order", market=instrument.market,
                       price_per_unit=plan.entry_price, total_quantity=plan.quantity,
                       timestamp=epoch_ms(at), client_order_id=client_order_id)
        return OrderPreview(True, "DRY_RUN_ONLY", _wire_json(payload), plan, result.record, kind)
    except (ValueError, TypeError, ArithmeticError, AttributeError) as exc:
        reason = str(exc) if isinstance(exc, ExchangeBlocked) else "INVALID_ORDER_METADATA"
        record = audit.record(at=at, approved=False, reason=reason, proposal=proposal,
                              equity=equity, controls=controls, settings=settings)
        return OrderPreview(False, reason, None, None, record, kind)
