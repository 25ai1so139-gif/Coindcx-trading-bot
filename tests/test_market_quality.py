import copy
import unittest
from datetime import timedelta
from decimal import Decimal

from data.quality import DataPolicy, assess
from data.schema import epoch_ms, milliseconds, normalize
from tests.market_fixtures import START, SYMBOL, end, metadata, rows


class NormalizationTests(unittest.TestCase):
    def test_valid_record_and_decimal_precision(self):
        record = normalize(rows(1)[0], SYMBOL)
        self.assertEqual(record.timestamp, START)
        self.assertEqual(record.open, Decimal("100"))
        self.assertEqual(record.row()["timeframe"], "15m")
        self.assertEqual(record.row()["symbol"], SYMBOL)

    def test_timezone_and_official_millisecond_conversion(self):
        row = rows(1)[0]
        row["timestamp"] = "2024-01-01T05:30:00+05:30"
        self.assertEqual(normalize(row, SYMBOL).timestamp, START)
        self.assertEqual(milliseconds(1704067200000), START)
        self.assertEqual(epoch_ms(START), 1704067200000)
        with self.assertRaises(ValueError):
            milliseconds("1704067200000.5")

    def test_timestamps_must_fit_utc_and_the_complete_candle_interval(self):
        for stamp in ('9999-12-31T23:59:59-01:00', '0001-01-01T00:00:00+01:00',
                      '9999-12-31T23:45:00Z'):
            with self.subTest(stamp=stamp), self.assertRaises(ValueError):
                normalize({**rows(1)[0], 'timestamp': stamp}, SYMBOL)

    def test_required_fields_and_invalid_numbers(self):
        for field in ("timestamp", "open", "high", "low", "close", "volume"):
            row = rows(1)[0]
            del row[field]
            with self.subTest(field=field), self.assertRaises(ValueError):
                normalize(row, SYMBOL)
        for value in ("NaN", "Infinity", "-1", "invalid"):
            row = rows(1)[0]
            row["volume"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize(row, SYMBOL)

    def test_negative_price_and_impossible_ohlc(self):
        for field, value in (("open", "-1"), ("low", "103"), ("high", "98"), ("close", "0")):
            row = rows(1)[0]
            row[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                normalize(row, SYMBOL)

    def test_zero_volume_is_preserved_for_analysis(self):
        row = rows(1)[0]
        row.update(volume="0", quote_volume="0")
        result = normalize(row, SYMBOL)
        self.assertEqual(result.volume, 0)
        self.assertEqual(result.quote_volume, 0)

    def test_extra_csv_columns_are_not_silently_ignored(self):
        with self.assertRaisesRegex(ValueError, 'column count'):
            normalize({**rows(1)[0], None: ['unexpected extra value']}, SYMBOL)

    def test_alignment_naive_timestamps_and_mixed_markets_fail(self):
        for change in ({"timestamp": "2024-01-01T00:01:00Z"},
                       {"timestamp": "2024-01-01T00:00:00"}, {"symbol": "OTHER"}, {"timeframe": "1m"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                normalize({**rows(1)[0], **change}, SYMBOL)


class EligibilityTests(unittest.TestCase):
    def setUp(self):
        self.policy = DataPolicy(min_history_bars=200, min_quote_volume_per_bar="100")

    def test_eligible_synthetic_fixture_is_explicitly_labelled(self):
        result = assess(rows(), metadata(), self.policy, end())
        self.assertTrue(result.report["eligible"])
        self.assertIn("SYNTHETIC_DATA_NOT_MARKET_EVIDENCE", result.report["warnings"])
        self.assertEqual(result.report["liquidity"], "MEETS_CONFIGURED_THRESHOLD")

    def test_duplicates_are_not_silently_removed(self):
        records = rows()
        records[2] = records[1].copy()
        result = assess(records, metadata(), self.policy, end())
        self.assertIn("DUPLICATE_TIMESTAMPS", result.report["reasons"])
        self.assertEqual(result.report["duplicate_timestamps"], 1)
        self.assertEqual(len(result.completed), 200)

    def test_out_of_order_records_are_reported_and_not_reordered(self):
        records = list(reversed(rows()))
        result = assess(records, metadata(), self.policy, end())
        self.assertIn("OUT_OF_ORDER", result.report["reasons"])
        self.assertEqual(result.completed[0].timestamp.isoformat(), records[0]["timestamp"])

    def test_missing_intervals_are_counted_not_filled(self):
        records = rows()
        records.pop(50)
        result = assess(records, metadata(), self.policy, end())
        self.assertEqual(result.report["missing_bars"], 1)
        self.assertEqual(len(result.completed), 199)
        self.assertIn("INCOMPLETE_HISTORY", result.report["reasons"])

    def test_requested_range_detects_missing_leading_history(self):
        meta = {**metadata(), "requested_start": (START - timedelta(minutes=15)).isoformat(),
                "requested_end": end().isoformat()}
        result = assess(rows(), meta, self.policy, end())
        self.assertEqual(result.report["expected_bars"], 201)
        self.assertEqual(result.report["missing_bars"], 1)

    def test_invalid_ohlc_exclusion_is_visible_and_original_is_preserved(self):
        records = rows()
        records[50]["high"] = "1"
        original = copy.deepcopy(records)
        result = assess(records, metadata(), self.policy, end())
        self.assertEqual(records, original)
        self.assertEqual(result.report["invalid_rows"], 1)
        self.assertEqual(result.report["excluded_rows"][0]["code"], "INVALID_RECORD")
        self.assertFalse(result.report["eligible"])

    def test_current_candle_is_excluded_without_lookahead(self):
        result = assess(rows(201), metadata(), self.policy, end() + timedelta(minutes=5))
        self.assertEqual(len(result.completed), 200)
        self.assertTrue(all(record.closed_at <= end() + timedelta(minutes=5) for record in result.completed))
        self.assertIn("INCOMPLETE_CANDLES_EXCLUDED", result.report["warnings"])
        self.assertTrue(result.report["eligible"])

    def test_future_candle_cannot_be_a_signal_record(self):
        result = assess(rows(202), metadata(), self.policy, end())
        self.assertIn("FUTURE_DATA", result.report["reasons"])
        self.assertEqual(len(result.completed), 200)

    def test_new_coin_gets_insufficient_history_without_age_blacklist(self):
        records = [{**row, "symbol": "I-NEW_MEME_INR"} for row in rows()]
        meta = {**metadata(), "symbol": "I-NEW_MEME_INR"}
        result = assess(records, meta, DataPolicy(), end())
        self.assertEqual(result.report["status"], "INSUFFICIENT_HISTORY")

    def test_zero_volume_and_illiquidity_are_distinct(self):
        records = rows()
        records[10]["volume"] = "0"
        result = assess(records, metadata(), self.policy, end())
        self.assertIn("ZERO_VOLUME", result.report["reasons"])
        records = rows()
        records[10]["quote_volume"] = "1"
        result = assess(records, metadata(), self.policy, end())
        self.assertIn("ILLIQUID", result.report["reasons"])

    def test_base_volume_is_never_claimed_as_verified_quote_liquidity(self):
        meta = {**metadata(), "quote_volume_verified": False}
        result = assess(rows(), meta, self.policy, end())
        self.assertEqual(result.report["liquidity"], "NOT_ASSESSED")
        self.assertIn("LIQUIDITY_REVIEW_REQUIRED", result.report["reasons"])

    def test_no_invented_default_liquidity_threshold(self):
        result = assess(rows(), metadata(), DataPolicy(min_history_bars=200), end())
        self.assertIsNone(result.report["policy"]["min_quote_volume_per_bar"])
        self.assertFalse(result.report["eligible"])

    def test_explicit_research_override_retains_liquidity_warning(self):
        policy = DataPolicy(min_history_bars=200, require_verified_liquidity=False)
        result = assess(rows(), metadata(), policy, end())
        self.assertTrue(result.report["eligible"])
        self.assertIn("QUOTE_LIQUIDITY_NOT_VERIFIED", result.report["warnings"])

    def test_staleness_uses_explicit_utc_reference(self):
        result = assess(rows(), metadata(), self.policy, end() + timedelta(minutes=31))
        self.assertIn("STALE_DATA", result.report["reasons"])
        self.assertTrue(assess(rows(), metadata(), self.policy, end()).report["eligible"])

    def test_unknown_inactive_and_wrong_currency_fail_closed(self):
        for change, reason in (({"market_status": "inactive"}, "MARKET_NOT_CONFIRMED_ACTIVE"),
                               ({"symbol": "bad/symbol"}, "INVALID_SYMBOL"),
                               ({"quote_currency": "USDT"}, "UNSUPPORTED_ACCOUNT_CURRENCY"),
                               ({"source_order_valid": False}, "OUT_OF_ORDER")):
            with self.subTest(change=change):
                result = assess(rows(), {**metadata(), **change}, self.policy, end())
                self.assertIn(reason, result.report["reasons"])
                self.assertFalse(result.report["eligible"])

    def test_policy_validation(self):
        for change in ({"min_history_bars": 199}, {"min_completeness": "1.1"},
                       {"max_staleness_minutes": -1}, {"min_quote_volume_per_bar": 0},
                       {"min_quote_volume_per_bar": "NaN"}, {"max_zero_volume_fraction": 1},
                       {"require_verified_liquidity": "false"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                DataPolicy(**change)

    def test_repeated_assessment_is_identical(self):
        self.assertEqual(assess(rows(), metadata(), self.policy, end()),
                         assess(rows(), metadata(), self.policy, end()))

    def test_malformed_metadata_attestations_fail_clearly(self):
        for change in ({"ingestion_warnings": None}, {"ingestion_warnings": "not an array"},
                       {"quote_volume_verified": "true"}, {"source_order_valid": "false"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                assess(rows(), {**metadata(), **change}, self.policy, end())
