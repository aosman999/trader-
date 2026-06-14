#!/usr/bin/env python3
"""
bot.py  --  the trading bot you run once a day.
===============================================

WHAT IT DOES, each time you run it:
  1. Connects to your "broker" (paper money OR your real MEXC account -- set by
     config.BROKER).
  2. Downloads recent prices.
  3. Asks the strategy: BUY, SELL, or HOLD?
  4. Acts on that decision, respecting the risk rules.
  5. Prints a clear summary.

SAFETY: with config.BROKER = "paper" it uses FAKE money. With "mexc" it talks to
your real account, but mexc.py stays in DRY-RUN (validates orders, places
nothing) until you deliberately turn that off. So this script cannot spend real
money by accident.

HOW TO RUN:
    python3 bot.py            # run once, using config.BROKER
    python3 bot.py --demo     # force paper mode with offline practice prices
    python3 bot.py --reset    # erase the paper portfolio and start fresh
"""

import os
import sys

import broker as broker_mod
import config
import strategy


def main():
    use_demo = "--demo" in sys.argv

    if "--reset" in sys.argv:
        for path in (config.STATE_FILE, config.LOG_FILE):
            if os.path.exists(path):
                os.remove(path)
        print("Paper portfolio reset. Starting fresh next run.")
        return

    # --demo always means safe paper mode, regardless of config.BROKER.
    if use_demo:
        broker = broker_mod.PaperBroker(use_demo=True)
    else:
        broker = broker_mod.make_broker()

    print(f"\n=== Trading bot | {config.SYMBOL} | {broker.label}"
          f"{' | DEMO data' if use_demo else ''} ===")
    if broker.is_live:
        print("  (real account selected; orders still gated by mexc.py dry-run)")

    # 1-2. Prices.
    try:
        prices = broker.history()
    except Exception as exc:  # noqa: BLE001
        print(f"\nCould not get prices / connect:\n  {exc}")
        return
    price_now = prices[-1]
    holding = broker.holding(price_now)

    # CIRCUIT BREAKER: protect the capital floor. If we've fallen to it, close any
    # open position and stop trading -- no new risk until you intervene.
    total_now = broker.total_value(price_now)
    if total_now <= config.FLOOR_USD:
        print(f"\n  ** FLOOR REACHED ** equity ${total_now:,.2f} <= "
              f"${config.FLOOR_USD:,.2f}")
        if holding:
            print(f"  Closing position to protect the floor: "
                  f"{broker.sell(price_now)}")
        print("  Trading halted. Review before resuming "
              "(raise FLOOR_USD or add funds).\n")
        return

    # 3. Decide.
    action, reason = strategy.decide(prices, holding, broker.entry_price())
    print(f"\n  Price now: ${price_now:,.2f}")
    print(f"  Decision : {action}  --  {reason}")

    # 4. Act.
    message = None
    if action == "BUY" and not holding:
        message = broker.buy(price_now)
    elif action == "SELL" and holding:
        message = broker.sell(price_now)
    print(f"  Executed : {message or 'nothing (no trade today)'}")

    # 5. Summary.
    total = broker.total_value(price_now)
    print("\n  ---- Account ----")
    print(f"  Cash      : ${broker.cash():,.2f}")
    print(f"  {config.SYMBOL + ' value':<10}: ${broker.coin_value(price_now):,.2f}")
    print(f"  TOTAL     : ${total:,.2f}")
    if not broker.is_live:
        profit = total - config.STARTING_CASH
        pct = profit / config.STARTING_CASH * 100
        print(f"  Since start: ${profit:+,.2f} ({pct:+.1f}%) "
              f"(started with ${config.STARTING_CASH:,.2f} fake)")
    print()


if __name__ == "__main__":
    main()
