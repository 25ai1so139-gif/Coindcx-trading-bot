# Phase 2 final audit and verification

Historical run record. [Phase 3 Gate 0](PHASE3_VALIDATION.md) subsequently reached
the current official site, aligned the candle endpoint, and passed public
integration. Its newer evidence supersedes this record's connectivity blocker;
the original test counts and limitations below describe the earlier audit.

Date: 2026-10-17. Host: Linux, Python 3.12.14.
Repository: 25ai1so139-gif/Coindcx-trading-bot, branch phase2-market-data.
Baseline commit: acde254c37b8f2f0fc84da00bd0a0012e2595cca.

**Offline verification: PASS. Current public API verification: BLOCKED.**
No Phase 3 work, private endpoint access, live orders, or profitability claims.
Existing Phase 2 files were inspected and amended; the project was not recreated.
No changes were staged, committed, or pushed during this audit.

## Requirement results

| # | Requirement | Status | Evidence and limits |
| --- | --- | --- | --- |
| 1 | Complete available unit suite | PASS | Final discovery: 151 tests, 150 passed, 0 failures, 0 errors, 1 optional integration skip. Separate enabled integration: 1 error; see below. |
| 2 | Inspect implementation and related tests | PASS | Reviewed loader.py, schema.py, quality.py, cache.py, coindcx.py, storage.py, commands.py, all three Phase 2 unit modules, fixtures and integration test; also CLI, risk, original tests and diff. |
| 3 | Verify every endpoint against official documentation | BLOCKED | All three routes match the official source revision below. Current canonical site and current server schemas could not be reached; snapshot agreement is not current live verification. |
| 4 | Public data without private credentials | PASS | Official unsigned examples for all three routes; transport creates GET without account authentication, rejects private/non-HTTPS routes and redirects. Covered by transport/discovery tests; no credential requirements added. |
| 5 | Read-only public smoke test | BLOCKED | Attempted discovery and enabled integration; proxy CONNECT 403 before an exchange response. Direct details/candles probes also blocked. |
| 6 | Candle normalization and data quality | PASS | 26 deterministic normalization/quality tests plus pipeline/API tests cover UTC, alignment, Decimal, duplicates, gaps, incomplete/future bars, invalid OHLC, volume, history and freshness. No actual market quality established. |
| 7 | Synthetic data remains clearly identified | PASS | Fixture module/docstrings, SYNTHETIC symbols, report kind/warnings, sample report filename and metadata; simulation requires explicit synthetic opt-in. No failed API request is replaced with fabricated candles. |
| 8 | Cache, rate limits, API errors and CSV | PASS | 29 mocked API/cache and 14 pipeline tests pass. TTL, integrity, retry/error handling, CSV review/evidence and reproducible exports tested. Actual server behavior remains blocked. |
| 9 | Phase 1 risk regression / live disabled | PASS | All 81 original tests pass independently. Config, risk, broker, engine and strategies are unchanged; manual/verify instantiate no broker and submit zero orders. |
| 10 | Final diff, assumptions and unresolved issues | PASS | Tracked diff and new files reviewed, whitespace clean; known limits and exact remaining work are recorded below. |

PASS for offline behavior means implemented and exercised by deterministic tests,
not evidence of exchange availability or trading performance.

## Verified defects and changes

1. **Rejected data could regain eligibility after re-import.**
   In data/quality.py, a source with 201 rows including one impossible high was
   correctly rejected. Its normalized export contained 200 valid rows and
   ingestion_eligible=false, so direct simulation loading rejected it. However,
   reassessing/re-importing that export previously returned eligible=true,
   forgetting the removed bad row. Version-2 input now preserves rejection as
   SOURCE_INGESTION_REJECTED unless its original ingestion flag is exactly true.
   CLI validation and re-import retain exit 2 and a rejected export; the loader
   remains blocked. Repair/reassess the original input and sidecar to change a
   policy or correct data. Do not use an already rejected normalized subset.
   Tests: CsvPipelineTests.test_reimport_cannot_erase_a_previous_ingestion_rejection
   and DataCommandTests.test_rejected_normalized_input_stays_blocked_in_cli.

2. **Timestamp range overflow escaped validation/cache recovery.**
   In data/schema.py, UTC conversion of an extreme offset could raise
   OverflowError. A corrupt cache fetched_at could therefore abort rather than
   become a cache miss. A normalized last-year candle could also be accepted
   even though its 15-minute closing time was unrepresentable. UTC conversion
   and record construction now reject these as ValueError; data/cache.py's
   existing corrupt-entry handler then returns a miss.
   Tests: NormalizationTests.test_timestamps_must_fit_utc_and_the_complete_candle_interval
   and ResponseCacheTests.test_overflowing_cache_timestamp_is_rejected.

The four new methods were run before the fix and reproduced the defects:
4 methods ran, unittest reported 5 failure entries and 3 error entries because
some methods have multiple subtests. They all pass after the fixes. There are
no remaining known failing unit tests. No risk settings were changed.

Also corrected data/loader.py's invalid-header explanation: version-2 failures
now name symbol/timeframe and optional quote_volume rather than claiming every
file requires only the six legacy columns. No accepted schema changed.

README.md and data/README.md now document the inherited rejection and current
results. COINDCX_API.md corrects the earlier instruction to publish a pending
network draft: the latest read found no pending draft and the three domains
already saved, although runtime requests still fail. PHASE2_VALIDATION.md retains
the original run as history and links to this audit; VALIDATION.md records the
new results.

## Commands and exact test counts

Commands were executed from the repository root with the existing venv.

| Run | Passed | Failed | Errors | Skipped | Total | Exit |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Baseline discovery before audit changes | 146 | 0 | 0 | 1 | 147 | 0 |
| Phase 2 unit modules after fixes | 69 | 0 | 0 | 0 | 69 | 0 |
| Original Phase 1 regression modules | 81 | 0 | 0 | 0 | 81 | 0 |
| Final complete discovery | 150 | 0 | 0 | 1 | 151 | 0 |
| Separately enabled public integration | 0 | 0 | 1 | 0 | 1 | 1 |

~~~bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m unittest tests.test_data_pipeline tests.test_market_quality tests.test_public_market_data -v
.venv/bin/python -m unittest tests.test_data tests.test_data_pipeline -v
.venv/bin/python -m unittest tests.test_config tests.test_risk tests.test_broker tests.test_data tests.test_engine_cli tests.test_repository_safety tests.test_strategies -v
COINDCX_RUN_PUBLIC_INTEGRATION=1 .venv/bin/python -m unittest tests.integration.test_coindcx_public -v
~~~

The first command was run for both the baseline and final discovery. Final
CSV loader/pipeline verification after the header-message correction passed
28/28 with no failures, errors or skips. Complete discovery was repeated after
that final code change and retained the totals above. Final
breakdown: configuration 9, risk 17, broker 19, original data 14, CLI/engine 15,
repository safety 3, strategies 4, quality 26, public API/cache 29, CSV/CLI
pipeline 14 passed. These add to 150.

Default discovery skips exactly
integration.test_coindcx_public.PublicReadOnlyIntegration.test_discovery_and_recent_candles
because COINDCX_RUN_PUBLIC_INTEGRATION is unset. The separately enabled run
attempted discovery but could not reach its assertions or candle-fetch stage.
Its error is PublicDataError(ACCESS_DENIED), caused by proxy CONNECT 403; it is
not a successful integration or a CoinDCX authentication response.

Pre-fix reproduction command:

~~~bash
.venv/bin/python -m unittest tests.test_data_pipeline.CsvPipelineTests.test_reimport_cannot_erase_a_previous_ingestion_rejection tests.test_data_pipeline.DataCommandTests.test_rejected_normalized_input_stays_blocked_in_cli tests.test_market_quality.NormalizationTests.test_timestamps_must_fit_utc_and_the_complete_candle_interval tests.test_public_market_data.ResponseCacheTests.test_overflowing_cache_timestamp_is_rejected -v
~~~

Logs are retained locally under /tmp/coindcx-phase2-audit-baseline.log,
coindcx-phase2-audit-reproduced-defects.log, coindcx-phase2-audit-fix-tests.log,
coindcx-phase2-audit-phase1-regressions.log, coindcx-phase2-audit-final-tests.log,
and coindcx-phase2-audit-public-integration.log. Those filenames after the first
share the same /tmp/ directory. A verified pre-edit source backup is
/tmp/coindcx-phase2-final-audit-before.zip. These are local artifacts, not commits.

## Official endpoint evidence

Canonical documentation: <https://docs.coindcx.com/>.

Re-cloned <https://github.com/coindcx-official/rest-api> during this audit.
Its current fetched HEAD was dc0b10dcc56742b22e3e63c5a7a30ed64cc0157e
(2022-03-31); its CNAME names docs.coindcx.com. This proves the reviewed official
source revision, not that an old source snapshot matches today's deployed API.

| Exact method and endpoint | Documented schema | Official source | Live result |
| --- | --- | --- | --- |
| GET https://api.coindcx.com/exchange/v1/markets | Array of active market strings | [Markets, lines 288–323](https://github.com/coindcx-official/rest-api/blob/dc0b10dcc56742b22e3e63c5a7a30ed64cc0157e/source/index.html.md#L288) | BLOCKED at proxy |
| GET https://api.coindcx.com/exchange/v1/markets_details | Array of objects; required fields consumed here are pair, symbol, base_currency_short_name (quote), target_currency_short_name (asset), status; coindcx_name is an optional name cross-check | [Details, lines 325–388](https://github.com/coindcx-official/rest-api/blob/dc0b10dcc56742b22e3e63c5a7a30ed64cc0157e/source/index.html.md#L325) | BLOCKED at proxy |
| GET https://public.coindcx.com/market_data/candles | Array of open, high, low, close, volume, time objects; prices/volume numeric, time opening epoch milliseconds; descending order, times unique | [Candles, lines 517–589](https://github.com/coindcx-official/rest-api/blob/dc0b10dcc56742b22e3e63c5a7a30ed64cc0157e/source/index.html.md#L517) | BLOCKED at proxy |

The full documented details example also contains currency long names,
min_quantity, max_quantity, min_price, max_price, min_notional, currency precision
fields, step, order_types, ecode, max_leverage and max_leverage_short. The data
client does not use these exchange execution fields or infer trading eligibility
from them. A market's leverage field does not change the local ceiling of 3x.

Documented candle intervals: **1m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 8h, 1d, 3d,
1w, 1M**. This project supports only 15m. Discovery endpoints have no interval.

Candle parameters: pair and interval required; optional startTime/endTime epoch
milliseconds; optional limit defaults to 500, maximum 1000. Use the returned
native pair. Volume is in the target asset, never assumed quote turnover.
The project filters [start, end); server inclusivity, oldest history, retention,
maximum date span and current numeric public request quota are undocumented.
The old commented rate note is not treated as a current quota. Local spacing,
bounded retries, page limits and TTLs are implementation policies.

[Official error table](https://github.com/coindcx-official/rest-api/blob/dc0b10dcc56742b22e3e63c5a7a30ed64cc0157e/source/includes/_errors.md)
lists 400/401/404/429/500/503. No invented server error-body schema is assumed.
All three public GET examples omit keys/signatures. The client has no private
API key parameter, account request, POST operation or order-submission method.

## Public smoke attempts

~~~bash
.venv/bin/python -m cli data markets --cache /tmp/coindcx-phase2-final-audit-cache
curl --connect-timeout 10 --max-time 30 --silent --show-error --dump-header /tmp/coindcx-audit-docs.headers --output /tmp/coindcx-audit-docs.html --write-out 'HTTP %{http_code}\n' https://docs.coindcx.com/
curl --connect-timeout 10 --max-time 20 --silent --show-error --output /tmp/coindcx-audit-details-response.json --write-out 'HTTP %{http_code}\n' https://api.coindcx.com/exchange/v1/markets_details
curl --connect-timeout 10 --max-time 20 --silent --show-error --output /tmp/coindcx-audit-candles-response.json --write-out 'HTTP %{http_code}\n' 'https://public.coindcx.com/market_data/candles?pair=B-BTC_USDT&interval=15m&limit=1'
~~~

Discovery returned exit 2 with API_FAILURE, reason ACCESS_DENIED,
http_status=403 and live_trading_enabled=false. Curl returned exit 56,
HTTP 000, and "CONNECT tunnel failed, response 403" for each direct probe.
The sample candle pair is from the documentation, not an assertion that it is
currently listed. No exchange response body or real dataset was obtained.

Saved environment settings list api.coindcx.com, public.coindcx.com and
docs.coindcx.com; there is no pending draft. This attached runtime still blocks
the requests. No proxy bypass, credential request, private route or live order
was attempted.

## Data quality, risk regression and repository hygiene

Normalization validates UTC-aware aligned timestamps, complete timestamp range,
finite Decimal values, positive OHLC, nonnegative volumes and coherent OHLC
bounds. Missing fields, mixed markets/timeframes, duplicates, unordered CSV,
missing intervals and out-of-window rows cannot silently pass the strict policy.
Current bars are excluded with a warning; future bars make eligibility fail.
Coverage uses explicit requested bounds when supplied and warns otherwise.
No synthetic filling, hidden deduplication or base-to-quote volume conversion occurs.

Default minimum history is 2880 bars, completeness 100%, freshness 30 minutes
relative to the specified evaluation time, no zero-volume bars, and verified
quote liquidity required. Public asset-volume data alone cannot satisfy strict
quote liquidity: the threshold is intentionally unset, so the default fails
closed. The research override leaves a visible NOT_ASSESSED liquidity warning.
Synthetic eligibility is a fixture-policy result, never market evidence.

Phase 1 tests confirm INR 2000 starting capital, margin sizing, at most 3x,
planned loss including fees and adverse slippage capped by percentage/INR 20/
remaining account budget, INR 40 or tighter daily limit, three entries per UTC
day, one position, stop/gap handling, persistent drawdown/emergency latches
within a run, and no-order manual/verify commands. INR 10 is the default risk
budget at starting equity, not a required minimum loss: small positions remain
smaller. Percentage and margin caps can tighten the absolute limits.

Git checks: no staged paths; only .env.example among tracked env/credential/
private-key candidates, and its values are blank. All three existing repository
hygiene tests pass. A current tracked/nonignored-content scan found zero matches
for common key/token/password assignments, GitHub/AWS key patterns or PEM
private keys. This is neither a full-history audit nor proof about every possible
secret format. git diff --check passed. The protected config/risk/broker/engine/
strategies, .env.example and requirements.txt have no diff from Phase 1.

## Remaining work and untested behavior

1. Resolve the attached runtime's proxy denial for the three already saved
   domains, or run the public-only commands in an environment with working
   access. Recheck current official documentation and rerun the enabled
   integration test; reconcile any real schema, pagination or boundary mismatch
   before declaring current endpoint compatibility.
2. Collect a real active INR market's history, verify actual requested coverage
   and provenance, and document defensible quote-liquidity measurements and a
   threshold. No real coin's history, liquidity, listing availability or retention
   has been validated. Current-active discovery also introduces survivorship bias.
3. Run the Phase 2 suite on native Windows. This audit executed on Linux only;
   the earlier Windows CI result covers the original 81 Phase 1 tests. This
   Phase 2 working tree has not been published to trigger Windows CI.
4. Live HTTP retries/Retry-After behavior, TLS, server limits and endpoint schemas
   have only mocked coverage here. Cache concurrent writers, filesystem failure/
   process-kill recovery, cross-process rate coordination and huge-scale ingestion
   are not fully tested. The cache is a local optimization, not a market-data
   authenticity or durability guarantee.
5. CSV status, liquidity and provenance review are operator attestations; local
   hashes cannot prevent deliberate relabeling or sidecar manipulation. Legacy
   CSVs keep the older Phase 1 gates until re-imported. The simulation loader's
   historical recheck uses the last candle close; it is not current feed-freshness
   validation. Use data validate without --as-of to check freshness now.
6. Existing Phase 1 limits remain: state/counters are in memory per replay,
   gaps can exceed planned stops/daily loss thresholds, fee/slippage rates are
   simulation assumptions (0.1% each by default), and emergency flattening uses
   the last available simulated close. No exchange kill switch, liquidation,
   funding, exchange lot-size model, FX conversion or delisted-universe archive
   has been established.

## Windows PowerShell verification

Run from an existing repository checkout; Git and Python 3.12 must be installed.
No activation policy change or private credentials are needed.

~~~powershell
Set-Location C:\path\to\Coindcx-trading-bot
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-index -r requirements.txt
Remove-Item Env:COINDCX_RUN_PUBLIC_INTEGRATION -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw "Unit tests failed." }
~~~

Optional public-only integration, once network access works:

~~~powershell
$env:COINDCX_RUN_PUBLIC_INTEGRATION = "1"
try {
    .\.venv\Scripts\python.exe -m unittest tests.integration.test_coindcx_public -v
    if ($LASTEXITCODE -ne 0) { throw "Public integration failed; inspect the error." }
} finally {
    Remove-Item Env:COINDCX_RUN_PUBLIC_INTEGRATION -ErrorAction SilentlyContinue
}
~~~

**Phase 3 has not started.**
