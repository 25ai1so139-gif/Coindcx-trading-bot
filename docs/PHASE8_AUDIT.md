# Phase 8 final validation and live-readiness audit

2026-10-17 UTC. Existing repository/branch retained: Coindcx-trading-bot,
phase2-market-data, HEAD acde254c37b8f2f0fc84da00bd0a0012e2595cca. These results
describe the inherited working tree plus the six paths listed below, not a
published commit. Execution environment: **Linux 6.18.55 x86_64/glibc 2.41,
CPython 3.12.14, SQLite 3.53.1**, existing .venv, standard library only.

**Offline safety/regressions: PASS. Public safe rejection and bounded recovery:
PASS within the measured scope. Genuine historical performance, qualified
real-data paper fills and current native Windows execution: UNVERIFIED.
Readiness for any limited live test: BLOCKED. No overall operational PASS.**

No private endpoint, real credential, real submission/cancellation/modification,
live or short enablement, parameter optimization, commit/push, indefinite service
or Phase 9 work occurred. No profitability conclusion follows from these tests.

## Gate 0 and evidence boundary

Reviewed the existing Phase 1 validation/Windows record; Phase 2/3/4 audits;
Phase 5 gate/remediation; Phase 6 gate, 6A persistence and 6B worker audits;
Phase 7 audit/readiness and public evidence. Checked actual configuration, CLI,
public pipeline/schema/quality/cache, both strategies and verification, risk
gate/sizing/controls/stops/audit, simulation/evaluation/reporting, broker/state/
SQLite/session/worker and exchange/auth/instrument/order/mock journal code.
Historical reports are not substituted for current test execution.

The Gate 0 baseline completed 578 tests: 577 passed, 0 failed, 0 errors, 1 optional
public skip. The final enabled run actually executed that public test. Required
offline controls passed; missing market, platform and real exchange evidence
still block operational readiness. Phase 8 auditing did not enable those paths.

The root PHASE1_AUDIT.md and VALIDATION.md retain the foundation results;
all 82 current Phase 1-group tests passed. Earlier Windows evidence covers an
old Phase 1 commit and 81 tests, not this 584-test tree. Phase 2's old proxy/host limitation was superseded in
later phases; this audit independently reached the current official site and
public GET client. No required safety success is inferred from publication.

## Exact test commands and counts

Commands executed from /workspace/Coindcx-trading-bot:

~~~bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m unittest tests.test_continuous_paper.Phase8AcceptanceTests -v
.venv/bin/python -m unittest tests.test_exchange_adapter tests.test_order_reconciliation tests.test_continuous_paper tests.test_persistence tests.test_central_risk tests.test_risk -v
COINDCX_RUN_PUBLIC_INTEGRATION=1 .venv/bin/python -m unittest discover -s tests -v
git diff --check
~~~

| Completed run | Passed | Failed | Errors | Skipped | Total | Seconds |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Gate 0 full default baseline | 577 | 0 | 0 | 1 | 578 | 23.315 |
| Six new synthetic acceptance tests | 6 | 0 | 0 | 0 | 6 | 0.571 |
| Final combined safety/adversarial group | 333 | 0 | 0 | 0 | 333 | 10.913 |
| Final full public-enabled discovery | 584 | 0 | 0 | 0 | 584 | 23.168 |

The sole baseline skip was
integration.test_coindcx_public.PublicReadOnlyIntegration.test_discovery_and_recent_candles,
disabled unless COINDCX_RUN_PUBLIC_INTEGRATION=1. It passed in final discovery:
**no available test remained skipped or unrun**. The final run includes these
groups: Phase 1 82; Phase 2 unit data 69; strategy/verification 54; historical
simulation/evaluation 63; central gate 86; persistence 57; worker/session 77;
exchange adapter/journal 95; actual public integration 1. Total 584.

Runner logs are /tmp/phase8-baseline.log, phase8-new-tests.log,
phase8-adversarial.log and phase8-full-public.log. They are local artifacts;
durable summarized public evidence is linked below. Shell capture preserved the
Python exit status, for example:

~~~bash
COINDCX_RUN_PUBLIC_INTEGRATION=1 .venv/bin/python -m unittest discover -s tests -v > /tmp/phase8-full-public.log 2>&1
result=$?; tail -n 6 /tmp/phase8-full-public.log; exit "$result"
~~~

No unresolved test failure occurred. No current Windows, real-authentication,
real-order, physical-power-loss, long-hosting or qualified performance test was
performed. These are missing verification activities, not passing unit tests.

## Measured public worker and reproducible zero-volume rejection

Actually executed:

~~~bash
.venv/bin/python -m tools.phase8_stability --seconds 60 --inject-timeout-once --output reports/phase8-public-stability
.venv/bin/python -m tools.phase8_stability --seconds 60 --inject-timeout-once --output reports/phase8-public-stability-final
.venv/bin/python -m tools.phase8_stability --replay reports/phase8-public-stability-final
~~~

Both bounded runs exited 0 and stopped durably; they were separate runs, not
continuous uptime. First run: **61.481 seconds**, four successful public fetches,
one explicitly injected timeout, zero observed provider fetch errors, zero
processed candles/entries/trades. The final run used the completed runner:

| Measurement | Actual final observation |
| --- | --- |
| Start / end UTC | 2026-10-17T12:24:34.294330 / 12:25:34.986425 |
| Requested / measured duration | 60 seconds / **60.692149 seconds**, including shutdown; initial discovery excluded |
| Public selection | I-BTC_INR selected from actual discovery; 339 confirmed active INR markets observed |
| Successful fetches / rows per fetch | 4 / 2,882 actual normalized completed OHLCV rows per window |
| Recorded worker HTTP responses | 20; all HTTP 200; excludes initial parent discovery |
| Observed public fetch errors | 0 |
| Controlled interruption | 1 injected fetch TimeoutError; explicitly synthetic fault, no fabricated candle |
| Recovery | NETWORK_ERROR followed by successful public fetches and DATA_BLOCKED/ZERO_VOLUME |
| Quality | One zero-volume bar, no missing/duplicate/invalid rows in the captured window; LIQUIDITY_REVIEW_REQUIRED also remains |
| Financial processing / simulated entries / closed trades | **0 / 0 / 0** |
| Equity / cash / realized P&L | **₹2,000 / ₹2,000 / ₹0** |
| Final state | STOPPED, emergency_halted=true, no position; worker exit 0; no shutdown error |
| Last qualified data success / equity mark | null / null; no accepted candle or marked-market equity is implied |
| Real/private operations | 0 |

The daily accounting day remains null until a candle is processed, so daily P&L
status is unavailable in this run. No trading-day rollover or filled-trade
stability was observed in these 60 seconds. UTC limits and rollover are instead
covered by deterministic tests, clearly separate from actual market evidence.

The runner uses production PaperLoop/PublicFeed and unchanged Settings/risk/
quality rules in a supervised child. It has a bounded parent shutdown with
termination escalation and a child shutdown timer; it creates a NEW account,
never resets an existing one. It records public bytes, URLs, hashes, normalized
batches, status observations and structured logs in ignored reports/. It never
reads credential variables. There is no indefinite service left running.

Offline --replay verified five archived response hashes and replayed their exact
bytes through PublicClient, normalization, quality and PaperLoop using the capture
clock. It made **zero network requests**, returned ZERO_VOLUME, retained an exact
unchanged financial snapshot, equity 2000, processed count 0 and exit 0. This is
actual recorded public data; the injected timeout and unit fixtures remain
explicitly synthetic. Captures are not repaired or used for market performance.

See [phase8-public-evidence.json](examples/phase8-public-evidence.json) for the
measured evidence, actual request/batch hashes and replay quality report. Raw
bodies/databases remain under reports/phase8-public-stability-final and are Git
ignored. Retain that directory to replay this specific observation; the compact
checked-in summary alone cannot reconstruct raw responses. A fresh public run
can return different history or fail and must be reported as observed.
Hashes establish content identity, not authenticated historical provenance.

## Historical performance audit

Only three existing local result files were found: reports/phase4-sma-synthetic/
results.json, phase4-sma-synthetic-final/results.json and
phase4-momentum-synthetic-final/results.json. All explicitly say
COMPLETE_SYNTHETIC_ONLY, symbol SYNTHETIC-INR, generated mathematical waveform,
not market data. Their source CSV is no longer present in data/local/ (only
.gitkeep was present before this task). No eligible real historical dataset or
real out-of-sample report was found. This task did not regenerate history or
present old reports as current reproducible market results.

| Performance requirement | Status | Finding |
| --- | --- | --- |
| Genuine eligible historical provenance/quality | UNVERIFIED | Public captures are genuine responses but fail eligibility; CSV hashes/operator review cannot authenticate independent market history |
| Chronological split implementation | PASS | splits.py validates ordered aligned half-open ranges and exact coverage; prior-only warmup, separate accounts and costed flat boundaries; 63 evaluation/accounting regressions |
| Actual untouched real train/validation/test evidence | UNVERIFIED | Existing synthetic artifacts show 2,880-bar periods starting Jan 31, Mar 1 and Mar 31 2024, ending Apr 30; no real untouched test exists |
| No-lookahead implementation | PASS | Strategies consume completed prefixes; next-bar-open execution and future-price invariance tests; worker never uses its execution bar as signal input |
| Survivorship/listing-time leakage | UNVERIFIED | Current-active discovery does not establish an historical universe; no delisted/listing-time dataset or audit trail |
| Fee/slippage arithmetic | PASS | Both sides costed, adverse fills, net ledger and cost stress tested; slippage is already inside fill P&L |
| Actual fee, spread, funding, borrow/tax costs | UNVERIFIED | Fixed configurable assumptions, not a verified schedule; funding is explicitly not modeled; real spot requests support 1x only |
| Metric definitions/numerics | PASS | Net P&L, sampled drawdown, mean net trade expectancy, profit factor from net winners/losers, costs and sample counts independently tested; undefined metrics null |
| Genuine net P&L/DD/expectancy/PF/trade sample | UNVERIFIED | No qualified market trades; no real returns or win rates reported here |
| Multiple symbols/regimes/statistical significance | UNVERIFIED | One-symbol framework and synthetic fixtures only; minimum bars do not prove significance; no annualized Sharpe estimate |
| Reproducibility mechanisms and parameter isolation | PASS | Settings/parameters/data/source hashes, deterministic run IDs and exports; sensitivity excludes test; no optimization or parameter change in this phase |
| Actual market reproducibility/untouched-selection discipline | UNVERIFIED | No real dataset; old report source fingerprints predate current code and source CSV is missing; rerun discipline is procedural, not enforced across operator experiments |

Current baselines stay SMA fast=5/slow=20 and momentum lookback=12/threshold=0.01.
Analytical stop references use the signal's closing price; simulated position
stops use the slipped next-entry price and configured protective fraction. They
can differ after a gap/slippage; the gate verifies both, refuses an already
breached analytical stop, and sizes from the actual modeled entry/stop/costs.
Retrospective completed-bar fills, fixed full fills, unknown intrabar order and
force-closing at split boundaries limit realism. Planned stop risk is not a
guaranteed realized-loss cap: gaps, latency and unavailable quotes can exceed it.
No synthetic trade count or return is evidence of market profitability.

## Official exchange contract audit

Re-fetched https://docs.coindcx.com/ over verified TLS: HTTP 200, 1,118,960 bytes,
SHA-256 02244e8e4675b63c8228a9754947e851885ca25e315f2fe7a0edba73640f4639.
This snapshot differs from Phase 7's hash; the applicable sections below were
read again. A documentation match or mock test does not prove server behavior.

| Contract/source | Documented fields / implementation and result |
| --- | --- |
| [Markets](https://docs.coindcx.com/#markets): GET https://api.coindcx.com/exchange/v1/markets | Active-symbol string array; actual public requests passed; no authentication |
| [Details](https://docs.coindcx.com/#markets-details): GET https://api.coindcx.com/exchange/v1/markets_details | Pair/symbol/status, base=quote/target=asset, precision, step, quantity/price bounds, min_notional and order_types; actual unsigned requests passed |
| [Candles](https://docs.coindcx.com/#candles): GET https://api.coindcx.com/market_data/candles | Descending array of open/high/low/close/volume/time; opening time integer ms; volume in target asset, not verified quote turnover; intervals 1m/15m/1h/1d; limit default 500/max 1000; optional startTime/endTime; actual 15m access passed, eligibility failed |
| [Authentication](https://docs.coindcx.com/#authentication) | Authenticated JSON POST, timestamp, HMAC-SHA256 over exact UTF-8 body, X-AUTH-APIKEY and X-AUTH-SIGNATURE. Local signature tests PASS; actual permissions/least privilege, server clock tolerance and key validity UNVERIFIED |
| [New spot order](https://docs.coindcx.com/#new-order): POST https://api.coindcx.com/exchange/v1/orders/create | side/order_type/market/price_per_unit/total_quantity/timestamp/client_order_id; numeric positive IDs, reused client IDs rejected. Offline BUY/limit body tests PASS; never transmitted; no server idempotent retry guarantee inferred |
| [Spot status](https://docs.coindcx.com/#order-status): POST https://api.coindcx.com/exchange/v1/orders/status | id or client_order_id; response identity/status/total/remaining/avg/price/fee_amount/created_at/updated_at. Numeric millisecond status timestamps; mocks only; actual server semantics UNVERIFIED |
| [Active orders](https://docs.coindcx.com/#active-orders): POST https://api.coindcx.com/exchange/v1/orders/active_orders | market, optional side, page, size max 200; orders wrapper. Its example uses ISO timestamps unlike numeric order-status timestamps. Offline signer prepares page 1 only; no active-order parser/full pagination/account reconciliation implemented |
| [Balances](https://docs.coindcx.com/#get-balances): POST https://api.coindcx.com/exchange/v1/users/balances | currency/balance/locked_balance; locked funds described as in use by an open order. Internal MockAccountReport fields are not this API schema; exact live accounting remains UNVERIFIED |
| [Spot cancel](https://docs.coindcx.com/#cancel): POST https://api.coindcx.com/exchange/v1/orders/cancel | id or client_order_id + timestamp; example success acknowledgment, not final fill proof. Do not use #cancel-order (margin) or #cancel-order-2 (futures) as spot evidence; no cancel request sent |
| [Order enums](https://docs.coindcx.com/#order) / [rate limits](https://docs.coindcx.com/#spot-api-rate-limits) | init/open/partially_filled/filled/cancelled/rejected/partially_cancelled. Spot order/status/cancel 2000 per 60s, active-order 300 per 60s documented; no public-candle quota inferred. Public retry policy remains bounded locally |

Server quantity step/minimum definitions are documented; offline exact Decimal
checks never increase quantity to meet a minimum. Base-currency decimal precision
is only a conservative local price check, not a documented exchange price tick.
Server acceptance of precision/minima remains UNVERIFIED without independently
permitted evidence. max_leverage metadata does not authorize a margin product.

New-order docs describe fee_amount as cumulative charged fee and fee/maker_fee/
taker_fee as percentages. The strategy fee setting is a fraction per side,
default 0.001 (0.1%), not a fetched maker/taker rate. Fee currency, actual tiers,
taxes and rounding are unverified. The mock quote-fee assumption is labeled and
cannot qualify balances or costs. Partial fills are cumulative in the mock;
partially_cancelled and ambiguous cancellation outcomes remain quarantined.

Timeouts become durable UNKNOWN, never permission to resend. Local unique client
IDs/reservations and conflicting-draft blocks are tested across restart. A valid
mock status plus internal account projection is not real exchange reconciliation.
No sandbox/testnet is independently verified; zero mentions in the captured docs
do not prove no such facility exists. No private endpoint above was contacted.

## Safety and stability requirement matrix

PASS below is scoped to supported offline/local-paper APIs and Linux tests.
It does not describe hostile arbitrary Python/SQL mutation or a live account.

| Requirement | Status | Implementation / evidence / boundary |
| --- | --- | --- |
| Phase 1–7 offline foundation regression | PASS | Full 584-test run, all inherited 578 tests retained |
| Complete operational Gate 0 evidence | BLOCKED | Real qualification, current Windows and real exchange accounting evidence absent |
| Central mandatory entry gate | PASS | Risk gate is authoritative at the sole broker creation site; path trace below and 86 direct adversarial tests |
| Starting equity ₹2,000 / INR / margin vs notional / 15m | PASS | Settings revalidated by gate; durable creation profile and acceptance tests |
| ₹10 initial planned risk and ₹20 ceiling | PASS | min(current equity × 0.005, configured cap ≤20, remaining daily/DD budget); independent cost/plan check and 10/20 boundary tests |
| Maximum 3x / shorts disabled | PASS | Reconstructed Settings and instrument ceiling; damaged 4x and SHORT tests; reviewed historical spot/adapter only 1x |
| Valid stop, conservative fees/slippage, affordable margin | PASS | Stop reference/entry-gap checks, costed plan and step/minimum refusal; stop and reconciliation tests |
| Daily halt min(₹40, 2% applicable daily start) | PASS | Equality/headroom/overnight loss basis and durable recovery tests; no silently raised threshold |
| Three entries per UTC day | PASS | Fourth rejected; committed count/UTC rollover and restart tests; per account, not shared across independent accounts |
| One open position / repeated and duplicate signals | PASS | Serialized broker, processed-candle uniqueness, session ownership and independent connection/process tests |
| Completed-only / incomplete and future data | PASS | Phase 2 assessment plus prior-only strategy/gate/session validation; no fabricated replacement bars |
| Invalid/stale/missing/duplicate data blocks entries | PASS | Pipeline/gate tests, adverse worker tests and real zero-volume rejection; invalid batches cannot execute modeled stops either |
| Stale/missing/transient recovery | PASS | Deterministic recovered history retains position without duplicate entry; public injected timeout recovered to safe rejection, not qualified processing |
| Provider timeout/rate-limit policy | PASS | Bounded attempts/delay/Retry-After and exhausted-policy tests; no provider failure or actual 429 observed in bounded public run |
| Restart preserves balances/positions/daily/DD/emergency halts | PASS | Exact reconciliation, child-process reopen/death and managed takeover tests; scope local SQLite on Linux |
| Persistence failure blocks entries | PASS | Atomic rollback/ambiguous-ack handling, poisoned handle, no automatic reset; new rejected-data storage-failure test |
| Corrupt/incompatible state rejected | PASS | State/schema/digest/chain/accounting validation and migration/recovery tests; no missing trades invented |
| Unknown execution status blocks conflicts | PASS | Mock journal persists uncertainty/faults/reservations across restart; no send/retry API; not a live execution bridge |
| Emergency halt / graceful shutdown / health | PASS | Durable stop and tested stale-mark flattening; measured worker exit 0; no entries after stop; last success null for rejected data |
| Fees/slippage/stop/P&L reconciliation | PASS | Deterministic entry/exit/restart assertions; zero market fills in public run, actual fee realism UNVERIFIED |
| Manual and verify order-free | PASS | Same read-only gate, sockets and broker construction forbidden in tests; no paper or real submission |
| Live submit/cancel/modify disabled | PASS | No live mode/private transport; DisabledExecution methods unconditionally raise, regardless of flags/credentials |
| Actual accepted real-data candle/fill stability | UNVERIFIED | All real windows rejected before processing; 0 processed bars is not successful trading stability |
| Long uptime/multi-day risk behavior in actual hosting | UNVERIFIED | Two separate minute-long checks, no 24/7 service/soak claim |
| Native Windows current source | UNVERIFIED | Linux only; old Phase 1 CI cannot qualify current SQLite/process behavior |
| Secret exclusions/final diff | PASS | No sensitive staged/tracked paths; index empty; 20 blank BOT_* placeholders; ignored state/captures; diff checks |
| Any limited live test readiness | BLOCKED | Required independent market, platform, execution/account and operational evidence missing; real execution remains absent |

Entry path trace: CLI backtest/CSV paper/evaluate -> eligibility -> simulate ->
PaperBroker.process_bar -> _open -> risk.entry.approve_entry -> audit -> record
entry/cash/position. Durable API -> BEGIN IMMEDIATE -> recovered candidate ->
same broker gate -> validate -> atomic candle/checkpoint/head commit. Managed
worker -> quality -> session.process (lease/stop/candle/prior-history checks) ->
same durable broker path. Only broker.py assigns a newly created Position;
state.py restores an already committed/reconciled position. Direct _open has
no current execution-candle context; bare plans/old approvals cannot authorize it.
Manual/verify only review. Exchange preview and journal prepare call the same
gate afresh; their output is an unsigned draft/reservation, not an executed entry.

Buy/hold benchmarks are labeled unconstrained arithmetic references, not broker
entries. Separate stateless simulations/accounts deliberately have separate
limits; no cross-account global capital authority is implemented. Hash checks,
operator-supplied eligibility and mutable Python state are not authentication
against a malicious caller. This is not an unlimited non-bypass security proof.

## Changes, findings and preserved code

No confirmed production implementation defect was found that required changing
the gate, limits, strategies, market qualification or persistence semantics.
Existing zero-volume tests checked rejection only; six additional acceptance
methods now demonstrate exact ₹2,000 preservation across repeated/restarted
rejection, timeout recovery without qualification, missing-history recovery
without duplicate entry, duplicate data with a stop wick preserving positions,
emergency stop using a stale last-known close and storage failure failing closed.
All fixtures in that test module are explicitly SYNTHETIC.

Two misleading general README claims remained from the initial version: no price
feed and no database. They now distinguish stateless paper --data from durable
paper start/status/stop and identify embedded SQLite. VALIDATION's opening now
limits earlier Windows success to its actual Phase 1 revision.

| Phase 8 path | Change |
| --- | --- |
| tests/test_continuous_paper.py | Six added deterministic acceptance tests; all previous assertions preserved |
| tools/phase8_stability.py | New bounded production-worker audit and offline exact-public-response replay |
| docs/examples/phase8-public-evidence.json | Actual final measurement, hashes, health/quality/replay evidence; no returns |
| docs/PHASE8_AUDIT.md | This requirement/evidence/readiness report |
| README.md | Current outcome/link, worker/replay/SQLite scope corrections |
| VALIDATION.md | Current exact counts and historical Windows scope |

Pre-edit archive /tmp/phase8-before.zip contains all 109 inherited nonignored
files. Final comparison: three inherited files modified, three added, **106
inherited files byte-identical**, none deleted. All production config/risk/
broker/persistence/session/worker/strategy/exchange sources are byte-identical.
All prior tests are retained. No test/assertion or risk rule was removed/weakened.
No dependency, .env.example, credential interface or live permission changed.
The much larger Git diff against HEAD includes inherited uncommitted phases;
phase-local comparison includes untracked files rather than attributing them all
to this audit. No source was staged, committed or pushed.

Current filename/index and common credential-pattern checks plus repository
safety tests found no real credentials or .env/state files tracked/staged.
Only .env.example is allowed, with 20 blank variables. This is not a complete
Git-history scan or proof against unknown secret formats. Captures contain only
whitelisted public responses, no authentication headers or private balances.

## Remaining security and operational prerequisites

| Prerequisite for any future limited live test | Status | Exact remaining work |
| --- | --- | --- |
| Current risk gate and local fail-closed recovery | PASS | Retain regressions; test any future execution bridge through this authority |
| Independent historical/liquidity/instrument qualification | BLOCKED | Obtain valid complete history and independently reviewed quote-liquidity, listing universe, precision/minimum and cost evidence; never relax zero-volume checks to force entries |
| Real untouched net-of-cost validation/sample | UNVERIFIED | Freeze selection before a sufficient real test; document survivorship, regimes, costs/funding where applicable and reproducible data/source versions |
| Qualified paper entries/exits/restarts over meaningful duration | UNVERIFIED | First obtain eligible evidence, then measure actual processed bars, fills, outages and halts; minute-long rejection is insufficient |
| Native Windows target | UNVERIFIED | Run the exact current tree under Windows/Python 3.12 and retain actual platform/revision/counts; do not copy a Linux venv |
| Real key authenticity/least-privilege/withdrawal restrictions | UNVERIFIED | Separately authorized future permission review; no credential requested or tested here |
| Complete status/balance/active-order/fee/cancel semantics | BLOCKED | Independently confirm all fields/pagination, fee assets/rounding and terminal fills; quarantine ambiguity rather than invent exchange behavior |
| Atomic global reservation/fill/account/risk authority | BLOCKED | Mock journal and paper account remain independent; no real execution bridge exists; never treat a draft as a fill or count it as reconciled |
| Real protective stops/exit behavior and unknown-order resolution | BLOCKED | No exchange-hosted stop/OCO/exit lifecycle or private transport; keep unknowns blocked and never blindly resend |
| Trusted backups/latest-state proof and platform storage | UNVERIFIED | Keep an external trusted checkpoint; old valid-file rollback cannot be detected by a fresh process without it; test restore freshness and local storage behavior |
| Hosting, clock, monitoring and capacity | UNVERIFIED | No supervisor/alerts/24-hour soak, disk/full-snapshot growth benchmark, physical power-loss, network-filesystem or multi-host guarantee; test these independently |
| Separate approval for subsequent scope | BLOCKED | Phase 8 only completed; explicit approval required before any later phase, without implicitly enabling live operations |

SQLite uses FULL synchronization/DELETE journaling and transactional validation,
but physical disk promises, hostile SQL edits and multi-host storage are outside
the proof. Full snapshots/history validation grow with trading; no compaction or
capacity certification exists. Source fingerprints deliberately reject changed
semantics (including some line-ending changes), not automatically migrate an
account. A storage failure cannot guarantee that an uncommitted halt was saved.
Integrity hashes are not signatures or access controls; protect files/backups.

The worker only knows completed 15m OHLCV, may stop processing an existing
position on invalid data, and emergency flattening is an estimate at the last
known completed close. It cannot protect real capital during an outage. Graceful
stop latches emergency permanently for that account; no implicit unhalt/reset is
provided. Health freshness does not substitute for out-of-band monitoring.
Credential objects in future offline-auth code redact repr, but are ordinary
process memory, not a vault; no secrets were loaded here.

## Exact native Windows PowerShell verification instructions

These commands were **not executed on Windows**. Run from the repository root
on an actual Windows machine with Python 3.12 installed. No activation/policy
change, real key or CoinDCX account is required.

~~~powershell
py -3.12 -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'venv creation failed' }
.\.venv\Scripts\python.exe -m pip install --no-index --no-cache-dir -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'dependency check failed' }
.\.venv\Scripts\python.exe -c "import platform,sqlite3,sys; print(platform.platform()); print(sys.version); print(sqlite3.sqlite_version); assert sys.platform == 'win32'; assert sys.version_info[:2] == (3,12)"
if ($LASTEXITCODE -ne 0) { throw 'native Windows/Python 3.12 required' }
Remove-Item Env:COINDCX_RUN_PUBLIC_INTEGRATION -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'offline tests failed' }

$env:COINDCX_RUN_PUBLIC_INTEGRATION = '1'
try {
    .\.venv\Scripts\python.exe -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) { throw 'public-enabled tests failed' }
} finally {
    Remove-Item Env:COINDCX_RUN_PUBLIC_INTEGRATION -ErrorAction SilentlyContinue
}

$auditPath = 'reports/phase8-public-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
.\.venv\Scripts\python.exe -m tools.phase8_stability --seconds 60 --inject-timeout-once --output $auditPath
if ($LASTEXITCODE -ne 0) { throw 'bounded audit failed; inspect evidence' }
.\.venv\Scripts\python.exe -m tools.phase8_stability --replay $auditPath
if ($LASTEXITCODE -ne 0) { throw 'zero-volume preservation replay failed or current observation differs' }
git diff --check
if ($LASTEXITCODE -ne 0) { throw 'diff whitespace check failed' }
~~~

The default suite intentionally skips one public test; enabling it attempts
public GETs only and network failure is a real failure to report. A new public
capture need not contain zero volume: --replay intentionally returns failure
unless this specific rejection/preservation condition is reproduced. It does
not assert that every future public response must be zero-volume. Review such
differences honestly, retain the evidence, and keep market qualification blocked.
Do not overwrite an existing paper database or clear halts for verification.

Phase 8 ends with these results reported. Phase 9, private operations and real
order execution remain disabled pending explicit further approval and evidence.
