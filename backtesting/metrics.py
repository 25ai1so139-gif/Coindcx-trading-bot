"""Decimal, net-of-cost metrics with explicit undefined and sample handling."""

from decimal import Decimal

from backtesting.engine import SimulationResult

ZERO = Decimal("0")


def calculate_metrics(result: SimulationResult) -> dict:
    pnl = [trade.net_pnl for trade in result.trades]
    wins = [value for value in pnl if value > 0]
    losses = [value for value in pnl if value < 0]
    profit, loss = sum(wins, ZERO), -sum(losses, ZERO)
    peak = result.starting_capital
    drawdown_inr = drawdown_fraction = ZERO
    max_notional = max_margin = ZERO
    leverage = []
    for observation in result.equity_observations:
        peak = max(peak, observation.equity)
        drawdown_inr = max(drawdown_inr, peak - observation.equity)
        drawdown_fraction = max(drawdown_fraction, (peak - observation.equity) / peak)
        max_notional = max(max_notional, observation.notional)
        max_margin = max(max_margin, observation.margin)
        if observation.effective_leverage is not None:
            leverage.append(observation.effective_leverage)
    streak = maximum_streak = 0
    for value in pnl:
        streak = streak + 1 if value < 0 else 0
        maximum_streak = max(streak, maximum_streak)
    events = result.risk_events
    daily = {event.timestamp.date().isoformat() for event in events if event.reason == "daily_loss_limit"}
    notices = ["Gross profit/loss sum winning/losing NET trade P&L; breakeven trades count in win-rate denominator.",
               "Slippage is already embedded in fill P&L; never subtract it a second time.",
               "Drawdown samples opens, lows when not stopped, closes and fills; highs/tick path are unknown.",
               "Exposure is fraction of bars touched by a position, including a partial bar; not elapsed holding time."]
    if len(pnl) < 30:
        notices.append("INSUFFICIENT_TRADE_SAMPLE: fewer than 30 closed trades; descriptive metrics only.")
    if not losses:
        notices.append("Profit factor undefined: no gross losses (including zero-trade runs).")
    nonpositive = sum(observation.equity <= 0 for observation in result.equity_observations)
    if nonpositive:
        notices.append("Notional/equity is undefined for nonpositive equity; those observations are excluded from leverage-ratio maximum.")
    return {
        "initial_equity_inr": result.starting_capital, "final_equity_inr": result.ending_equity,
        "net_pnl_inr": result.net_pnl,
        "net_pnl_percent": result.net_pnl / result.starting_capital * 100,
        "gross_profit_inr": profit, "gross_loss_inr": loss,
        "total_trades": len(pnl), "closed_trades": len(pnl), "open_positions": 0,
        "winning_trades": len(wins), "losing_trades": len(losses),
        "win_rate_percent": Decimal(len(wins)) / len(pnl) * 100 if pnl else None,
        "average_win_inr": profit / len(wins) if wins else None,
        "average_loss_inr": loss / len(losses) if losses else None,
        "profit_factor": profit / loss if loss else None,
        "max_drawdown_inr": drawdown_inr, "max_drawdown_percent": drawdown_fraction * 100,
        "expectancy_per_trade_inr": sum(pnl, ZERO) / len(pnl) if pnl else None,
        "fees_inr": result.total_fees,
        "slippage_inr": sum((trade.slippage for trade in result.trades), ZERO),
        "reference_price_pnl_before_costs_inr": sum((trade.gross_pnl + trade.slippage for trade in result.trades), ZERO),
        "exposure_bar_fraction": Decimal(result.exposed_bars) / result.bars if result.bars else ZERO,
        "maximum_marked_notional_inr": max_notional, "maximum_margin_inr": max_margin,
        "maximum_entry_leverage": max((trade.leverage for trade in result.trades), default=ZERO),
        "maximum_observed_notional_to_equity": max(leverage, default=ZERO),
        "nonpositive_equity_observations": nonpositive,
        "daily_loss_limit_activations": len(daily), "daily_loss_limit_dates": sorted(daily),
        "risk_activation_counts": {reason: sum(event.reason == reason for event in events)
                                   for reason in ("daily_loss_limit", "daily_trade_limit", "max_drawdown", "emergency_shutdown")},
        "maximum_consecutive_losses": maximum_streak,
        "largest_absolute_trade_pnl_fraction": max((abs(value) for value in pnl), default=ZERO)
            / sum((abs(value) for value in pnl), ZERO) if any(pnl) else None,
        "return_volatility": None, "sharpe_ratio": None,
        "risk_adjusted_metric_status": "NOT_ESTIMATED: no validated annualization, independent-return or sample assumptions",
        "notices": notices,
    }
