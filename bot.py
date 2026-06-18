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


MANUAL_POS_FILE = "manual_positions.json"   # manual futures trades (from talk.py)


def _manual_pnl(p, price):
    """Profit/loss of a manual futures position at `price`. Returns
    (pct_move, usd) where pct_move is the raw price move and usd is the dollar
    P/L on the user's money (margin x leverage x move). usd is None when we don't
    know the margin (how much money they put in -- add it via talk.py)."""
    entry = p.get("entry")
    if not entry:
        return None, None
    side = p.get("side", "long")
    move = (price / entry - 1) if side == "long" else (entry / price - 1)
    margin = p.get("margin")
    lev = p.get("lev") or 1
    usd = margin * lev * move if margin else None
    return move * 100, usd


def _pnl_money(pct, usd):
    """A short human tail for a notification: the dollar P/L if we know the size,
    otherwise just the % move with a nudge to tell us the size."""
    if pct is None:
        return ""
    if usd is not None:
        verb = "profit" if usd >= 0 else "loss"
        return f" Estimated {verb}: ${abs(usd):,.2f} ({pct:+.2f}% move)."
    return f" ({pct:+.2f}% move -- tell me your position size for the $ figure.)"


def _manual_exit_signal(broker, p):
    """Beyond TP/SL: should the user bail out EARLY? Returns a short reason if the
    trade's thesis is breaking -- the trend turning against the position across
    several timeframes -- so we can tell them to exit before the stop. None if the
    setup still looks fine."""
    coin, side = p.get("coin"), p.get("side", "long")
    against = checked = 0
    for tf in ("5m", "15m", "1h"):
        try:
            prices = broker.get_prices(coin, tf)
        except Exception:  # noqa: BLE001
            continue
        checked += 1
        if side == "long" and strategy.trend_down(prices):
            against += 1
        elif side == "short" and strategy.trend_up(prices):
            against += 1
    if checked >= 2 and against >= 2:
        way = "downtrend" if side == "long" else "uptrend"
        return (f"the trend has flipped against you ({against}/{checked} "
                f"timeframes now in a {way})")
    return None


def _check_manual_positions(broker):
    """Watch manually-entered futures trades (added via talk.py) and text the user
    when one (a) hits its take-profit / stop-loss, OR (b) has its thesis break --
    the trend turning against it -- so they can exit early, before the stop."""
    if not os.path.exists(MANUAL_POS_FILE):
        return
    try:
        with open(MANUAL_POS_FILE) as f:
            positions = json.load(f)
    except Exception:  # noqa: BLE001
        return
    kept = []
    for p in positions:
        coin, side = p.get("coin"), p.get("side", "long")
        tp, sl = p.get("tp"), p.get("sl")
        try:
            price = broker.get_prices(coin, config.INTERVAL)[-1]
        except Exception:  # noqa: BLE001 - keep watching if we can't price it now
            kept.append(p)
            continue
        hit = None
        if side == "long":
            if tp and price >= tp:
                hit = "TAKE-PROFIT"
            elif sl and price <= sl:
                hit = "STOP-LOSS"
        else:  # short
            if tp and price <= tp:
                hit = "TAKE-PROFIT"
            elif sl and price >= sl:
                hit = "STOP-LOSS"
        if hit:
            pct, usd = _manual_pnl(p, price)
            money = _pnl_money(pct, usd)
            notify.send(f"Your {coin} {side} hit {hit} at ${price:g} -- "
                        f"close it on MEXC now.{money}", title=f"Manual {coin}: {hit}")
            print(f"  Manual {coin} {side} hit {hit} at ${price:g}{money} -- texted you.")
            continue   # done with this one

        # No TP/SL yet -- but should they exit EARLY because the setup is failing?
        reason = _manual_exit_signal(broker, p)
        if reason and not p.get("exit_warned"):
            pct, usd = _manual_pnl(p, price)
            money = _pnl_money(pct, usd)
            notify.send(f"Consider EXITING your {coin} {side} (now ${price:g}): "
                        f"{reason}. It hasn't hit TP/SL, but the setup is weakening "
                        f"-- your call.{money}", title=f"Manual {coin}: consider exit")
            print(f"  Manual {coin} {side}: early-exit warning ({reason}).")
            p["exit_warned"] = True
        elif not reason and p.get("exit_warned"):
            p["exit_warned"] = False   # trend recovered -> re-arm the warning
        kept.append(p)
    with open(MANUAL_POS_FILE, "w") as f:
        json.dump(kept, f, indent=2)


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


def _spot_pnl_usd(entry, amount, price):
    """Net dollar P/L of a spot position sold at `price`, after estimated round-
    trip fees. None if we don't know the entry."""
    if not entry:
        return None
    gross = amount * (price - entry)
    fee = getattr(config, "FEE_PCT", 0.0) or 0.0
    fees = (amount * entry + amount * price) * fee   # buy fee + sell fee
    return gross - fees


def _manage_one(broker, pos, prices):
    """Decide sell/hold on ONE held coin. Returns (sold?, note, value_if_held)."""
    symbol, price, entry = pos["symbol"], prices[-1], pos["entry"]
    pnl = (price / entry - 1) * 100 if entry else 0.0
    value = broker.position_value(symbol, pos["amount"], price)
    high_water = broker.update_high_water(symbol, entry, price)
    action, reason = strategy.decide(prices, True, entry, high_water=high_water,
                                     strategy_name=_active_strategy())

    # Anti-churn: don't bail on a SOFT (strategy) signal within MIN_HOLD_MIN of
    # entering -- a real stop-loss / trailing stop still exits any time. This
    # stops the buy-now-sell-next-minute flip-flopping.
    if action == "SELL" and config.MIN_HOLD_MIN > 0:
        age_min = (time.time() - pos.get("opened_at", 0.0)) / 60
        soft = ("stop-loss" not in reason) and ("trailing" not in reason)
        if soft and pos.get("opened_at") and age_min < config.MIN_HOLD_MIN:
            print(f"  {symbol}: soft exit held off ({age_min:.0f}<"
                  f"{config.MIN_HOLD_MIN}min, anti-churn) -- {reason}")
            return False, f"{symbol} {pnl:+.1f}% (young)", value

    if action == "SELL":
        try:
            msg = broker.close(symbol, pos["amount"], price)
        except Exception as exc:  # noqa: BLE001
            hint = _order_error_hint(exc)
            print(f"  {symbol}: close FAILED -- {hint}")
            notify.send(f"Close failed for {symbol}: {hint}",
                        title="Bot: close FAILED")
            return False, f"{symbol}: close failed", value
        net = _spot_pnl_usd(entry, pos["amount"], price)
        if net is not None:
            verb = "Profit" if net >= 0 else "Loss"
            money = f" {verb}: ${abs(net):,.2f} ({pnl:+.1f}%)."
            note = f"Closed {symbol} {net:+,.2f} USD ({pnl:+.1f}%)"
        else:
            money, note = "", f"Closed {symbol} ({pnl:+.1f}%)"
        _journal(symbol, entry, price, net, pnl, _active_strategy())
        _set_cooldown(symbol)          # don't re-enter this coin for a while
        print(f"  {symbol}: SELL -- {reason}.{money}")
        notify.send(msg + money, title=f"Bot: closed {symbol}")
        return True, note, 0.0
    print(f"  {symbol}: hold ({pnl:+.1f}%, peak ${high_water:,.4f}) -- {reason}")
    return False, f"{symbol} {pnl:+.1f}%", value


def _manage_positions(broker, positions):
    """Manage every held coin. Floor circuit breaker on TOTAL equity first (close
    all + halt). Returns (status, traded?, held_symbols, held_value)."""
    if not positions:
        return "no open positions", False, [], 0.0
    cash = broker.cash()
    priced, total_value = [], 0.0
    for pos in positions:
        try:
            prices = broker.get_prices(pos["symbol"])
        except Exception:  # noqa: BLE001 - keep it; just can't manage it this run
            priced.append((pos, None))
            continue
        priced.append((pos, prices))
        total_value += broker.position_value(pos["symbol"], pos["amount"],
                                             prices[-1])
    equity = cash + total_value
    print(f"\n  Holding {len(positions)} position(s); equity ${equity:,.2f}")

    # Circuit breaker on TOTAL equity -- close everything and halt. Only when we
    # could price every position (don't liquidate blind on a fetch glitch).
    if all(pr is not None for _, pr in priced) and equity <= config.FLOOR_USD:
        print(f"  ** FLOOR REACHED ** (${equity:,.2f} <= ${config.FLOOR_USD})")
        for pos, prices in priced:
            try:
                broker.close(pos["symbol"], pos["amount"], prices[-1])
            except Exception:  # noqa: BLE001
                pass
        notify.send(f"FLOOR hit (equity ${equity:,.2f}) -- closed all positions "
                    f"and halted. Review before resuming.", title="Bot: floor stop")
        print("  Trading halted. Review before resuming.\n")
        return f"Floor stop: closed all at ${equity:,.2f}", True, [], 0.0

    held, held_value, traded, notes = [], 0.0, False, []
    for pos, prices in priced:
        if prices is None:
            held.append(pos["symbol"])
            continue
        sold, note, value = _manage_one(broker, pos, prices)
        notes.append(note)
        if sold:
            traded = True
        else:
            held.append(pos["symbol"])
            held_value += value
    return "; ".join(notes), traded, held, held_value


EVAL_CAP = 12   # max triggered coins to fully evaluate per run (API budget)
DEPLOY_BUFFER = 0.98   # spend ~98% of cash; the rest covers fees/rounding/lag so
                       # MEXC doesn't reject the order ("Insufficient position")
MIN_TRADE_USD = 1.0    # never place an order smaller than this (exchange minimum)

SKIP_FILE = "skip_symbols.json"   # coins MEXC won't let the API trade (code 10007)
# Stablecoins / fiat tokens: trading these against USDT can't make real profit and
# several aren't API-tradeable. Never trade them.
STABLES = {"USDT", "USDC", "USDE", "USD1", "DAI", "TUSD", "BUSD", "FDUSD",
           "PYUSD", "USDP", "GUSD", "USDD", "FRAX", "LUSD", "EUR", "EURT",
           "EURS", "EURI", "EURC", "GBP", "AEUR", "USDG", "USDY"}


def _load_skip():
    if os.path.exists(SKIP_FILE):
        try:
            with open(SKIP_FILE) as f:
                return set(json.load(f))
        except Exception:  # noqa: BLE001
            return set()
    return set()


def _add_skip(symbol):
    """Remember a coin MEXC won't trade via API, so we never try it again."""
    syms = _load_skip()
    syms.add(symbol)
    with open(SKIP_FILE, "w") as f:
        json.dump(sorted(syms), f)


_ACTIVE_STRATEGY = None       # cached for this run


def _active_strategy():
    """Which strategy to trade with: the learned best (if AUTO_LEARN and we've
    picked one) else the configured STRATEGY."""
    global _ACTIVE_STRATEGY
    if _ACTIVE_STRATEGY is not None:
        return _ACTIVE_STRATEGY
    name = config.STRATEGY
    if config.AUTO_LEARN:
        try:
            import learn
            best = learn.load_best()
            if best and best.get("strategy") in strategy.STRATEGIES:
                name = best["strategy"]
        except Exception:  # noqa: BLE001
            pass
    _ACTIVE_STRATEGY = name
    return name


def _maybe_learn(broker):
    """Periodically re-run the strategy tournament and switch to the winner."""
    if not config.AUTO_LEARN:
        return
    try:
        import learn
        if not learn.due(config.LEARN_EVERY_HOURS):
            return
        coins = [s for s in broker.universe()
                 if s.upper() not in STABLES and s not in _load_skip()]
        coins = coins[:config.LEARN_COINS]
        name, summary = learn.pick_best(broker, coins, config.INTERVAL)
        prev = (learn.load_best() or {}).get("strategy")
        learn.save_best(name, summary)
        learn.mark_done()
        global _ACTIVE_STRATEGY
        _ACTIVE_STRATEGY = name
        s = summary.get(name, {})
        print(f"  Learned: best strategy now '{name}' "
              f"({s.get('avg_return', 0) * 100:+.1f}% avg, "
              f"{s.get('winrate', 0) * 100:.0f}% wins over {len(coins)} coins)")
        if prev and prev != name:
            notify.send(f"Switched strategy to '{name}' "
                        f"({s.get('avg_return', 0) * 100:+.1f}% in recent backtests, "
                        f"was '{prev}').", title="Bot: learned a better strategy")
    except Exception as exc:  # noqa: BLE001 - learning must never crash a run
        print(f"  (learning skipped: {str(exc).splitlines()[0][:80]})")


JOURNAL_FILE = "trade_journal.csv"


def _journal(symbol, entry, exit_price, net, pnl_pct, strat):
    """Append one closed spot trade to the journal so we can review what works."""
    import csv
    new = not os.path.exists(JOURNAL_FILE)
    with open(JOURNAL_FILE, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["time", "symbol", "strategy", "entry", "exit",
                        "pnl_usd", "pnl_pct"])
        w.writerow([datetime.now().strftime("%Y-%m-%d %H:%M"), symbol, strat,
                    f"{entry:.6f}", f"{exit_price:.6f}",
                    "" if net is None else f"{net:.2f}", f"{pnl_pct:.2f}"])


COOLDOWN_FILE = "reentry_cooldown.json"   # when we last closed each coin


def _set_cooldown(symbol):
    data = {}
    if os.path.exists(COOLDOWN_FILE):
        try:
            with open(COOLDOWN_FILE) as f:
                data = json.load(f)
        except Exception:  # noqa: BLE001
            data = {}
    data[symbol] = time.time()
    with open(COOLDOWN_FILE, "w") as f:
        json.dump(data, f)


def _in_cooldown(symbol):
    """True if we closed this coin too recently to re-enter it (anti-churn)."""
    if config.REENTRY_COOLDOWN_MIN <= 0 or not os.path.exists(COOLDOWN_FILE):
        return False
    try:
        with open(COOLDOWN_FILE) as f:
            t = json.load(f).get(symbol, 0.0)
    except Exception:  # noqa: BLE001
        return False
    return time.time() - t < config.REENTRY_COOLDOWN_MIN * 60


DAY_START_FILE = "day_start.json"


def _day_start_equity(current):
    """The spot equity at the start of today (records it on the first run of a
    new day). Used for the daily profit target."""
    today = _today()
    data = {}
    if os.path.exists(DAY_START_FILE):
        try:
            with open(DAY_START_FILE) as f:
                data = json.load(f)
        except Exception:  # noqa: BLE001
            data = {}
    if data.get("date") != today:
        data = {"date": today, "equity": current}
        with open(DAY_START_FILE, "w") as f:
            json.dump(data, f)
    return data.get("equity", current)


PROFIT_BASE_FILE = "profit_base.json"   # the equity the doubling ladder starts from


def _daily_target(day_start_equity):
    """The daily profit target in dollars. Starts at DAILY_PROFIT_STOP and doubles
    each time the account doubles (base $2 -> $4 at 2x -> $8 at 4x ...). 0 = off."""
    base = config.DAILY_PROFIT_STOP
    if base <= 0:
        return 0.0
    base_eq = None
    if os.path.exists(PROFIT_BASE_FILE):
        try:
            with open(PROFIT_BASE_FILE) as f:
                base_eq = json.load(f).get("equity")
        except Exception:  # noqa: BLE001
            base_eq = None
    if not base_eq or base_eq <= 0:
        base_eq = day_start_equity
        with open(PROFIT_BASE_FILE, "w") as f:
            json.dump({"equity": base_eq}, f)
    import math
    ratio = day_start_equity / base_eq if base_eq > 0 else 1.0
    doublings = int(math.floor(math.log2(ratio))) if ratio >= 1 else 0
    return base * (2 ** max(0, doublings))


REPORT_STAMP = "last_report.json"


def _maybe_report():
    """Once every REPORT_EVERY_DAYS, text a report card of trades since the last
    one: how many, win rate, net dollars, best and worst."""
    if config.REPORT_EVERY_DAYS <= 0 or not os.path.exists(JOURNAL_FILE):
        return
    last = 0.0
    if os.path.exists(REPORT_STAMP):
        try:
            with open(REPORT_STAMP) as f:
                last = json.load(f).get("ts", 0.0)
        except Exception:  # noqa: BLE001
            last = 0.0
    if time.time() - last < config.REPORT_EVERY_DAYS * 86400:
        return
    import csv
    pnls = []
    try:
        with open(JOURNAL_FILE) as f:
            for r in csv.DictReader(f):
                if not r.get("pnl_usd"):
                    continue
                try:
                    ts = datetime.strptime(r["time"], "%Y-%m-%d %H:%M").timestamp()
                except Exception:  # noqa: BLE001
                    ts = 0.0
                if ts >= last:
                    pnls.append(float(r["pnl_usd"]))
    except Exception:  # noqa: BLE001
        return
    with open(REPORT_STAMP, "w") as f:
        json.dump({"ts": time.time()}, f)
    if not pnls:
        return
    n, wins = len(pnls), sum(1 for p in pnls if p > 0)
    notify.send(f"Report card: {n} trades, {wins / n * 100:.0f}% wins, "
                f"net ${sum(pnls):+.2f} (best ${max(pnls):+.2f}, "
                f"worst ${min(pnls):+.2f}). Strategy: {_active_strategy()}.",
                title="Bot: trade report card")


def _tf_prices(broker, symbol):
    """Fetch each timeframe's candles once (for trend + S/R-confluence checks)."""
    out = []
    for tf in config.TIMEFRAMES:
        try:
            out.append(broker.get_prices(symbol, tf))
        except Exception:  # noqa: BLE001
            continue
    return out


def _confirm_long(broker, symbol, prices, strat, sup):
    """Count the LONG confirmations present; return (count, labels). The bot
    enters when at least config.MIN_CONFIRMATIONS are present -- it does NOT need
    all of them (e.g. support + volume is enough). Cheap checks first; the costly
    multi-timeframe checks run only if still needed."""
    labels = []
    if strat:
        labels.append("strategy")
    if sup:
        labels.append("support")
    if config.USE_BUY_POWER and broker.buy_power(symbol) >= config.BUY_POWER_MIN:
        labels.append("power")
    if config.USE_VOLUME and broker.volume_ratio(symbol) >= config.VOL_MIN_RATIO:
        labels.append("volume")
    if config.USE_SR and strategy.has_room(prices, "long", config.SR_MIN_ROOM):
        labels.append("room")
    if len(labels) < config.MIN_CONFIRMATIONS:           # only then pay for TF scan
        tfp = _tf_prices(broker, symbol)
        if sum(strategy.trend_up(p) for p in tfp) >= config.MIN_TF_AGREE:
            labels.append("trend")
        if sup and sum(strategy.at_support(p, config.SR_TOL)
                       for p in tfp) >= config.BOUNCE_TF_MIN:
            labels.append("confluence")
    return len(labels), labels


def _confirm_short(broker, symbol, prices, strat, res):
    """Count the SHORT confirmations present; return (count, labels)."""
    labels = []
    if strat:
        labels.append("strategy")
    if res:
        labels.append("resistance")
    if config.USE_BUY_POWER and broker.buy_power(symbol) <= (1 - config.BUY_POWER_MIN):
        labels.append("power")
    if config.USE_VOLUME and broker.volume_ratio(symbol) >= config.VOL_MIN_RATIO:
        labels.append("volume")
    if config.USE_SR and strategy.has_room(prices, "short", config.SR_MIN_ROOM):
        labels.append("room")
    if len(labels) < config.MIN_CONFIRMATIONS:
        tfp = _tf_prices(broker, symbol)
        if sum(strategy.trend_down(p) for p in tfp) >= config.MIN_TF_AGREE:
            labels.append("trend")
        if res and sum(strategy.at_resistance(p, config.SR_TOL)
                       for p in tfp) >= config.BOUNCE_TF_MIN:
            labels.append("confluence")
    return len(labels), labels


def _scan_setups(broker):
    """Scan the universe. A coin is a candidate when it shows at least
    MIN_CONFIRMATIONS confirmations (any combination -- e.g. support+volume, or
    strategy+trend) -- it does NOT need all of them. Returns
    (best_long, long_cands, raw_longs, best_signal)."""
    try:
        universe = broker.universe()
    except Exception as exc:  # noqa: BLE001
        print(f"  Could not list coins: {str(exc).splitlines()[0][:60]}")
        return None, [], [], None

    # Drop stablecoins/fiat (can't profit) and coins MEXC won't trade via API.
    skip = _load_skip()
    universe = [s for s in universe if s.upper() not in STABLES and s not in skip]

    src = "watchlist" if config.WATCHLIST else "most-active MEXC coins"
    print(f"  Scanning {len(universe)} {src} on the {config.INTERVAL} timeframe...")

    # Cheap pass: coins with a directional trigger (strategy signal or at S/R).
    long_trig, short_trig, raw_longs = [], [], []
    best_any = None   # strongest-trending coin overall (ultimate force fallback)
    for symbol in universe:
        try:
            prices = broker.get_prices(symbol, config.INTERVAL)
        except Exception:  # noqa: BLE001
            continue
        action, _ = strategy.decide(prices, False, 0.0,
                                    strategy_name=_active_strategy())
        if config.AUTO_LEARN:
            strat = action == "BUY"             # trade the single learned-best one
        elif config.USE_ALL_STRATEGIES:
            strat = strategy.any_long_signal(prices)
        else:
            strat = action == "BUY"
        sup = config.USE_SR_BOUNCE and strategy.at_support(prices, config.SR_TOL)
        score = strategy.momentum_score(prices)
        if best_any is None or score > best_any[0]:
            best_any = (score, symbol, prices[-1])
        if strat:
            raw_longs.append((score, symbol, prices[-1]))
        if strat or sup:
            long_trig.append((score, symbol, prices, strat, sup))
        elif config.FUTURES_SIGNALS:
            sstrat = strategy.short_signal(prices)
            res = config.USE_SR_BOUNCE and strategy.at_resistance(prices, config.SR_TOL)
            if sstrat or res:
                short_trig.append((-score, symbol, prices, sstrat, res))
    long_trig.sort(reverse=True)
    short_trig.sort(reverse=True)
    raw_longs.sort(reverse=True)
    # Ultimate fallback so the idle-force ALWAYS has something: if no coin even
    # signalled, use the strongest-trending coin (only ever used by the force).
    if not raw_longs and best_any:
        raw_longs = [best_any]

    if not (long_trig or short_trig):
        print("  Setups forming: none right now.")
    else:
        print(f"  Evaluating setups (need {config.MIN_CONFIRMATIONS}+ confirmations):")

    # Expensive pass (capped): count confirmations, keep those that qualify.
    long_cands = []
    for score, symbol, prices, strat, sup in long_trig[:EVAL_CAP]:
        n, labels = _confirm_long(broker, symbol, prices, strat, sup)
        ok = n >= config.MIN_CONFIRMATIONS
        print(f"    LONG  {symbol:<10} {score * 100:+6.2f}%  "
              f"{'+'.join(labels) or 'trigger'}  [{n} {'OK' if ok else 'no'}]")
        if ok:
            long_cands.append((score, symbol, prices[-1], "+".join(labels)))

    short_cands = []
    if config.FUTURES_SIGNALS:
        for score, symbol, prices, strat, res in short_trig[:EVAL_CAP]:
            n, labels = _confirm_short(broker, symbol, prices, strat, res)
            ok = n >= config.MIN_CONFIRMATIONS
            print(f"    SHORT {symbol:<10} {score * 100:+6.2f}%  "
                  f"{'+'.join(labels) or 'trigger'}  [{n} {'OK' if ok else 'no'}]")
            if ok:
                short_cands.append((score, symbol, prices[-1], "+".join(labels)))

    best_long = None
    if long_cands:
        best_long = (long_cands[0][1], long_cands[0][2], long_cands[0][3])

    best_signal = None
    options = []
    if long_cands:
        options.append((long_cands[0][0], long_cands[0][1], long_cands[0][2], "LONG"))
    if short_cands:
        options.append((short_cands[0][0], short_cands[0][1], short_cands[0][2],
                        "SHORT"))
    if options:
        options.sort(reverse=True)
        _, sym, prc, direction = options[0]
        best_signal = (sym, prc, direction)

    return best_long, long_cands, raw_longs, best_signal


def _maybe_enter(broker, held, held_value, long_cands, raw_longs):
    """Open new spot positions up to config.MAX_POSITIONS. Deploys all available
    cash this run, split evenly across however many good setups it found (one
    great setup -> all the money in it; three at once -> a third each). Returns
    (status_text, a_trade_happened)."""
    free = config.MAX_POSITIONS - len(held)
    cash = broker.cash()
    spot_equity = cash + held_value             # whole spot account value

    if config.TARGET_SPOT_ONLY:
        total = spot_equity
        print(f"  Spot equity ${spot_equity:,.2f} (cash ${cash:,.2f}); "
              f"goal tracks spot only")
    else:
        fut = _futures_equity()
        total = spot_equity + fut
        print(f"  Spot ${spot_equity:,.2f} + futures ${fut:,.2f} = ${total:,.2f}")
    if config.TARGET_USD > 0:
        print(f"  {_goal_progress(total)}")
    if _goal_milestone(total):
        return f"Goal reached ${total:,.2f}; not opening new trades", False

    # Bank the day: once today's profit hits the (doubling) target, stop opening
    # new trades until tomorrow. Exits still run via _manage_positions.
    day_start = _day_start_equity(spot_equity)
    target = _daily_target(day_start)
    if target > 0:
        gain = spot_equity - day_start
        if gain >= target:
            print(f"  Up ${gain:,.2f} today (target ${target:,.0f}) -- banking it, "
                  f"no new trades until tomorrow.\n")
            return (f"Banked ${gain:,.2f} today (>= ${target:,.0f}); done for the "
                    f"day"), False
        print(f"  Today: {gain:+,.2f} of ${target:,.0f} target")

    if free <= 0:
        return f"Holding max {config.MAX_POSITIONS}; not adding", False

    # How much cash we may deploy. With RESERVE_FLOOR we keep the floor as cash;
    # without it we deploy everything, but only START trades while we're still
    # above the floor (the circuit breaker handles dropping to it mid-trade).
    if config.RESERVE_FLOOR:
        available = max(0.0, cash - config.FLOOR_USD)
    else:
        available = cash if spot_equity > config.FLOOR_USD else 0.0
    if available < 1:
        print(f"  No deployable cash (${cash:,.2f}); not entering.\n")
        return f"In cash ${cash:,.2f}; not entering", False

    # Candidates we don't already hold (and aren't in the re-entry cooldown), best
    # first.
    cands = [c for c in long_cands
             if c[1] not in held and not _in_cooldown(c[1])]
    if not cands and _should_force_trade():
        pool = [c for c in raw_longs
                if c[1] not in held and not _in_cooldown(c[1])]
        if pool:
            cands = [(pool[0][0], pool[0][1], pool[0][2],
                      f"FORCED idle {_idle_days()}d")]
            print(f"  Idle {_idle_days()}d -> forcing best available: {pool[0][1]}")
    if not cands:
        idle = f" | idle {_idle_days()}d" if config.MAX_IDLE_DAYS else ""
        print(f"  No new confirmed setups. Cash ${cash:,.2f}.{idle}\n")
        return f"In cash ${cash:,.2f}; no new setups{idle}", False

    n = min(free, len(cands))                   # how many we open this run
    # Leave a small buffer below the reported cash for fees, rounding and the
    # exchange's balance-settlement lag -- spending literally 100% gets rejected
    # ("Insufficient position"). And don't split so thin an order becomes dust.
    spendable = available * DEPLOY_BUFFER
    while n > 1 and spendable / n < MIN_TRADE_USD:
        n -= 1
    per = spendable / n                          # spendable cash, split evenly
    opened = []
    for c in cands[:n]:
        symbol, price = c[1], c[2]
        try:
            msg = broker.open(symbol, price, budget=per)
        except Exception as exc:  # noqa: BLE001 - one bad order must not crash the run
            text = str(exc)
            if "10007" in text or "not support api" in text:
                _add_skip(symbol)        # MEXC won't trade it via API -> never retry
                print(f"  {symbol} not API-tradeable -> skip-listed (no retry).")
                continue                 # expected; don't spam a notification
            hint = _order_error_hint(exc)
            print(f"  Order FAILED {symbol}: {hint}")
            notify.send(f"Order failed for {symbol}: {hint}",
                        title="Bot: order FAILED")
            continue
        if msg:
            opened.append(symbol)
            _record_trade_today()
            notify.send(msg, title=f"Bot: entered {symbol}")
            print(f"  Entered {symbol} ~${per:,.2f}: {msg}")
    if opened:
        return f"Entered {', '.join(opened)} (~${per:,.2f} each)", True
    return f"In cash ${cash:,.2f}; setups found but orders blocked", False


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
        positions = broker.current_positions()
    except Exception as exc:  # noqa: BLE001
        print(f"\nCould not reach the account:\n  {exc}")
        return

    # Watch the user's manually-entered futures trades (from talk.py) and text
    # them if any has hit its take-profit or stop-loss.
    _check_manual_positions(broker)

    # Self-improvement: occasionally re-test the strategies and switch to the
    # best, and text a periodic performance report card.
    _maybe_learn(broker)
    _maybe_report()
    if config.AUTO_LEARN:
        print(f"  Trading strategy: {_active_strategy()} (auto-learned)")

    # Always scan -- this drives the spot auto-trade AND the futures signal, and
    # runs even while a spot trade is open.
    best_long, long_cands, raw_longs, best_signal = _scan_setups(broker)

    # Trading-session gate: only OPEN new trades / send new signals inside the
    # chosen sessions. (Managing/exiting an open position is never blocked.)
    in_session = _in_session()
    if not in_session and config.TRADING_SESSIONS:
        print(f"  Outside trading sessions {config.TRADING_SESSIONS} -- "
              f"no new entries/signals.")

    # Futures signal: text the best LONG or SHORT setup to place by hand.
    if in_session and config.FUTURES_SIGNALS and best_signal:
        _send_futures_signal(best_signal[0], best_signal[1], best_signal[2])

    # Spot side (long-only: buys to enter, sells to exit). Manage what we hold
    # (exits always allowed), then open new positions up to MAX_POSITIONS.
    status, traded, held, held_value = _manage_positions(broker, positions)
    if in_session:
        enter_status, entered = _maybe_enter(broker, held, held_value,
                                             long_cands, raw_longs)
        traded = traded or entered
        status = f"{status} | {enter_status}" if positions else enter_status
    elif not positions:
        status = "Outside session; not entering"

    print(f"  Cash available: ${broker.cash():,.2f}\n")

    # Periodic status notification ("what it found"). A trade this run already
    # sent its own alert, so only send the heartbeat when nothing traded.
    if not traded and _heartbeat_due(config.NOTIFY_STATUS_MINUTES):
        notify.send(status, title="Bot status")


if __name__ == "__main__":
    main()
