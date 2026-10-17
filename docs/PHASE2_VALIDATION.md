# Phase 2 implementation and validation

This is the original implementation run record. The subsequent
[final audit](PHASE2_AUDIT.md) supersedes its test totals and network next steps:
150 unit tests passed, one integration test skipped by default; explicitly
running integration produced one proxy-access error. Two verified defects were
fixed with four new regression tests. Current live compatibility remains blocked.

Date: 2026-10-17. Branch: `phase2-market-data`, based on the verified Phase 1
commit `acde254c37b8f2f0fc84da00bd0a0012e2595cca`. No Phase 3 work, strategy
optimization, real orders, private endpoint requests, or credential requirements
were added. Phase 2 changes have not been committed or pushed.

## Changes reviewed

| Files | Change and reason |
| --- | --- |
| `data/schema.py` | UTC/Decimal, 15m normalized records with symbol/timeframe; preserve zero volume for reporting, reject invalid fields/values/ranges |
| `data/quality.py` | Validated DataPolicy, eligibility reasons, coverage, duplicate/order checks, incomplete exclusions, history/freshness, volume and quote-liquidity checks |
| `data/coindcx.py` | Three whitelisted unsigned public GET routes, native market discovery, documented millisecond range pagination, HTTP failures/retries, no-progress guards, default TLS and blocked redirects |
| `data/cache.py` | Local raw successful-response cache, fetch times/digests, TTLs, atomic replacement, no stale failure fallback |
| `data/storage.py` | Legacy/normalized CSV import, exact source retention, reproducible exports and reports, new review-required sidecars, no overwrite |
| `data/commands.py`, `cli.py` | `data markets`, `data fetch`, `data import`, `data validate`; structured API failure and noneligible exit status 2; no broker path |
| `data/loader.py`, `data/__init__.py` | Version-2 CSV adapter into existing Candle/MarketData, retained Phase 1 gates, ingestion flag and policy recheck |
| `data/policy.example.json`, `data/research-policy.example.json` | Default fail-closed liquidity policy and clearly explicit research override; no invented quote threshold |
| `tools/generate_sample_data.py` | Label synthetic fixture market status and unverified quote volume for reproducible inspection |
| `tests/market_fixtures.py`, `tests/test_market_quality.py` | Synthetic normalization, timestamps, missing/duplicate/order checks, invalid prices/volume/OHLC, current/future/stale data, eligibility and policy tests |
| `tests/test_public_market_data.py` | Mocked public requests, bounds/pagination, rate-limit delays, errors/timeouts, TLS/route guards, cache TTL/integrity/failure handling |
| `tests/test_data_pipeline.py` | CSV roundtrip/reproducibility/evidence, review reset, failed-ingestion gate, CLI import/inspect/fetch/error behavior without orders |
| `tests/integration/` | One opt-in unsigned public discovery/recent-candles check, disabled by default |
| `README.md`, `data/README.md`, `docs/COINDCX_API.md` | Architecture, actual CLI/Windows commands, exact official source, limits and quality assumptions |
| `docs/examples/eligibility.synthetic.json`, this file, `VALIDATION.md` | Actual labeled synthetic report, test results and outstanding access limits |

`config.py`, `risk/`, `paper_trading/`, `backtesting/`, `strategies/`, `.env.example`,
and `requirements.txt` are unchanged. The standard library handles HTTP, CSV,
UTC timestamps, Decimal, caching, and tests; pandas/requests are unnecessary.
All 81 existing Phase 1 tests still pass.

## Official API evidence

Reviewed CoinDCX's official `coindcx-official/rest-api` source at revision
`dc0b10dcc56742b22e3e63c5a7a30ed64cc0157e` (2022-03-31), whose CNAME is the official
documentation domain. It documents public discovery and candle start/end filters,
millisecond units, descending records, default 500 / maximum 1,000 candle limit,
intervals, asset-volume semantics, and error codes. See
[COINDCX_API.md](COINDCX_API.md) for immutable references and explicit limits.
The canonical site and live API remain unverified behind the cloud egress proxy;
the source snapshot must not be portrayed as a successful current live check.

## Executed tests

Exact command from the repository root:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Host: Linux, Python 3.12.14. **147 discovered, 146 passed, 0 failures, 0 errors,
1 skipped**. The skip is
`integration.test_coindcx_public.PublicReadOnlyIntegration.test_discovery_and_recent_candles`,
disabled unless `COINDCX_RUN_PUBLIC_INTEGRATION=1`. All unit network responses,
retry clocks/delays, cache clocks, and quality fixture times are controlled; unit
tests do not use live CoinDCX. No test failures occurred in the expanded runs.
Final review added an additional regression for malformed metadata attestations;
those now fail with a clear validation error. The final runner log reports
`Ran 147 tests` and `OK (skipped=1)`.
Phase 2 Windows execution was not performed; the earlier Windows result concerns
the original 81 Phase 1 tests only.

## Functional checks

- Generated `data/local/phase2-sample.csv`: 3,072 clearly synthetic 15m bars.
- `data import` and `data validate` with `--as-of 2024-02-02T00:00:00Z` returned
  exit 2 and `LIQUIDITY_REVIEW_REQUIRED` under the default policy, as intended.
  Their report shows 3,072 completed bars, zero missing bars, unassessed liquidity,
  and a synthetic warning; that actual report is bundled under `docs/examples/`.
- Import with `--policy data/research-policy.example.json` returned exit 0 and
  retained `QUOTE_LIQUIDITY_NOT_VERIFIED` / `NOT_ASSESSED` rather than claiming liquidity.
- `verify --data data/local/phase2-research.csv --allow-synthetic` exercised the
  version-2 adapter successfully and reported zero orders.
- `data markets --cache data/local/phase2-api-cache` attempted the documented
  unsigned discovery request and returned exit 2 / `API_FAILURE` /
  `ACCESS_DENIED` / HTTP 403. The proxy blocked the connection before the exchange;
  this is not a claim that CoinDCX itself rejected it or requires credentials.
- `git diff --check` passed. Final inspection includes untracked new modules,
  because `git diff` alone does not show them.

## Remaining limitations and exact next steps

1. Review/save the saved network draft additions `docs.coindcx.com`,
   `api.coindcx.com`, `public.coindcx.com` in environment settings, then publish
   the environment. This draft is confirmed saved; it did not apply runtime
   access or publish itself. No API keys were requested.
2. Retry `python -m cli data markets`, select a returned active INR pair, and
   use the README's exact bounded public fetch command. Run the opt-in integration
   test only after access works. Diagnose any schema difference against the
   current official documentation; do not disable checks or invent replacements.
3. Default public candle data lacks reliable quote turnover, so complete history
   alone is insufficient for strict liquidity eligibility. Supply properly reviewed
   quote-volume CSV data and a justified policy, or use the explicit research
   override with its warning for offline analysis only. No production threshold
   or real market's liquidity/history has been established here.
4. Legacy six-column files retain the Phase 1 gate; re-import to adopt version 2.
   Every transformed historical output needs new manual provenance review. CSV
   status/quote-volume assertions are operator attestations, not independent
   exchange verification. Digests and valid OHLC cannot prove authenticity.
5. No FX conversion, delisted-universe archive, trading realism improvements, or
   strategy changes were implemented. The INR account, leverage/risk ceilings,
   one-position rule, daily caps and emergency behavior remain Phase 1 controls.

Windows PowerShell verification (Git and Python 3.12 required):

```powershell
cd Coindcx-trading-bot
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-index -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Optional public integration, explicitly contacts only documented public GETs:

```powershell
$env:COINDCX_RUN_PUBLIC_INTEGRATION = "1"
.\.venv\Scripts\python.exe -m unittest tests.integration.test_coindcx_public -v
Remove-Item Env:COINDCX_RUN_PUBLIC_INTEGRATION
```

Phase 2 implementation/offline checks are complete; live compatibility is blocked
by external access. Phase 3 requires the user's separate approval.
