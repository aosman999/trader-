# Connecting the bot to MEXC FUTURES — read every line

> **⚠️ Futures are leveraged. You can lose your entire $20 fast — faster than
> with spot.** A leveraged position gets **liquidated** (force-closed at a total
> loss of its margin) when price moves against you by roughly `100 / leverage`
> percent. At 10x that's only a ~10% move; crypto does that in a day. This bot
> caps leverage at **10x** and defaults to **2x**, uses **isolated margin**, is
> **long-only**, keeps a **tight 2% stop-loss**, and only takes **high-quality
> setups** — but none of that removes the risk. Treat the $20 as money you are
> fully prepared to lose.

---

## How the safety design limits the damage

- **Leverage hard-capped at 10x** in `mexc_futures.py` (`MAX_LEVERAGE`). No
  setting can exceed it. Default is `LEVERAGE = 2` in `config.py`.
- **Isolated margin** — a losing trade can lose at most the margin placed on it,
  never the rest of your balance.
- **Long-only** — it never shorts (shorting adds a second way to lose).
- **Tight stop-loss (2%)** and **2:1 take-profit (4%)** — losers stay small,
  winners are bigger than losers.
- **Selective entries** — the `pro` strategy only trades a confirmed, established
  uptrend, so most days it does nothing. Fewer trades = fewer ways to lose.
- **`MAX_MARGIN_USD`** caps how much margin any single trade uses.
- **Dry-run by default** — builds and logs orders but places nothing until you
  deliberately turn it off.

## Step 1 — Create futures-enabled API keys

1. MEXC → **API Management** → create a key.
2. Enable **Futures trading** permission. **Do NOT enable Withdrawals.**
3. IP-whitelist the key if you can.
4. Save the API Key and Secret. Never put them in a file or share them.

> MEXC has at times restricted futures order placement via API for retail
> accounts. If the check in Step 3 fails with a permission error, your account
> may not be allowed to trade futures through the API — that's a MEXC setting,
> not something code can fix.

## Step 2 — Set the keys as environment variables

```bash
export MEXC_API_KEY="your_api_key_here"
export MEXC_API_SECRET="your_secret_key_here"
```
(Windows / making them permanent: see MEXC_SETUP.md, same idea.)

## Step 3 — Prove it works, trading nothing

```bash
python3 check_mexc_futures.py
```
Four read-only checks (price, contract size, balance, positions). Places no
orders. If all pass, the connection works.

## Step 4 — Point the bot at futures (still safe)

In `config.py`:
```python
BROKER = "mexc_futures"
LEVERAGE = 2          # up to 10; higher = closer to liquidation
```
Now `python3 bot.py` decides on real futures prices and your real balance, but
because `DRY_RUN_DEFAULT = True` in `mexc_futures.py`, it only *builds* the order
and logs `DRY-RUN: would OPEN LONG ...` — placing nothing. Run it as a daily
routine (see SCHEDULING.md) and watch `bot.log` for a while.

## Step 5 — Going live (only when truly ready)

Do **not** until Step 3 passes and you've watched dry-run for a while.

1. In `mexc_futures.py` set `DRY_RUN_DEFAULT = False`. Keep `LEVERAGE` low and
   `MAX_MARGIN_USD` small.
2. Run `python3 bot.py` **by hand**, watch the first real position open, and
   confirm it on MEXC. Check the **liquidation price** MEXC shows you.
3. Only then let the daily routine carry it.

Flip back to safety anytime: `DRY_RUN_DEFAULT = True`, or `BROKER = "paper"`.
Tell me when Step 3 passes and we'll do go-live together, carefully.
