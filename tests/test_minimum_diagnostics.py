"""SYNTHETIC minimum-order explanations; never genuine instrument qualification."""

import unittest
from dataclasses import asdict, replace
from decimal import Decimal, localcontext
from unittest.mock import patch

from exchange.diagnostics import minimum_order_diagnostic
from tests.exchange_fixtures import fixture

D = Decimal


class MinimumDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.settings, _, _, instrument, _ = fixture()
        self.instrument = replace(instrument, step=D(1), min_quantity=D(1), min_notional=D(100), quantity_precision=0)

    def test_default_margin_floors_below_minimum_and_reports_no_trade_without_resizing(self):
        result = minimum_order_diagnostic(self.settings, self.instrument, D(9))
        self.assertEqual(result["status"], "NO_TRADE")
        self.assertEqual(result["candidate"]["quantity"], 11)
        self.assertEqual(result["candidate"]["notional"], D("99.099"))
        self.assertEqual(result["theoretical_minimum"]["quantity"], 12)
        self.assertEqual(result["configured_margin"], 100)
        self.assertEqual(self.settings.margin_amount, 100)

    def test_exact_boundary_is_size_only_and_still_has_no_approval(self):
        settings = replace(self.settings, fee_rate=0, slippage_rate=0)
        result = minimum_order_diagnostic(settings, self.instrument, D(10))
        self.assertEqual(result["status"], "SIZE_ONLY_NOT_APPROVED")
        self.assertEqual(result["candidate"]["notional"], 100)
        self.assertFalse(result["risk_approved"])

    def test_non_decimal_step_uses_exact_upward_minimum_for_explanation_only(self):
        settings = replace(self.settings, slippage_rate=0)
        instrument = replace(self.instrument, step=D('.3'), min_quantity=D('.3'), quantity_precision=1)
        result = minimum_order_diagnostic(settings, instrument, D(7))
        self.assertEqual(result["theoretical_minimum"]["quantity"], D('14.4'))
        self.assertEqual(result["theoretical_minimum"]["notional"], D('100.8'))
        self.assertEqual(result["status"], "NO_TRADE")

    def test_more_requested_margin_cannot_bypass_existing_ten_rupee_risk_budget(self):
        settings = replace(self.settings, margin_amount=500, stop_loss_fraction=D('.5'))
        instrument = replace(self.instrument, step=D('.01'), min_quantity=D('.01'), quantity_precision=2)
        result = minimum_order_diagnostic(settings, instrument, D(100))
        self.assertEqual(result["status"], "NO_TRADE")
        self.assertLessEqual(result["candidate"]["planned_stop_risk"], 10)
        self.assertLess(result["candidate"]["notional"], 100)

    def test_synthetic_margin_and_notional_are_distinct_and_real_spot_three_x_is_rejected(self):
        settings = replace(self.settings, leverage=3)
        result = minimum_order_diagnostic(settings, self.instrument, D(9))
        minimum = result["theoretical_minimum"]
        self.assertEqual(minimum["notional"], minimum["margin"] * 3)
        real = minimum_order_diagnostic(settings, replace(self.instrument, kind="public_metadata"), D(9))
        self.assertEqual(real["status"], "NO_TRADE")
        self.assertEqual(real["reason"], "SPOT_ORDER_LEVERAGE_UNSUPPORTED")

    def test_weaker_risk_profile_cannot_be_described_as_an_approved_configuration(self):
        result = minimum_order_diagnostic(replace(self.settings, risk_per_trade=D('.01')), self.instrument, D(9))
        self.assertEqual(result["status"], "NO_TRADE")
        self.assertEqual(result["reason"], "PHASE5_PROFILE_REQUIRED")

    def test_invalid_references_reject_before_any_size_is_available(self):
        for value in (0, -1, "NaN", "Infinity", "bad", "1e1000"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                minimum_order_diagnostic(self.settings, self.instrument, value)

    def test_diagnostic_cannot_construct_broker_sign_request_or_open_a_socket(self):
        before = asdict(self.settings), asdict(self.instrument)
        with patch('socket.socket', side_effect=AssertionError), patch('paper_trading.broker.PaperBroker', side_effect=AssertionError), patch('exchange.auth.Credentials.from_env', side_effect=AssertionError):
            result = minimum_order_diagnostic(self.settings, self.instrument, D(9))
        self.assertEqual(result["orders_submitted"], 0)
        self.assertFalse(result["risk_approved"])
        self.assertFalse(result["live_trading_enabled"])
        self.assertEqual(before, (asdict(self.settings), asdict(self.instrument)))

    def test_caller_decimal_precision_does_not_round_down_the_required_minimum(self):
        expected = minimum_order_diagnostic(self.settings, self.instrument, D(9))
        with localcontext() as context:
            context.prec = 2
            self.assertEqual(minimum_order_diagnostic(self.settings, self.instrument, D(9)), expected)
