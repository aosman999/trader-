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

import json
import os
import sys
import time

import broker as broker_mod
import config
import notify
import strategy

HEARTBEAT_FILE = "last_heartbeat.json"   # remembers when we last sent a status


def _heartbeat_due(minutes):
    """True at most once per `minutes`, so a status push isn't sent every run."""
    if minutes <= 0:
        return False
    now = time.time()
    last = 0.0
    if os.path.exists(HEARTBEAT_FILE):
        try:
            with open(HEARTBEAT_FILE) as f:
                last = json.load(f).get("ts", 0.0)
        except Exception:  # noqa: BLE001
            last = 0.0
    if now - last >= minutes * 60:
        with open(HEARTBEAT_FILE, "w") as f:
            json.dump({"ts": now}, f)
        return True
    return False


def _count_trend_agreement(broker, symbol):
    """Check the trend on every timeframe in config.TIMEFRAMES. Returns
    (how_many_are_in_uptrend, how_many_we_could_check)."""
    agree = 0
    checked = 0
    for tf in config.TIMEFRAMES:
        try:
            prices = broker.get_prices(symbol, tf)
        except Exception:  # noqa: BLE001 - a timeframe we can't fetch is skipped
            continue
        checked += 1
        if strategy.trend_up(prices):
            agree += 1
    return agree, checked


def _manage_open_position(broker, pos):
    """We already hold a coin: check the floor, then decide sell/hold on it.
    Returns (status_text, a_trade_happened)."""
    symbol = pos["symbol"]
    prices = broker.get_prices(symbol)
    price = prices[-1]
    value = broker.position_value(symbol, pos["amount"], price)
    equity = broker.cash() + value
    pnl = (price / pos["entry"] - 1) * 100 if pos["entry"] else 0.0

    print(f"\n  Holding  : {symbol} (entry ${pos['entry']:,.2f})")
    print(f"  Price now: ${price:,.2f}   Equity: ${equity:,.2f}")

    # Circuit breaker: protect the floor.
    if equity <= config.FLOOR_USD:
        print(f"  ** FLOOR REACHED ** (${equity:,.2f} <= ${config.FLOOR_USD:,.2f})")
        msg = broker.close(symbol, pos['amount'], price)
        print(f"  Closing to protect the floor: {msg}")
        notify.send(f"FLOOR hit (${equity:,.2f}). {msg}", title="Bot: floor stop")
        print("  Trading halted. Review before resuming.\n")
        return f"Floor stop: closed {symbol}", True

    # Update the peak-since-entry, then decide (the trailing stop uses it).
    high_water = broker.update_high_water(symbol, pos["entry"], price)
    action, reason = strategy.decide(prices, True, pos["entry"],
                                     high_water=high_water)
    print(f"  Peak     : ${high_water:,.2f}")
    print(f"  Decision : {action}  --  {reason}")
    if action == "SELL":
        msg = broker.close(symbol, pos['amount'], price)
        print(f"  Executed : {msg}")
        notify.send(msg, title=f"Bot: closed {symbol}")
        return f"Closed {symbol} at {pnl:+.1f}%", True
    print("  Executed : holding (no change)")
    return (f"Holding {symbol}: {pnl:+.1f}% (now ${price:,.4f}, "
            f"peak ${high_water:,.4f})"), False


def _scan_and_maybe_enter(broker):
    """We're in cash: scan the watchlist and enter the best qualifying coin.
    Returns (status_text, a_trade_happened)."""
    cash = broker.cash()
    print(f"\n  In cash  : ${cash:,.2f}")
    if cash <= config.FLOOR_USD:
        print(f"  At/under floor (${config.FLOOR_USD:,.2f}); not opening new trades.\n")
        return f"At floor ${cash:,.2f}; not trading", False

    try:
        universe = broker.universe()
    except Exception as exc:  # noqa: BLE001
        print(f"  Could not list coins: {str(exc).splitlines()[0][:60]}")
        return f"In cash ${cash:,.2f}; coin-list error", False

    best = None       # (score, symbol, price, reason)
    candidates = 0    # coins with a raw BUY signal on the primary timeframe
    src = "watchlist" if config.WATCHLIST else "most-active MEXC coins"
    print(f"  Scanning {len(universe)} {src} on the {config.INTERVAL} timeframe...")
    for symbol in universe:
        try:
            prices = broker.get_prices(symbol, config.INTERVAL)
        except Exception:  # noqa: BLE001 - skip a coin we can't price
            continue
        action, _ = strategy.decide(prices, False, 0.0)
        if action != "BUY":
            continue
        candidates += 1
        # Multi-timeframe confirmation: only enter if enough timeframes agree
        # the trend is up. Trade WITH the bigger market structure.
        agree, checked = _count_trend_agreement(broker, symbol)
        if agree < config.MIN_TF_AGREE:
            print(f"    {symbol:<8} BUY but {agree}/{checked} timeframes agree; skip")
            continue
        score = strategy.momentum_score(prices)
        print(f"    {symbol:<8} BUY confirmed ({agree}/{checked} timeframes, "
              f"strength {score * 100:+.1f}%)")
        if best is None or score > best[0]:
            best = (score, symbol, prices[-1], "multi-timeframe confirmed uptrend")

    if best is None:
        print(f"  {candidates} buy-signals, none confirmed. Staying in cash.\n")
        return (f"In cash ${cash:,.2f}; no confirmed setup "
                f"({len(universe)} scanned)"), False

    _, symbol, price, reason = best
    print(f"\n  Best pick: {symbol} @ ${price:,.2f}  ({reason})")
    msg = broker.open(symbol, price)
    print(f"  Executed : {msg or 'nothing (floor/size limit)'}")
    if msg:
        notify.send(msg, title=f"Bot: entered {symbol}")
        return f"Entered {symbol} @ ${price:,.4f}", True
    return f"In cash ${cash:,.2f}; setup found but size/floor blocked it", False


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
        status, traded = _manage_open_position(broker, pos)
    else:
        status, traded = _scan_and_maybe_enter(broker)

    print(f"  Cash available: ${broker.cash():,.2f}\n")

    # Periodic status notification ("what it found"). A trade this run already
    # sent its own alert, so only send the heartbeat when nothing traded.
    if not traded and _heartbeat_due(config.NOTIFY_STATUS_MINUTES):
        notify.send(status, title="Bot status")


if __name__ == "__main__":
    main()
