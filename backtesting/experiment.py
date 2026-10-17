"""Fixed-parameter chronological evaluation; never selects a strategy on test P&L."""

import hashlib
import json
import platform
from dataclasses import asdict, replace
from pathlib import Path

from backtesting.benchmarks import benchmarks
from backtesting.datasets import BacktestBlocked, EligibleDataset, market_digest
from backtesting.costs import fixed_decimal
from backtesting.engine import simulate
from backtesting.metrics import calculate_metrics
from backtesting.splits import SplitPlan, chronological_periods
from config import Settings
from config import decimal_value
from strategies import create_strategy


def source_digest() -> str:
    root = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256()
    paths = [root / "cli.py", root / "config.py"]
    for directory in ("backtesting", "data", "paper_trading", "risk", "strategies"):
        paths.extend((root / directory).rglob("*.py"))
    for path in sorted(paths):
        relative = path.relative_to(root)
        digest.update(str(relative).replace("\\", "/").encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


@fixed_decimal
def run_experiment(dataset: EligibleDataset, settings: Settings, strategy, plan: SplitPlan, *,
                   parameter_sensitivity: tuple[dict, ...] = (), stress_multiplier=2) -> dict:
    if dataset.evidence.get("quality", {}).get("eligible") is not True:
        raise BacktestBlocked("BLOCKED: dataset lacks passing Phase 2 eligibility evidence")
    if (dataset.evidence.get("market_sha256") != market_digest(dataset.market)
            or dataset.evidence.get("kind") != dataset.market.kind):
        raise BacktestBlocked("BLOCKED: dataset differs from the eligibility evidence")
    if settings.mode != "backtest":
        raise ValueError("chronological evaluation requires backtest mode")
    if settings.starting_capital != 2000:
        raise ValueError("Phase 4 evaluation requires initial INR 2000; legacy independent simulations remain configurable")
    if strategy.name != settings.strategy:
        raise ValueError("strategy and configuration disagree")
    # Validate every candidate before executing or exposing the final test period.
    baseline_parameters = asdict(strategy)
    # Only the existing immutable baseline strategies are supported by this evaluator.
    registered = create_strategy(settings.strategy, **baseline_parameters)
    if type(strategy) is not type(registered):
        raise ValueError("evaluation requires a registered immutable baseline strategy")
    candidates = [create_strategy(settings.strategy, **parameters) for parameters in parameter_sensitivity]
    stress_multiplier = decimal_value(stress_multiplier, "stress_multiplier")
    if stress_multiplier <= 1:
        raise ValueError("stress multiplier must be greater than one")
    stressed = replace(settings, fee_rate=settings.fee_rate * stress_multiplier,
                       slippage_rate=settings.slippage_rate * stress_multiplier)
    periods = chronological_periods(dataset.market, settings, strategy.minimum_bars, plan)
    # A larger sensitivity warmup must fit BEFORE running the baseline test.
    candidate_periods = [chronological_periods(dataset.market, settings, item.minimum_bars, plan) for item in candidates]

    def evaluate(period, selected_settings, selected_strategy):
        context = dataset.risk_context
        if context is not None and context.costs is not None:
            # The declared cost sensitivity is hypothetical, not a new market quote.
            context = replace(context, costs=replace(context.costs, fee_rate=selected_settings.fee_rate,
                                                      slippage_rate=selected_settings.slippage_rate))
        replay = simulate(selected_settings, period.market, selected_strategy,
                          trade_start=period.start, risk_context=context)
        if replay.interrupted:
            raise BacktestBlocked("BLOCKED: interrupted simulation; no complete evaluation report")
        evaluation_candles = period.market.candles[period.warmup_bars:]
        return {"name": period.name, "start_inclusive": period.start, "end_exclusive": period.end,
                "sample_bars": len(evaluation_candles), "warmup_bars": period.warmup_bars,
                "warmup_start": period.market.candles[0].timestamp,
                "metrics": calculate_metrics(replay), "benchmarks": benchmarks(evaluation_candles, selected_settings),
                "simulation": asdict(replay)}

    # Development-only alternatives are explicitly excluded from test evaluation.
    sensitivity = [{"parameters": asdict(candidate), "periods": [evaluate(period, settings, candidate)
                    for period in candidate_ranges[:2]], "test_evaluated": False}
                   for candidate, candidate_ranges in zip(candidates, candidate_periods)]
    baseline = [evaluate(period, settings, strategy) for period in periods]
    stress = [evaluate(period, stressed, strategy) for period in periods]
    report = {
        "schema_version": 1, "phase": 4, "status": "COMPLETE_SYNTHETIC_ONLY" if dataset.market.kind == "synthetic" else "COMPLETE_REVIEWED_HISTORICAL",
        "currency": "INR", "symbol": dataset.market.symbol, "timeframe": settings.timeframe,
        "data": dataset.evidence, "configuration": asdict(settings), "strategy": strategy.name,
        "strategy_parameters": baseline_parameters, "split_plan": asdict(plan),
        "boundary_policy": "independent fresh INR accounts, no carried positions; prior completed candles warm indicators only; force-close at each period end with costs",
        "test_policy": "parameters fixed before evaluation; no optimizer or final-test parameter ranking; operator must preserve untouched-test discipline across runs",
        "periods": baseline, "cost_stress": {"multiplier": stress_multiplier, "assumptions": stress[0]["simulation"]["cost_assumptions"], "periods": stress},
        "parameter_sensitivity": sensitivity, "parameter_selection": "none; sensitivity is development-only and no candidate is chosen automatically",
        "reproducibility": {"python": platform.python_version(), "source_sha256": source_digest(),
                            "randomness": "none", "numeric_arithmetic": "Decimal precision 28 / ROUND_HALF_EVEN, isolated context"},
        "orders_submitted": 0, "live_trading_enabled": False, "short_entries_enabled": False,
        "limitations": [
            "SYNTHETIC FIXTURES: NOT REAL-MARKET PERFORMANCE" if dataset.market.kind == "synthetic" else "Historical provenance/liquidity is an operator attestation, not independently authenticated.",
            "No order-book/funding/spread history; fixed full fills and cost sensitivity do not establish precise execution realism.",
            "Zero fee/slippage assumptions remain zero when multiplied; configure positive rates for a useful stress test.",
            "Stops and daily thresholds can be exceeded by gaps; never clamp reported losses.",
            "Drawdown/activation telemetry has bar-level ordering, not tick timing; high-water marks omit unknown intrabar highs.",
            "Train/validation/test accounts are independent; their balances must not be added or portrayed as a continuous portfolio.",
            "INR only, one symbol per run; no regime attribution or multi-symbol concentration inference.",
            "Minimum period length is an evidence floor, not proof of statistical significance; no annualized Sharpe/volatility is estimated.",
            "Leverage is abstract collateral, not a verified exchange product; no liquidation, borrow, taxes, lot sizes or partial fills.",
            "State and safety latches are in memory per simulation; repeated runs do not share a persistent account.",
            "Reports describe the supplied history and assumptions; no metric predicts future profitability."]}
    identity = json.dumps(report, sort_keys=True, default=str, separators=(",", ":")).encode()
    report["run_id"] = hashlib.sha256(identity).hexdigest()
    return report
