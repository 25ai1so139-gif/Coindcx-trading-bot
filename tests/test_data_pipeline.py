import hashlib
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from unittest.mock import patch

from cli import main
from data.coindcx import PublicDataError
from data.loader import load_csv
from data.quality import DataPolicy, assess
from data.storage import read_csv, write_dataset
from tests.market_fixtures import csv_fixture, end, metadata, rows


class CsvPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.input = self.directory / 'source.csv'
        csv_fixture(self.input)
        self.policy = DataPolicy(min_history_bars=200, min_quote_volume_per_bar="100")

    def export(self, output):
        source = read_csv(self.input)
        result = assess(source.rows, source.metadata, self.policy, end())
        write_dataset(output, result, source.metadata, source.raw)
        return result

    def test_csv_roundtrip_retains_values_and_all_required_fields(self):
        output = self.directory / 'normalized.csv'
        assessment = self.export(output)
        imported = read_csv(output)
        repeated = assess(imported.rows, imported.metadata, self.policy, end())
        self.assertEqual(assessment.completed, repeated.completed)
        self.assertEqual(len(imported.rows), 200)
        self.assertEqual(imported.rows[0]['symbol'], metadata()['symbol'])
        self.assertEqual(imported.rows[0]['timeframe'], '15m')

    def test_original_bytes_and_review_reset_are_preserved(self):
        before = self.input.read_bytes()
        output = self.directory / 'normalized.csv'
        self.export(output)
        meta = json.loads(output.with_suffix('.json').read_text())
        raw = output.parent / meta['raw_file']
        self.assertEqual(raw.read_bytes(), before)
        self.assertEqual(self.input.read_bytes(), before)
        self.assertEqual(meta['raw_sha256'], hashlib.sha256(before).hexdigest())
        self.assertFalse(meta['quality_reviewed'])
        self.assertTrue(output.with_suffix('.report.json').is_file())

    def test_export_is_reproducible(self):
        first = self.directory / 'first.csv'
        second = self.directory / 'second.csv'
        self.export(first)
        self.export(second)
        self.assertEqual(first.read_bytes(), second.read_bytes())
        self.assertEqual(first.with_suffix('.json').read_bytes(), second.with_suffix('.json').read_bytes())
        self.assertEqual(first.with_suffix('.report.json').read_bytes(), second.with_suffix('.report.json').read_bytes())

    def test_export_never_overwrites(self):
        output = self.directory / 'normalized.csv'
        self.export(output)
        before = output.read_bytes()
        with self.assertRaises(ValueError):
            self.export(output)
        self.assertEqual(output.read_bytes(), before)

    def test_phase1_loader_requires_review_then_rechecks_quality(self):
        output = self.directory / 'normalized.csv'
        self.export(output)
        with self.assertRaisesRegex(ValueError, 'quality review'):
            # synthetic opt-in does not need historical provenance review, but this
            # test switches to historical to verify the existing review gate.
            meta = json.loads(output.with_suffix('.json').read_text())
            meta.update(kind='historical', source='https://public.coindcx.com/market_data/candles')
            output.with_suffix('.json').write_text(json.dumps(meta))
            load_csv(output, min_history_bars=200)
        meta['quality_reviewed'] = True
        output.with_suffix('.json').write_text(json.dumps(meta))
        result = load_csv(output, min_history_bars=200)
        self.assertEqual(len(result.candles), 200)
        meta['market_status'] = 'inactive'
        output.with_suffix('.json').write_text(json.dumps(meta))
        with self.assertRaisesRegex(ValueError, 'quality recheck'):
            load_csv(output, min_history_bars=200)

    def test_bad_source_cannot_become_eligible_by_dropping_invalid_rows(self):
        records = rows()
        records.append({**records[-1], 'high': '1'})
        csv_fixture(self.input, records)
        output = self.directory / 'rejected.csv'
        assessment = self.export(output)
        self.assertFalse(assessment.report['eligible'])
        with self.assertRaisesRegex(ValueError, 'ingestion eligibility'):
            load_csv(output, min_history_bars=200, allow_synthetic=True)
        self.assertEqual(len(read_csv(output).rows), 200)
        self.assertEqual(assessment.report['input_rows'], 201)

    def test_reimport_cannot_erase_a_previous_ingestion_rejection(self):
        csv_fixture(self.input, rows() + [{**rows()[-1], 'high': '1'}])
        rejected = self.directory / 'rejected.csv'
        self.export(rejected)
        imported = read_csv(rejected)
        repeated = assess(imported.rows, imported.metadata, self.policy, end())
        self.assertFalse(repeated.report['eligible'])
        self.assertIn('SOURCE_INGESTION_REJECTED', repeated.report['reasons'])
        reexported = self.directory / 'reexported.csv'
        write_dataset(reexported, repeated, imported.metadata, imported.raw)
        self.assertFalse(read_csv(reexported).metadata['ingestion_eligible'])
        with self.assertRaisesRegex(ValueError, 'ingestion eligibility'):
            load_csv(reexported, min_history_bars=200, allow_synthetic=True)

    def test_corruption_and_missing_sidecar_are_rejected(self):
        self.input.write_bytes(self.input.read_bytes() + b'\n')
        with self.assertRaisesRegex(ValueError, 'SHA-256'):
            read_csv(self.input)
        self.input.with_suffix('.json').unlink()
        with self.assertRaises(FileNotFoundError):
            read_csv(self.input)


class DataCommandTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.input = self.directory / 'source.csv'
        csv_fixture(self.input)
        self.policy = self.directory / 'policy.json'
        self.policy.write_text(json.dumps({'min_history_bars':200, 'min_quote_volume_per_bar':'100'}))
        env = patch.dict(os.environ, {}, clear=True)
        env.start()
        self.addCleanup(env.stop)

    def invoke(self, action, *extra):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = main(['data', action, *extra])
        return result, stdout.getvalue(), stderr.getvalue()

    def test_import_and_validate_run_offline_without_any_broker(self):
        output = self.directory / 'normalized.csv'
        with patch('socket.socket', side_effect=AssertionError('network prohibited')), \
             patch('paper_trading.broker.PaperBroker.__init__', side_effect=AssertionError('orders prohibited')):
            code, text, errors = self.invoke('import', '--input', str(self.input), '--output', str(output),
                                            '--policy', str(self.policy), '--as-of', end().isoformat())
            self.assertEqual(code, 0, errors)
            self.assertTrue(json.loads(text)['eligible'])
            code, text, errors = self.invoke('validate', '--input', str(output), '--policy', str(self.policy),
                                            '--as-of', end().isoformat())
            self.assertEqual(code, 0, errors)
            self.assertFalse(json.loads(text)['live_trading_enabled'])

    def test_default_policy_fails_closed_with_an_inspectable_report(self):
        code, text, errors = self.invoke('validate', '--input', str(self.input), '--as-of', end().isoformat())
        self.assertEqual(code, 2, errors)
        self.assertEqual(json.loads(text)['status'], 'INSUFFICIENT_HISTORY')

    def test_rejected_normalized_input_stays_blocked_in_cli(self):
        csv_fixture(self.input, rows() + [{**rows()[-1], 'high': '1'}])
        rejected = self.directory / 'rejected.csv'
        reexported = self.directory / 'reexported.csv'
        arguments = ('--policy', str(self.policy), '--as-of', end().isoformat())
        code, _, errors = self.invoke('import', '--input', str(self.input),
                                      '--output', str(rejected), *arguments)
        self.assertEqual(code, 2, errors)
        for action, extra in (('validate', ()), ('import', ('--output', str(reexported)))):
            code, text, errors = self.invoke(action, '--input', str(rejected), *extra, *arguments)
            with self.subTest(action=action):
                self.assertEqual(code, 2, errors)
                self.assertEqual(json.loads(text)['status'], 'SOURCE_INGESTION_REJECTED')
        self.assertFalse(read_csv(reexported).metadata['ingestion_eligible'])

    def test_api_failure_is_a_structured_failure_not_a_dataset(self):
        with patch('data.commands.PublicClient') as client:
            client.return_value.discover.side_effect = PublicDataError('API_FAILURE', 'HTTP 503', 503)
            code, text, errors = self.invoke('markets')
        self.assertEqual(code, 2, errors)
        self.assertEqual(json.loads(text)['http_status'], 503)
        self.assertEqual(json.loads(text)['status'], 'API_FAILURE')

    def test_fetch_is_wired_to_public_client_and_never_a_broker(self):
        from data.coindcx import History, Market
        market = Market(metadata()['symbol'], 'SYNTHETICINR', 'INR', 'SYNTHETIC', 'active', True)
        history = History(tuple(rows()), market, (b'[]',), True, ())
        output = self.directory / 'fetched.csv'
        with patch('data.commands.PublicClient') as client, \
             patch('paper_trading.broker.PaperBroker.__init__', side_effect=AssertionError):
            client.return_value.history.return_value = history
            code, text, errors = self.invoke('fetch', '--pair', market.pair, '--start', rows(1)[0]['timestamp'],
                                            '--end', end().isoformat(), '--output', str(output), '--policy', str(self.policy))
        # The public API fixture deliberately cannot attest quote turnover.
        self.assertEqual(code, 2, errors)
        self.assertIn('LIQUIDITY_REVIEW_REQUIRED', json.loads(text)['reasons'])
        self.assertTrue(output.is_file())
        self.assertFalse(read_csv(output).metadata['quality_reviewed'])

    def test_unknown_policy_fields_fail_clearly(self):
        self.policy.write_text('{"made_up_threshold": 1}')
        code, text, errors = self.invoke('validate', '--input', str(self.input), '--policy', str(self.policy))
        self.assertEqual(code, 2)
        self.assertIn('unknown fields', errors)
