#!/usr/bin/env python3
"""
dashboard.py  --  a friendly one-screen status report.
======================================================

Shows, at a glance:
  * your fake-money portfolio and total profit/loss,
  * the current price plus the indicators the strategy uses,
  * what the strategy would decide right now,
  * a little ASCII price chart of the last few weeks, and
  * your most recent trades.

It only READS data -- it never trades. Run it any time:

    python3 dashboard.py            # using real prices
    python3 dashboard.py --demo     # using offline practice prices
"""

import csv
import os
import sys

import config
import data
import portfolio
import strategy


def sparkline(values, width=48):
    """Turn a list of numbers into a tiny text chart using block characters."""
    blocks = "▁▂▃▄▅▆▇█"
    values = values[-width:]
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1
    return "".join(blocks[int((v - lo) / span * (len(blocks) - 1))]
                   for v in values)


def recent_trades(limit=5):
    """Return the last few rows from trades.csv as (date, action, price)."""
    if not os.path.exists(config.LOG_FILE):
        return []
    with open(config.LOG_FILE) as f:
        rows = list(csv.DictReader(f))
    out = []
    for row in rows[-limit:]:
        date = row["timestamp_utc"].split("T")[0]
        out.append((date, row["action"], float(row["price"])))
    return out


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

    price_now = prices[-1]
    state = portfolio.load()
    holding = state["coins"] > 0
    total = portfolio.total_value(state, price_now)
    profit = total - config.STARTING_CASH
    pct = profit / config.STARTING_CASH * 100

    bar = "=" * 56
    print(f"\n{bar}")
    print(f"  {config.SYMBOL} PAPER-TRADING DASHBOARD"
          f"   ({'DEMO' if use_demo else 'LIVE'} prices)")
    print(bar)

    # --- Portfolio ---
    print("\n  PORTFOLIO (fake money)")
    print(f"    Cash        : ${state['cash']:>12,.2f}")
    print(f"    {config.SYMBOL + ' held':<12}: {state['coins']:>15.8f}"
          f"  (${state['coins'] * price_now:,.2f})")
    print(f"    Total value : ${total:>12,.2f}")
    print(f"    Profit/Loss : ${profit:>+12,.2f}  ({pct:+.1f}%)")

    # --- Market & indicators ---
    fast = strategy.simple_moving_average(prices, config.SMA_FAST)
    slow = strategy.simple_moving_average(prices, config.SMA_SLOW)
    rsi_val = strategy.rsi(prices, config.RSI_PERIOD)
    print("\n  MARKET")
    print(f"    Price now   : ${price_now:>12,.2f}")
    if fast and slow:
        trend = "up ▲" if fast > slow else "down ▼"
        print(f"    SMA {config.SMA_FAST:>2}/{config.SMA_SLOW:<2}   : "
              f"${fast:,.0f} / ${slow:,.0f}   (trend {trend})")
    if rsi_val is not None:
        if rsi_val >= config.RSI_SELL:
            tag = "overbought"
        elif rsi_val <= config.RSI_BUY:
            tag = "oversold"
        else:
            tag = "neutral"
        print(f"    RSI({config.RSI_PERIOD})     : {rsi_val:>12.0f}   ({tag})")

    print(f"\n    Last ~7 weeks: {sparkline(prices)}")
    print(f"    range ${min(prices[-48:]):,.0f} "
          f"-> ${max(prices[-48:]):,.0f}")

    # --- Today's decision ---
    action, reason = strategy.decide(prices, holding, state["entry_price"])
    print(f"\n  STRATEGY: {config.STRATEGY}")
    print(f"    Decision now: {action}  --  {reason}")
    print("    (run  python3 bot.py  to actually act on it)")

    # --- Recent trades ---
    trades = recent_trades()
    print("\n  RECENT TRADES")
    if trades:
        for date, act, price in trades:
            print(f"    {date}  {act:<4} at ${price:,.2f}")
    else:
        print("    (none yet -- run the bot for a while)")

    print(f"\n{bar}")
    print("  Reminder: pretend money, real prices. No profit is guaranteed.")
    print(f"{bar}\n")


if __name__ == "__main__":
    main()
