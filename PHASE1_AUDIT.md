# Phase 1 — foundation audit and safety verification

Completed 2026-10-17 on Linux with Python 3.12.14. Scope: the existing offline
backtest/paper foundation only. No CoinDCX connection, live order, credential
request, live-trading enablement, or profitability claim was made. Phase 2 has
not been started.

## Scope and Git state

Inspected configuration, CLI, broker, risk modules, simulation sequencing,
strategies, dataset loading, README, environment template, dependency file, tests,
and Git changes. Before this audit the working tree already contained the prior
foundation as untracked files, plus modified README and `.gitignore`. Git HEAD
still contains the initial README and ignore file. Consequently, `git diff` alone
does not show most application code; untracked files were inspected directly.
Pre-audit files were archived outside the checkout before edits. No existing
checkout, working changes, or source files were reset or recreated.

The requested position amount is interpreted as **margin collateral**; notional
is derived as margin × leverage. The requested defaults remain ₹2,000, 15 minutes,
1x leverage with a hard 3x ceiling, and backtest/paper modes only.

## Findings and changes

| Finding before audit | Result and affected files | Evidence |
| --- | --- | --- |
| Planned risk had a percentage ceiling only; it could exceed ₹20 after equity growth or configuration changes. | Fixed in [config.py](config.py) and [risk/sizing.py](risk/sizing.py): hard ₹20 maximum, lowerable but not raisable. Default 0.5% still budgets ₹10 at ₹2,000. Sizing also respects remaining daily/drawdown headroom. | `test_default_budget_is_ten_rupees_and_hard_ceiling_is_twenty`, `test_equity_growth_cannot_raise_absolute_risk_ceiling`, `test_remaining_account_budget_is_included_in_sizing` |
| Daily loss was 2% of day-start equity, so ₹40 was not an absolute ceiling. | Fixed in [risk/controls.py](risk/controls.py): lower of the percentage budget and ₹40. Net equity loss includes realized P&L, fees, and marked open P&L. UTC reset retains overnight gap losses against previous equity. | `test_rupee_daily_cap_does_not_grow_with_equity`, `test_daily_percentage_can_be_stricter_than_rupee_cap`, existing overnight-gap and latch tests |
| No maximum trades per day. | Fixed in [risk/controls.py](risk/controls.py) and [paper_trading/broker.py](paper_trading/broker.py): at most three filled entries per UTC day. Stops and winners count. The third position remains manageable; a fourth entry is blocked. Counts reset at the next observed UTC day. | `test_three_entries_per_day_counts_winners_and_blocks_fourth`, `test_third_entry_is_allowed_to_remain_open_and_exit`, `test_stopped_entries_count_towards_daily_limit` |
| Account stop prices used gross marked equity and did not reserve exit fee/slippage, allowing avoidable limit overshoot even without a gap. | Fixed in [paper_trading/broker.py](paper_trading/broker.py): solve for the pre-slippage trigger that leaves the target equity after both modeled exit costs. A triggered account limit latches even at Decimal rounding boundaries. | `test_account_trigger_reserves_exit_fee_and_slippage`, `test_unrealized_drawdown_closes_position_and_latches` |
| No emergency shutdown mechanism or handled Ctrl+C replay result. | Added latched `emergency_shutdown()` in [paper_trading/broker.py](paper_trading/broker.py). [backtesting/engine.py](backtesting/engine.py) requests cleanup on handled interrupts/errors. [cli.py](cli.py) returns 130 for interruption and reports partial replay results when available. Emergency flattening uses the last available candle close with costs and is idempotent. | Broker emergency tests, `test_keyboard_interrupt_flattens_and_reports_partial_run`, `test_strategy_error_requests_emergency_cleanup_and_propagates`, CLI interruption tests |
| `.env` was ignored, but `.env.local`, `.env.production`, and common secret files were not. | Broadened [.gitignore](.gitignore) for `.env.*`, credential/secret files and directories, and private-key extensions, with an exception for `.env.example`. [.env.example](.env.example) still contains blank setting names only, including the new limits. | All three tests in [tests/test_repository_safety.py](tests/test_repository_safety.py) |

These behavior changes were explained before editing. The ₹10–₹20 range is a
maximum planned-risk budget range, never a required minimum risk. Small positions
are not enlarged to risk ₹10. A requested ₹100 margin can therefore risk much
less. `max_planned_risk`, `daily_loss_amount`, and `max_trades_per_day` can be
tightened, but values above ₹20, ₹40, or 3 are rejected, including OS overrides.

Two existing broker tests were updated to reflect the new policy rather than
requiring twenty same-day trades or sizing past remaining daily headroom. They
still verify daily-loss lockout and now check reduced sizing. The future-candle
test now freezes the clock to remove wall-clock dependence. The suite grew by
27 tests, from 54 to 81.

## Controls verified

- [config.py](config.py), [tests/test_config.py](tests/test_config.py): rejects
  zero, negative, nonfinite, and malformed capital; leverage above 3x or below 1x;
  unsupported timeframes; notional amount mode; invalid stop/risk fractions;
  inconsistent percentage limits; and invalid absolute caps/trade counts.
  Only `backtest` and `paper` modes are accepted; `live` is rejected.
- [cli.py](cli.py), [tests/test_engine_cli.py](tests/test_engine_cli.py):
  `manual` aliases `verify`. Both evaluate a signal and fresh-account sizing
  preview, submit zero orders, and do not construct a broker. There is no live
  command or exchange transport. All four data commands pass with credential
  variables absent and socket construction/connections blocked in tests.
- [paper_trading/broker.py](paper_trading/broker.py): one position at a time;
  repeated BUY does not stack positions. Fee and slippage costs are adverse on
  both fills, margin is reserved rather than charged as a loss, and fees are
  included in net P&L. Illustrative 0.1% fee/slippage assumptions remain unchanged;
  they are not verified CoinDCX rates.
- [risk/stops.py](risk/stops.py), [risk/sizing.py](risk/sizing.py),
  [tests/test_broker.py](tests/test_broker.py), [tests/test_risk.py](tests/test_risk.py):
  positive finite stop triggers, valid stop fractions, intrabar and entry-bar
  stops, worse gap fills, affordable margin, cost-inclusive planned risk, daily
  resets, and drawdown/emergency latches are tested. SELL closes a long position;
  it never creates a short.
- [backtesting/engine.py](backtesting/engine.py): signals use completed candles
  and fill on the next open. History warmup and the final-bar no-fill behavior
  are tested. Paper/backtest accounting uses the same broker.
- [data/loader.py](data/loader.py), [tests/test_data.py](tests/test_data.py):
  INR-only, finite valid OHLCV, completed bars, gap-free unique timestamps,
  adequate history, provenance review, checksum verification, and explicit
  synthetic opt-in remain enforced by the CLI loader. Established and meme
  symbols receive the same structural checks.

## Test results

Exact command from the repository root, before and after changes:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

| Run | Executed | Passed | Failures | Errors | Skipped |
| --- | ---: | ---: | ---: | ---: | ---: |
| Existing baseline | 54 | 54 | 0 | 0 | 0 |
| Final Phase 1 | 81 | 81 | 0 | 0 | 0 |

No expected-failure or zero-test runs were used. No failing checks remain.
All tests ran on Python 3.12.14; Windows execution was not available here.

Additional isolated synthetic smoke checks generated 3,072 candles and exercised
`backtest`, `paper`, `verify`, and `manual` with `--strategy`, `--margin-amount 100`,
`--leverage 3`, and `--allow-synthetic`. Both simulations produced trades,
had at most three entries per UTC day, and returned identical JSON on repeat.
Both verification commands reported zero orders. `git diff --check` passed.
No real historical performance was evaluated.

## Remaining risks and unresolved issues

1. **Thresholds do not guarantee realized loss caps.** A gap can exceed the
   planned stop or ₹40 daily limit. A deterministic test explicitly produces a
   ₹50 gap loss and verifies that the loss is recorded honestly and further
   entries halt. The implementation never clamps a reported loss to the limit.
2. **Limits are per in-memory simulation account.** Restarting or running another
   process creates a fresh account; counters/halts are not durable or shared.
   `verify` does not check a persistent portfolio. It is not authorization to trade.
3. **Emergency cleanup is best-effort.** Tested interrupts/errors at replay
   boundaries flatten the simulated position. Forced termination, power loss,
   a second interrupt, arbitrary mid-mutation interruption, and durable recovery
   are not guaranteed. This is not an exchange-level emergency-stop service.
4. **Market realism is incomplete.** No order-book liquidity, partial fills,
   liquidation engine, funding/borrow costs, taxes, or CoinDCX lot/minimum-order
   rules are modeled. Drawdown uses bar opens/lows/closes, not the full tick path.
   Fixed slippage can understate thin meme-coin execution costs.
5. **Data provenance remains an operator attestation.** A checksum binds local
   bytes; it cannot prove authenticity, genuine volume, or liquidity. Raw USDT is
   rejected; timestamp-aligned INR conversion is not implemented. Directly
   constructing `MarketData` in Python bypasses the loader's provenance checks;
   use the documented loader/CLI for reviewed historical inputs.
6. **Some existing settings remain configurable.** Starting capital defaults to
   ₹2,000 but other positive values remain supported for independent simulations.
   Drawdown and percentage limits remain configurable within validation. Minimum
   history defaults to 30 days but can be lowered explicitly to 200 bars. The new
   absolute INR/trade ceilings and 3x leverage ceiling cannot be raised in settings.
7. **Git ignores are not a secret scanner.** Common sensitive paths are excluded
   and no such paths are tracked in the current index. Arbitrarily named secrets,
   secrets embedded in source, `git add -f`, and a comprehensive history scan are
   outside that guarantee. No credentials are needed or included by this project.

## Exact Windows test commands

In PowerShell, from the checkout's parent directory, with Git and Python 3.12
installed:

```powershell
cd Coindcx-trading-bot
py -3.12 --version
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-index -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

If `.venv` already uses Python 3.12, reuse it and run the last command. There is
no activation requirement, network package download, `.env` loading, or API-key
setup. The hygiene tests require local Git. This concludes Phase 1 only.
