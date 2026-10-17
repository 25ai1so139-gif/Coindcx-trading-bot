"""SYNTHETIC interval regressions; no real candles, fills or liquidity evidence."""

import copy
import tempfile
import unittest
from datetime import timedelta, timezone
from decimal import localcontext
from pathlib import Path
from unittest.mock import patch

from backtesting.datasets import BacktestBlocked, load_eligible
from config import Settings
from data.coindcx import PublicClient
from data.diagnostics import interval_volume_check
from data.intervals import interval_candle_check
from data.models import Candle
from data.quality import DataPolicy, assess
from data.schema import epoch_ms, normalize
from data.storage import read_csv, write_dataset
from strategies import create_strategy
from strategies.verification import verify_file
from tests.market_fixtures import START, SYMBOL, end, metadata, rows
from tests.test_public_market_data import ACTIVE, DETAILS, api_row, reply


class IntervalTraceTests(unittest.TestCase):
    def sample(self):
        bar = {**api_row(0), "volume": "15"}
        minutes = [{**bar, "time": bar["time"] + index * 60000, "volume": "1"} for index in range(15)]
        return bar, minutes

    def check(self, bar, minutes, **overrides):
        args = {"pair": SYMBOL, "minute_pair": SYMBOL, "as_of": START + timedelta(minutes=15), **overrides}
        return interval_candle_check(bar, minutes, **args)

    def test_exact_closed_boundary_matches_ohlcv_without_mutating_source(self):
        bar, minutes = self.sample()
        before = copy.deepcopy((bar, minutes))
        result = self.check(bar, minutes)
        self.assertEqual(result["status"], "MATCH")
        self.assertEqual(result["mismatched_fields"], [])
        self.assertEqual(result["source_open_utc"], START.isoformat())
        self.assertEqual(result["source_close_utc"], (START + timedelta(minutes=15)).isoformat())
        self.assertFalse(result["liquidity_verified"])
        self.assertFalse(result["source_activity_verified"])
        self.assertEqual(before, (bar, minutes))

    def test_utc_and_ist_clocks_select_exactly_the_same_interval(self):
        bar, minutes = self.sample()
        utc_end = START + timedelta(minutes=15)
        ist_end = utc_end.astimezone(timezone(timedelta(hours=5, minutes=30)))
        self.assertEqual(self.check(bar, minutes, as_of=utc_end), self.check(bar, minutes, as_of=ist_end))

    def test_seconds_microseconds_fractional_and_overflow_times_are_not_guessed(self):
        bar, minutes = self.sample()
        for time in (bar["time"] // 1000, bar["time"] * 1000, str(bar["time"]) + ".5", "1e1000"):
            with self.subTest(time=time):
                self.assertEqual(self.check({**bar, "time": time}, minutes)["status"], "UNVERIFIED")

    def test_next_interval_boundary_and_prior_context_are_excluded(self):
        bar, minutes = self.sample()
        context = [{**minutes[0], "time": bar["time"] - 60000, "volume": "200"},
                   *minutes, {**minutes[-1], "time": bar["time"] + 900000, "volume": "300"}]
        self.assertEqual(self.check(bar, context), self.check(bar, minutes))

    def test_next_interval_cannot_replace_the_missing_last_minute(self):
        bar, minutes = self.sample()
        wrong = [*minutes[:-1], {**minutes[-1], "time": bar["time"] + 900000}]
        result = self.check(bar, wrong)
        self.assertEqual(result["status"], "UNVERIFIED")
        self.assertEqual(result["code"], "MISSING_MINUTE_INTERVALS")

    def test_duplicate_cannot_be_hidden_by_sorting_or_matching_volume(self):
        bar, minutes = self.sample()
        for sequence in ([*minutes, minutes[0]], [*minutes[:-1], minutes[0]]):
            with self.subTest(length=len(sequence)):
                self.assertEqual(self.check(bar, sequence)["code"], "DUPLICATE_MINUTE_TIMESTAMP")

    def test_missing_and_misaligned_minutes_cannot_claim_a_match(self):
        bar, minutes = self.sample()
        for sequence in (minutes[:-1], [{**minutes[0], "time": bar["time"] + 1}, *minutes[1:]]):
            self.assertEqual(self.check(bar, sequence)["status"], "UNVERIFIED")

    def test_incomplete_and_future_intervals_fail_both_diagnostics(self):
        bar, minutes = self.sample()
        for cutoff in (START - timedelta(minutes=1), START + timedelta(minutes=15, microseconds=-1)):
            with self.subTest(cutoff=cutoff):
                for result in (self.check(bar, minutes, as_of=cutoff), interval_volume_check(bar, minutes, as_of=cutoff)):
                    self.assertEqual(result["status"], "UNVERIFIED")
                    self.assertEqual(result["code"], "INCOMPLETE_OR_FUTURE_INTERVAL")

    def test_naive_or_missing_evaluation_clock_cannot_establish_completion(self):
        bar, minutes = self.sample()
        for clock in (None, START.replace(tzinfo=None)):
            self.assertEqual(self.check(bar, minutes, as_of=clock)["status"], "UNVERIFIED")

    def test_raw_descending_and_normalized_ascending_compare_but_scrambled_order_rejects(self):
        bar, minutes = self.sample()
        self.assertEqual(self.check(bar, minutes), self.check(bar, list(reversed(minutes))))
        minutes[1], minutes[2] = minutes[2], minutes[1]
        self.assertEqual(self.check(bar, minutes)["code"], "OUT_OF_ORDER_MINUTES")

    def test_explicit_flat_zero_is_retained_without_verifying_activity_or_liquidity(self):
        bar, minutes = self.sample()
        for record in [bar, *minutes]:
            record.update(open="100", high="100", low="100", close="100", volume="0")
        result = self.check(bar, minutes)
        self.assertEqual(result["status"], "MATCH")
        self.assertEqual(result["minute_derived_values"]["volume"], "0")
        self.assertFalse(result["source_activity_verified"])
        self.assertFalse(result["liquidity_verified"])

    def test_missing_malformed_negative_and_nonfinite_volumes_are_not_zero(self):
        bar, minutes = self.sample()
        for value in (None, "", "bad", "NaN", "Infinity", "-1", True, "1e1000"):
            with self.subTest(value=value):
                sequence = [{**minutes[0], "volume": value}, *minutes[1:]]
                self.assertEqual(self.check(bar, sequence)["status"], "UNVERIFIED")
        del minutes[0]["volume"]
        self.assertEqual(self.check(bar, minutes)["status"], "UNVERIFIED")

    def test_impossible_or_missing_ohlc_cannot_get_volume_only_assurance(self):
        bar, minutes = self.sample()
        for fields in ({"low": "1000"}, {"open": "NaN"}, {"close": "0"}):
            self.assertEqual(self.check(bar, [{**minutes[0], **fields}, *minutes[1:]])["status"], "UNVERIFIED")
        del minutes[0]["high"]
        self.assertEqual(self.check(bar, minutes)["status"], "UNVERIFIED")

    def test_volume_only_discrepancy_is_exact_and_ohlc_remains_unchanged(self):
        bar, minutes = self.sample()
        bar["volume"] = "0.086267"
        for minute in minutes:
            minute["volume"] = "0"
        minutes[0]["volume"] = "0.085028"  # Synthetic shape, not actual market minutes.
        result = self.check(bar, minutes)
        self.assertEqual(result["code"], "CROSS_INTERVAL_VOLUME_MISMATCH")
        self.assertEqual(result["mismatched_fields"], ["volume"])
        self.assertEqual(result["source_values"]["volume"], "0.086267")
        self.assertEqual(result["minute_derived_values"]["volume"], "0.085028")
        with localcontext() as context:
            context.prec = 2
            self.assertEqual(self.check(bar, minutes), result)

    def test_ohlc_discrepancy_has_a_quarantine_code_even_when_volume_matches(self):
        bar, minutes = self.sample()
        minutes[-1]["close"] = "100"
        result = self.check(bar, minutes)
        self.assertEqual(result["status"], "MISMATCH")
        self.assertEqual(result["code"], "CROSS_INTERVAL_CANDLE_MISMATCH")
        self.assertEqual(result["mismatched_fields"], ["close"])

    def test_wrong_or_missing_source_pair_is_not_a_cross_market_match(self):
        bar, minutes = self.sample()
        for pair in ("I-OTHER_INR", "", None):
            self.assertEqual(self.check(bar, minutes, minute_pair=pair)["code"], "INTERVAL_SYMBOL_MISMATCH")

    def test_ohlc_quarantine_survives_export_and_blocks_strategy_and_order_paths(self):
        settings = Settings(min_history_bars=200)
        policy = DataPolicy(min_history_bars=200, min_quote_volume_per_bar="100")
        meta = {**metadata(), "ingestion_warnings": ["CROSS_INTERVAL_CANDLE_MISMATCH"]}
        assessment = assess(rows(), meta, policy, end())
        self.assertFalse(assessment.report["eligible"])
        self.assertIn("SOURCE_INTERVAL_MISMATCH", assessment.report["reasons"])
        strategy = create_strategy("sma_cross")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "synthetic-quarantine.csv"
            write_dataset(path, assessment, meta, b'SYNTHETIC interval quarantine fixture')
            imported = read_csv(path)
            again = assess(imported.rows, imported.metadata, policy, end()).report
            self.assertIn("SOURCE_INGESTION_REJECTED", again["reasons"])
            self.assertIn("SOURCE_INTERVAL_MISMATCH", again["reasons"])
            with patch.object(type(strategy), "evaluate", side_effect=AssertionError("strategy must not run")), \
                 patch("paper_trading.broker.PaperBroker", side_effect=AssertionError("orders forbidden")), \
                 patch("socket.socket", side_effect=AssertionError("network forbidden")):
                with self.assertRaises(BacktestBlocked):
                    load_eligible(path, settings, allow_synthetic=True, as_of=end())
                review = verify_file(path, settings, strategy, as_of=end(), allow_synthetic=True)
                self.assertEqual(review["signal"], "NO_TRADE")
                self.assertEqual(review["orders_submitted"], 0)

    def test_production_history_preserves_direct_fifteen_minute_values_without_resampling(self):
        source = [api_row(index) for index in reversed(range(200))]
        source[0]["volume"] = "0.086267"  # Deliberate synthetic marker.
        queue = [reply(ACTIVE), reply(DETAILS), reply(source)]
        requested = []
        def transport(url, timeout):
            requested.append(url)
            return queue.pop(0)
        history = PublicClient(transport=transport, request_interval=0).history(SYMBOL, START, end())
        record = normalize(history.rows[-1], SYMBOL)
        candle = Candle(record.timestamp, record.open, record.high, record.low, record.close, record.volume)
        self.assertEqual(str(candle.volume), "0.086267")
        self.assertEqual(epoch_ms(candle.timestamp), source[0]["time"])
        self.assertEqual(candle.closed_at, end())
        self.assertEqual([url for url in requested if "/candles?" in url][0].count("interval=15m"), 1)
        self.assertFalse(any("interval=1m&" in url for url in requested))
