#!/usr/bin/env python3
"""
backtest.py  --  fast-forward the strategies over a whole price history.
=======================================================================

bot.py makes ONE decision per run (realistic, one day at a time). A backtest
instead replays a strategy across ALL the historical days at once, so you can
see in seconds how it WOULD have done -- and compare every strategy against
simply buying and holding the coin.

This is the honest way to judge a strategy BEFORE trusting it. Remember: good
past performance does NOT guarantee future results. Markets change.

    python3 backtest.py            # compare all strategies on real prices
    python3 backtest.py --demo     # compare all strategies on offline prices
"""

import sys

import config
import data
import portfolio
import strategy


def run_backtest(prices, strategy_name):
    """Replay one named strategy over the price history. Returns
    (final_value, trades_made, winning_sells)."""
    state = {"cash": config.STARTING_CASH, "coins": 0.0, "entry_price": 0.0}
    trades = 0
    wins = 0

    # Walk forward day by day, only using prices known "as of" that day.
    for day in range(2, len(prices)):
        window = prices[:day + 1]
        price = window[-1]
        holding = state["coins"] > 0
        action, _ = strategy.decide(window, holding, state["entry_price"],
                                    strategy_name=strategy_name)

        if action == "BUY" and not holding:
            spend = state["cash"] * config.TRADE_FRACTION
            if spend >= 1:
                fee = spend * config.FEE_PCT
                state["coins"] += (spend - fee) / price
                state["cash"] -= spend
                state["entry_price"] = price
                trades += 1
        elif action == "SELL" and holding:
            entry = state["entry_price"]
            proceeds = state["coins"] * price
            state["cash"] += proceeds - proceeds * config.FEE_PCT
            state["coins"] = 0.0
            state["entry_price"] = 0.0
            if price > entry:
                wins += 1

    return portfolio.total_value(state, prices[-1]), trades, wins


def main():
    use_demo = "--demo" in sys.argv
    if use_demo:
        prices = data.demo_closes(config.HISTORY_DAYS, seed=42)
    else:
        try:
            prices = data.get_closes(config.SYMBOL, config.INTERVAL,
                                     config.HISTORY_DAYS)
        except Exception as exc:  # noqa: BLE001
            print(f"Could not get prices: {exc}")
            return

    start = config.STARTING_CASH
    buy_hold = start * (prices[-1] / prices[0])  # the bar to beat

    print(f"\n=== Backtest | {config.SYMBOL} | "
          f"{'DEMO' if use_demo else 'LIVE'} | {len(prices)} days ===")
    print(f"  Starting cash: ${start:,.2f}\n")
    print(f"  {'strategy':<12} {'final $':>12} {'return':>9} "
          f"{'trades':>7} {'wins':>5}")
    print(f"  {'-' * 12} {'-' * 12:>12} {'-' * 9:>9} {'-' * 7:>7} {'-' * 5:>5}")

    results = {}
    for name in strategy.STRATEGIES:
        final, trades, wins = run_backtest(prices, name)
        results[name] = final
        ret = (final / start - 1) * 100
        star = "  <- current" if name == config.STRATEGY else ""
        print(f"  {name:<12} {final:>12,.2f} {ret:>+8.1f}% "
              f"{trades:>7} {wins:>5}{star}")

    bh_ret = (buy_hold / start - 1) * 100
    print(f"  {'buy & hold':<12} {buy_hold:>12,.2f} {bh_ret:>+8.1f}% "
          f"{1:>7} {'-':>5}")

    best = max(list(results.items()) + [("buy & hold", buy_hold)],
              key=lambda kv: kv[1])
    print(f"\n  Best over this period: {best[0]} (${best[1]:,.2f})")
    print("  Note: the winner changes with the time period. Backtest several\n"
          "  periods before trusting any strategy -- and never risk money you\n"
          "  can't afford to lose.\n")


if __name__ == "__main__":
    main()
