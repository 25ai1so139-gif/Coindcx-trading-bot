"""Offline SYNTHETIC adapter/auth/metadata tests; no real keys or private IO."""

import hashlib
import hmac
import io
import json
import unittest
import os
from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import timedelta
from decimal import Decimal, localcontext
from unittest.mock import Mock, patch

from data.coindcx import HttpResponse, PublicClient, unsigned_get
from exchange.auth import Credentials, ReadOnlyPolicy, prepare_read_only, private_failure
from exchange.contracts import DisabledExecution, ExchangeBlocked, READ_ONLY, SPOT_CREATE
from exchange.instruments import Instrument, discover_instrument
from exchange.orders import preview_entry
from exchange.reconciliation import _wire_request
from risk.audit import RiskAudit
from risk import entry as risk_gate
from tests.exchange_fixtures import D, SYMBOL, fixture


class AuthenticationSafetyTests(unittest.TestCase):
    def setUp(self):
        self.settings, self.at, self.proposal, self.instrument, self.account = fixture()
        self.credentials = Credentials("SYNTHETIC_TEST_KEY", "SYNTHETIC_TEST_SECRET")

    def test_default_disabled_policy_does_not_read_credentials(self):
        self.assertFalse(ReadOnlyPolicy.from_env({}).enabled)
        with patch("exchange.auth.Credentials.from_env", side_effect=AssertionError), self.assertRaises(ExchangeBlocked):
            prepare_read_only("balances", None, ReadOnlyPolicy(), at=self.at)

    def test_missing_or_invalid_credentials_errors_are_redacted(self):
        for value in (None, "", " contains space", "line\nbreak", "é", "x" * 513, {}, True):
            for field in ("key", "secret"):
                with self.subTest(field=field, value_type=type(value).__name__), self.assertRaises(ExchangeBlocked) as error:
                    Credentials(value if field == "key" else "SYNTHETIC_KEY", value if field == "secret" else "SYNTHETIC_SECRET")
                self.assertEqual(str(error.exception), "INVALID_OR_MISSING_CREDENTIALS")

    def test_credentials_read_only_from_approved_names(self):
        with self.assertRaises(ExchangeBlocked):
            Credentials.from_env({"API_KEY": "SYNTHETIC_KEY", "API_SECRET": "SYNTHETIC_SECRET"})
        value = Credentials.from_env({"COINDCX_API_KEY": "SYNTHETIC_KEY", "COINDCX_API_SECRET": "SYNTHETIC_SECRET"})
        self.assertEqual(repr(value), "Credentials(<redacted>)")
        with self.assertRaises(TypeError):
            vars(value)

    def test_strict_read_only_enable_flag(self):
        self.assertTrue(ReadOnlyPolicy.from_env({"COINDCX_ENABLE_READ_ONLY": "1"}).enabled)
        for value in ("true", "yes", "", "2", True):
            with self.subTest(value=value), self.assertRaises(ExchangeBlocked):
                ReadOnlyPolicy.from_env({"COINDCX_ENABLE_READ_ONLY": value})

    def test_enabled_flag_alone_is_not_separate_approval(self):
        with self.assertRaises(ExchangeBlocked):
            prepare_read_only("balances", self.credentials, ReadOnlyPolicy(True), at=self.at)

    def test_read_only_hmac_matches_documented_exact_json_bytes(self):
        request = prepare_read_only("balances", self.credentials, ReadOnlyPolicy(True), at=self.at, separately_approved=True)
        headers = request.headers_for_offline_test()
        expected = hmac.new(b"SYNTHETIC_TEST_SECRET", request.body, hashlib.sha256).hexdigest()
        self.assertEqual(headers["X-AUTH-SIGNATURE"], expected)
        self.assertEqual(request.url, READ_ONLY["balances"])
        self.assertEqual(json.loads(request.body), {"timestamp": 1704247200000})
        self.assertNotIn("SYNTHETIC_TEST", repr(request))

    def test_read_only_requests_cannot_sign_create_cancel_withdraw_or_arbitrary_urls(self):
        for operation in ("create", "cancel", "modify", "withdraw", SPOT_CREATE, [], None):
            with self.subTest(type=type(operation).__name__), self.assertRaises(ExchangeBlocked):
                prepare_read_only(operation, self.credentials, ReadOnlyPolicy(True), at=self.at, separately_approved=True)

    def test_order_status_request_uses_client_id_without_legacy_uuid_exchange_id(self):
        request = prepare_read_only("order_status", self.credentials, ReadOnlyPolicy(True), at=self.at,
                                   separately_approved=True, client_order_id="synthetic-local-1")
        self.assertEqual(json.loads(request.body)["client_order_id"], "synthetic-local-1")
        self.assertNotIn("id", json.loads(request.body))

    def test_private_active_order_envelope_has_bounded_documented_page(self):
        request = prepare_read_only("active_orders", self.credentials, ReadOnlyPolicy(True), at=self.at,
                                   separately_approved=True, market="SYNTHETICINR")
        self.assertEqual(json.loads(request.body)["size"], 200)

    def test_missing_status_identifier_or_market_rejects(self):
        for operation in ("order_status", "active_orders"):
            with self.subTest(operation=operation), self.assertRaises(ExchangeBlocked):
                prepare_read_only(operation, self.credentials, ReadOnlyPolicy(True), at=self.at, separately_approved=True)

    def test_all_private_transport_operations_are_unconditionally_disabled(self):
        with patch("socket.socket", side_effect=AssertionError("no socket")), patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("no request")):
            for method in ("submit", "cancel", "modify", "read_account"):
                with self.subTest(method=method), self.assertRaises(ExchangeBlocked):
                    getattr(DisabledExecution(), method)(enabled=True, credentials=self.credentials)

    def test_auth_and_rate_limit_classification_never_auto_retries(self):
        self.assertEqual(private_failure(401), "AUTHENTICATION_OR_PERMISSION_ERROR")
        self.assertEqual(private_failure(403), "AUTHENTICATION_OR_PERMISSION_ERROR")
        self.assertEqual(private_failure(429), "RATE_LIMITED_RECONCILE_BEFORE_RETRY")
        self.assertEqual(private_failure(503), "PRIVATE_REQUEST_UNRESOLVED")

    def test_existing_public_transport_still_rejects_all_private_routes(self):
        for url in (*READ_ONLY.values(), SPOT_CREATE):
            with self.subTest(url=url), self.assertRaises(ValueError):
                unsigned_get(url, 1)


class InstrumentMetadataTests(unittest.TestCase):
    def test_limit_request_cannot_assume_market_only_instrument_support(self):
        self.detail['order_types']=['market_order']
        with self.assertRaises(ExchangeBlocked):
            discover_instrument(self.client,SYMBOL)

    def test_ambiguous_market_symbol_cannot_choose_an_exchange_implicitly(self):
        markets=self.client.discover()
        second=replace(markets[0],pair='OTHER-SYNTHETIC_INR')
        with patch.object(self.client,'discover',return_value=markets+(second,)),self.assertRaises(ExchangeBlocked):
            discover_instrument(self.client,SYMBOL)

    def setUp(self):
        self.settings, self.at, self.proposal, self.instrument, self.account = fixture()
        self.detail = dict(pair=SYMBOL, symbol="SYNTHETICINR", status="active", base_currency_short_name="INR",
            target_currency_short_name="SYNTHETIC", base_currency_precision=6, target_currency_precision=4,
            min_quantity=".0001", max_quantity="1000", min_notional="1", min_price=".0001", max_price="1000000", step=".0001",
            max_leverage=0, max_leverage_short=0, order_types=["limit_order", "market_order"])
        self.calls = []
        def transport(url, timeout):
            self.calls.append(url)
            payload = ["SYNTHETICINR"] if url.endswith('/markets') else [self.detail]
            return HttpResponse(200, json.dumps(payload).encode(), {})
        self.client = PublicClient(transport=transport, now=lambda:self.at, sleep=lambda _:None, request_interval=0)

    def test_constraint_discovery_reuses_unsigned_client_and_native_market_mapping(self):
        result = discover_instrument(self.client, SYMBOL)
        self.assertEqual(result.market, "SYNTHETICINR")
        self.assertEqual(result.pair, SYMBOL)
        self.assertEqual(result.kind, "public_metadata")
        self.assertEqual(result.step, D(".0001"))
        self.assertTrue(all(url.startswith('https://api.coindcx.com/exchange/v1/markets') for url in self.calls))

    def test_discovery_does_not_upgrade_liquidity_or_infer_three_times_leverage(self):
        result = discover_instrument(self.client, SYMBOL)
        self.assertFalse(hasattr(result, "liquidity_verified"))
        self.assertFalse(hasattr(result, "max_leverage"))

    def test_inactive_market_is_rejected(self):
        self.detail["status"] = "inactive"
        with self.assertRaises(ExchangeBlocked):
            discover_instrument(self.client, SYMBOL)

    def test_missing_constraints_fail_closed(self):
        for key in ("step", "min_notional", "max_quantity", "base_currency_precision"):
            with self.subTest(key=key):
                detail = self.detail.pop(key)
                with self.assertRaises(ExchangeBlocked):
                    discover_instrument(self.client, SYMBOL)
                self.detail[key] = detail

    def test_wrong_currency_or_invalid_precision_is_rejected(self):
        for changes in ({"quote":"USDT"}, {"price_precision":True}, {"quantity_precision":19}, {"step":"0.00001", "quantity_precision":4}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(self.instrument, **changes)

    def test_nonfinite_negative_or_inverted_constraints_reject(self):
        for changes in ({"step":"NaN"}, {"step":0}, {"min_notional":-1}, {"min_quantity":1001}, {"min_price":1000001}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(self.instrument, **changes)

    def test_quantity_precision_and_minimums_are_enforced_without_rounding(self):
        for quantity, price in ((".00011",100), (".00001",100), (1001,100), (".0001",100), (1,"100.0000001")):
            with self.subTest(quantity=quantity,price=price), self.assertRaises(ValueError):
                self.instrument.validate_size(quantity,price)

    def test_exact_constraint_boundary_is_allowed(self):
        self.instrument.validate_size(D('.01'),D(100))


class OrderPreviewTests(unittest.TestCase):
    def setUp(self):
        self.settings, self.at, self.proposal, self.instrument, self.account = fixture()
        self.audit = RiskAudit()

    def review(self, **overrides):
        values = dict(settings=self.settings, account=self.account, proposal=self.proposal, instrument=self.instrument,
                      at=self.at, client_order_id="synthetic-local-1", audit=self.audit)
        values.update(overrides)
        return preview_entry(**values)

    def test_preview_calls_existing_gate_and_submits_zero_orders(self):
        before = deepcopy(self.account.controls.__dict__)
        with patch("risk.entry.approve_entry", wraps=risk_gate.approve_entry) as gate, patch("socket.socket", side_effect=AssertionError):
            result = self.review()
        self.assertTrue(result.approved, result.reason)
        self.assertEqual(gate.call_count,1)
        self.assertEqual(result.orders_submitted,0)
        self.assertFalse(result.live_trading_enabled)
        self.assertEqual(before,self.account.controls.__dict__)
        self.assertEqual(result.data_kind,"synthetic")

    def test_wire_body_has_documented_spot_fields_and_exact_decimal_numbers(self):
        result = self.review()
        payload = _wire_request(result.request_json)
        self.assertEqual(payload['market'],'SYNTHETICINR')
        self.assertNotIn('pair',payload)
        self.assertNotIn('leverage',payload)
        self.assertEqual(payload['price_per_unit'],result.plan.entry_price)
        self.assertEqual(payload['total_quantity'],result.plan.quantity)
        self.assertEqual(result.plan.margin,result.plan.notional/self.settings.leverage)
        self.assertNotIn('AUTH',result.request_json)

    def test_supplied_plan_or_old_approval_is_not_a_supported_input(self):
        with self.assertRaises(TypeError):
            self.review(plan=self.review().plan)

    def test_missing_account_or_audit_fails_closed(self):
        self.assertFalse(self.review(account=None).approved)
        with self.assertRaises(ValueError):
            self.review(audit=None)

    def test_invalid_stop_is_rejected_and_logged(self):
        proposal=replace(self.proposal,decision=replace(self.proposal.decision,stop_loss_reference=None))
        result=self.review(proposal=proposal)
        self.assertFalse(result.approved)
        self.assertIsNone(result.request_json)
        self.assertFalse(self.audit.records[-1].approved)

    def test_stale_or_future_metadata_is_rejected(self):
        for stamp in (self.at-timedelta(minutes=6),self.at+timedelta(seconds=1)):
            with self.subTest(stamp=stamp):
                result=self.review(instrument=replace(self.instrument,observed_at=stamp))
                self.assertEqual(result.reason,'STALE_INSTRUMENT_METADATA')

    def test_stale_market_signal_is_rejected_by_gate(self):
        result=self.review(at=self.at+timedelta(minutes=31))
        self.assertEqual(result.reason,'STALE_MARKET_DATA')

    def test_incomplete_or_duplicate_candles_are_rejected(self):
        for records in (self.proposal.candles+(replace(self.proposal.candles[-1],timestamp=self.at),), self.proposal.candles+(self.proposal.candles[-1],)):
            with self.subTest(size=len(records)):
                self.assertFalse(self.review(proposal=replace(self.proposal,candles=records)).approved)

    def test_ineligible_market_and_missing_fees_remain_rejected(self):
        for changes in ({'eligible':False},{'costs':None},{'instrument':None}):
            with self.subTest(changes=changes):
                proposal=replace(self.proposal,market=replace(self.proposal.market,**changes))
                self.assertFalse(self.review(proposal=proposal).approved)

    def test_three_times_spot_preview_remains_unsupported_and_four_times_invalid(self):
        from tests.helpers import synthetic_proposal
        settings=replace(self.settings,leverage=3)
        controls=deepcopy(self.account.controls);controls.settings=settings
        account=replace(self.account,controls=controls)
        proposal=replace(self.proposal,market=replace(self.proposal.market,costs=replace(self.proposal.market.costs,fee_rate=settings.fee_rate)))
        self.assertEqual(self.review(settings=settings,account=account,proposal=proposal).reason,'SPOT_ORDER_LEVERAGE_UNSUPPORTED')
        with self.assertRaises(ValueError):
            replace(self.settings,leverage=4)

    def test_quantity_and_price_constraints_do_not_round_a_plan_up_or_down(self):
        for changes in ({'max_quantity':D('.5')},{'min_price':D(101)},{'max_price':D(99)},{'price_precision':0}):
            with self.subTest(changes=changes):
                result=self.review(instrument=replace(self.instrument,**changes))
                self.assertFalse(result.approved)
                self.assertIsNone(result.request_json)

    def test_metadata_pair_or_provenance_mismatch_is_rejected(self):
        for changes in ({'pair':'OTHER-INR'},{'kind':'public_metadata'}):
            with self.subTest(changes=changes):
                self.assertFalse(self.review(instrument=replace(self.instrument,**changes)).approved)

    def test_gate_and_wire_constraint_disagreement_is_rejected(self):
        self.assertEqual(self.review(instrument=replace(self.instrument,step=D('.001'))).reason,'RISK_AND_ORDER_CONSTRAINTS_MISMATCH')

    def test_invalid_client_id_rejects_without_logging_its_value(self):
        for identifier in ('',None,[], 'SYNTHETIC_SECRET_WITH_NEWLINE\n', 'x'*101):
            with self.subTest(type=type(identifier).__name__):
                self.assertEqual(self.review(client_order_id=identifier).reason,'INVALID_CLIENT_ORDER_ID')

    def test_daily_loss_and_emergency_halts_are_the_original_gate_controls(self):
        for field in ('daily_halted','emergency_halted','drawdown_halted'):
            controls=deepcopy(self.account.controls);setattr(controls,field,True)
            with self.subTest(field=field):
                self.assertFalse(self.review(account=replace(self.account,controls=controls)).approved)

    def test_one_position_and_three_entries_per_day_remain_enforced(self):
        self.assertEqual(self.review(account=replace(self.account,has_open_position=True)).reason,'one_open_position')
        controls=deepcopy(self.account.controls);controls.entries_today=3
        self.assertEqual(self.review(account=replace(self.account,controls=controls)).reason,'daily_trade_limit')

    def test_readiness_uncertainty_is_rejected_by_shared_gate(self):
        self.assertEqual(self.review(execution_ready=False).reason,'EXECUTION_CONTEXT_REQUIRED')

    def test_ambient_decimal_context_cannot_change_the_draft(self):
        normal=self.review().request_json
        with localcontext() as context:
            context.prec=6
            self.assertEqual(self.review().request_json,normal)


class PublicInspectionCommandTests(unittest.TestCase):
    def test_inspection_has_no_credentials_or_order_access_and_does_not_claim_eligibility(self):
        from cli import main
        _,_,_,instrument,_=fixture()
        with patch.dict(os.environ,{},clear=True),patch('exchange.commands.discover_instrument',return_value=instrument),patch('socket.socket',side_effect=AssertionError),redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(['exchange','instrument','--pair',SYMBOL]),0)
        report=json.loads(output.getvalue())
        self.assertFalse(report['market_qualified'])
        self.assertFalse(report['live_trading_enabled'])
        self.assertEqual(report['orders_submitted'],0)

    def test_metadata_failure_returns_blocked_without_provider_details(self):
        from cli import main
        with patch('exchange.commands.discover_instrument',side_effect=ExchangeBlocked('SYNTHETIC_PRIVATE_EXCEPTION')),redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(['exchange','instrument','--pair',SYMBOL]),2)
        self.assertNotIn('SYNTHETIC_PRIVATE_EXCEPTION',output.getvalue())
        self.assertEqual(json.loads(output.getvalue())['status'],'BLOCKED')

    def test_no_private_command_exists(self):
        from cli import main
        with redirect_stderr(io.StringIO()),self.assertRaises(SystemExit) as error:
            main(['exchange','submit'])
        self.assertEqual(error.exception.code,2)
