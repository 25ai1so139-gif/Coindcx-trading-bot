# Phase 8F — rules recorded before testing

These are the actual existing implementation rules, recorded before Phase 8F
unit tests or any historical evaluation. They are not new trading rules or
optimized parameters. No historical experiment is authorized until eligibility
passes. See PHASE8F_AUDIT.md for the eventual data decision and test evidence.

## Configuration and strategy signals

Settings defaults: backtest mode, simulated INR 2000, requested **margin** INR
100, leverage 1x with absolute ceiling 3x, 15m, SMA strategy, risk_per_trade
0.005 (initial INR 10), max_planned_risk INR 20, stop_loss_fraction 0.02,
daily_loss_limit 0.02 with INR 40 cap, max_trades_per_day 3, max_drawdown 0.05,
max_margin_fraction 0.25, fee_rate 0.001, slippage_rate 0.001,
min_history_bars 2880. Genuine reviewed spot requires 1x, independently of the
3x ceiling. Live mode and short entries are unavailable.

- **SMA crossover**: fast=5, slow=20; require integer 1 <= fast < slow and at
  least slow+1=21 completed closes. Compute fast/slow means on the previous
  close and current close. LONG only when previous_fast <= previous_slow and
  current_fast > current_slow. SHORT only when previous_fast >= previous_slow
  and current_fast < current_slow. Otherwise NO_TRADE. A continuing trend is
  not another crossover. Ties on the current means do not trigger either side.
- **Momentum**: lookback=12, threshold=0.01; require positive integer lookback
  and finite 0 < threshold < 1. At least lookback+1=13 completed closes.
  r = latest_close / close_12_intervals_earlier - 1. LONG when r >= 0.01;
  SHORT when r <= -0.01; otherwise NO_TRADE. These are inclusive level tests,
  not threshold-crossing events: a sustained return can repeat LONG each bar.
- Shared validation requires finite positive OHLCV, coherent prices, unique
  ascending gap-free aligned 15m UTC candles closed by as_of, a valid symbol,
  valid timeframe/parameters and no future clock/data. Insufficient/invalid
  inputs or indicators yield explicit NO_TRADE with reasons, not invented values.
- Directional decisions have the last input candle's closing timestamp, raw
  latest-close entry reference, and analytical stop reference 0.98×close for
  LONG or 1.02×close for SHORT. NO_TRADE has no entry or stop. The SHORT stop
  reference is analytical only; it does not authorize a short position.

## Historical replay and exits

The engine additionally requires max(2880, strategy.minimum_bars) past candles.
In a chronological period its preceding warmup is read-only and cannot trade.
An earlier closed-bar decision is pending for the **next** bar's open; the
current bar is appended to indicator history only after pending processing.
No current high/low/close enters the prior signal. All supplied bars must already
be completed for historical replay; this is not a live fill model.

LONG maps to BUY; SHORT maps to SELL, which closes an existing long at the next
open. With no long it receives an unsupported-short rejection. NO_TRADE maps to
HOLD and does not automatically close a long. There is no take-profit, trailing
stop, time exit or reversal-to-short rule. Remaining positions close at period/
data end using the final close and modeled exit costs.

At each bar the broker: validates a strictly newer completed candle; observes
opening equity/risk; closes an existing position at the open if a halt is active;
handles SELL or gate-approved BUY at the open; then checks the long protective
stop and daily/drawdown equity floor against the bar low; finally observes close
equity. It logs bar-level events, not known intrabar execution timestamps.

Every BUY invokes the existing central gate immediately before the sole position
creation. Repeated BUY while open is rejected. The broker rejects duplicate or
backward timestamps; a signal is consumed only once per input bar. Momentum may
re-enter on a later continuing LONG after a stop, subject to fresh gate, daily
entry count and all halts; no additional signal cooldown is implemented.
Persistent candle identity prevention belongs to the separate durable paper API;
historical periods use independent in-memory accounts, not the paper database.

## Position sizing, costs and risk

Let R be next-open reference, f=0.001, s=0.001, L=configured leverage,
E=R(1+s), stop trigger T=E(1−0.02), modeled no-gap stop fill F=T(1−s).
Per-unit planned stop loss = E−F + f(E+F), including both fees and exit slippage.
The gate also rejects an opening reference at/below the prior analytical stop.
Actual position stop is calculated from modeled entry E and remains fixed.

With current equity Q, gate risk budget is the minimum of Q×0.005, configured
INR 20 cap, absolute INR 20, and remaining daily/drawdown equity-floor allowance.
Margin ceiling M=min(INR 100,Q×0.25). Maximum quantity is the minimum of
M×L/E, risk budget/per-unit stop loss, and cash affordability Q/(E/L+E×f).
The existing sizer rounds DOWN to instrument quantity_step, never increases a
quantity to fit minimums, and rejects nonpositive/unrepresentable quantity,
quantity below minimum, or notional below minimum. Notional=qE, margin=qE/L,
entry fee=qE×f; cash reserves margin+entry fee. Margin is collateral, not a fee.

Real history requires reviewed/eligible market and liquidity, verified spot
instrument/step/minimums/max-leverage, declared matching fee/slippage assumptions,
fresh data against evaluation time, protective stop and valid current account/
day state. It rejects existing position, emergency/drawdown/daily halt, the fourth
UTC-day entry, and all uncertain/missing entry evidence. Pure size calculation
or an old approval cannot bypass a fresh gate check.

Daily loss budget=min(INR 40,0.02×applicable daily starting equity). On UTC-day
change, the basis is the last observed equity, preserving overnight gap losses.
Daily halt stays latched that day; entry count resets on the next UTC day.
Five-percent peak-equity drawdown and emergency halt remain latched. Strategy
losses can be larger than planned budgets across gaps; nothing clamps reported
losses or guarantees a maximum realized loss.

For an open long, the broker solves a price that would leave the daily/drawdown
equity floor after adverse exit slippage/fees. Trigger=max(fixed stop,risk-floor
price), with stop taking the reason on equality. If low<=trigger, exit reference
is min(open,trigger), so a gap cannot fill at an advantageous stop price; actual
modeled exit=reference×(1−s). Newly opened positions can stop within their entry
bar. Halt exits are latched; emergency cleanup flattens at last validated close.
Unknown bar path, partial fills, spread/depth and physical execution latency are
not established by these OHLC rules.

## Evaluation, metrics and constraints

Default nominal split for the stored 120-day archive, all end-exclusive UTC:
warmup 2026-06-19 14:30→2026-07-19 14:30; train through 2026-08-18 14:30;
validation through 2026-09-17 14:30; test through 2026-10-17 14:30. Each segment
is 2880 bars. Each evaluated period starts a fresh INR 2000 account, reads only
its preceding warmup and is forcibly flat at its end. Do not add independent
period balances as though they were a continuous portfolio. Data-quality review
does not establish a sealed/untouched performance experiment.

The existing evaluator runs fixed baseline periods and a predeclared 2x cost
stress (fee and slippage each 0.002). Optional parameter-sensitivity candidates
are limited to train/validation; there is no automatic candidate selection.
No candidates or changed periods are chosen here. Operator discipline, not an
immutable test lock, must prevent subsequent test-based tuning. Funding/borrow/
liquidation/tax/partial fills and a separate bid/ask spread are not modeled; this
implementation has no verified derivatives product or funding history. Configured
fee/slippage values are assumptions, not verified exchange rates or impact data.

Trade gross_pnl=q×(exit_fill−entry_fill), already including slippage; net_pnl=
gross_pnl−entry_and_exit_fees. Metrics' gross_profit/gross_loss instead sum
winning/losing **NET** trade P&L and are labeled accordingly. Reference-price P&L
before costs adds embedded slippage back to trade gross. Do not subtract
slippage twice. Win rate uses net-positive trades / all closed trades, including
breakevens in the denominator; expectancy is mean net P&L; profit factor is net
winning sum / absolute net losing sum and is undefined without losses. Fewer
than 30 closed trades is explicitly an insufficient sample, not profitable proof.

Drawdown samples opening, fill, surviving intrabar low and close equity; unknown
intrabar highs are omitted. Exposure is fraction of bars touched, including
partial bars, not elapsed holding time. No Sharpe/annualized volatility is
estimated. Cash benchmark assumes no interest/inflation. Buy-and-hold uses full
affordable capital at 1x with same estimated costs and period endpoints, without
strategy stops/daily limits; its eight-decimal quantity is an abstract benchmark,
not validated public instrument step/minimum constraints or matched risk exposure.
Benchmark and performance values must remain unavailable if eligibility fails.

These rules are complete for the supported offline numerical model. They do
not establish execution realism, authenticated market eligibility or profitability.
Production config/risk/strategy/backtest code is not changed by this document.
