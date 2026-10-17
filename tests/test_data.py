import csv
import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from data.loader import load_csv
from tools.generate_sample_data import generate


class HistoricalDataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "market.csv"
        generate(self.path, 200)
        self.metadata = self.path.with_suffix(".json")

    def update_metadata(self, **changes):
        values = json.loads(self.metadata.read_text())
        values.update(changes)
        self.metadata.write_text(json.dumps(values), encoding="utf-8")

    def rewrite_rows(self, change):
        with self.path.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        change(rows)
        with self.path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        self.update_metadata(sha256=hashlib.sha256(self.path.read_bytes()).hexdigest())

    def load(self, **kwargs):
        return load_csv(self.path, min_history_bars=200, **kwargs)

    def test_synthetic_data_requires_explicit_opt_in(self):
        with self.assertRaisesRegex(ValueError, "synthetic"):
            self.load()
        market = self.load(allow_synthetic=True)
        self.assertEqual(market.kind, "synthetic")
        self.assertEqual(len(market.candles), 200)

    def test_established_and_meme_symbols_use_same_history_gate(self):
        for symbol in ("BTC-INR", "NEW-MEME-INR"):
            self.update_metadata(symbol=symbol, kind="historical", quality_reviewed=True,
                                 source="https://public.coindcx.com/reviewed-source")
            self.assertEqual(self.load().symbol, symbol)
        with self.assertRaisesRegex(ValueError, "insufficient history"):
            load_csv(self.path, min_history_bars=2880)

    def test_historical_data_needs_quality_review_and_provenance(self):
        self.update_metadata(kind="historical", source="https://public.coindcx.com/source")
        with self.assertRaisesRegex(ValueError, "quality review"):
            self.load()
        self.update_metadata(quality_reviewed=True, source="http://example.com/data")
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            self.load()

    def test_checksum_mismatch_is_rejected(self):
        self.path.write_bytes(self.path.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            self.load(allow_synthetic=True)

    def test_usdt_is_not_silently_treated_as_rupees(self):
        self.update_metadata(quote_currency="USDT")
        with self.assertRaisesRegex(ValueError, "INR"):
            self.load(allow_synthetic=True)

    def test_missing_metadata_is_rejected(self):
        self.metadata.unlink()
        with self.assertRaises(FileNotFoundError):
            self.load(allow_synthetic=True)

    def test_missing_bars_and_duplicate_bars_are_rejected(self):
        self.rewrite_rows(lambda rows: rows.pop(50))
        with self.assertRaisesRegex(ValueError, "gap-free"):
            self.load(allow_synthetic=True)

    def test_duplicate_timestamp_is_rejected(self):
        self.rewrite_rows(lambda rows: rows[1].update(timestamp=rows[0]["timestamp"]))
        with self.assertRaisesRegex(ValueError, "unique"):
            self.load(allow_synthetic=True)

    def test_invalid_ohlc_is_rejected(self):
        self.rewrite_rows(lambda rows: rows[10].update(high="1"))
        with self.assertRaisesRegex(ValueError, "OHLC"):
            self.load(allow_synthetic=True)

    def test_zero_volume_is_rejected(self):
        self.rewrite_rows(lambda rows: rows[10].update(volume="0"))
        with self.assertRaisesRegex(ValueError, "volume"):
            self.load(allow_synthetic=True)

    def test_nonfinite_price_is_rejected(self):
        self.rewrite_rows(lambda rows: rows[10].update(close="NaN"))
        with self.assertRaisesRegex(ValueError, "finite"):
            self.load(allow_synthetic=True)

    def test_naive_and_unclosed_timestamps_are_rejected(self):
        self.rewrite_rows(lambda rows: rows[0].update(timestamp="2024-01-01T00:00:00"))
        with self.assertRaisesRegex(ValueError, "timezone"):
            self.load(allow_synthetic=True)

    def test_future_candle_is_rejected(self):
        with patch("data.loader.datetime", wraps=datetime) as clock:
            clock.now.return_value = datetime(2024, 1, 1, tzinfo=timezone.utc)
            with self.assertRaisesRegex(ValueError, "completed historical"):
                self.load(allow_synthetic=True)

    def test_sample_generator_preserves_existing_files(self):
        before = self.path.read_bytes()
        with self.assertRaises(ValueError):
            generate(self.path)
        self.assertEqual(before, self.path.read_bytes())
