from datetime import datetime, timedelta, timezone
from decimal import Decimal

from data.models import Candle

START = datetime(2024, 1, 1, tzinfo=timezone.utc)


def candle(index: int = 0, open: str = "100", high: str = "100",
           low: str = "100", close: str = "100") -> Candle:
    return Candle(START + timedelta(minutes=15 * index), Decimal(open), Decimal(high),
                  Decimal(low), Decimal(close), Decimal("1000"))


def synthetic_proposal(settings, at, reference=Decimal("100"), *, symbol="SYNTHETIC-INR"):
    """Explicit fabricated prior history for broker unit tests, never market evidence."""
    from risk.proposal import EntryProposal, MarketContext
    from strategies.base import Direction, StrategyDecision
    records = tuple(Candle(at - timedelta(minutes=15 * (settings.min_history_bars - index)),
                           reference, reference, reference, reference, Decimal("1000"))
                    for index in range(settings.min_history_bars))
    decision = StrategyDecision(Direction.LONG, at, "synthetic_fixture", symbol, "15m", reference,
                                reference * (1 - settings.stop_loss_fraction),
                                "SYNTHETIC_FIXTURE", "Explicit synthetic unit-test proposal")
    return EntryProposal(decision.strategy, decision, records,
                         MarketContext.synthetic(symbol, settings, allow_synthetic=True), reference)


from paper_trading.broker import PaperBroker as ProductionBroker


class SyntheticBroker(ProductionBroker):
    """Test adapter supplies explicit context; production broker has no such default."""

    def process_bar(self, bar, signal=None, *, entry=None):
        from strategies.base import Signal
        signal = Signal.HOLD if signal is None else signal
        if signal == Signal.BUY and entry is None:
            entry = synthetic_proposal(self.settings, bar.timestamp, bar.open)
        return super().process_bar(bar, signal, entry=entry)
