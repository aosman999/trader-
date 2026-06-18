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

# MAX CONCURRENT POSITIONS -- how many different coins the bot may hold at once.
# 1 = all money in the single best setup (one coin at a time). 3 = it may spread
# across up to 3 coins. Each run it deploys all your available cash, split evenly
# across however many good setups it finds that moment: one great setup -> all
# the money in it; three at once -> a third each. export MAX_POSITIONS="3"
MAX_POSITIONS = _i("MAX_POSITIONS", "1")

# CAPITAL FLOOR -- the bot never knowingly risks money below this, and halts +
# closes if equity falls to it. export FLOOR_USD="12"
FLOOR_USD = _f("FLOOR_USD", "12")

# HOW the floor is protected:
#   "true"  (default, safer) -- RESERVE the floor as cash. The bot only ever
#           spends money ABOVE FLOOR_USD, so even a total loss leaves the floor
#           untouched. It simply can't go below the floor.
#   "false" (riskier) -- deploy ALL your cash into a trade. The floor is then
#           protected only by the circuit breaker: the bot exits everything and
#           HALTS the moment total equity falls to FLOOR_USD. A fast crash
#           between the once-a-minute checks could briefly dip below the floor.
# export RESERVE_FLOOR="false"
RESERVE_FLOOR = _s("RESERVE_FLOOR", "true").strip().lower() in (
    "true", "1", "yes", "on")

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

# When "true", a momentum entry fires if ANY built-in strategy (sma, rsi,
# breakout, pro) signals -- not just the one in STRATEGY above. More setups,
# more trades. export USE_ALL_STRATEGIES="true"
USE_ALL_STRATEGIES = _s("USE_ALL_STRATEGIES", "false").strip().lower() in (
    "true", "1", "yes", "on")

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

# A trade fires when at least this many CONFIRMATIONS line up -- in ANY
# combination (strategy, support/resistance, trend, buy/sell power, volume,
# room, S/R confluence). It does NOT need all of them. 2 = a solid pair like
# "support + volume" is enough; 3 = stricter. export MIN_CONFIRMATIONS="2"
MIN_CONFIRMATIONS = _i("MIN_CONFIRMATIONS", "2")

# SUPPORT/RESISTANCE filter. When "true", a setup must also have room to run --
# a LONG won't enter right under a resistance level, a SHORT won't enter right
# above support. SR_MIN_ROOM is the clear space required (0.03 = 3%).
# export USE_SR="true"
USE_SR = _s("USE_SR", "false").strip().lower() in ("true", "1", "yes", "on")
SR_MIN_ROOM = _f("SR_MIN_ROOM", "0.03")

# S/R BOUNCE entries. When "true", ALSO enter on a bounce: long when price sits
# on support AND buyers dominate; short when on resistance AND sellers dominate.
# This adds entry opportunities on top of the momentum signal. export USE_SR_BOUNCE="true"
USE_SR_BOUNCE = _s("USE_SR_BOUNCE", "false").strip().lower() in (
    "true", "1", "yes", "on")
SR_TOL = _f("SR_TOL", "0.01")   # how close to the level counts as "on" it (1%)
# A bounce is confirmed when the level shows up on at least this many timeframes
# (multi-timeframe S/R confluence -- a stronger level). 1 = just the primary
# timeframe (no confluence required). export BOUNCE_TF_MIN="2"
BOUNCE_TF_MIN = _i("BOUNCE_TF_MIN", "2")

# BUY/SELL POWER filter. When "true", measures buying vs selling pressure from
# recent volume (volume on up-candles / total). A LONG needs buyers in control
# (>= BUY_POWER_MIN); a SHORT needs sellers in control (<= 1 - BUY_POWER_MIN).
# export USE_BUY_POWER="true"
USE_BUY_POWER = _s("USE_BUY_POWER", "false").strip().lower() in (
    "true", "1", "yes", "on")
BUY_POWER_MIN = _f("BUY_POWER_MIN", "0.55")   # 0.55 = 55% of volume buying

# VOLUME filter. When "true", a setup must have real interest behind it: recent
# volume at least VOL_MIN_RATIO x its average. export USE_VOLUME="true"
USE_VOLUME = _s("USE_VOLUME", "false").strip().lower() in ("true", "1", "yes", "on")
VOL_MIN_RATIO = _f("VOL_MIN_RATIO", "1.0")    # 1.0 = at least average volume

# TRADING SESSIONS (UTC). Only trade during these market sessions; empty = 24/7.
# Options: NY, London, Tokyo, Sydney. NOTE: all four together cover almost the
# whole day, so listing all four is basically 24/7. Pick specific ones (e.g.
# "London,NY") to restrict to the high-liquidity hours. export TRADING_SESSIONS="London,NY"
TRADING_SESSIONS = [s.strip() for s in _s("TRADING_SESSIONS", "").split(",")
                    if s.strip()]

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
# SELF-IMPROVEMENT (learn & adapt)
# ---------------------------------------------------------------------------
# When "true", the bot periodically BACKTESTS every built-in strategy on recent
# real prices across the coins it watches, and switches to whichever performed
# best -- so it adapts to current conditions instead of being stuck on one. It
# re-checks every LEARN_EVERY_HOURS hours over LEARN_COINS coins. Honest limit:
# backtests use PAST data; a past winner is not a promise of future profit.
# export AUTO_LEARN="true"
AUTO_LEARN = _s("AUTO_LEARN", "false").strip().lower() in ("true", "1", "yes", "on")
LEARN_EVERY_HOURS = _i("LEARN_EVERY_HOURS", "24")
LEARN_COINS = _i("LEARN_COINS", "8")
# Text a weekly trade-performance report card (win rate, P/L). 0 = off.
REPORT_EVERY_DAYS = _i("REPORT_EVERY_DAYS", "7")

# Measure the goal on your SPOT account only (ignore the futures wallet). Set
# this "true" if you're trading spot only and want the $ target to track just
# spot. Default "false" = goal tracks spot + futures combined.
# export TARGET_SPOT_ONLY="true"
TARGET_SPOT_ONLY = _s("TARGET_SPOT_ONLY", "false").strip().lower() in (
    "true", "1", "yes", "on")

# ---------------------------------------------------------------------------
# REALISM / FILES
# ---------------------------------------------------------------------------

FEE_PCT = _f("FEE_PCT", "0.001")        # simulated trading fee for paper/backtest

STATE_FILE = "portfolio.json"           # paper cash + holdings
LOG_FILE = "trades.csv"                 # a row per buy/sell
