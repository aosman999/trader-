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
from datetime import datetime

import broker as broker_mod
import config
import notify
import strategy

HEARTBEAT_FILE = "last_heartbeat.json"   # remembers when we last sent a status
LAST_TRADE_FILE = "last_trade.json"      # date of the last trade (for max-idle)
SHOW_TOP_SETUPS = 12                      # how many candidate setups to detail


def _today():
    return datetime.now().strftime("%Y-%m-%d")


def _record_trade_today():
    with open(LAST_TRADE_FILE, "w") as f:
        json.dump({"date": _today()}, f)


def _idle_days():
    """Days since the last trade. Starts the clock today on the first ever run."""
    if not os.path.exists(LAST_TRADE_FILE):
        _record_trade_today()
        return 0
    try:
        with open(LAST_TRADE_FILE) as f:
            last = datetime.strptime(json.load(f)["date"], "%Y-%m-%d").date()
        return (datetime.now().date() - last).days
    except Exception:  # noqa: BLE001
        return 0


def _should_force_trade():
    """True if we've gone MAX_IDLE_DAYS without trading (last-resort entry)."""
    return config.MAX_IDLE_DAYS > 0 and _idle_days() >= config.MAX_IDLE_DAYS


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

    src = "watchlist" if config.WATCHLIST else "most-active MEXC coins"
    print(f"  Scanning {len(universe)} {src} on the {config.INTERVAL} timeframe...")

    # Pass 1: find every coin forming a BUY setup, ranked by strength.
    buy_cands = []   # (score, symbol, price)
    for symbol in universe:
        try:
            prices = broker.get_prices(symbol, config.INTERVAL)
        except Exception:  # noqa: BLE001 - skip a coin we can't price
            continue
        action, _ = strategy.decide(prices, False, 0.0)
        if action == "BUY":
            buy_cands.append((strategy.momentum_score(prices), symbol, prices[-1]))
    buy_cands.sort(reverse=True)

    # Pass 2: SHOW each setup (strength + how many timeframes agree), and pick
    # the strongest one that passes multi-timeframe confirmation.
    best = None       # (symbol, price, reason)
    shown = buy_cands[:SHOW_TOP_SETUPS]
    if not buy_cands:
        print("  Setups forming: none right now.")
    else:
        print(f"  Setups forming ({len(buy_cands)}; showing top {len(shown)}):")
    for score, symbol, price in shown:
        agree, checked = _count_trend_agreement(broker, symbol)
        confirmed = agree >= config.MIN_TF_AGREE
        tag = "CONFIRMED" if confirmed else f"need {config.MIN_TF_AGREE}"
        print(f"    {symbol:<10} strength {score * 100:+6.2f}%   "
              f"trend {agree}/{checked} timeframes   [{tag}]")
        if confirmed and best is None:
            best = (symbol, price, "multi-timeframe confirmed uptrend")

    # Last resort: don't sit idle past MAX_IDLE_DAYS -- take the best raw setup.
    if best is None and buy_cands and _should_force_trade():
        _, symbol, price = buy_cands[0]
        best = (symbol, price,
                f"FORCED: {_idle_days()} days idle (>= {config.MAX_IDLE_DAYS})")
        print(f"  No confirmed setup, but idle {_idle_days()} days -> forcing "
              f"best available: {symbol}")

    if best is None:
        idle = f" | idle {_idle_days()}d" if config.MAX_IDLE_DAYS else ""
        print(f"  None confirmed. Staying in cash.{idle}\n")
        return (f"In cash ${cash:,.2f}; {len(buy_cands)} setups, none confirmed"
                f"{idle}"), False

    symbol, price, reason = best
    print(f"\n  Best pick: {symbol} @ ${price:,.2f}  ({reason})")
    msg = broker.open(symbol, price)
    print(f"  Executed : {msg or 'nothing (floor/size limit)'}")
    if msg:
        _record_trade_today()
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
