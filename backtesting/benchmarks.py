"""Comparable-period descriptive references, without strategy risk controls."""

from decimal import Decimal, ROUND_DOWN
from typing import Sequence

from backtesting.costs import CostModel
from config import Settings
from data.models import Candle


def benchmarks(candles: Sequence[Candle], settings: Settings) -> dict:
    if not candles:
        raise ValueError("benchmark needs observed evaluation-period prices")
    costs = CostModel.from_settings(settings)
    entry, exit_fill = costs.entry_fill(candles[0].open), costs.exit_fill(candles[-1].close)
    quantity = (settings.starting_capital / (entry * (1 + settings.fee_rate))).quantize(
        Decimal("0.00000001"), rounding=ROUND_DOWN)
    fees = costs.fee(quantity, entry) + costs.fee(quantity, exit_fill)
    pnl = quantity * (exit_fill - entry) - fees
    return {"cash_only": {"final_equity_inr": settings.starting_capital, "net_pnl_inr": Decimal("0"),
                          "assumption": "no interest or inflation adjustment"},
            "buy_and_hold": {"initial_equity_inr": settings.starting_capital,
                             "final_equity_inr": settings.starting_capital + pnl,
                             "net_pnl_inr": pnl, "net_pnl_percent": pnl / settings.starting_capital * 100,
                             "fees_inr": fees,
                             "slippage_inr": quantity * (entry - candles[0].open + candles[-1].close - exit_fill),
                             "quantity": quantity, "entry_price": entry, "exit_price": exit_fill,
                             "assumption": "1x unleveraged full affordable capital, same period/costs; NO stops or daily limits; different risk exposure"}}
