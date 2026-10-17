# Phase 4 backtesting interface and assumptions

Phase 5 subsequently added mandatory entry approval and decision-audit exports;
see [the remediation report](PHASE5_REMEDIATION.md) for the current entry contract,
stricter override rejection, reviewed instrument rules and risk_decisions.csv.
The Phase 4 accounting/split description below remains the historical foundation.

This extends the existing Python 3.12 engine and PaperBroker. It does not create
an exchange account/order client. All arithmetic in replay/evaluation uses an
isolated Decimal context: precision 28, ROUND_HALF_EVEN. Existing sizing rounds
quantity down to eight decimal places; that is an abstract simulator resolution,
not a verified exchange lot rule.

## Entry points and data contract

- `cli backtest` / `cli paper` retain single replay behavior and add quality,
  configuration, cost, equity and metric output. `paper` is still offline replay.
- `cli evaluate` requires CSV/sidecar, a split-plan JSON and a new output directory.
  It supports the same strategy/margin/leverage options, plus `--fee-rate`,
  `--slippage-rate`, `--data-policy`, `--data-as-of`, `--stress-multiplier` (default 2)
  and optional development-only `--sensitivity` JSON.
- `load_eligible` composes the original loader with Phase 2 `read_csv`/`assess`.
  Checks include checksum, provenance review, 15m/INR, finite positive coherent
  OHLCV, unique ordered gap-free completed candles, history, freshness, active
  status, existing ingestion rejection and quote-liquidity policy. Incomplete
  datasets are rejected before simulation; no candle is filled or invented.
- Real data requires a reviewed source, reliable quote-volume evidence and an
  explicit threshold. `require_verified_liquidity=false` cannot bypass that.
  The CLI rechecks legacy files too. Imported external provenance is identified
  separately from claimed CoinDCX public provenance; neither URL is proof of
  authenticity. Tests that change historical metadata use labelled synthetic
  stand-ins only.
- Synthetic input requires `--allow-synthetic` and stays synthetic in JSON,
  Markdown and CSV. Its liquidity status can remain NOT_ASSESSED. No eligible
  real dataset currently exists locally.
- Historical freshness is measured at dataset end by default, or an explicit
  historical cutoff. This is intentional for archival research and never a
  claim that the last candle is current. Cutoffs in the future are rejected;
  data beyond or incomplete at a requested cutoff is rejected. Simulation also
  rejects candles not closed at the actual clock.

`EligibleDataset` binds the assessed MarketData to a canonical digest. The
evaluator rejects replacement candles/metadata with reused eligibility evidence.
This guards accidental substitution; local metadata, class construction and
operator attestations are not authenticated security boundaries. Direct
`simulate` remains the original low-level numerical API: validate provenance
through `load_eligible`/CLI rather than constructing unreviewed MarketData.

## Chronological split contract

`SplitPlan` accepts `train_start`, `validation_start`, `test_start`, `test_end`
(aware UTC-convertible ISO datetimes aligned to 15 minutes), and
`min_evaluation_bars` (default 2,880, never below 200). Ranges are:

| Period | Included candle opening timestamps |
| --- | --- |
| Train | [train_start, validation_start) |
| Validation | [validation_start, test_start) |
| Test | [test_start, test_end) |

Every period needs complete exact coverage plus at least
max(settings.min_history_bars, strategy.minimum_bars) preceding warmup candles.
Each evaluation starts with a fresh ₹2,000 account, no position and fresh risk
counters. Prior completed candles warm indicators; they generate no warmup fills
or performance. A decision at the preceding candle close may execute at the
first evaluation candle open. Decisions during a period execute at the next
open. No last-bar signal creates a same-bar entry. Open positions are closed
at the final observed close with exit costs; their close time may equal the
exclusive period endpoint. No prior position, equity or order crosses a split.

This is a comparison of independent period accounts, not a continuous portfolio
or walk-forward optimization. Forced exits and fresh accounts affect performance;
do not add the ending balances. A small-period override does not establish
meaningful out-of-sample evidence. Fewer than 30 trades is explicitly flagged,
and 30 or more trades is still no significance guarantee.

Baseline parameters are explicit and frozen for all periods. A sensitivity file
contains full constructor objects for the selected strategy, such as the two
predeclared SMA objects in `examples/phase4-sma-sensitivity.synthetic.json`.
Alternatives are validated before execution and run only on train/validation.
There is no optimizer, automatic selection, test-period candidate ranking or
parameter mutation. The operator must reserve untouched test data across runs;
the software cannot prove that a human has never previously inspected it.

## Risk and cost accounting

The existing shared entry_plan, size_position, RiskControls and stop functions
remain authoritative. Defaults remain ₹100 requested margin, 1x leverage with
3x hard maximum, 0.5% initial planned-risk budget (₹10 at ₹2,000), ₹20 ceiling,
₹40 daily loss cap, at most three entries per UTC day, one long position,
5% drawdown halt and emergency latch. Small positions are never enlarged to
force ₹10 risk. Settings may tighten limits. No short position is supported.

| Item | Formula / interpretation |
| --- | --- |
| Entry fill | reference × (1 + slippage_rate) |
| Exit fill | reference × (1 − slippage_rate) |
| Fee per leg | quantity × filled price × fee_rate |
| Entry notional | quantity × entry fill |
| Reserved margin | entry notional / leverage; not a P&L expense |
| Gross trade P&L | quantity × (exit fill − entry fill), including slippage already |
| Net trade P&L | gross trade P&L − entry fee − exit fee |
| Slippage INR | quantity × [(entry fill − entry reference) + (exit reference − exit fill)] |
| Reference-price P&L | quantity × (exit reference − entry reference); net = reference P&L − slippage − fees |
| Open equity | cash + reserved margin + quantity × (mark − entry fill) |
| Realized P&L while open | previous net closed trades − current entry fee |
| Unrealized P&L | quantity × (mark − entry fill); future exit costs are not yet paid |

Risk sizing includes both fees and adverse stop fill; stops are recalculated
from the actual modeled entry fill, not guaranteed at the earlier analytical
signal price. Long stops trigger on candle lows; a gap uses the worse open, then
adverse exit slippage. Daily/drawdown price triggers reserve exit costs. Gaps
may exceed planned budgets and loss thresholds; losses are never clipped.
Entry leverage and marked notional/equity are separate quantities: price moves
change the latter even though the contractual sizing leverage stays fixed.

The shared CostModel derives rates from validated Settings. Default fee and
slippage are 0.001 **on each leg**, symmetric. They are user assumptions, not
verified CoinDCX schedules. No separate spread, historical funding, borrowing,
tax, liquidation, order-book participation, partial fill or exchange-size model
is invented. Leverage is only an abstract collateral simulation; real product
availability and instrument-specific charges are unverified.

Stress replays the same periods/parameters with both rates multiplied by two
(or `--stress-multiplier` >1), subject to existing 0..0.05 rate validation. It
records changed rates and may change sizing, halts and trades; total P&L need
not decrease monotonically because the trade path can change. Zero rates stay
zero when multiplied and the report discloses the uninformative stress case.
No parameters are selected on stress or final-test results.

## Metrics and uncertainty

All periods expose initial/final equity; net INR/percentage; summed positive
and absolute negative **net** trade P&L as gross profit/loss; trade/closed counts;
win percentage; average win and absolute average loss; profit factor; expectancy;
maximum INR/percentage drawdown; modeled fees/slippage; bar exposure; margin,
notional, entry leverage and marked notional/equity maxima; daily loss activation
dates/counts; other risk events; consecutive losses and largest absolute trade
P&L share. Breakeven trades count in win-rate denominator and reset loss streaks.

No trades => undefined win rate/expectancy/average wins/losses. No gross losses
=> undefined profit factor, not infinity or a valid zero. JSON uses null, CSV
empty cells and Markdown undefined. Zero-trade equity/P&L remains defined. Losses
and drawdown above 100% are recorded honestly. Nonpositive-equity notional ratios
are undefined and excluded, with an explicit count/warning. Volatility and Sharpe
are null/NOT_ESTIMATED because no annualization, return-independence and sufficient
sample assumptions have been established.

Drawdown uses the existing broker's sampled sequence: opens, entry effects,
intrabar lows when no stop fills, closes and exits. Unknown intrabar highs/tick
order are omitted; observed drawdown can understate full tick drawdown. Multiple
samples share opening timestamp with a phase label; close/low observations are
attributed to that candle's UTC opening day, not exact tick times. Intrabar stop
closed_at is the containing candle opening timestamp; it does not claim that
the stop executed at that exact second. Forced end/emergency exits use the last
close at closed_at, which can start a new UTC risk-accounting day. Final
entries_today is that final observed day's counter, not a full-run trade count.

Exposure is the fraction of evaluation bars touched by an open position,
including entry/exit or partial bars. It is not measured elapsed time. Execution
assumes the next open is tradable with zero additional decision latency beyond
the configured adverse fill; real fill availability is not established.

Benchmarks use actual supplied evaluation-period first open and final close,
the same initial capital and modeled costs. Buy-and-hold is 1x full affordable
capital, without strategy stops/daily limits; cash-only assumes no interest.
Their risk exposures differ from the strategy. Synthetic benchmarks are synthetic.
There is one symbol per run; multi-asset/regime attribution is not established.

## Report files and reproduction

Each new report directory contains `results.json`, `report.md`, `metrics.csv`,
`trades.csv`, `equity.csv` and `risk_events.csv`. Empty event/trade tables retain
headers. Every CSV row identifies run, data kind, symbol, timeframe, variant and
period. JSON contains the full configuration, ranges/warmup, quality policy,
data classification/provenance, CSV/sidecar/canonical-data digests, runtime Python
version, current source digest and deterministic content-based run ID. Decimal
values serialize as strings. Reports refuse overwrite and clean up newly created
partial output after a handled export failure; process death recovery is not
guaranteed. Large histories produce large reports; no streaming/OOM guarantee.

See the README for tested-equivalent PowerShell commands and PHASE4_AUDIT.md
for the exact Linux commands actually run. No native Windows Phase 4 run or
real-market out-of-sample result is claimed. Phase 5 is outside this work.
