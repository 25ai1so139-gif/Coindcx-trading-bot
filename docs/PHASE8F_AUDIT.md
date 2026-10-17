# Phase 8F — historical strategy evaluation preflight

17 October 2026. **Historical backtest/OOS evaluation BLOCKED; permitted entry
action NO_TRADE.** The stored data is genuine public-response provenance and
has the reported nominal coverage, but none of the four datasets qualifies under
unchanged strategy/liquidity/source rules. Both strategy preflights reject every
symbol before any signal, account, fill, benchmark or performance experiment.

Actual tests: **Linux 6.18.55 x86_64/glibc 2.41, CPython 3.12.14, SQLite 3.53.1**,
standard library only. Final full discovery: **634 passed, 0 failed, 0 errors,
0 skipped**. These software tests are not evidence of profitability. Native
Windows and actual exchange execution remain UNVERIFIED.

No existing trading/data/risk/backtest source or old test changed. Live and short
entries stay disabled; no private endpoint, credential, real order, reset of a
paper account, strategy tuning or Phase 9 work. Initial simulated capital remains
INR 2000, requested margin INR 100, configured leverage 1x/ceiling 3x and all
existing risk limits remain intact.

## Gate 0 and rules recorded before testing

Inspected Phase 8E's audit/evidence, actual stored history/raw response/sidecars,
public pipeline/quality/loader, both strategies, strategy verification, config,
central gate/sizing/stops/controls, broker, engine, split/evaluation/metrics and
benchmark code and existing tests. Source/untracked work was archived for a
phase-local diff before edits.

The exact rules were written to [PHASE8F_RULES.md](PHASE8F_RULES.md) and their
configuration/strategy/source hashes recorded at **2026-10-17T15:02:37.360701Z**
(20:32:37.360701 IST), **before Phase 8F unit tests and data preflight**. The
[published rules manifest](examples/phase8f-rules.json) is byte-identical to the
original reports/phase8f/rules-before-tests.json. Hash checks still pass. This
is a local audit record, not an independently signed/preregistered experiment.

Exact baseline rules, with no invented exits or revised parameters:

| Item | Implemented behavior |
| --- | --- |
| SMA | fast=5/slow=20, 21 closes minimum; LONG on previous_fast<=previous_slow and current_fast>current_slow; SHORT on reverse inequalities; otherwise NO_TRADE |
| Momentum | lookback=12/threshold=0.01, 13 closes minimum; return=latest/close_12_intervals_earlier−1; LONG at >=0.01, SHORT at <=−0.01; otherwise NO_TRADE; level test may repeat every bar |
| Signal evidence | Last completed candle's close time; raw-close entry reference; LONG analytical stop=0.98×close, SHORT analytical stop=1.02×close; invalid/insufficient data/indicators yield NO_TRADE |
| Historical entry | Prior completed-bar LONG can fill at the next bar's open only after fresh central approval; indicator history excludes that new bar until processing ends |
| Position/exit | One long only; SHORT/SELL exits a long at next open and never opens a short. HOLD does not close a long. No take-profit, trailing stop, time exit or short reversal. End-of-period closes at final close with costs |
| Sizing | Requested margin is a ceiling, not exposure; round DOWN by verified step, cap collateral/cash and planned stop risk, reject min quantity/notional failures; never enlarge to fit |
| Stop | Modeled entry=open×1.001, fixed trigger=entry×0.98, adverse exit=reference×0.999; gap exit reference=min(open,trigger). Daily/drawdown floor may trigger earlier; new entries can stop in their first bar |
| Costs | Assumed fee 0.001 and adverse slippage 0.001 on each side; both stop-side fees/slippage included in planned risk. No authenticated fee tier, depth/impact or funding history |
| Duplicates | Strictly increasing unique candles; repeated BUY while open rejected. Continuing momentum can re-enter on a later bar after exit if the fresh gate permits; no extra cooldown invented |

Full sizing formulas, gate requirements, event order, equity floors, metric
definitions, gross-versus-net distinction and limitations are in the rules
document. These definitions are complete for the supported offline numerical
model; actual market execution realism is not established.

## Task 1 — actual stored historical data

Audited the **existing Phase 8E archive**, not a new fetch or a synthetic copy:
reports/phase8e-history. Its original fixed four-asset acquisition occurred
2026-10-17T14:38:33.722542Z through 14:39:12.122347Z, with 54 recorded unsigned
GETs. Phase 8F data auditing/replay itself made **zero network requests**. The
separate optional public unit integration ran in final discovery; it checks
recent public discovery/candle structure, not these datasets' trading eligibility.

Source: documented GET https://api.coindcx.com/market_data/candles, interval=15m,
exact native INR pairs from public active discovery/details. Original query URLs,
response hashes, raw-page archive hashes, CSV hashes and sidecar decisions were
revalidated. All **46,080 raw records match stored normalized OHLCV exactly**;
the immutable per-dataset raw archive hashes also match their original sidecars.

All four windows are **[2026-06-19T14:30:00Z, 2026-10-17T14:30:00Z)**, equivalent
to 19 June 20:00 IST → 17 October 20:00 IST, 2026, end exclusive. First candle
opens at the start; final opening is 17 October 14:15 UTC/19:45 IST and closes
at the exclusive end. Current prices or current market freshness are not claimed.

| Pair | Rows / completed | Invalid OHLC/time/volume | Missing / duplicates / incomplete | Zero volume | Positive-volume shape only | Eligible strategy observations |
| --- | ---: | ---: | --- | ---: | ---: | ---: |
| I-BTC_INR | 11,520 / 11,520 | 0 | 0 / 0 / 0 | 6 | 11,514 | 0 |
| I-ETH_INR | 11,520 / 11,520 | 0 | 0 / 0 / 0 | 46 | 11,474 | 0 |
| I-SOL_INR | 11,520 / 11,520 | 0 | 0 / 0 / 0 | 23 | 11,497 | 0 |
| I-DOGE_INR | 11,520 / 11,520 | 0 | 0 / 0 / 0 | 195 | 11,325 | 0 |

Raw pages are descending; normalized records are ascending, aligned UTC with
coherent finite positive OHLC. Explicit finite zero volume is structurally valid
in CandleRecord but excluded by the unchanged strictly positive-volume trading
Candle/history model. The 270 zeros remain source observations; no rows were
dropped, padded, forward-filled or assigned fabricated positive volume.
The 45,810 positive-volume rows pass local shape requirements only. They are
**not eligible samples** without sufficient preceding qualified history, market
review, source consistency, instrument/cost and liquidity evidence.

### ETH interval consistency and liquidity

Exact-byte offline replay of reports/phase8e-trace reproduces the bar opening
2026-10-13T23:30:00Z: direct 15m volume **0.086267 ETH**, corresponding 15 unique
complete 1m sum **0.085028 ETH**, difference **0.001239 ETH**. All OHLC values
agree, boundary selection and different request limits agree, and normalization
preserves the source numbers. Production requests 15m directly; no local
resampling created the discrepancy. The cause inside the provider remains
UNVERIFIED. This is verification of archived evidence, not a new server probe.
Known mismatch quarantine remains SOURCE_INTERVAL_MISMATCH; no value was repaired.

All four datasets retain SOURCE_INGESTION_REJECTED, ZERO_VOLUME and
LIQUIDITY_REVIEW_REQUIRED. quality_reviewed and ingestion_eligible remain false.
**No stored quote-volume observations exist for any symbol**; quote_volume is
unavailable, not zero. Candle volume is in target-asset units, not INR turnover
or order-book depth. Close×asset-volume cannot invent executable quote liquidity.
No independently justified verified quote-volume threshold, historical spread/
depth/impact evidence or authoritative zero/no-trade convention is present.
Gaps/duplicates being zero cannot establish market quality or a fill.

Current active pair mapping is recorded, but historical listing/rebranding/
delisting identity, universe survivorship, authentic trade completeness and
historical constraint changes are not independently qualified. The quoted
source's nominal 120-day coverage is not a retention/listing-history guarantee.

## Chronology and period-level quality

The existing split remains fixed; no new favorable window was selected. Every
segment has 2,880 observed 15m bars per symbol:

| Segment | Start UTC | End exclusive UTC |
| --- | --- | --- |
| Pre-train warmup | 2026-06-19 14:30 | 2026-07-19 14:30 |
| Train | 2026-07-19 14:30 | 2026-08-18 14:30 |
| Validation | 2026-08-18 14:30 | 2026-09-17 14:30 |
| Planned final test | 2026-09-17 14:30 | 2026-10-17 14:30 |

Actual zero-volume exclusions by fixed segment:

| Pair | Warmup | Train | Validation | Test | Total |
| --- | ---: | ---: | ---: | ---: | ---: |
| BTC | 3 | 2 | 0 | 1 | 6 |
| ETH | 15 | 22 | 5 | 4 | 46 |
| SOL | 7 | 12 | 0 | 4 | 23 |
| DOGE | 65 | 81 | 20 | 29 | 195 |

These are **data-quality counts, not performance/market regimes**. Zero-free
BTC/SOL validation periods cannot bypass their preceding warmup exclusions,
source ingestion decision or missing liquidity qualification. Longest uninterrupted
positive-volume runs are BTC 6,060, ETH 1,910, SOL 4,503, DOGE 959: no full
unchanged 11,520-bar experiment is supplied by such a run. No period was shortened
or data combined with another window to obtain results.

The split plan supports independent fresh INR 2000 accounts, read-only past
warmup, next-bar entries and forced flat period boundaries. Period balances
must not be added as a continuous portfolio. Parameters are fixed; optional
sensitivity is train/validation only. Cost stress is predeclared at 2x each rate.
No historical strategy/test performance was observed or selected in this audit;
there is no independently sealed test set or technical lock against future
operator test-based tuning. Do not call an unexecuted final period a passed OOS test.

## Tasks 2–4 — preflight result, sizing and unavailable metrics

The existing eligibility loader rejected **all eight combinations** before any
strategy calculation or simulation:

| Symbol | SMA 5/20 | Momentum 12/0.01 | Permitted entry action |
| --- | --- | --- | --- |
| BTC | BLOCKED | BLOCKED | NO_TRADE |
| ETH | BLOCKED | BLOCKED | NO_TRADE |
| SOL | BLOCKED | BLOCKED | NO_TRADE |
| DOGE | BLOCKED | BLOCKED | NO_TRADE |

The earliest loader rejection is missing explicit historical quality review;
the separately verified zero/source/liquidity failures show why the review flag
cannot simply be enabled. In a guarded functional run, sockets, both strategy
calculations, PaperBroker, simulate, run_experiment and benchmarks were forbidden.
All eight preflight rejections completed with **zero signals, zero account
creation, zero experiments and zero orders**. These are preflight cases, not
eight simulated trades or eight strategy-generated NO_TRADE signals.

Archived last-close/public-metadata sizing still returns NO_TRADE at unchanged
INR 100 margin/1x. Observations are the bar closed 17 October 2026 14:30 UTC,
with public constraints observed 14:38–14:39 UTC; they are historical snapshots,
not current prices or verified constraints for every earlier candle.

| Pair | Reference INR price | Step / min quantity | Min INR notional | Rounded quantity | Modeled notional / 1x margin INR | Next stepped minimum margin INR |
| --- | ---: | --- | ---: | ---: | ---: | ---: |
| BTC | 8221532.7 | 0.00001 / 0.00001 | 100 | 0.00001 | 82.297542327 | 164.595084654 |
| ETH | 244000 | 0.0001 / 0.0000001 | 100 | 0.0004 | 97.6976000 | 122.122 |
| SOL | 10477.2 | 0.001 / 0.01 | 100 | 0.009 | 94.3890948 | 104.876772 |
| DOGE | 8.0731 | 1 / 0.001 | 100 | 12 | 96.9740772 | 105.0552503 |

Every rounded notional is below INR 100, and SOL also fails min quantity.
These are labeled hypothetical sizing explanations using existing assumptions,
not an order or recommendation to enlarge margin/leverage. Margin and notional
are distinct; they coincide numerically at 1x. A 3x ceiling cannot authorize an
unsupported real leveraged spot product. Snapshot sizing cannot prove no order
could ever fit every historical price/contract, and no eligible strategy entry
was generated to test such a proposition.

**Historical backtests executed: 0. OOS evaluations executed: 0.** All requested
performance fields in each preflight record are null:

| Requested result | Actual status |
| --- | --- |
| Closed-trade count/sample | Unavailable; no experiment, not a zero-trade backtest result |
| Gross fill P&L before fees / reference P&L before all modeled costs / net P&L | Unavailable |
| Win rate / expectancy / profit factor | Unavailable |
| Maximum drawdown / exposure | Unavailable |
| Fees / slippage / funding performance | Unavailable; configured costs are assumptions, unsupported funding is not invented |
| Benchmark comparison / cost sensitivity | Unavailable; no benchmark fills or stress returns calculated |
| Cross-symbol/time-period/regime robustness and parameter sensitivity | BLOCKED by eligibility; no rankings, optimization or regime labels |

The raw sample is 11,520 bars per symbol, 2,880 per planned segment; qualified
strategy sample is zero. An ending account balance is not reported because no
historical account was created. Prior paper rejection preserving INR 2000 is
not repurposed into historical profitability evidence.

### Methodology limits requiring evidence before performance claims

- Configured 0.1% fees/slippage per side are not independently calibrated
  executable costs. No historical order book, full-fill/queue model or separate
  spread is available. Funding, borrow, liquidation and taxes are unmodeled;
  no supported derivatives product/funding history makes invented costs valid.
- Stop gaps and adverse costs may exceed planned risk/daily thresholds. The
  model uses OHLC lows and conservative gap reference, but exact intrabar path,
  timestamps and high-water equity peaks are unknown. Exposure is bars touched,
  not elapsed holding time.
- The gate checks instrument step/minimums and real spot 1x, but historical
  metadata and price ticks are unqualified. InstrumentSpec has no maximum-size/
  price-tick fields; those checks exist in the offline exchange adapter, not as
  a claim that this backtester exercises a complete server contract.
- The existing buy-and-hold benchmark uses full affordable 1x capital and an
  abstract eight-decimal quantity, not verified public step/minimum rules; it
  has no strategy stops/daily limits and different exposure. It cannot yet be
  presented as an exchange-feasible or risk-matched comparison.
- Metric gross_profit/gross_loss are sums of winning/losing NET trades; trade
  gross_pnl already embeds slippage and excludes fees. Exact definitions are
  frozen in the rules document; no double subtraction or fabricated return.
- No strategy dataset optimization occurred. One symbol per independent run,
  four currently active assets, and operator-managed test discipline cannot
  establish portfolio/regime robustness, avoid survivorship or prove future returns.

These are disclosed limitations, not permissions to relax protections. No
confirmed new production defect required changing existing working code.

## Tests, exact commands and reproducible evidence

| Actual Linux run | Passed | Failed | Errors | Skipped | Total | Seconds |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Full default baseline | 633 | 0 | 0 | 1 | 634 | 30.118 |
| Strategy/backtesting/gate/interval/sizing group | 245 | 0 | 0 | 0 | 245 | 14.630 |
| **Final full public-enabled discovery** | **634** | **0** | **0** | **0** | **634** | **29.346** |
| Native Windows | N/A | N/A | N/A | Not executed | N/A | N/A |

The optional public discovery/recent-candle test is the baseline's sole skip;
it actually passed in final discovery. No available Linux test remained skipped
or unrun. Existing tests are synthetic/mocked software verification, including
costs, next-bar/no-lookahead, stops/gaps, source rejection, duplicate signals,
leverage/budgets/daily count/halts, one position, persistence/process restart,
unknown exchange state and disabled live/manual execution. No old test was
changed and no redundant new unit tests were added. The new read-only audit
tool's actual rejection path and no-side-effect guards were functionally checked;
not every helper error/eligible-input branch was individually unit-tested.

Exact commands, from repository root:

~~~bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m unittest tests.test_backtesting tests.test_chronological_evaluation tests.test_strategy_engine tests.test_signal_verification tests.test_engine_cli tests.test_central_risk tests.test_interval_trace tests.test_minimum_diagnostics -v
COINDCX_RUN_PUBLIC_INTEGRATION=1 .venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m tools.phase8e_trace --replay reports/phase8e-trace
.venv/bin/python -m tools.phase8f_audit --output reports/phase8f-audit
git diff --check
~~~

Choose a NEW output directory on rerun; existing artifacts are never overwritten.
The initial ordinary audit used the identical original rules file under reports/;
the final guarded run used the published docs/examples/phase8f-rules.json. Its
functional invocation added mocks that raise for socket.socket, SmaCross._calculate,
Momentum._calculate, PaperBroker, simulate, run_experiment and benchmarks, then
called tools.phase8f_audit.run with source/trace/rules and a new output directory.
No forbidden call occurred. Guarded results are in reports/phase8f-guarded;
this is not an added unittest count.

Logs: /tmp/phase8f-baseline.log, /tmp/phase8f-relevant.log,
/tmp/phase8f-full-public.log and /tmp/phase8f-stored-audit.log. Wrappers preserved
the actual Python exit code, for example:

~~~bash
COINDCX_RUN_PUBLIC_INTEGRATION=1 .venv/bin/python -m unittest discover -s tests -v > /tmp/phase8f-full-public.log 2>&1
result=$?; tail -n 6 /tmp/phase8f-full-public.log; exit "$result"
~~~

Compact evidence: [phase8f-evidence.json](examples/phase8f-evidence.json), with
per-period counts, exact preflight rejections, unavailable metrics, original
prices/constraints and hashes. Source contract references remain official
[markets](https://docs.coindcx.com/#markets),
[details](https://docs.coindcx.com/#markets-details) and
[candles](https://docs.coindcx.com/#candles). The retained Phase 8E documentation
snapshot SHA-256 is 4aa8e4e4a3f26cb626c847b651853734405dbcbe88a087963602964a0d7b2603;
no fresh documentation or historical data was fetched for this audit.

Public archived replay inputs are bundled locally in
reports/phase8f-replay-inputs.zip: **3,342,701 bytes**, 85 source files plus a hash
manifest, SHA-256
2ff6f63c3c03083592d53767c13ab06056189d7c1b52ec798e081cd64c2a3835.
It contains only original public history/trace artifacts and the frozen rules,
no database/account/credential/cache. Restore those relative archive directories
in an otherwise suitable checkout without overwriting existing data; tests alone
do not require these original captures. Replay requires the original bytes;
refetching changes fetch metadata and may reflect provider revisions. Hashes are
identity checks, not signatures or independent proof of market trades. Source
line-ending conversion also changes the frozen source hashes and must be disclosed.

## Requirement matrix and remaining blockers

| Requirement | Status | Evidence / remaining scope |
| --- | --- | --- |
| Inspect Phase 8E, source and stored datasets before changes | PASS | Existing archive/source inspected, source preserved, rules recorded before tests |
| Preserve INR 2000, leverage ceiling, risk/short/stop/emergency rules | PASS | All existing config/gate/broker/risk/state code unchanged; full regressions pass |
| Live disabled; no private endpoints, credentials, orders or Phase 9 | PASS | Offline audit/guarded preflight, unchanged disabled adapter, optional test public only |
| Actual 11,520 candles/pair, identity/timeframe/date range and raw provenance | PASS | Original page/raw-archive/CSV hashes and all 46,080 numerical matches |
| Timestamp order/boundaries/gaps/duplicates/completed OHLCV validation | PASS for structural sample | All aligned/complete/coherent; zero volume retained, no source quality inference from counts |
| ETH interval volume consistency | FAIL for archived sample | Exact 0.001239 ETH discrepancy; correct quarantine, no source repair; this is not a failing unit test |
| Provider's exact discrepancy/zero convention and historical identity | UNVERIFIED | Same-source observations/current metadata do not independently establish semantics |
| Identify eligible observations and executable quote liquidity | BLOCKED | No strategy-eligible sample; zero/source exclusions, no verified quote turnover/depth |
| Exact SMA/momentum entry/exit/stop/size/signal definition before tests | PASS for supported offline model | Frozen rules/hash record, no invented trading rules |
| Reproducible chronological historical/OOS performance | BLOCKED | Eight preflight rejections; no backtest/benchmark/signal/fill executed |
| Minimum-order feasibility under unchanged margin/leverage | BLOCKED | All four archived snapshot quantities NO_TRADE; historical feasibility not fabricated |
| Requested performance metrics/sample size/benchmark/cost sensitivity | BLOCKED | Nominal raw bars reported; all experiment metrics unavailable/null |
| Cross-symbol/period/regime/parameter robustness | BLOCKED for performance | Data-quality period counts verified; no optimization, performance rankings or regime claims |
| Relevant and complete available Linux tests | PASS | 245 focused and 634 final tests; no failures/errors/skips in final |
| Current native Windows and actual server execution | UNVERIFIED | No native runner/private server used; old Windows evidence does not cover this revision |
| Final diff, secret exclusions and preservation | PASS within checked scope | All existing code/tests retained, only two inherited docs changed, no staged files or known secret paths |

The audit is finished, but **Phase 8F historical strategy evaluation remains
BLOCKED**. Remaining prerequisites: authoritative source clarification or
independently reconcilable history, justified reviewed quote-liquidity evidence,
qualified contiguous warmup/evaluation periods, historical instrument/cost facts
and feasible requested sizes within unchanged limits. Execution/benchmark model
limitations must be resolved or explicitly bounded before claiming realistic
market performance. No flag toggle, fabricated quote volume, order enlargement,
new window/parameter tuning or skipped risk check is a valid substitute.

## Changed files and final preservation

Added docs/PHASE8F_RULES.md, docs/examples/phase8f-rules.json,
tools/phase8f_audit.py, docs/PHASE8F_AUDIT.md and docs/examples/phase8f-evidence.json.
README.md/VALIDATION.md point to the latest result. Generated public data/evidence
remain ignored. No dependency, existing application/test, .gitignore or
.env.example change. Phase-local comparison against /tmp/phase8f-before.zip:
**two inherited documentation files modified, five new files, 128 inherited files
byte-identical, none deleted**. All persistence-bound trading sources retain
their fingerprints. No account reset, staging, commit or push.

Known .env/secret/private-key exclusions and the empty index were checked without
printing values; .env.example retains exactly 20 blank BOT_* placeholders. These
checks do not constitute a comprehensive unknown-format secret or Git-history scan.

## Native Windows PowerShell instructions — not executed here

From a native Windows checkout with Python 3.12 and Git; preserve existing data:

~~~powershell
$env:PYTHONUTF8 = '1'
py -3.12 -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'venv creation failed' }
.\.venv\Scripts\python.exe -m pip install --no-index --no-cache-dir -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'dependency check failed' }
.\.venv\Scripts\python.exe -c "import sys,platform,sqlite3; print(platform.platform()); print(sys.version); print(sqlite3.sqlite_version); assert sys.platform == 'win32'; assert sys.version_info[:2] == (3,12)"
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
# Requires original stored history/trace archives and matching frozen source bytes.
# Choose a NEW output path; this command audits and never runs a backtest.
.\.venv\Scripts\python.exe -m tools.phase8f_audit --output reports/phase8f-local
if ($LASTEXITCODE -ne 0) { throw 'stored-data audit failed; do not reset or fabricate inputs' }
~~~

Native Windows remains UNVERIFIED until actually executed. Completion of this
audit does not authorize the next phase. Wait for explicit approval.
