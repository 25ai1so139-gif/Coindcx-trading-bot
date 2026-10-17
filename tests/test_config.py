import unittest
from decimal import Decimal

from config import Settings


class ConfigurationTests(unittest.TestCase):
    def test_protective_defaults(self):
        settings = Settings()
        self.assertEqual(settings.starting_capital, Decimal("2000"))
        self.assertEqual(settings.max_leverage, 3)
        self.assertEqual(settings.leverage, 1)
        self.assertEqual(settings.amount_type, "margin")
        self.assertEqual(settings.timeframe, "15m")
        self.assertEqual(settings.min_history_bars, 30 * 24 * 4)
        self.assertEqual(settings.max_planned_risk, 20)
        self.assertEqual(settings.daily_loss_amount, 40)
        self.assertEqual(settings.max_trades_per_day, 3)

    def test_live_and_unsupported_modes_are_rejected(self):
        for mode in ("live", "real", "", "BACKTEST"):
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                Settings(mode=mode)

    def test_invalid_settings_are_rejected(self):
        cases = (
            {"starting_capital": 0}, {"margin_amount": -1},
            {"starting_capital": "NaN"}, {"fee_rate": "Infinity"},
            {"slippage_rate": "nonsense"}, {"amount_type": "notional"},
            {"account_currency": "USDT"}, {"timeframe": "1m"},
            {"strategy": "unknown"}, {"stop_loss_fraction": 0},
            {"stop_loss_fraction": 1}, {"risk_per_trade": -1},
            {"max_margin_fraction": 1}, {"fee_rate": -1}, {"fee_rate": "0.051"},
            {"slippage_rate": "0.051"}, {"daily_loss_limit": "0.001"},
            {"max_drawdown": "0.01"}, {"min_history_bars": 199},
            {"min_history_bars": 200.5}, {"min_history_bars": True},
        )
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValueError):
                Settings(**case)

    def test_maximum_leverage_is_enforced(self):
        self.assertEqual(Settings(leverage=3).leverage, 3)
        for case in ({"leverage": "3.0001"}, {"max_leverage": 4},
                     {"leverage": "0.5"}, {"max_leverage": 2, "leverage": 3}):
            with self.subTest(case=case), self.assertRaises(ValueError):
                Settings(**case)

    def test_environment_values_are_validated(self):
        settings = Settings.from_env({"BOT_MODE": "paper", "BOT_LEVERAGE": "2",
                                      "BOT_MARGIN_AMOUNT": "125", "BOT_MIN_HISTORY_BARS": "400"})
        self.assertEqual(settings.mode, "paper")
        self.assertEqual(settings.margin_amount, 125)
        self.assertEqual(settings.min_history_bars, 400)
        for env in ({"BOT_MODE": "live"}, {"BOT_LEVERAGE": ""},
                    {"BOT_MIN_HISTORY_BARS": "200.5"}):
            with self.subTest(env=env), self.assertRaises(ValueError):
                Settings.from_env(env)

    def test_absolute_limits_cannot_be_relaxed_by_configuration(self):
        for case in ({"max_planned_risk": "20.01"}, {"daily_loss_amount": "40.01"},
                     {"max_trades_per_day": 4}, {"max_trades_per_day": 0},
                     {"max_trades_per_day": 1.5}, {"max_trades_per_day": True},
                     {"max_planned_risk": 0}, {"daily_loss_amount": -1}):
            with self.subTest(case=case), self.assertRaises(ValueError):
                Settings(**case)
        for key, value in (("BOT_MAX_PLANNED_RISK", "21"), ("BOT_DAILY_LOSS_AMOUNT", "41"),
                           ("BOT_MAX_TRADES_PER_DAY", "4"), ("BOT_MAX_TRADES_PER_DAY", "2.5")):
            with self.subTest(key=key), self.assertRaises(ValueError):
                Settings.from_env({key: value})

    def test_limits_can_be_tightened(self):
        settings = Settings.from_env({"BOT_MAX_PLANNED_RISK": "10", "BOT_DAILY_LOSS_AMOUNT": "30",
                                      "BOT_MAX_TRADES_PER_DAY": "2"})
        self.assertEqual(settings.max_planned_risk, 10)
        self.assertEqual(settings.daily_loss_amount, 30)
        self.assertEqual(settings.max_trades_per_day, 2)

    def test_all_risk_fractions_reject_invalid_boundaries(self):
        for name in ("risk_per_trade", "stop_loss_fraction", "daily_loss_limit", "max_drawdown",
                     "max_margin_fraction"):
            for value in ("-0.01", "0", "1", "NaN", "Infinity"):
                with self.subTest(name=name, value=value), self.assertRaises(ValueError):
                    Settings(**{name: value})

    def test_capital_and_timeframes_fail_closed(self):
        for value in ("-1", "0", "NaN", "Infinity", "-Infinity", "invalid"):
            with self.subTest(capital=value), self.assertRaises(ValueError):
                Settings(starting_capital=value)
        for value in ("", "1m", "5m", "1h", "15", "15M"):
            with self.subTest(timeframe=value), self.assertRaises(ValueError):
                Settings(timeframe=value)
