# Phase 3 final strategy audit

Date: 2026-10-17. Environment: Linux 6.18.55, Python 3.12.14.
Existing branch: phase2-market-data. Current Phase 1/2/3 working files preserved;
no reset, recreation, commit or push. No Phase 4 work or private endpoint access.
Short entries and live trading remain disabled.

**Final strategy/safety audit: PASS after two fixes.**
Real-market liquidity qualification and native Windows execution are not established.

## Requirement status

| # | Requirement | Status | Evidence / practical limit |
| --- | --- | --- | --- |
| 1 | Inspect strategies, verifier, settings, risk and related tests | PASS | Actual SMA/momentum, base/result/replay interfaces, CLI, snapshot/entry/sizing/stop/limit code, Phase 2 loader/quality/storage/client and relevant tests reviewed |
| 2 | Complete available suite and exact counts/environment | PASS | Final enabled full discovery: 206 passed, 0 failed, 0 errors, 0 skipped on Linux/Python 3.12.14 |
| 3 | No lookahead; incomplete, duplicate and insufficient data | PASS | Existing input/prefix/next-open tests pass; new result validation rejects future/stale decision timestamps, with emergency cleanup in replay |
| 4 | Zero-order manual/verify; no short entries; Phase 1 limits | PASS | Both aliases tested with sockets/broker construction prohibited; SHORT maps only to a long exit in replay and NO_TRADE in entry review; original limits retained |
| 5 | Timestamp, stop and risk-estimate correctness | PASS | Fixed Decimal-erased stop distance and unchecked strategy results; availability/model limitations are explicit below |
| 6 | Phase 2 integration; no synthetic/real liquidity confusion | PASS | All 69 data unit regressions and actual recent public integration pass; strict real-data quote-liquidity gate remains; no real market is declared qualified |
| 7 | Deterministic fixes/tests and reruns | PASS | Seven new test methods; confirmed failures reproduced before fixes, 72 affected tests and full suite passed afterward |
| 8 | No tuning or fabricated performance | PASS | SMA/momentum parameters and algorithms unchanged in this audit; no returns/win-rate/profitability claims |
| 9 | Final diff, secret exclusions and preservation | PASS | Existing source archived before edits, incremental changes reviewed including untracked files; whitespace/secret/index checks passed |
| 10 | Exact PowerShell instructions; honest platform reporting | PASS | Commands below; no native Windows test was executed or claimed |

Additional deployment/data facts: real-market liquidity qualification is
**BLOCKED pending reliable reviewed evidence**; native Windows execution is
**BLOCKED in this Linux-only session**. These are not passing market/execution claims.

## Confirmed defects and fixes

### 1. Decimal precision could erase a protective stop

Files: strategies/base.py and risk/sizing.py.

With the accepted positive fraction 1e-40 at normal prices, Decimal arithmetic
rounded the stop to exactly the entry. Both LONG and SHORT analytical candidates
remained directional, and manual LONG review could produce an entry_candidate
and cost-only risk preview with no actual protective distance. With fees and
slippage set to zero, sizing raised Decimal DivisionByZero.

Strategy references must now remain strictly below entry for LONG and above
entry for SHORT at the active Decimal precision; otherwise NO_TRADE /
INVALID_INDICATOR. Shared long sizing rejects a nonprotective stop, nonpositive/
nonfinite stop fill or per-unit stop risk before quantity calculation.

This adds runtime validation, not a new numeric policy or tuned minimum fraction.
Existing ordinary stop settings and risk ceilings are unchanged. The invalid
precision case now fails explicitly instead of approving an equal-entry stop.

### 2. Rich strategy results were trusted at the consumption boundary

Files: strategies/base.py, strategies/verification.py and backtesting/engine.py.

Synthetic reproduction showed manual approval of:
- A candidate timestamp after the evaluation time.
- A legacy Signal.SELL wrapped in StrategyDecision: signal=sell but
  entry_candidate=true with a long risk preview.
- A candidate with a different protective stop from the configured stop used
  by the sizer; its stop was silently superseded by a different modeled plan.

Built-in normal decisions were correct; the gap affected malformed/extended
strategy outputs, including overrides of evaluate. There were still zero orders.

A shared validate_decision now requires StrategyDecision with an explicit
Direction, matching strategy/symbol/timeframe, nonempty reasons,
finite named indicators, and an appropriate aware timestamp. A directional result
must use the last completed close/time and the configured protective stop.
NO_TRADE results may not propose entry/stop prices.

Manual review rejects invalid results as NO_TRADE / INVALID_STRATEGY_DECISION
before publishing a candidate or risk preview. Replay checks the result before
creating its next pending action; an invalid result triggers existing emergency
cleanup and propagates a clear error. The old signal-only compatibility path
remains available with its existing broker controls.

### New deterministic tests

- DecisionTests.test_unrepresentable_stop_distance_cannot_be_a_directional_signal
- ReplayDecisionTests.test_malformed_enriched_decision_halts_replay_before_any_entry
- PositionSizingTests.test_stop_distance_must_remain_protective_at_decimal_precision
- VerificationTests.test_signal_timestamp_is_last_close_not_the_later_review_time
- VerificationTests.test_invalid_strategy_results_cannot_get_a_verified_risk_preview
- VerificationTests.test_unrepresentable_stop_does_not_receive_manual_approval
- ManualCommandTests.test_both_aliases_reject_future_strategy_timestamps_without_orders

The existing cost-aware manual preview test now independently reconstructs the
modeled loss from quantity, stop fill, entry fee and exit fee. Six new methods
were run before fixing the defects: unittest reported 20 failure entries and
2 error entries because methods contain multiple subtests. All final methods
pass. The seventh is an additional positive timestamp check.

## Final test results and exact commands

| Run | Passed | Failed | Errors | Skipped | Total | Exit |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Audit baseline | 198 | 0 | 0 | 1 | 199 | 0 |
| Affected strategy/verification/risk modules after fixes | 72 | 0 | 0 | 0 | 72 | 0 |
| Phase 1 module group | 82 | 0 | 0 | 0 | 82 | 0 |
| Phase 2 unit module group | 69 | 0 | 0 | 0 | 69 | 0 |
| Final default full discovery | 205 | 0 | 0 | 1 | 206 | 0 |
| Final full discovery with public integration enabled | 206 | 0 | 0 | 0 | 206 | 0 |

The Phase 1 group includes all 81 existing tests plus the new sizing precision
regression. Strategy/verification modules now contain 54 tests: their previous
48 plus six new methods. 82 + 69 + 54 + 1 public integration = 206.

Commands executed from the existing repository root:

~~~bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m unittest tests.test_strategy_engine tests.test_signal_verification tests.test_risk -v
.venv/bin/python -m unittest tests.test_config tests.test_risk tests.test_broker tests.test_data tests.test_engine_cli tests.test_repository_safety tests.test_strategies -v
.venv/bin/python -m unittest tests.test_data_pipeline tests.test_market_quality tests.test_public_market_data -v
COINDCX_RUN_PUBLIC_INTEGRATION=1 .venv/bin/python -m unittest discover -s tests -v
~~~

Default discovery skips exactly
integration.test_coindcx_public.PublicReadOnlyIntegration.test_discovery_and_recent_candles,
which requires explicit opt-in. The final enabled run actually executed it;
no available test was skipped in that run. It uses only the three unsigned
whitelisted public routes, then checks normalized UTC/OHLC, completed candles,
ordering and uniqueness. It does not authenticate, access balances, or submit orders.

Final complete runner output: Ran 206 tests in 4.026s / OK.
Logs in /tmp/: coindcx-phase3-final-audit-baseline.log,
coindcx-phase3-final-audit-reproduced.log, coindcx-phase3-final-audit-affected.log,
coindcx-phase3-final-audit-phase1.log, coindcx-phase3-final-audit-phase2.log,
coindcx-phase3-final-audit-offline.log and coindcx-phase3-final-audit-complete.log.
Verified pre-edit archive: /tmp/coindcx-phase3-final-audit-before.zip.
These are local evidence files, not published artifacts.

## Signals, stop references and estimate availability

| Situation | Timestamp / price references | Risk estimate |
| --- | --- | --- |
| Valid LONG review with eligible data and fresh flat account | Signal time equals last completed candle close, even if review is 15 minutes later. Candidate references last close/configured stop. Verified top-level prices match the adverse entry fill and stop in the shared plan. | Available; includes modeled entry/exit fees and stop slippage, capped by existing percentage/INR/remaining-account budgets |
| Calculated neutral NO_TRADE | Last candle close; entry/stop None | None |
| Insufficient strategy warmup or invalid indicator | Refusal timestamp can be the evaluation time, not a new market signal; entry/stop None | None |
| Missing, stale, ineligible or changing input; invalid returned result | No accepted candidate; signal_timestamp and references None | None |
| Directional candidate rejected by missing/stale/blocked account state | Candidate's valid close timestamp and unapproved reference prices may remain visible; final signal is NO_TRADE | None; reference prices are not an approved cost-adjusted plan |
| SHORT candidate | Analytical above-entry stop reference may be shown, but final entry review is NO_TRADE | None; short execution/sizing is disabled |
| Invalid configuration or malformed CLI syntax | No usable signal/reference values; configuration refusal is structured NO_TRADE, syntax errors may produce usage only | None |

A modeled estimate is not a reliable bound on realized loss. The reference is
a completed candle close, not an executable current bid/ask. Freshness allows
up to 30 minutes or a stricter stored policy; --as-of is explicit historical
analysis, not current freshness. Fee/slippage defaults are illustrative 0.1%
per side. Gaps can exceed stops and daily thresholds; funding, taxes, liquidation,
exchange lot sizes and order-book fill realism are not established.

## Risk and data findings

Effective settings were checked as INR 2000, backtest mode, margin sizing,
maximum leverage 3, timeframe 15m, planned-risk ceiling INR 20, daily amount
INR 40 and at most three entries per UTC day. Initial percentage budget remains
INR 10 at starting capital; small positions are not forced to lose that amount.

All existing stop, fee/slippage, remaining-budget, daily loss, UTC reset,
drawdown/emergency, third-entry/fourth-entry and one-position tests pass.
Manual verification observes a copy of supplied controls and cannot consume
entries or clear latches. Repeated review is idempotent; actual simulated entries
remain counted by PaperBroker alone.

Phase 2 import/checksum/provenance/history gates and strict real-data quality
policy remain in use. A research override cannot disable real-market liquidity
review in manual verification. Synthetic opt-in and fixture/report labels remain
explicit. Public asset volume is not promoted to verified quote turnover, and
the default threshold remains unset. No real coin's complete history or reliable
liquidity was qualified by this audit. Tests with historical metadata are explicitly
labelled synthetic stand-ins, not actual market observations.

## Final diff and secret checks

Changed in this audit:
- strategies/base.py, strategies/verification.py, backtesting/engine.py:
  shared decision validation and protective-reference guard.
- risk/sizing.py: runtime precision/finite-risk guards.
- tests/test_strategy_engine.py, tests/test_signal_verification.py, tests/test_risk.py:
  deterministic regressions and independent modeled-loss assertion.
- README.md, VALIDATION.md, docs/PHASE3_STRATEGIES.md,
  docs/PHASE3_VALIDATION.md: current results/contract and historical-record pointers.
- docs/PHASE3_AUDIT.md: this new audit report.

SMA/momentum algorithms and parameters, config.py, broker/stop/limit policies,
Phase 2 implementation, requirements, .env.example and .gitignore are unchanged
relative to the start of this audit. Existing uncommitted/untracked work was
preserved; git diff alone does not include every new module, so files were also
reviewed directly and compared with the pre-audit archive.

git diff --check passed. No staged paths. The only tracked env/credential/
private-key filename candidate is .env.example, whose values remain blank.
Existing secret exclusion tests pass for .env variants, credentials/secrets
files and directories, .pem and .key files. Current tracked and nonignored
working-file scans found no common credential/private-key patterns. This is not
a full-history scan or proof against every possible secret format.

## Exact remaining work and next steps

1. Run the commands below on native Windows using this audited working tree;
   current code is uncommitted/unpushed. The earlier native Windows CI record
   covers Phase 1 only; no current Windows result is inferred from Linux/WSL.
2. Before any real-data signal is considered qualified, obtain reviewed sufficient
   INR historical data, independently reliable quote-volume evidence and a
   defensible threshold, plus a fresh actual simulated-account state. Keep the
   default real-data NO_TRADE behavior until those checks pass.
3. Account snapshots remain operator assertions and replay state remains
   in-memory. The audit does not establish durable counters/latches, cross-process
   execution coordination or truthfulness of manually edited files.
4. Current settings retain the existing ability to override starting capital for
   independent simulations; actual default/effective capital was INR 2000.
   No new restriction or silent change to Phase 1 configuration was introduced.
5. Custom rich strategies must satisfy the validated current-close/configured-stop
   contract. Alternative stop models, short entries and execution changes are
   unsupported here; no Phase 4 feature was introduced.
6. Review these local changes. Phase 4, publishing and real-money behavior require
   separate instructions; no further phase was started.

## Windows PowerShell commands

Install Git and Python 3.12. Run against the audited files from the repository root.
These are instructions, not a claim they were executed on Windows.

~~~powershell
Set-Location C:\path\to\Coindcx-trading-bot
git --version
py -3.12 --version
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-index -r requirements.txt
Remove-Item Env:COINDCX_RUN_PUBLIC_INTEGRATION -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw "Unit tests failed." }
~~~

Optional complete suite including public read-only integration:

~~~powershell
$env:COINDCX_RUN_PUBLIC_INTEGRATION = "1"
try {
    .\.venv\Scripts\python.exe -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) { throw "Complete verification failed; inspect the error." }
} finally {
    Remove-Item Env:COINDCX_RUN_PUBLIC_INTEGRATION -ErrorAction SilentlyContinue
}
~~~

No Phase 4, private CoinDCX request, real order or live-trading enablement occurred.
