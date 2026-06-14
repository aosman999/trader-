#!/usr/bin/env python3
"""
backtest.py  --  fast-forward the strategy over a whole price history.
=====================================================================

bot.py makes ONE decision per run (realistic, one day at a time). A backtest
instead replays the strategy across ALL the historical days at once, so you can
see in seconds how it WOULD have done over months -- including how it compares
to simply buying and holding the coin.

This is the honest way to judge a strategy BEFORE trusting it. Remember: good
past performance does NOT guarantee future results. Markets change.

    python3 backtest.py            # backtest on real historical prices
    python3 backtest.py --demo     # backtest on offline practice prices
"""

import sys

import config
import data
import portfolio
import strategy


def run_backtest(prices):
    # A self-contained fake portfolio just for the simulation.
    state = {"cash": config.STARTING_CASH, "coins": 0.0, "entry_price": 0.0}
    trades = 0
    wins = 0

    # Walk forward day by day. We start once there's enough history for the
    # slow moving average to exist.
    for day in range(config.SMA_SLOW + 1, len(prices)):
        window = prices[:day + 1]          # prices known "as of" this day
        price = window[-1]
        holding = state["coins"] > 0
        action, _ = strategy.decide(window, holding, state["entry_price"])

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
            if price > entry:
                wins += 1

    final = portfolio.total_value(state, prices[-1])
    return final, trades, wins


def main():
    use_demo = "--demo" in sys.argv
    if use_demo:
        prices = data.demo_closes(config.HISTORY_DAYS, seed=42)
    else:
        try:
            prices = data.get_daily_closes(config.SYMBOL, config.HISTORY_DAYS)
        except Exception as exc:  # noqa: BLE001
            print(f"Could not get prices: {exc}")
            return

    start = config.STARTING_CASH
    final, trades, wins = run_backtest(prices)

    # Benchmark: what if you had just bought on day one and held? This is the
    # bar any strategy must beat to be worth the effort.
    buy_hold = start * (prices[-1] / prices[0])

    print(f"\n=== Backtest | {config.SYMBOL} | "
          f"{'DEMO' if use_demo else 'LIVE'} | {len(prices)} days ===")
    print(f"  Starting cash      : ${start:,.2f}")
    print(f"  Strategy final     : ${final:,.2f} "
          f"({(final / start - 1) * 100:+.1f}%)")
    print(f"  Buy-and-hold final : ${buy_hold:,.2f} "
          f"({(buy_hold / start - 1) * 100:+.1f}%)")
    print(f"  Trades made        : {trades} (winning sells: {wins})")
    verdict = ("strategy beat buy-and-hold" if final > buy_hold
               else "buy-and-hold was better here")
    print(f"  Verdict            : {verdict}\n")


if __name__ == "__main__":
    main()
