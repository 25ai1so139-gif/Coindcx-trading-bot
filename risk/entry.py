"""The mandatory, read-only gate for every supported simulated entry."""

from dataclasses import dataclass, fields
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from config import Settings, decimal_value
from backtesting.costs import fixed_decimal
from data.schema import SYMBOL, utc
from risk.audit import RiskAudit, RiskRecord
from risk.controls import RiskControls
from risk.proposal import CostAssumptions, EntryProposal, InstrumentSpec, MarketContext
from risk.sizing import PositionPlan, size_position
from strategies.base import Direction, validate_decision, validate_history


@dataclass(frozen=True, slots=True)
class RiskDecision:
    approved: bool
    reason: str
    plan: PositionPlan | None
    record: RiskRecord


class Rejected(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise Rejected(code)


@fixed_decimal
def approve_entry(settings: Settings, controls: RiskControls | None, equity,
                  proposal: EntryProposal | None, *, at, has_open_position: bool,
                  audit: RiskAudit, execution_ready: bool = True) -> RiskDecision:
    """Revalidate evidence and sizing; log BEFORE any caller may use a plan.

    The broker calls this immediately before its sole position-open mutation.
    A bare sizing result, previously accepted proposal or old approval is not
    permission to open a position. Account state is never mutated by this review.
    """
    if not isinstance(audit, RiskAudit):
        raise ValueError("RISK_AUDIT_REQUIRED")
    plan = None
    budget = None
    try:
        require(isinstance(settings, Settings), "INVALID_SETTINGS")
        try:
            Settings(**{field.name: getattr(settings, field.name) for field in fields(Settings)})
        except (ValueError, TypeError, ArithmeticError):
            raise Rejected("INVALID_SETTINGS")
        require(settings.starting_capital == 2000, "INITIAL_CAPITAL_MUST_BE_2000")
        require(settings.risk_per_trade <= Decimal("0.005"), "INITIAL_RISK_PERCENT_EXCEEDS_HALF_PERCENT")
        require(settings.daily_loss_limit <= Decimal("0.02"), "DAILY_PERCENT_LIMIT_EXCEEDS_2_PERCENT")
        try:
            stamp = utc(at)
        except (ValueError, TypeError, OverflowError):
            raise Rejected("INVALID_TIMESTAMP")
        require(stamp <= datetime.now(timezone.utc), "FUTURE_EVALUATION_TIME")
        require(isinstance(proposal, EntryProposal), "ENTRY_PROPOSAL_REQUIRED")
        require(isinstance(proposal.strategy, str) and SYMBOL.fullmatch(proposal.strategy), "INVALID_STRATEGY")
        market = proposal.market
        require(isinstance(market, MarketContext), "MARKET_CONTEXT_REQUIRED")
        require(isinstance(market.symbol, str) and SYMBOL.fullmatch(market.symbol), "INVALID_SYMBOL")
        require(market.timeframe == settings.timeframe == "15m" and market.quote_currency == "INR", "INVALID_MARKET")
        require(market.kind in {"synthetic", "historical"}, "INVALID_DATA_KIND")
        require(market.eligible is True, "MARKET_INELIGIBLE")
        require(type(market.max_staleness_minutes) is int and 0 <= market.max_staleness_minutes <= 30,
                "INVALID_FRESHNESS_POLICY")
        require(market.kind == "synthetic" or (market.quality_reviewed is True and market.liquidity_verified is True),
                "UNVERIFIED_MARKET_ELIGIBILITY")
        try:
            candles = validate_history(proposal.candles, stamp)
        except (ValueError, TypeError, ArithmeticError, AttributeError):
            raise Rejected("INVALID_OR_INCOMPLETE_MARKET_DATA")
        require(len(candles) >= settings.min_history_bars, "INSUFFICIENT_HISTORY")
        require(stamp - candles[-1].closed_at <= timedelta(minutes=market.max_staleness_minutes), "STALE_MARKET_DATA")
        try:
            decision = validate_decision(proposal.decision, strategy=proposal.strategy, candles=candles,
                                         as_of=stamp, symbol=market.symbol, timeframe=market.timeframe,
                                         stop_loss_fraction=settings.stop_loss_fraction)
        except (ValueError, TypeError, ArithmeticError, AttributeError):
            raise Rejected("INVALID_SIGNAL_OR_STOP")
        require(decision.signal != Direction.SHORT, "SHORT_ENTRY_UNSUPPORTED")
        require(decision.signal == Direction.LONG, "NO_TRADE")
        require(type(has_open_position) is bool, "invalid_position_state")
        require(not has_open_position, "one_open_position")
        require(isinstance(controls, RiskControls), "RISK_STATE_REQUIRED")
        require(controls.settings == settings, "risk_settings_mismatch")
        require(controls.day == stamp.date(), "risk_state_day_mismatch")
        require(type(controls.entries_today) is int and 0 <= controls.entries_today <= settings.max_trades_per_day,
                "INVALID_ENTRY_COUNT")
        require(all(type(getattr(controls, name)) is bool for name in
                    ("daily_halted", "drawdown_halted", "emergency_halted")), "INVALID_HALT_STATE")
        equity = decimal_value(equity, "equity")
        require(equity > 0, "INSUFFICIENT_EQUITY")
        peak, daily_start = (decimal_value(getattr(controls, name), name) for name in ("peak_equity", "day_start_equity"))
        require(daily_start > 0 and peak >= max(settings.starting_capital, daily_start, equity), "INVALID_ACCOUNT_EQUITY")
        require(decimal_value(controls.last_equity, "last_equity") == equity, "STALE_ACCOUNT_EQUITY")
        require(not controls.emergency_halted, "emergency_shutdown")
        require(not controls.drawdown_halted and equity > peak * (1 - settings.max_drawdown), "max_drawdown")
        require(not controls.daily_halted and equity > daily_start - controls.daily_loss_budget, "daily_loss_limit")
        require(controls.entries_today < settings.max_trades_per_day, "daily_trade_limit")
        require(execution_ready is True, "EXECUTION_CONTEXT_REQUIRED")
        instrument = market.instrument
        require(isinstance(instrument, InstrumentSpec), "INSTRUMENT_DETAILS_REQUIRED")
        require(instrument.symbol == market.symbol, "INSTRUMENT_SYMBOL_MISMATCH")
        require(type(instrument.verified) is bool, "INVALID_INSTRUMENT")
        if market.kind == "historical":
            require(instrument.verified is True and instrument.product == "spot", "UNSUPPORTED_OR_UNVERIFIED_INSTRUMENT")
            require(settings.leverage == 1, "UNSUPPORTED_REAL_MARKET_LEVERAGE")
        else:
            require(instrument.product == "abstract_synthetic", "INVALID_SYNTHETIC_INSTRUMENT")
        leverage_max = decimal_value(instrument.max_leverage, "instrument max leverage")
        require(1 <= settings.leverage <= leverage_max <= 3, "LEVERAGE_LIMIT")
        step = decimal_value(instrument.quantity_step, "quantity_step")
        min_qty = decimal_value(instrument.minimum_quantity, "minimum_quantity")
        min_notional = decimal_value(instrument.minimum_notional, "minimum_notional")
        require(step > 0 and min_qty >= 0 and min_notional >= 0, "INVALID_INSTRUMENT_CONSTRAINTS")
        require(market.kind == "synthetic" or (min_qty > 0 and min_notional > 0), "INSTRUMENT_MINIMUMS_REQUIRED")
        costs = market.costs
        require(isinstance(costs, CostAssumptions) and costs.declared is True, "COST_ASSUMPTIONS_REQUIRED")
        require(decimal_value(costs.fee_rate, "fee_rate") == settings.fee_rate
                and decimal_value(costs.slippage_rate, "slippage_rate") == settings.slippage_rate, "COST_ASSUMPTIONS_MISMATCH")
        reference = decimal_value(proposal.reference_price, "reference_price")
        require(reference > 0, "INVALID_REFERENCE_PRICE")
        require(reference > decision.stop_loss_reference, "STOP_ALREADY_BREACHED")
        floor, _ = controls.equity_floor
        budget = min(equity * settings.risk_per_trade, settings.max_planned_risk, Decimal("20"), equity - floor)
        require(budget > 0, "NO_REMAINING_RISK_BUDGET")
        try:
            plan = size_position(settings, equity, reference, remaining_risk_budget=equity - floor,
                                 quantity_step=step, minimum_quantity=min_qty, minimum_notional=min_notional)
            require(isinstance(plan, PositionPlan), "INVALID_POSITION_PLAN")
            for field in fields(PositionPlan):
                value = decimal_value(getattr(plan, field.name), field.name)
                require(value >= 0 if field.name == "entry_fee" else value > 0, "INVALID_POSITION_PLAN")
            expected_entry = reference * (1 + settings.slippage_rate)
            stop_fill = plan.stop_price * (1 - settings.slippage_rate)
            actual_loss = plan.quantity * (plan.entry_price - stop_fill) + plan.entry_fee + plan.quantity * stop_fill * settings.fee_rate
            require(plan.entry_price == expected_entry and 0 < plan.stop_price < plan.entry_price
                    and plan.stop_price == plan.entry_price * (1 - settings.stop_loss_fraction), "INVALID_POSITION_STOP")
            require(plan.quantity % step == 0 and plan.quantity >= min_qty and plan.notional >= min_notional, "INSTRUMENT_SIZE_CONSTRAINTS")
            require(plan.notional == plan.quantity * plan.entry_price and plan.margin == plan.notional / settings.leverage,
                    "INVALID_MARGIN_OR_NOTIONAL")
            require(plan.margin <= min(settings.margin_amount, equity * settings.max_margin_fraction)
                    and plan.margin + plan.entry_fee <= equity, "INSUFFICIENT_MARGIN")
            require(plan.entry_fee == plan.notional * settings.fee_rate, "INVALID_FEES")
            require(plan.planned_stop_risk <= budget and actual_loss <= budget, "PLANNED_RISK_LIMIT")
            require(abs(plan.planned_stop_risk - actual_loss) <= Decimal("1e-20"), "INCONSISTENT_PLANNED_RISK")
        except Rejected:
            raise
        except (ValueError, TypeError, ArithmeticError, AttributeError):
            raise Rejected("POSITION_SIZING_UNAVAILABLE")
        reason = "APPROVED"
    except Rejected as exc:
        reason = str(exc)
    except (ValueError, TypeError, ArithmeticError, AttributeError, OverflowError):
        reason = "INVALID_RISK_INPUT"
    record = audit.record(at=at, approved=reason == "APPROVED", reason=reason,
                          proposal=proposal, equity=equity, controls=controls, plan=plan,
                          permitted_risk=budget, settings=settings)
    return RiskDecision(reason == "APPROVED", reason, plan if reason == "APPROVED" else None, record)


def entry_plan(settings, controls, equity, reference_price, has_open_position, *, proposal=None, at=None, audit=None):
    """Compatibility name; missing rich context can no longer produce a plan."""
    if audit is None:
        raise ValueError("ENTRY_PROPOSAL_AND_AUDIT_REQUIRED")
    if not isinstance(proposal, EntryProposal) or proposal.reference_price != reference_price:
        proposal = None
    result = approve_entry(settings, controls, equity, proposal, at=at,
                           has_open_position=has_open_position, audit=audit)
    if not result.approved:
        raise ValueError(result.reason)
    return result.plan
