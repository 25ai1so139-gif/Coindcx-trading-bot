import unittest
from decimal import Decimal

from config import Settings
from tests.helpers import SyntheticBroker as PaperBroker
from strategies.base import Signal
from tests.helpers import candle

D = Decimal


class PaperBrokerTests(unittest.TestCase):
    def test_margin_is_reserved_and_not_charged_as_a_loss(self):
        broker = PaperBroker(Settings(fee_rate=0, slippage_rate=0, leverage=3))
        broker.process_bar(candle(), Signal.BUY)
        self.assertEqual(broker.cash, 1900)
        self.assertEqual(broker.equity(D(100)), 2000)
        broker.process_bar(candle(1), Signal.SELL)
        self.assertEqual(broker.cash, 2000)

    def test_fees_are_charged_once_on_each_fill(self):
        broker = PaperBroker(Settings(fee_rate="0.001", slippage_rate=0))
        broker.process_bar(candle(), Signal.BUY)
        broker.process_bar(candle(1), Signal.SELL)
        trade = broker.trades[0]
        self.assertEqual(trade.fees, D("0.2"))
        self.assertEqual(trade.net_pnl, D("-0.2"))
        self.assertEqual(broker.cash, D("1999.8"))
        self.assertEqual(broker.cash, broker.settings.starting_capital + trade.net_pnl)

    def test_slippage_is_adverse_on_both_sides(self):
        broker = PaperBroker(Settings(fee_rate=0, slippage_rate="0.001"))
        broker.process_bar(candle(), Signal.BUY)
        broker.process_bar(candle(1), Signal.SELL)
        trade = broker.trades[0]
        self.assertEqual(trade.entry_price, D("100.1"))
        self.assertEqual(trade.exit_price, D("99.9"))
        self.assertLess(trade.net_pnl, 0)

    def test_stop_loss_executes_on_low_even_when_close_recovers(self):
        broker = PaperBroker(Settings(fee_rate=0, slippage_rate=0))
        broker.process_bar(candle(), Signal.BUY)
        broker.process_bar(candle(1, high="105", low="95", close="104"))
        self.assertIsNone(broker.position)
        self.assertEqual(broker.trades[0].reason, "stop_loss")
        self.assertEqual(broker.trades[0].exit_price, 98)
        self.assertEqual(broker.cash, 1998)

    def test_stop_is_enforced_during_entry_candle(self):
        broker = PaperBroker(Settings(fee_rate=0, slippage_rate=0))
        broker.process_bar(candle(low="90"), Signal.BUY)
        self.assertIsNone(broker.position)
        self.assertEqual(broker.trades[0].reason, "stop_loss")

    def test_gap_through_stop_uses_worse_open_and_slippage(self):
        broker = PaperBroker(Settings(slippage_rate="0.001"))
        broker.process_bar(candle(), Signal.BUY)
        broker.process_bar(candle(1, open="90", high="91", low="89", close="90"))
        self.assertEqual(broker.trades[0].exit_price, D("89.91"))
        self.assertLess(broker.trades[0].exit_price, D("98"))

    def test_daily_loss_limit_exits_and_blocks_reentry(self):
        broker = PaperBroker(Settings(fee_rate=0, slippage_rate=0))
        broker.risk.observe(D(2000), candle().timestamp)
        broker.cash = D(1961)  # Explicit fixture: INR 39 already lost today.
        for index in range(5):
            broker.process_bar(candle(index, low="95"), Signal.BUY)
        self.assertEqual(broker.risk.halt_reason, "daily_loss_limit")
        self.assertEqual(broker.cash, 1960)
        self.assertEqual(len(broker.trades), 1)
        broker.process_bar(candle(5), Signal.BUY)
        self.assertIsNone(broker.position)
        self.assertEqual(len(broker.trades), 1)

    def test_remaining_daily_budget_reduces_position_before_entry(self):
        broker = PaperBroker(Settings(fee_rate=0, slippage_rate=0))
        broker.risk.observe(D(2000), candle().timestamp)
        broker.cash = D(1961)  # Existing realized losses during this UTC day.
        broker.process_bar(candle(low="95"), Signal.BUY)
        self.assertEqual(broker.trades[0].quantity, D("0.5"))
        self.assertEqual(broker.trades[0].exit_price, 98)
        self.assertEqual(broker.cash, 1960)

    def test_three_entries_per_day_counts_winners_and_blocks_fourth(self):
        broker = PaperBroker(Settings(fee_rate=0, slippage_rate=0))
        for index in range(3):
            broker.process_bar(candle(2 * index), Signal.BUY)
            broker.process_bar(candle(2 * index + 1, open="101", high="101", low="101", close="101"),
                               Signal.SELL)
        self.assertEqual(broker.risk.entries_today, 3)
        self.assertEqual(broker.risk.entry_block_reason, "daily_trade_limit")
        self.assertIsNone(broker.risk.halt_reason)
        broker.process_bar(candle(6), Signal.BUY)
        self.assertIsNone(broker.position)
        self.assertEqual(len(broker.trades), 3)
        broker.process_bar(candle(96), Signal.BUY)
        self.assertIsNotNone(broker.position)
        self.assertEqual(broker.risk.entries_today, 1)

    def test_third_entry_is_allowed_to_remain_open_and_exit(self):
        broker = PaperBroker(Settings(fee_rate=0, slippage_rate=0))
        for index in range(2):
            broker.process_bar(candle(2 * index), Signal.BUY)
            broker.process_bar(candle(2 * index + 1), Signal.SELL)
        broker.process_bar(candle(4), Signal.BUY)
        self.assertIsNotNone(broker.position)
        self.assertEqual(broker.risk.entries_today, 3)
        broker.process_bar(candle(5), Signal.SELL)
        self.assertIsNone(broker.position)
        self.assertEqual(len(broker.trades), 3)

    def test_stopped_entries_count_towards_daily_limit(self):
        broker = PaperBroker(Settings(fee_rate=0, slippage_rate=0))
        for index in range(4):
            broker.process_bar(candle(index, low="95"), Signal.BUY)
        self.assertEqual(len(broker.trades), 3)
        self.assertEqual(broker.risk.entries_today, 3)

    def test_unrealized_drawdown_closes_position_and_latches(self):
        broker = PaperBroker(Settings(fee_rate=0, slippage_rate=0))
        broker.process_bar(candle(), Signal.BUY)
        broker.process_bar(candle(1, open="300", high="300", low="300", close="300"))
        broker.process_bar(candle(2, open="300", high="300", low="180", close="300"))
        self.assertIsNone(broker.position)
        self.assertEqual(broker.trades[0].reason, "max_drawdown")
        self.assertEqual(broker.trades[0].exit_price, 190)
        self.assertEqual(broker.cash, 2090)
        broker.process_bar(candle(96), Signal.BUY)
        self.assertIsNone(broker.position)
        self.assertEqual(broker.risk.halt_reason, "max_drawdown")

    def test_account_trigger_reserves_exit_fee_and_slippage(self):
        broker = PaperBroker(Settings())
        broker.process_bar(candle(), Signal.BUY)
        broker.process_bar(candle(1, open="300", high="300", low="300", close="300"))
        peak = broker.risk.peak_equity
        broker.process_bar(candle(2, open="300", high="300", low="180", close="300"))
        self.assertEqual(broker.trades[0].reason, "max_drawdown")
        self.assertAlmostEqual(broker.cash, peak * D("0.95"), places=18)
        self.assertEqual(broker.risk.halt_reason, "max_drawdown")

    def test_gap_can_exceed_daily_limit_and_is_reported_without_clamping(self):
        broker = PaperBroker(Settings(fee_rate=0, slippage_rate=0))
        broker.process_bar(candle(), Signal.BUY)
        broker.process_bar(candle(1, open="50", high="50", low="50", close="50"))
        self.assertEqual(broker.cash, 1950)
        self.assertEqual(broker.trades[0].net_pnl, -50)
        self.assertEqual(broker.risk.halt_reason, "daily_loss_limit")

    def test_emergency_shutdown_closes_once_with_costs_and_never_reopens(self):
        broker = PaperBroker(Settings())
        broker.process_bar(candle(), Signal.BUY)
        broker.emergency_shutdown()
        self.assertIsNone(broker.position)
        self.assertEqual(broker.trades[0].reason, "emergency_shutdown")
        self.assertEqual(broker.trades[0].exit_price, D("99.9"))
        self.assertGreater(broker.trades[0].fees, 0)
        self.assertEqual(broker.cash, D(2000) + broker.trades[0].net_pnl)
        first_cash = broker.cash
        broker.emergency_shutdown()
        self.assertEqual(broker.cash, first_cash)
        self.assertEqual(len(broker.trades), 1)
        broker.process_bar(candle(96), Signal.BUY)
        self.assertIsNone(broker.position)
        self.assertEqual(broker.risk.entry_block_reason, "emergency_shutdown")

    def test_emergency_shutdown_before_any_bar_is_safe(self):
        broker = PaperBroker(Settings())
        broker.emergency_shutdown()
        broker.process_bar(candle(), Signal.BUY)
        self.assertEqual(broker.cash, 2000)
        self.assertEqual(broker.trades, [])

    def test_buy_does_not_stack_positions(self):
        broker = PaperBroker(Settings(fee_rate=0, slippage_rate=0))
        broker.process_bar(candle(), Signal.BUY)
        first = broker.position
        broker.process_bar(candle(1), Signal.BUY)
        self.assertIs(broker.position, first)

    def test_end_of_data_realizes_exit_fees(self):
        broker = PaperBroker(Settings(slippage_rate=0))
        last = candle()
        broker.process_bar(last, Signal.BUY)
        broker.finish(last)
        self.assertIsNone(broker.position)
        self.assertEqual(broker.trades[0].reason, "end_of_data")
        self.assertEqual(broker.cash, D("1999.8"))

    def test_duplicate_bars_and_raw_signals_are_rejected(self):
        broker = PaperBroker(Settings())
        broker.process_bar(candle())
        with self.assertRaises(ValueError):
            broker.process_bar(candle(), Signal.BUY)
        with self.assertRaises(ValueError):
            broker.process_bar(candle(1), "buy")
