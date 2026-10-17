# Phase 3 validation record

This records the original implementation run. The subsequent
[final strategy audit](PHASE3_AUDIT.md) supersedes its totals: 206 tests passed
with public integration enabled, none failed/errored/skipped. That audit fixed
unchecked rich decision results and Decimal-erased protective stop distances;
the numeric risk limits and SMA/momentum rules remain unchanged.

2026-10-17. Linux / Python 3.12.14. Existing branch phase2-market-data.
No Phase 4, private API request, live order, strategy optimization, or profitability
claim. Phase 2 working changes were preserved in a verified pre-edit archive at
/tmp/coindcx-phase3-before.zip; nothing was reset, staged, committed or pushed.

## Gate 0 — PASS before strategy coding

Inspected PHASE2_AUDIT.md, COINDCX_API.md, actual implementation/tests and Git
changes. The previously recorded Phase 2 CONNECT-403 limitation was real for
that audit; it did not persist in this session.

1. Phase 2 unit modules: 69 passed, 0 failed, 0 errors, 0 skipped.
2. Original Phase 1 modules: 81 passed, 0 failed, 0 errors, 0 skipped.
3. Existing full discovery: 150 passed, 0 failed, 0 errors, 1 optional integration
   skip out of 151.
4. Explicit public discovery/recent-candle integration passed: 1/1.
5. Current canonical documentation returned HTTP 200. It names
   https://api.coindcx.com/market_data/candles and spot intervals 1m, 15m, 1h,
   1d, differing from the old 2022 snapshot. Strategy work was held while this
   difference was investigated. Bounded unsigned canonical GETs for active
   I-DOT_INR returned HTTP 200 and four candles with OHLCV/time schema.
6. Corrected the client candle URL and asserted it in the pagination test.
   Repeated full discovery: 150 passed/1 optional skip; integration against the
   corrected canonical route: 1 passed. Only then did Phase 3 strategy coding start.

Documentation: <https://docs.coindcx.com/#candles>, markets/details sections on
the same current site. Retrieved HTML SHA-256:
9026600440d6a9328124b85c07c688aa595bcc5010a4783a70c4720abad7bbbf.
Local capture: /tmp/coindcx-phase3-gate0-current-docs.html.

All three client routes remain unsigned GET-only HTTPS paths:
- https://api.coindcx.com/exchange/v1/markets
- https://api.coindcx.com/exchange/v1/markets_details
- https://api.coindcx.com/market_data/candles

Direct diagnostics with Python's default urllib User-Agent received HTTP
403 / Cloudflare 1010 browser_signature_banned. Curl and the project's existing
descriptive User-Agent succeeded for the canonical bounded request. Authentication,
TLS verification and redirect protections were unchanged. No credentials were
requested, and there was no private endpoint or proxy-policy bypass.

Only recent public compatibility was established. Whole-history coverage, real
quote liquidity, all market listings, historical survivorship and profitability
remain unverified. These do not authorize a signal from unqualified real data:
manual review still refuses insufficient history or unverified quote liquidity.
See COINDCX_API.md for current evidence and the historical source record.

## Changes relative to the start of Phase 3

| Files | Change / reason |
| --- | --- |
| strategies/base.py | Explicit Direction and StrategyDecision, UTC/closed/clean-candle validation, finite indicator evidence, NO_TRADE reasons and legacy replay adapter |
| strategies/sma_cross.py, strategies/momentum.py | Configurable validated baselines with directional/neutral decisions and evidence; existing default rule thresholds retained |
| strategies/__init__.py | Constructor-based parameter validation and factory; no silent irrelevant arguments |
| strategies/verification.py (new) | Offline data freshness/eligibility, consistent input snapshots, candidate and risk review; structured NO_TRADE and zero orders |
| risk/context.py (new) | Strict simulated-account snapshot schema; freshness/day/counter/balance/latch checks; copied existing controls |
| risk/entry.py (new), paper_trading/broker.py | Shared read-only entry planning delegates to existing RiskControls/size_position; broker alone records entries |
| backtesting/engine.py | Shared input preflight before broker creation; richer decisions evaluated only after close, next-open fills and legacy strategies retained |
| cli.py | Strategy parameters and manual symbol/timeframe/as-of/risk-state flags; no fresh-account assumption; structured configuration refusal |
| data/coindcx.py | Gate 0 correction to current official candle URL, still only three unsigned GET routes |
| tests/test_public_market_data.py | Assert canonical route in existing bounded-pagination test |
| tests/integration/test_coindcx_public.py | Normalize actual recent public candles and check close time, uniqueness and ordering |
| tests/test_strategy_engine.py (new), tests/test_signal_verification.py (new) | 48 deterministic synthetic strategy, data, risk, state and command tests |
| docs/examples/phase3-account.synthetic.json (new) | Fully labelled fabricated account for the historical synthetic command example, never actual account state |
| README.md, VALIDATION.md | Current architecture/behavior, exact Windows commands and executed results |
| docs/COINDCX_API.md, docs/PHASE2_AUDIT.md | Current endpoint evidence; preserve older audit as history and supersede its connectivity blocker |
| docs/PHASE3_STRATEGIES.md, docs/PHASE3_VALIDATION.md (new) | Interface/parameters/state contract, changed-file inventory, gate/test/smoke evidence and limitations |

No changes to config.py, risk/controls.py, risk/sizing.py, risk/stops.py,
.env.example, .gitignore, requirements.txt, the sample generator or the Windows
workflow were needed. Numeric Phase 1 risk limits were not changed. Manual
verification is intentionally stricter: it checks freshness now, requires state
for a directional entry review, and forces strict real-data liquidity/completeness.

## Exact final tests — PASS

| Run | Passed | Failed | Errors | Skipped | Total | Exit |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Original Phase 1 regressions | 81 | 0 | 0 | 0 | 81 | 0 |
| Phase 2 unit regressions | 69 | 0 | 0 | 0 | 69 | 0 |
| New Phase 3 tests | 48 | 0 | 0 | 0 | 48 | 0 |
| Default complete discovery | 198 | 0 | 0 | 1 | 199 | 0 |
| Complete discovery with public integration enabled | 199 | 0 | 0 | 0 | 199 | 0 |

From repository root:

~~~bash
.venv/bin/python -m unittest tests.test_config tests.test_risk tests.test_broker tests.test_data tests.test_engine_cli tests.test_repository_safety tests.test_strategies -v
.venv/bin/python -m unittest tests.test_data_pipeline tests.test_market_quality tests.test_public_market_data -v
.venv/bin/python -m unittest tests.test_strategy_engine tests.test_signal_verification -v
.venv/bin/python -m unittest discover -s tests -v
COINDCX_RUN_PUBLIC_INTEGRATION=1 .venv/bin/python -m unittest discover -s tests -v
~~~

Default discovery skips exactly
integration.test_coindcx_public.PublicReadOnlyIntegration.test_discovery_and_recent_candles,
disabled unless COINDCX_RUN_PUBLIC_INTEGRATION=1. The final enabled full run
actually executed it, including normalized UTC/OHLC/completed/unique/ordered
candle checks; nothing was skipped in that run. Public assertions establish a
small observation, not dependable long-term availability or liquidity.

Logs in /tmp/: coindcx-phase3-phase1-regressions.log,
coindcx-phase3-phase2-regressions.log, coindcx-phase3-strategy-tests.log,
coindcx-phase3-full-tests.log and coindcx-phase3-full-public-tests.log.
Final enabled run: Ran 199 tests in 2.355s / OK.

Development tests initially exposed a normalized CSV fixture without its matching
version-2 sidecar; the fixture was corrected without relaxing the loader. Further
tests exposed an inconsistent configuration-refusal report and NaN threshold
parse path; manual refusals now include NO_TRADE/entry_candidate=false/zero
orders, with threshold validation performed by the strategy constructor.
All final tests pass; no unresolved test failure remains.

## Safety and strategy coverage

| Requirement | Status | Tested behavior |
| --- | --- | --- |
| Gate 0 | PASS | Both prior phases' unit suites and actual canonical public integration passed before strategy coding |
| Modular input and decisions | PASS | LONG/SHORT/NO_TRADE, timestamp/name/reference/stop/reason/evidence; all supplied candles validated |
| SMA crossover | PASS | Both crossing directions, no crossing/repeated trend, custom periods, invalid windows |
| Momentum | PASS | Positive/negative inclusive thresholds, neutral band, lookback and parameter validation |
| No lookahead | PASS | Incomplete/future candles and future evaluation rejected; actual replay prefixes unaffected by later altered prices; decision executes only next open |
| Missing/invalid data and indicators | PASS | Missing records, insufficient history/warmup, gaps/order/duplicates, malformed/nonfinite values, invalid derived indicator and changing read snapshots |
| Risk integration | PASS | 3x setting ceiling; INR 10 initial budget/INR 20 ceiling; remaining daily budget; daily/drawdown/emergency latches, three-entry and one-position rules |
| Manual safety | PASS | Sockets/broker construction prohibited in deterministic tests; both aliases report zero orders, including rejected data/state/configuration |
| Repeated decisions | PASS | Pure repeated evaluations; repeated verification leaves account counters/latches and input/state files unchanged |
| Regressions | PASS | All 81 Phase 1 and 69 Phase 2 unit tests retained and passed |
| Windows execution | NOT RUN | Exact commands provided, Linux equivalents exercised; no native Windows runner executed Phase 3 |

## Executed command smoke checks

Generated the existing mathematical waveform (3072 candles) into a temporary
directory using tools.generate_sample_data.generate. Ran these through
.venv/bin/python -m cli, each with --data <temporary>/phase3-sample.csv
--allow-synthetic:

- backtest --strategy sma_cross --fast 5 --slow 20 --margin-amount 100 --leverage 1
- paper --strategy momentum --lookback 12 --threshold 0.01 --margin-amount 100 --leverage 3
- manual --strategy momentum --lookback 12 --threshold 0.01 --symbol SYNTHETIC-INR --timeframe 15m --as-of 2024-02-02T00:00:00Z --risk-state docs/examples/phase3-account.synthetic.json
- verify --strategy sma_cross --fast 5 --slow 20 --symbol SYNTHETIC-INR --timeframe 15m --as-of 2024-02-02T00:00:00Z --risk-state docs/examples/phase3-account.synthetic.json

All returned exit 0 and live_trading_enabled=false. Manual returned LONG /
POSITIVE_MOMENTUM, verify returned NO_TRADE / NO_CROSS, both with
orders_submitted=0. These are synthetic wiring observations only. No monetary
return is claimed or used to tune a parameter. Actual command invocations and
summaries are retained in /tmp/coindcx-phase3-cli-smoke.json; temporary CSVs were
removed. README contains the corresponding exact Windows PowerShell commands.

## Remaining limits / unverified behavior

- SHORT analytical signals have proper above-entry stop references, but the
  preserved broker/sizer remain long-only. Manual short entry is refused; no
  short fees, borrow/funding, liquidation or exchange execution realism is claimed.
- Snapshots are operator assertions, not authenticated or durable account
  storage. A caller can falsify a local file. Verification is read-only and does
  not coordinate entries across processes. Replays still start independent
  accounts; drawdown/emergency latches persist only within that account's life.
- No real coin's entire history, quote liquidity, eligibility or trading outcome
  was established. Public asset volume is not verified quote turnover. Real-data
  manual review stays NO_TRADE until strict policy and provenance gates pass.
- Recent public schema/route compatibility passed; service availability, rate
  quota, full pagination coverage for every market and long-term data stability
  are not guaranteed. No retry/TLS/authentication protections were weakened.
- Fee/slippage assumptions and gap losses remain Phase 1 limitations. Stops and
  daily loss thresholds cannot guarantee a maximum realized loss through gaps.
- Native Windows Phase 3 tests were not run; this host is Linux. The previous
  Windows CI record covers only Phase 1. No Phase 3 CI publication was requested
  or performed.
- Git diff --check, review of all changed/new files, source/secret exclusions,
  Markdown links and configuration defaults were checked. Final review preserves
  pre-existing Phase 2 source and untracked files; no credentials were added.

Phase 3 implementation and verification are complete within these documented
limits. Phase 4 has not started and requires separate user approval.
