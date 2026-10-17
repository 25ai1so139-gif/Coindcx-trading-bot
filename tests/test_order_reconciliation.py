"""Durable SYNTHETIC mock reconciliation; no real exchange or account state."""

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from decimal import localcontext
from pathlib import Path
from unittest.mock import patch

from exchange.contracts import DisabledExecution, ExchangeBlocked
from exchange.reconciliation import (FAILURES, JournalError, MockAccountReport, MockOrderJournal,
                                     _hash, _wire_request, blocked, expected_mock_account, normalize_status)
from paper_trading.state import canonical, strict_json
from risk.audit import RiskAudit
from risk import entry as risk_gate
from tests.exchange_fixtures import D, SYMBOL, fixture, mock_response


class JournalFixture(unittest.TestCase):
    def setUp(self):
        self.settings, self.at, self.proposal, self.instrument, self.account = fixture()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "mock.sqlite3"
        self.book = MockOrderJournal.create(self.path,self.settings,symbol=SYMBOL,allow_mock=True,at=self.at)
        self.audit = RiskAudit()

    def reopen(self):
        return MockOrderJournal.open(self.path,self.settings,symbol=SYMBOL,allow_mock=True)

    def prepare(self, client="synthetic-1", book=None, account=None):
        return (book or self.book).prepare(client,account or self.account,self.proposal,self.instrument,at=self.at,audit=self.audit)

    def response(self, status="open", **kwargs):
        request = self.book.snapshot().state["orders"]["synthetic-1"]["request"]
        return mock_response(request,status=status,**kwargs)

    def observe(self, status="open", **kwargs):
        return self.book.record_mock_status("synthetic-1",self.response(status,**kwargs),at=self.at)

    def advance(self):
        self.at += timedelta(seconds=1)


class ReconciliationStateTests(JournalFixture):
    def test_mock_journal_rejects_phantom_equity_and_nonfixture_account(self):
        controls=deepcopy(self.account.controls)
        controls.last_equity=controls.peak_equity=D(2500)
        for account in (replace(self.account,equity=D(2500),controls=controls),replace(self.account,kind='paper')):
            with self.subTest(kind=account.kind,equity=account.equity):
                self.assertFalse(self.prepare(account=account).approved)
        self.assertEqual(self.book.snapshot().state['orders'],{})

    def test_unexpected_order_status_leaves_durable_quarantine_after_reopen(self):
        raw={'client_order_id':'SYNTHETIC_UNKNOWN_CLIENT','provider_secret':'SYNTHETIC_SECRET_NOT_STORED'}
        try:self.book.record_mock_status('unknown-client',raw,at=self.at)
        except JournalError:pass
        self.assertIn('UNEXPECTED_ORDER',self.reopen().snapshot().state['faults'])
        self.assertFalse(self.prepare(book=self.reopen()).approved)
        self.assertNotIn(b'SYNTHETIC_SECRET_NOT_STORED',self.path.read_bytes())

    def test_unknown_request_failure_cannot_disappear_on_restart(self):
        try:self.book.record_mock_failure('unknown-client','TIMEOUT_AFTER_REQUEST',at=self.at)
        except JournalError:pass
        self.assertIn('UNEXPECTED_ORDER',self.reopen().snapshot().state['faults'])
        self.assertFalse(self.prepare(book=self.reopen()).approved)

    def test_invalid_account_report_is_durably_uncertain(self):
        try:self.book.reconcile_mock_account(None,at=self.at)
        except (JournalError,ExchangeBlocked):pass
        self.assertIn('ACCOUNT_MISMATCH',self.reopen().snapshot().state['faults'])
        self.assertFalse(self.prepare(book=self.reopen()).approved)

    def test_partial_average_cannot_change_without_additional_fills(self):
        self.prepare();self.observe('partially_filled')
        self.advance();self.observe('partially_filled',average='1',updated_at=int(self.at.timestamp()*1000))
        self.assertIn('STATUS_REGRESSION',self.book.snapshot().state['faults'])

    def test_large_fee_fault_cannot_bypass_shared_gate_on_later_entry(self):
        self.prepare();self.observe('filled',fee='10000')
        with patch('risk.entry.approve_entry',wraps=risk_gate.approve_entry) as gate:
            result=self.prepare('synthetic-2')
        self.assertFalse(result.approved)
        self.assertEqual(gate.call_count,1)
        self.assertIn('EXECUTION_COST_OVERRUN',self.book.snapshot().state['faults'])

    def test_exchange_order_id_cannot_be_reassigned_to_second_client_id(self):
        first=self.prepare();self.observe('rejected')
        self.book.reconcile_mock_account(MockAccountReport(D(2000),D(0),()),at=self.at)
        second=self.prepare('synthetic-2')
        self.book.record_mock_status('synthetic-2',mock_response(second.request_json,order_id='12345'),at=self.at)
        self.assertIn('ORDER_MISMATCH',self.book.snapshot().state['faults'])

    def test_prepare_calls_gate_and_reserves_uncertain_request_not_a_fill(self):
        with patch("risk.entry.approve_entry",wraps=risk_gate.approve_entry) as gate,patch("socket.socket",side_effect=AssertionError):
            result=self.prepare()
        self.assertTrue(result.approved,result.reason)
        self.assertEqual(gate.call_count,1)
        value=self.book.snapshot().state
        self.assertEqual(value["label"],"SYNTHETIC_MOCK_ONLY")
        self.assertEqual(value["orders"]["synthetic-1"]["local"],"PREPARED")
        self.assertTrue(blocked(value))
        self.assertEqual(expected_mock_account(value).cash_total,2000)

    def test_prepared_request_blocks_conflicting_or_duplicate_new_drafts(self):
        self.prepare()
        for client in ("synthetic-1","synthetic-2"):
            with self.subTest(client=client):
                result=self.prepare(client)
                self.assertFalse(result.approved)
                self.assertIsNone(result.request_json)
        self.assertEqual(len(self.book.snapshot().state["orders"]),1)
        self.assertEqual(len(self.book.snapshot().state["reviews"]),2)

    def test_init_and_open_map_to_pending_observed_states_and_remain_blocked(self):
        self.prepare()
        self.observe("init")
        self.advance()
        self.observe("open",updated_at=int(self.at.timestamp()*1000))
        order=self.book.snapshot().state["orders"]["synthetic-1"]
        self.assertEqual(order["local"],"OBSERVED")
        self.assertEqual(order["report"]["status"],"open")
        self.assertFalse(self.prepare("synthetic-2").approved)

    def test_rejected_request_requires_account_reconciliation_before_new_draft(self):
        self.prepare();self.observe("rejected")
        self.assertFalse(self.prepare("synthetic-2").approved)
        self.book.reconcile_mock_account(MockAccountReport(D(2000),D(0),()),at=self.at)
        self.assertTrue(self.prepare("synthetic-2").approved)

    def test_cancelled_zero_fill_can_reconcile_but_original_client_id_cannot_be_reused(self):
        self.prepare();self.observe("cancelled")
        self.book.reconcile_mock_account(MockAccountReport(D(2000),D(0),()),at=self.at)
        self.assertFalse(self.prepare().approved)
        self.assertTrue(self.prepare("synthetic-2").approved)

    def test_partial_and_full_fills_project_exact_mock_costs_and_remain_one_position(self):
        self.prepare();self.observe("partially_filled",fee=".02")
        first=expected_mock_account(self.book.snapshot().state)
        self.assertGreater(first.asset_quantity,0)
        self.assertEqual(first.open_order_ids,("12345",))
        self.advance();self.observe("filled",fee=".05",updated_at=int(self.at.timestamp()*1000))
        value=self.book.snapshot().state
        report=expected_mock_account(value)
        wire=_wire_request(value["orders"]["synthetic-1"]["request"])
        self.assertEqual(report.cash_total,2000-wire["total_quantity"]*wire["price_per_unit"]-D('.05'))
        self.assertEqual(report.open_order_ids,())
        self.book.reconcile_mock_account(report,at=self.at)
        self.assertFalse(self.prepare("synthetic-2").approved)
        self.assertEqual(self.audit.records[-1].reason,"one_open_position")

    def test_duplicate_status_response_is_idempotent(self):
        self.prepare();before=self.observe()
        self.advance();after=self.observe()
        self.assertEqual(before,after)

    def test_timeout_after_request_is_durable_unknown_not_a_resend(self):
        self.prepare()
        self.book.record_mock_failure("synthetic-1","TIMEOUT_AFTER_REQUEST",at=self.at)
        reopened=self.reopen()
        self.assertEqual(reopened.snapshot().state["orders"]["synthetic-1"]["local"],"UNKNOWN")
        with patch.object(DisabledExecution,"submit",side_effect=AssertionError("must not send")):
            self.assertFalse(self.prepare("synthetic-2",book=reopened).approved)

    def test_status_lookup_can_resolve_unknown_but_does_not_repeat_request(self):
        self.prepare()
        self.book.record_mock_failure("synthetic-1","TIMEOUT_AFTER_REQUEST",at=self.at)
        self.observe("rejected")
        self.book.reconcile_mock_account(MockAccountReport(D(2000),D(0),()),at=self.at)
        self.assertFalse(blocked(self.book.snapshot().state))
        self.assertTrue(self.prepare("synthetic-2").approved)

    def test_authentication_errors_and_429_never_enable_automatic_retries(self):
        self.prepare()
        for reason in FAILURES:
            with self.subTest(reason=reason):
                self.book.record_mock_failure("synthetic-1",reason,at=self.at)
                self.assertFalse(self.prepare("synthetic-2").approved)
        self.assertEqual(len(self.book.snapshot().state["orders"]),1)

    def test_unknown_wire_status_is_quarantined_without_raw_payload(self):
        self.prepare();raw=self.response();raw.update(status="SYNTHETIC_UNKNOWN_VALUE",provider_secret="SYNTHETIC_SECRET_NOT_STORED")
        self.book.record_mock_status("synthetic-1",raw,at=self.at)
        value=self.book.snapshot().state
        self.assertEqual(value["orders"]["synthetic-1"]["reason"],"UNKNOWN_ORDER_STATUS")
        self.assertNotIn(b"SYNTHETIC_SECRET_NOT_STORED",self.path.read_bytes())
        self.assertFalse(self.prepare("synthetic-2").approved)

    def test_partially_cancelled_remains_unresolved_without_documented_fill_evidence(self):
        self.prepare();self.observe("partially_filled")
        self.advance();self.observe("partially_cancelled",updated_at=int(self.at.timestamp()*1000))
        order=self.book.snapshot().state["orders"]["synthetic-1"]
        self.assertEqual(order["local"],"UNKNOWN")
        self.assertEqual(order["reason"],"UNVERIFIED_PARTIAL_CANCELLATION")
        self.assertEqual(order["report"]["status"],"partially_filled")

    def test_private_stream_envelope_cannot_be_treated_as_rest_status_or_clear_reservation(self):
        # SYNTHETIC shape of documented spot order-update, not a captured private response.
        self.prepare()
        envelope = {"event": "order-update", "data": [self.response("filled", fee=".05")]}
        self.book.record_mock_status("synthetic-1", envelope, at=self.at)
        recovered = self.reopen()
        order = recovered.snapshot().state["orders"]["synthetic-1"]
        self.assertEqual(order["local"], "UNKNOWN")
        self.assertEqual(order["reason"], "INVALID_STATUS_RESPONSE")
        self.assertIsNone(order["report"])
        with patch.object(DisabledExecution, "submit", side_effect=AssertionError("no real transport")):
            self.assertFalse(self.prepare("synthetic-2", book=recovered).approved)

    def test_stream_cancellation_fields_do_not_authorize_inferred_rest_fill_after_restart(self):
        self.prepare()
        before = self.observe("partially_filled").state["orders"]["synthetic-1"]["report"]
        self.advance()
        raw = self.response("partially_cancelled", updated_at=int(self.at.timestamp()*1000))
        raw.update(cancelled_quantity=raw["remaining_quantity"], remaining_quantity=0,
                   base_currency_short_name="INR", target_currency_short_name="SYNTHETIC")
        self.book.record_mock_status("synthetic-1", raw, at=self.at)
        recovered = self.reopen()
        order = recovered.snapshot().state["orders"]["synthetic-1"]
        self.assertEqual(order["local"], "UNKNOWN")
        self.assertEqual(order["reason"], "UNVERIFIED_PARTIAL_CANCELLATION")
        self.assertEqual(order["report"], before)
        self.assertFalse(self.prepare("synthetic-2", book=recovered).approved)

    def test_uuid_order_ids_are_rejected_using_current_documentation(self):
        self.prepare();self.observe(order_id="c87ca633-6218-44ea-900b-e86981358cbd")
        self.assertEqual(self.book.snapshot().state["orders"]["synthetic-1"]["local"],"UNKNOWN")

    def test_partial_fill_cannot_regress_to_open_or_larger_remaining(self):
        self.prepare();self.observe("partially_filled")
        self.advance();self.observe("open",updated_at=int(self.at.timestamp()*1000))
        self.assertIn("STATUS_REGRESSION",self.book.snapshot().state["faults"])

    def test_terminal_status_cannot_change(self):
        self.prepare();self.observe("rejected")
        self.advance();self.observe("open",updated_at=int(self.at.timestamp()*1000))
        self.assertIn("STATUS_REGRESSION",self.book.snapshot().state["faults"])

    def test_changed_order_identity_or_market_latches_fault(self):
        self.prepare();raw=self.response();raw['market']='OTHERINR'
        self.book.record_mock_status("synthetic-1",raw,at=self.at)
        self.assertIn("ORDER_MISMATCH",self.book.snapshot().state["faults"])

    def test_price_or_quantity_mismatch_cannot_overwrite_local_request(self):
        self.prepare();before=self.book.snapshot().state["orders"]["synthetic-1"]["request"]
        raw=self.response();raw['total_quantity']=D(1000)
        self.book.record_mock_status("synthetic-1",raw,at=self.at)
        value=self.book.snapshot().state
        self.assertEqual(value["orders"]["synthetic-1"]["request"],before)
        self.assertIn("ORDER_MISMATCH",value["faults"])

    def test_invalid_or_future_report_timestamp_is_unknown(self):
        self.prepare();raw=self.response();raw['updated_at']+=1000
        self.book.record_mock_status("synthetic-1",raw,at=self.at)
        self.assertEqual(self.book.snapshot().state["orders"]["synthetic-1"]["reason"],"INVALID_STATUS_RESPONSE")

    def test_response_with_impossible_remaining_or_nonfinite_fee_is_unknown(self):
        self.prepare()
        for changes in ({'remaining_quantity':D(-1)},{'remaining_quantity':D(10000)},{'fee_amount':'NaN'},{'avg_price':True}):
            with self.subTest(changes=changes):
                raw=self.response();raw.update(changes)
                self.book.record_mock_status("synthetic-1",raw,at=self.at)
                self.assertEqual(self.book.snapshot().state["orders"]["synthetic-1"]["local"],"UNKNOWN")

    def test_fee_overrun_latches_uncertainty_instead_of_adjusting_approval(self):
        self.prepare();self.observe("filled",fee="1")
        self.assertIn("EXECUTION_COST_OVERRUN",self.book.snapshot().state["faults"])

    def test_account_mismatch_with_unexpected_position_latches_fault(self):
        self.book.reconcile_mock_account(MockAccountReport(D(2000),D(1),()),at=self.at)
        self.assertIn("ACCOUNT_MISMATCH",self.reopen().snapshot().state["faults"])
        self.assertFalse(self.prepare().approved)

    def test_unexpected_balance_or_open_order_cannot_clear_block(self):
        for report in (MockAccountReport(D(1999),D(0),()),MockAccountReport(D(2000),D(0),("999",))):
            self.book.reconcile_mock_account(report,at=self.at)
            self.assertFalse(self.prepare().approved)
        self.book.reconcile_mock_account(MockAccountReport(D(2000),D(0),()),at=self.at)
        self.assertIn("ACCOUNT_MISMATCH",self.book.snapshot().state["faults"])

    def test_balance_report_cannot_resolve_unknown_order(self):
        self.prepare()
        value=self.book.reconcile_mock_account(MockAccountReport(D(2000),D(0),()),at=self.at).state
        self.assertFalse(value["account_reconciled"])
        self.assertFalse(self.prepare("synthetic-2").approved)

    def test_emergency_halt_persists_and_shared_gate_logs_its_reason(self):
        self.book.emergency_halt(at=self.at)
        result=self.prepare(book=self.reopen())
        self.assertFalse(result.approved)
        self.assertEqual(result.reason,'emergency_shutdown')
        self.assertTrue(result.risk_record.emergency_halted)
        self.assertFalse(self.account.controls.emergency_halted)

    def test_daily_halt_rejection_does_not_create_request(self):
        controls=deepcopy(self.account.controls);controls.daily_halted=True
        result=self.prepare(account=replace(self.account,controls=controls))
        self.assertEqual(result.reason,'daily_loss_limit')
        self.assertEqual(self.book.snapshot().state["orders"],{})

    def test_rejected_risk_review_is_logged_without_reserving_a_client_id(self):
        proposal=replace(self.proposal,market=replace(self.proposal.market,eligible=False))
        result=self.book.prepare('synthetic-1',self.account,proposal,self.instrument,at=self.at,audit=self.audit)
        self.assertFalse(result.approved)
        self.assertTrue(self.prepare().approved)

    def test_journal_does_not_change_paper_account_or_expose_execution(self):
        before=deepcopy(self.account.controls.__dict__)
        self.prepare();self.observe('filled',fee='.05')
        self.assertEqual(self.account.equity,2000)
        self.assertEqual(self.account.controls.__dict__,before)
        self.assertFalse(hasattr(self.book,'submit'))

    def test_ambient_decimal_context_does_not_change_reconciliation(self):
        self.prepare();self.observe('filled',fee='.05')
        expected=self.book.snapshot()
        with localcontext() as context:
            context.prec=5
            self.assertEqual(self.reopen().snapshot(),expected)


class JournalRecoveryTests(JournalFixture):
    def test_rehashed_invalid_stop_cannot_be_accepted_as_valid_history(self):
        self.prepare()
        with sqlite3.connect(self.path) as connection:
            raw=connection.execute('SELECT payload FROM events WHERE revision=1').fetchone()[0]
            event=strict_json(raw);event['plan']['stop_price']='9999'
            payload=canonical(event);digest=_hash(payload)
            prior=connection.execute('SELECT chain FROM events WHERE revision=0').fetchone()[0]
            chain=_hash(canonical([prior,1,digest]))
            connection.execute('UPDATE events SET payload=?,digest=?,chain=? WHERE revision=1',(payload,digest,chain))
            connection.execute('UPDATE head SET chain=?',(chain,))
        with self.assertRaises(JournalError):
            self.reopen()

    def test_fresh_reopen_can_detect_rollback_using_external_checkpoint(self):
        old=self.path.read_bytes();self.prepare();head=self.book.snapshot()
        self.path.write_bytes(old)
        with self.assertRaises(JournalError):
            MockOrderJournal.open(self.path,self.settings,symbol=SYMBOL,allow_mock=True,expected_head=head)

    def child(self, body, expected=0):
        code="""
import sys,os,json
from datetime import datetime
from exchange.reconciliation import MockOrderJournal
from tests.exchange_fixtures import fixture,SYMBOL
from risk.audit import RiskAudit
settings,at,proposal,instrument,account=fixture()
book=MockOrderJournal.open(sys.argv[1],settings,symbol=SYMBOL,allow_mock=True)
"""+body
        result=subprocess.run([sys.executable,'-c',code,str(self.path)],capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,expected,result.stderr)
        return result

    def test_actual_process_restart_preserves_prepared_and_unknown_requests(self):
        self.prepare();self.book.record_mock_failure('synthetic-1','TIMEOUT_AFTER_REQUEST',at=self.at)
        before=self.book.snapshot()
        result=self.child('print(book.snapshot().state_json)\n')
        self.assertEqual(result.stdout.strip(),before.state_json)

    def test_actual_process_death_before_commit_leaves_no_prepared_request(self):
        before=self.book.snapshot()
        self.child("book._commit=lambda connection:os._exit(73)\nbook.prepare('synthetic-1',account,proposal,instrument,at=at,audit=RiskAudit())\n",73)
        self.assertEqual(self.reopen().snapshot(),before)

    def test_actual_process_death_after_commit_preserves_one_request(self):
        self.child("commit=book._commit\ndef die(connection):\n commit(connection)\n os._exit(74)\nbook._commit=die\nbook.prepare('synthetic-1',account,proposal,instrument,at=at,audit=RiskAudit())\n",74)
        value=self.reopen().snapshot().state
        self.assertEqual(len(value['orders']),1)
        self.assertFalse(self.prepare(book=self.reopen()).approved)

    def test_two_connections_cannot_prepare_conflicting_requests(self):
        second=self.reopen()
        with ThreadPoolExecutor(max_workers=2) as executor:
            one=executor.submit(self.prepare,'synthetic-1',self.book)
            two=executor.submit(self.prepare,'synthetic-2',second)
            results=[one.result(timeout=10),two.result(timeout=10)]
        self.assertEqual(sum(result.approved for result in results),1)
        self.assertEqual(len(self.reopen().snapshot().state['orders']),1)

    def test_commit_failure_is_atomic_and_poisons_handle(self):
        before=self.book.snapshot()
        with patch.object(self.book,'_commit',side_effect=sqlite3.OperationalError('SYNTHETIC_SECRET_NOT_LOGGED')):
            with self.assertRaises(JournalError) as error:
                self.prepare()
        self.assertNotIn('SYNTHETIC_SECRET_NOT_LOGGED',str(error.exception))
        self.assertEqual(self.reopen().snapshot(),before)
        with self.assertRaises(JournalError):
            self.prepare()

    def test_missing_path_never_creates_fresh_history(self):
        path=self.path.with_name('missing.sqlite3')
        with self.assertRaises(JournalError):
            MockOrderJournal.open(path,self.settings,symbol=SYMBOL,allow_mock=True)
        self.assertFalse(path.exists())

    def test_explicit_mock_opt_in_and_existing_file_protection(self):
        with self.assertRaises(ValueError):
            MockOrderJournal.open(self.path,self.settings,symbol=SYMBOL)
        before=self.path.read_bytes()
        with self.assertRaises(FileExistsError):
            MockOrderJournal.create(self.path,self.settings,symbol=SYMBOL,allow_mock=True)
        self.assertEqual(self.path.read_bytes(),before)

    def test_corrupt_database_or_history_fails_closed(self):
        self.prepare()
        with sqlite3.connect(self.path) as connection:
            connection.execute("UPDATE events SET payload='{}' WHERE revision=1")
        with self.assertRaises(JournalError):
            self.reopen()

    def test_configuration_or_schema_version_mismatch_rejects_without_reset(self):
        with self.assertRaises(JournalError):
            MockOrderJournal.open(self.path,replace(self.settings,fee_rate='.002'),symbol=SYMBOL,allow_mock=True)
        with sqlite3.connect(self.path) as connection:
            connection.execute('PRAGMA user_version=99')
        with self.assertRaises(JournalError):
            self.reopen()

    def test_in_process_rollback_of_whole_valid_file_is_detected(self):
        old=self.path.read_bytes()
        self.prepare()
        self.path.write_bytes(old)
        with self.assertRaises(JournalError):
            self.book.snapshot()

    def test_reentrant_audit_callback_cannot_commit_a_request(self):
        audit=RiskAudit()
        original=audit.record
        def nested(**kwargs):
            try:self.book.emergency_halt(at=self.at)
            except JournalError:pass
            return original(**kwargs)
        with patch.object(audit,'record',side_effect=nested),self.assertRaises(JournalError):
            self.book.prepare('synthetic-1',self.account,self.proposal,self.instrument,at=self.at,audit=audit)
        self.assertEqual(self.reopen().snapshot().state['orders'],{})

    def test_returned_snapshot_is_detached_and_contains_no_credential_environment(self):
        with patch.dict(os.environ,{'COINDCX_API_KEY':'SYNTHETIC_CREDENTIAL_SENTINEL','COINDCX_API_SECRET':'SYNTHETIC_CREDENTIAL_SENTINEL'}):
            self.prepare()
        snapshot=self.book.snapshot()
        value=snapshot.state;value['emergency_halted']=True
        self.assertFalse(self.book.snapshot().state['emergency_halted'])
        self.assertNotIn(b'SYNTHETIC_CREDENTIAL_SENTINEL',self.path.read_bytes())

    def test_closed_handle_cannot_prepare(self):
        self.book.close()
        with self.assertRaises(JournalError):
            self.prepare()

    def test_invalid_wire_status_does_not_store_arbitrary_provider_extras(self):
        self.prepare();raw=self.response();raw.update(provider_secret='SYNTHETIC_PRIVATE_BODY',error='SYNTHETIC_PRIVATE_BODY')
        self.book.record_mock_status('synthetic-1',raw,at=self.at)
        self.assertNotIn(b'SYNTHETIC_PRIVATE_BODY',self.path.read_bytes())


if __name__=='__main__':
    unittest.main()
