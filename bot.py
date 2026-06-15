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
from datetime import datetime, timezone

import broker as broker_mod
import config
import notify
import strategy

HEARTBEAT_FILE = "last_heartbeat.json"   # remembers when we last sent a status
LAST_TRADE_FILE = "last_trade.json"      # date of the last trade (for max-idle)
LAST_SIGNAL_FILE = "last_signal.json"    # last futures signal sent (dedupe)
GOAL_FILE = "goal_reached.json"          # marks that we've alerted on the goal
TARGET_START_FILE = "target_start.json"  # date the deadline clock started
SHOW_TOP_SETUPS = 12                      # how many candidate setups to detail
SIGNAL_COOLDOWN_MIN = 60                  # don't re-text the same signal within this


_SESSIONS = {"sydney": (22, 7), "tokyo": (0, 9),
             "london": (8, 17), "ny": (13, 22)}   # UTC hour ranges


def _in_session():
    """True if it's inside one of config.TRADING_SESSIONS (UTC). Empty = always."""
    if not config.TRADING_SESSIONS:
        return True
    h = datetime.now(timezone.utc).hour
    for name in config.TRADING_SESSIONS:
        rng = _SESSIONS.get(name.strip().lower())
        if not rng:
            continue
        start, end = rng
        if (start < end and start <= h < end) or \
           (start > end and (h >= start or h < end)):
            return True
    return False


def _futures_equity():
    """Total value of the futures wallet in USDT (read-only -- futures *trading*
    via API is blocked, but reading the balance works). 0 on any failure."""
    try:
        import mexc_futures
        return mexc_futures.MexcFuturesClient().usdt_equity()
    except Exception:  # noqa: BLE001
        return 0.0


def _goal_progress(total):
    """Short, informational progress string toward TARGET_USD (across the whole
    account), including the optional deadline. Tracks only -- forces nothing."""
    if config.TARGET_USD <= 0:
        return ""
    pct = total / config.TARGET_USD * 100
    s = f"Goal ${config.TARGET_USD:,.0f}: at ${total:,.2f} ({pct:.1f}%)"
    if config.TARGET_DAYS > 0:
        start = None
        if os.path.exists(TARGET_START_FILE):
            try:
                with open(TARGET_START_FILE) as f:
                    start = datetime.strptime(json.load(f)["date"], "%Y-%m-%d").date()
            except Exception:  # noqa: BLE001
                start = None
        if start is None:
            start = datetime.now().date()
            with open(TARGET_START_FILE, "w") as f:
                json.dump({"date": start.strftime("%Y-%m-%d")}, f)
        left = max(0, config.TARGET_DAYS - (datetime.now().date() - start).days)
        s += f", {left} of {config.TARGET_DAYS} days left"
    return s


def _goal_milestone(cash):
    """Alert ONCE when the profit goal is reached. Returns True only if the bot
    should STOP opening new trades (TARGET_STOP); by default it keeps trading."""
    if config.TARGET_USD <= 0 or cash < config.TARGET_USD:
        if os.path.exists(GOAL_FILE):    # below target again -> re-arm the alert
            os.remove(GOAL_FILE)
        return False
    if not os.path.exists(GOAL_FILE):
        tail = ("stopping new trades to bank it" if config.TARGET_STOP
                else "and it keeps trading")
        notify.send(f"GOAL REACHED: ${cash:,.2f} (target ${config.TARGET_USD:,.0f}) "
                    f"-- {tail}.", title="Bot: GOAL reached")
        with open(GOAL_FILE, "w") as f:
            f.write("1")
        print(f"  GOAL REACHED ${cash:,.2f} >= ${config.TARGET_USD:,.0f} ({tail}).")
    return config.TARGET_STOP


def _fmt_price(p):
    """Format a price compactly across very different scales (BTC vs DOGE)."""
    if p >= 100:
        return f"{p:,.2f}"
    if p >= 1:
        return f"{p:,.4f}"
    return f"{p:.6f}"


def _send_futures_signal(symbol, entry, direction):
    """Text the user a futures trade (LONG or SHORT) to place BY HAND (MEXC
    blocks futures API). Deduped so the same signal isn't re-sent every minute."""
    if not config.FUTURES_SIGNALS:
        return
    key = f"{symbol}/{direction}"
    last_key, last_ts = None, 0.0
    if os.path.exists(LAST_SIGNAL_FILE):
        try:
            with open(LAST_SIGNAL_FILE) as f:
                d = json.load(f)
            last_key, last_ts = d.get("key"), d.get("ts", 0.0)
        except Exception:  # noqa: BLE001
            pass
    if key == last_key and time.time() - last_ts < SIGNAL_COOLDOWN_MIN * 60:
        return  # already texted this one recently

    lev = config.LEVERAGE
    tp_pct = config.SIGNAL_TP_PCT
    sl_pct = config.STOP_LOSS_PCT
    if direction == "LONG":
        tp = entry * (1 + tp_pct)        # profit is above, stop is below
        sl = entry * (1 - sl_pct)
    else:  # SHORT -- mirror image: profit BELOW entry, stop ABOVE
        tp = entry * (1 - tp_pct)
        sl = entry * (1 + sl_pct)
    msg = (f"FUTURES SIGNAL -- place this by hand:\n"
           f"Coin: {symbol}\n"
           f"Direction: {direction}\n"
           f"Leverage: {lev}x (isolated)\n"
           f"Entry: ~${_fmt_price(entry)}\n"
           f"Take-profit: ${_fmt_price(tp)} ({tp_pct * 100:.0f}% in your favour)\n"
           f"Stop-loss: ${_fmt_price(sl)} ({sl_pct * 100:.0f}% against you)\n"
           f"Risk only a small part of your futures balance.")
    notify.send(msg, title=f"Futures signal: {direction} {symbol}")
    with open(LAST_SIGNAL_FILE, "w") as f:
        json.dump({"key": key, "ts": time.time()}, f)
    print(f"  Futures SIGNAL texted: {direction} {symbol} @ ${_fmt_price(entry)} "
          f"({lev}x, TP {tp_pct * 100:.0f}%, SL {sl_pct * 100:.0f}%)")


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


def _order_error_hint(exc):
    """Turn an order exception into a short, human message -- with a clear hint
    if the exchange is blocking order placement (a common MEXC restriction)."""
    text = str(exc)
    if "403" in text or "Access Denied" in text:
        return ("EXCHANGE BLOCKED the order (403 Access Denied). Futures order "
                "placement via API is not permitted on this account/region. "
                "No code fix -- consider spot, or another exchange.")
    return str(exc).splitlines()[0][:160]


def _count_agreement(broker, symbol, trend_fn):
    """Across every timeframe in config.TIMEFRAMES, count how many match the
    given trend (trend_up for longs, trend_down for shorts)."""
    agree = 0
    checked = 0
    for tf in config.TIMEFRAMES:
        try:
            prices = broker.get_prices(symbol, tf)
        except Exception:  # noqa: BLE001 - a timeframe we can't fetch is skipped
            continue
        checked += 1
        if trend_fn(prices):
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
        try:
            msg = broker.close(symbol, pos['amount'], price)
        except Exception as exc:  # noqa: BLE001
            hint = _order_error_hint(exc)
            print(f"  Close FAILED: {hint}")
            notify.send(f"Close failed for {symbol}: {hint}",
                        title="Bot: close FAILED")
            return f"Close failed: {hint[:80]}", False
        print(f"  Executed : {msg}")
        notify.send(msg, title=f"Bot: closed {symbol}")
        return f"Closed {symbol} at {pnl:+.1f}%", True
    print("  Executed : holding (no change)")
    return (f"Holding {symbol}: {pnl:+.1f}% (now ${price:,.4f}, "
            f"peak ${high_water:,.4f})"), False


def _long_candidate(broker, symbol, prices, action):
    """Decide if `symbol` is a LONG candidate and how. Returns (score, kind) or
    None. kind is 'momentum' (trend signal) or 'bounce' (off support + buyers)."""
    momentum = (strategy.any_long_signal(prices) if config.USE_ALL_STRATEGIES
                else action == "BUY")
    at_sup = config.USE_SR_BOUNCE and strategy.at_support(prices, config.SR_TOL)
    if not (momentum or at_sup):
        return None
    bp = broker.buy_power(symbol) if (config.USE_BUY_POWER or at_sup) else 1.0
    bounce = at_sup and bp >= config.BUY_POWER_MIN
    if not (momentum or bounce):
        return None
    # shared confirmations
    if config.USE_SR and not strategy.has_room(prices, "long", config.SR_MIN_ROOM):
        return None
    if config.USE_BUY_POWER and bp < config.BUY_POWER_MIN:
        return None
    if config.USE_VOLUME and broker.volume_ratio(symbol) < config.VOL_MIN_RATIO:
        return None
    return strategy.momentum_score(prices), ("momentum" if momentum else "bounce")


def _short_candidate(broker, symbol, prices):
    """Decide if `symbol` is a SHORT candidate. Returns (score, kind) or None."""
    momentum = strategy.short_signal(prices)
    at_res = config.USE_SR_BOUNCE and strategy.at_resistance(prices, config.SR_TOL)
    if not (momentum or at_res):
        return None
    bp = broker.buy_power(symbol) if (config.USE_BUY_POWER or at_res) else 0.0
    bounce = at_res and bp <= (1 - config.BUY_POWER_MIN)
    if not (momentum or bounce):
        return None
    if config.USE_SR and not strategy.has_room(prices, "short", config.SR_MIN_ROOM):
        return None
    if config.USE_BUY_POWER and bp > (1 - config.BUY_POWER_MIN):
        return None
    if config.USE_VOLUME and broker.volume_ratio(symbol) < config.VOL_MIN_RATIO:
        return None
    return -strategy.momentum_score(prices), ("momentum" if momentum else "bounce")


def _confirm_best(broker, cands, trend_fn, direction):
    """PRINT the top candidates and return (score, symbol, price, kind) of the
    strongest CONFIRMED one.
      momentum -> needs the TREND to agree across MIN_TF_AGREE timeframes.
      bounce   -> needs the support/resistance LEVEL to show up on BOUNCE_TF_MIN
                  timeframes (multi-timeframe confluence -- a stronger level)."""
    lvl = "support" if direction == "LONG" else "resistance"
    at_level = ((lambda pr: strategy.at_support(pr, config.SR_TOL))
                if direction == "LONG"
                else (lambda pr: strategy.at_resistance(pr, config.SR_TOL)))
    best = None
    for score, symbol, price, kind in cands[:SHOW_TOP_SETUPS]:
        if kind == "bounce":
            agree, checked = _count_agreement(broker, symbol, at_level)
            confirmed = agree >= config.BOUNCE_TF_MIN
            note = (f"on {lvl} {agree}/{checked} TF"
                    + ("" if confirmed else f" (need {config.BOUNCE_TF_MIN})"))
        else:
            agree, checked = _count_agreement(broker, symbol, trend_fn)
            confirmed = agree >= config.MIN_TF_AGREE
            note = (f"trend {agree}/{checked} TF"
                    + ("" if confirmed else f" (need {config.MIN_TF_AGREE})"))
        print(f"    {direction:<5} {symbol:<10} strength {score * 100:+6.2f}%   "
              f"{note}   [{'CONFIRMED' if confirmed else 'no'}]")
        if confirmed and best is None:
            best = (score, symbol, price, kind)
    return best


def _scan_setups(broker):
    """Scan the whole universe and PRINT every forming setup. Returns
    (best_long, long_cands, best_signal):
      best_long   = (symbol, price, reason) confirmed LONG, for the spot auto-trade
      long_cands  = ranked raw long candidates (for the max-idle fallback)
      best_signal = (symbol, price, direction) strongest confirmed LONG *or* SHORT.
    Runs every minute even while a spot trade is open, so signals keep coming."""
    try:
        universe = broker.universe()
    except Exception as exc:  # noqa: BLE001
        print(f"  Could not list coins: {str(exc).splitlines()[0][:60]}")
        return None, [], None

    src = "watchlist" if config.WATCHLIST else "most-active MEXC coins"
    print(f"  Scanning {len(universe)} {src} on the {config.INTERVAL} timeframe...")

    # Pass 1: collect long & short candidates (momentum or bounce).
    long_cands = []    # (score, symbol, price, kind)
    short_cands = []   # (score, symbol, price, kind)
    for symbol in universe:
        try:
            prices = broker.get_prices(symbol, config.INTERVAL)
        except Exception:  # noqa: BLE001 - skip a coin we can't price
            continue
        action, _ = strategy.decide(prices, False, 0.0)
        lc = _long_candidate(broker, symbol, prices, action)
        if lc:
            long_cands.append((lc[0], symbol, prices[-1], lc[1]))
            continue
        if config.FUTURES_SIGNALS:
            sc = _short_candidate(broker, symbol, prices)
            if sc:
                short_cands.append((sc[0], symbol, prices[-1], sc[1]))
    long_cands.sort(reverse=True)
    short_cands.sort(reverse=True)

    if not (long_cands or short_cands):
        print("  Setups forming: none right now.")
    else:
        print(f"  Setups forming (long {len(long_cands)}, short "
              f"{len(short_cands)}):")

    # Pass 2: confirm. Momentum needs timeframe agreement; bounce is pre-confirmed.
    best_long_full = _confirm_best(broker, long_cands, strategy.trend_up, "LONG")
    best_short_full = None
    if config.FUTURES_SIGNALS:
        best_short_full = _confirm_best(broker, short_cands, strategy.trend_down,
                                        "SHORT")

    best_long = None
    if best_long_full:
        kind = best_long_full[3]
        reason = ("bounce off support" if kind == "bounce"
                  else "multi-timeframe confirmed uptrend")
        best_long = (best_long_full[1], best_long_full[2], reason)

    # Best futures signal = whichever confirmed setup (long or short) is strongest.
    best_signal = None  # (symbol, price, direction)
    options = []
    if best_long_full:
        options.append((best_long_full[0], best_long_full[1], best_long_full[2],
                        "LONG"))
    if best_short_full:
        options.append((best_short_full[0], best_short_full[1],
                        best_short_full[2], "SHORT"))
    if options:
        options.sort(reverse=True)
        _, sym, prc, direction = options[0]
        best_signal = (sym, prc, direction)

    return best_long, long_cands, best_signal


def _maybe_enter_spot(broker, best, buy_cands):
    """Spot side: with the scan's result, open the best setup (auto). Returns
    (status_text, a_trade_happened)."""
    cash = broker.cash()                       # spare spot USDT (drives sizing)
    fut = _futures_equity()                     # whole futures wallet (read-only)
    total = cash + fut                          # goal is the WHOLE account
    print(f"  In cash  : ${cash:,.2f} spot  + ${fut:,.2f} futures = "
          f"${total:,.2f} total")
    if config.TARGET_USD > 0:
        print(f"  {_goal_progress(total)}")
    # Goal is judged on the TOTAL account (spot + futures).
    if _goal_milestone(total):
        return f"Goal reached ${total:,.2f}; banked, not trading", False
    if cash <= config.FLOOR_USD:
        print(f"  At/under floor (${config.FLOOR_USD:,.2f}); not opening new trades.\n")
        return f"At floor ${cash:,.2f} spot; not trading", False

    # Last resort: don't sit idle past MAX_IDLE_DAYS -- take the best raw setup.
    if best is None and buy_cands and _should_force_trade():
        symbol, price = buy_cands[0][1], buy_cands[0][2]
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
    print(f"  Best pick: {symbol} @ ${price:,.2f}  ({reason})")
    try:
        msg = broker.open(symbol, price)
    except Exception as exc:  # noqa: BLE001 - a failed order must not crash the run
        hint = _order_error_hint(exc)
        print(f"  Order FAILED: {hint}")
        notify.send(f"Order failed for {symbol}: {hint}", title="Bot: order FAILED")
        return f"Order failed: {hint[:80]}", False
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

    # Always scan -- this drives the spot auto-trade AND the futures signal, and
    # runs even while a spot trade is open.
    best_long, long_cands, best_signal = _scan_setups(broker)

    # Trading-session gate: only OPEN new trades / send new signals inside the
    # chosen sessions. (Managing/exiting an open position is never blocked.)
    in_session = _in_session()
    if not in_session and config.TRADING_SESSIONS:
        print(f"  Outside trading sessions {config.TRADING_SESSIONS} -- "
              f"no new entries/signals.")

    # Futures signal: text the best LONG or SHORT setup to place by hand.
    if in_session and config.FUTURES_SIGNALS and best_signal:
        _send_futures_signal(best_signal[0], best_signal[1], best_signal[2])

    # Spot side (long-only: buys to enter, sells to exit).
    if pos:
        status, traded = _manage_open_position(broker, pos)   # exits always allowed
    elif in_session:
        status, traded = _maybe_enter_spot(broker, best_long, long_cands)
    else:
        status, traded = f"Outside session; not entering", False

    print(f"  Cash available: ${broker.cash():,.2f}\n")

    # Periodic status notification ("what it found"). A trade this run already
    # sent its own alert, so only send the heartbeat when nothing traded.
    if not traded and _heartbeat_due(config.NOTIFY_STATUS_MINUTES):
        notify.send(status, title="Bot status")


if __name__ == "__main__":
    main()
