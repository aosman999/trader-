# Run the bot 24/7 on a cheap server — 3 steps

This puts the bot on a small always-on cloud computer (a "VPS") that you own,
so it runs by itself without your laptop or phone. It starts in **dry-run**
(places no real orders) so you can watch it safely first.

> Make a **fresh** MEXC API key first (Futures ON, Withdrawals OFF). Never reuse
> a key you've pasted anywhere.

---

## Step 1 — Rent the server (about 5 minutes)

1. Sign up at a provider — e.g. **Hetzner** (cheapest, ~€4/mo), **DigitalOcean**,
   or **AWS Lightsail**.
2. Create the smallest server, choosing **Ubuntu** as the system.
3. They give you an **IP address** and a **password** (or set one). Keep them.

## Step 2 — Put the bot on it (copy-paste)

Connect to the server from your computer's terminal (use your real IP):

```bash
ssh root@YOUR_SERVER_IP
```

Then paste this block to install everything and download the bot:

```bash
apt update && apt install -y git python3
git clone https://github.com/aosman999/trader-.git
cd trader-
git checkout claude/gallant-allen-wk749j
```

Add your **fresh** keys so they're remembered every time:

```bash
echo 'export MEXC_API_KEY="your_new_key"'    >> ~/.bashrc
echo 'export MEXC_API_SECRET="your_new_secret"' >> ~/.bashrc
source ~/.bashrc
```

Point the bot at MEXC futures, then test the connection (places no trade):

```bash
sed -i 's/^BROKER = .*/BROKER = "mexc_futures"/' config.py
python3 check_mexc_futures.py
```

You want all four checks to say `ok`. (If they fail, your MEXC account may not
be allowed to trade futures by API — see FUTURES_SETUP.md.)

## Step 3 — Make it run every hour

```bash
chmod +x run_daily.sh setup_schedule.sh
./setup_schedule.sh hourly
```

Done. It now runs every hour on its own. It is still in **dry-run**, so it
writes `DRY-RUN: would OPEN LONG…` to `bot.log` and trades nothing.

Watch what it's doing anytime:

```bash
tail -n 30 bot.log
```

---

## Going live later (one line, when you're ready)

After watching dry-run for a while:

```bash
sed -i 's/^DRY_RUN_DEFAULT = True/DRY_RUN_DEFAULT = False/' mexc_futures.py
python3 bot.py        # run once by hand and watch the first REAL order
```

Flip back to safe anytime by setting it to `True` again. Keep `LEVERAGE` low and
the `$12` floor in place. Trade only money you can afford to lose.
