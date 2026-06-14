"""
strategy.py
===========
The "brain" that looks at recent prices and says BUY, SELL, or HOLD.

It uses the moving-average crossover idea explained in config.py, plus the
risk rules (stop-loss / take-profit). It does NOT know about money or fees --
it only produces a decision. bot.py is what acts on that decision.
"""

import config


def simple_moving_average(prices, window):
    """Average of the last `window` prices. Returns None if not enough data."""
    if len(prices) < window:
        return None
    return sum(prices[-window:]) / window


def decide(prices, holding, entry_price):
    """Look at the price history and return (action, reason).

    action is one of: "BUY", "SELL", "HOLD".

    Parameters:
      prices       -- list of daily closes, oldest first, newest last
      holding      -- True if we currently own the coin, else False
      entry_price  -- the price we paid when we bought (only used if holding)
    """
    price_now = prices[-1]

    # Need yesterday's averages too, so we can detect a "crossover" (a change
    # from one side to the other). That requires one extra day of history.
    if len(prices) < config.SMA_SLOW + 1:
        return "HOLD", "not enough price history yet"

    fast_now = simple_moving_average(prices, config.SMA_FAST)
    slow_now = simple_moving_average(prices, config.SMA_SLOW)
    fast_prev = simple_moving_average(prices[:-1], config.SMA_FAST)
    slow_prev = simple_moving_average(prices[:-1], config.SMA_SLOW)

    # ---- Rules that apply while we OWN the coin -------------------------------
    if holding:
        # Risk rule 1: stop-loss. Cut losses if price dropped too far.
        if price_now <= entry_price * (1 - config.STOP_LOSS_PCT):
            return "SELL", (f"stop-loss hit (down "
                            f"{(1 - price_now / entry_price) * 100:.1f}%)")

        # Risk rule 2: take-profit. Lock in gains if price rose enough.
        if price_now >= entry_price * (1 + config.TAKE_PROFIT_PCT):
            return "SELL", (f"take-profit hit (up "
                            f"{(price_now / entry_price - 1) * 100:.1f}%)")

        # Trend rule: fast average crossed BELOW slow average -> trend turning
        # down -> get out.
        if fast_prev >= slow_prev and fast_now < slow_now:
            return "SELL", "fast average crossed below slow (downtrend)"

        return "HOLD", "still in an uptrend; holding"

    # ---- Rules that apply while we are in CASH (not holding) ------------------
    # Buy when the fast average crosses ABOVE the slow average (uptrend begins).
    if fast_prev <= slow_prev and fast_now > slow_now:
        return "BUY", "fast average crossed above slow (uptrend)"

    return "HOLD", "no entry signal; waiting in cash"
