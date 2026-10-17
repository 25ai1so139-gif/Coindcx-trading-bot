# Phase 6A audit — restart-safe paper persistence

2026-10-17 (Asia/Kolkata date). Existing repository/branch preserved:
25ai1so139-gif/Coindcx-trading-bot, phase2-market-data.
Execution: Linux 6.18.55 x86_64, CPython 3.12.14, SQLite 3.53.1, existing .venv.

**Restart-safe persistence: PASS for the explicit PersistentPaperBroker API on
the tested Linux/local-SQLite configuration.** This is not a native Windows,
physical power-loss, real-market or continuous-operation certification.
**Phase 6B: BLOCKED / not implemented; separate approval required.**

## Scope and implementation evidence

Inspected the Phase 5 remediation report, actual config, risk/proposal/audit/
sizing/controls/entry/stops, PaperBroker and its histories, replay/manual interfaces,
tests, Git status and existing diff before editing. Baseline discovery passed all
354 enabled unit tests with one optional public-integration skip (355 total).

Added an explicit durable facade rather than rewriting working broker logic.
The old paper/backtest CLI replays and PaperBroker remain stateless independent
simulations; they do not gain recovery automatically. Future continuous code must
use this explicit API. No continuous loop, polling/service, new exchange transport,
private endpoint, credential request, real order, live/short enablement, commit
or push was implemented/performed.

New entry path:

1. PersistentPaperBroker.process_bar obtains BEGIN IMMEDIATE on the account file.
2. _read validates schema/metadata, full checkpoint history and financial/risk state.
3. The private candidate runs the unchanged PaperBroker.process_bar -> _open ->
   risk.entry.approve_entry -> whitelisted RiskAudit.record path.
4. Checkpoint, processed-candle key and head update occur in the same transaction.
5. Full revalidation runs before commit. A successful Update is returned only
   after commit; failure discards the candidate and blocks that handle.

Recovery in paper_trading/state.py restores a prior position only from a verified
committed checkpoint with matching approval, accounting and processed entry candle;
it is not a new entry or executable approval token. It does not increment counters
or charge fees again. No mutable recovered broker is exposed. Standalone pure
sizing/direct private entry protections remain unchanged and regression-tested.

## Per-requirement status

| Requirement | Status | Code and test evidence |
| --- | --- | --- |
| 1. Inspect existing implementation and audit | PASS | Actual files/interfaces inspected, pre-edit archive and full baseline; Phase 5 risk core retained |
| 2. Durable transactional storage | PASS | persistence.py uses SQLite DELETE journaling, synchronous=FULL, explicit transactions, foreign keys and closed per-operation connections |
| 3. Equity/P&L/position/candle/risk/history persistence | PASS | state.py strict canonical codec; exact state equality after a real child-process reopen and versus original broker across entry, hold, exit and finish |
| 4a. Atomicity across restart | PASS | Real process death before commit with a nonempty hot journal restores the exact previous snapshot; death after commit retains exactly one exit |
| 4b. Duplicate entry/candle prevention | PASS | Unique persisted candle keys and fresh transactional reads; identical/numerically equivalent duplicate is no-op without calling gate; changed candle rejects; two actual processes produce one entry |
| 4c. Corrupt/inconsistent/incompatible state rejected | PASS | Checksums/chain/head/schema/constraints plus independent accounting and history checks; rehashed cash, risk count, halt, missing trade/approval, invalid stop/equity/exit candle, trigger, missing tail, engine/config and malformed SQLite/JSON cases |
| 5. Existing gate authoritative; failure closed | PASS | Gate spy/rejected market/bare BUY/SHORT/repeated BUY tests; write/ack/logging/lock failures, reentrant callback and blocked/closed handles tested; original 86 central-risk tests pass |
| 6. Credentials excluded | PASS | Stored fields are whitelisted settings/account/candles/records; no raw proposal metadata/reason or credential environment reads; synthetic credential sentinel is absent from DB; secret exclusions remain intact |
| 7. Deterministic adversarial coverage | PASS | 57 persistence methods include actual subprocess termination/reopen, threads, two-process serialization and reconciliation; all data explicitly synthetic |
| 8. Migration and last-valid-state recovery | PASS | Validated schema-1 compatibility fixtures -> 2 without payload changes; exception/process-death DDL rollback; exact-checkpoint backup recovery; stale/mismatched/incomplete history rejects rather than inventing balances/trades |
| 9. Regression/adversarial suites and actual environment | PASS | Final discovery: 411 passed, 0 failed, 0 errors, 1 optional skip; 161 targeted and 57 persistence passed on Linux |
| 10. Schema/backup/failure/verification documentation | PASS | PHASE6A_PERSISTENCE.md, this report, README and VALIDATION include explicit API scope, commands and limitations |
| Native Windows execution | UNVERIFIED | No Windows runner executed this source; historical Phase 1 results do not extend to it |
| Real-market qualification | UNVERIFIED | No real history/liquidity/instrument/cost qualification was performed; synthetic storage tests establish none |
| Physical power cut, distributed filesystems and long-session capacity | UNVERIFIED | No hardware/multi-host/long-running throughput or retention claim |
| Phase 6B continuous engine | BLOCKED | Not built or authorized by this task; wait for approval |

The unchanged limits are initial equity INR 2000, margin-based sizing, at most 3x
leverage, 15m, initial planned-risk budget at most INR 10 (0.5% equity), INR 20
absolute risk ceiling, daily halt at lower of INR 40/2% daily starting equity,
three filled entries per UTC day, one open long and no short/live entries.
Existing default 5% observed drawdown and emergency/UTC reset rules are retained.
The durable API additionally requires paper mode and binds exact Settings to the
account; it rejects attempts to resume with different risk configuration.

## Test commands and exact counts

Executed from /workspace/Coindcx-trading-bot:

~~~bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m unittest tests.test_persistence -v
.venv/bin/python -m unittest tests.test_persistence tests.test_central_risk tests.test_risk -v
git diff --check
~~~

| Final/baseline run | Passed | Failed | Errors | Skipped | Total |
| --- | ---: | ---: | ---: | ---: | ---: |
| Pre-edit baseline | 354 | 0 | 0 | 1 | 355 |
| Final persistence | 57 | 0 | 0 | 0 | 57 |
| Final persistence + central risk + sizing/halts | 161 | 0 | 0 | 0 | 161 |
| Final full discovery | 411 | 0 | 0 | 1 | 412 |

All final command exits were 0. Final durations: 57 tests in 1.806s, 161 in
2.994s, 412 in 19.230s. Full-log groups: Phase 1 82, Phase 2 unit 69, Phase 3 54,
Phase 4 63, Phase 5 central gate 86, Phase 6A persistence 57, all passed. These
group counts are from discovery, not claims of separate per-phase invocations.

The sole skip is
integration.test_coindcx_public.PublicReadOnlyIntegration.test_discovery_and_recent_candles,
disabled unless COINDCX_RUN_PUBLIC_INTEGRATION=1. It was not enabled in Phase 6A:
local storage/restart verification needs no CoinDCX connectivity. No unit test
was skipped. Native Windows, actual power loss, real-market and continuous-loop
tests were not run, and no such result is claimed.

Development review also ran:

~~~bash
.venv/bin/python -m unittest tests.test_persistence.RecoveryAndAccountingTests.test_duplicate_bar_after_restart_is_noop_without_gate_call tests.test_persistence.CorruptionTests.test_incompatible_affinity_or_missing_constraints_reject_valid_looking_rows -v
~~~

Before the fixes this selected 2 methods and produced 2 failed schema subtests
and 1 duplicate-format error. These are three outcome records from two methods,
not three test methods. The numeric-equivalence and schema-constraint defects in
the new code were fixed and the affected tests plus full suite rerun. Review also
tightened exit-candle binding, recorded entry-equity reconciliation, closed-trade
modeled risk, reserved-name trigger detection and explicitly closed test DB handles.
No preexisting test/assertion or risk rule was removed or weakened.

Evidence is local: /tmp/coindcx-phase6a-baseline.log, persistence.log,
adversarial.log, full.log and review-reproduction.log (same full prefix for each).
Pre-edit snapshot: /tmp/coindcx-phase6a-before.zip. Phase-only diff:
/tmp/coindcx-phase6a-final.diff. These temporary artifacts are not published CI or
durable account recovery records.

## Backup/recovery and remaining limits

See the [storage guide](PHASE6A_PERSISTENCE.md) for the full schema and APIs.
SQLite rollback recovers the last committed transaction, not a fabricated account.
Logical corruption does not cause automatic fallback to an older checkpoint.
Explicit backup restore requires the independently known exact latest committed
Checkpoint and a new destination; the damaged primary is preserved. A stale
backup or unknown latest commit is BLOCKED, not an invitation to reset risk state.
The format-1 migration fixture is explicitly synthetic/unreleased; no deployed
legacy database or unsaved Phase 5 in-memory session is claimed recovered.

Integrity hashes are not signatures. An entirely valid older file can only be
detected across a fresh process with a trusted external checkpoint; callers must
retain that anchor. If an ambiguous write may have committed beyond the known
receipt and the primary is unreadable, recovery completeness is unknown and must
remain blocked. Do not substitute a backup's old receipt for latest-state evidence.
Committed emergency halts persist; a storage failure cannot promise durability
for an uncommitted halt request. The failed handle permits no further entry.

Use one local file for all writers of one account. Multi-host/network filesystem
correctness, external file replacement during writes and cryptographic anti-tamper
are not established. Full snapshots repeat history; long-session disk/validation
cost and retention/compaction remain unbenchmarked. Review operational capacity
before a continuous service; none was built here. Source-byte fingerprints are
strict, including line-ending changes, and unsupported engine changes fail closed.
Existing OHLC gap/stop-fill/execution-assumption limits remain. No profitability,
real-market liquidity or actual fee/leveraged-product qualification is inferred.

## Final diff and preservation

Nine paths change relative to the pre-edit snapshot:

| File | Change |
| --- | --- |
| paper_trading/persistence.py (new) | Explicit account API, SQLite transaction/identity/integrity protocol, backup/recovery/migration |
| paper_trading/state.py (new) | Typed credential-free snapshots and accounting/risk/history reconciliation |
| tests/test_persistence.py (new) | 57 deterministic synthetic restart/corruption/concurrency/migration tests |
| .gitignore | Local account/backup/receipt directory and SQLite sidecars |
| README.md | Explicit API scope and local verification commands |
| VALIDATION.md | Phase 6A evidence and scoped status |
| docs/PHASE6A_PERSISTENCE.md (new) | Schema, API, failure and recovery contract |
| docs/PHASE6A_AUDIT.md (new) | This audit |
| docs/PHASE5_REMEDIATION.md | Historical-scope pointer to the subsequent authorized work |

No existing file deleted/recreated/reset. All previous source/tests, risk limits,
broker/gate/strategy/CLI implementation, config, requirements, .env.example and
Windows workflow remain byte-identical to the audit-start snapshot. All earlier
untracked/uncommitted work is preserved. Nothing is staged. Git/added-file
whitespace and secret-path checks pass; .env.example still has blank values only.
No credentials/private-key paths are tracked or staged, no common real-key pattern
was found in current nonignored source. This is not an exhaustive Git-history scan.

## Native Windows PowerShell verification — instructions only

~~~powershell
Set-Location C:\path\to\Coindcx-trading-bot
py -3.12 --version
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-index -r requirements.txt
.\.venv\Scripts\python.exe -c "import platform, sqlite3, sys; print(platform.platform(), sys.version, sqlite3.sqlite_version); assert sys.platform == 'win32'; assert sys.version_info[:2] == (3, 12)"
if ($LASTEXITCODE -ne 0) { throw "Native Windows and Python 3.12 are required." }
Remove-Item Env:COINDCX_RUN_PUBLIC_INTEGRATION -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -m unittest tests.test_persistence -v
if ($LASTEXITCODE -ne 0) { throw "Persistence verification failed." }
.\.venv\Scripts\python.exe -m unittest tests.test_persistence tests.test_central_risk tests.test_risk -v
if ($LASTEXITCODE -ne 0) { throw "Adversarial verification failed." }
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw "Full regression failed." }
~~~

Record actual platform/counts before changing Windows status. Next: review this
Phase 6A implementation, retain independently qualified recovery evidence where
used, obtain native Windows/market evidence as appropriate and wait for separate
approval before Phase 6B. No continuous or real-money operation is authorized here.
