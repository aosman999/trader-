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

| File            | What it does                                                        |
|-----------------|---------------------------------------------------------------------|
| `config.py`     | All the settings (coin, fake cash, risk rules, strategy). Start here.|
| `data.py`       | Downloads real daily prices (tries several free sources).           |
| `strategy.py`   | The "brain": decides BUY / SELL / HOLD.                             |
| `portfolio.py`  | Tracks the fake money; remembers it between runs.                    |
| `bot.py`        | **Run this once a day.** Makes one decision and updates your money.  |
| `backtest.py`   | Replays the strategy over months of history to judge it.            |
| `tests/`        | Quick self-tests that prove the logic works (no internet needed).   |

It uses **only Python's standard library** — nothing to install.

---

## Quick start

You need Python 3.8 or newer. Check with `python3 --version`.

```bash
# 1. See it work instantly with offline practice data:
python3 bot.py --demo

# 2. Judge the strategy over a long history:
python3 backtest.py --demo

# 3. When you have internet, use REAL market prices:
python3 bot.py

# Start over any time:
python3 bot.py --reset
```

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

## The strategy (in plain English)

It uses a **moving-average crossover** — one of the oldest, simplest ideas:

- Track a **fast** average (last 10 days) and a **slow** average (last 30 days).
- Fast crosses **above** slow → prices trending up → **BUY**.
- Fast crosses **below** slow → prices trending down → **SELL**.

Plus two safety rules whenever it holds coins:

- **Stop-loss:** sell if down 5% (cut losses early).
- **Take-profit:** sell if up 10% (lock in gains).

Every number above lives in `config.py` — change them and re-run the backtest
to see the effect. **This strategy will not always win.** The demo backtest
even shows it losing to simple buy-and-hold sometimes. That's normal and honest.

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
