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


def swing_levels(prices, k=3):
    """Find recent support (swing lows) and resistance (swing highs) -- prices
    that stood out as a local low/high with `k` candles lower/higher on each
    side. Returns (resistances, supports)."""
    highs, lows = [], []
    for i in range(k, len(prices) - k):
        window = prices[i - k:i + k + 1]
        if prices[i] == max(window):
            highs.append(prices[i])
        if prices[i] == min(window):
            lows.append(prices[i])
    return highs, lows


def has_room(prices, direction, min_room):
    """Support/Resistance filter. For a LONG, True if there's at least `min_room`
    (fraction) of clear space up to the nearest resistance -- i.e. we're NOT
    buying right into a ceiling. Mirror for a SHORT (room down to support).
    True when there's no level in the way (clear sky)."""
    price = prices[-1]
    highs, lows = swing_levels(prices)
    if direction == "long":
        above = [h for h in highs if h > price * 1.001]
        if not above:
            return True                       # clear sky above
        return (min(above) - price) / price >= min_room
    below = [l for l in lows if l < price * 0.999]
    if not below:
        return True                           # clear floor below (for a short)
    return (price - max(below)) / price >= min_room


def at_support(prices, tol):
    """True if price is sitting right on a support level (a swing low) -- within
    `tol` (fraction). A bounce-long candidate."""
    price = prices[-1]
    _, lows = swing_levels(prices)
    return any(l > 0 and abs(price - l) / l <= tol for l in lows)


def at_resistance(prices, tol):
    """True if price is sitting right on a resistance level (a swing high).
    A bounce-short candidate."""
    price = prices[-1]
    highs, _ = swing_levels(prices)
    return any(h > 0 and abs(price - h) / h <= tol for h in highs)


def trend_up(prices):
    """True if this timeframe is in an uptrend (fast average above slow).
    Used for multi-timeframe confirmation before a LONG."""
    fast = simple_moving_average(prices, config.SMA_FAST)
    slow = simple_moving_average(prices, config.SMA_SLOW)
    return fast is not None and slow is not None and fast > slow


def trend_down(prices):
    """True if this timeframe is in a downtrend (fast average below slow).
    Used for multi-timeframe confirmation before a SHORT."""
    fast = simple_moving_average(prices, config.SMA_FAST)
    slow = simple_moving_average(prices, config.SMA_SLOW)
    return fast is not None and slow is not None and fast < slow


def short_signal(prices):
    """True if a confirmed SHORT setup is forming -- the exact mirror image of the
    'pro' long entry: a fresh downward crossover, downward momentum (not yet
    oversold), price below both averages, and the slow average already falling."""
    if len(prices) < config.SMA_SLOW + 1:
        return False
    fast_now = simple_moving_average(prices, config.SMA_FAST)
    slow_now = simple_moving_average(prices, config.SMA_SLOW)
    fast_prev = simple_moving_average(prices[:-1], config.SMA_FAST)
    slow_prev = simple_moving_average(prices[:-1], config.SMA_SLOW)
    rsi_now = rsi(prices, config.RSI_PERIOD)
    price_now = prices[-1]

    crossover_down = fast_prev >= slow_prev and fast_now < slow_now
    momentum_ok = rsi_now is not None and config.RSI_BUY < rsi_now <= 48
    below_trend = price_now < slow_now and price_now < fast_now
    slow_past = simple_moving_average(prices[:-5], config.SMA_SLOW)
    trend_falling = slow_past is not None and slow_now < slow_past
    return crossover_down and momentum_ok and below_trend and trend_falling


def _risk_exit(price_now, entry_price, high_water):
    """Shared safety net used while holding. Returns a (action, reason) SELL
    tuple if a risk rule fires, else None.

      * Hard stop-loss from entry -- caps the loss if the trade goes wrong fast.
      * Trailing stop -- once the price has risen, lock in gains by exiting if it
        falls TRAIL_PCT below the highest price seen since entry. This lets a
        winner run far above +16% while protecting the profit.
    """
    if not entry_price:
        return None
    if price_now <= entry_price * (1 - config.STOP_LOSS_PCT):
        return "SELL", (f"stop-loss hit (down "
                        f"{(1 - price_now / entry_price) * 100:.1f}%)")
    if high_water and price_now <= high_water * (1 - config.TRAIL_PCT):
        gain = (price_now / entry_price - 1) * 100
        return "SELL", (f"trailing stop ({config.TRAIL_PCT * 100:.0f}% off peak; "
                        f"locking in {gain:+.1f}% from entry)")
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


def stdev_of_returns(prices, window):
    """A simple volatility gauge: how bumpy recent day-to-day moves have been.
    Higher = riskier. None if not enough data."""
    if len(prices) < window + 1:
        return None
    rets = [(prices[i] / prices[i - 1] - 1) for i in range(-window, 0)]
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / len(rets)
    return var ** 0.5


def _decide_pro(prices, holding):
    """A more "experienced" strategy: it only buys when SEVERAL signals agree,
    which means it trades less often and avoids many bad entries -- the single
    biggest way to lower risk. It combines:

      * trend       (fast average just crossed above slow -> uptrend starting)
      * momentum    (RSI is rising but NOT yet overbought)
      * sanity      (price is above the slow average)

    It exits on the first sign of trouble: trend breaking down, or the price
    looking overbought (lock in gains). The stop-loss / take-profit safety net
    in decide() still applies on top of all this.
    """
    if len(prices) < config.SMA_SLOW + 1:
        return "HOLD", "not enough price history yet"

    fast_now = simple_moving_average(prices, config.SMA_FAST)
    slow_now = simple_moving_average(prices, config.SMA_SLOW)
    fast_prev = simple_moving_average(prices[:-1], config.SMA_FAST)
    slow_prev = simple_moving_average(prices[:-1], config.SMA_SLOW)
    rsi_now = rsi(prices, config.RSI_PERIOD)
    price_now = prices[-1]

    if holding:
        # Exit when the uptrend breaks (fast crosses back below slow). We do NOT
        # exit just because momentum is high -- the trailing stop in _risk_exit
        # takes profits instead, so a strong winner is free to keep running.
        if fast_prev >= slow_prev and fast_now < slow_now:
            return "SELL", "trend broke down (fast crossed below slow)"
        return "HOLD", "trend healthy; letting it run (trailing stop active)"

    # Entry: require ALL of these to agree -- the more filters, the fewer but
    # higher-quality the trades. We only take setups where the trend is clearly
    # already up, not just barely turning.
    crossover_up = fast_prev <= slow_prev and fast_now > slow_now
    momentum_ok = rsi_now is not None and 52 <= rsi_now < config.RSI_SELL
    above_trend = price_now > slow_now and price_now > fast_now
    # Slow average itself rising over the last 5 days = a real, established uptrend
    # (not a one-day blip). This filter avoids most "false start" entries.
    slow_past = simple_moving_average(prices[:-5], config.SMA_SLOW)
    trend_rising = slow_past is not None and slow_now > slow_past
    if crossover_up and momentum_ok and above_trend and trend_rising:
        return "BUY", (f"high-quality setup: confirmed uptrend, RSI {rsi_now:.0f}, "
                       f"price above both averages")
    return "HOLD", "no high-quality setup; staying out (most days are HOLD)"


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


def exponential_moving_average(prices, period):
    """EMA -- like a moving average but weights recent prices more, so it reacts
    faster to turns than a simple average. None if not enough data."""
    if len(prices) < period:
        return None
    k = 2.0 / (period + 1)
    e = sum(prices[:period]) / period      # seed with the SMA of the first window
    for p in prices[period:]:
        e = p * k + e * (1 - k)
    return e


def _decide_ema(prices, holding):
    """EMA crossover -- the faster-reacting cousin of the SMA strategy. Buy when
    the fast EMA crosses above the slow EMA, sell when it crosses back below."""
    if len(prices) < config.SMA_SLOW + 1:
        return "HOLD", "not enough price history yet"
    fast_now = exponential_moving_average(prices, config.SMA_FAST)
    slow_now = exponential_moving_average(prices, config.SMA_SLOW)
    fast_prev = exponential_moving_average(prices[:-1], config.SMA_FAST)
    slow_prev = exponential_moving_average(prices[:-1], config.SMA_SLOW)
    if holding:
        if fast_prev >= slow_prev and fast_now < slow_now:
            return "SELL", "EMA fast crossed below slow (downtrend)"
        return "HOLD", "EMA still in an uptrend; holding"
    if fast_prev <= slow_prev and fast_now > slow_now:
        return "BUY", "EMA fast crossed above slow (uptrend)"
    return "HOLD", "no EMA entry signal; waiting in cash"


def _price_std(prices, n):
    window = prices[-n:]
    m = sum(window) / n
    return (sum((p - m) ** 2 for p in window) / n) ** 0.5


def _decide_bollinger(prices, holding):
    """Bollinger Band mean-reversion -- buy a dip when price falls to the lower
    band (cheap relative to its recent range), sell when it reverts to the middle
    (the average). A classic 'buy low, sell back to fair value' strategy."""
    n = 20
    if len(prices) < n + 1:
        return "HOLD", "not enough price history yet"
    mid = sum(prices[-n:]) / n
    sd = _price_std(prices, n)
    lower = mid - 2 * sd
    price = prices[-1]
    if holding:
        if price >= mid:
            return "SELL", "price reverted to the mean (Bollinger middle)"
        return "HOLD", "below the mean; waiting for reversion up"
    if price <= lower:
        return "BUY", "price at the lower Bollinger band (oversold dip)"
    return "HOLD", "price inside the bands; waiting for a dip"


def any_long_signal(prices):
    """True if ANY of the built-in strategies (sma, rsi, breakout, pro) signals a
    BUY here -- so the bot can take a good setup from any of them, not just the
    one configured in STRATEGY."""
    for name in STRATEGIES:
        action, _ = decide(prices, False, 0.0, strategy_name=name)
        if action == "BUY":
            return True
    return False


def momentum_score(prices):
    """A number for RANKING coins that all have a BUY signal: higher = stronger.
    Uses how far the fast average sits above the slow average (trend strength)."""
    fast = simple_moving_average(prices, config.SMA_FAST)
    slow = simple_moving_average(prices, config.SMA_SLOW)
    if not fast or not slow:
        return 0.0
    return (fast / slow) - 1.0


# Registry so backtest.py can ask for any strategy by name.
STRATEGIES = {
    "sma": _decide_sma,
    "rsi": _decide_rsi,
    "breakout": _decide_breakout,
    "pro": _decide_pro,
    "ema": _decide_ema,
    "bollinger": _decide_bollinger,
}


def decide(prices, holding, entry_price, high_water=0.0, strategy_name=None):
    """Top-level decision. Picks the strategy (defaults to config.STRATEGY),
    but ALWAYS checks the stop-loss / trailing-stop safety net first.

    `high_water` is the highest price seen since entry (for the trailing stop).
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
        exit_signal = _risk_exit(price_now, entry_price, high_water)
        if exit_signal:
            return exit_signal

    return STRATEGIES[name](prices, holding)
