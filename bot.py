#!/usr/bin/env python3
"""
bot.py  --  the paper-trading crypto bot you run once a day.
============================================================

WHAT IT DOES, each time you run it:
  1. Loads your fake-money portfolio (remembered from last time).
  2. Downloads recent real prices for your coin.
  3. Asks the strategy: BUY, SELL, or HOLD?
  4. Acts on that decision with FAKE money, respecting the risk rules.
  5. Saves everything and prints a clear summary.

IMPORTANT: This trades PRETEND money only. It is not connected to any real
exchange or real funds, and it cannot make or guarantee real profit. It is a
safe way to learn how a strategy behaves before risking anything real.

HOW TO RUN:
    python3 bot.py            # use real market prices
    python3 bot.py --demo     # use offline practice prices (no internet needed)
    python3 bot.py --reset    # erase the portfolio and start fresh
"""

import os
import sys

import config
import data
import portfolio
import strategy


def main():
    use_demo = "--demo" in sys.argv

    # --reset: wipe saved state so you can start over.
    if "--reset" in sys.argv:
        for path in (config.STATE_FILE, config.LOG_FILE):
            if os.path.exists(path):
                os.remove(path)
        print("Portfolio reset. Starting fresh next run.")
        return

    print(f"\n=== Paper-trading bot | {config.SYMBOL} | "
          f"{'DEMO data' if use_demo else 'LIVE prices'} ===")

    # 1. Load where we left off.
    state = portfolio.load()

    # 2. Get prices.
    if use_demo:
        # A fixed seed makes the demo reproducible run-to-run.
        prices = data.demo_closes(config.HISTORY_DAYS, seed=42)
        print(f"  [data] using {len(prices)} days of offline demo prices")
    else:
        try:
            prices = data.get_daily_closes(config.SYMBOL, config.HISTORY_DAYS)
        except Exception as exc:  # noqa: BLE001
            print(f"\nCould not get live prices:\n  {exc}")
            return

    price_now = prices[-1]
    holding = state["coins"] > 0

    # 3. Decide.
    action, reason = strategy.decide(prices, holding, state["entry_price"])

    # 4. Act (with fake money).
    print(f"\n  Price now: ${price_now:,.2f}")
    print(f"  Decision : {action}  --  {reason}")

    message = None
    if action == "BUY" and not holding:
        message = portfolio.buy(state, price_now)
    elif action == "SELL" and holding:
        message = portfolio.sell(state, price_now)

    if message:
        print(f"  Executed : {message}")
    else:
        print("  Executed : nothing (no trade today)")

    portfolio.save(state)

    # 5. Summary.
    total = portfolio.total_value(state, price_now)
    profit = total - config.STARTING_CASH
    pct = profit / config.STARTING_CASH * 100
    print("\n  ---- Portfolio ----")
    print(f"  Cash      : ${state['cash']:,.2f}")
    print(f"  {config.SYMBOL + ' held':<10}: {state['coins']:.8f} "
          f"(${state['coins'] * price_now:,.2f})")
    print(f"  TOTAL     : ${total:,.2f}")
    print(f"  Since start: ${profit:+,.2f} ({pct:+.1f}%)")
    print(f"  (started with ${config.STARTING_CASH:,.2f} of fake money)\n")


if __name__ == "__main__":
    main()
