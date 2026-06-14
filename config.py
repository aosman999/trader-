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

# ---------------------------------------------------------------------------
# YOUR (PRETEND) MONEY
# ---------------------------------------------------------------------------

# How much fake cash the bot starts with the very first time it runs.
# After that, the real balance is remembered in portfolio.json.
STARTING_CASH = 10_000.0  # dollars

# ---------------------------------------------------------------------------
# RISK MANAGEMENT  (the most important part)
# ---------------------------------------------------------------------------
# These rules exist so a single bad trade can't wipe you out. In real trading,
# protecting your downside matters far more than chasing big wins.

# When the bot decides to BUY, what fraction of available cash does it use?
# 0.50 means "spend at most half of my cash on this trade." Keeping some cash
# in reserve means one trade going wrong doesn't sink everything.
TRADE_FRACTION = 0.50

# Stop-loss: if the price falls this far below what we paid, sell immediately
# to cut the loss. 0.05 = sell if we're down 5%.
STOP_LOSS_PCT = 0.05

# Take-profit: if the price rises this far above what we paid, sell to lock in
# the gain. 0.10 = sell once we're up 10%.
TAKE_PROFIT_PCT = 0.10

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
