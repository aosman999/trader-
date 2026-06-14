"""
config.py
=========
All the knobs for the paper-trading bot live here, in one place.

A "paper-trading" bot uses REAL market prices but FAKE money. Nothing here
can touch a real exchange account or real funds. It's a flight simulator for
trading: you get to watch a strategy play out with zero financial risk.

Change the numbers below to experiment. Every setting is explained.
"""

# ---------------------------------------------------------------------------
# WHAT TO TRADE
# ---------------------------------------------------------------------------

# The crypto symbol. "BTC" = Bitcoin, "ETH" = Ethereum, "SOL" = Solana, etc.
# We always trade it against US dollars (USD/USDT).
SYMBOL = "BTC"

# WHERE trades happen:
#   "paper"        -> fake money (the safe default; use this for weeks first)
#   "mexc"         -> your REAL MEXC SPOT account (you own the coin; no leverage)
#   "mexc_futures" -> your REAL MEXC FUTURES account (LEVERAGED; can be liquidated)
# IMPORTANT: even with a real broker, nothing trades until you turn OFF dry-run
# in mexc.py / mexc_futures.py. Until then it only validates/builds orders.
# Read MEXC_SETUP.md (spot) or FUTURES_SETUP.md (futures) before changing this.
BROKER = "paper"

# FUTURES ONLY -- how much leverage to use. HARD-capped at 10x in code
# (mexc_futures.MAX_LEVERAGE); nothing can exceed it. Higher leverage = a
# smaller price move can liquidate (zero out) the trade. We default LOW on
# purpose; raise it only if you truly accept the added risk.
#   At  2x: a ~50% adverse move liquidates.   At 10x: a ~10% move liquidates.
LEVERAGE = 2

# ---------------------------------------------------------------------------
# YOUR (PRETEND) MONEY
# ---------------------------------------------------------------------------

# How much fake cash the bot starts with the very first time it runs.
# Set to $20 to mirror the real-money plan, so the paper results reflect what
# that size of account would actually do (fees and small-order limits included).
# After the first run, the balance is remembered in portfolio.json.
STARTING_CASH = 20.0  # dollars

# ---------------------------------------------------------------------------
# RISK MANAGEMENT  (the most important part)
# ---------------------------------------------------------------------------
# These rules exist so a single bad trade can't wipe you out. In real trading,
# protecting your downside matters far more than chasing big wins.

# When the bot decides to BUY, what fraction of available cash does it use?
# 0.50 means "spend at most half of my cash on this trade." Keeping some cash
# in reserve means one trade going wrong doesn't sink everything.
TRADE_FRACTION = 0.50

# Stop-loss: if the price falls this far below our entry, exit immediately to
# cut the loss SMALL. 0.02 = exit if price drops 2%.
#   NOTE ON LEVERAGE (futures): a price stop is multiplied by leverage in money
#   terms. At 10x, a 2% price stop ~= losing 20% of that trade's margin. Keeping
#   this tight is what stops a single trade from doing real damage.
STOP_LOSS_PCT = 0.02

# Take-profit: lock in the gain once price rises this far above entry.
# 0.04 = take profit at +4%. This is set wider than the stop (2:1), so the
# winners are bigger than the losers -- which matters more than win rate.
TAKE_PROFIT_PCT = 0.04

# ---------------------------------------------------------------------------
# WHICH STRATEGY TO USE
# ---------------------------------------------------------------------------
# The bot ships with three classic, easy-to-understand strategies. Pick one
# here. Use backtest.py to compare how all three would have performed before
# committing to one. None of them is magic; none wins every time.
#
#   "sma"      Moving-average crossover. Rides trends: buys when prices start
#              climbing, sells when they start falling. (Good all-rounder.)
#   "rsi"      RSI mean-reversion. Buys when the coin looks "oversold" (beaten
#              down) and sells when it looks "overbought." (Bargain hunting.)
#   "breakout" Donchian breakout. Buys when price punches above its recent
#              high, sells when it drops below its recent low. (Momentum.)
#   "pro"      The "experienced" one. Only buys when trend, momentum, AND price
#              all agree, so it trades less and avoids many bad entries -- the
#              biggest way to lower risk. Exits at the first sign of trouble.
STRATEGY = "pro"

# --- settings for the "sma" strategy ---
# A moving average is the average price over the last N days. We track a FAST
# one (reacts quickly) and a SLOW one (reacts slowly). Fast crossing above slow
# is a BUY; crossing below is a SELL.
SMA_FAST = 10   # fast moving average, in days
SMA_SLOW = 30   # slow moving average, in days

# --- settings for the "rsi" strategy ---
# RSI is a 0-100 gauge of how hard a price has recently risen vs fallen.
# Below ~30 = "oversold" (possible bargain -> buy). Above ~70 = "overbought"
# (possibly overheated -> sell).
RSI_PERIOD = 14
RSI_BUY = 30    # buy when RSI dips below this
RSI_SELL = 70   # sell when RSI rises above this

# --- settings for the "breakout" strategy ---
# Look back this many days. Buy if today's price is the highest in that window;
# sell if it's the lowest.
DONCHIAN_DAYS = 20

# How many days of price history to download each run. Needs to be comfortably
# larger than SMA_SLOW so the averages have enough data.
HISTORY_DAYS = 120

# ---------------------------------------------------------------------------
# REALISM
# ---------------------------------------------------------------------------

# Exchanges charge a fee on every trade. We simulate it so the paper results
# aren't unrealistically rosy. 0.001 = 0.1% per trade (typical for crypto).
FEE_PCT = 0.001

# ---------------------------------------------------------------------------
# FILES  (where the bot remembers things between runs)
# ---------------------------------------------------------------------------

STATE_FILE = "portfolio.json"   # current cash + holdings
LOG_FILE = "trades.csv"         # a row for every buy/sell, for your records
