import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from backtesting.engine import simulate
from cli import main
from config import Settings
from data.loader import MarketData
from paper_trading.broker import PaperBroker
from strategies.base import Signal
from tests.helpers import candle
from tools.generate_sample_data import generate


class AlwaysBuy:
    minimum_bars = 1

    def signal(self, candles):
        return Signal.BUY


class SimulationTests(unittest.TestCase):
    def test_keyboard_interrupt_flattens_and_reports_partial_run(self):
        class InterruptAfterEntry(AlwaysBuy):
            calls = 0

            def signal(self, candles):
                self.calls += 1
                if self.calls == 2:
                    raise KeyboardInterrupt
                return Signal.BUY

        market = MarketData("TEST-INR", "INR", "synthetic", "test",
                            tuple(candle(index) for index in range(210)))
        result = simulate(Settings(min_history_bars=200), market, InterruptAfterEntry())
        self.assertTrue(result.interrupted)
        self.assertEqual(result.bars, 201)
        self.assertEqual(result.halt_reason, "emergency_shutdown")
        self.assertEqual(len(result.trades), 1)
        self.assertEqual(result.trades[0].reason, "emergency_shutdown")
        self.assertEqual(result.ending_equity, result.starting_capital + result.trades[0].net_pnl)

    def test_strategy_error_requests_emergency_cleanup_and_propagates(self):
        class BrokenStrategy(AlwaysBuy):
            calls = 0

            def signal(self, candles):
                self.calls += 1
                if self.calls == 2:
                    raise ValueError("deliberate strategy failure")
                return Signal.BUY

        market = MarketData("TEST-INR", "INR", "synthetic", "test",
                            tuple(candle(index) for index in range(210)))
        settings = Settings(min_history_bars=200)
        broker = PaperBroker(settings)
        with patch("backtesting.engine.PaperBroker", return_value=broker):
            with self.assertRaisesRegex(ValueError, "strategy failure"):
                simulate(settings, market, BrokenStrategy())
        self.assertIsNone(broker.position)
        self.assertEqual(broker.trades[0].reason, "emergency_shutdown")
        self.assertEqual(broker.risk.entry_block_reason, "emergency_shutdown")

    def test_signal_executes_next_open_after_history_gate(self):
        candles = tuple(candle(index) for index in range(200)) + (
            candle(200, open="110", high="110", low="110", close="110"),)
        market = MarketData("TEST-INR", "INR", "synthetic", "test", candles)
        result = simulate(Settings(min_history_bars=200, fee_rate=0, slippage_rate=0),
                          market, AlwaysBuy())
        self.assertEqual(len(result.trades), 1)
        self.assertEqual(result.trades[0].opened_at, candles[200].timestamp)
        self.assertEqual(result.trades[0].entry_price, 110)

    def test_last_bar_signal_cannot_trade_on_same_bar(self):
        market = MarketData("TEST-INR", "INR", "synthetic", "test",
                            tuple(candle(index) for index in range(200)))
        result = simulate(Settings(min_history_bars=200), market, AlwaysBuy())
        self.assertEqual(result.trades, ())
        self.assertEqual(result.net_pnl, 0)

    def test_paper_and_backtest_share_accounting(self):
        market = MarketData("TEST-INR", "INR", "synthetic", "test",
                            tuple(candle(index) for index in range(210)))
        historical = simulate(Settings(min_history_bars=200), market, AlwaysBuy())
        paper = simulate(Settings(mode="paper", min_history_bars=200), market, AlwaysBuy())
        self.assertEqual(historical.trades, paper.trades)
        self.assertEqual(historical.ending_equity, paper.ending_equity)
        self.assertEqual(paper.ending_equity - paper.starting_capital,
                         sum(trade.net_pnl for trade in paper.trades))


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "demo.csv"
        generate(self.path, 210)
        env_patch = patch.dict(os.environ, {"BOT_MIN_HISTORY_BARS": "200"}, clear=True)
        env_patch.start()
        self.addCleanup(env_patch.stop)

    def invoke(self, command, *extra):
        output, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            status = main([command, "--data", str(self.path), "--allow-synthetic", *extra])
        return status, output.getvalue(), errors.getvalue()

    def test_manual_and_verify_never_submit_orders(self):
        for command in ("manual", "verify"):
            with patch("paper_trading.broker.PaperBroker.__init__", side_effect=AssertionError):
                status, output, errors = self.invoke(command)
            self.assertEqual(status, 0, errors)
            report = json.loads(output)
            self.assertEqual(report["orders_submitted"], 0)
            self.assertFalse(report["live_trading_enabled"])

    def test_all_data_commands_run_without_credentials_or_network(self):
        for command in ("verify", "manual", "backtest", "paper"):
            with patch("socket.socket", side_effect=AssertionError("network forbidden")), \
                 patch("socket.create_connection", side_effect=AssertionError("network forbidden")):
                status, output, errors = self.invoke(command)
            self.assertEqual(status, 0, errors)
            self.assertFalse(json.loads(output)["live_trading_enabled"])

    def test_interrupted_simulation_returns_130_with_shutdown_report(self):
        class InterruptAfterEntry(AlwaysBuy):
            calls = 0

            def signal(self, candles):
                self.calls += 1
                if self.calls == 2:
                    raise KeyboardInterrupt
                return Signal.BUY

        with patch.dict("cli.STRATEGIES", {"sma_cross": InterruptAfterEntry}):
            status, output, errors = self.invoke("paper")
        self.assertEqual(status, 130, errors)
        report = json.loads(output)
        self.assertTrue(report["interrupted"])
        self.assertEqual(report["halt_reason"], "emergency_shutdown")
        self.assertEqual(report["trades"][0]["reason"], "emergency_shutdown")

    def test_interrupt_during_loading_has_non_success_exit(self):
        with patch("cli.load_csv", side_effect=KeyboardInterrupt):
            status, output, errors = self.invoke("paper")
        self.assertEqual(status, 130)
        self.assertEqual(output, "")
        self.assertNotIn("Traceback", errors)

    def test_both_simulation_commands_run_with_selected_strategy(self):
        for mode in ("backtest", "paper"):
            status, output, errors = self.invoke(mode, "--strategy", "momentum")
            self.assertEqual(status, 0, errors)
            report = json.loads(output)
            self.assertEqual(report["mode"], mode)
            self.assertEqual(report["strategy"], "momentum")
            self.assertGreater(report["trade_count"], 0)
            self.assertIn("Synthetic", report["warning"])

    def test_excess_leverage_is_rejected_without_orders(self):
        status, output, errors = self.invoke("paper", "--leverage", "4")
        self.assertEqual(status, 2)
        self.assertEqual(output, "")
        self.assertIn("leverage", errors)

    def test_live_environment_setting_fails_closed(self):
        with patch.dict(os.environ, {"BOT_MODE": "live"}):
            status, output, errors = self.invoke("paper")
        self.assertEqual(status, 2)
        self.assertEqual(output, "")
        self.assertIn("disabled", errors)

    def test_invalid_numeric_argument_has_no_traceback(self):
        with redirect_stderr(io.StringIO()) as errors, self.assertRaises(SystemExit) as raised:
            main(["paper", "--data", str(self.path), "--leverage", "garbage"])
        self.assertEqual(raised.exception.code, 2)
        self.assertNotIn("Traceback", errors.getvalue())

    def test_no_live_command_exists(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
            main(["live"])
        self.assertEqual(raised.exception.code, 2)

    def test_strategy_listing(self):
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["strategies"]), 0)
        self.assertEqual(set(output.getvalue().splitlines()), {"sma_cross", "momentum"})
