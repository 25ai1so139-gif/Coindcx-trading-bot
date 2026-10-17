"""Phase 4 deterministic synthetic accounting/execution tests, not market results."""

import unittest
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from backtesting.benchmarks import benchmarks
from backtesting.costs import CostModel
from backtesting.engine import SimulationResult, simulate
from backtesting.metrics import calculate_metrics
from config import Settings
from data.loader import MarketData
from paper_trading.broker import EquityObservation, RiskEvent, Trade
from tests.helpers import SyntheticBroker as PaperBroker
from strategies.base import Signal
from tests.helpers import START, candle

D = Decimal


class Buy:
    minimum_bars = 1

    def signal(self, candles):
        return Signal.BUY


def market(bars):
    return MarketData("SYNTHETIC-INR", "INR", "synthetic", "synthetic unit fixture", tuple(bars))


def observation(index, equity):
    return EquityObservation(START + timedelta(minutes=15 * index), "synthetic_fixture", D(equity),
                             D(equity), D(equity) - 2000, D(0), D(0), D(0), D(0))


def fixture_trade(index, net):
    # Synthetic closed-trade ledger, deliberately independent of sizing implementation.
    return Trade(START + timedelta(minutes=30 * index), START + timedelta(minutes=30 * index + 15),
                 D(1), D(100), D(1), D(100), D(102) + D(net), D(net) + 2, D(2), D(net),
                 "synthetic_fixture", D(99), D(102) + D(net), D(1), D(100), D(3))


def metric_fixture(nets=(20, -10, -5)):
    trades = tuple(fixture_trade(index, net) for index, net in enumerate(nets))
    pnl = sum((trade.net_pnl for trade in trades), D(0))
    return SimulationResult("backtest", "SYNTHETIC-INR", "synthetic", 4, D(2000), D(2000) + pnl,
                            pnl, D(2 * len(trades)), D(0), None, None, len(trades), False, trades,
                            tuple(observation(index, equity) for index, equity in enumerate((2000, 2020, 1990, 2005))),
                            (), 2, CostModel.from_settings(Settings()).assumptions())


class CostAndAccountingTests(unittest.TestCase):
    def test_cost_assumptions_are_explicit_and_unverified(self):
        costs = CostModel.from_settings(Settings(fee_rate="0.002", slippage_rate="0.003"))
        self.assertEqual(costs.entry_fill(D(100)), D("100.3"))
        self.assertEqual(costs.exit_fill(D(100)), D("99.7"))
        self.assertEqual(costs.fee(D(2), D("100.3")), D("0.4012"))
        self.assertFalse(costs.assumptions()["schedule_verified"])
        self.assertIn("not modeled", costs.assumptions()["funding"])

    def test_reference_pnl_minus_fees_and_slippage_equals_cash_pnl(self):
        broker = PaperBroker(Settings(fee_rate="0.002", slippage_rate="0.003", leverage=3))
        broker.process_bar(candle(), Signal.BUY)
        broker.process_bar(candle(1, open="105", high="105", low="105", close="105"), Signal.SELL)
        trade = broker.trades[0]
        self.assertEqual(trade.entry_price, D("100.3"))
        self.assertEqual(trade.exit_price, D("104.685"))
        self.assertEqual(trade.fees, trade.quantity * (D("100.3") + D("104.685")) * D("0.002"))
        self.assertEqual(trade.slippage, trade.quantity * (D("0.3") + D("0.315")))
        reference_pnl = trade.quantity * D(5)
        self.assertAlmostEqual(reference_pnl - trade.fees - trade.slippage, trade.net_pnl, places=20)
        self.assertAlmostEqual(broker.cash - 2000, trade.net_pnl, places=20)

    def test_every_equity_sample_reconciles_realized_and_unrealized(self):
        broker = PaperBroker(Settings())
        broker.process_bar(candle(), Signal.BUY)
        broker.process_bar(candle(1, open="105", high="106", low="104", close="106"))
        open_sample = broker.equity_observations[-1]
        self.assertLess(open_sample.realized_pnl, 0)  # entry fee already paid
        self.assertGreater(open_sample.unrealized_pnl, 0)
        broker.finish(broker.last_candle)
        for sample in broker.equity_observations:
            self.assertAlmostEqual(sample.equity, 2000 + sample.realized_pnl + sample.unrealized_pnl, places=20)
        self.assertEqual(broker.equity_observations[-1].unrealized_pnl, 0)

    def test_margin_and_notional_are_separate_and_leverage_cannot_exceed_three(self):
        broker = PaperBroker(Settings(fee_rate=0, slippage_rate=0, leverage=3))
        broker.process_bar(candle(), Signal.BUY)
        plan = broker.position.plan
        self.assertEqual(plan.margin, 100)
        self.assertEqual(plan.notional, 300)
        self.assertEqual(broker.cash, 1900)
        with self.assertRaises(ValueError):
            Settings(leverage="3.0001")

    def test_adverse_gap_and_stop_costs_are_not_clamped(self):
        broker = PaperBroker(Settings())
        broker.process_bar(candle(), Signal.BUY)
        broker.process_bar(candle(1, open="50", high="51", low="49", close="50"))
        trade = broker.trades[0]
        self.assertEqual(trade.exit_reference, 50)
        self.assertEqual(trade.exit_price, D("49.95"))
        self.assertLess(trade.net_pnl, -40)
        self.assertTrue(broker.risk.daily_halted)
        self.assertEqual(sum(event.reason == "daily_loss_limit" for event in broker.risk_events), 1)

    def test_intrabar_stop_reference_and_slippage_are_recorded(self):
        broker = PaperBroker(Settings())
        broker.process_bar(candle(low="90"), Signal.BUY)
        trade = broker.trades[0]
        self.assertEqual(trade.exit_reference, trade.entry_price * D("0.98"))
        self.assertEqual(trade.exit_price, trade.exit_reference * D("0.999"))
        self.assertAlmostEqual(-trade.net_pnl, trade.planned_stop_risk, places=20)

    def test_risk_activation_telemetry_does_not_clear_halts(self):
        broker = PaperBroker(Settings(fee_rate=0, slippage_rate=0))
        for index in range(4):
            broker.process_bar(candle(index, low="90"), Signal.BUY)
        self.assertEqual(len(broker.trades), 3)
        self.assertEqual(sum(event.reason == "daily_trade_limit" for event in broker.risk_events), 1)
        broker.emergency_shutdown()
        broker.process_bar(candle(96), Signal.BUY)
        self.assertIsNone(broker.position)
        self.assertEqual(broker.risk.halt_reason, "emergency_shutdown")
        self.assertEqual(sum(event.reason == "emergency_shutdown" for event in broker.risk_events), 1)

    def test_daily_halt_activations_are_separate_across_utc_days(self):
        broker = PaperBroker(Settings(fee_rate=0, slippage_rate=0))
        for index in (0, 96):
            broker.process_bar(candle(index), Signal.BUY)
            broker.process_bar(candle(index + 1, open="50", high="50", low="50", close="50"))
        self.assertEqual(sum(event.reason == "daily_loss_limit" for event in broker.risk_events), 2)
        self.assertEqual(broker.risk.entries_today, 1)


class PeriodReplayTests(unittest.TestCase):
    def setUp(self):
        self.settings = Settings(min_history_bars=200, fee_rate=0, slippage_rate=0)
        self.bars = tuple(candle(index) for index in range(205))

    def test_past_warmup_can_only_fill_at_evaluation_open(self):
        bars = self.bars[:200] + tuple(candle(index, open="110", high="110", low="110", close="110") for index in range(200, 205))
        result = simulate(self.settings, market(bars), Buy(), trade_start=bars[200].timestamp)
        self.assertEqual(result.bars, 5)
        self.assertEqual(len(result.trades), 1)
        self.assertEqual(result.trades[0].opened_at, bars[200].timestamp)
        self.assertEqual(result.trades[0].entry_price, 110)
        self.assertEqual(result.trades[0].closed_at, bars[-1].closed_at)
        self.assertEqual(result.trades[0].reason, "end_of_data")

    def test_all_decision_inputs_are_completed_at_decision_time(self):
        seen = []
        class Inspect(Buy):
            def signal(self, history):
                seen.append(tuple(history))
                return Signal.BUY
        simulate(self.settings, market(self.bars), Inspect(), trade_start=self.bars[200].timestamp)
        self.assertEqual([items[-1].timestamp for items in seen], [bar.timestamp for bar in self.bars[199:]])
        self.assertTrue(all(len(items) == 1 for items in seen))

    def test_changing_future_prices_cannot_change_an_earlier_fill(self):
        first = simulate(self.settings, market(self.bars), Buy(), trade_start=self.bars[200].timestamp)
        changed = self.bars[:204] + (candle(204, open="120", high="120", low="120", close="120"),)
        second = simulate(self.settings, market(changed), Buy(), trade_start=changed[200].timestamp)
        self.assertEqual(first.trades[0].opened_at, second.trades[0].opened_at)
        self.assertEqual(first.trades[0].entry_price, second.trades[0].entry_price)
        self.assertEqual(first.equity_observations[:4], second.equity_observations[:4])

    def test_warmup_is_not_traded_and_accounts_start_fresh(self):
        for _ in range(2):
            result = simulate(self.settings, market(self.bars), Buy(), trade_start=self.bars[200].timestamp)
            self.assertEqual(result.entries_today, 1)
            self.assertEqual(result.starting_capital, 2000)
            self.assertEqual(result.equity_observations[0].timestamp, self.bars[200].timestamp)

    def test_invalid_start_or_insufficient_warmup_is_blocked_before_broker(self):
        for stamp in (self.bars[199].timestamp, self.bars[200].timestamp + timedelta(minutes=1), self.bars[-1].closed_at):
            with self.subTest(stamp=stamp), patch("backtesting.engine.PaperBroker", side_effect=AssertionError):
                with self.assertRaises(ValueError):
                    simulate(self.settings, market(self.bars), Buy(), trade_start=stamp)

    def test_duplicate_or_gap_input_is_blocked_before_broker(self):
        for bars in (self.bars[:201] + self.bars[200:], self.bars[:201] + self.bars[202:]):
            with self.subTest(bars=len(bars)), patch("backtesting.engine.PaperBroker", side_effect=AssertionError):
                with self.assertRaises(ValueError):
                    simulate(self.settings, market(bars), Buy(), trade_start=self.bars[200].timestamp)

    def test_incomplete_input_is_blocked_before_broker(self):
        with patch("backtesting.engine.datetime") as clock, patch("backtesting.engine.PaperBroker", side_effect=AssertionError):
            clock.now.return_value = self.bars[-1].timestamp + timedelta(minutes=1)
            with self.assertRaises(ValueError):
                simulate(self.settings, market(self.bars), Buy(), trade_start=self.bars[200].timestamp)

    def test_identical_replay_is_exactly_reproducible(self):
        one = simulate(self.settings, market(self.bars), Buy(), trade_start=self.bars[200].timestamp)
        two = simulate(self.settings, market(self.bars), Buy(), trade_start=self.bars[200].timestamp)
        self.assertEqual(one, two)

    def test_replay_is_independent_of_ambient_decimal_precision(self):
        from decimal import localcontext
        with localcontext() as context:
            context.prec = 8
            low = simulate(self.settings, market(self.bars), Buy(), trade_start=self.bars[200].timestamp)
            self.assertEqual(context.prec, 8)
        normal = simulate(self.settings, market(self.bars), Buy(), trade_start=self.bars[200].timestamp)
        self.assertEqual(low, normal)


class MetricTests(unittest.TestCase):
    def test_independent_trade_ledger_metrics(self):
        metric = calculate_metrics(metric_fixture())
        self.assertEqual(metric["net_pnl_inr"], 5)
        self.assertEqual(metric["final_equity_inr"], 2005)
        self.assertEqual(metric["net_pnl_percent"], D("0.25"))
        self.assertEqual((metric["gross_profit_inr"], metric["gross_loss_inr"]), (20, 15))
        self.assertEqual(metric["profit_factor"], D(20) / 15)
        self.assertEqual(metric["win_rate_percent"], D(1) / 3 * 100)
        self.assertEqual(metric["average_win_inr"], 20)
        self.assertEqual(metric["average_loss_inr"], D("7.5"))
        self.assertEqual(metric["expectancy_per_trade_inr"], D(5) / 3)
        self.assertEqual(metric["maximum_consecutive_losses"], 2)
        self.assertEqual(metric["fees_inr"], 6)
        self.assertEqual(metric["slippage_inr"], 3)
        self.assertEqual(metric["reference_price_pnl_before_costs_inr"] - 6 - 3, 5)

    def test_drawdown_uses_equity_peak_including_unrealized_samples(self):
        metric = calculate_metrics(metric_fixture())
        self.assertEqual(metric["max_drawdown_inr"], 30)
        self.assertEqual(metric["max_drawdown_percent"], D(30) / 2020 * 100)
        self.assertEqual(metric["exposure_bar_fraction"], D("0.5"))

    def test_zero_trades_and_zero_losses_are_undefined_safely(self):
        for nets in ((), (10,), (0,)):
            with self.subTest(nets=nets):
                metric = calculate_metrics(metric_fixture(nets))
                self.assertIsNone(metric["profit_factor"])
                self.assertIsNone(metric["average_loss_inr"])
                self.assertIsNone(metric["sharpe_ratio"])
                if not nets:
                    self.assertIsNone(metric["win_rate_percent"])
                    self.assertIsNone(metric["expectancy_per_trade_inr"])

    def test_breakeven_resets_loss_streak_and_counts_in_win_rate(self):
        metric = calculate_metrics(metric_fixture((-1, 0, -2, 4)))
        self.assertEqual(metric["maximum_consecutive_losses"], 1)
        self.assertEqual(metric["win_rate_percent"], 25)

    def test_daily_activations_count_dates_and_other_events_separately(self):
        events = (RiskEvent(START, "daily_loss_limit", D(1960)),
                  RiskEvent(START, "daily_trade_limit", D(1960)),
                  RiskEvent(START + timedelta(days=1), "daily_loss_limit", D(1920)))
        metric = calculate_metrics(replace(metric_fixture(), risk_events=events))
        self.assertEqual(metric["daily_loss_limit_activations"], 2)
        self.assertEqual(metric["risk_activation_counts"]["daily_trade_limit"], 1)

    def test_negative_equity_drawdown_is_not_clipped(self):
        result = replace(metric_fixture(), equity_observations=(observation(0, 2000), observation(1, -50)))
        metric = calculate_metrics(result)
        self.assertEqual(metric["max_drawdown_inr"], 2050)
        self.assertEqual(metric["max_drawdown_percent"], D("102.5"))
        self.assertEqual(metric["nonpositive_equity_observations"], 1)

    def test_exposure_and_leverage_use_actual_marks(self):
        result = simulate(Settings(min_history_bars=200, fee_rate=0, slippage_rate=0, leverage=3),
                          market(tuple(candle(index) for index in range(205))), Buy(), trade_start=candle(200).timestamp)
        metric = calculate_metrics(result)
        self.assertEqual(metric["exposure_bar_fraction"], 1)
        self.assertEqual(metric["maximum_marked_notional_inr"], 300)
        self.assertEqual(metric["maximum_margin_inr"], 100)
        self.assertEqual(metric["maximum_entry_leverage"], 3)
        self.assertEqual(metric["maximum_observed_notional_to_equity"], D("0.15"))


class BenchmarkTests(unittest.TestCase):
    def test_benchmark_uses_only_supplied_period_and_one_x_capital(self):
        bars = (candle(), candle(1, open="110", high="110", low="110", close="110"))
        reference = benchmarks(bars, Settings(fee_rate=0, slippage_rate=0, leverage=3))
        self.assertEqual(reference["buy_and_hold"]["quantity"], 20)
        self.assertEqual(reference["buy_and_hold"]["net_pnl_inr"], 200)
        self.assertEqual(reference["cash_only"]["final_equity_inr"], 2000)

    def test_benchmark_costs_reduce_cash_and_reconcile(self):
        reference = benchmarks((candle(),), Settings())["buy_and_hold"]
        self.assertAlmostEqual(reference["net_pnl_inr"], -reference["fees_inr"] - reference["slippage_inr"], places=20)
        self.assertLess(reference["final_equity_inr"], 2000)

    def test_missing_benchmark_prices_are_rejected(self):
        with self.assertRaises(ValueError):
            benchmarks((), Settings())
