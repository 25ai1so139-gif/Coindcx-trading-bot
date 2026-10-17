# Phase 5 remediation — central risk gate audit

Historical Phase 5 scope. The subsequently authorized [Phase 6A audit](PHASE6A_AUDIT.md)
records the new explicit durable paper-account API. Its persistence evidence does
not certify a continuous loop, native Windows or real-market qualification.

## Final audit — 2026-10-17

This section supersedes the original remediation totals below. Audit environment:
Linux 6.18.55 x86_64, Python 3.12.14, existing .venv, branch phase2-market-data.
The repository already contained uncommitted Phase 2–5 work; it was preserved.

| Conclusion | Status | Scope |
| --- | --- | --- |
| Phase 5 central risk gate implementation | PASS | Supported current offline APIs, after the fixes below |
| Phase 5 adversarial verification | PASS | 86 deterministic central-risk tests and all regressions on Linux |
| Restart-safe persistence | UNVERIFIED | Not implemented/tested; explicitly a Phase 6 prerequisite |
| Native Windows verification | UNVERIFIED | Current source was not executed on Windows; historical Phase 1 CI is insufficient |
| Real-market qualification | UNVERIFIED | No independently qualified real history, liquidity or instrument/execution evidence |
| Phase 6 readiness | BLOCKED | Persistence/recovery, platform/market evidence and separate approval remain outstanding |

There is no overall operational PASS. No private CoinDCX request, API credential,
real order, live/short enablement, commit, push or Phase 6 implementation occurred.
The public-enabled suite used the existing unsigned read-only integration only;
passing discovery/recent-candle retrieval does not establish market eligibility.

### Requirement and configured-limit verification

PASS means implemented and tested within one offline broker/session. It is not
proof of real execution, authenticated operator metadata or crash recovery.

| Requirement | Status | Actual implementation and deterministic evidence |
| --- | --- | --- |
| Initial equity INR 2000; INR/margin sizing; 15m; backtest/paper only | PASS | config.py Settings validation is reconstructed in risk/entry.py approve_entry; gate additionally rejects other starting equity; config and central tests |
| One mandatory approval on every supported entry path | PASS | Sole position creation is PaperBroker._open after approve_entry; raw BUY, private open, bare plan, old approval, direct replay and both CLI simulations covered in BrokerBoundaryTests/ReplayAndCommandBoundaryTests |
| Invalid, incomplete, duplicate, unordered, missing or future candles | PASS | validate_history/Candle and broker current-candle revalidation; MarketAndSignalGateTests plus Phase 2/3 tests |
| Stale market data | PASS | Most recent completed close must be within configured staleness, at most 30 minutes, against explicit replay/review clock; below/equal/above boundary and stricter policy tested |
| Missing/invalid stop and already-breached entry reference | PASS | validate_decision enforces protective configured analytical stop; gate independently checks modeled execution stop and fees; zero/nonprotective/wrong-distance and gap tests |
| INR 10 initial budget, INR 20 absolute ceiling | PASS | At most 0.5% of current equity, configured absolute cap no greater than 20 and remaining daily/drawdown headroom; below/equal/above 10 and 20 and fees causing breach tested; 20 boundary uses explicitly synthetic INR 4000 equity |
| Maximum 3x leverage and margin/notional distinction | PASS | Reconstructed Settings plus instrument limit/symbol, independent quantity/notional/margin checks; damaged 4x rejects; INR 100 margin at 3x gives INR 300 exposure in synthetic test |
| Margin affordability, 25% default equity cap and instrument constraints | PASS | size_position plus independent gate reconstruction; minimums never cause rounding up; new default/0.3/0.03, exact minimum and unrepresentable precision tests |
| Daily halt at lower of INR 40 or 2% of applicable daily start | PASS | RiskControls.daily_loss_budget, current threshold and latch reviewed centrally; equality, recovery, remaining headroom, lower-equity and overnight-gap cases tested |
| Maximum three filled entries per UTC day | PASS | Counter advances only on approved fill, fourth rejects; UTC rollover resets daily counter/halt only, retains overnight loss basis; no implicit day reset at approval |
| One open position | PASS | Central current-position check and serialized broker operations; repeated/concurrent BUY and private attempts tested |
| Emergency halt and drawdown halt | PASS | Current/latching checks and existing protective/cleanup exits; default 5% observed-equity drawdown, recovery/next-day persistence and emergency re-entry tests |
| Stronger configured limits remain stronger | PASS | New risk-percentage, absolute-risk, daily-percentage, daily-amount and one-entry tests; none raised to hard ceilings |
| Eligible matching market and required costs/instrument details | PASS | Missing/ineligible/mismatched/unreviewed inputs reject; historical path permits reviewed 1x spot only; synthetic context is explicitly abstract and never real liquidity evidence |
| SHORT cannot open a position; manual/verify submit zero orders | PASS | SHORT centrally rejects, SELL may exit a long; manual aliases call read-only gate with broker construction and socket access forbidden in tests |
| UTC decision records and modeled risk/cost/exposure fields | PASS | risk/audit.py whitelists fields, adds effective_leverage; missing values null, secret sentinel/overflow/backend failure tests; JSON/CSV export tests |
| Callback/concurrent entry consistency | PASS | Nested process_bar is rejected before candle/day changes; guard always released; emergency during logging still prevents commit; 4 new callback/failure tests plus existing concurrency test |
| Session halt lifetime and explicit reset rules | PASS | Daily halt/count reset only on next observed UTC day; drawdown/emergency stay latched for broker lifetime; independent simulations deliberately start new sessions |
| Restart-safe account/counter/halt/audit recovery | UNVERIFIED | No durable store or recovery tests; no resume behavior claimed |
| Secrets and live execution exclusions | PASS | .env variants/private-key/credential paths ignored, .env.example blank values only; no sensitive paths tracked, nothing staged, safety tests pass; scan limitations below |
| Complete available regression suite | PASS | 355 passed, zero failures/errors/skips with optional public integration enabled |
| Current native Windows execution | UNVERIFIED | Linux only; exact PowerShell commands retained below |
| Authentic real history, liquidity and executable instrument assumptions | UNVERIFIED | Passing historical-labelled stand-ins and public smoke test is not independent qualification |

### Entry-path trace and proof boundary

1. CLI backtest/paper -> load_eligible -> simulate -> PaperBroker.process_bar ->
   _open -> approve_entry -> RiskAudit.record -> record_entry -> reserve cash and
   create Position. Historical direct simulate has no synthetic fallback.
2. CLI evaluate -> run_experiment -> baseline/cost-stress/development scenarios ->
   the same simulate path. Dataset identity/context is propagated to each replay.
3. Direct broker BUY follows the same _open. _open requires the current validated
   execution candle and reference; a direct call cannot establish that context.
   The position property is read-only. A constructed PositionPlan/Position or
   prior RiskDecision is not accepted as entry permission.
4. Manual/verify -> verify_file -> the same read-only approve_entry; they have no
   broker, order transport or execution call. Early data/config rejection logs a
   rejection and cannot reach a fill.
5. Legacy entry_plan is a context/audit-requiring wrapper around approve_entry;
   missing rich input rejects. size_position only returns arithmetic, and cannot
   mutate broker/account state or authorize an order.

Search of all production Python code found one non-null _position assignment,
in broker._open, after mandatory approval. Other assignments initialize/close it.
Existing gate-spy, rejected-context, direct-call, concurrency, plan-injection and
zero-order tests exercise these boundaries. Buy-and-hold benchmark arithmetic is
explicitly an unconstrained descriptive reference; it creates no broker position
and must not be read as risk-approved execution. No future continuous engine was
built or certified. Future entry paths must use this boundary and be retested.

This is supported-API enforcement, not protection from arbitrary Python memory
mutation, replacing functions/subclasses, forged operator attestations or another
independent process. Locks/counters belong to one broker instance. No stronger
non-bypass, authenticated-market or cross-process guarantee is claimed.

### Confirmed findings, fixes and the two removed sizing lines

1. Logging reentrancy: a logging callback could call process_bar(HOLD) for a later
   UTC day while approval was being logged. The outer entry then changed cash and
   position before failing on backwards risk observation. Two new tests failed
   against the pre-fix broker. paper_trading/broker.py now guards the entire bar
   operation against reentrancy while holding the existing lock. The guard resets
   in finally; ordinary later calls still work after logger failure. Emergency
   shutdown remains available during approval and record_entry prevents a fill
   when that callback latches it. An approval log remains a review, not a fill.
2. Sizing precision: division with / could round a lot count before ROUND_DOWN.
   An INR 2 margin/INR 1 price proposal with a lot just larger than 2 returned an
   invalid two-unit quantity; an extremely fine step also returned a rounded lot
   count. Two new tests reproduced this before the fix. The existing independent
   gate checked step integrity; this was an unsafe calculator result, not a proven
   accepted-order bypass. risk/sizing.py now uses Decimal integer division and
   checks the rounded quantity against its maximum and exact step. Unrepresentable
   integer counts fail closed; the gate logs POSITION_SIZING_UNAVAILABLE.
3. Audit clarity: the existing leverage field represented notional/margin, not
   exposure/account equity. risk/audit.py now additionally records
   effective_leverage = proposed notional / current equity, before entry costs.
   Missing plan or nonpositive/invalid equity produces null. The synthetic 3x,
   INR 100 margin, INR 2000 equity test expects leverage 3 and exposure ratio 0.15.
4. Empty audit export: risk_decisions.csv repeated symbol and data_kind in its
   header when no decisions existed (33 columns, 31 unique). The new empty-export
   assertion failed before the fix. backtesting/reporting.py now adds only field
   names not already supplied by the report labels. Nonempty records, empty schema
   uniqueness and the added effective_leverage column are tested together.

The old signature and fixed eight-decimal quantize line are visible replacements
in the available risk/sizing.py diff against HEAD: optional instrument step/minimum
parameters and step-based rounding replace them. No risk budget, remaining-budget
cap, margin affordability or leverage control was deleted. CostModel/stop-precision
guards visible against HEAD were already present at this audit's start and remain.
The prior report's /tmp/coindcx-phase5-remediation-before.zip is unavailable in
this environment, so exact historical attribution to a two-line phase-only diff
is UNVERIFIED. This audit compared HEAD, actual current code and the newly saved
audit-start snapshot, rather than claiming to have recovered that old archive.
The audit fixes the step calculation as above. Default step remains 0.00000001;
numeric default sizing and non-power-of-ten steps pass. Decimal trailing-zero
serialization is not identical to old quantize; callers should parse values as
decimals rather than require padded text. An interim new test incorrectly assumed
identical zero padding; its numeric compatibility assertion was retained and the
formatting assumption corrected. No pre-audit assertion was removed or disabled.

### Persistence contract and remaining blockers

The original Phase 5 Task 4 requires "Persistent halt state during the configured
trading session" and "Explicit reset conditions and audit logging." The original
Phase 6 Task 3 separately requires transactional persistence, duplicate prevention
after restart and corruption detection/fail-closed recovery. Therefore this audit
keeps the implemented session latches, UTC daily reset and explicit independent
simulation boundary; it does not add a Phase 6 state store. Read-only risk-state
JSON and completed CSV/JSON reports are not restart recovery.

Remaining work before claiming continuous-operation readiness:

- Obtain separate approval and recheck the Phase 6 gate; do not start it here.
- Implement transactional account/open-position/counter/halt/processed-candle
  persistence, recovery validation and cross-process ownership in the authorized
  Phase 6 scope. Prove restart, duplicate prevention, corruption and interrupted
  writes with tests before claiming recovery.
- Execute the current checkout on native Windows/Python 3.12 and retain results;
  no Windows execution or Windows-specific filesystem/locking proof exists here.
- Independently qualify real historical data/liquidity and matching instrument,
  precision/minimums, costs and execution model. Public recent candles alone do
  not qualify these. Real leverage/funding/borrow/liquidation remain unsupported.
- Retain OHLC-model limitations: adverse gaps may exceed planned loss/daily
  thresholds, no guarantee of a real stop fill, no order book/partial fills/latency
  model, and observed drawdown is not authenticated tick-by-tick high-water truth.
- Session logs may be unavailable if a logging backend itself raises; entry then
  aborts before money changes. No durable audit or crash atomicity is claimed.
- Historical phase-only diff provenance cannot be independently reconstructed
  without the previous temporary archive. Current safety behavior and this audit's
  eight-file diff are independently inspected/tested. External strict consumers
  of audit schemas/Decimal text have not been tested against the additive field.

### Exact final-audit test commands and results

Executed from /workspace/Coindcx-trading-bot; output redirected to the local logs
listed below. Baseline and final default discovery use the same first command.

~~~bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m unittest tests.test_central_risk.BrokerBoundaryTests -v
.venv/bin/python -m unittest tests.test_central_risk tests.test_risk -v
.venv/bin/python -m unittest tests.test_central_risk -v
COINDCX_RUN_PUBLIC_INTEGRATION=1 .venv/bin/python -m unittest discover -s tests -v
git diff --check
~~~

| Run | Passed | Failed | Errors | Skipped | Total |
| --- | ---: | ---: | ---: | ---: | ---: |
| Audit baseline | 343 | 0 | 0 | 1 | 344 |
| Callback reproductions before fix | 0 | 2 | 0 | 0 | 2 |
| Sizing reproductions before fix | 0 | 2 | 0 | 0 | 2 |
| Empty audit CSV reproduction before fix | 0 | 1 | 0 | 0 | 1 |
| Broker boundary group after callback fix | 24 | 0 | 0 | 0 | 24 |
| Central-risk plus sizing/halt regressions | 104 | 0 | 0 | 0 | 104 |
| Final central-risk module | 86 | 0 | 0 | 0 | 86 |
| Final default full discovery | 354 | 0 | 0 | 1 | 355 |
| Final public-enabled full discovery | 355 | 0 | 0 | 0 | 355 |

Phase 1/2/3/4 groups in final full discovery passed 82/69/54/63 tests respectively;
these counts are extracted from the full log, not separate group commands in this
final audit. The 86 gate tests add 11 methods to the prior 75. Existing assertions
and strategy parameters remain. Reproductions used these exact commands:

~~~bash
.venv/bin/python -m unittest tests.test_central_risk.BrokerBoundaryTests.test_logging_callback_cannot_advance_account_day_during_approval tests.test_central_risk.BrokerBoundaryTests.test_handled_nested_bar_rejection_preserves_outer_entry_context -v
.venv/bin/python -m unittest tests.test_central_risk.AccountAndSizingGateTests.test_lot_division_cannot_round_a_subminimum_quantity_up tests.test_central_risk.AccountAndSizingGateTests.test_unrepresentable_lot_count_rejects_instead_of_rounding -v
.venv/bin/python -m unittest tests.test_central_risk.ReplayAndCommandBoundaryTests.test_reporting_exports_approval_and_rejection_audit_csv -v
~~~

The only default skip is
integration.test_coindcx_public.PublicReadOnlyIntegration.test_discovery_and_recent_candles;
it passed with COINDCX_RUN_PUBLIC_INTEGRATION=1. No available test was left unrun
in enabled discovery. All final commands exited 0; pre-fix reproductions exited 1.
No native Windows, restart recovery or real-market qualification test was run;
no such result is claimed. All fabricated fixtures retain synthetic labels.

Local logs use /tmp/coindcx-phase5-final- plus baseline.log, reproduction.log,
sizing-reproduction.log, csv-reproduction.log, broker.log, adversarial.log,
central.log, offline.log and complete.log. Audit-start archive:
/tmp/coindcx-phase5-final-before.zip.
Phase-only final diff: /tmp/coindcx-phase5-final.diff. These /tmp artifacts are
local evidence, not repository-published durable recovery or CI records.

### Final diff and secret exclusions

This audit changes eight files: paper_trading/broker.py (bar guard), risk/sizing.py
(safe lot calculation), risk/audit.py (exposure field), tests/test_central_risk.py
(11 methods and expanded CSV schema assertions), backtesting/reporting.py (unique
empty audit headers), README.md, VALIDATION.md and this report. No existing file
is deleted. config.py, risk/proposal.py, risk/entry.py,
RiskControls, stops, account snapshot validation, strategy algorithms, dependencies,
.env.example and .gitignore are unchanged from audit start. Earlier uncommitted
and untracked work is preserved; HEAD includes older phases and is not the audit
diff baseline. git diff --check passes. Nothing is staged.

Git path checks found no tracked .env/private-key/credential paths. .env.example
contains variable names with empty values only. Representative .env, .env.local,
.env.production, secrets/demo.json, credentials.json, sample.key and sample.pem
paths are ignored. No common real-key/private-key pattern was found in current
nonignored source files; this is not a proof about arbitrary credentials or all
historical Git objects. No credential environment values were read or logged.

Exact Windows PowerShell setup/test commands are retained at the end of this
report. They are instructions only, not evidence of Windows execution.

## Original remediation record — historical evidence

The following 344-test/75-new-method results predate this final audit. They are
retained for comparison; the current 355-test/86-method results above supersede
their totals and current-status conclusions.

2026-10-17. Existing repository: 25ai1so139-gif/Coindcx-trading-bot,
branch phase2-market-data. Linux 6.18.55 x86_64, Python 3.12.14, existing .venv.

**PASS: implemented central approval and current offline entry boundaries.**
**BLOCKED: actual real-market qualification and native Windows verification.**
This specifically authorized remediation supersedes the earlier code-missing
finding. It does not clear real-data readiness or authorize Phase 6. No private
request, secret request, real order, live/short enablement, commit or push.

## Per-requirement results

| Requirement | Status | Code/test evidence |
| --- | --- | --- |
| 1. Inspect actual Phase 5 state and prior interfaces/tests | PASS | Read Phase 1–4 audit evidence and Phase 5/6 Gate 0 records; traced actual risk, broker, data, strategy, replay, CLI and reporting paths; reran baseline before edits |
| 2. Correct shared approval interface | PASS | risk/entry.py approve_entry takes proposal/market/cost/instrument evidence, completed history, execution clock and current account; returns RiskDecision and mandatory RiskRecord |
| 3. Mandatory integration on every supported entry | PASS | PaperBroker._open is the sole position creation; it always calls approve_entry. Replay, both simulation CLI modes and broker-free manual aliases are tested with gate spies |
| 4a. Invalid/stale/incomplete market data | PASS | Revalidation, minimum history, UTC completion/freshness, finite coherent OHLCV, duplicate/order/gap checks; invalid current broker bars reject before money mutation |
| 4b. Missing/invalid stop | PASS | Validated enriched signal requires protective configured stop and correct last-close timestamp; next-open reference at/below the analytical stop also rejects |
| 4c. Planned risk above allowed amount | PASS | Percentage/absolute/remaining-budget sizing plus independent loss reconstruction from modeled fills and both fees; below/equal/above INR 10 and INR 20 tested |
| 4d. Leverage above 3x | PASS | Settings reconstructed at approval, maximum instrument leverage bounded at 3, instrument-symbol binding and margin/notional relationship checked |
| 4e. Unsafe margin/position sizing | PASS | Finite positive plan, affordability, correct notional, step multiples/minimums, down-only rounding; never increase quantity/risk to meet a minimum |
| 4f. Daily loss halt | PASS | Shared RiskControls, current threshold and latched state checked; lower of INR 40/2% of daily starting equity and remaining drawdown/daily headroom |
| 4g. Three entries already filled today | PASS | Filled-entry counter only after approval; fourth attempt rejects; UTC rollover and no implicit gate reset tested |
| 4h. One open position | PASS | Repeated BUY rejected/audited, read-only position property and in-instance serialization; duplicate concurrent calls tested |
| 4i. Emergency/drawdown halt | PASS | Current/latched breach rejects, old approvals cannot re-enter, existing emergency flattening/protective exits remain available |
| 4j. Ineligible symbol/market | PASS | Signal/context symbol, timeframe/INR, eligibility, real quality/liquidity review and instrument symbol checked; synthetic data never qualifies real liquidity |
| 4k. Missing fee/slippage or instrument information | PASS | Explicit rates must match Settings; missing, unverified, mismatched or unsupported details reject |
| 5. Fixed protection limits | PASS | Entry requires initial INR 2000, risk percentage at most 0.5% (INR 10 initially, INR 20 absolute), daily percentage at most 2%/INR 40, at most three entries, one long, leverage at most 3; defaults/core halt/reset logic preserved |
| 6. Lower-level API bypass prevention | PASS | Bare BUY, direct/private _open, bare PositionPlan, old entry_plan, reused approvals and ineligible direct simulate calls tested; private open additionally requires the current validated execution bar |
| 7. UTC decision logging without credentials | PASS | Structured whitelisted RiskRecord in session/standard logger/returned JSON and report CSV; no raw metadata or exception payloads; logging failure prevents entry |
| 8. Adversarial tests and prior regressions | PASS | 75 new methods; all existing module groups rerun; one old unsafe-budget expectation corrected explicitly below |
| 9. Full suite and platform reporting | PASS | Final enabled suite: 344 passed, 0 failed, 0 errors, 0 skipped on Linux; default suite 343 passed, 1 optional skip |
| 10. Diff/preservation/unverified behavior | PASS | Pre-edit archive comparison includes untracked work; no preexisting file deleted, no assertion disabled, secret exclusions/template/dependencies preserved; limits below |
| Actual historical/instrument/cost authenticity | BLOCKED | No real dataset or independently verified instrument was qualified; no real-market performance inferred |
| Native Windows execution | BLOCKED | Linux only; exact local commands below, no earlier Phase 1 CI extrapolation |

PASS for bypass prevention covers supported APIs, not hostile Python code that
replaces functions, writes private fields or fabricates metadata/account truth.

## Implementation and deliberate behavior changes

The previous entry_plan accepted only equity/price/account state. It could not
centrally validate a signal, explicit stop, freshness, eligibility or instrument
assumptions. Tracing the old broker showed raw BUY/private open could reach
position creation without those inputs. Passing older tests did not prove this
stronger contract.

The new read-only account review is:

```python
approval = approve_entry(
    settings, controls, equity, proposal,
    at=evaluation_time, has_open_position=has_position, audit=audit,
)
```

EntryProposal contains strategy, StrategyDecision, sufficient completed prior
candles, MarketContext and actual proposed reference price. MarketContext carries
symbol/timeframe/INR, kind, eligibility/review, freshness, InstrumentSpec and
CostAssumptions. InstrumentSpec binds the symbol and includes product, quantity
step, quantity/notional minimums, leverage maximum and reviewed/verified flag.
CostAssumptions explicitly declares the per-leg fee/slippage rates. Missing
context rejects; no rejection exposes an executable plan.

PaperBroker.process_bar requires entry=EntryProposal for a BUY. Its _open calls
the central function immediately before record_entry, margin/fee reservation
and the only Position creation. Direct _open cannot establish a validated
execution-bar context. The position property is read-only; operations on the
same instance are serialized and reentrant entry callbacks reject. A prior
approval or bare sizing object is never a fill token. The old entry_plan name
is a context-requiring review wrapper. Pure sizing and benchmark arithmetic
do not create positions or grant execution permission.

Replay adapts legacy Signal strategies into enriched proposals while preserving
their small indicator window; the gate receives enough completed prior history.
Rich decisions remain validated before becoming pending actions. Invalid rich
results are audited and trigger existing emergency cleanup. Next-open execution
and final-bar no-fill behavior remain. SHORT exits a long only; flat SHORT
attempts reject centrally. Manual/verify use the same gate for previews, construct
no broker and submit zero orders. Invalid manual configuration is also audited.

The Phase 2 assessment attaches reviewed risk context; historical MarketData
passed directly to simulate never receives synthetic fallback. Explicit synthetic
MarketData is a numerical fixture using an abstract context, never real eligibility.
Chronological periods propagate context and declare hypothetical sensitivity costs.

The following tighter entry rules were explained before application:

- Initial capital must be INR 2000; risk percentage may be lowered but not exceed
  0.5%; daily percentage may be lowered but not exceed 2%.
- Initial planned budget is at most INR 10; equity growth may increase it only
  up to INR 20. Small positions are never enlarged to force INR 10 risk.
- The INR 40 daily ceiling, three entries per observed UTC day, one long,
  maximum 3x, default 5% drawdown and existing emergency/reset rules remain.

Settings still parses broader legacy values and size_position remains a pure
calculator; such values no longer grant entry permission. One old manual test
expecting INR 20 starting risk from a 2% override was changed to require rejection.
The INR 20 gate boundary now uses explicitly synthetic grown equity INR 4000
at the unchanged 0.5% rate. Original standalone calculator tests are retained.

The execution stop retains the existing configured distance from adverse entry
fill; the analytical stop is separately validated and may not already be breached.
Both references and modeled stop fill are logged. Carried-position gaps still
exit at the worse available open with costs; losses are never clipped to budgets.
Exit helpers validate current-candle price/time before cash mutation. None of
these models guarantees a real exit price or realized loss cap.

## Logging and remaining trust boundaries

RiskRecord includes UTC time, outcome/reason, symbol/strategy, signal time/kind;
analytical entry/stop and modeled fill/stop; planned/permitted risk, margin,
notional, leverage, estimated fees/slippage; equity, daily start/budget/count and
halt flags. Unavailable values are null. A rejected calculated plan may appear
in the audit for diagnosis but is never returned for execution.

Records appear in SimulationResult.risk_decisions, manual JSON and chronological
risk_decisions.csv. Standard logger coindcx.risk emits INFO; returned records do
not depend on configuring an INFO handler. A backend logging exception blocks
entry before money mutation. Raw exception messages, metadata and credential
environment values are not audit payloads. Approval is a review, not proof of
a fill: interruption may abort execution, and manual approval never fills.

Remaining limitations:

1. Real quality/liquidity and instrument verified flags remain operator
   attestations, not authenticated exchange truth. Actual real-market qualification
   remains BLOCKED. Historical entry approval supports reviewed 1x spot only;
   real leveraged/margin/derivatives models remain rejected.
2. Synthetic 3x/fees/slippage are explicit abstract assumptions, not verified
   CoinDCX schedules. Funding, borrow, liquidation, tax, book depth, partial fills
   and latency are unsupported. Stops/daily thresholds can be exceeded by gaps.
3. Freshness uses the explicit replay clock for historical work, not current
   market freshness. Broker processing requires completed execution candles;
   it is not a continuous real-time service. OHLC tick order/high-water precision
   and observed drawdown remain limited as documented in Phase 4.
4. State/audits are per in-memory session or completed report exports. Locks
   cover one broker instance, not multiple processes. New processes/independent
   brokers do not share counters; forced termination, mid-mutation interruption,
   durable recovery and cross-process truth are not established.
5. Snapshots and local metadata can be false; this gate is not a sandbox against
   arbitrary Python mutation/monkeypatching or deliberate data mislabelling.
6. No current native Windows run, real-market out-of-sample result, profitability
   conclusion, hosting or Phase 6 readiness is claimed. Review and approve
   separately before Phase 6; recheck its prerequisites rather than assuming them.

## Files changed relative to this remediation's start

| Paths | Purpose |
| --- | --- |
| risk/entry.py | Mandatory approval and protective compatibility wrapper |
| risk/proposal.py; risk/audit.py (new) | Explicit evidence/request types and whitelisted decision records |
| risk/sizing.py | Optional instrument step/minimums, down-only quantity |
| paper_trading/broker.py | Sole-entry gate, validated execution context, read-only position, serialization, guarded exits |
| backtesting/engine.py | Proposals/history/next-open references, malformed decision audit, returned records |
| backtesting/datasets.py; backtesting/experiment.py | Reviewed context and declared cost sensitivity propagation |
| backtesting/reporting.py | Risk-decision CSV and dataset identity labels |
| strategies/verification.py; cli.py | Same gate for previews, propagation and invalid-config audit |
| tests/test_central_risk.py (new) | 75 deterministic adversarial methods |
| tests/helpers.py; tests/test_broker.py; tests/test_backtesting.py | Explicit synthetic proposals for original broker assertions |
| tests/test_signal_verification.py | Rejection of now-forbidden larger starting risk |
| README.md; VALIDATION.md; docs/PHASE5_REMEDIATION.md | Current contract, evidence, instructions and limits |
| docs/PHASE5_GATE0.md; docs/PHASE6_GATE0.md; docs/PHASE4_BACKTESTING.md | Historical-record pointers; original evidence retained |

config.py, RiskControls, risk/context.py, stops.py, strategy/base algorithms,
.gitignore, .env.example and requirements.txt are unchanged. Earlier uncommitted
and untracked work was preserved. No existing file was deleted or reset. Phase
attribution uses /tmp/coindcx-phase5-remediation-before.zip, not HEAD alone.
git diff --check and repository hygiene pass; nothing staged. Current nonignored
working-file scans found no common API-key/private-key patterns; this is not an
exhaustive history scan. Environment example values remain blank.

## Exact commands and test evidence

Executed from /workspace/Coindcx-trading-bot on Linux:

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m unittest tests.test_central_risk -v
.venv/bin/python -m unittest tests.test_config tests.test_risk tests.test_broker tests.test_data tests.test_engine_cli tests.test_repository_safety tests.test_strategies -v
.venv/bin/python -m unittest tests.test_data_pipeline tests.test_market_quality tests.test_public_market_data -v
.venv/bin/python -m unittest tests.test_strategy_engine tests.test_signal_verification -v
.venv/bin/python -m unittest tests.test_backtesting tests.test_chronological_evaluation -v
COINDCX_RUN_PUBLIC_INTEGRATION=1 .venv/bin/python -m unittest discover -s tests -v
git diff --check
```

| Run | Passed | Failed | Errors | Skipped | Total |
| --- | ---: | ---: | ---: | ---: | ---: |
| Baseline before remediation | 268 | 0 | 0 | 1 | 269 |
| New gate module | 75 | 0 | 0 | 0 | 75 |
| Phase 1 group | 82 | 0 | 0 | 0 | 82 |
| Phase 2 unit group | 69 | 0 | 0 | 0 | 69 |
| Phase 3 group with stated policy correction | 54 | 0 | 0 | 0 | 54 |
| Phase 4 group | 63 | 0 | 0 | 0 | 63 |
| Final default full discovery | 343 | 0 | 0 | 1 | 344 |
| Final enabled full discovery | 344 | 0 | 0 | 0 | 344 |

All exits 0. Final outputs: Ran 344 tests in 20.704s / OK with integration;
Ran 344 tests in 18.954s / OK (skipped=1) by default. The final run includes the
last instrument-symbol check and all 75 new methods. No assertion was disabled.
The default skip is exactly
integration.test_coindcx_public.PublicReadOnlyIntegration.test_discovery_and_recent_candles;
it actually passed in enabled discovery using unsigned public GETs. No available
test was skipped in that enabled run. Native Windows and actual market/instrument
qualification were not run; no future Phase 6 test or feature is claimed.

Adversarial cases cover every listed rejection, signal/time/stop boundaries,
rounding/minimums, below/equal/above INR 10 and 20, fees causing breach, current
and latched halts, UTC reset/no implicit reset, third/fourth/repeated entry,
emergency re-entry, old approvals, direct/private/simulation bypass attempts,
pure-plan injection, concurrent duplicate bars, logging failure/overflow/secret
sentinel, isolated Decimal precision, both CLI simulations, broker-free manual
aliases, malformed rich decisions and CSV. Historical-labelled stand-ins are
explicitly fabricated fixtures, never qualification or market performance.

Local evidence logs under /tmp all use prefix coindcx-phase5-remediation-:
baseline.log, adversarial.log, phase1.log, phase2.log, phase3.log, phase4.log,
offline.log and complete.log. Phase-only diff: final.diff with that prefix.
No known failing tests remain.

Actual additional smoke checks generated 240 labelled synthetic candles and a
labelled fabricated account snapshot, then ran backtest, paper, manual and verify.
All exited 0 and exposed decision records; manual/verify returned NO_TRADE and
zero orders. These do not establish performance. Exact example commands:

```bash
BOT_MIN_HISTORY_BARS=200 .venv/bin/python -m cli backtest --data data/local/phase5-remediation.synthetic.csv --strategy sma_cross --allow-synthetic
BOT_MIN_HISTORY_BARS=200 .venv/bin/python -m cli paper --data data/local/phase5-remediation.synthetic.csv --strategy momentum --lookback 1 --threshold 0.001 --leverage 3 --allow-synthetic
BOT_MIN_HISTORY_BARS=200 .venv/bin/python -m cli manual --data data/local/phase5-remediation.synthetic.csv --strategy momentum --lookback 1 --threshold 0.001 --as-of 2024-01-03T12:00:00Z --risk-state /tmp/coindcx-phase5-remediation-account.synthetic.json --allow-synthetic
BOT_MIN_HISTORY_BARS=200 .venv/bin/python -m cli verify --data data/local/phase5-remediation.synthetic.csv --strategy momentum --lookback 1 --threshold 0.001 --as-of 2024-01-03T12:00:00Z --risk-state /tmp/coindcx-phase5-remediation-account.synthetic.json --allow-synthetic
```

Outputs are /tmp/coindcx-phase5-remediation-backtest.json, paper.json, manual.json
and verify.json (same prefix for each). No real return/win-rate claim is made.

## Windows PowerShell verification and next steps

Instructions only; not executed on Windows. Install Git and Python 3.12 and use
the actual audited files:

```powershell
Set-Location C:\path\to\Coindcx-trading-bot
git --version
py -3.12 --version
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-index -r requirements.txt
.\.venv\Scripts\python.exe -c "import platform, sys; print(platform.platform()); assert sys.platform == 'win32'; assert sys.version_info[:2] == (3, 12)"
if ($LASTEXITCODE -ne 0) { throw "Native Windows and Python 3.12 are required." }
Remove-Item Env:COINDCX_RUN_PUBLIC_INTEGRATION -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -m unittest tests.test_central_risk -v
if ($LASTEXITCODE -ne 0) { throw "Central risk tests failed." }
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw "Full regression failed." }
```

Optional complete suite with only public read-only integration:

```powershell
$env:COINDCX_RUN_PUBLIC_INTEGRATION = "1"
try {
    .\.venv\Scripts\python.exe -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) { throw "Complete verification failed; inspect output." }
} finally {
    Remove-Item Env:COINDCX_RUN_PUBLIC_INTEGRATION -ErrorAction SilentlyContinue
}
```

No secrets, .env loading or third-party download is needed. Next: verify on
native Windows, obtain qualified real data/instrument evidence where needed,
review this remediation, and wait for separate approval before Phase 6. No
continuous loop, restart recovery, paper start/status/stop or Phase 7 work was
implemented.
