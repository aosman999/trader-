#!/usr/bin/env python3
"""
learn.py  --  the bot's self-improvement: test the strategies, use the best.
============================================================================

This is the honest version of "learning to trade better". It does NOT use a
mysterious AI that gets rich on its own. Instead, every so often it:

  1. Pulls recent REAL prices for the coins the bot watches.
  2. BACKTESTS every built-in strategy (trend / mean-reversion / breakout /
     multi-filter) across all of them -- replaying how each WOULD have traded.
  3. Scores them by average return (and win rate), and picks the best one.
  4. Writes the winner to best_strategy.json, which bot.py then trades with.

So the bot keeps adapting to current market conditions instead of being stuck on
one strategy. Run it yourself any time:

    python3 learn.py            # test on your real watchlist, pick the best
    python3 learn.py --demo     # test on offline practice prices

IMPORTANT, and not negotiable: a strategy winning a backtest is NOT a promise it
will win next week. Markets change. This tilts the odds in your favour; it can't
guarantee profit.
"""

import json
import os
import sys
import time

import backtest
import config
import strategy

BEST_FILE = "best_strategy.json"     # the chosen strategy the live bot reads
STAMP_FILE = "last_learn.json"        # when we last re-evaluated (for throttling)


def evaluate(broker, coins, interval):
    """Backtest every strategy across `coins`. Returns a per-strategy summary:
    {name: {avg_return, trades, winrate, coins}}."""
    rows = {name: [] for name in strategy.STRATEGIES}
    for coin in coins:
        try:
            prices = broker.get_prices(coin, interval)
        except Exception:  # noqa: BLE001 - a coin we can't price is skipped
            continue
        if len(prices) < config.SMA_SLOW + 5:
            continue
        for name in strategy.STRATEGIES:
            final, trades, wins = backtest.run_backtest(prices, name)
            rows[name].append((final / config.STARTING_CASH - 1.0, trades, wins))

    summary = {}
    for name, data in rows.items():
        if not data:
            continue
        tot_trades = sum(r[1] for r in data)
        tot_wins = sum(r[2] for r in data)
        summary[name] = {
            "avg_return": sum(r[0] for r in data) / len(data),
            "trades": tot_trades,
            "winrate": (tot_wins / tot_trades) if tot_trades else 0.0,
            "coins": len(data),
        }
    return summary


def pick_best(broker, coins, interval):
    """Return (best_strategy_name, summary). Considers only strategies that
    actually traded (a do-nothing strategy shouldn't 'win' by never risking
    anything); ranks by average return, then win rate."""
    summary = evaluate(broker, coins, interval)
    eligible = {n: s for n, s in summary.items() if s["trades"] >= 1}
    pool = eligible or summary
    if not pool:
        return config.STRATEGY, summary
    best = max(pool.items(), key=lambda kv: (kv[1]["avg_return"], kv[1]["winrate"]))
    return best[0], summary


def save_best(name, summary):
    with open(BEST_FILE, "w") as f:
        json.dump({"strategy": name, "when": time.strftime("%Y-%m-%d %H:%M"),
                   "summary": summary}, f, indent=2)


def load_best():
    if os.path.exists(BEST_FILE):
        try:
            with open(BEST_FILE) as f:
                return json.load(f)
        except Exception:  # noqa: BLE001
            return None
    return None


def due(every_hours):
    """True if it's been at least `every_hours` since the last evaluation."""
    if every_hours <= 0:
        return False
    last = 0.0
    if os.path.exists(STAMP_FILE):
        try:
            with open(STAMP_FILE) as f:
                last = json.load(f).get("ts", 0.0)
        except Exception:  # noqa: BLE001
            last = 0.0
    return time.time() - last >= every_hours * 3600


def mark_done():
    with open(STAMP_FILE, "w") as f:
        json.dump({"ts": time.time()}, f)


def main():
    use_demo = "--demo" in sys.argv
    import broker as broker_mod
    broker = broker_mod.PaperBroker(use_demo=True) if use_demo \
        else broker_mod.make_broker()
    try:
        coins = broker.universe()[:config.LEARN_COINS]
    except Exception as exc:  # noqa: BLE001
        print(f"Could not list coins: {exc}")
        return

    print(f"\n=== Strategy tournament | {len(coins)} coins | "
          f"{config.INTERVAL} | {'DEMO' if use_demo else 'LIVE'} ===")
    name, summary = pick_best(broker, coins, config.INTERVAL)
    print(f"  {'strategy':<12}{'avg return':>11}{'win rate':>10}{'trades':>8}")
    for n, s in sorted(summary.items(), key=lambda kv: -kv[1]["avg_return"]):
        star = "  <- best" if n == name else ""
        print(f"  {n:<12}{s['avg_return'] * 100:>+10.1f}%{s['winrate'] * 100:>9.0f}%"
              f"{s['trades']:>8}{star}")
    save_best(name, summary)
    mark_done()
    print(f"\n  Using '{name}' until the next check. (Past results don't "
          f"guarantee future ones.)\n")


if __name__ == "__main__":
    main()
