from dataclasses import dataclass
from decimal import Decimal

from config import Settings
from data.loader import MarketData
from data.models import Candle
from paper_trading.broker import PaperBroker, Trade
from strategies.base import Signal, Strategy


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


def simulate(settings: Settings, market: MarketData, strategy: Strategy) -> SimulationResult:
    if market.quote_currency != settings.account_currency:
        raise ValueError("market quote currency does not match account currency")
    minimum = max(settings.min_history_bars, strategy.minimum_bars)
    if len(market.candles) < minimum:
        raise ValueError(f"insufficient history: need {minimum} bars")
    broker = PaperBroker(settings)
    pending = Signal.HOLD
    history: list[Candle] = []
    processed = 0
    interrupted = False
    try:
        for index, candle in enumerate(market.candles):
            # A previous closed-bar decision executes at this bar's open.
            broker.process_bar(candle, pending)
            processed += 1
            history.append(candle)
            if len(history) > strategy.minimum_bars:
                del history[0]
            pending = strategy.signal(history) if index + 1 >= minimum else Signal.HOLD
        broker.finish(market.candles[-1])
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
    )
