"""Labelled synthetic fixtures exercise gates, splits, reports and no tuning."""

import csv
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from backtesting.datasets import BacktestBlocked, load_eligible
from backtesting.experiment import run_experiment
from backtesting.reporting import write_report
from backtesting.splits import SplitPlan, chronological_periods
from cli import main
from config import Settings
from data.quality import DataPolicy
from strategies import create_strategy
from tests.helpers import START, candle
from tests.test_backtesting import market
from tools.generate_sample_data import generate


def split_plan():
    return SplitPlan(*(START + timedelta(minutes=15 * index) for index in (200, 400, 600, 800)),
                     min_evaluation_bars=200)


class SplitTests(unittest.TestCase):
    def setUp(self):
        self.market = market(candle(index) for index in range(800))
        self.settings = Settings(min_history_bars=200)

    def test_chronological_disjoint_exact_coverage(self):
        periods = chronological_periods(self.market, self.settings, 21, split_plan())
        self.assertEqual([period.name for period in periods], ["train", "validation", "test"])
        seen = set()
        for index, period in enumerate(periods):
            bars = period.market.candles[period.warmup_bars:]
            self.assertEqual(len(bars), 200)
            self.assertEqual(period.warmup_bars, 200)
            self.assertEqual(bars[0].timestamp, candle((index + 1) * 200).timestamp)
            self.assertFalse(seen.intersection(bar.timestamp for bar in bars))
            seen.update(bar.timestamp for bar in bars)
            self.assertTrue(all(bar.closed_at <= period.start for bar in period.market.candles[:period.warmup_bars]))
            self.assertTrue(all(bar.closed_at <= period.end for bar in bars))

    def test_ranges_are_never_shuffled(self):
        for period in chronological_periods(self.market, self.settings, 21, split_plan()):
            times = [bar.timestamp for bar in period.market.candles]
            self.assertEqual(times, sorted(times))

    def test_configurable_ranges_normalize_aware_offsets_to_utc(self):
        plan = SplitPlan("2024-01-03T07:30:00+05:30", "2024-01-05T09:30:00+05:30",
                         "2024-01-07T11:30:00+05:30", "2024-01-09T13:30:00+05:30", 200)
        self.assertEqual(plan, split_plan())

    def test_invalid_dates_order_alignment_and_minimum_are_rejected(self):
        plan = split_plan()
        cases = ({"train_start": plan.validation_start}, {"test_end": plan.test_start},
                 {"train_start": START.replace(tzinfo=None)},
                 {"test_start": plan.test_start + timedelta(minutes=1)},
                 {"min_evaluation_bars": 199}, {"min_evaluation_bars": True})
        for changes in cases:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(plan, **changes)

    def test_insufficient_periods_and_missing_boundary_coverage_are_blocked(self):
        for plan in (replace(split_plan(), min_evaluation_bars=201),
                     replace(split_plan(), train_start=candle(199).timestamp),
                     replace(split_plan(), test_end=candle(801).timestamp)):
            with self.subTest(plan=plan), self.assertRaisesRegex(ValueError, "insufficient evidence"):
                chronological_periods(self.market, self.settings, 21, plan)

    def test_larger_indicator_warmup_must_fit_before_train_start(self):
        with self.assertRaisesRegex(ValueError, "preceding warmup"):
            chronological_periods(self.market, self.settings, 201, split_plan())


class DatasetAndEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "fixture.synthetic.csv"
        generate(self.path, 800)
        self.settings = Settings(min_history_bars=200)
        self.strategy = create_strategy("sma_cross")

    def metadata(self, **changes):
        path = self.path.with_suffix(".json")
        meta = json.loads(path.read_text(encoding="utf-8"))
        meta.update(changes)
        path.write_text(json.dumps(meta), encoding="utf-8")

    def dataset(self):
        return load_eligible(self.path, self.settings, allow_synthetic=True)

    def experiment(self, **kwargs):
        return run_experiment(self.dataset(), self.settings, self.strategy, split_plan(), **kwargs)

    def invoke(self, command="evaluate", *extra):
        plan = self.root / "plan.json"
        plan.write_text(json.dumps({"train_start": candle(200).timestamp.isoformat(),
                                  "validation_start": candle(400).timestamp.isoformat(),
                                  "test_start": candle(600).timestamp.isoformat(),
                                  "test_end": candle(800).timestamp.isoformat(),
                                  "min_evaluation_bars": 200}), encoding="utf-8")
        args = [command, "--data", str(self.path), "--allow-synthetic"]
        if command == "evaluate":
            args += ["--plan", str(plan), "--output", str(self.root / "report")]
        output, errors = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, {"BOT_MIN_HISTORY_BARS": "200"}, clear=True), redirect_stdout(output), redirect_stderr(errors):
            status = main([*args, *extra])
        return status, output.getvalue(), errors.getvalue()

    def test_synthetic_opt_in_and_unequivocal_source_label(self):
        with self.assertRaisesRegex(BacktestBlocked, "synthetic"):
            load_eligible(self.path, self.settings)
        dataset = self.dataset()
        self.assertEqual(dataset.evidence["source_class"], "synthetic")
        self.assertIn("SYNTHETIC_DATA_NOT_MARKET_EVIDENCE", dataset.evidence["quality"]["warnings"])
        self.assertFalse(dataset.evidence["current_market_freshness_qualified"])

    def test_legacy_historical_liquidity_bypass_is_closed(self):
        # Generated prices remain SYNTHETIC stand-ins, even with historical metadata.
        self.metadata(kind="historical", quality_reviewed=True, source="https://api.coindcx.com/market_data/candles")
        for require in (True, False):
            policy = DataPolicy(min_history_bars=200, require_verified_liquidity=require)
            with self.subTest(require=require), self.assertRaisesRegex(BacktestBlocked, "LIQUIDITY_REVIEW_REQUIRED"):
                load_eligible(self.path, self.settings, policy=policy)

    def test_both_old_simulation_commands_reject_unqualified_historical_data(self):
        self.metadata(kind="historical", quality_reviewed=True, source="https://example.org/synthetic-stand-in")
        for command in ("backtest", "paper"):
            with patch("backtesting.engine.PaperBroker", side_effect=AssertionError):
                status, output, errors = self.invoke(command)
            self.assertEqual(status, 2, errors)
            self.assertEqual(json.loads(output)["status"], "BLOCKED")
            self.assertIn("LIQUIDITY_REVIEW_REQUIRED", output)

    def test_historical_source_categories_do_not_assert_independent_authentication(self):
        # All rows are SYNTHETIC stand-ins, including the invented quote volumes.
        # Historical metadata exercises label/gate logic, not real qualification.
        import hashlib
        with self.path.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        for row in rows:
            row["quote_volume"] = "100000"
            row["symbol"] = "SYNTHETIC-INR"
            row["timeframe"] = "15m"
        with self.path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        for source, label in (("https://api.coindcx.com/market_data/candles", "coindcx_public_provenance"),
                              ("https://example.org/synthetic-test", "imported_external_provenance")):
            self.metadata(kind="historical", quality_reviewed=True, source=source, quote_volume_verified=True,
                          schema_version=2, ingestion_eligible=True,
                          sha256=hashlib.sha256(self.path.read_bytes()).hexdigest(),
                          data_policy={"min_history_bars": 200, "min_quote_volume_per_bar": "1000"})
            with self.subTest(label=label):
                dataset = self.dataset()
                self.assertEqual(dataset.evidence["source_class"], label)
                self.assertIn("not independently authenticated", dataset.evidence["provenance_limit"])

    def test_staleness_is_checked_relative_to_explicit_historical_cutoff(self):
        dataset = self.dataset()
        self.assertEqual(dataset.evidence["historical_as_of"], candle(800).timestamp.isoformat())
        with self.assertRaisesRegex(BacktestBlocked, "STALE_DATA"):
            load_eligible(self.path, self.settings, allow_synthetic=True, as_of=candle(803).timestamp)

    def test_incomplete_at_requested_cutoff_is_not_simulated(self):
        with self.assertRaises(BacktestBlocked):
            load_eligible(self.path, self.settings, allow_synthetic=True, as_of=candle(799).timestamp)

    def test_changed_csv_or_invalid_ohlc_is_blocked(self):
        self.path.write_bytes(self.path.read_bytes().replace(b"1000", b"-100", 1))
        with self.assertRaisesRegex(BacktestBlocked, "SHA-256"):
            self.dataset()

    def test_checksum_updated_corrupt_data_is_still_blocked(self):
        import hashlib
        self.path.write_bytes(self.path.read_bytes().replace(b"1000", b"-100", 1))
        self.metadata(sha256=hashlib.sha256(self.path.read_bytes()).hexdigest())
        with self.assertRaisesRegex(BacktestBlocked, "CSV line"):
            self.dataset()

    def test_rejected_ingestion_cannot_be_rehabilitated(self):
        self.metadata(schema_version=2, ingestion_eligible=False)
        with self.assertRaisesRegex(BacktestBlocked, "ingestion"):
            self.dataset()

    def test_changed_snapshot_between_loader_and_assessment_is_blocked(self):
        dataset = self.dataset()
        changed = replace(dataset.market, symbol="CHANGED-INR")
        with self.assertRaisesRegex(BacktestBlocked, "changed"):
            load_eligible(self.path, self.settings, allow_synthetic=True, loaded_market=changed)

    def test_eligibility_cannot_be_reused_for_a_different_market(self):
        dataset = self.dataset()
        changed = replace(dataset, market=replace(dataset.market, symbol="ALTERED-INR"))
        with patch("backtesting.experiment.simulate", side_effect=AssertionError):
            with self.assertRaisesRegex(BacktestBlocked, "differs"):
                run_experiment(changed, self.settings, self.strategy, split_plan())

    def test_no_passing_quality_flag_blocks_before_simulation(self):
        dataset = self.dataset()
        changed = replace(dataset, evidence={**dataset.evidence, "quality": {"eligible": False}})
        with patch("backtesting.experiment.simulate", side_effect=AssertionError):
            with self.assertRaisesRegex(BacktestBlocked, "eligibility"):
                run_experiment(changed, self.settings, self.strategy, split_plan())

    def test_three_periods_flat_start_full_liquidation_and_fixed_parameters(self):
        report = self.experiment()
        self.assertEqual(report["status"], "COMPLETE_SYNTHETIC_ONLY")
        self.assertEqual(report["strategy_parameters"], {"fast": 5, "slow": 20})
        for period in report["periods"]:
            self.assertEqual(period["sample_bars"], 200)
            self.assertEqual(period["simulation"]["bars"], 200)
            self.assertEqual(period["metrics"]["initial_equity_inr"], 2000)
            self.assertEqual(period["metrics"]["open_positions"], 0)
            self.assertEqual(period["simulation"]["equity_observations"][0]["equity"], 2000)
            for trade in period["simulation"]["trades"]:
                self.assertGreaterEqual(trade["opened_at"], period["start_inclusive"])
                self.assertLessEqual(trade["closed_at"], period["end_exclusive"])
                self.assertLessEqual(trade["leverage"], 3)
                self.assertLessEqual(trade["planned_stop_risk"], 20)

    def test_parameter_sensitivity_never_evaluates_test_or_changes_baseline(self):
        report = self.experiment(parameter_sensitivity=({"fast": 3, "slow": 10},))
        self.assertEqual(report["strategy_parameters"], {"fast": 5, "slow": 20})
        candidate = report["parameter_sensitivity"][0]
        self.assertEqual([period["name"] for period in candidate["periods"]], ["train", "validation"])
        self.assertFalse(candidate["test_evaluated"])
        self.assertEqual(report["parameter_selection"].split(";")[0], "none")

    def test_invalid_candidate_or_split_blocks_before_simulation(self):
        for candidates in (({"fast": 50, "slow": 20},), ({"fast": 5, "slow": 250},)):
            with self.subTest(candidates=candidates), patch("backtesting.experiment.simulate", side_effect=AssertionError):
                with self.assertRaises(ValueError):
                    self.experiment(parameter_sensitivity=candidates)

    def test_cost_stress_uses_explicit_higher_assumptions_without_selecting_parameters(self):
        report = self.experiment()
        for period in report["cost_stress"]["periods"]:
            assumptions = period["simulation"]["cost_assumptions"]
            self.assertEqual(assumptions["fee_rate"], self.settings.fee_rate * 2)
            self.assertEqual(assumptions["slippage_rate"], self.settings.slippage_rate * 2)
        self.assertFalse(report["cost_stress"]["assumptions"]["schedule_verified"])

    def test_invalid_stress_assumptions_block_before_simulation(self):
        for multiplier in (0, 1, "NaN", "Infinity", 100):
            with self.subTest(multiplier=multiplier), patch("backtesting.experiment.simulate", side_effect=AssertionError):
                with self.assertRaises(ValueError):
                    self.experiment(stress_multiplier=multiplier)

    def test_zero_cost_stress_is_disclosed_as_uninformative(self):
        settings = replace(self.settings, fee_rate=0, slippage_rate=0)
        report = run_experiment(self.dataset(), settings, self.strategy, split_plan())
        self.assertEqual(report["cost_stress"]["assumptions"]["fee_rate"], 0)
        self.assertTrue(any("Zero fee/slippage" in line for line in report["limitations"]))

    def test_both_baseline_strategies_can_run_without_parameter_selection(self):
        settings = replace(self.settings, strategy="momentum")
        report = run_experiment(self.dataset(), settings, create_strategy("momentum"), split_plan())
        self.assertEqual(report["strategy"], "momentum")
        self.assertEqual(report["parameter_sensitivity"], [])
        self.assertFalse(report["short_entries_enabled"])

    def test_experiment_context_does_not_depend_on_callers_decimal_context(self):
        from decimal import localcontext
        normal = self.experiment()
        with localcontext() as context:
            context.prec = 8
            other = self.experiment()
        self.assertEqual(normal, other)

    def test_interrupted_period_blocks_complete_report(self):
        from backtesting.engine import simulate
        dataset = self.dataset()
        replay = simulate(self.settings, dataset.market, self.strategy)
        with patch("backtesting.experiment.simulate", return_value=replace(replay, interrupted=True)):
            with self.assertRaisesRegex(BacktestBlocked, "interrupted"):
                self.experiment()

    def test_zero_trade_reports_keep_null_metrics_and_full_csv_headers(self):
        from tests.market_fixtures import csv_fixture, rows
        # Flat, structurally valid synthetic bars: neither baseline should cross.
        records = rows(800)
        csv_fixture(self.path, records)
        self.metadata(schema_version=2, ingestion_eligible=True,
                      data_policy={"min_history_bars": 200, "require_verified_liquidity": False})
        report = self.experiment()
        self.assertTrue(all(period["metrics"]["total_trades"] == 0 for period in report["periods"]))
        output = self.root / "zero"
        write_report(output, report)
        decoded = json.loads((output / "results.json").read_text())
        self.assertIsNone(decoded["periods"][0]["metrics"]["win_rate_percent"])
        with (output / "trades.csv").open(newline="", encoding="utf-8") as stream:
            reader = csv.DictReader(stream)
            self.assertIn("entry_price", reader.fieldnames)
            self.assertEqual(list(reader), [])

    def test_identical_experiment_and_report_bytes_are_reproducible(self):
        one, two = self.experiment(), self.experiment()
        self.assertEqual(one, two)
        first, second = self.root / "one", self.root / "two"
        write_report(first, one)
        write_report(second, two)
        for path in first.iterdir():
            self.assertEqual(path.read_bytes(), (second / path.name).read_bytes())

    def test_reports_label_synthetic_json_csv_and_markdown(self):
        report = self.experiment()
        output = self.root / "exports"
        write_report(output, report)
        decoded = json.loads((output / "results.json").read_text(encoding="utf-8"))
        self.assertEqual(decoded["data"]["kind"], "synthetic")
        self.assertIn("NOT REAL-MARKET PERFORMANCE", (output / "report.md").read_text(encoding="utf-8"))
        with (output / "metrics.csv").open(newline="", encoding="utf-8") as stream:
            metrics = list(csv.DictReader(stream))
        self.assertEqual(len(metrics), 6)
        self.assertTrue(all(row["data_kind"] == "synthetic" for row in metrics))
        self.assertEqual({row["period"] for row in metrics}, {"train", "validation", "test"})

    def test_report_writer_refuses_existing_path_and_preserves_files(self):
        output = self.root / "existing"
        output.mkdir()
        sentinel = output / "keep.txt"
        sentinel.write_text("preserve", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            write_report(output, self.experiment())
        self.assertEqual(sentinel.read_text(), "preserve")

    def test_incomplete_report_is_cleaned_after_export_failure(self):
        output = self.root / "incomplete"
        with patch("backtesting.reporting.markdown_report", side_effect=ValueError("synthetic failure")):
            with self.assertRaises(ValueError):
                write_report(output, self.experiment())
        self.assertFalse(output.exists())

    def test_evaluate_cli_needs_no_network_or_credentials_and_submits_no_orders(self):
        with patch("socket.socket", side_effect=AssertionError("network forbidden")), \
             patch("socket.create_connection", side_effect=AssertionError("network forbidden")):
            status, output, errors = self.invoke("evaluate", "--fee-rate", "0.002", "--slippage-rate", "0.003")
        self.assertEqual(status, 0, errors)
        result = json.loads(output)
        self.assertEqual(result["orders_submitted"], 0)
        self.assertFalse(result["live_trading_enabled"])
        self.assertTrue((self.root / "report" / "results.json").exists())

    def test_evaluate_cli_insufficient_data_returns_blocked_and_no_reports(self):
        generate(self.root / "tiny.csv", 200)
        status, output, errors = self.invoke("evaluate", "--data", str(self.root / "tiny.csv"))
        self.assertEqual(status, 2)
        self.assertEqual(json.loads(output)["status"], "BLOCKED")
        self.assertIn("insufficient evidence", errors)
        self.assertFalse((self.root / "report").exists())

    def test_evaluate_cli_rejects_live_and_excess_leverage(self):
        status, output, _ = self.invoke("evaluate", "--leverage", "4")
        self.assertEqual(status, 2)
        self.assertEqual(json.loads(output)["status"], "BLOCKED")
        with self.assertRaises(ValueError):
            Settings(mode="live")

    def test_evaluation_does_not_silently_accept_changed_initial_capital(self):
        with self.assertRaisesRegex(ValueError, "INR 2000"):
            run_experiment(self.dataset(), replace(self.settings, starting_capital=3000), self.strategy, split_plan())
