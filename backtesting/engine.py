from dataclasses import dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal

from config import Settings
from data.loader import MarketData
from data.models import Candle
from paper_trading.broker import EquityObservation, PaperBroker, RiskEvent, Trade
from backtesting.costs import CostModel, fixed_decimal
from data.schema import utc
from strategies.base import Direction, Signal, Strategy, StrategyDecision, replay_action, validate_decision, validate_history
from risk.audit import RiskRecord
from risk.proposal import EntryProposal, MarketContext
from risk import entry as risk_gate


@dataclass(frozen=True, slots=True)
class SimulationResult:
    mode: str
    symbol: str
    data_kind: str
    bars: int
    starting_capital: Decimal
    ending_equity: Decimal
    net_pnl: Decimal
    total_fees: Decimal
    max_drawdown: Decimal
    halt_reason: str | None
    entry_block_reason: str | None
    entries_today: int
    interrupted: bool
    trades: tuple[Trade, ...]
    equity_observations: tuple[EquityObservation, ...]
    risk_events: tuple[RiskEvent, ...]
    exposed_bars: int
    cost_assumptions: dict
    risk_decisions: tuple[RiskRecord, ...] = ()


@fixed_decimal
def simulate(settings: Settings, market: MarketData, strategy: Strategy, *,
             trade_start: datetime | None = None,
             risk_context: MarketContext | None = None) -> SimulationResult:
    """Replay once; optional earlier candles warm indicators without trading.

    Each explicit trade_start starts a fresh account. Earlier candles can supply
    a decision at that boundary; no position or pending order is carried in.
    """
    if market.quote_currency != settings.account_currency:
        raise ValueError("market quote currency does not match account currency")
    minimum = max(settings.min_history_bars, strategy.minimum_bars)
    if len(market.candles) < minimum:
        raise ValueError(f"insufficient history: need {minimum} bars")
    candles = validate_history(market.candles, datetime.now(timezone.utc))
    if risk_context is None and market.kind == "synthetic":
        # Explicit synthetic MarketData is a numerical fixture, never real eligibility.
        risk_context = MarketContext.synthetic(market.symbol, settings, allow_synthetic=True)
    if risk_context is not None and (risk_context.symbol != market.symbol or risk_context.kind != market.kind):
        raise ValueError("risk context does not match market identity")
    start_index = 0
    if trade_start is not None:
        trade_start = utc(trade_start)
        starts = [index for index, bar in enumerate(candles) if bar.timestamp == trade_start]
        if not starts or starts[0] < minimum:
            raise ValueError("trade_start must be a candle boundary after sufficient preceding warmup")
        start_index = starts[0]
    broker = PaperBroker(settings)
    pending = Signal.HOLD
    proposal = None
    history: list[Candle] = []
    processed = 0
    interrupted = False
    try:
        for index, candle in enumerate(candles):
            # A previous closed-bar decision executes at this bar's open.
            if index >= start_index:
                entry = replace(proposal, reference_price=candle.open) if proposal is not None else None
                broker.process_bar(candle, pending, entry=entry)
                processed += 1
            history.append(candle)
            if len(history) > minimum:
                del history[0]
            if index + 1 >= minimum:
                if callable(getattr(strategy, "evaluate", None)):
                    visible = history[-strategy.minimum_bars:]
                    decision = strategy.evaluate(visible, as_of=candle.closed_at,
                                                 symbol=market.symbol, timeframe=settings.timeframe,
                                                 stop_loss_fraction=settings.stop_loss_fraction)
                    try:
                        decision = validate_decision(decision, strategy=strategy.name, candles=visible,
                                                     as_of=candle.closed_at, symbol=market.symbol,
                                                     timeframe=settings.timeframe,
                                                     stop_loss_fraction=settings.stop_loss_fraction)
                    except ValueError:
                        refused = EntryProposal(strategy.name, decision, tuple(history), risk_context, candle.close)
                        risk_gate.approve_entry(settings, broker.risk, broker.risk.last_equity, refused,
                                                at=candle.closed_at, has_open_position=broker.position is not None,
                                                audit=broker.risk_audit)
                        raise
                    pending = replay_action(decision.signal)
                else:
                    # Preserve existing local strategies implementing the old protocol.
                    pending = strategy.signal(history[-strategy.minimum_bars:])
                    if not isinstance(pending, Signal):
                        raise ValueError("legacy strategy must return a Signal")
                    direction = {Signal.BUY: Direction.LONG, Signal.SELL: Direction.SHORT,
                                 Signal.HOLD: Direction.NO_TRADE}[pending]
                    entry_ref = candle.close if direction != Direction.NO_TRADE else None
                    stop_ref = (entry_ref * (1 - settings.stop_loss_fraction if direction == Direction.LONG
                                            else 1 + settings.stop_loss_fraction)) if entry_ref else None
                    decision = StrategyDecision(direction, candle.closed_at, "legacy", market.symbol, settings.timeframe,
                                                entry_ref, stop_ref, "LEGACY_SIGNAL", "Offline legacy adapter")
                proposal = EntryProposal(decision.strategy, decision, tuple(history), risk_context, candle.close)
            else:
                pending = Signal.HOLD
        broker.finish(candles[-1])
    except KeyboardInterrupt:
        broker.emergency_shutdown()
        interrupted = True
    except Exception:
        broker.emergency_shutdown()
        raise
    return SimulationResult(
        settings.mode, market.symbol, market.kind, processed,
        settings.starting_capital, broker.cash, broker.cash - settings.starting_capital,
        sum((trade.fees for trade in broker.trades), Decimal("0")),
        broker.risk.max_observed_drawdown, broker.risk.halt_reason,
        broker.risk.entry_block_reason, broker.risk.entries_today, interrupted, tuple(broker.trades),
        tuple(broker.equity_observations), tuple(broker.risk_events), broker.exposed_bars,
        CostModel.from_settings(settings).assumptions(),
        tuple(broker.risk_audit.records),
    )
