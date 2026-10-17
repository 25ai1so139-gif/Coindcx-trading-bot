import unittest
from datetime import timedelta
from decimal import Decimal

from config import Settings
from risk.controls import RiskControls
from risk.sizing import size_position
from risk.stops import long_stop_reference
from tests.helpers import START, candle

D = Decimal


class PositionSizingTests(unittest.TestCase):
    def test_default_budget_is_ten_rupees_and_hard_ceiling_is_twenty(self):
        default = size_position(Settings(margin_amount=1000, leverage=3), D(2000), D(100))
        self.assertLessEqual(default.planned_stop_risk, 10)
        self.assertGreater(default.planned_stop_risk, D("9.99"))
        capped = size_position(Settings(margin_amount=1000, leverage=3, risk_per_trade="0.02"),
                               D(2000), D(100))
        self.assertLessEqual(capped.planned_stop_risk, 20)
        self.assertGreater(capped.planned_stop_risk, D("19.99"))

    def test_equity_growth_cannot_raise_absolute_risk_ceiling(self):
        plan = size_position(Settings(margin_amount=10000, leverage=3), D(10000), D(100))
        self.assertLessEqual(plan.planned_stop_risk, 20)

    def test_small_positions_are_not_inflated_to_ten_rupees_risk(self):
        plan = size_position(Settings(), D(2000), D(100))
        self.assertLess(plan.planned_stop_risk, 10)

    def test_remaining_account_budget_is_included_in_sizing(self):
        plan = size_position(Settings(margin_amount=1000, leverage=3), D(1961), D(100), D(1))
        self.assertLessEqual(plan.planned_stop_risk, 1)
        for value in (D(0), D(-1), D("NaN")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                size_position(Settings(), D(2000), D(100), value)

    def test_invalid_stop_trigger_is_rejected(self):
        for trigger in (D(0), D(-1), D("NaN"), D("Infinity")):
            with self.subTest(trigger=trigger), self.assertRaises(ValueError):
                long_stop_reference(candle(), trigger)

    def test_stop_distance_must_remain_protective_at_decimal_precision(self):
        for costs in ({}, {"fee_rate": 0, "slippage_rate": 0}):
            with self.subTest(costs=costs), self.assertRaisesRegex(ValueError, "stop"):
                size_position(Settings(stop_loss_fraction="1e-40", **costs), D(2000), D(100))

    def test_margin_amount_is_not_notional(self):
        plan = size_position(Settings(leverage=3, fee_rate=0, slippage_rate=0), D(2000), D(100))
        self.assertEqual(plan.margin, 100)
        self.assertEqual(plan.notional, 300)
        self.assertEqual(plan.quantity, 3)

    def test_risk_budget_includes_both_fees_and_stop_slippage(self):
        settings = Settings(margin_amount=1500, leverage=3)
        plan = size_position(settings, D(2000), D(100))
        exit_fill = plan.stop_price * (1 - settings.slippage_rate)
        loss = plan.quantity * (plan.entry_price - exit_fill)
        round_trip_fees = plan.entry_fee + plan.quantity * exit_fill * settings.fee_rate
        self.assertAlmostEqual(plan.planned_stop_risk, loss + round_trip_fees, places=20)
        self.assertLessEqual(plan.planned_stop_risk, D(2000) * settings.risk_per_trade)
        self.assertLess(plan.margin, settings.margin_amount)

    def test_margin_is_capped_and_fees_are_affordable(self):
        settings = Settings(margin_amount=100000, stop_loss_fraction="0.0001",
                            fee_rate=0, slippage_rate=0, leverage=3)
        plan = size_position(settings, D(2000), D(100))
        self.assertLessEqual(plan.margin, D(500))
        self.assertLessEqual(plan.margin + plan.entry_fee, D(2000))

    def test_lower_equity_reduces_risk_budget(self):
        settings = Settings(margin_amount=1500, leverage=3)
        full = size_position(settings, D(2000), D(100))
        reduced = size_position(settings, D(1000), D(100))
        self.assertLessEqual(reduced.planned_stop_risk, D(5))
        self.assertLess(reduced.quantity, full.quantity)

    def test_invalid_equity_and_prices_fail_closed(self):
        for equity, price in (("0", "100"), ("-1", "100"), ("2000", "0"),
                              ("NaN", "100"), ("2000", "Infinity")):
            with self.subTest(equity=equity, price=price), self.assertRaises(ValueError):
                size_position(Settings(), D(equity), D(price))


class RiskControlTests(unittest.TestCase):
    def test_rupee_daily_cap_does_not_grow_with_equity(self):
        controls = RiskControls(Settings())
        controls.observe(D(2500), START)
        controls.observe(D(2500), START + timedelta(days=1))
        self.assertEqual(controls.daily_loss_budget, 40)
        controls.observe(D(2460), START + timedelta(days=1, hours=1))
        self.assertEqual(controls.halt_reason, "daily_loss_limit")

    def test_daily_percentage_can_be_stricter_than_rupee_cap(self):
        controls = RiskControls(Settings(starting_capital=1000))
        controls.observe(D(1000), START)
        self.assertEqual(controls.daily_loss_budget, 20)
        controls.observe(D(980), START + timedelta(hours=1))
        self.assertEqual(controls.halt_reason, "daily_loss_limit")

    def test_daily_limit_latches_until_next_utc_day(self):
        controls = RiskControls(Settings())
        controls.observe(D(2000), START)
        controls.observe(D(1960), START + timedelta(hours=1))
        self.assertEqual(controls.halt_reason, "daily_loss_limit")
        controls.observe(D(2000), START + timedelta(hours=2))
        self.assertEqual(controls.halt_reason, "daily_loss_limit")
        controls.observe(D(2000), START + timedelta(days=1))
        self.assertIsNone(controls.halt_reason)

    def test_drawdown_halt_persists_after_recovery_and_next_day(self):
        controls = RiskControls(Settings())
        controls.observe(D(2000), START)
        controls.observe(D(1900), START + timedelta(hours=1))
        self.assertEqual(controls.halt_reason, "max_drawdown")
        controls.observe(D(2100), START + timedelta(days=1))
        self.assertEqual(controls.halt_reason, "max_drawdown")
        self.assertEqual(controls.max_observed_drawdown, D("0.05"))

    def test_peak_equity_protects_unrealized_gains(self):
        controls = RiskControls(Settings())
        controls.observe(D(2200), START)
        controls.observe(D(2090), START + timedelta(minutes=15))
        self.assertEqual(controls.halt_reason, "max_drawdown")

    def test_overnight_gap_is_not_erased_by_daily_reset(self):
        controls = RiskControls(Settings())
        controls.observe(D(2000), START)
        controls.observe(D(1950), START + timedelta(days=1))
        self.assertEqual(controls.halt_reason, "daily_loss_limit")

    def test_invalid_time_is_rejected(self):
        controls = RiskControls(Settings())
        with self.assertRaises(ValueError):
            controls.observe(D(2000), START.replace(tzinfo=None))
        controls.observe(D(2000), START)
        with self.assertRaises(ValueError):
            controls.observe(D(2000), START - timedelta(days=1))
