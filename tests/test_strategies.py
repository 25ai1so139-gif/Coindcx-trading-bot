import unittest
from decimal import Decimal

from strategies.base import Signal
from strategies.momentum import Momentum
from strategies.sma_cross import SmaCross
from tests.helpers import candle


def history(prices):
    return [candle(index, open=str(price), high=str(price), low=str(price), close=str(price))
            for index, price in enumerate(prices)]


class StrategyTests(unittest.TestCase):
    def test_sma_buy_and_sell_crossovers(self):
        strategy = SmaCross(fast=2, slow=3)
        self.assertEqual(strategy.signal(history([100, 100, 100, 110])), Signal.BUY)
        self.assertEqual(strategy.signal(history([100, 100, 100, 90])), Signal.SELL)

    def test_momentum_uses_closed_history(self):
        strategy = Momentum(lookback=1, threshold=Decimal("0.01"))
        self.assertEqual(strategy.signal(history([100, 102])), Signal.BUY)
        self.assertEqual(strategy.signal(history([100, 98])), Signal.SELL)
        self.assertEqual(strategy.signal(history([100, 100])), Signal.HOLD)

    def test_insufficient_strategy_history_holds(self):
        for strategy in (SmaCross(), Momentum()):
            self.assertEqual(strategy.signal(history([100])), Signal.HOLD)

    def test_invalid_strategy_parameters_are_rejected(self):
        for create in (lambda: SmaCross(20, 5), lambda: SmaCross(1.5, 5),
                       lambda: Momentum(0), lambda: Momentum(threshold=Decimal("NaN"))):
            with self.assertRaises(ValueError):
                create()
