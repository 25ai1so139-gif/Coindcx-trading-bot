# Phase 3 strategy and verification interface

Strategies produce analytical evidence; they cannot place orders. Python 3.12
standard-library code only. Existing INR 2000 capital, margin amount, 15m,
at-most-3x settings and Phase 1 risk ceilings are retained.

## Strategy contract

Implement strategies.base.Strategy, preferably by inheriting ValidatedStrategy.
The two registered implementations are frozen dataclasses.

~~~python
decision = strategy.evaluate(
    candles,
    as_of=utc_evaluation_time,
    symbol="SYNTHETIC-INR",  # labelled synthetic example, not a real market
    timeframe="15m",
    stop_loss_fraction=Decimal("0.02"),
)
~~~

Input is a sequence of data.models.Candle, ordered, unique, gap-free at 15m,
with aware UTC-normalizable opening timestamps, finite positive OHLC/volume,
and coherent OHLC bounds. Each candle must close by as_of; a future evaluation
clock is rejected. Validation covers the whole supplied sequence, not just the
indicator window. Invalid records, missing fields, future/incomplete candles,
missing intervals, duplicates, insufficient history or invalid indicators return
NO_TRADE with a reason. The direct replay API uses the same validation before
constructing a broker. Data provenance/liquidity eligibility is additionally
enforced by file loading and manual verification, not inferred from bare candles.

StrategyDecision fields:

| Field | Meaning |
| --- | --- |
| signal | Direction.LONG, Direction.SHORT or Direction.NO_TRADE |
| timestamp | Last completed candle's close for a calculated decision; evaluation time (or None for invalid time) for a validation refusal |
| strategy | Stable registry name |
| symbol / timeframe | Requested context, validated by the strategy and matched to metadata by manual review |
| entry_reference | Latest completed close for a directional candidate; None on neutral/invalid data |
| stop_loss_reference | LONG below reference, SHORT above reference, using the configured stop fraction; not a fill guarantee |
| reason_code / reason | Machine-readable refusal/evidence and explanatory text |
| indicators | Finite Decimal evidence used by the baseline rule |

The strategies are stateless. Re-evaluating the same closed history and context
returns the same result. No new account entry or counter change occurs. SMA only
signals on a new crossing; momentum can remain directional on successive bars.
Repeated manual review is idempotent, not an instruction to open repeated positions.

Returned rich decisions are validated again by manual verification and replay,
including custom evaluate overrides. Direction must be an actual Direction enum;
strategy/symbol/timeframe and reason/evidence must match the contract. Directional
timestamps must equal the last completed close, entry must equal its close price,
and stop must match the configured fraction on the protective side. Malformed
results cannot receive a risk preview; replay requests emergency cleanup.
Tiny positive fractions that round a stop to entry are refused. Shared sizing
also rejects nonpositive/nonfinite stop fills or per-unit risk before dividing.

## Baseline rules and parameters

| Strategy | Parameters / defaults | Minimum bars | Decision |
| --- | --- | --- | --- |
| sma_cross | fast=5, slow=20; integers, 1 <= fast < slow | slow + 1 | LONG when previous fast <= slow and current fast > slow; SHORT for the reverse crossing; otherwise NO_TRADE |
| momentum | lookback=12 positive integer; threshold=0.01 finite fraction strictly between 0 and 1 | lookback + 1 | Latest close / lookback close - 1; LONG at or above threshold, SHORT at or below negative threshold, otherwise NO_TRADE |

CLI flags: --fast / --fast-period, --slow / --slow-period, --lookback,
--threshold. Irrelevant parameters fail rather than being ignored. Registry
construction checks the class constructor's accepted keyword parameters.
Defaults and example thresholds were not optimized against the fixtures.

The old signal(candles) interface remains as a compatibility adapter returning
BUY/SELL/HOLD. New replay calls evaluate after a candle closes and executes
the resulting action at the next open. The existing simulator remains long-only:
LONG maps to BUY, SHORT to SELL (exit a long), NO_TRADE to HOLD. A SHORT does not
open a short. Manual entry verification returns NO_TRADE / SHORT_ENTRY_UNSUPPORTED
for SHORT candidates, retaining their evidence and protective reference. No short
risk estimate or funding/liquidation/borrow model is claimed.

## Manual review

Both manual and verify execute the same read-only path:

1. Validate requested symbol/timeframe and evaluation clock.
2. Reuse the existing CSV provenance, synthetic opt-in, checksum, history,
   completed-bar and structural gates.
3. Reassess with Phase 2 quality controls at the actual evaluation time; confirm
   assessed candles/context match the loaded signal inputs.
4. Calculate the strategy decision only on eligible, completed input.
5. Validate a supplied simulated-account snapshot, including freshness, kind,
   UTC day, finite balances, counters and boolean halt latches.
6. Observe a copy of RiskControls, then call the same risk.entry.entry_plan
   used by PaperBroker. Do not record an entry or mutate/persist the snapshot.
7. Print the decision, candidate evidence, reasons, quality report and risk
   preview when supported. Every report has orders_submitted=0 and
   live_trading_enabled=false.

Real historical data cannot use a research liquidity exemption in manual review:
require_verified_liquidity is forced true, completeness 100%, positive volume and
freshness <=30 minutes (or a stricter stored policy). A justified stored
min_quote_volume_per_bar and reviewed quote-volume evidence are required.
Explicit synthetic opt-in permits an offline synthetic exercise with an
unverified-liquidity warning; it is not real-market qualification.

Without --as-of, freshness is checked against current UTC. An explicit --as-of
allows historical verification and is recorded as evaluation_mode=historical;
it cannot be in the future and never claims current freshness. A dataset's own
last close is not silently substituted for now.

The candidate contains the strategy's reference close/stop. On a verified LONG,
top-level entry_reference and stop_loss_reference match risk_preview's adverse
entry fill and cost-aware stop. Planned risk includes both fees and stop slippage.
Missing/unusable state, failed data/risk checks and neutral/unsupported signals
return NO_TRADE. A completed review returns exit 0 for either verdict; inspect
signal/reasons, not just exit status. Invalid configuration/parameters return
exit 2 with structured NO_TRADE; malformed command syntax uses argparse exit 2.
Ctrl+C returns 130 and cannot submit orders.

## Account snapshot

--risk-state reads JSON; it does not create a paper account, write the file,
consume an entry, reset a UTC day or clear a latch. Missing state yields
RISK_STATE_REQUIRED. Both the data and account state must be fresh at the stated
evaluation time. State from a different UTC day is rejected until a fresh
consistent state is supplied, rather than assuming counters reset.

Required fields:

| Field | Validation |
| --- | --- |
| schema_version | Integer 1 |
| account_mode | paper or backtest; live rejected |
| kind | synthetic for synthetic fixtures; paper for real-data paper-account reviews |
| as_of | Aware timestamp, not after evaluation; age <=30 minutes or stricter data policy |
| starting_capital | Must match validated Settings (INR 2000 default) |
| equity | Finite; a depleted account is rejected by existing loss/risk logic |
| peak_equity | Finite, at least capital, equity and day_start_equity |
| day_start_equity | Finite and positive |
| day | ISO UTC date matching the evaluation/snapshot day |
| entries_today | Integer 0..configured maximum (at most 3) |
| has_open_position | Boolean; blocks new entries when true |
| daily_halted / drawdown_halted / emergency_halted | Actual booleans, retained as latches |
| label | Optional descriptive text, ignored by calculations |

The complete bundled example, examples/phase3-account.synthetic.json, is explicitly
fabricated for the generator's 2024-02-02 endpoint. It is not an actual account.
Do not relabel it as paper or change historical candles/state to appear fresh.

For in-memory integration, verification also accepts a VerificationAccount
holding existing RiskControls, marked equity, snapshot time and position flag.
It revalidates and copies those controls. Supply the actual simulated state:
no broker is constructed by the verifier and no state is inferred from a signal.
The file schema is a transport for the same review, not authenticated account
storage. Operator assertions and local hashes cannot prove that history or
account latches were honestly recorded.

## Preserved risk policy and limits

risk.entry.entry_plan is used for both broker entries and LONG verification.
It checks the existing one-position rule, Settings match, initialized state,
RiskControls.entry_block_reason and remaining equity-floor budget before
delegating to existing size_position. Broker alone records a simulated entry.

Initial percentage budget is INR 10 at INR 2000, capped at INR 20 and remaining
daily/drawdown budget; margin/cash constraints can make planned risk smaller.
Daily loss uses the lower of the existing percentage/INR 40 limit; at most
three entries per UTC day, one open position, and drawdown/emergency latches
remain unchanged. Gaps can exceed modeled thresholds. Fee/slippage defaults
remain illustrative 0.1% per side.

There is no persistent account service, exchange kill switch, short execution,
FX conversion, authenticated API, automatic order route, strategy optimization
or profitability evidence. Replays still start independent accounts; repeated
manual reviews of a snapshot do not provide cross-process execution coordination.
See README for exact Windows commands and PHASE3_VALIDATION.md for actual results.
The later final audit and updated counts are in [PHASE3_AUDIT.md](PHASE3_AUDIT.md).
