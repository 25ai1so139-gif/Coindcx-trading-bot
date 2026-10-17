# Phase 8B — Windows, historical data and paper qualification

2026-10-17, Asia/Kolkata (IST). Existing checkout and uncommitted work preserved;
branch phase2-market-data, HEAD acde254c37b8f2f0fc84da00bd0a0012e2595cca.
Actual execution: **Linux 6.18.55 x86_64/glibc 2.41, CPython 3.12.14,
SQLite 3.53.1**, existing .venv, no third-party dependencies.

**Linux safety/regressions PASS. Native Windows UNVERIFIED. Eligible genuine
historical evaluation and paper-trading qualification BLOCKED. No overall
live-readiness PASS.** No private endpoint/stream, credential, real order,
cancel/modify operation, live/short enablement, parameter optimization or Phase 9
work occurred. Publishing this report means files in the working tree; no Git
commit, push or external publication was performed.

## Gate 0 and actual tests

Inspected Phase 8's audit, measured public evidence, actual CLI/data/quality,
strategy/risk, broker/persistence/worker and offline exchange interfaces. Its zero
processed candles and zero fills establish rejection behavior only. They are
not evidence of profitability, accepted-data stability or Windows compatibility.
No safety limit was relaxed to generate a trade.

| Executed Linux run | Passed | Failed | Errors | Skipped | Total | Seconds |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Gate 0 full default baseline | 583 | 0 | 0 | 1 | 584 | 16.641 |
| Initial safety/adversarial group | 333 | 0 | 0 | 0 | 333 | 7.915 |
| Initial full public-enabled discovery | 584 | 0 | 0 | 0 | 584 | 17.674 |
| Two added synthetic contract guards | 2 | 0 | 0 | 0 | 2 | 0.031 |
| Final safety/adversarial group | 335 | 0 | 0 | 0 | 335 | 8.102 |
| **Final full public-enabled discovery** | **586** | **0** | **0** | **0** | **586** | **18.023** |
| Native Windows | N/A | N/A | N/A | N/A | Not executed | N/A |

Exact commands from the repository root:

~~~bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m unittest tests.test_exchange_adapter tests.test_order_reconciliation tests.test_continuous_paper tests.test_persistence tests.test_central_risk tests.test_risk -v
COINDCX_RUN_PUBLIC_INTEGRATION=1 .venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m unittest tests.test_order_reconciliation.ReconciliationStateTests.test_private_stream_envelope_cannot_be_treated_as_rest_status_or_clear_reservation tests.test_order_reconciliation.ReconciliationStateTests.test_stream_cancellation_fields_do_not_authorize_inferred_rest_fill_after_restart -v
~~~

The safety and enabled-full commands were rerun after adding both guards. Capture
preserved each Python exit code, for example:

~~~bash
COINDCX_RUN_PUBLIC_INTEGRATION=1 .venv/bin/python -m unittest discover -s tests -v > /tmp/phase8b-full-public-final.log 2>&1
result=$?; tail -n 6 /tmp/phase8b-full-public-final.log; exit "$result"
~~~

Logs: /tmp/phase8b-baseline.log, phase8b-safety.log, phase8b-full-public.log,
phase8b-new-tests.log, phase8b-safety-final.log and phase8b-full-public-final.log.
The sole baseline skip was the optional public discovery/recent-candle test,
enabled by COINDCX_RUN_PUBLIC_INTEGRATION=1. It actually passed in both enabled
discoveries. No available test remained skipped/unrun in the final Linux suite.
Fixtures and mocked private messages are explicitly SYNTHETIC; their passing
tests do not create genuine market performance or server verification.

Native Windows could not be executed: only a Linux environment is attached and
no Windows execution/runner tool is available. Neither PowerShell executable is
installed here; installing PowerShell, WSL or Wine on Linux would not establish
native Windows execution. No current Windows pass/failure/skip count is asserted.
The old 81-test Phase 1 CI result does not cover the current source. Exact local
commands appear below, as authorized by the user's fallback instruction.

## Genuine historical data investigation

Actually executed:

~~~bash
.venv/bin/python -m tools.phase8b_history --output reports/phase8b-history
~~~

The fixed BTC/ETH/SOL/DOGE asset sample was chosen before fetching; native INR
pairs were selected from actual active discovery, not assumed tradable or chosen
for returns. The 10.998-second capture made **18 recorded unsigned HTTPS GETs,
all HTTP 200**. Raw response bytes, hashes, normalized CSVs, strict-quality
reports and original-provenance sidecars are retained under the ignored output
directory. No candle/volume/gap was invented, replaced, interpolated or repaired.

Capture began at **18:56:54 IST on 17 October 2026**. Requested history spans
**17 September 18:15 IST to 17 October 18:45 IST, end exclusive**. Machine records
retain the required UTC timestamps: 2026-09-17T12:45:00+00:00 through
2026-10-17T13:15:00+00:00. Historical freshness is evaluated against that explicit
cutoff, not presented as current market qualification. Window length is 2,882
15m candles: default 2,880-bar history plus two worker context bars.

| Actual pair | Rows/completed | Invalid OHLC/time | Missing | Duplicates | Zero-volume bars | Eligibility |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| I-BTC_INR | 2,882 | 0 | 0 | 0 | 1 | BLOCKED |
| I-ETH_INR | 2,882 | 0 | 0 | 0 | 4 | BLOCKED |
| I-SOL_INR | 2,882 | 0 | 0 | 0 | 4 | BLOCKED |
| I-DOGE_INR | 2,882 | 0 | 0 | 0 | 29 | BLOCKED |

All four had ordered, unique, aligned UTC openings, finite positive/coherent
OHLC and exact requested coverage. Last returned opening was 18:30 IST; its
close at 18:45 is within the exclusive requested end. Volume zero is preserved
for quality review and rejected under the unchanged strict trading policy.
All four reports also contain **LIQUIDITY_REVIEW_REQUIRED**: the documented
candle volume is in target asset units, and no verified quote-volume series or
independently justified liquidity threshold is available. PublicFeed explicitly
does not set reviewed/verified flags or provide a qualified instrument context.
Fetching public metadata does not remove those blocks.

Symbol checks bind each requested native pair to current active discovery and
quote/asset metadata. Candle responses lack a per-row symbol field; identity is
bound by the exact request URL. Historical listing dates, redenominations,
rebrands, delisted constituents and listing-time universe membership remain
UNVERIFIED. This is a four-asset sample, not proof that every exchange market
lacks usable history, and current-active discovery does not resolve survivorship.

Re-import validation was also executed for every exported CSV. Equivalent child
commands (full argv/results are retained in the evidence):

~~~bash
.venv/bin/python -m cli data validate --input reports/phase8b-history/I-BTC_INR.csv --as-of 2026-10-17T13:15:00+00:00
.venv/bin/python -m cli data validate --input reports/phase8b-history/I-ETH_INR.csv --as-of 2026-10-17T13:15:00+00:00
.venv/bin/python -m cli data validate --input reports/phase8b-history/I-SOL_INR.csv --as-of 2026-10-17T13:15:00+00:00
.venv/bin/python -m cli data validate --input reports/phase8b-history/I-DOGE_INR.csv --as-of 2026-10-17T13:15:00+00:00
~~~

All correctly returned **exit 2 / eligible=false**, retaining
SOURCE_INGESTION_REJECTED, ZERO_VOLUME and LIQUIDITY_REVIEW_REQUIRED. These are
expected rejection results, not failing unit tests. Exporting/re-importing the
normalized file cannot erase original rejection.

**Real backtests run: 0. Untouched out-of-sample tests run: 0.** Eligibility did
not support them. A 30-day history window also cannot supply the existing default
30-day warmup plus separate 30-day train/validation/test periods. Further data
should be acquired only with preserved provenance and a predeclared split plan;
longer coverage alone will not cure the observed zero-volume/liquidity failures.
No market net P&L, drawdown, win rate, profit factor or expectancy is fabricated.
Existing synthetic reports remain software examples and were not relabeled.

## Bounded paper diagnostic — qualification BLOCKED

With no eligible sampled dataset, the existing bounded worker tool was used for
**safe-rejection diagnostics only**, with unchanged quality/risk controls:

~~~bash
.venv/bin/python -m tools.phase8_stability --seconds 60 --output reports/phase8b-public-rejection
.venv/bin/python -m tools.phase8_stability --replay reports/phase8b-public-rejection
~~~

| Requested measurement | Actual observation |
| --- | --- |
| Time | 18:57:30.660146–18:58:34.346107 IST, 17 October 2026 |
| Duration | **63.685977 seconds**, including shutdown; requested 60; initial parent discovery excluded |
| Pair / feed | Actual discovered I-BTC_INR; genuine unsigned public data, no synthetic fault injection |
| Completed fetches | **5**, each a 2,882-candle raw window |
| Recorded worker HTTP requests | **25**, all 200; excludes parent discovery |
| Fetch errors / injected interruptions | **0 / 0** |
| Data-rejected cycles | **5**, ZERO_VOLUME plus missing liquidity qualification |
| Valid/eligible candles processed into account | **0 / 0**; structurally valid raw OHLCV is not accepted account processing |
| Strategy signals generated | **0**; rejection occurred before strategy evaluation |
| Rejected entry signals | **0**; no entry proposed. Five rejected data cycles are not five rejected signals |
| Simulated entries / closed trades | **0 / 0** |
| Simulated fees / slippage cost | **₹0 / ₹0**, because there were no fills |
| Starting / final equity / change | **₹2,000 / ₹2,000 / ₹0** |
| Open position | None |
| Last qualified data / current market mark | Unavailable / unavailable; initial balance preservation is not marked-market performance |
| Shutdown | Worker exit 0, STOPPED, durable emergency halt true, no shutdown error |

Fees/slippage remain configured estimates (0.001 per side each); zero observed
cost does not verify exchange fee tiers or market execution. Daily accounting
day and current daily P&L are unavailable before any bar is processed. The short
run did not cross a 15m boundary or measure real trade/restart/multi-day behavior.
Those controls are covered by separate deterministic synthetic tests only.

Offline replay verified five exact archived HTTP responses through PublicClient,
normalization, quality and PaperLoop, made **zero network requests**, and
reproduced DATA_BLOCKED/ZERO_VOLUME with an unchanged financial snapshot and
₹2,000 equity. This proves reproducible safe rejection, not trading qualification.
No indefinite worker remains running; no 24/7 or profitability claim is made.

## Exchange contracts: sources, mocks and remaining uncertainty

Re-fetched official https://docs.coindcx.com/ with verified TLS: HTTP 200,
1,118,960 bytes; HTML SHA-256
7b77ac0e97bd43ae3a25455f2e0a56d1faae6942984efc156a1f5712c6fb9f3e.
Only this public documentation and unsigned public GET routes were contacted.

| Requirement and official source | Verified documentation/mock scope | Remaining server evidence |
| --- | --- | --- |
| [Markets](https://docs.coindcx.com/#markets) GET https://api.coindcx.com/exchange/v1/markets and [details](https://docs.coindcx.com/#markets-details) GET https://api.coindcx.com/exchange/v1/markets_details | Active symbols and native pair/asset/quote mapping; public access passed | Historical listing identity UNVERIFIED |
| [Candles](https://docs.coindcx.com/#candles) GET https://api.coindcx.com/market_data/candles | OHLCV/time array, opening epoch ms, descending unique times, asset volume; intervals 1m/15m/1h/1d; limit 500 default/1000 max; optional startTime/endTime; 15m actual access passed, no key required | Eligibility failed; quote liquidity remains unavailable |
| [Quantity/precision/minima](https://docs.coindcx.com/#markets-details) | target_currency_precision, step, min/max_quantity; base_currency_precision; price bounds; min_notional in base currency. Exact Decimal local boundaries and no risk-increasing rounding tested | Actual server acceptance UNVERIFIED; base-currency decimals are not independent proof of a price tick |
| [Authentication](https://docs.coindcx.com/#authentication) | Timestamped JSON POST, exact-body HMAC-SHA256, X-AUTH-APIKEY / X-AUTH-SIGNATURE; synthetic signing/redaction/default-disabled tests pass | Real credentials, least privilege, permitted scopes and clock tolerance UNVERIFIED; no credentials loaded |
| [New order](https://docs.coindcx.com/#new-order) / [status](https://docs.coindcx.com/#order-status) | BUY/limit drafts and cumulative quantities/avg_price/fee_amount, numeric IDs and timestamps; local unique client ID, unknown status/reservation and duplicate protections tested | No request transmitted; status/balance/fee settlement and idempotent server retry behavior UNVERIFIED |
| [Spot private order stream](https://docs.coindcx.com/#get-order-update) | **Documentation explicitly says fee_amount is charged in base-currency; remaining_quantity is pending unfilled/uncancelled; cancelled_quantity is cancelled quantity.** base currency means quote in this API's market metadata, e.g. INR for BTCINR | Private stream never connected; no supported stream parser. This does not independently verify REST cancellation accounting or actual fee settlement |
| [Spot cancellation](https://docs.coindcx.com/#cancel) and [enums](https://docs.coindcx.com/#order) | Cancel acknowledgment alone is not final fill proof. Local mock handles known partial/full fills conservatively; partial cancellations stay UNKNOWN and block conflicts | Definitive REST partial-cancellation/fee/trade accounting UNVERIFIED; no cancel sent |
| [Balances](https://docs.coindcx.com/#get-balances) | currency/balance/locked_balance documented; mock account projection remains a separate internal schema | Real reconciliation, active-order pagination, fee rounding/taxes/tiers and execution bridge remain UNVERIFIED/BLOCKED |

**Correction to the earlier broad fee-currency limitation:** the public
documentation does specify base-currency fee denomination for the private spot
order-update event. Its section's extracted-text SHA-256 is
d6ba47b78d71bc11f95bee2ffa71b3e566a7fc9c1dffcf33e0cece0ddfb539f2.
That narrow documented fact is now verified; it is not evidence of a tested REST
settlement lifecycle or a universally authenticated fee schedule. The mock quote
fee assumption is consistent with that documented stream denomination, but
the mock has no real-account bridge. Earlier audits remain historical records.

Two added **synthetic** tests prove a stream event/data wrapper cannot be consumed
as REST status to release a reservation, and stream-style cancelled_quantity plus
remaining_quantity=0 cannot cause an inferred partial-cancellation fill. Both
preserve UNKNOWN across reopen, retain the last valid partial report where one
exists, and block another draft. Existing known-fill/cancel/no-blind-retry tests
remain unchanged. No private stream/client/REST transport was implemented.

Current public metadata observed quantity steps BTC 0.00001, ETH 0.0001,
SOL 0.001, DOGE 1; all four min_notional values were ₹100. These are timestamped
observations in the evidence, not guaranteed future exchange constraints. For
example, min_quantity need not itself be an exact step multiple. The adapter
checks both without increasing an approved size. Price ticks and actual fill
fees remain unqualified. Spot supports 1x in this implementation; the 3x ceiling
does not authorize undocumented real leverage.

A separate **hypothetical pure-sizing inspection**, not a backtest, gate
approval or paper fill, called risk.sizing.size_position with unchanged defaults:
₹2,000 equity, ₹100 requested margin, 1x leverage, default fee/slippage estimates,
each captured last close and its public step/minimums. All four correctly
rejected as below instrument minimum after down-rounding. References were
BTC 8215555.4, ETH 244280, SOL 10479.5 and DOGE 8.0181 INR. Exact parameters and
outcomes are in hypothetical_default_size_checks in the evidence. This is an
additional future sizing constraint, not permission to bypass data eligibility
or silently raise margin/leverage. The first ad hoc inspection wrapper had an
indentation error before execution; the corrected wrapper completed all four
checks. No production calculation, account or test failed or changed.

## Risk/recovery verification and final requirement matrix

| Requirement | Status | Code and evidence / limit |
| --- | --- | --- |
| Gate 0 code/evidence review and complete Linux regressions | PASS | Actual audit/code reviewed; final 586 tests, including optional public test |
| Task 1 current native Windows | UNVERIFIED | No native environment executed; counts N/A; commands below |
| Task 2 genuine public history acquisition/validation | PASS | Four fixed real-response samples; UTC/OHLC/gap/duplicate checks and raw/CSV hashes |
| Task 2 eligible history for genuine backtest/OOS | BLOCKED | All four fail zero-volume and quote-liquidity rules; insufficient evaluation coverage; no backtest/OOS run |
| Task 3 eligible-data paper-trading qualification | BLOCKED | Diagnostic has zero accepted bars/signals/trades; no qualified-fill stability established |
| Task 3 measured rejection/shutdown/equity preservation | PASS | Actual 63.686s measurement and exact-byte offline replay; all requested counters reported |
| Task 4 documented constraints and local precision/minimum checks | PASS | Public metadata and mock boundaries verified; server price tick/acceptance UNVERIFIED |
| Default ₹100 margin feasibility at captured prices | BLOCKED | Pure size checks for all four fall below observed minimums after down-rounding; no size enlarged and no entry approved |
| Task 4 documented spot-stream fee denomination | PASS | Official #get-order-update definition; no private stream accessed |
| Task 4 actual REST fee/cancel/permission behavior | UNVERIFIED | Mocks do not establish real settlement/scopes; unsupported messages quarantine |
| Task 5 central gate on supported entries | PASS | risk/entry.py approve_entry and sole broker open mutation; direct/raw/private-plan/reentrant paths in 86 gate tests; durable wrapper reloads under transaction |
| Maximum leverage 3x / short entries disabled | PASS | Settings reconstructed centrally, instrument ceiling, damaged 4x and SHORT rejection tests; real reviewed spot/adapter 1x only |
| ₹2,000 initial equity, margin vs notional and 15m | PASS | Existing validated settings, central creation profile and persistence regressions; defaults untouched |
| ₹10 initial planned-risk budget / ₹20 ceiling | PASS | 0.5% current equity, configured absolute cap ≤20, remaining headroom, fees/slippage and independent plan math; exact boundary tests |
| Daily loss min(₹40, 2% applicable daily start) | PASS | risk/controls.py budget/latch, threshold equality, overnight loss basis, persisted halt and UTC recovery tests |
| Max three entries per UTC day | PASS | Filled-entry counter, fourth rejection, restart/rollover tests; per account, not across independent simulations/databases |
| One open position / duplicate prevention | PASS | Serialized broker, unique processed candle keys, managed lease, two-process tests; duplicate signals cannot stack positions |
| Invalid/stale/incomplete data and missing stop block entry | PASS | Central data/stop checks, quality gating, adverse worker/replay tests; actual bad-volume history rejected |
| Persistence failure / interrupted writes | PASS | Atomic rollback, ambiguous acknowledgment, poisoned handles, child-process death before/after commit; no auto-reset |
| Restart/position/equity/fees reconciliation | PASS | Exact financial state, daily/DD/emergency latches and processed IDs preserved in Linux tests; no real-fill restart claimed |
| Emergency stop / drawdown / graceful shutdown | PASS | Durable stop and persistent latches; actual worker STOPPED with equity preserved; last-close modeled exits can be stale |
| Unknown execution status blocks conflicts | PASS | Durable mock UNKNOWN/reservation/account-fault handling and new stream guard tests; real bridge remains absent |
| Manual/verify, private transport and live operations disabled | PASS | Full zero-order tests; no live mode; DisabledExecution submit/cancel/modify/read_account always rejects |
| Task 6 report/provenance/commands/final diff | PASS | This matrix, linked evidence, test counts and phase-local comparison |
| Overall live or Phase 9 readiness | BLOCKED | Windows, eligible history/untouched evaluation, qualified fills, real exchange accounting and operational evidence remain missing |

Risk review remains fresh at PaperBroker._open immediately before its sole
position creation; simulation/evaluation and durable/session worker routes all
use that boundary. Recovery restores an already validated committed position,
not a new permission. Manual/verify only review. Mock journal previews call the
same gate and never fill a real account. The proof covers supported APIs/local
SQLite, not malicious arbitrary Python/SQL or newly created independent accounts.
Planned loss caps cannot guarantee realized loss through gaps or unavailable data.

## Changes, artifact integrity and remaining work

Phase-local changes:

| File | Purpose |
| --- | --- |
| tools/phase8b_history.py (new) | Fixed four-asset, bounded read-only history/instrument capture using existing quality/export; immutable new output, no trading |
| tests/test_order_reconciliation.py | Two additional deterministic synthetic unsupported-stream/cancellation quarantine tests |
| docs/examples/phase8b-evidence.json (new) | Actual history, hashes, CSV rejection results, measured worker/replay counters and documentation clarification |
| docs/PHASE8B_AUDIT.md (new) | This requirement/status report and commands |
| README.md / VALIDATION.md | Current results and limitations; previous reports preserved |

The pre-edit archive /tmp/phase8b-before.zip captured 112 inherited files.
Final comparison: three inherited files changed, three added, **109 inherited
files byte-identical**, none deleted. All production trading/data/risk/strategy/
exchange/persistence source and existing test assertions are preserved; only the
new audit utility and two test methods were added. No dependency, numeric risk
limit, eligibility flag, secret template or live permission changed. The larger
Git diff against HEAD includes inherited phases; no source was staged or pushed.

Verified all 18 historical response hashes, all four CSV hashes and all 25 worker
response hashes against the summarized evidence. See
[phase8b-evidence.json](examples/phase8b-evidence.json). Raw bodies, CSV sidecars,
SQLite and logs remain in ignored reports/phase8b-history and
reports/phase8b-public-rejection; retain them to reproduce this exact observation.
Hashes bind content, not independently authenticated historical exchange trades.
No sensitive filename or common credential pattern was found staged/tracked;
.env.example remains 20 blank BOT_* placeholders, state/capture directories are
ignored. This is not a complete Git-history or unknown-secret-format audit.

Remaining work: run the actual current tree on Windows and retain counts;
independently investigate the zero-volume periods and historical symbol identity
without filling gaps or deleting rejected records; obtain defensible quote-volume/
instrument/cost evidence and a predeclared adequate chronological dataset; then
measure qualified paper bars/fills/recovery across multiple completed intervals.
Also review requested margin versus observed lot/minimum constraints while
retaining all risk ceilings; the current default-size rejection must not be
converted into automatic quantity enlargement.
Do not treat a zero-volume policy relaxation as qualification. Server tick,
REST fee/cancellation/balance/pagination and permission validation remain
unverified under the prohibition on private access. No real execution bridge or
exchange-hosted protective stop lifecycle exists. Longer hosting/physical-failure,
clock/monitoring, snapshot growth, external trusted backup freshness and multi-host
storage still need evidence; source fingerprints may reject changed line endings.

## Native Windows PowerShell commands — not executed here

Run from a Windows checkout of this exact source with Python 3.12 and Git. Do not
copy the Linux .venv or overwrite an existing paper database. No credential or
CoinDCX account is required; no execution-policy/activation change is needed.

~~~powershell
$env:PYTHONUTF8 = '1'
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

$historyPath = 'reports/phase8b-history-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
.\.venv\Scripts\python.exe -m tools.phase8b_history --output $historyPath
if ($LASTEXITCODE -ne 0) { throw 'history capture failed; inspect artifacts' }
$auditPath = 'reports/phase8b-paper-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
.\.venv\Scripts\python.exe -m tools.phase8_stability --seconds 60 --output $auditPath
if ($LASTEXITCODE -ne 0) { throw 'bounded diagnostic failed; inspect artifacts' }
.\.venv\Scripts\python.exe -m tools.phase8_stability --replay $auditPath
if ($LASTEXITCODE -ne 0) { throw 'captured zero-volume condition differed or replay failed; inspect evidence' }
git diff --check
if ($LASTEXITCODE -ne 0) { throw 'diff whitespace check failed' }
~~~

The default test command intentionally skips the optional public test; the
enabled command attempts unsigned public GETs and may fail if the network does.
Record actual Windows counts/revision/platform rather than assuming Linux totals.
Capture tools exit 0 for successful diagnostics even when market qualification
is BLOCKED; consult eligible/status and processed/fill counts. --replay is
specifically a zero-volume preservation check and can correctly return failure
when a future capture differs. Never fabricate or alter market data to make it
pass. Phase 9 and private/live operations remain disabled; further scope requires
explicit approval.
