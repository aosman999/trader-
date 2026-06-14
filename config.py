"""
config.py
=========
All the knobs for the bot. Every value below has a sensible default, but each
can be overridden in your keys.env file WITHOUT editing this file -- which means
updates (git pull) never overwrite your settings.

To change a setting, add a line to keys.env, e.g.:
    export BROKER="mexc_futures"
    export LEVERAGE="3"
    export WATCHLIST="BTC,ETH,SOL"
"""

import os


def _s(name, default):
    return os.environ.get(name, default)


def _f(name, default):
    return float(os.environ.get(name, default))


def _i(name, default):
    return int(os.environ.get(name, default))


# ---------------------------------------------------------------------------
# WHAT TO TRADE
# ---------------------------------------------------------------------------

# The crypto symbol used for single-coin tools (dashboard, backtest).
SYMBOL = _s("SYMBOL", "BTC")

# WATCHLIST -- which coins to scan.
#   "AUTO" (default) = automatically use the most actively-traded USDT coins on
#          MEXC, so the bot can trade ANY coin, not a fixed list.
#   or an explicit list to restrict it, e.g.  export WATCHLIST="BTC,ETH,SOL"
_WL = _s("WATCHLIST", "AUTO").strip()
WATCHLIST_AUTO = _WL.upper() in ("AUTO", "ALL", "")
WATCHLIST = [] if WATCHLIST_AUTO else [c.strip() for c in _WL.split(",") if c.strip()]

# In AUTO mode, scan at most this many of the most-active coins each run. Keeps
# runs fast and within MEXC's rate limits; the most liquid coins are also the
# safest to trade (tight spreads). Raise it to cover more coins per run.
# export MAX_SCAN="30"
MAX_SCAN = _i("MAX_SCAN", "30")

# WHERE trades happen: "paper" (fake money), "mexc" (real spot), or
# "mexc_futures" (real leveraged futures). Set in keys.env: export BROKER="..."
BROKER = _s("BROKER", "paper")

# FUTURES ONLY -- leverage, HARD-capped at 10x in code. Higher = closer to
# liquidation. export LEVERAGE="2"
LEVERAGE = _i("LEVERAGE", "2")

# ---------------------------------------------------------------------------
# YOUR MONEY
# ---------------------------------------------------------------------------

# Starting balance for paper trading (mirrors your real plan). export STARTING_CASH="20"
STARTING_CASH = _f("STARTING_CASH", "20")

# ---------------------------------------------------------------------------
# RISK MANAGEMENT  (the most important part)
# ---------------------------------------------------------------------------

# Fraction of available cash used per BUY. export TRADE_FRACTION="0.5"
TRADE_FRACTION = _f("TRADE_FRACTION", "0.5")

# CAPITAL FLOOR -- the bot never knowingly risks money below this, and halts +
# closes if equity falls to it. export FLOOR_USD="12"
FLOOR_USD = _f("FLOOR_USD", "12")

# Stop-loss: exit if price moves this far against entry. 0.04 = 4%.
# export STOP_LOSS_PCT="0.04"
STOP_LOSS_PCT = _f("STOP_LOSS_PCT", "0.04")

# Trailing take-profit: let winners run, exit this far below the peak-since-entry.
# 0.05 = 5% off the peak. export TRAIL_PCT="0.05"
TRAIL_PCT = _f("TRAIL_PCT", "0.05")

# ---------------------------------------------------------------------------
# STRATEGY
# ---------------------------------------------------------------------------
# "sma", "rsi", "breakout", or "pro" (the selective multi-signal one).
STRATEGY = _s("STRATEGY", "pro")

SMA_FAST = _i("SMA_FAST", "10")     # fast moving average length
SMA_SLOW = _i("SMA_SLOW", "30")     # slow moving average length

RSI_PERIOD = _i("RSI_PERIOD", "14")
RSI_BUY = _i("RSI_BUY", "30")       # buy when RSI dips below this
RSI_SELL = _i("RSI_SELL", "70")     # sell when RSI rises above this

DONCHIAN_DAYS = _i("DONCHIAN_DAYS", "20")

# Primary timeframe the bot triggers and exits on: "1m","5m","15m","30m",
# "1h","4h","1d","1w". export INTERVAL="1m"
INTERVAL = _s("INTERVAL", "1m")

# Candles of history to download each run.
HISTORY_DAYS = _i("HISTORY_DAYS", "120")

# MULTI-TIMEFRAME CONFIRMATION -- before entering, check the trend on all these
# and only buy when at least MIN_TF_AGREE of them are in an uptrend.
TIMEFRAMES = [c.strip() for c in
              _s("TIMEFRAMES", "1m,5m,15m,30m,1h,4h,1d,1w").split(",") if c.strip()]
MIN_TF_AGREE = _i("MIN_TF_AGREE", "6")

# SUPPORT/RESISTANCE filter. When "true", a setup must also have room to run --
# a LONG won't enter right under a resistance level, a SHORT won't enter right
# above support. SR_MIN_ROOM is the clear space required (0.03 = 3%).
# export USE_SR="true"
USE_SR = _s("USE_SR", "false").strip().lower() in ("true", "1", "yes", "on")
SR_MIN_ROOM = _f("SR_MIN_ROOM", "0.03")

# BUY/SELL POWER filter. When "true", measures buying vs selling pressure from
# recent volume (volume on up-candles / total). A LONG needs buyers in control
# (>= BUY_POWER_MIN); a SHORT needs sellers in control (<= 1 - BUY_POWER_MIN).
# export USE_BUY_POWER="true"
USE_BUY_POWER = _s("USE_BUY_POWER", "false").strip().lower() in (
    "true", "1", "yes", "on")
BUY_POWER_MIN = _f("BUY_POWER_MIN", "0.55")   # 0.55 = 55% of volume buying

# DON'T SIT IDLE TOO LONG. If MAX_IDLE_DAYS > 0 and no trade has happened in that
# many days, the bot takes the BEST available candidate even without full
# multi-timeframe confirmation -- so it never goes longer than this without
# trading. The clock resets on every trade. 0 = off (purely selective).
# Note: a forced trade is lower quality than a confirmed one, so keep this
# generous. export MAX_IDLE_DAYS="3"
MAX_IDLE_DAYS = _i("MAX_IDLE_DAYS", "0")

# FUTURES SIGNALS (manual). MEXC blocks placing futures orders via API, but you
# can trade futures by hand. If "true", whenever the bot finds a confirmed setup
# it TEXTS you the trade to place yourself (coin, LONG, entry, leverage, take-
# profit, stop-loss). Spot still auto-trades on its own. export FUTURES_SIGNALS="true"
FUTURES_SIGNALS = _s("FUTURES_SIGNALS", "false").strip().lower() in (
    "true", "1", "yes", "on")
# Fixed take-profit % shown in the texted signal (a manual trade can't trail).
# export SIGNAL_TP_PCT="0.16"
SIGNAL_TP_PCT = _f("SIGNAL_TP_PCT", "0.16")

# ---------------------------------------------------------------------------
# NOTIFICATIONS
# ---------------------------------------------------------------------------

# Send a status notification (what it found) at most this often, in minutes.
# 0 = off. export NOTIFY_STATUS_MINUTES="15"
NOTIFY_STATUS_MINUTES = _i("NOTIFY_STATUS_MINUTES", "15")

# PROFIT GOAL. When your spot balance reaches TARGET_USD, the bot texts you a
# milestone alert. By default it KEEPS TRADING after that; set TARGET_STOP="true"
# if you'd rather it stop and bank the win. 0 = off. It's a price level, not a
# deadline -- no setting makes a target arrive faster than the market allows.
# export TARGET_USD="1000"
TARGET_USD = _f("TARGET_USD", "0")
TARGET_STOP = _s("TARGET_STOP", "false").strip().lower() in ("true", "1", "yes", "on")

# Optional DEADLINE for the goal, in days. This is PURELY a progress tracker --
# it reports how you're pacing toward the target and how many days are left. It
# does NOT and CANNOT make returns arrive faster; forcing a deadline would only
# make the bot take reckless trades and lose money. export TARGET_DAYS="21"
TARGET_DAYS = _i("TARGET_DAYS", "0")

# ---------------------------------------------------------------------------
# REALISM / FILES
# ---------------------------------------------------------------------------

FEE_PCT = _f("FEE_PCT", "0.001")        # simulated trading fee for paper/backtest

STATE_FILE = "portfolio.json"           # paper cash + holdings
LOG_FILE = "trades.csv"                 # a row per buy/sell
