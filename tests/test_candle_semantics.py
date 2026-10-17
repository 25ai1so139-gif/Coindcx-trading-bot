"""Deterministic SYNTHETIC reproductions of observed source-zero semantics."""

import copy
import unittest
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

from data.coindcx import PublicClient, PublicDataError
from data.diagnostics import invalid_volume_reason, interval_volume_check
from data.models import Candle
from data.quality import DataPolicy, assess
from data.schema import epoch_ms, milliseconds, normalize
from tests.market_fixtures import START, SYMBOL, end, metadata, rows
from tests.test_public_market_data import ACTIVE, DETAILS, api_row, reply


class VolumeSemanticsTests(unittest.TestCase):
    def setUp(self):
        self.policy = DataPolicy(min_history_bars=200, min_quote_volume_per_bar="100")

    def flat(self):
        values = rows()
        values[10].update(open="101", high="101", low="101", close="101", volume="0", quote_volume="0")
        return values

    def test_flat_zero_is_structurally_valid_and_preserved_but_trading_screen_rejects(self):
        values = self.flat()
        original = copy.deepcopy(values)
        report = assess(values, metadata(), self.policy, end())
        self.assertEqual(values, original)
        self.assertEqual(len(report.completed), 200)
        self.assertEqual(report.completed[10].volume, 0)
        self.assertEqual(report.report["invalid_rows"], 0)
        self.assertIn("ZERO_VOLUME", report.report["reasons"])
        diagnostic = report.report["volume_diagnostics"][0]
        self.assertEqual(diagnostic["code"], "ZERO_VOLUME_FLAT")
        self.assertTrue(diagnostic["structurally_valid"])
        self.assertEqual(diagnostic["source_activity"], "UNVERIFIED")
        self.assertEqual(diagnostic["disposition"], "QUARANTINED_FOR_TRADING")

    def test_nonflat_zero_does_not_get_mislabeled_as_a_verified_no_trade_interval(self):
        values = rows()
        values[10]["volume"] = "0"
        report = assess(values, metadata(), self.policy, end()).report
        self.assertEqual(report["volume_diagnostics"][0]["code"], "ZERO_VOLUME_PRICE_RANGE")
        self.assertEqual(report["volume_diagnostics"][0]["source_activity"], "UNVERIFIED")
        self.assertFalse(report["eligible"])

    def test_numeric_string_decimal_and_negative_zero_are_not_missing_volume(self):
        for value in (0, 0.0, "0", "0.0000", Decimal(0), "-0"):
            with self.subTest(value=value):
                record = normalize({**self.flat()[10], "volume": value}, SYMBOL)
                self.assertEqual(record.volume, 0)
                self.assertIsNone(invalid_volume_reason({"volume": value}))

    def test_missing_null_and_blank_volume_are_distinct_from_explicit_zero(self):
        for fields in ({}, {"volume": None}, {"volume": ""}):
            with self.subTest(fields=fields):
                values = rows()
                del values[10]["volume"]
                values[10].update(fields)
                report = assess(values, metadata(), self.policy, end()).report
                self.assertEqual(report["invalid_rows"], 1)
                self.assertEqual(report["zero_volume_bars"], 0)
                self.assertEqual(report["volume_diagnostics"][0]["code"], "VOLUME_MISSING")

    def test_malformed_nonfinite_and_negative_volume_have_specific_rejections(self):
        for value, code in (("bad", "VOLUME_MALFORMED"), (True, "VOLUME_MALFORMED"),
                            ({}, "VOLUME_MALFORMED"), ("NaN", "VOLUME_NONFINITE"),
                            ("Infinity", "VOLUME_NONFINITE"), ("-1", "VOLUME_NEGATIVE")):
            with self.subTest(value=value):
                values = rows()
                values[10]["volume"] = value
                report = assess(values, metadata(), self.policy, end()).report
                self.assertFalse(report["eligible"])
                self.assertEqual(report["zero_volume_bars"], 0)
                self.assertEqual(report["volume_diagnostics"][0]["code"], code)
                self.assertFalse(report["volume_diagnostics"][0]["structurally_valid"])

    def test_incomplete_zero_is_excluded_not_used_as_a_completed_no_trade_bar(self):
        values = rows(201)
        values[-1].update(volume="0", quote_volume="0", open="101", high="101", low="101", close="101")
        assessment = assess(values, metadata(), self.policy, end() + timedelta(minutes=5))
        self.assertEqual(len(assessment.completed), 200)
        self.assertEqual(assessment.report["zero_volume_bars"], 0)
        self.assertIn("INCOMPLETE_CANDLES_EXCLUDED", assessment.report["warnings"])

    def test_future_zero_cannot_disappear_as_a_completed_zero(self):
        values = rows(202)
        values[-1]["volume"] = "0"
        assessment = assess(values, metadata(), self.policy, end())
        self.assertIn("FUTURE_DATA", assessment.report["reasons"])
        self.assertFalse(assessment.report["eligible"])
        self.assertEqual(assessment.report["zero_volume_bars"], 0)

    def test_explicit_research_retention_does_not_make_a_zero_execution_candle(self):
        policy = replace(self.policy, max_zero_volume_fraction=Decimal(".01"), require_verified_liquidity=False,
                         min_quote_volume_per_bar=None)
        assessment = assess(self.flat(), metadata(), policy, end())
        self.assertTrue(assessment.report["eligible"])  # Existing research opt-in only.
        self.assertEqual(assessment.report["eligibility_scope"], "DATA_POLICY_SCREEN_NOT_ENTRY_APPROVAL")
        record = assessment.completed[10]
        with self.assertRaises(ValueError):
            Candle(record.timestamp, record.open, record.high, record.low, record.close, record.volume)

    def test_deleting_zero_instead_of_preserving_it_creates_an_explicit_missing_interval(self):
        values = self.flat()
        del values[10]
        meta = {**metadata(), "requested_start": START.isoformat(), "requested_end": end().isoformat()}
        report = assess(values, meta, self.policy, end()).report
        self.assertEqual(report["missing_bars"], 1)
        self.assertIn("INCOMPLETE_HISTORY", report["reasons"])

    def test_invalid_ohlc_does_not_become_valid_because_volume_is_zero(self):
        values = self.flat()
        values[10]["low"] = "200"
        report = assess(values, metadata(), self.policy, end()).report
        self.assertEqual(report["invalid_rows"], 1)
        self.assertIn("INVALID_DATA", report["reasons"])

    def test_missing_prices_are_not_forward_filled_from_adjacent_candles(self):
        values = self.flat()
        del values[10]["close"]
        assessment = assess(values, metadata(), self.policy, end())
        self.assertNotIn("close", values[10])
        self.assertEqual(len(assessment.completed), 199)
        self.assertIn("INVALID_DATA", assessment.report["reasons"])

    def test_milliseconds_and_ist_offset_normalize_to_same_utc_open(self):
        record = normalize({**self.flat()[0], "timestamp": "2024-01-01T05:30:00+05:30"}, SYMBOL)
        self.assertEqual(record.timestamp, milliseconds(1704067200000))
        self.assertEqual(record.timestamp, START)
        self.assertEqual(epoch_ms(record.timestamp), 1704067200000)

    def test_seconds_are_not_silently_guessed_as_milliseconds(self):
        with self.assertRaises(ValueError):
            normalize({**self.flat()[0], "timestamp": milliseconds(1704067200)}, SYMBOL)


class ApiVolumeBoundaryTests(unittest.TestCase):
    def history(self, pages):
        queue = [reply(ACTIVE), reply(DETAILS), *pages]
        return PublicClient(transport=lambda *_: queue.pop(0), request_interval=0).history(SYMBOL, START, end(4), limit=2)

    def test_raw_zero_is_preserved_through_historical_pagination_and_utc_normalization(self):
        zero = {**api_row(2), "open": "101", "high": "101", "low": "101", "close": "101", "volume": 0}
        history = self.history([reply([api_row(3), zero]), reply([api_row(1), api_row(0)])])
        self.assertEqual(history.rows[2]["volume"], 0)
        self.assertEqual(normalize(history.rows[2], SYMBOL).volume, 0)
        self.assertEqual(PublicClient._decode(history.raw_pages[0])[1], zero)

    def test_missing_api_volume_is_an_api_error_not_zero_or_an_empty_history(self):
        item = api_row(0)
        del item["volume"]
        with self.assertRaises(PublicDataError) as caught:
            self.history([reply([item])])
        self.assertEqual(caught.exception.code, "INVALID_API_RESPONSE")

    def test_null_api_volume_survives_to_invalid_record_quarantine_without_zero_substitution(self):
        history = self.history([reply([{**api_row(0), "volume": None}])])
        self.assertIsNone(history.rows[0]["volume"])
        assessment = assess(history.rows, metadata(), DataPolicy(min_history_bars=200), end(4))
        self.assertEqual(assessment.report["zero_volume_bars"], 0)
        self.assertEqual(assessment.report["volume_diagnostics"][0]["code"], "VOLUME_MISSING")

    def test_duplicated_zero_timestamp_is_not_deduplicated_or_removed(self):
        zero = {**api_row(0), "volume": 0}
        history = self.history([reply([api_row(1), zero, zero])])
        report = assess(history.rows, metadata(), DataPolicy(min_history_bars=200), end(4)).report
        self.assertEqual(report["duplicate_timestamps"], 1)
        self.assertIn("DUPLICATE_TIMESTAMPS", report["reasons"])
        self.assertEqual(report["zero_volume_bars"], 2)


class IntervalConsistencyTests(unittest.TestCase):
    def sample(self):
        bar = {**api_row(0), "volume": 0}
        minutes = [{**bar, "time": bar["time"] + i * 60000} for i in range(15)]
        return bar, minutes

    def test_zero_interval_match_retains_zero_and_is_not_trade_evidence(self):
        bar, minutes = self.sample()
        original = copy.deepcopy((bar, minutes))
        result = interval_volume_check(bar, minutes)
        self.assertEqual(result["status"], "MATCH")
        self.assertEqual(result["minute_sum"], "0")
        self.assertEqual(original, (bar, minutes))

    def test_positive_source_mismatch_is_not_rounded_or_repaired(self):
        bar, minutes = self.sample()
        bar["volume"] = "0.086267"
        minutes[0]["volume"] = "0.085028"  # Synthetic reproduction of observed difference.
        original = copy.deepcopy((bar, minutes))
        result = interval_volume_check(bar, minutes)
        self.assertEqual(result["status"], "MISMATCH")
        self.assertEqual(result["code"], "CROSS_INTERVAL_VOLUME_MISMATCH")
        self.assertEqual(original, (bar, minutes))

    def test_missing_duplicate_misaligned_or_malformed_minutes_cannot_claim_match(self):
        bar, minutes = self.sample()
        for values in (minutes[:-1], minutes + [minutes[0]],
                       [{**minutes[0], "time": minutes[0]["time"] + 1}, *minutes[1:]],
                       [{**minutes[0], "volume": None}, *minutes[1:]],
                       [{**minutes[0], "volume": "1e1000"}, *minutes[1:]]):
            with self.subTest(rows=len(values)):
                self.assertEqual(interval_volume_check(bar, values)["status"], "UNVERIFIED")

    def test_known_source_interval_mismatch_blocks_otherwise_eligible_history(self):
        meta = {**metadata(), "ingestion_warnings": ["CROSS_INTERVAL_VOLUME_MISMATCH"]}
        policy = DataPolicy(min_history_bars=200, min_quote_volume_per_bar="100")
        self.assertTrue(assess(rows(), metadata(), policy, end()).report["eligible"])
        report = assess(rows(), meta, policy, end()).report
        self.assertFalse(report["eligible"])
        self.assertIn("SOURCE_INTERVAL_MISMATCH", report["reasons"])
