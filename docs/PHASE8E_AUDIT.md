# Phase 8E — market-data root-cause audit

17 October 2026. Existing repository and uncommitted work preserved. Execution:
**Linux 6.18.55 x86_64/glibc 2.41, CPython 3.12.14, SQLite 3.53.1**.
User-facing times below are IST; machine evidence retains explicit UTC.

**Audit/regressions PASS; market-data qualification and backtesting BLOCKED.**
The ETH volume discrepancy is already in the public source responses. No local
timeframe conversion/aggregation defect was found in the sampled production
path. The provider's precise aggregation/revision mechanism remains UNVERIFIED;
it was not "fixed" by substituting minute-derived values. A separate diagnostic
completion-check defect was reproduced, fixed and regression-tested.

No private endpoint, credentials, real orders, live/short enablement, risk-limit
increase, strategy optimization, indefinite worker or Phase 9 work. No real
backtest, market P&L or profitability claim. Native Windows remains UNVERIFIED.

## Gate 0 and preserved contract

Inspected [Phase 8D](PHASE8D_AUDIT.md), its raw history/ETH trace and actual
data/coindcx.py, schema.py, diagnostics.py, quality.py, storage.py, loader.py,
strategy validation/verification, chronological dataset/evaluation interfaces,
public instrument/minimum diagnostics, config and central gate. Existing tests,
Git index and inherited working changes were checked before edits.

The baseline completed with 615 passed, 0 failed, 0 errors, one optional public
skip, 616 total. No critical test blocker prevented this audit.

Unchanged: ₹2,000 initial simulated equity, ₹100 requested margin, configured
1x leverage and 3x ceiling, 15m, ₹10 initial planned-risk budget/₹20 absolute cap,
daily halt at min(₹40, 2% of applicable daily starting equity), three UTC-day
entries, one open position, stop-loss/drawdown/emergency controls, short entries
disabled and no live mode. Genuine spot is still restricted to 1x by the gate;
the 3x ceiling does not establish a supported leveraged product. No existing
paper account was reset or altered by the diagnostic tools.

## ETH: exact raw-to-strategy trace

Target native pair I-ETH_INR is confirmed active with ETH asset/INR quote by
public discovery/details. Target opening is **14 October 2026 05:00 IST**, closing
05:15 IST: UTC [2026-10-13T23:30:00Z, 23:45:00Z), epoch opening
**1791934200000 milliseconds**. The actual production response body is:

~~~json
[{"open":250244.2,"high":250244.2,"low":249701,"close":250218.5,"volume":0.086267,"time":1791934200000}]
~~~

| Stage | Observed behavior |
| --- | --- |
| PublicClient.history | Requests interval=15m directly; no 1m resampling. Exact native pair and explicit millisecond bounds; descending pages are retained and normalized ascending |
| JSON decode | Numeric decimals parsed as Decimal; volume is not defaulted, converted to INR or rounded to float |
| Timestamp normalization | Integer milliseconds → timezone-aware UTC opening 23:30; closed_at is 23:45. No seconds guessing, IST shift or close-time relabeling |
| CandleRecord / CSV | open 250244.2, high 250244.2, low 249701, close 250218.5, volume 0.086267; quote_volume remains unavailable |
| Diagnostic-only 1m comparison | Exactly 15 unique aligned openings 23:30–23:44, all complete. Derived OHLC matches the direct 15m bar exactly; volume sum is 0.085028 ETH |
| Quality/strategy boundary | Known mismatch → SOURCE_INTERVAL_MISMATCH; source ingestion/zero/liquidity exclusions retained. Actual verify_file returns NO_TRADE before strategy execution; no broker/order construction |

**Only volume differs: 0.086267 − 0.085028 = 0.001239 ETH.** Normalization
preserves the direct 15m value exactly. Data/intervals.py derives comparison
numbers only; it never creates replacement strategy candles or an approved size.

The fresh bounded trace started **20:13:14.210861 IST**, lasted **5.614799
seconds**, and made **8 unsigned API GETs, all HTTP 200**. It exercised production
history plus exact 15m limits 1/1000, a three-bar 15m neighbor window, exact 15
minutes and a 45-minute context window. Exact limit responses agree, and the
selected minute sum agrees between narrow/wide requests. Two neighboring 15m
bars match all five OHLCV values; only the target's volume differs. The preceding
flat zero bar also matches 15 zero-volume minutes, without proving actual trades
were absent. No gaps, duplicates or incomplete minutes explain the difference.

Exact target request parameters are pair=I-ETH_INR, startTime=1791934200000,
endTime=1791935099999; interval=15m with limit=1 or 1000, or interval=1m with
limit=1000. Context uses startTime=1791933300000, endTime=1791935999999. Local
window convention is [start,end); the public client sends end_ms−1 and filters
explicitly. No undocumented query parameter was added.

Fresh HTTP Date/ETag headers and exact raw body hashes are archived. This does
not prove the provider bypassed internal caches or promises identical correction
rules across intervals. Official semantics do not establish a zero/no-data
convention or explain this persistent discrepancy. No independent historical
trade reconciliation was available in the inspected pipeline. **Provider cause
UNVERIFIED; source qualification BLOCKED.** Replacing the bar with a computed
sum would hide the disagreement and is not supported by verified semantics.

## Confirmed diagnostic defect and changes

Before the fix, interval_volume_check could return MATCH when supplied 15 equal
minute volumes for a future/unclosed interval. It checked timestamp coverage but
not completion against an evaluation clock. This was a diagnostic false assurance,
**not the cause of the historical ETH mismatch**. Trading strategy/gate completion
checks were already separate and remain unchanged.

- data/diagnostics.py now checks interval close against explicit as_of or the
  current UTC clock. Unclosed/future intervals return UNVERIFIED with
  INCOMPLETE_OR_FUTURE_INTERVAL. Existing callers remain compatible.
- data/intervals.py adds a full read-only OHLCV comparator with mandatory explicit
  evaluation time and bound source-pair identity. It validates numbers, OHLC,
  timestamp units/alignment, exact half-open coverage, duplicate/gap/order and
  completion checks. Its output explicitly cannot verify trades/liquidity or
  authorize entry; source values are never mutated.
- data/quality.py additionally quarantines a known CROSS_INTERVAL_CANDLE_MISMATCH
  as SOURCE_INTERVAL_MISMATCH. Existing volume-only mismatches still block.
- tests/test_interval_trace.py adds **18 SYNTHETIC deterministic tests**, including
  the completion regression, UTC/IST equivalence, seconds/microseconds/fractional
  units, edge selection, missing/duplicate/scrambled minutes, invalid/missing OHLCV,
  flat zeros, exact volume differences/Decimal precision, wrong pair, direct-15m
  preservation and quarantine propagation through export/import, loader and verify.
- tools/phase8e_trace.py captures the bounded public trace, verifies all historical
  raw/CSV values, records review/minimum costs and supports exact-byte offline
  replay. It has no order sender or repair/approval path.

The new quarantine propagation test supplies otherwise eligible **synthetic**
history, proves the rejection survives export/import, and forbids strategy,
broker construction and sockets while reviewing it. No previous assertion was
removed or weakened. No verified source-semantic correction to the ETH values
was made.

## Volume, liquidity and minimum qualification evidence

Explicit finite nonnegative volume is structurally distinct from missing,
blank/null, malformed, nonfinite or negative volume. A flat zero is retained as
an observation; malformed values are rejected, never coerced to zero. Nonflat
zeros retain a distinct diagnostic. Genuine no-trade versus upstream no-data
remains UNVERIFIED. A match between two same-provider intervals is not independent
trade completeness or executable liquidity.

Both existing strategies still require strictly positive-volume execution
candles and the strict data screen. Research retention cannot authorize a fill.
No zero exception, replacement candle, invented quote turnover or lower
eligibility threshold was introduced.

Minimum evidence before this strategy can qualify a genuine historical symbol:

1. Exact asset/INR market identity, active status and reliable listing/rebrand/
   contract history for the evaluated period; current-active metadata alone
   cannot settle historical identity or survivorship.
2. Traceable raw source, hashes and explicit range; finite coherent OHLCV,
   unique aligned UTC openings, complete/gap-free candles, no future input and
   enough preceding history. The unchanged evaluation floor is 2,880 warmup
   bars plus three 2,880-bar evaluation periods. Do not fill missing intervals.
3. Known source contradictions resolved with authoritative evidence or a
   justified exclusion/quarantine scope. A zero-bar policy requires verified
   source semantics and an explicitly validated strategy/execution model;
   neither permission nor such a model is inferred here.
4. Verified quote-turnover provenance and units with an independently justified
   minimum threshold, plus suitable depth/spread/impact evidence for executable
   liquidity. Actual asset volume or close×asset-volume cannot replace this.
   A historical turnover screen alone is not proof of an executable fill.
5. Reviewed instrument/product constraints for the period: asset step/min/max,
   quote min-notional, price precision/tick, supported order type and leverage.
   Current public metadata is an observation, not authenticated old constraints.
6. Explicit both-side fee/slippage assumptions and evidence for their relevance;
   spread, partial fills, taxes/rounding and any product-applicable funding/borrow
   need appropriate treatment. No funding or leveraged spot product is invented.
7. A fresh central-gate decision with valid account/day/position/halts, protective
   stop and safely calculable margin/notional/risk. CSV flags or sizing alone
   cannot authorize an entry. Historical freshness uses its declared cutoff,
   never relabeled as current market freshness.

No inspected candidate currently meets this evidence set. Public discovery,
raw candles and metadata are useful inputs, not liquidity/quality attestation.

## Fresh genuine historical availability

Reused the existing capture tool without editing or recreating it:

~~~bash
.venv/bin/python -m tools.phase8d_readiness --output reports/phase8e-history
~~~

Its artifact format remains labeled Phase 8D; this is an actual new fetch during
Phase 8E. It started **20:08:33.722542 IST**, finished **20:09:12.122347 IST**,
duration **38.399805 seconds**, with **54 unsigned GETs, all HTTP 200**.
The same fixed BTC/ETH/SOL/DOGE INR sample and 120-day window were chosen before
fetching, with no return-based symbol/window selection.

All four datasets cover **19 June 2026 20:00 IST → 17 October 2026 20:00 IST,
end exclusive**: UTC [2026-06-19T14:30:00Z, 2026-10-17T14:30:00Z). First opening
is 19 June 20:00 IST; last opening is 17 October 19:45 IST, closed at 20:00 IST.

| Pair | Rows / complete | Gaps | Duplicate | Invalid OHLC/time/volume | Incomplete | Flat zero bars | Longest positive-volume run | Eligible |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| I-BTC_INR | 11,520 / 11,520 | 0 | 0 | 0 | 0 | 6 | 6,060 | No |
| I-ETH_INR | 11,520 / 11,520 | 0 | 0 | 0 | 0 | 46 | 1,910 | No |
| I-SOL_INR | 11,520 / 11,520 | 0 | 0 | 0 | 0 | 23 | 4,503 | No |
| I-DOGE_INR | 11,520 / 11,520 | 0 | 0 | 0 | 0 | 195 | 959 | No |

All **46,080 raw records match normalized CSV OHLCV exactly**; source pages are
descending and normalized data ascending. The 270 zeros are all explicit flat
source records. All primary reports fail ZERO_VOLUME/LIQUIDITY_REVIEW_REQUIRED;
reassessment also preserves SOURCE_INGESTION_REJECTED, with ETH adding
SOURCE_INTERVAL_MISMATCH. Original raw/CSV/sidecar files were not rewritten.

Nominal 120-day count supports the planned 30-day warmup and three 30-day periods:
warmup 19 June–19 July, train 19 July–18 August, validation 18 August–17 September,
test 17 September–17 October, all boundaries at 20:00 IST, 2026. **None is a
qualified dataset.** Positive subruns above are diagnostics, not chosen backtests;
none supplies the unchanged full evaluation length. No interval was dropped or
filled to create an eligible sample. Historical listing identity/retention
guarantees, independent source completeness and quote liquidity remain unverified.

**Genuine backtests/OOS executed: 0.** Market trade count, net P&L, drawdown,
expectancy, profit factor and benchmark performance are unavailable, not invented
zeros. Unit-test synthetic accounts/returns do not provide real-market evidence.

## Public instrument constraints and minimum-order arithmetic

Fresh public metadata observed BTC 20:08:47.518544, ETH 20:08:56.229552,
SOL 20:09:04.849230, DOGE 20:09:12.120149 IST. These timestamps bind the snapshots;
they are not current entry permission. References below are all the completed
bar opening **17 October 19:45 IST**, closed **20:00 IST**, not executable quotes.
Capture started 8 minutes 33.722542 seconds after that close.

| Pair | Reference INR price | Asset step | Minimum quantity | Maximum quantity | Minimum INR notional | Asset / quote decimals |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| BTC | 8221532.7 | 0.00001 | 0.00001 | 2 | 100 | 5 / 1 |
| ETH | 244000 | 0.0001 | 0.0000001 | 20 | 100 | 4 / 1 |
| SOL | 10477.2 | 0.001 | 0.01 | 10000000 | 100 | 3 / 1 |
| DOGE | 8.0731 | 1 | 0.001 | 200000 | 100 | 0 / 4 |

CoinDCX calls the quote currency base_currency; min_notional is in that quote
currency (INR here). Step/min/max quantity are asset units. Base-currency decimal
precision does not independently establish a server price tick or valid slipped
limit price. Instrument.validate_size and disabled execution remain unchanged.

At unchanged 1x, notional = quantity×modeled entry and margin = notional/leverage.
The existing model estimates 0.1% adverse slippage and 0.1% fee on **each** side;
entry = reference×1.001, stop = entry×0.98, no-gap stop fill = stop×0.999.
The existing sizer rounds quantity DOWN; fees are additional cash, not collateral.

| Pair | Down-rounded candidate | Candidate notional / 1x margin INR | Entry fee INR | Planned stop risk INR | Outcome |
| --- | ---: | ---: | ---: | ---: | --- |
| BTC | 0.00001 | 82.297542327 | 0.082297542327 | 1.88947092023643954 | NO_TRADE |
| ETH | 0.0004 | 97.6976000 | 0.0976976000 | 2.243041152352000 | NO_TRADE |
| SOL | 0.009 | 94.3890948 | 0.0943890948 | 2.167081115295096 | NO_TRADE |
| DOGE | 12 | 96.9740772 | 0.0969740772 | 2.226429777916344 | NO_TRADE |

Each candidate is below ₹100 min_notional; SOL is also below 0.01 minimum
quantity. The next permitted lot exceeds the ₹100 margin ceiling:

| Pair | Arithmetic stepped minimum quantity | Minimum modeled notional / 1x margin INR | Estimated entry fee | Estimated stop exit fee | Margin + entry fee | Planned no-gap stop risk |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| BTC | 0.00002 | 164.595084654 | 0.164595084654 | 0.16114187977795908 | 164.759679738654 | 3.77894184047287908 |
| ETH | 0.0005 | 122.122 | 0.1221220000 | 0.119559880440000 | 122.2441220000 | 2.803801440440000 |
| SOL | 0.01 | 104.876772 | 0.104876772 | 0.10267645732344 | 104.981648772 | 2.40786790588344 |
| DOGE | 13 | 105.0552503 | 0.1050552503 | 0.102851191148706 | 105.1603055503 | 2.411965592742706 |

These are arithmetic lower bounds at modeled prices, **not fully validated
orders, settings recommendations or fills**. They omit unverified server tick,
actual fee rounding/taxes, book spread/impact, partial-fill and historical
constraint evidence. Modeled risks below ₹10 do not override margin/minimums,
market ineligibility or account/stop/halt checks. Gap losses can exceed planned
risk. No amount, leverage or risk setting was increased; no risk approval issued.
No compliant full order was established. Funding/borrow is not modeled or
invented for an unsupported leveraged product. Actual paid fees/trades here: none.

## Official sources and retained provenance

Official https://docs.coindcx.com/ returned HTTP 200 over verified TLS at
2026-10-17T14:43:49.695743Z, 1,118,960 bytes; SHA-256
4aa8e4e4a3f26cb626c847b651853734405dbcbe88a087963602964a0d7b2603.
Raw HTML and extracted sections remain in reports/phase8e-official-docs.

| Official source | Contract / request scope |
| --- | --- |
| [Markets](https://docs.coindcx.com/#markets) | GET https://api.coindcx.com/exchange/v1/markets; active symbols, unsigned/no key |
| [Details](https://docs.coindcx.com/#markets-details) | GET https://api.coindcx.com/exchange/v1/markets_details; native pair, asset/quote identity, step/min/max/min_notional, decimal fields, limit support |
| [Candles](https://docs.coindcx.com/#candles) | GET https://api.coindcx.com/market_data/candles; OHLCV/time, volume in target asset, open time in ms, descending unique bars; 1m/15m/1h/1d; startTime/endTime optional ms; limit default 500/max 1000 |
| [Spot order-update](https://docs.coindcx.com/#get-order-update), documentation only | fee_amount in base/quote currency; not evidence of our configured fee rate, actual settlement or private server behavior |

Only official documentation and the original three public GET routes were
contacted. No authentication headers or credential input. Numeric public metadata
and raw API access passed; actual private/server execution remains UNVERIFIED.
The official public docs do not establish the provider's cross-interval revision
policy or zero convention. Local code cannot invent those missing semantics.

Raw bytes/query URLs/fetch timestamps/public cache headers/page and CSV hashes,
quality decisions, sizing assumptions and costs are retained under ignored
reports/phase8e-history and reports/phase8e-trace. Compact actual evidence:
[phase8e-evidence.json](examples/phase8e-evidence.json). Checksums establish
content identity, not signatures, historical identity or independent trade truth.

## Commands, test counts and replay

| Run on actual Linux | Passed | Failed | Errors | Skipped | Total | Seconds |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Full baseline | 615 | 0 | 0 | 1 | 616 | 16.512 |
| New interval regressions + old semantics | 39 | 0 | 0 | 0 | 39 | 0.059 |
| Combined data/sizing/risk/persistence/worker/exchange group | 452 | 0 | 0 | 0 | 452 | 8.282 |
| **Final full public-enabled discovery** | **634** | **0** | **0** | **0** | **634** | **18.051** |
| Native Windows | N/A | N/A | N/A | Not executed | N/A | N/A |

All 18 new and every existing test passed. The baseline's sole skip was the
optional public discovery/recent-candle test, which actually passed in final
discovery. No available Linux test remained unrun/skipped. All new fixtures and
private exchange mocks are labeled SYNTHETIC; no real order/fee server contract
or market return is inferred from them. Every new diagnostic tool network/error
branch was not individually unit-tested; normal capture and exact offline replay
were functionally tested, and existing client errors/retries remain covered.

Exact commands from repository root:

~~~bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m unittest tests.test_interval_trace tests.test_candle_semantics -v
.venv/bin/python -m unittest tests.test_interval_trace tests.test_candle_semantics tests.test_minimum_diagnostics tests.test_market_quality tests.test_data_pipeline tests.test_public_market_data tests.test_exchange_adapter tests.test_order_reconciliation tests.test_continuous_paper tests.test_persistence tests.test_central_risk tests.test_risk -v
COINDCX_RUN_PUBLIC_INTEGRATION=1 .venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m tools.phase8d_readiness --output reports/phase8e-history
.venv/bin/python -m tools.phase8e_trace --history reports/phase8e-history --output reports/phase8e-trace
.venv/bin/python -m tools.phase8e_trace --replay reports/phase8e-trace
git diff --check
~~~

The capture/trace commands refuse an existing output directory; choose new names
for a new fetch, retaining original artifacts. For this fixed historical window,
pass --end 2026-10-17T14:30:00+00:00 to the history tool. A refetch may reflect
provider revisions; replay retains exact captured inputs. Offline replay was
actually run with socket creation forbidden and reproduced all 46,080 matches,
the volume-only discrepancy and four NO_TRADE reviews with zero network/orders.

Logs: /tmp/phase8e-baseline.log, phase8e-interval-tests.log,
phase8e-relevant.log, phase8e-full-public.log and phase8e-public-trace.log.
Capture preserved Python exit status, for example:

~~~bash
COINDCX_RUN_PUBLIC_INTEGRATION=1 .venv/bin/python -m unittest discover -s tests -v > /tmp/phase8e-full-public.log 2>&1
result=$?; tail -n 6 /tmp/phase8e-full-public.log; exit "$result"
~~~

One exploratory documentation extractor used the wrong heading capitalization
and raised ValueError after saving the raw HTML; the corrected extractor passed
and retained all four sections. This was not a unit-test/product failure or a
source-data repair. No failing test remains.

## Requirement matrix and remaining blockers

| Requirement | Status | Evidence / remaining limit |
| --- | --- | --- |
| Inspect Phase 8D and actual source before edits | PASS | Existing reports/source/index inspected; baseline passed |
| Preserve equity profile, leverage ceiling, all risk/short/emergency limits | PASS | Config/gate/sizer/stops/broker/state/session unchanged; all risk/recovery regressions pass |
| Live disabled; no private endpoints, keys or real orders | PASS | Public-only transport unchanged, disabled exchange adapter tests pass; actual captures unsigned |
| No fabricated market data, liquidity or profitability; no Phase 9 | PASS | Original values retained, synthetic fixtures labeled, no real backtest or subsequent phase |
| Exact ETH discrepancy and raw/timestamp/timeframe/strategy trace | PASS | Volume-only difference at exact ms opening; no local resampling; direct normalization matches; strict verifier rejects |
| Resolve precise upstream ETH aggregation/revision mechanism | UNVERIFIED | Public semantics and same-source responses cannot establish cause; no unsupported correction |
| Admit ETH as eligible after a verified root-cause correction | BLOCKED | Persistent source contradiction, zero-volume and liquidity exclusions |
| Timestamp/timezone/boundary/duplicate/missing/incomplete regressions | PASS | 18 new deterministic tests; future/unclosed diagnostic MATCH defect fixed |
| Distinguish explicit zero from malformed/missing volume | PASS | Schema/diagnostics preserve structural zeros; malformed data rejected, no substitution |
| Independently verify zero intervals mean genuine no trades | UNVERIFIED | No authoritative zero convention or reconciled historical trades; quarantine retained |
| Market metadata and minimum qualification evidence documented | PASS | Public identity/constraint snapshots, official definitions and checklist above |
| Verified executable quote liquidity | BLOCKED | Asset volume is not quote turnover/depth; no justified verified threshold or historical execution evidence |
| Genuine historical availability and structural audit | PASS | Four 120-day, 11,520-row windows, no structural gaps/duplicates/incomplete bars; 46,080 exact value matches |
| Eligible history and untouched OOS backtest | BLOCKED | Strict data/metadata/liquidity/minimum-order requirements fail; no backtest or performance claims |
| Public minimum quantity/notional/margin/fee arithmetic | PASS | Actual documented metadata and unchanged sizing; exact numbers and assumptions retained |
| Compliant ₹100 margin order | BLOCKED | All four NO_TRADE; next lot exceeds requested margin; source eligibility also fails |
| Actual exchange fee tier/server price-tick/historical constraints | UNVERIFIED | Mock/local checks and configured estimates only; no private server exercise |
| Central gate, stop, daily halt/count, one-position, recovery and emergency regressions | PASS for tested offline APIs | Relevant 452 and complete 634 suites; persisted process-death/restart tests use synthetic accounts |
| Complete available Linux tests and final diff/secret exclusions | PASS | 634 pass, no failures/errors/skips; unchanged old assertions/core, empty index and known secret-path checks |
| Current native Windows / physical power-loss / sustained real-market operation | UNVERIFIED | Not executed in this Linux audit; no inference from old Phase 1 CI or bounded captures |

The audit is complete; **market-data/root-cause qualification remains BLOCKED**.
Remaining prerequisites are authoritative provider clarification or independent
reconcilable source evidence, justified liquidity/listing/instrument/cost review,
eligible contiguous history and a feasible requested configuration within the
unchanged limits. Do not toggle flags, erase zeros, substitute minute aggregates
or enlarge orders to obtain trades. No automatic follow-on phase is authorized.

## Final diff and preservation

Phase-local comparison against /tmp/phase8e-before.zip includes inherited
untracked work. Four inherited files changed: data/diagnostics.py,
data/quality.py, README.md and VALIDATION.md. Five files added:
data/intervals.py, tests/test_interval_trace.py, tools/phase8e_trace.py,
docs/PHASE8E_AUDIT.md and docs/examples/phase8e-evidence.json.
**121 inherited files are byte-identical; none deleted.** All pre-existing tests
and all 12 persistence-fingerprint-bound trading sources are unchanged. No
dependencies, configuration limits, database schema, permissions, .gitignore or
.env.example changed. No state balance/halt reset, staging, commit or push.

Known .env/secret/key paths and local response/database artifacts remain ignored;
.env.example still has 20 blank BOT_* placeholders. Tracked paths/index and
high-confidence new-file secret patterns were checked without printing values.
This is not a comprehensive unknown-secret-format or Git-history audit.

## Windows PowerShell verification — instructions only

Run from a native Windows checkout with Python 3.12/Git. No native Windows
execution occurred here; WSL/Wine/Linux PowerShell cannot establish it.

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
# Optional bounded public diagnostic; output directories must be NEW.
.\.venv\Scripts\python.exe -m tools.phase8d_readiness --output reports/phase8e-local-history --end 2026-10-17T14:30:00+00:00
if ($LASTEXITCODE -ne 0) { throw 'history capture failed' }
.\.venv\Scripts\python.exe -m tools.phase8e_trace --history reports/phase8e-local-history --output reports/phase8e-local-trace
if ($LASTEXITCODE -ne 0) { throw 'trace failed' }
.\.venv\Scripts\python.exe -m tools.phase8e_trace --replay reports/phase8e-local-trace
if ($LASTEXITCODE -ne 0) { throw 'offline replay failed' }
~~~

Capture/replay success means diagnostics completed, not trading qualification.
Live trading remains disabled. Await explicit approval before subsequent work.
