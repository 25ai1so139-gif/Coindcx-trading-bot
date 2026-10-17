# Phase 7 audit — offline exchange and reconciliation readiness

2026-10-17 UTC. Actual environment: Linux 6.18.55 x86_64/glibc 2.41,
CPython 3.12.14, SQLite 3.53.1. Results describe the current working tree, not a
published commit. No native Windows execution, private network access, real
credentials, order submission/cancellation/modification, short enablement,
profitability claim or Phase 8 work occurred.

**Offline architecture, deterministic safety and regressions: PASS on Linux.
Real exchange execution/account reconciliation readiness: BLOCKED. No overall
operational PASS.**

## Gate 0

Inspected the Phase 1–6B audit/validation records and actual configuration, CLI,
data client/schema/quality/cache, strategy/review interfaces, risk gate/sizing/
stops/controls/audit, broker, state codec and SQLite session/persistence code.
Gate 0 full discovery passed before implementation: 482 passed, 0 failed,
0 errors, 1 optional public skip (483 total). No critical regression was found.
The mandatory gate and durable recoveries are exercised by all pre-existing
tests, including real child-process deaths and two-process duplicate prevention.

Phase 6B historical evidence showed safe public-data rejection, not a qualified
fill. The user explicitly allowed documenting unverified public-data behavior
in Gate 0 item 6. This task therefore proceeded with **offline/mock readiness
only**, retaining the real-market entry block. Current public discovery,
instrument inspection, enabled integration and actual worker smoke were run as
described below. Qualified real-data paper fills, private permissions, native
Windows and operational hosting remain missing evidence, not inferred successes.

## Final exact commands and counts

All commands ran from /workspace/Coindcx-trading-bot with the existing Python
3.12 virtual environment. No dependency installation or package additions were
needed. Counts below are completed runs, with shell exit codes preserved.

| Command | Passed | Failed | Errors | Skipped | Total |
| --- | ---: | ---: | ---: | ---: | ---: |
| .venv/bin/python -m unittest discover -s tests -v (Gate 0) | 482 | 0 | 0 | 1 | 483 |
| .venv/bin/python -m unittest tests.test_exchange_adapter tests.test_order_reconciliation tests.test_continuous_paper tests.test_persistence tests.test_central_risk tests.test_risk -v | 327 | 0 | 0 | 0 | 327 |
| .venv/bin/python -m unittest discover -s tests -v (final) | 577 | 0 | 0 | 1 | 578 |
| COINDCX_RUN_PUBLIC_INTEGRATION=1 .venv/bin/python -m unittest discover -s tests -v (final) | 578 | 0 | 0 | 0 | 578 |
| COINDCX_RUN_PUBLIC_INTEGRATION=1 .venv/bin/python -m unittest tests.integration.test_coindcx_public -v | 1 | 0 | 0 | 0 | 1 |

Final safety/offline/public runs took 12.034s / 27.314s / 29.116s respectively.
The separately enabled integration took 2.320s. The optional integration is the
only default skip; it was separately executed and included in final enabled
discovery, so no available test remained unrun. Native Windows, private auth/order
validation, physical power loss, long hosting and market qualification were not
performed. They are limitations, not skipped passing unit tests.

New modules contain 44 adapter/auth/metadata/CLI tests and 51 journal/reconciliation
tests (95 total), all clearly labeled SYNTHETIC. All 482 prior offline tests remain
unchanged and pass. Earlier passing intermediate suites did not replace final
verification. New adversarial reproductions exposed defects in this phase's code;
they were fixed before the final full runs, as detailed below.

Example actual capture wrapper (same structure used for each final test command):

~~~bash
.venv/bin/python -m unittest discover -s tests -v > /tmp/phase7-full-offline-final.log 2>&1
code=$?; tail -n 6 /tmp/phase7-full-offline-final.log; exit "$code"
COINDCX_RUN_PUBLIC_INTEGRATION=1 .venv/bin/python -m unittest discover -s tests -v > /tmp/phase7-full-public-final.log 2>&1
code=$?; tail -n 6 /tmp/phase7-full-public-final.log; exit "$code"
~~~

The /tmp files are current execution artifacts, not durable production evidence.
Exact Windows PowerShell verification commands are in PHASE7_READINESS.md and
README.md. No Windows pass is inferred from Linux or historical Phase 1 CI.

## Implementation and changed files

| File | Change |
| --- | --- |
| exchange/__init__.py | New package explicitly limited to offline readiness |
| exchange/contracts.py | Verified spot identifiers/status names, static rejection codes and unconditionally disabled submit/cancel/modify/private transport |
| exchange/auth.py | Optional environment credential interface, redacted memory objects, disabled policy and locally signed read-only envelopes; no sender |
| exchange/instruments.py | Reuse public discovery/client; validate identity, constraints, limit support and freshness without qualifying liquidity |
| exchange/orders.py | Fresh central-gate review, exact Decimal spot BUY/limit request JSON, no cached plan permission, no transport |
| exchange/reconciliation.py | Independent transactional mock journal, reservations, unknown/fault quarantine, conservative statuses, internal synthetic account comparison and restart recovery |
| exchange/commands.py | Public-only exchange instrument --pair inspection |
| cli.py | Dispatch/help for that public inspection; existing paper/manual/verify/backtest commands preserved |
| tests/exchange_fixtures.py | Explicit synthetic metadata, account, proposal and mock-response helpers |
| tests/test_exchange_adapter.py | 44 deterministic auth, metadata, request, risk and CLI tests |
| tests/test_order_reconciliation.py | 51 deterministic state, corruption, unknown-order, mismatch, concurrency and real child-process recovery tests |
| README.md / VALIDATION.md | Current commands, scope and final verification results |
| docs/PHASE7_READINESS.md | API sources, design, assumptions, operating/Windows instructions and Phase 8 prerequisites |
| docs/PHASE7_AUDIT.md | This evidence and requirement report |
| docs/examples/phase7-public-evidence.json | Actual read-only discovery/instrument/worker evidence; explicitly not qualification or returns |

Only cli.py, README.md and VALIDATION.md were modified from the inherited tree;
13 files were added, 93 inherited files remained byte-identical, and none were
deleted. All Phase 5 gate/config/risk limits, Phase 6A/6B
broker/storage/session code, public pipeline, strategies and all pre-existing
tests remain byte-identical to the pre-edit archive. No existing file was deleted,
no core trading fingerprint was altered, and no rule or strategy parameter was
weakened/tuned. Git HEAD predates earlier phases; its larger cumulative diff also
contains inherited uncommitted work, which is not this task's change set.

## Central authority and reconciliation safeguards

Existing execution remains strategy/simulation/worker -> PaperBroker.process_bar
-> sole _open mutation -> risk.entry.approve_entry. The state codec restores
previously validated positions rather than creating a new approved entry. Manual
and verify still perform reviews with zero orders. Managed paper accounts retain
their ownership/stop transaction requirements.

New request flow is preview_entry -> fresh account controls -> approve_entry ->
local instrument/request constraints. An arbitrary PositionPlan or old approval
cannot be supplied as permission. The mock journal calls that same path under
BEGIN IMMEDIATE, overlays its own emergency/known-position state on a copy, and
passes unresolved readiness to the central gate. It commits a PREPARED_NOT_SENT
reservation before returning a draft. Pending/unknown/held-position/account-fault
states block another draft. A standalone preview is a stateless hypothetical
review, never a reservation, fill or execution permission.

The journal's fixed synthetic baseline cannot be replaced by a supplied ₹2,500
equity assertion or a different account kind. Known filled mock exposure is held;
no exit, deposit, realized-return or real account projection is fabricated.
Request/status storage never changes paper equity or counters. Existing Phase 5
entry limits stay authoritative for actual paper entries. A future real execution
bridge needs additional atomic fill/risk integration; it is not implemented here.

Timeout/auth/429 statuses become UNKNOWN, not retry permission. Invalid and
partially_cancelled statuses preserve the last valid observation and block new
drafts. Known statuses plus exact internal mock-account comparison can resolve
recoverable no-fill uncertainty; mismatches and emergency latches persist.
Identical status repeats are no-ops. Identity reassignment, cumulative-fill/fee/
time/average regressions and unexpected requests are durable faults. There is no
fault-clear/reset/resend command or network order method.

SQLite journal transactions use FULL synchronization, DELETE journaling, strict
application/schema/settings/implementation bindings, canonical event digests,
hash chains/head and independent replay/request-plan-cost checks. Rejected risk
reviews are also durably recorded. Storage or ambiguous commit failures poison
the handle; explicit reopen recovers the actual committed history. Tests kill
child processes before/after commit and recover unresolved requests. Separate
connections cannot reserve conflicting requests. A trusted external expected_head
can detect whole-file rollback after restart; without independent latest evidence
a fresh process cannot prove a valid old file is the newest. Hashes are not
authentication or a defense against arbitrary hostile Python/direct SQL edits.

## Verified documentation and actual public evidence

Official https://docs.coindcx.com/ returned HTTP 200 with TLS verification.
Captured deployed HTML SHA-256:
6ca23c1831245795d6df8a58a0d0bdecae40996681b99a02475945b855247ab5.
The same snapshot digest is recorded in phase7-public-evidence.json. Reviewed source sections and
exact routes/schemas are listed in PHASE7_READINESS.md.

Public markets/market-details/candles remain unsigned GETs. Candle intervals are
1m/15m/1h/1d; only 15m is used. Spot creation uses the new-order section, not the
futures create-order heading. The current docs require positive numeric spot
order IDs and reject reused client_order_id values. Older UUID examples do not
override that contract. Spot status fields, cumulative quantities, fee_amount and
millisecond timestamps are parsed only from mocked private responses.

Actually executed public commands:

~~~bash
.venv/bin/python -m cli data markets
.venv/bin/python -m cli exchange instrument --pair I-BTC_INR
COINDCX_RUN_PUBLIC_INTEGRATION=1 .venv/bin/python -m unittest tests.integration.test_coindcx_public -v
PYTHONPATH=. .venv/bin/python /tmp/phase7-worker-smoke.py
~~~

I-BTC_INR was chosen from the **actual discovery output**, not hardcoded as
tradable. Discovery returned 991 markets, including 339 confirmed active INR
markets. Instrument inspection succeeded and returned the distinct order market
BTCINR, fresh constraints and declared limit support, while explicitly setting
market_qualified=false and price_tick_exchange_validated=false.

The actual foreground-worker harness started a temporary account, inspected it
through the CLI and stopped it from a separate process. All three exit codes were
0. At 2026-10-17T11:39:31 UTC the worker reported DATA_BLOCKED/ZERO_VOLUME,
₹2,000 equity, zero processed candles/entries/orders, then STOPPED with the
emergency latch retained. This proves public fetch/safe-rejection/control behavior,
not eligible real-data processing or a qualified fill. No worker remains running.
The durable JSON artifact records these observations and zero private requests.
The first attempted harness reused an absent /tmp Phase 6B helper and could not
run; a new temporary Phase 7 harness was written and successfully executed. No
claim depends on the missing helper or on environment publication.

## Confirmed defects fixed before final verification

Deterministic adversarial tests first reproduced these gaps in the new code:

1. Unknown local-request status/failure and an invalid account report initially
   failed only the current call/handle. Reopening could lose that uncertainty.
   They now commit UNEXPECTED_ORDER / ACCOUNT_MISMATCH quarantine events. The
   initial three-test reproduction failed 3 assertions; final tests pass.
2. An unexplained higher-equity snapshot could authorize a draft in a journal
   with a different fixed ₹2,000 baseline. Mock preparation and recovery now bind
   that baseline and require the explicit synthetic account kind. Its adversarial
   reproduction failed before the fix and passes in the complete suite.
3. Instrument discovery initially did not require explicit limit-order support
   or reject an ambiguous order-market mapping. The two-test reproduction
   failed; discovery now refuses missing/market-only support and duplicate active
   mappings. All final adapter and regression tests pass.

Additional tested guards cover rehashed invalid stop/fee math, same-quantity
average corrections, reused exchange IDs and fee overruns. No pre-existing Phase
1–6B test was removed, relaxed or edited to make these outcomes pass.

## Requirement statuses and exact remaining work

| Requirement | Status | Evidence / limit |
| --- | --- | --- |
| Gate 0 code/audit/full regression | PASS on Linux | Baseline and all final tests passed; real-market limitation explicitly documented |
| Central gate and fixed risk policy | PASS for supported paper/draft APIs | Existing 86 gate tests plus new request/journal spies and rejection cases; core source unchanged |
| Phase 6A restart and Phase 6B worker safety | PASS on Linux | All persistence/worker regressions plus actual public CLI safe-rejection/stop smoke |
| Public market/instrument discovery and quality | PASS for access/validation | Existing pipeline unchanged; new active/unambiguous/limit/constraint checks tested; actual public inspection passed |
| Public rate-limit compliance | PASS for bounded local policy; server quota UNVERIFIED | Existing spacing/Retry-After/timeout tests; no documented public candle quota inferred |
| Secret-safe future auth interface | PASS offline | Disabled policy, approved variable names, redacted objects, no withdrawal/write signer, no private sender |
| Actual credential authenticity/permissions | UNVERIFIED / disabled | No real keys or authenticated endpoint used; no minimum-scope/withdrawal-permission assertion |
| Spot order construction | PASS offline only | Gate-approved exact Decimal BUY/limit drafts, constraints, 1x restriction; no transmitted order |
| Exchange validation of precision/requests/stops | UNVERIFIED / disabled | Conservative base-currency decimal check, no independently verified price tick or server stop lifecycle |
| Mock reconciliation, no blind retry | PASS for modeled states | Durable reservations/unknown/faults, mocked partial/full/no-fill terminal reports, mismatch and restart/concurrency tests |
| Partial cancellation / real balances / fee currency | UNVERIFIED / blocked | Ambiguous status quarantined; account model is explicitly internal synthetic data with quote-fee assumption |
| Real fill/risk/persistence execution bridge | NOT IMPLEMENTED / BLOCKED | Mock journal does not mutate paper state or implement real execution authority |
| No real/private/short execution | PASS | No private transport, disabled submit/cancel/modify, no order CLI, unchanged paper-only settings |
| Secret/Git hygiene and final diff | PASS | Existing exclusions/placeholders retained; staged index empty; no credentials/state files tracked; whitespace checked |
| Native Windows | UNVERIFIED | Linux only; exact PowerShell commands supplied |
| Real-market qualification | BLOCKED | No verified quote-liquidity/execution evidence; worker history rejected for zero volume |
| 24/7 deployment/capacity/physical failures | UNVERIFIED | No service installed, publication claim, soak or hardware-failure test |
| Phase 8 readiness | BLOCKED pending evidence and approval | Prerequisites below; no Phase 8 work performed |

Before any exchange-execution scope: independently qualify history, liquidity,
instrument minima/tick and fee assumptions; retain native Windows evidence if it
is the target; obtain separately approved read-only account/permission testing;
verify complete active-order/balance pagination and exact quantity/fee/cancellation
semantics; design/test an atomic global risk reservation/fill/account authority,
protective stops, unresolved-order investigation and trusted recovery evidence.
Do not clear latches or fabricate balances to pass these gates. Confirm officially
supported test facilities before relying on a sandbox. Review durable hosting,
backups, monitoring, clock and capacity separately. Approval is required before
Phase 8, and none of this enables live trading automatically.
