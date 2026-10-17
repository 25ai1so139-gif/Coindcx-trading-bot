"""Phase 5 adversarial synthetic fixtures; no actual market or execution evidence."""

import copy
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import asdict, replace
from datetime import timedelta, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from backtesting.engine import simulate
from cli import main
from config import Settings
from data.loader import MarketData
from paper_trading.broker import PaperBroker, Position
from risk.audit import RiskAudit
from risk.controls import RiskControls
from risk.entry import approve_entry, entry_plan
from risk.proposal import CostAssumptions, EntryProposal, MarketContext
from risk.sizing import PositionPlan, size_position
from strategies.base import Direction, Signal
from tests.helpers import candle, synthetic_proposal
from tests.test_engine_cli import AlwaysBuy
from tools.generate_sample_data import generate

D = Decimal


class GateFixture:
    def setUp(self):
        self.settings = Settings(min_history_bars=200)
        self.at = candle(200).timestamp
        self.proposal = synthetic_proposal(self.settings, self.at)
        self.controls = RiskControls(self.settings)
        self.controls.observe(D(2000), self.at)
        self.audit = RiskAudit()

    def review(self, *, proposal=None, settings=None, controls=None, equity=D(2000), at=None, has_position=False):
        return approve_entry(settings or self.settings, controls or self.controls, equity,
                             self.proposal if proposal is None else proposal, at=self.at if at is None else at,
                             has_open_position=has_position, audit=self.audit)

    def assert_rejected(self, result, reason):
        self.assertFalse(result.approved)
        self.assertIsNone(result.plan)
        self.assertEqual(result.reason, reason)
        self.assertEqual(result.record.reason, reason)
        self.assertFalse(result.record.approved)

    def with_market(self, **changes):
        return replace(self.proposal, market=replace(self.proposal.market, **changes))


class MarketAndSignalGateTests(GateFixture, unittest.TestCase):
    def test_audit_distinguishes_collateral_leverage_and_account_exposure(self):
        settings = replace(self.settings, leverage=3, fee_rate=0, slippage_rate=0)
        controls = RiskControls(settings)
        controls.observe(D(2000), self.at)
        result = self.review(settings=settings, controls=controls,
                             proposal=synthetic_proposal(settings, self.at))
        self.assertTrue(result.approved)
        self.assertEqual(result.record.leverage, 3)
        self.assertEqual(result.record.notional, 300)
        self.assertEqual(result.record.effective_leverage, D("0.15"))

    def test_audit_missing_plan_or_nonpositive_equity_has_no_exposure_estimate(self):
        self.assertIsNone(self.audit.record(at=self.at, approved=False, reason="SYNTHETIC_TEST").effective_leverage)
        plan = size_position(self.settings, D(2000), D(100))
        for value in (None, D(0), D(-1), D("NaN")):
            with self.subTest(equity=value):
                record = self.audit.record(at=self.at, approved=False, reason="SYNTHETIC_TEST",
                                           plan=plan, equity=value)
                self.assertIsNone(record.effective_leverage)

    def test_unsafe_input_shapes_are_rejected_without_logging_raw_values(self):
        for changes in ({"kind": []}, {"symbol": []}, {"instrument": {}}, {"costs": {}},
                        {"quality_reviewed": "true", "kind": "historical"}):
            with self.subTest(changes=changes):
                result = self.review(proposal=self.with_market(**changes))
                self.assertFalse(result.approved)
                self.assertIsNone(result.plan)
                self.assertIsNotNone(result.record.timestamp)

    def test_valid_proposal_is_read_only_and_logs_complete_modeled_plan(self):
        before = copy.deepcopy(self.controls.__dict__)
        result = self.review()
        self.assertTrue(result.approved)
        self.assertEqual(self.controls.__dict__, before)
        self.assertEqual(len(self.audit.records), 1)
        record = result.record
        self.assertEqual(record.timestamp, self.at)
        self.assertEqual(record.timestamp.tzinfo, timezone.utc)
        self.assertEqual(record.data_kind, "synthetic")
        self.assertEqual(record.planned_risk, result.plan.planned_stop_risk)
        self.assertEqual(record.permitted_risk, 10)
        self.assertEqual(record.margin * record.leverage, record.notional)
        self.assertGreater(record.estimated_fees, 0)
        self.assertGreater(record.estimated_slippage, 0)
        self.assertEqual(record.stop_reference, self.proposal.decision.stop_loss_reference)
        self.assertEqual(record.stop_price, result.plan.stop_price)

    def test_missing_proposal_is_rejected_and_audited(self):
        result = approve_entry(self.settings, self.controls, 2000, None, at=self.at,
                               has_open_position=False, audit=self.audit)
        self.assert_rejected(result, "ENTRY_PROPOSAL_REQUIRED")

    def test_missing_market_context_is_rejected(self):
        self.assert_rejected(self.review(proposal=replace(self.proposal, market=None)), "MARKET_CONTEXT_REQUIRED")

    def test_ineligible_market_cannot_pass_with_other_valid_fields(self):
        for value in (False, "true", 1, None):
            with self.subTest(value=value):
                self.assert_rejected(self.review(proposal=self.with_market(eligible=value)), "MARKET_INELIGIBLE")

    def test_symbol_and_timeframe_or_currency_mismatches_reject(self):
        for changes, reason in (({"symbol": "../invalid"}, "INVALID_SYMBOL"),
                                ({"timeframe": "1h"}, "INVALID_MARKET"),
                                ({"quote_currency": "USDT"}, "INVALID_MARKET"),
                                ({"symbol": "DIFFERENT-INR"}, "INVALID_SIGNAL_OR_STOP")):
            with self.subTest(changes=changes):
                self.assert_rejected(self.review(proposal=self.with_market(**changes)), reason)

    def test_missing_and_insufficient_history_reject(self):
        for records in ((), self.proposal.candles[1:]):
            self.assert_rejected(self.review(proposal=replace(self.proposal, candles=records)), "INSUFFICIENT_HISTORY")

    def test_duplicate_out_of_order_and_gapped_history_reject(self):
        records = self.proposal.candles
        cases = (records[:50] + (records[49],) + records[50:], tuple(reversed(records)), records[:50] + records[51:])
        for rows in cases:
            with self.subTest(length=len(rows)):
                self.assert_rejected(self.review(proposal=replace(self.proposal, candles=rows)), "INVALID_OR_INCOMPLETE_MARKET_DATA")

    def test_incomplete_and_future_candles_reject(self):
        rows = self.proposal.candles
        for stamp in (self.at - timedelta(minutes=15), self.at + timedelta(minutes=15)):
            changed = rows[:-1] + (replace(rows[-1], timestamp=stamp),)
            at = self.at - timedelta(minutes=5) if stamp < self.at else self.at
            self.assert_rejected(self.review(proposal=replace(self.proposal, candles=changed), at=at),
                                 "INVALID_OR_INCOMPLETE_MARKET_DATA")

    def test_mutated_invalid_ohlc_or_nan_volume_reject(self):
        for field, value in (("high", D(1)), ("volume", D("NaN")), ("close", D(0))):
            rows = copy.deepcopy(self.proposal.candles)
            object.__setattr__(rows[-1], field, value)
            self.assert_rejected(self.review(proposal=replace(self.proposal, candles=rows)), "INVALID_OR_INCOMPLETE_MARKET_DATA")

    def test_staleness_just_below_equal_and_above_thirty_minutes(self):
        for offset, permitted in ((timedelta(minutes=30) - timedelta(microseconds=1), True),
                                  (timedelta(minutes=30), True),
                                  (timedelta(minutes=30, microseconds=1), False)):
            result = self.review(at=self.at + offset)
            self.assertEqual(result.approved, permitted)
            if not permitted:
                self.assertEqual(result.reason, "STALE_MARKET_DATA")

    def test_stricter_staleness_and_invalid_freshness_policy(self):
        self.assert_rejected(self.review(proposal=self.with_market(max_staleness_minutes=0),
                                         at=self.at + timedelta(seconds=1)), "STALE_MARKET_DATA")
        for value in (31, -1, True, "30"):
            self.assert_rejected(self.review(proposal=self.with_market(max_staleness_minutes=value)), "INVALID_FRESHNESS_POLICY")

    def test_invalid_naive_or_future_evaluation_time_reject(self):
        for stamp, reason in ((self.at.replace(tzinfo=None), "INVALID_TIMESTAMP"),
                              ("invalid timestamp", "INVALID_TIMESTAMP"),
                              (self.at + timedelta(days=50000), "FUTURE_EVALUATION_TIME")):
            self.assert_rejected(self.review(at=stamp), reason)
            self.assertEqual(self.audit.records[-1].timestamp.utcoffset(), timedelta(0))

    def test_missing_zero_nonprotective_or_wrong_distance_stop_reject(self):
        for stop in (None, D(0), D(100), D(101), D(-1), D("NaN"), D(1)):
            decision = replace(self.proposal.decision, stop_loss_reference=stop)
            with self.subTest(stop=stop):
                self.assert_rejected(self.review(proposal=replace(self.proposal, decision=decision)), "INVALID_SIGNAL_OR_STOP")

    def test_entry_gap_at_or_below_the_analytical_stop_rejects(self):
        for reference in (D(98), D(97)):
            self.assert_rejected(self.review(proposal=replace(self.proposal, reference_price=reference)), "STOP_ALREADY_BREACHED")

    def test_future_or_stale_signal_timestamp_reject(self):
        for stamp in (self.at + timedelta(minutes=15), self.at - timedelta(minutes=15), self.at.replace(tzinfo=None)):
            self.assert_rejected(self.review(proposal=replace(self.proposal, decision=replace(self.proposal.decision, timestamp=stamp))),
                                 "INVALID_SIGNAL_OR_STOP")

    def test_short_is_explicitly_rejected(self):
        decision = replace(self.proposal.decision, signal=Direction.SHORT, stop_loss_reference=D(102))
        self.assert_rejected(self.review(proposal=replace(self.proposal, decision=decision)), "SHORT_ENTRY_UNSUPPORTED")

    def test_neutral_signal_has_no_permission_or_plan(self):
        decision = replace(self.proposal.decision, signal=Direction.NO_TRADE, entry_reference=None, stop_loss_reference=None)
        self.assert_rejected(self.review(proposal=replace(self.proposal, decision=decision)), "NO_TRADE")

    def test_raw_strings_or_legacy_signal_cannot_masquerade_as_direction(self):
        for signal in ("LONG", Signal.BUY):
            self.assert_rejected(self.review(proposal=replace(self.proposal, decision=replace(self.proposal.decision, signal=signal))),
                                 "INVALID_SIGNAL_OR_STOP")

    def test_missing_instrument_details_and_cost_assumptions_reject(self):
        for changes, reason in (({"instrument": None}, "INSTRUMENT_DETAILS_REQUIRED"),
                                ({"costs": None}, "COST_ASSUMPTIONS_REQUIRED"),
                                ({"costs": replace(self.proposal.market.costs, declared=False)}, "COST_ASSUMPTIONS_REQUIRED")):
            self.assert_rejected(self.review(proposal=self.with_market(**changes)), reason)

    def test_fee_and_slippage_assumptions_must_match_sizing_settings(self):
        for changes in ({"fee_rate": D("0.002")}, {"slippage_rate": D("0.002")}):
            costs = replace(self.proposal.market.costs, **changes)
            self.assert_rejected(self.review(proposal=self.with_market(costs=costs)), "COST_ASSUMPTIONS_MISMATCH")

    def test_unqualified_real_market_and_unsupported_leverage_reject(self):
        # Historical labels below exercise the gate; every price is still fabricated.
        context = replace(self.proposal.market, kind="historical")
        self.assert_rejected(self.review(proposal=replace(self.proposal, market=context)), "UNVERIFIED_MARKET_ELIGIBILITY")
        context = replace(context, quality_reviewed=True, liquidity_verified=True)
        self.assert_rejected(self.review(proposal=replace(self.proposal, market=context)), "UNSUPPORTED_OR_UNVERIFIED_INSTRUMENT")

    def test_invalid_instrument_precision_minimums_and_max_leverage_reject(self):
        for changes, reason in (({"quantity_step": 0}, "INVALID_INSTRUMENT_CONSTRAINTS"),
                                ({"minimum_quantity": -1}, "INVALID_INSTRUMENT_CONSTRAINTS"),
                                ({"minimum_notional": -1}, "INVALID_INSTRUMENT_CONSTRAINTS"),
                                ({"max_leverage": 4}, "LEVERAGE_LIMIT"),
                                ({"symbol": "DIFFERENT-INR"}, "INSTRUMENT_SYMBOL_MISMATCH")):
            instrument = replace(self.proposal.market.instrument, **changes)
            self.assert_rejected(self.review(proposal=self.with_market(instrument=instrument)), reason)

    def test_verified_spot_constraint_path_uses_metadata_without_claiming_real_evidence(self):
        # All prices/metadata here are fabricated gate stand-ins, never qualification.
        instrument = replace(self.proposal.market.instrument, product="spot", verified=True,
                             quantity_step=D("0.03"), minimum_quantity=D("0.03"),
                             minimum_notional=D(1), max_leverage=D(1))
        context = replace(self.proposal.market, kind="historical", quality_reviewed=True,
                          liquidity_verified=True, instrument=instrument)
        result = self.review(proposal=replace(self.proposal, market=context))
        self.assertTrue(result.approved)
        self.assertEqual(result.plan.quantity % D("0.03"), 0)
        self.assertEqual(result.record.data_kind, "historical")
        settings = replace(self.settings, leverage=2)
        controls = RiskControls(settings)
        controls.observe(D(2000), self.at)
        self.assert_rejected(self.review(settings=settings, controls=controls,
                                         proposal=replace(self.proposal, market=context)), "UNSUPPORTED_REAL_MARKET_LEVERAGE")
        bad = replace(context, instrument=replace(instrument, minimum_notional=0))
        self.assert_rejected(self.review(proposal=replace(self.proposal, market=bad)), "INSTRUMENT_MINIMUMS_REQUIRED")


class AccountAndSizingGateTests(GateFixture, unittest.TestCase):
    def test_default_quantity_preserves_legacy_numeric_result(self):
        settings = replace(self.settings, leverage=3, fee_rate=0, slippage_rate=0)
        # INR 100 margin * 3 / INR 80 = 3.75 units; no rounding or risk inflation.
        plan = size_position(settings, D(2000), D(80))
        self.assertEqual(plan.quantity, D("3.75000000"))
        self.assertEqual(plan.margin, 100)
        self.assertEqual(plan.notional, 300)

    def test_lot_division_cannot_round_a_subminimum_quantity_up(self):
        # The requested lot is just larger than the affordable two units.
        # '/' rounds the ratio to 1, and multiplication rounds the lot back to 2.
        settings = replace(self.settings, margin_amount=2, fee_rate=0, slippage_rate=0)
        with self.assertRaisesRegex(ValueError, "too small"):
            size_position(settings, D(2000), D(1), quantity_step=D("2.0000000000000000000000000001"))

    def test_unrepresentable_lot_count_rejects_instead_of_rounding(self):
        with self.assertRaises(ArithmeticError):
            size_position(self.settings, D(2000), D(100), quantity_step=D("1e-100"))
        # Integer count 3 fits, but its product with this 29-digit step rounds
        # off the exact step grid at precision 28. This must also fail closed.
        settings = replace(self.settings, margin_amount=1, fee_rate=0, slippage_rate=0)
        with self.assertRaisesRegex(ValueError, "represented safely"):
            size_position(settings, D(2000), D(1), quantity_step=D("0.33333333333333333333333333333"))
        instrument = replace(self.proposal.market.instrument, quantity_step=D("1e-100"))
        self.assert_rejected(self.review(proposal=self.with_market(instrument=instrument)),
                             "POSITION_SIZING_UNAVAILABLE")

    def test_non_power_of_ten_steps_and_exact_instrument_minimum_boundaries(self):
        settings = replace(self.settings, leverage=3, fee_rate=0, slippage_rate=0)
        controls = RiskControls(settings)
        controls.observe(D(2000), self.at)
        original = synthetic_proposal(settings, self.at, D(80))
        for step, expected in (("0.3", "3.6"), ("0.03", "3.75")):
            instrument = replace(original.market.instrument, quantity_step=D(step),
                                 minimum_quantity=D(expected), minimum_notional=D(expected) * 80)
            proposal = replace(original, market=replace(original.market, instrument=instrument))
            with self.subTest(step=step):
                result = self.review(settings=settings, controls=controls, proposal=proposal)
                self.assertTrue(result.approved)
                self.assertEqual(result.plan.quantity, D(expected))
                self.assertLessEqual(result.plan.margin, 100)
                oversized = replace(instrument, minimum_quantity=D(expected) + D("0.00000001"))
                result = self.review(settings=settings, controls=controls,
                                     proposal=replace(proposal, market=replace(proposal.market, instrument=oversized)))
                self.assert_rejected(result, "POSITION_SIZING_UNAVAILABLE")

    def test_stricter_configured_limits_are_not_raised_to_fixed_ceilings(self):
        cases = (({"risk_per_trade": "0.0025"}, "risk", D(5)),
                 ({"max_planned_risk": 7}, "risk", D(7)),
                 ({"daily_loss_limit": "0.01"}, "daily", D(20)),
                 ({"daily_loss_amount": 25}, "daily", D(25)),
                 ({"max_trades_per_day": 1}, "entries", D(1)))
        for changes, constraint, limit in cases:
            settings = replace(self.settings, margin_amount=1000, leverage=3, **changes)
            controls = RiskControls(settings)
            controls.observe(D(2000), self.at)
            proposal = synthetic_proposal(settings, self.at)
            with self.subTest(changes=changes):
                if constraint == "entries":
                    controls.record_entry()
                    self.assert_rejected(self.review(settings=settings, controls=controls, proposal=proposal),
                                         "daily_trade_limit")
                elif constraint == "daily":
                    controls.observe(D(2000) - limit, self.at)
                    self.assertEqual(controls.daily_loss_budget, limit)
                    self.assert_rejected(self.review(settings=settings, controls=controls, proposal=proposal,
                                                     equity=D(2000) - limit), "daily_loss_limit")
                else:
                    result = self.review(settings=settings, controls=controls, proposal=proposal)
                    self.assertTrue(result.approved)
                    self.assertEqual(result.record.permitted_risk, limit)
                    self.assertLessEqual(result.plan.planned_stop_risk, limit)

    def test_caller_decimal_precision_cannot_weaken_risk_comparisons(self):
        from decimal import localcontext
        expected = self.review()
        with localcontext() as context:
            context.prec = 3
            actual = self.review()
            self.assertEqual(context.prec, 3)
        self.assertEqual(actual, expected)

    def test_existing_position_rejects_even_a_valid_signal(self):
        self.assert_rejected(self.review(has_position=True), "one_open_position")

    def test_daily_halt_and_recovery_do_not_restore_permission(self):
        self.controls.daily_halted = True
        self.assert_rejected(self.review(), "daily_loss_limit")
        self.assertTrue(self.controls.daily_halted)

    def test_daily_threshold_equality_rejects_even_if_latch_was_false(self):
        self.controls.last_equity = D(1960)
        self.assert_rejected(self.review(equity=D(1960)), "daily_loss_limit")
        self.assertFalse(self.controls.daily_halted)  # gate is read-only, broker observes/latches

    def test_daily_loss_budget_is_the_lower_of_two_percent_or_forty(self):
        for start, equity in ((2000, 1960), (1000, 980), (3000, 2960)):
            self.controls.day_start_equity = D(start)
            self.controls.peak_equity = D(max(2000, start))
            self.controls.last_equity = D(equity)
            result = self.review(equity=D(equity))
            # A smaller account can also breach the stricter peak drawdown.
            self.assertFalse(result.approved)
            self.assertEqual(result.record.daily_loss_budget, min(D(40), D(start) * D("0.02")))

    def test_drawdown_and_emergency_halts_reject_and_remain_latched(self):
        for flag, reason in (("drawdown_halted", "max_drawdown"), ("emergency_halted", "emergency_shutdown")):
            setattr(self.controls, flag, True)
            self.assert_rejected(self.review(), reason)
            self.assertTrue(getattr(self.controls, flag))
            setattr(self.controls, flag, False)

    def test_third_entry_can_be_reviewed_but_fourth_cannot(self):
        self.controls.entries_today = 2
        self.assertTrue(self.review().approved)
        self.controls.entries_today = 3
        self.assert_rejected(self.review(), "daily_trade_limit")

    def test_gate_does_not_implicitly_reset_a_new_utc_day(self):
        self.assert_rejected(self.review(at=self.at + timedelta(days=1)), "STALE_MARKET_DATA")
        fresh = synthetic_proposal(self.settings, self.at + timedelta(days=1))
        self.assert_rejected(self.review(proposal=fresh, at=self.at + timedelta(days=1)), "risk_state_day_mismatch")
        self.assertEqual(self.controls.day, self.at.date())

    def test_corrupt_counters_halts_and_position_state_fail_closed(self):
        for count in (-1, 4, True, "0"):
            self.controls.entries_today = count
            self.assert_rejected(self.review(), "INVALID_ENTRY_COUNT")
        self.controls.entries_today = 0
        self.controls.daily_halted = "false"
        self.assert_rejected(self.review(), "INVALID_HALT_STATE")
        self.controls.daily_halted = False
        self.assert_rejected(self.review(has_position="false"), "invalid_position_state")

    def test_uninitialized_mismatched_or_missing_controls_reject(self):
        fresh = RiskControls(self.settings)
        self.assert_rejected(self.review(controls=fresh), "risk_state_day_mismatch")
        other = RiskControls(replace(self.settings, leverage=2))
        other.observe(D(2000), self.at)
        self.assert_rejected(self.review(controls=other), "risk_settings_mismatch")
        result = approve_entry(self.settings, None, 2000, self.proposal, at=self.at,
                               has_open_position=False, audit=self.audit)
        self.assert_rejected(result, "RISK_STATE_REQUIRED")

    def test_stale_or_inconsistent_equity_rejects(self):
        self.assert_rejected(self.review(equity=1999), "STALE_ACCOUNT_EQUITY")
        self.controls.peak_equity = D(1900)
        self.assert_rejected(self.review(), "INVALID_ACCOUNT_EQUITY")

    def test_zero_negative_and_nan_equity_reject(self):
        for value in (0, -1, "NaN", "Infinity"):
            result = self.review(equity=value)
            self.assertFalse(result.approved)
            self.assertIsNone(result.plan)

    def test_leverage_damaged_above_three_is_rejected_at_gate(self):
        settings = copy.deepcopy(self.settings)
        object.__setattr__(settings, "leverage", D(4))
        self.assert_rejected(self.review(settings=settings), "INVALID_SETTINGS")

    def test_live_or_other_initial_capital_and_weaker_daily_policy_reject(self):
        settings = copy.deepcopy(self.settings)
        object.__setattr__(settings, "mode", "live")
        self.assert_rejected(self.review(settings=settings), "INVALID_SETTINGS")
        self.assert_rejected(self.review(settings=replace(self.settings, starting_capital=3000)), "INITIAL_CAPITAL_MUST_BE_2000")
        self.assert_rejected(self.review(settings=replace(self.settings, daily_loss_limit="0.03")), "DAILY_PERCENT_LIMIT_EXCEEDS_2_PERCENT")

    def test_risk_override_cannot_raise_the_initial_ten_rupee_budget(self):
        self.assert_rejected(self.review(settings=replace(self.settings, risk_per_trade="0.01")),
                             "INITIAL_RISK_PERCENT_EXCEEDS_HALF_PERCENT")

    def boundary(self, limit):
        settings = replace(self.settings, margin_amount=1000, leverage=3, fee_rate=0, slippage_rate=0,
                           risk_per_trade="0.005")
        controls = RiskControls(settings)
        controls.observe(D(2000), self.at)
        equity = D(2000) if limit == 10 else D(4000)
        controls.peak_equity = controls.last_equity = controls.day_start_equity = equity
        proposal = synthetic_proposal(settings, self.at)
        for value, expected in ((D(limit) - D("0.00000002"), True), (D(limit), True),
                                (D(limit) + D("0.00000002"), False)):
            quantity = value / 2
            notional = quantity * 100
            plan = PositionPlan(quantity, D(100), D(98), notional / 3, notional, D(0), value)
            with self.subTest(limit=limit, risk=value), patch("risk.entry.size_position", return_value=plan):
                result = self.review(settings=settings, controls=controls, proposal=proposal, equity=equity)
            self.assertEqual(result.approved, expected)
            if not expected:
                self.assertEqual(result.reason, "PLANNED_RISK_LIMIT")
                self.assertEqual(result.record.planned_risk, value)

    def test_risk_just_below_equal_and_above_ten(self):
        self.boundary(10)

    def test_risk_just_below_equal_and_above_twenty(self):
        self.boundary(20)

    def test_fees_can_make_an_otherwise_equal_ten_rupee_plan_unsafe(self):
        settings = replace(self.settings, margin_amount=1000, leverage=3, slippage_rate=0)
        controls = RiskControls(settings)
        controls.observe(D(2000), self.at)
        proposal = synthetic_proposal(settings, self.at)
        plan = PositionPlan(D(5), D(100), D(98), D(500) / 3, D(500), D("0.5"), D(10))
        with patch("risk.entry.size_position", return_value=plan):
            self.assert_rejected(self.review(settings=settings, controls=controls, proposal=proposal), "PLANNED_RISK_LIMIT")

    def test_rounding_never_increases_quantity_to_meet_minimum(self):
        instrument = replace(self.proposal.market.instrument, quantity_step=D("0.3"))
        result = self.review(proposal=self.with_market(instrument=instrument))
        self.assertTrue(result.approved)
        self.assertEqual(result.plan.quantity % D("0.3"), 0)
        self.assertLessEqual(result.plan.margin, 100)
        instrument = replace(instrument, minimum_quantity=D(2))
        self.assert_rejected(self.review(proposal=self.with_market(instrument=instrument)), "POSITION_SIZING_UNAVAILABLE")

    def test_minimum_notional_and_unrepresentable_quantity_reject(self):
        instrument = replace(self.proposal.market.instrument, minimum_notional=D(1000))
        self.assert_rejected(self.review(proposal=self.with_market(instrument=instrument)), "POSITION_SIZING_UNAVAILABLE")
        instrument = replace(self.proposal.market.instrument, quantity_step=D(10))
        self.assert_rejected(self.review(proposal=self.with_market(instrument=instrument)), "POSITION_SIZING_UNAVAILABLE")

    def test_plan_integrity_is_checked_independently_of_sizing(self):
        plan = size_position(self.settings, D(2000), D(100))
        for changes in ({"quantity": D("NaN")}, {"margin": D(0)}, {"notional": D(1)},
                        {"stop_price": D(100)}, {"entry_fee": D(0)}, {"planned_stop_risk": D(21)}):
            with self.subTest(changes=changes), patch("risk.entry.size_position", return_value=replace(plan, **changes)):
                result = self.review()
            self.assertFalse(result.approved)
            self.assertIsNone(result.plan)

    def test_overflowing_plan_math_still_produces_a_logged_rejection(self):
        plan = PositionPlan(D("1e999999"), D("1e999999"), D("1e999998"), D(1), D(1), D(0), D(1))
        with patch("risk.entry.size_position", return_value=plan):
            result = self.review()
        self.assertFalse(result.approved)
        self.assertIsNone(result.plan)
        self.assertIsNone(result.record.estimated_fees)
        self.assertEqual(self.audit.records[-1], result.record)

    def test_position_sizing_errors_do_not_log_exception_secrets(self):
        with patch("risk.entry.size_position", side_effect=ValueError("private-password-must-not-appear")):
            result = self.review()
        self.assert_rejected(result, "POSITION_SIZING_UNAVAILABLE")
        self.assertNotIn("private-password", json.dumps([asdict(row) for row in self.audit.records], default=str))


class BrokerBoundaryTests(GateFixture, unittest.TestCase):
    def test_logging_callback_cannot_advance_account_day_during_approval(self):
        broker = PaperBroker(self.settings)
        def advance_day(*args, **kwargs):
            broker.process_bar(candle(300))
        with patch("risk.audit.LOGGER.info", side_effect=advance_day):
            with self.assertRaisesRegex(ValueError, "reentrant bar processing"):
                broker.process_bar(candle(200), Signal.BUY, entry=self.proposal)
        self.assertIsNone(broker.position)
        self.assertEqual(broker.cash, 2000)
        self.assertEqual(broker.risk.entries_today, 0)
        self.assertEqual(broker.risk.day, self.at.date())
        self.assertEqual(broker.last_bar, self.at)

    def test_handled_nested_bar_rejection_preserves_outer_entry_context(self):
        broker = PaperBroker(self.settings)
        def attempt_nested_bar(*args, **kwargs):
            with self.assertRaisesRegex(ValueError, "reentrant bar processing"):
                broker.process_bar(candle(300), Signal.BUY,
                                   entry=synthetic_proposal(self.settings, candle(300).timestamp))
        with patch("risk.audit.LOGGER.info", side_effect=attempt_nested_bar):
            broker.process_bar(candle(200), Signal.BUY, entry=self.proposal)
        self.assertIsNotNone(broker.position)
        self.assertEqual(broker.position.opened_at, self.at)
        self.assertEqual(broker.risk.entries_today, 1)
        self.assertEqual(broker.risk.day, self.at.date())
        self.assertEqual(broker.last_bar, self.at)
        self.assertEqual(len(broker.risk_audit.records), 1)

    def test_emergency_from_logging_callback_prevents_entry_commit(self):
        broker = PaperBroker(self.settings)
        with patch("risk.audit.LOGGER.info", side_effect=lambda *args, **kwargs: broker.emergency_shutdown()):
            with self.assertRaisesRegex(ValueError, "risk controls do not permit"):
                broker.process_bar(candle(200), Signal.BUY, entry=self.proposal)
        self.assertTrue(broker.risk.emergency_halted)
        self.assertIsNone(broker.position)
        self.assertEqual(broker.cash, 2000)
        self.assertEqual(broker.risk.entries_today, 0)

    def test_failed_logging_does_not_leave_bar_guard_latched(self):
        broker = PaperBroker(self.settings)
        with patch("risk.audit.LOGGER.info", side_effect=RuntimeError("synthetic logging failure")):
            with self.assertRaises(RuntimeError):
                broker.process_bar(candle(200), Signal.BUY, entry=self.proposal)
        next_bar = candle(201)
        broker.process_bar(next_bar, Signal.BUY,
                           entry=synthetic_proposal(self.settings, next_bar.timestamp))
        self.assertIsNotNone(broker.position)
        self.assertEqual(broker.risk.entries_today, 1)

    def test_structured_logger_emits_one_record_for_approval_and_rejection(self):
        broker = PaperBroker(self.settings)
        with self.assertLogs("coindcx.risk", level="INFO") as captured:
            broker.process_bar(candle(200), Signal.BUY, entry=self.proposal)
            broker.process_bar(candle(201), Signal.BUY, entry=synthetic_proposal(self.settings, candle(201).timestamp))
        records = [json.loads(record.message) for record in captured.records]
        self.assertEqual([record["reason"] for record in records], ["APPROVED", "one_open_position"])
        self.assertTrue(all(record["timestamp"].endswith("+00:00") for record in records))

    def test_direct_valid_private_open_has_no_validated_execution_bar(self):
        broker = PaperBroker(self.settings)
        broker.risk.observe(D(2000), self.at)
        self.assertFalse(broker._open(D(100), self.at, self.proposal))
        self.assertEqual(broker.risk_audit.records[-1].reason, "EXECUTION_CONTEXT_REQUIRED")
        self.assertIsNone(broker.position)

    def test_wrong_object_cannot_be_used_as_a_private_open_proposal(self):
        broker = PaperBroker(self.settings)
        broker.risk.observe(D(2000), self.at)
        plan = size_position(self.settings, D(2000), D(100))
        self.assertFalse(broker._open(D(100), self.at, plan))
        self.assertEqual(broker.risk_audit.records[-1].reason, "ENTRY_PROPOSAL_REQUIRED")

    def test_sell_cannot_log_a_long_entry_as_an_approved_trade(self):
        broker = PaperBroker(self.settings)
        broker.process_bar(candle(200), Signal.SELL, entry=self.proposal)
        self.assertIsNone(broker.position)
        self.assertEqual(broker.risk_audit.records[-1].reason, "ACTION_SIGNAL_MISMATCH")

    def test_invalid_current_bar_is_rejected_before_cash_mutation_and_logged(self):
        broker = PaperBroker(self.settings)
        malformed = copy.deepcopy(candle(200))
        object.__setattr__(malformed, "high", D(1))
        with self.assertRaises(ValueError):
            broker.process_bar(malformed, Signal.BUY, entry=self.proposal)
        self.assertIsNone(broker.position)
        self.assertEqual(broker.cash, 2000)
        self.assertEqual(broker.risk_audit.records[-1].reason, "INVALID_BROKER_CANDLE")

    def test_threaded_duplicate_entry_attempts_cannot_stack_positions(self):
        from concurrent.futures import ThreadPoolExecutor
        broker = PaperBroker(self.settings)
        def attempt():
            try:
                broker.process_bar(candle(200), Signal.BUY, entry=self.proposal)
            except ValueError:
                pass  # All later attempts are the same already processed bar.
        with ThreadPoolExecutor(max_workers=4) as executor:
            list(executor.map(lambda _: attempt(), range(8)))
        self.assertIsNotNone(broker.position)
        self.assertEqual(broker.risk.entries_today, 1)
        self.assertEqual(sum(row.approved for row in broker.risk_audit.records), 1)

    def test_raw_buy_without_context_cannot_open(self):
        broker = PaperBroker(self.settings)
        broker.process_bar(candle(200), Signal.BUY)
        self.assertIsNone(broker.position)
        self.assertEqual(broker.cash, 2000)
        self.assertEqual(broker.risk.entries_today, 0)
        self.assertEqual(broker.risk_audit.records[-1].reason, "ENTRY_PROPOSAL_REQUIRED")

    def test_private_open_method_still_requires_central_review(self):
        broker = PaperBroker(self.settings)
        broker.risk.observe(D(2000), self.at)
        broker._open(D(100), self.at)
        self.assertIsNone(broker.position)
        self.assertFalse(broker._open(D(100), self.at, replace(self.proposal, market=None)))
        self.assertEqual(len(broker.risk_audit.records), 2)

    def test_pure_sizing_and_constructed_position_are_not_order_permissions(self):
        broker = PaperBroker(self.settings)
        plan = size_position(self.settings, D(2000), D(100))
        with self.assertRaises(AttributeError):
            broker.position = Position(plan, self.at, D(100))
        with self.assertRaises(ValueError):
            entry_plan(self.settings, self.controls, D(2000), D(100), False)
        self.assertIsNone(broker.position)

    def test_compatibility_wrapper_rejects_a_bare_plan_even_with_audit(self):
        plan = size_position(self.settings, D(2000), D(100))
        with self.assertRaisesRegex(ValueError, "ENTRY_PROPOSAL_REQUIRED"):
            entry_plan(self.settings, self.controls, 2000, 100, False,
                       proposal=plan, at=self.at, audit=self.audit)
        self.assertEqual(self.audit.records[-1].reason, "ENTRY_PROPOSAL_REQUIRED")

    def test_private_exit_cannot_invent_prices_or_mutate_before_validation(self):
        broker = PaperBroker(self.settings)
        broker.process_bar(candle(200), Signal.BUY, entry=self.proposal)
        before = broker.cash, broker.position, tuple(broker.trades)
        for price, stamp in ((D(10000), self.at), (D("NaN"), self.at),
                              (D(100), self.at.replace(tzinfo=None)),
                              (D(100), self.at + timedelta(days=1))):
            with self.assertRaises(ValueError):
                broker._close(price, stamp, "synthetic_invalid_exit")
            self.assertEqual((broker.cash, broker.position, tuple(broker.trades)), before)

    def test_repeated_buy_is_reviewed_and_logged_as_one_position_rejection(self):
        broker = PaperBroker(self.settings)
        broker.process_bar(candle(200), Signal.BUY, entry=self.proposal)
        first = broker.position
        broker.process_bar(candle(201), Signal.BUY, entry=synthetic_proposal(self.settings, candle(201).timestamp))
        self.assertIs(broker.position, first)
        self.assertEqual(broker.risk.entries_today, 1)
        self.assertEqual([row.reason for row in broker.risk_audit.records], ["APPROVED", "one_open_position"])

    def test_three_entries_then_fourth_and_utc_rollover(self):
        broker = PaperBroker(self.settings)
        for index in range(200, 208, 2):
            broker.process_bar(candle(index), Signal.BUY, entry=synthetic_proposal(self.settings, candle(index).timestamp))
            broker.process_bar(candle(index + 1), Signal.SELL)
        self.assertEqual(len(broker.trades), 3)
        self.assertEqual(broker.risk.entries_today, 3)
        self.assertEqual(broker.risk_audit.records[-1].reason, "daily_trade_limit")
        broker.process_bar(candle(288), Signal.BUY, entry=synthetic_proposal(self.settings, candle(288).timestamp))
        self.assertIsNotNone(broker.position)
        self.assertEqual(broker.risk.entries_today, 1)

    def test_gap_daily_halt_blocks_direct_reentry_even_with_new_valid_proposal(self):
        broker = PaperBroker(self.settings)
        broker.process_bar(candle(200), Signal.BUY, entry=self.proposal)
        broker.process_bar(candle(201, open="50", high="50", low="50", close="50"))
        cash = broker.cash
        broker.process_bar(candle(202), Signal.BUY, entry=synthetic_proposal(self.settings, candle(202).timestamp))
        self.assertIsNone(broker.position)
        self.assertEqual(broker.cash, cash)
        self.assertEqual(broker.risk_audit.records[-1].reason, "daily_loss_limit")

    def test_emergency_closes_once_and_reused_proposal_cannot_reenter(self):
        broker = PaperBroker(self.settings)
        broker.process_bar(candle(200), Signal.BUY, entry=self.proposal)
        broker.emergency_shutdown()
        cash = broker.cash
        broker._open(D(100), self.at, self.proposal)
        self.assertIsNone(broker.position)
        self.assertEqual(broker.cash, cash)
        self.assertEqual(broker.risk_audit.records[-1].reason, "emergency_shutdown")

    def test_valid_old_approval_cannot_bypass_recheck_of_changed_state(self):
        broker = PaperBroker(self.settings)
        broker.risk.observe(D(2000), self.at)
        approval = self.review()
        self.assertTrue(approval.approved)
        broker.risk.emergency_halted = True
        broker._open(D(100), self.at, self.proposal)
        self.assertIsNone(broker.position)
        self.assertEqual(broker.risk_audit.records[-1].reason, "emergency_shutdown")

    def test_private_open_rejects_changed_fill_reference(self):
        broker = PaperBroker(self.settings)
        broker.risk.observe(D(2000), self.at)
        self.assertFalse(broker._open(D(101), self.at, self.proposal))
        self.assertEqual(broker.risk_audit.records[-1].reason, "ENTRY_PROPOSAL_REQUIRED")

    def test_short_proposal_cannot_be_used_with_buy_action(self):
        broker = PaperBroker(self.settings)
        decision = replace(self.proposal.decision, signal=Direction.SHORT, stop_loss_reference=D(102))
        broker.process_bar(candle(200), Signal.BUY, entry=replace(self.proposal, decision=decision))
        self.assertIsNone(broker.position)
        self.assertEqual(broker.risk_audit.records[-1].reason, "SHORT_ENTRY_UNSUPPORTED")

    def test_audit_logging_failure_prevents_any_entry_mutation(self):
        broker = PaperBroker(self.settings)
        with patch("risk.audit.LOGGER.info", side_effect=RuntimeError("synthetic log failure")):
            with self.assertRaises(RuntimeError):
                broker.process_bar(candle(200), Signal.BUY, entry=self.proposal)
        self.assertIsNone(broker.position)
        self.assertEqual(broker.cash, 2000)
        self.assertEqual(broker.risk.entries_today, 0)

    def test_audit_is_mandatory_for_direct_gate_and_compatibility_api(self):
        with self.assertRaises(ValueError):
            approve_entry(self.settings, self.controls, 2000, self.proposal, at=self.at,
                          has_open_position=False, audit=None)
        with self.assertRaises(ValueError):
            entry_plan(self.settings, self.controls, 2000, 100, False, proposal=self.proposal, at=self.at)


class ReplayAndCommandBoundaryTests(unittest.TestCase):
    def test_reporting_exports_approval_and_rejection_audit_csv(self):
        from backtesting.datasets import load_eligible
        from backtesting.experiment import run_experiment
        from backtesting.reporting import write_report
        from strategies import create_strategy
        from tests.test_chronological_evaluation import split_plan
        import csv
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.synthetic.csv"
            generate(path, 800)
            dataset = load_eligible(path, self.settings, allow_synthetic=True)
            report = run_experiment(dataset, self.settings, create_strategy("sma_cross"), split_plan())
            output = Path(directory) / "report"
            write_report(output, report)
            with (output / "risk_decisions.csv").open(newline="", encoding="utf-8") as stream:
                records = list(csv.DictReader(stream))
            self.assertTrue(records)
            self.assertTrue(all(record["data_kind"] == "synthetic" for record in records))
            self.assertTrue(all(record["timestamp"] and record["reason"] for record in records))
            self.assertIn("effective_leverage", records[0])
            # A no-entry run must still export one unambiguous audit schema.
            empty = copy.deepcopy(report)
            groups = [empty["periods"], empty["cost_stress"]["periods"]]
            groups.extend(candidate["periods"] for candidate in empty["parameter_sensitivity"])
            for group in groups:
                for period in group:
                    period["simulation"]["risk_decisions"] = []
            empty_output = Path(directory) / "empty-report"
            write_report(empty_output, empty)
            with (empty_output / "risk_decisions.csv").open(newline="", encoding="utf-8") as stream:
                reader = csv.DictReader(stream)
                self.assertEqual(len(reader.fieldnames), len(set(reader.fieldnames)))
                self.assertIn("effective_leverage", reader.fieldnames)
                self.assertEqual(list(reader), [])

    def test_manual_and_verify_call_the_same_gate_and_cannot_construct_a_broker(self):
        from tests.test_signal_verification import VerificationFixture
        fixture = type("SyntheticManualFixture", (VerificationFixture, unittest.TestCase), {})()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        for command in ("manual", "verify"):
            output = io.StringIO()
            with patch.dict(os.environ, {"BOT_MIN_HISTORY_BARS": "200"}, clear=True), \
                 patch("risk.entry.approve_entry", wraps=approve_entry) as gate, \
                 patch("paper_trading.broker.PaperBroker.__init__", side_effect=AssertionError("orders forbidden")), \
                 patch("socket.socket", side_effect=AssertionError("network forbidden")), redirect_stdout(output):
                status = main([command, "--data", str(fixture.path), "--strategy", "momentum", "--lookback", "1",
                               "--as-of", fixture.review()["as_of"], "--risk-state", str(fixture.state), "--allow-synthetic"])
            self.assertEqual(status, 0)
            self.assertGreater(gate.call_count, 0)
            report = json.loads(output.getvalue())
            self.assertEqual(report["orders_submitted"], 0)
            self.assertTrue(report["risk_decisions"][-1]["approved"])

    def test_malformed_enriched_decision_is_audited_before_emergency_cleanup(self):
        from strategies.momentum import Momentum
        class Bad(Momentum):
            def evaluate(self, candles, **context):
                return replace(super().evaluate(candles, **context), timestamp=context["as_of"] + timedelta(minutes=15))
        broker = PaperBroker(self.settings)
        with patch("backtesting.engine.PaperBroker", return_value=broker):
            with self.assertRaises(ValueError):
                simulate(self.settings, self.market, Bad(1))
        self.assertTrue(broker.risk.emergency_halted)
        self.assertFalse(broker.risk_audit.records[-1].approved)
        self.assertEqual(broker.risk_audit.records[-1].reason, "INVALID_SIGNAL_OR_STOP")
    def setUp(self):
        self.settings = Settings(min_history_bars=200)
        self.bars = tuple(candle(index) for index in range(205))
        self.market = MarketData("SYNTHETIC-INR", "INR", "synthetic", "synthetic unit fixture", self.bars)

    def test_replay_uses_central_gate_for_each_buy_and_returns_decisions(self):
        with patch("risk.entry.approve_entry", wraps=approve_entry) as gate:
            result = simulate(self.settings, self.market, AlwaysBuy())
        self.assertGreater(gate.call_count, 0)
        self.assertEqual(gate.call_count, len(result.risk_decisions))
        self.assertEqual(result.risk_decisions[0].reason, "APPROVED")
        self.assertTrue(all(row.reason == "one_open_position" for row in result.risk_decisions[1:]))

    def test_direct_replay_cannot_ignore_an_ineligible_context(self):
        context = replace(MarketContext.synthetic(self.market.symbol, self.settings, allow_synthetic=True), eligible=False)
        result = simulate(self.settings, self.market, AlwaysBuy(), risk_context=context)
        self.assertEqual(result.trades, ())
        self.assertTrue(all(row.reason == "MARKET_INELIGIBLE" for row in result.risk_decisions))

    def test_real_market_without_explicit_evidence_cannot_get_synthetic_fallback(self):
        # Synthetic prices with historical metadata are a deliberate gate stand-in.
        market = replace(self.market, kind="historical", source="https://example.org/synthetic-stand-in")
        result = simulate(self.settings, market, AlwaysBuy())
        self.assertEqual(result.trades, ())
        self.assertTrue(all(row.reason == "MARKET_CONTEXT_REQUIRED" for row in result.risk_decisions))

    def test_valid_data_cannot_bypass_missing_costs_or_instrument_via_simulate(self):
        context = MarketContext.synthetic(self.market.symbol, self.settings, allow_synthetic=True)
        for changes, reason in (({"costs": None}, "COST_ASSUMPTIONS_REQUIRED"),
                                ({"instrument": None}, "INSTRUMENT_DETAILS_REQUIRED")):
            result = simulate(self.settings, self.market, AlwaysBuy(), risk_context=replace(context, **changes))
            self.assertEqual(result.trades, ())
            self.assertTrue(all(row.reason == reason for row in result.risk_decisions))

    def test_both_simulation_cli_commands_use_central_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.synthetic.csv"
            generate(path, 210)
            for command in ("backtest", "paper"):
                output = io.StringIO()
                with patch.dict(os.environ, {"BOT_MIN_HISTORY_BARS": "200"}, clear=True), \
                     patch("risk.entry.approve_entry", wraps=approve_entry) as gate, redirect_stdout(output), redirect_stderr(io.StringIO()):
                    status = main([command, "--data", str(path), "--strategy", "momentum", "--allow-synthetic"])
                self.assertEqual(status, 0)
                self.assertGreater(gate.call_count, 0)
                report = json.loads(output.getvalue())
                self.assertEqual(len(report["risk_decisions"]), gate.call_count)
                self.assertFalse(report["live_trading_enabled"])
