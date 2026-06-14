#!/usr/bin/env python3
"""
bot.py  --  the trading bot you run on a schedule.
==================================================

WHAT IT DOES, each run:
  1. Connects to your broker (paper money OR a real MEXC account).
  2. If it already holds a coin -> manages just that one (sell / hold).
  3. If it's in cash -> SCANS your whole watchlist and trades the SINGLE best
     high-quality setup (or nothing, if none qualify).
  4. Always protects the $12 capital floor.

It holds at most ONE coin at a time, which keeps risk and sizing simple.

SAFETY: with config.BROKER = "paper" it uses FAKE money. With a real broker it
stays in DRY-RUN (decides trades, places nothing) until you turn that off.

HOW TO RUN:
    python3 bot.py            # run once, using config.BROKER
    python3 bot.py --demo     # force paper mode with offline practice prices
    python3 bot.py --reset    # erase the paper portfolio and start fresh
"""

import os
import sys

import broker as broker_mod
import config
import notify
import strategy


def _manage_open_position(broker, pos):
    """We already hold a coin: check the floor, then decide sell/hold on it."""
    symbol = pos["symbol"]
    prices = broker.get_prices(symbol)
    price = prices[-1]
    value = broker.position_value(symbol, pos["amount"], price)
    equity = broker.cash() + value

    print(f"\n  Holding  : {symbol} (entry ${pos['entry']:,.2f})")
    print(f"  Price now: ${price:,.2f}   Equity: ${equity:,.2f}")

    # Circuit breaker: protect the floor.
    if equity <= config.FLOOR_USD:
        print(f"  ** FLOOR REACHED ** (${equity:,.2f} <= ${config.FLOOR_USD:,.2f})")
        msg = broker.close(symbol, pos['amount'], price)
        print(f"  Closing to protect the floor: {msg}")
        notify.send(f"FLOOR hit (${equity:,.2f}). {msg}", title="Bot: floor stop")
        print("  Trading halted. Review before resuming.\n")
        return

    action, reason = strategy.decide(prices, True, pos["entry"])
    print(f"  Decision : {action}  --  {reason}")
    if action == "SELL":
        msg = broker.close(symbol, pos['amount'], price)
        print(f"  Executed : {msg}")
        notify.send(msg, title=f"Bot: closed {symbol}")
    else:
        print("  Executed : holding (no change)")


def _scan_and_maybe_enter(broker):
    """We're in cash: scan the watchlist and enter the best qualifying coin."""
    cash = broker.cash()
    print(f"\n  In cash  : ${cash:,.2f}")
    if cash <= config.FLOOR_USD:
        print(f"  At/under floor (${config.FLOOR_USD:,.2f}); not opening new trades.\n")
        return

    best = None   # (score, symbol, price, reason)
    print(f"  Scanning {len(config.WATCHLIST)} coins for a high-quality setup...")
    for symbol in config.WATCHLIST:
        try:
            prices = broker.get_prices(symbol)
        except Exception as exc:  # noqa: BLE001 - skip a coin we can't price
            print(f"    {symbol:<5} skipped ({str(exc).splitlines()[0][:40]})")
            continue
        action, reason = strategy.decide(prices, False, 0.0)
        if action == "BUY":
            score = strategy.momentum_score(prices)
            print(f"    {symbol:<5} BUY signal (strength {score * 100:+.1f}%)")
            if best is None or score > best[0]:
                best = (score, symbol, prices[-1], reason)
        else:
            print(f"    {symbol:<5} {action.lower()}")

    if best is None:
        print("  No coin has a high-quality setup right now. Staying in cash.\n")
        return

    _, symbol, price, reason = best
    print(f"\n  Best pick: {symbol} @ ${price:,.2f}  ({reason})")
    msg = broker.open(symbol, price)
    print(f"  Executed : {msg or 'nothing (floor/size limit)'}")
    if msg:
        notify.send(msg, title=f"Bot: entered {symbol}")


def main():
    use_demo = "--demo" in sys.argv

    if "--reset" in sys.argv:
        for path in (config.STATE_FILE, config.LOG_FILE):
            if os.path.exists(path):
                os.remove(path)
        print("Paper portfolio reset. Starting fresh next run.")
        return

    broker = broker_mod.PaperBroker(use_demo=True) if use_demo \
        else broker_mod.make_broker()

    print(f"\n=== Trading bot | watchlist {','.join(config.WATCHLIST)} | "
          f"{broker.label}{' | DEMO data' if use_demo else ''} ===")
    if broker.is_live:
        dry = getattr(getattr(broker, "client", None), "dry_run", True)
        if dry:
            print("  (real account; DRY-RUN on -- decides trades, places NONE)")
        else:
            print("  (real account; LIVE -- it WILL place REAL orders / real money)")

    try:
        pos = broker.current_position()
    except Exception as exc:  # noqa: BLE001
        print(f"\nCould not reach the account:\n  {exc}")
        return

    if pos:
        _manage_open_position(broker, pos)
    else:
        _scan_and_maybe_enter(broker)

    print(f"  Cash available: ${broker.cash():,.2f}\n")


if __name__ == "__main__":
    main()
