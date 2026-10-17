"""Offline signal review. This module has no broker, transport, or order API."""

import json
from dataclasses import asdict, is_dataclass, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal, DecimalException
from pathlib import Path

from config import Settings
from data.loader import load_csv
from data.quality import DataPolicy, assess
from data.schema import SYMBOL, utc
from data.storage import read_csv
from risk.context import VerificationAccount
from risk import entry as risk_gate
from risk.audit import RiskAudit
from risk.proposal import EntryProposal, MarketContext
from strategies.base import Direction, InvalidDecision, Strategy, validate_decision


def verify_file(path: str | Path, settings: Settings, strategy: Strategy, *,
                as_of: datetime | None = None, symbol: str | None = None,
                timeframe: str = "15m", allow_synthetic: bool = False,
                risk_state: str | Path | None = None,
                account: VerificationAccount | None = None) -> dict:
    now = datetime.now(timezone.utc)
    audit = RiskAudit()
    proposal = controls = equity = None
    evaluation = now
    report = {
        "command": "verify", "symbol": symbol, "timeframe": timeframe,
        "strategy": strategy.name, "signal": Direction.NO_TRADE.value,
        "strategy_parameters": asdict(strategy) if is_dataclass(strategy) else {},
        "signal_timestamp": None, "entry_reference": None, "stop_loss_reference": None,
        "as_of": evaluation.isoformat(), "evaluation_mode": "historical" if as_of is not None else "current",
        "candidate": None, "risk_preview": None, "data_quality": None,
        "entry_candidate": False, "reasons": [], "warnings": [],
        "orders_submitted": 0, "live_trading_enabled": False, "currency": "INR",
        "risk_decisions": [],
        "note": "Read-only simulated-account review; this is not authorization to submit orders.",
    }

    def reject(*reasons) -> dict:
        report["reasons"].extend(reasons)
        if not audit.records:
            audit.record(at=evaluation, approved=False, reason="VERIFICATION_REJECTED",
                         proposal=proposal, equity=equity, controls=controls, settings=settings)
        report["risk_decisions"] = [asdict(record) for record in audit.records]
        return report

    try:
        evaluation = utc(as_of) if as_of is not None else now
        report["as_of"] = evaluation.isoformat()
    except (ValueError, TypeError, OverflowError) as exc:
        return reject("INVALID_EVALUATION_TIME", str(exc))
    if evaluation > now:
        return reject("FUTURE_EVALUATION_TIME")
    if timeframe != settings.timeframe:
        return reject("INVALID_TIMEFRAME")
    if symbol is not None and (not isinstance(symbol, str) or not SYMBOL.fullmatch(symbol)):
        return reject("INVALID_SYMBOL")
    try:
        market = load_csv(path, settings.min_history_bars, allow_synthetic)
        report.update(symbol=market.symbol, data_kind=market.kind)
        if symbol is not None and symbol != market.symbol:
            return reject("SYMBOL_MISMATCH")
        imported = read_csv(path)
        stored = DataPolicy(**imported.metadata["data_policy"]) if "data_policy" in imported.metadata else DataPolicy(
            min_history_bars=settings.min_history_bars)
        # Research files cannot relax real-market verification. Explicit synthetic
        # opt-in is an offline exercise and never attests real liquidity.
        policy = replace(stored, min_history_bars=max(settings.min_history_bars, stored.min_history_bars),
                         min_completeness=Decimal("1"), max_zero_volume_fraction=Decimal("0"),
                         max_staleness_minutes=min(30, stored.max_staleness_minutes),
                         require_verified_liquidity=market.kind != "synthetic")
        assessment = assess(imported.rows, imported.metadata, policy, evaluation)
        report["data_quality"] = assessment.report
        report["warnings"].extend(assessment.report["warnings"])
        if market.kind == "synthetic":
            report["warning"] = "Synthetic fixtures only; no market performance or real liquidity is established."
        if not assessment.report["eligible"]:
            return reject("DATA_INELIGIBLE", *assessment.report["reasons"])
        # The loader and quality assessment read separate snapshots. Never review
        # one dataset's quality and calculate a signal from different candles.
        from data.models import Candle
        assessed = tuple(Candle(record.timestamp, record.open, record.high, record.low,
                                record.close, record.volume) for record in assessment.completed)
        if (market.candles != assessed or market.symbol != imported.metadata["symbol"]
                or market.kind != imported.metadata["kind"]
                or market.source != imported.metadata["source"]
                or (market.kind == "historical" and imported.metadata.get("quality_reviewed") is not True)):
            return reject("DATA_CHANGED_DURING_REVIEW")
        decision = strategy.evaluate(market.candles, as_of=evaluation, symbol=market.symbol,
                                     timeframe=timeframe, stop_loss_fraction=settings.stop_loss_fraction)
        decision = validate_decision(decision, strategy=strategy.name, candles=market.candles,
                                     as_of=evaluation, symbol=market.symbol, timeframe=timeframe,
                                     stop_loss_fraction=settings.stop_loss_fraction)
        context = MarketContext.reviewed(imported.metadata, assessment.report, settings)
        proposal = EntryProposal(strategy.name, decision, market.candles, context, market.candles[-1].close)
        report.update(candidate=asdict(decision), signal_timestamp=decision.timestamp,
                      entry_reference=decision.entry_reference, stop_loss_reference=decision.stop_loss_reference)
        if decision.signal == Direction.NO_TRADE:
            risk_gate.approve_entry(settings, None, None, proposal, at=evaluation,
                                    has_open_position=False, audit=audit)
            return reject(decision.reason_code)
        if account is not None and risk_state is not None:
            return reject("AMBIGUOUS_RISK_STATE")
        if risk_state is not None:
            account = VerificationAccount.from_mapping(settings, json.loads(Path(risk_state).read_text(encoding="utf-8")))
        if account is None:
            return reject("RISK_STATE_REQUIRED")
        expected_kind = "synthetic" if market.kind == "synthetic" else "paper"
        if account.kind != expected_kind:
            return reject("ACCOUNT_DATA_KIND_MISMATCH")
        controls = account.reviewed_controls(settings, evaluation,
                                             timedelta(minutes=policy.max_staleness_minutes))
        equity = account.equity
        approval = risk_gate.approve_entry(settings, controls, equity, proposal, at=evaluation,
                                           has_open_position=account.has_open_position, audit=audit)
        if not approval.approved:
            return reject(approval.reason)
        plan = approval.plan
        report.update(signal=decision.signal.value, entry_candidate=True, risk_preview=asdict(plan),
                      entry_reference=plan.entry_price, stop_loss_reference=plan.stop_price)
        report["reasons"].append(decision.reason_code)
        report["risk_decisions"] = [asdict(record) for record in audit.records]
        return report
    except InvalidDecision as exc:
        return reject("INVALID_STRATEGY_DECISION", str(exc))
    except (OSError, ValueError, TypeError, OverflowError, DecimalException) as exc:
        return reject("VERIFICATION_REJECTED", str(exc))
