# Running the bot automatically every day

The bot is meant to run **once a day**. You can do that by hand
(`python3 bot.py`) — but here's how to let your computer do it for you.

> Your computer must be **on and awake** at the scheduled time for it to run.
> A daily strategy doesn't need a always-on server; just pick a time you're
> usually powered on.

---

## macOS / Linux (easiest)

From inside this folder:

```bash
chmod +x run_daily.sh setup_schedule.sh
./setup_schedule.sh            # runs daily at 09:00
# or choose a time, e.g. 6:30pm:
./setup_schedule.sh 18 30
# or, to allow several trades per day, run every hour
# (match this with INTERVAL = "1h" in config.py):
./setup_schedule.sh hourly
```

> **Match the schedule to `config.INTERVAL`.** If `INTERVAL = "1h"`, schedule
> `hourly` so the bot checks each new hourly candle — that's what lets it take
> 0 trades on a quiet day and several on an active one. If `INTERVAL = "1d"`,
> a once-a-day schedule is right.

Check it's scheduled:

```bash
crontab -l
```

Stop it any time:

```bash
./setup_schedule.sh --remove
```

Each run is appended to **`bot.log`** in this folder, so you can review the
whole history whenever you like.

---

## Windows (Task Scheduler)

1. Press Start, type **Task Scheduler**, open it.
2. Click **Create Basic Task…**
3. Name it `Crypto Paper Bot`, click Next.
4. Trigger: **Daily**, pick a time, Next.
5. Action: **Start a program**.
6. Program/script: `python`
7. Add arguments: `bot.py`
8. Start in: the full path to this folder
   (e.g. `C:\Users\you\trader-`).
9. Finish.

To stop it later, delete the task from Task Scheduler.

---

## Good habits

- Run `python3 dashboard.py` whenever you want a status snapshot.
- Skim `trades.csv` and `bot.log` weekly to see what it's been doing.
- Re-run `python3 backtest.py` now and then to sanity-check the strategy.
