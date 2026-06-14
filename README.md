# Crypto Paper-Trading Bot 🪙📝

A beginner-friendly bot that practices crypto trading with **fake money** and
**real prices**. It's a flight simulator for trading: you learn how a strategy
behaves over time **without risking a single real cent**.

> **Read this first — honest expectations**
>
> - This bot trades **pretend money only**. It is **not** connected to any
>   exchange or real funds and **cannot** make you real money.
> - **No bot, person, or algorithm can guarantee profit.** Markets are partly
>   random. Anyone promising guaranteed daily returns is mistaken or scamming.
> - The point here is to **learn safely**: watch a strategy, read its trades,
>   and understand risk — before you ever consider real money.

---

## What's inside

| File               | What it does                                                       |
|--------------------|-------------------------------------------------------------------|
| `config.py`        | All the settings (coin, fake cash, risk rules, strategy). Start here.|
| `data.py`          | Downloads real daily prices (tries several free sources).         |
| `strategy.py`      | The "brain": three selectable strategies (sma / rsi / breakout).  |
| `portfolio.py`     | Tracks the fake money; remembers it between runs.                  |
| `bot.py`           | **Run this once a day.** Makes one decision and updates your money.|
| `dashboard.py`     | A one-screen status report (read-only; never trades).             |
| `backtest.py`      | Replays **all** strategies over history and compares them.        |
| `run_daily.sh`     | Wrapper the scheduler calls; logs each run to `bot.log`.           |
| `setup_schedule.sh`| One command to run the bot automatically every day (macOS/Linux). |
| `SCHEDULING.md`    | How to automate the daily run (macOS/Linux **and** Windows).      |
| `mexc.py`          | Safe-by-default client for MEXC **spot** (you own the coin).       |
| `check_mexc.py`    | Proves your MEXC **spot** connection works **without trading**.    |
| `MEXC_SETUP.md`    | Step-by-step guide to connect MEXC spot safely.                   |
| `mexc_futures.py`  | MEXC **futures** client: leverage capped 10x, isolated, long-only.|
| `check_mexc_futures.py`| Proves your MEXC **futures** connection works **without trading**.|
| `FUTURES_SETUP.md` | Futures setup + heavy risk/leverage/liquidation warnings.         |
| `tests/`           | Quick self-tests that prove the logic works (no internet needed). |

It uses **only Python's standard library** — nothing to install.

---

## Quick start

You need Python 3.8 or newer. Check with `python3 --version`.

```bash
# 1. See it work instantly with offline practice data:
python3 bot.py --demo

# 2. Judge the strategy over a long history:
python3 backtest.py --demo

# 3. See a full status snapshot any time (read-only):
python3 dashboard.py --demo

# 4. When you have internet, use REAL market prices:
python3 bot.py

# Start over any time:
python3 bot.py --reset
```

## Run it automatically every day

Don't want to remember to run it? Schedule it (full guide in `SCHEDULING.md`):

```bash
# macOS / Linux — run daily at 09:00:
./setup_schedule.sh
# ...or pick a time, e.g. 6:30pm:
./setup_schedule.sh 18 30
# stop it later:
./setup_schedule.sh --remove
```

Each automated run is appended to `bot.log`. Windows users: see `SCHEDULING.md`.

## The daily routine

Run `python3 bot.py` once a day. Each run it:

1. loads your fake portfolio from last time,
2. fetches the latest real prices,
3. decides BUY / SELL / HOLD,
4. acts with fake money (respecting the risk rules), and
5. prints a summary and logs any trade to `trades.csv`.

> Tip: you can automate the daily run later with `cron` (Mac/Linux) or Task
> Scheduler (Windows) — but run it by hand for a few weeks first so you
> understand what it's doing.

## The strategies (in plain English)

Pick one with `STRATEGY` in `config.py`, then compare them with `backtest.py`:

- **`sma`** — *moving-average crossover.* Track a fast average (10 days) and a
  slow one (30 days). Fast crossing **above** slow → uptrend → **BUY**; crossing
  **below** → downtrend → **SELL**. Rides trends.
- **`rsi`** — *mean-reversion.* RSI is a 0–100 "how overheated is the price"
  gauge. Buy when it's **oversold** (≤30), sell when **overbought** (≥70).
  Bargain-hunting.
- **`breakout`** — *Donchian breakout.* Buy when price sets a new 20-day **high**,
  sell when it sets a new 20-day **low**. Chases momentum.

Whichever you choose, two safety rules apply whenever it holds coins:

- **Stop-loss:** sell if down 5% (cut losses early).
- **Take-profit:** sell if up 10% (lock in gains).

Every number lives in `config.py` — change them and re-run the backtest to see
the effect. **No strategy always wins.** The demo backtest even shows all three
losing to simple buy-and-hold over one stretch. That's normal and honest — which
strategy wins depends entirely on the time period.

## Making it your own

- Trade a different coin: set `SYMBOL = "ETH"` (or `"SOL"`, etc.) in `config.py`.
- Be more cautious: lower `TRADE_FRACTION`, tighten `STOP_LOSS_PCT`.
- Try different trend speeds: change `SMA_FAST` / `SMA_SLOW`, then backtest.

## Going to real money (please read)

Don't rush this. A responsible path looks like:

1. Paper-trade here for **several weeks** and read every trade.
2. Backtest across **different time periods**, not just one lucky stretch.
3. If you still want to go live, use a regulated exchange's **own** API with
   **tiny** amounts you can afford to lose, hard risk limits, and keys that are
   **read-only or trade-only (never withdrawal)**.
4. Understand the taxes and rules where you live.

Capital you put into crypto can go to **zero**. Only ever risk money you can
fully afford to lose.
