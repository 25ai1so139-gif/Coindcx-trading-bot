"""Synthetic account/candle fixtures only, including historical-gate stand-ins."""

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from cli import main
from config import Settings
from data.loader import load_csv
from risk.context import VerificationAccount
from strategies.momentum import Momentum
from strategies.base import Signal
from strategies.verification import verify_file
from tests.market_fixtures import SYMBOL, csv_fixture, end, rows


def account_mapping(**changes):
    """Fabricated simulated state for tests; never an actual account snapshot."""
    return {"schema_version": 1, "account_mode": "paper", "kind": "synthetic",
            "label": "SYNTHETIC offline test account", "as_of": end().isoformat(),
            "starting_capital": "2000", "equity": "2000", "peak_equity": "2000",
            "day_start_equity": "2000", "day": end().date().isoformat(), "entries_today": 0,
            "has_open_position": False, "daily_halted": False, "drawdown_halted": False,
            "emergency_halted": False, **changes}


class VerificationFixture:
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.path = self.directory / "synthetic.csv"
        self.state = self.directory / "synthetic-account.json"
        self.write_records()
        self.write_account()
        self.settings = Settings(min_history_bars=200)

    def write_records(self, records=None):
        if records is None:
            records = rows()
            records[-1].update(close="104", high="104")
        csv_fixture(self.path, records)
        # The nine-column Phase 2 schema requires its matching version-2 sidecar.
        sidecar = self.path.with_suffix(".json")
        metadata = json.loads(sidecar.read_text())
        metadata.update(schema_version=2, ingestion_eligible=True,
                        data_policy={"min_history_bars": 200, "min_quote_volume_per_bar": "100"})
        sidecar.write_text(json.dumps(metadata), encoding="utf-8")

    def write_account(self, **changes):
        self.state.write_text(json.dumps(account_mapping(**changes)), encoding="utf-8")

    def review(self, **changes):
        arguments = {"as_of": end(), "symbol": SYMBOL, "allow_synthetic": True,
                     "risk_state": self.state, **changes}
        return verify_file(self.path, self.settings, Momentum(1), **arguments)

    def assert_no_trade(self, report, reason=None):
        self.assertEqual(report["signal"], "NO_TRADE")
        self.assertFalse(report["entry_candidate"])
        self.assertEqual(report["orders_submitted"], 0)
        self.assertFalse(report["live_trading_enabled"])
        if reason:
            self.assertIn(reason, report["reasons"])


class VerificationTests(VerificationFixture, unittest.TestCase):
    def test_valid_long_has_timestamp_parameters_reasons_and_shared_cost_inclusive_plan(self):
        self.settings = Settings(min_history_bars=200, margin_amount=1000, leverage=3)
        report = self.review()
        self.assertEqual(report["signal"], "LONG")
        self.assertEqual(report["signal_timestamp"], end())
        self.assertEqual(report["strategy_parameters"]["lookback"], 1)
        self.assertIn("POSITIVE_MOMENTUM", report["reasons"])
        plan = report["risk_preview"]
        self.assertLessEqual(plan["planned_stop_risk"], 10)
        self.assertGreater(plan["planned_stop_risk"], Decimal("9.99"))
        self.assertEqual(report["stop_loss_reference"], plan["stop_price"])
        self.assertEqual(report["entry_reference"], plan["entry_price"])
        self.assertGreater(plan["entry_fee"], 0)
        self.assertEqual(plan["notional"], plan["margin"] * 3)
        self.assertEqual(report["orders_submitted"], 0)
        self.assertIn("Synthetic", report["warning"])
        stop_fill = plan["stop_price"] * (1 - self.settings.slippage_rate)
        modeled_loss = (plan["quantity"] * (plan["entry_price"] - stop_fill)
                        + plan["entry_fee"] + plan["quantity"] * stop_fill * self.settings.fee_rate)
        self.assertAlmostEqual(plan["planned_stop_risk"], modeled_loss, places=20)

    def test_signal_timestamp_is_last_close_not_the_later_review_time(self):
        report = self.review(as_of=end() + timedelta(minutes=15))
        self.assertEqual(report["signal"], "LONG")
        self.assertEqual(report["signal_timestamp"], end())
        self.assertNotEqual(report["signal_timestamp"].isoformat(), report["as_of"])

    def test_invalid_strategy_results_cannot_get_a_verified_risk_preview(self):
        market = load_csv(self.path, min_history_bars=200, allow_synthetic=True)
        candidate = Momentum(1).evaluate(market.candles, as_of=end(), symbol=SYMBOL)
        changes = (
            {"timestamp": end() + timedelta(minutes=15)},
            {"timestamp": end() - timedelta(minutes=15)},
            {"timestamp": end().replace(tzinfo=None)},
            {"signal": Signal.SELL}, {"signal": "LONG"},
            {"strategy": "different_strategy"}, {"symbol": "I-OTHER_INR"}, {"timeframe": "1h"},
            {"entry_reference": Decimal("999")}, {"stop_loss_reference": Decimal("1")},
            {"stop_loss_reference": Decimal("NaN")}, {"indicators": {"return_fraction": Decimal("NaN")}},
            {"reason": ""}, {"reason_code": ""},
        )
        for change in changes:
            with self.subTest(change=change), patch.object(Momentum, "evaluate", return_value=replace(candidate, **change)):
                report = self.review()
                self.assert_no_trade(report, "INVALID_STRATEGY_DECISION")
                self.assertIsNone(report["risk_preview"])
                self.assertIsNone(report["signal_timestamp"])

    def test_unrepresentable_stop_does_not_receive_manual_approval(self):
        self.settings = Settings(min_history_bars=200, stop_loss_fraction="1e-40")
        report = self.review()
        self.assert_no_trade(report, "INVALID_INDICATOR")
        self.assertIsNone(report["risk_preview"])

    def test_larger_configured_initial_budget_is_rejected_by_central_gate(self):
        self.settings = Settings(min_history_bars=200, margin_amount=1000, leverage=3, risk_per_trade="0.02")
        self.assert_no_trade(self.review(), "INITIAL_RISK_PERCENT_EXCEEDS_HALF_PERCENT")

    def test_small_margin_does_not_force_a_ten_rupee_loss(self):
        plan = self.review()["risk_preview"]
        self.assertGreater(plan["planned_stop_risk"], 0)
        self.assertLess(plan["planned_stop_risk"], 10)

    def test_remaining_daily_budget_reduces_manual_plan(self):
        self.write_account(equity="1961")
        plan = self.review()["risk_preview"]
        self.assertGreater(plan["planned_stop_risk"], 0)
        self.assertLessEqual(plan["planned_stop_risk"], 1)

    def test_missing_state_never_assumes_a_new_account(self):
        self.assert_no_trade(self.review(risk_state=None), "RISK_STATE_REQUIRED")

    def test_symbol_and_timeframe_mismatches_are_rejected(self):
        for arguments, reason in (({"symbol": "I-OTHER_INR"}, "SYMBOL_MISMATCH"),
                                  ({"symbol": "../bad"}, "INVALID_SYMBOL"),
                                  ({"timeframe": "1m"}, "INVALID_TIMEFRAME")):
            with self.subTest(arguments=arguments):
                self.assert_no_trade(self.review(**arguments), reason)

    def test_historical_data_is_not_claimed_fresh_now(self):
        self.assert_no_trade(self.review(as_of=None), "STALE_DATA")

    def test_incomplete_candle_cannot_enter_the_strategy(self):
        report = self.review(as_of=end() - timedelta(minutes=5))
        self.assert_no_trade(report, "DATA_INELIGIBLE")
        self.assertIsNone(report["candidate"])
        self.assertIn("INCOMPLETE_CANDLES_EXCLUDED", report["warnings"])

    def test_missing_corrupt_duplicate_and_insufficient_datasets_fail_closed(self):
        for records in (rows(199), rows()[:50] + rows()[51:], rows() + [rows()[-1]]):
            with self.subTest(count=len(records)):
                self.write_records(records)
                self.assert_no_trade(self.review(), "VERIFICATION_REJECTED")
        self.path.unlink()
        self.assert_no_trade(self.review(), "VERIFICATION_REJECTED")

    def test_future_data_and_future_evaluation_are_rejected(self):
        self.write_records(rows(202))
        self.assert_no_trade(self.review(), "FUTURE_DATA")
        from datetime import datetime, timezone
        self.assert_no_trade(self.review(as_of=datetime(2099, 1, 1, tzinfo=timezone.utc)),
                             "FUTURE_EVALUATION_TIME")

    def test_invalid_evaluation_time_is_a_structured_abstention(self):
        self.assert_no_trade(self.review(as_of="not a timestamp"), "INVALID_EVALUATION_TIME")

    def test_quality_cannot_approve_different_candles_from_the_signal_input(self):
        market = load_csv(self.path, min_history_bars=200, allow_synthetic=True)
        different = replace(market, candles=(*market.candles[:-1],
                                             replace(market.candles[-1], close=Decimal("101"))))
        with patch("strategies.verification.load_csv", return_value=different):
            self.assert_no_trade(self.review(), "DATA_CHANGED_DURING_REVIEW")

    def test_neutral_signal_and_long_strategy_warmup_remain_no_trade(self):
        self.write_records(rows())
        self.assert_no_trade(self.review(), "BELOW_THRESHOLD")
        self.write_records()
        report = verify_file(self.path, self.settings, Momentum(300), as_of=end(),
                             symbol=SYMBOL, allow_synthetic=True, risk_state=self.state)
        self.assert_no_trade(report, "INSUFFICIENT_DATA")

    def test_short_candidate_is_explicit_but_unsupported_entry_is_rejected(self):
        records = rows()
        records[-1].update(close="98", low="98")
        self.write_records(records)
        report = self.review()
        self.assert_no_trade(report, "SHORT_ENTRY_UNSUPPORTED")
        self.assertEqual(report["candidate"]["signal"], "SHORT")
        self.assertGreater(report["stop_loss_reference"], report["entry_reference"])
        self.assertIsNone(report["risk_preview"])

    def test_daily_halt_and_recovered_but_latched_daily_halt_reject(self):
        for state in ({"equity": "1960"}, {"daily_halted": True}):
            with self.subTest(state=state):
                self.write_account(**state)
                self.assert_no_trade(self.review(), "daily_loss_limit")

    def test_drawdown_halt_and_emergency_halt_reject(self):
        for state, reason in (({"peak_equity": "2200", "equity": "2090"}, "max_drawdown"),
                              ({"emergency_halted": True}, "emergency_shutdown")):
            with self.subTest(state=state):
                self.write_account(**state)
                self.assert_no_trade(self.review(), reason)

    def test_three_entries_and_one_open_position_block_new_entry(self):
        for state, reason in (({"entries_today": 3}, "daily_trade_limit"),
                              ({"has_open_position": True}, "one_open_position")):
            with self.subTest(state=state):
                self.write_account(**state)
                self.assert_no_trade(self.review(), reason)

    def test_stale_future_and_wrong_day_states_do_not_reset_limits(self):
        for state, reason in (({"as_of": (end() - timedelta(minutes=31)).isoformat()}, "stale_risk_state"),
                              ({"as_of": (end() + timedelta(minutes=1)).isoformat()}, "future_risk_state"),
                              ({"day": (end() - timedelta(days=1)).date().isoformat()}, "risk_state_day_mismatch")):
            with self.subTest(state=state):
                self.write_account(**state)
                report = self.review()
                self.assert_no_trade(report, "VERIFICATION_REJECTED")
                self.assertIn(reason, report["reasons"])

    def test_malformed_and_live_account_states_reject_without_orders(self):
        for state in ({"entries_today": -1}, {"entries_today": 4}, {"entries_today": True},
                      {"has_open_position": "false"}, {"emergency_halted": "false"},
                      {"equity": "NaN"}, {"peak_equity": "100"}, {"account_mode": "live"},
                      {"starting_capital": "10000"}, {"schema_version": True}):
            with self.subTest(state=state):
                self.write_account(**state)
                self.assert_no_trade(self.review(), "VERIFICATION_REJECTED")
        self.state.write_text('{"truncated": true}')
        self.assert_no_trade(self.review(), "VERIFICATION_REJECTED")

    def test_account_kind_and_conflicting_state_sources_are_rejected(self):
        self.write_account(kind="paper")
        self.assert_no_trade(self.review(), "ACCOUNT_DATA_KIND_MISMATCH")
        account = VerificationAccount.from_mapping(self.settings, account_mapping())
        self.assert_no_trade(self.review(account=account), "AMBIGUOUS_RISK_STATE")

    def test_repeat_reviews_do_not_mutate_account_counters_latches_or_files(self):
        account = VerificationAccount.from_mapping(self.settings, account_mapping(entries_today=2))
        before = vars(account.controls).copy()
        before_files = {path.name: path.read_bytes() for path in self.directory.iterdir()}
        first = self.review(account=account, risk_state=None)
        second = self.review(account=account, risk_state=None)
        self.assertEqual(first, second)
        self.assertEqual(first["signal"], "LONG")
        self.assertEqual(vars(account.controls), before)
        self.assertEqual({path.name: path.read_bytes() for path in self.directory.iterdir()}, before_files)

    def test_direct_context_cannot_bypass_count_or_boolean_validation(self):
        for key, value in (("entries_today", -1), ("emergency_halted", "false")):
            account = VerificationAccount.from_mapping(self.settings, account_mapping())
            setattr(account.controls, key, value)
            with self.subTest(key=key):
                self.assert_no_trade(self.review(account=account, risk_state=None), "VERIFICATION_REJECTED")

    def test_current_equity_breach_is_detected_without_mutating_source_controls(self):
        account = VerificationAccount.from_mapping(self.settings, account_mapping())
        account = replace(account, equity=Decimal("1960"))
        self.assert_no_trade(self.review(account=account, risk_state=None), "daily_loss_limit")
        self.assertFalse(account.controls.daily_halted)

    def test_real_data_policy_cannot_use_the_research_liquidity_override(self):
        # All bytes are still synthetic test evidence. The metadata switch only
        # exercises the historical review path; no real market is represented.
        meta_path = self.path.with_suffix(".json")
        meta = json.loads(meta_path.read_text())
        meta.update(kind="historical", source="https://api.coindcx.com/market_data/candles",
                    quality_reviewed=True, quote_volume_verified=False,
                    data_policy={"min_history_bars": 200, "require_verified_liquidity": False})
        meta_path.write_text(json.dumps(meta))
        self.write_account(kind="paper")
        self.assert_no_trade(self.review(allow_synthetic=False), "LIQUIDITY_REVIEW_REQUIRED")


class ManualCommandTests(VerificationFixture, unittest.TestCase):
    # Exercise the CLI with sockets and broker construction prohibited.
    def invoke(self, *extra):
        output, errors = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, {"BOT_MIN_HISTORY_BARS": "200"}, clear=True), \
             patch("socket.socket", side_effect=AssertionError("network forbidden")), \
             patch("paper_trading.broker.PaperBroker.__init__", side_effect=AssertionError("broker forbidden")), \
             redirect_stdout(output), redirect_stderr(errors):
            status = main([*extra])
        return status, json.loads(output.getvalue()), errors.getvalue()

    def arguments(self, command="manual"):
        return [command, "--data", str(self.path), "--symbol", SYMBOL, "--timeframe", "15m",
                "--allow-synthetic", "--as-of", end().isoformat(), "--risk-state", str(self.state),
                "--strategy", "momentum", "--lookback", "1", "--threshold", "0.01"]

    def test_both_manual_alias_and_verify_are_offline_and_order_free(self):
        for command in ("manual", "verify"):
            code, report, errors = self.invoke(*self.arguments(command))
            with self.subTest(command=command):
                self.assertEqual(code, 0, errors)
                self.assertEqual(report["signal"], "LONG")
                self.assertEqual(report["orders_submitted"], 0)
                self.assertFalse(report["live_trading_enabled"])

    def test_both_aliases_reject_future_strategy_timestamps_without_orders(self):
        market = load_csv(self.path, min_history_bars=200, allow_synthetic=True)
        decision = Momentum(1).evaluate(market.candles, as_of=end(), symbol=SYMBOL)
        decision = replace(decision, timestamp=end() + timedelta(minutes=15))
        for command in ("manual", "verify"):
            with self.subTest(command=command), patch.object(Momentum, "evaluate", return_value=decision):
                code, report, errors = self.invoke(*self.arguments(command))
                self.assertEqual(code, 0, errors)
                self.assert_no_trade(report, "INVALID_STRATEGY_DECISION")

    def test_manual_rejects_excess_leverage_and_invalid_parameters_as_no_trade(self):
        for extra in (["--leverage", "4"], ["--lookback", "0"], ["--threshold", "NaN"],
                      ["--fast", "2"]):
            with self.subTest(extra=extra):
                code, report, errors = self.invoke(*self.arguments(), *extra)
                self.assertEqual(code, 2)
                self.assert_no_trade(report)

    def test_manual_risk_halt_and_stale_data_are_no_trade(self):
        self.write_account(emergency_halted=True)
        code, report, errors = self.invoke(*self.arguments())
        self.assertEqual(code, 0, errors)
        self.assert_no_trade(report, "emergency_shutdown")
        arguments = self.arguments()
        index = arguments.index("--as-of")
        del arguments[index:index+2]
        code, report, errors = self.invoke(*arguments)
        self.assertEqual(code, 0, errors)
        self.assert_no_trade(report, "STALE_DATA")
