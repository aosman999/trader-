"""
strategy.py
===========
The "brain" that looks at recent prices and says BUY, SELL, or HOLD.

It offers THREE classic strategies (pick one with STRATEGY in config.py):

  "sma"      moving-average crossover  -- ride trends
  "rsi"      RSI mean-reversion        -- buy dips, sell spikes
  "breakout" Donchian breakout         -- buy new highs, sell new lows

Whichever you pick, the same safety rules apply while holding coins:
a STOP-LOSS (cut losses) and a TAKE-PROFIT (lock in gains).

This file only produces a decision. bot.py is what acts on it with fake money.
"""

import config


# ---------------------------------------------------------------------------
# Indicator helpers (small reusable math building blocks)
# ---------------------------------------------------------------------------

def simple_moving_average(prices, window):
    """Average of the last `window` prices. None if not enough data."""
    if len(prices) < window:
        return None
    return sum(prices[-window:]) / window


def rsi(prices, period):
    """Relative Strength Index (0-100). None if not enough data.

    It compares the size of recent up-moves to recent down-moves. A high value
    means price has been rising hard (overbought); a low value means it has
    been falling hard (oversold).
    """
    if len(prices) < period + 1:
        return None
    gains = 0.0
    losses = 0.0
    # Look at the last `period` day-to-day changes.
    for i in range(-period, 0):
        change = prices[i] - prices[i - 1]
        if change >= 0:
            gains += change
        else:
            losses -= change  # make it a positive number
    if losses == 0:
        return 100.0  # nothing but gains -> maximally overbought
    rs = (gains / period) / (losses / period)
    return 100 - (100 / (1 + rs))


def _risk_exit(price_now, entry_price):
    """Shared safety net used by every strategy while holding. Returns a
    (action, reason) SELL tuple if a risk rule fires, else None."""
    if not entry_price:
        return None
    if price_now <= entry_price * (1 - config.STOP_LOSS_PCT):
        return "SELL", (f"stop-loss hit (down "
                        f"{(1 - price_now / entry_price) * 100:.1f}%)")
    if price_now >= entry_price * (1 + config.TAKE_PROFIT_PCT):
        return "SELL", (f"take-profit hit (up "
                        f"{(price_now / entry_price - 1) * 100:.1f}%)")
    return None


# ---------------------------------------------------------------------------
# The three strategies. Each returns (action, reason).
# ---------------------------------------------------------------------------

def _decide_sma(prices, holding):
    if len(prices) < config.SMA_SLOW + 1:
        return "HOLD", "not enough price history yet"
    fast_now = simple_moving_average(prices, config.SMA_FAST)
    slow_now = simple_moving_average(prices, config.SMA_SLOW)
    fast_prev = simple_moving_average(prices[:-1], config.SMA_FAST)
    slow_prev = simple_moving_average(prices[:-1], config.SMA_SLOW)

    if holding:
        if fast_prev >= slow_prev and fast_now < slow_now:
            return "SELL", "fast average crossed below slow (downtrend)"
        return "HOLD", "still in an uptrend; holding"
    if fast_prev <= slow_prev and fast_now > slow_now:
        return "BUY", "fast average crossed above slow (uptrend)"
    return "HOLD", "no entry signal; waiting in cash"


def _decide_rsi(prices, holding):
    value = rsi(prices, config.RSI_PERIOD)
    if value is None:
        return "HOLD", "not enough price history yet"
    if holding:
        if value >= config.RSI_SELL:
            return "SELL", f"RSI {value:.0f} is overbought (>= {config.RSI_SELL})"
        return "HOLD", f"RSI {value:.0f}; holding until overbought"
    if value <= config.RSI_BUY:
        return "BUY", f"RSI {value:.0f} is oversold (<= {config.RSI_BUY})"
    return "HOLD", f"RSI {value:.0f}; waiting for an oversold dip"


def _decide_breakout(prices, holding):
    n = config.DONCHIAN_DAYS
    if len(prices) < n + 1:
        return "HOLD", "not enough price history yet"
    price_now = prices[-1]
    window = prices[-n - 1:-1]      # the n days BEFORE today
    high = max(window)
    low = min(window)
    if holding:
        if price_now < low:
            return "SELL", f"price broke below {n}-day low (${low:,.0f})"
        return "HOLD", "holding; no breakdown yet"
    if price_now > high:
        return "BUY", f"price broke above {n}-day high (${high:,.0f})"
    return "HOLD", "no breakout yet; waiting in cash"


# Registry so backtest.py can ask for any strategy by name.
STRATEGIES = {
    "sma": _decide_sma,
    "rsi": _decide_rsi,
    "breakout": _decide_breakout,
}


def decide(prices, holding, entry_price, strategy_name=None):
    """Top-level decision. Picks the strategy (defaults to config.STRATEGY),
    but ALWAYS checks the stop-loss / take-profit safety net first.

    Returns (action, reason) where action is "BUY", "SELL", or "HOLD".
    """
    name = strategy_name or config.STRATEGY
    if name not in STRATEGIES:
        raise ValueError(f"Unknown STRATEGY {name!r}. "
                         f"Choose one of: {', '.join(STRATEGIES)}")

    price_now = prices[-1]

    # Safety net comes first: if we're holding and a risk rule fires, exit now
    # regardless of what the strategy thinks.
    if holding:
        exit_signal = _risk_exit(price_now, entry_price)
        if exit_signal:
            return exit_signal

    return STRATEGIES[name](prices, holding)
