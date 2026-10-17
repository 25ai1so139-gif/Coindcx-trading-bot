"""Deterministic synthetic candles only; none are real market observations."""

import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

from backtesting.engine import simulate
from config import Settings
from data.loader import MarketData
from strategies import create_strategy
from strategies.base import Direction, replay_action, Signal
from strategies.base import ValidatedStrategy
from strategies.momentum import Momentum
from strategies.sma_cross import SmaCross
from tests.helpers import candle, START
from tests.test_strategies import history


class DecisionTests(unittest.TestCase):
    def evaluate(self, strategy, prices, **extra):
        records = history(prices)
        context = {"as_of": records[-1].closed_at, "symbol": "SYNTHETIC-INR", **extra}
        return strategy.evaluate(records, **context)

    def test_sma_long_short_and_no_trade_decisions(self):
        strategy = SmaCross(2, 3)
        for prices, expected in (([100, 100, 100, 110], Direction.LONG),
                                 ([100, 100, 100, 90], Direction.SHORT),
                                 ([100, 100, 100, 100], Direction.NO_TRADE)):
            with self.subTest(prices=prices):
                result = self.evaluate(strategy, prices)
                self.assertEqual(result.signal, expected)
                self.assertTrue(result.reason)
                self.assertEqual(result.strategy, "sma_cross")
                self.assertEqual(result.timestamp, history(prices)[-1].closed_at)

    def test_sma_does_not_repeat_a_cross_when_already_above(self):
        result = self.evaluate(SmaCross(2, 3), [100, 101, 102, 103, 104])
        self.assertEqual(result.signal, Direction.NO_TRADE)
        self.assertEqual(result.reason_code, "NO_CROSS")

    def test_stop_references_are_on_the_protective_side(self):
        for price, direction, expected in ((102, Direction.LONG, Decimal("99.96")),
                                            (98, Direction.SHORT, Decimal("99.96"))):
            with self.subTest(direction=direction):
                result = self.evaluate(Momentum(1), [100, price])
                self.assertEqual(result.signal, direction)
                self.assertEqual(result.entry_reference, price)
                self.assertEqual(result.stop_loss_reference, expected)

    def test_unrepresentable_stop_distance_cannot_be_a_directional_signal(self):
        for price in (102, 98):
            result = self.evaluate(Momentum(1), [100, price], stop_loss_fraction=Decimal("1e-40"))
            with self.subTest(price=price):
                self.assertEqual(result.signal, Direction.NO_TRADE)
                self.assertEqual(result.reason_code, "INVALID_INDICATOR")
                self.assertIsNone(result.stop_loss_reference)

    def test_momentum_exact_thresholds_and_neutral_band(self):
        strategy = Momentum(1, Decimal("0.01"))
        for price, expected in ((101, Direction.LONG), (99, Direction.SHORT), (100, Direction.NO_TRADE)):
            with self.subTest(price=price):
                self.assertEqual(self.evaluate(strategy, [100, price]).signal, expected)

    def test_custom_parameters_change_the_rule_without_optimization(self):
        self.assertEqual(self.evaluate(Momentum(1, Decimal("0.05")), [100, 102]).signal, Direction.NO_TRADE)
        self.assertEqual(create_strategy("sma_cross", fast=2, slow=7).minimum_bars, 8)
        self.assertEqual(create_strategy("momentum", lookback=5, threshold="0.02").minimum_bars, 6)

    def test_wrong_strategy_parameters_are_rejected(self):
        for name, params in (("momentum", {"fast": 2}), ("sma_cross", {"threshold": "0.01"}),
                              ("unknown", {})):
            with self.subTest(name=name), self.assertRaises(ValueError):
                create_strategy(name, **params)

    def test_new_registered_strategy_does_not_need_a_second_parameter_registry(self):
        class SyntheticCustom(ValidatedStrategy):
            name = "synthetic_custom"
            minimum_bars = 2

            def __init__(self, period=2):
                self.period = period

        with patch.dict("strategies.STRATEGIES", {"synthetic_custom": SyntheticCustom}):
            self.assertEqual(create_strategy("synthetic_custom", period=5).period, 5)

    def test_invalid_parameters_are_rejected(self):
        for params in ({"fast": 0}, {"fast": True}, {"fast": 3, "slow": 3}, {"slow": 1.5}):
            with self.subTest(params=params), self.assertRaises(ValueError):
                SmaCross(**params)
        for params in ({"lookback": False}, {"lookback": -1}, {"threshold": 0},
                       {"threshold": 1}, {"threshold": "Infinity"}, {"threshold": "NaN"}):
            with self.subTest(params=params), self.assertRaises(ValueError):
                Momentum(**params)

    def test_insufficient_and_empty_data_have_no_entry_or_stop(self):
        for records in ([], history([100])):
            result = SmaCross().evaluate(records, as_of=START + timedelta(hours=1), symbol="SYNTHETIC-INR")
            self.assertEqual(result.signal, Direction.NO_TRADE)
            self.assertEqual(result.reason_code, "INSUFFICIENT_DATA")
            self.assertIsNone(result.entry_reference)
            self.assertIsNone(result.stop_loss_reference)

    def test_missing_or_non_candle_input_is_rejected(self):
        for records in (None, [{}], ["missing OHLC"], "not a candle sequence"):
            with self.subTest(records=records):
                result = Momentum(1).evaluate(records, as_of=START, symbol="SYNTHETIC-INR")
                self.assertEqual(result.signal, Direction.NO_TRADE)
                self.assertEqual(result.reason_code, "INVALID_CANDLES")

    def test_revalidation_rejects_a_nonfinite_mutated_record(self):
        records = history([100, 102])
        object.__setattr__(records[-1], "close", Decimal("NaN"))
        result = Momentum(1).evaluate(records, as_of=START + timedelta(hours=1), symbol="SYNTHETIC-INR")
        self.assertEqual(result.signal, Direction.NO_TRADE)
        self.assertEqual(result.reason_code, "INVALID_CANDLES")

    def test_nonfinite_derived_indicator_is_a_visible_abstention(self):
        evidence = (Direction.LONG, "SYNTHETIC_BAD_INDICATOR", "Synthetic invalid indicator", {"mean": Decimal("NaN")})
        with patch.object(SmaCross, "_calculate", return_value=evidence):
            result = self.evaluate(SmaCross(2, 3), [100] * 4)
        self.assertEqual(result.signal, Direction.NO_TRADE)
        self.assertEqual(result.reason_code, "INVALID_INDICATOR")

    def test_incomplete_and_future_records_never_generate_signals(self):
        records = history([100, 100, 100, 110])
        partial = SmaCross(2, 3).evaluate(records, as_of=records[-1].timestamp + timedelta(minutes=5),
                                         symbol="SYNTHETIC-INR")
        self.assertEqual(partial.reason_code, "INCOMPLETE_CANDLE")
        future_records = history([100, 100]) + [candle(3)]
        future = Momentum(1).evaluate(future_records, as_of=START + timedelta(minutes=30),
                                      symbol="SYNTHETIC-INR")
        self.assertEqual(future.reason_code, "FUTURE_DATA")
        self.assertTrue(all(result.signal == Direction.NO_TRADE for result in (partial, future)))

    def test_duplicate_old_timestamp_is_rejected_even_outside_indicator_window(self):
        records = history([100] * 10 + [102])
        records.insert(6, records[0])
        result = Momentum(1).evaluate(records, as_of=records[-1].closed_at, symbol="SYNTHETIC-INR")
        self.assertEqual(result.reason_code, "DUPLICATE_TIMESTAMP")

    def test_gaps_and_reversed_history_are_rejected(self):
        for records in (history([100, 101, 102])[::2], list(reversed(history([100, 102])))):
            result = Momentum(1).evaluate(records, as_of=START + timedelta(hours=1), symbol="SYNTHETIC-INR")
            self.assertEqual(result.signal, Direction.NO_TRADE)
            self.assertEqual(result.reason_code, "INVALID_CANDLE_SEQUENCE")

    def test_context_timeframe_symbol_stop_and_future_clock_are_validated(self):
        for extra in ({"timeframe": "1h"}, {"symbol": "bad/symbol"}, {"stop_loss_fraction": 0},
                      {"as_of": datetime(2099, 1, 1, tzinfo=timezone.utc)}, {"as_of": datetime(2024, 1, 1)}):
            with self.subTest(extra=extra):
                self.assertEqual(self.evaluate(Momentum(1), [100, 102], **extra).signal, Direction.NO_TRADE)

    def test_repeated_evaluation_is_identical_and_does_not_change_input(self):
        records = history([100, 102])
        before = tuple(records)
        arguments = {"as_of": records[-1].closed_at, "symbol": "SYNTHETIC-INR"}
        strategy = Momentum(1)
        self.assertEqual(strategy.evaluate(records, **arguments), strategy.evaluate(records, **arguments))
        self.assertEqual(tuple(records), before)

    def test_closed_prefix_is_unchanged_by_later_prices(self):
        def replay(last_price):
            decisions = []
            class ObservedMomentum(Momentum):
                def evaluate(self, candles, **context):
                    assert all(record.closed_at <= context["as_of"] for record in candles)
                    decision = super().evaluate(candles, **context)
                    decisions.append(decision)
                    return decision
            market = MarketData("SYNTHETIC-INR", "INR", "synthetic", "synthetic test fixture",
                                tuple(history([100] * 199 + [102, 102, last_price])))
            simulate(Settings(min_history_bars=200), market, ObservedMomentum(1))
            return decisions
        self.assertEqual(replay(1000000)[:-1], replay(1)[:-1])


class ReplayDecisionTests(unittest.TestCase):
    def test_malformed_enriched_decision_halts_replay_before_any_entry(self):
        class FutureDecision(Momentum):
            def evaluate(self, candles, **context):
                return replace(super().evaluate(candles, **context),
                               timestamp=context["as_of"] + timedelta(minutes=15))
        records = tuple(history([100] * 199 + [102, 102]))
        market = MarketData("SYNTHETIC-INR", "INR", "synthetic", "synthetic test fixture", records)
        from paper_trading.broker import PaperBroker
        settings = Settings(min_history_bars=200)
        broker = PaperBroker(settings)
        with patch("backtesting.engine.PaperBroker", return_value=broker):
            with self.assertRaisesRegex(ValueError, "decision timestamp"):
                simulate(settings, market, FutureDecision(1))
        self.assertTrue(broker.risk.emergency_halted)
        self.assertEqual(broker.trades, [])
        self.assertIsNone(broker.position)
    def test_direct_replay_rejects_future_or_gapped_inputs_before_constructing_a_broker(self):
        records = tuple(history([100] * 201))
        future = tuple(replace(record, timestamp=record.timestamp + timedelta(days=40000)) for record in records)
        gapped = (*records[:100], *records[101:])
        for candles in (future, gapped):
            market = MarketData("SYNTHETIC-INR", "INR", "synthetic", "synthetic test fixture", candles)
            with self.subTest(future=candles is future), \
                 patch("backtesting.engine.PaperBroker", side_effect=AssertionError("broker prohibited")), \
                 self.assertRaises(ValueError):
                simulate(Settings(min_history_bars=200), market, Momentum(1))
    def test_short_adapter_is_only_a_long_exit(self):
        self.assertEqual(replay_action(Direction.SHORT), Signal.SELL)
        records = tuple(history([100] * 199 + [90, 90]))
        market = MarketData("SYNTHETIC-INR", "INR", "synthetic", "synthetic test fixture", records)
        self.assertEqual(simulate(Settings(min_history_bars=200), market, Momentum(1)).trades, ())

    def test_enriched_decision_executes_only_at_the_next_open(self):
        records = tuple(history([100] * 199 + [102, 110]))
        market = MarketData("SYNTHETIC-INR", "INR", "synthetic", "synthetic test fixture", records)
        result = simulate(Settings(min_history_bars=200, fee_rate=0, slippage_rate=0), market, Momentum(1))
        self.assertEqual(len(result.trades), 1)
        self.assertEqual(result.trades[0].opened_at, records[200].timestamp)
        self.assertEqual(result.trades[0].entry_price, 110)
