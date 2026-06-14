# Connecting the bot to MEXC (real account) — do this carefully

This guide gets the bot *talking* to your real MEXC account **without trading
yet**. We prove every piece works first. Take it one step at a time.

> **Honest reality check before you spend a cent**
> - **No bot makes guaranteed profit, and none profits every day.** Expect
>   losing days even when things go well.
> - **$20 is very small for live trading.** MEXC has minimum order sizes, and
>   fees (~0.1% per side) plus the bid/ask spread eat into every round-trip
>   trade. Fees on tiny trades can outweigh the strategy's edge. Treat this $20
>   as money you are **fully prepared to lose** — tuition, not an investment.
> - Go live **only after** weeks of paper trading you've actually watched.

---

## Step 1 — Create SAFE API keys on MEXC

1. Log in to MEXC → profile → **API Management**.
2. Create a new API key.
3. Permissions: enable **Spot Trading** ONLY.
   **Do NOT enable Withdrawals.** A trading bot never needs to move money out,
   so a leaked key can't drain your account.
4. If MEXC offers **IP whitelisting**, restrict the key to your computer's IP.
5. Copy the **API Key** and **Secret Key**. The secret is shown once — save it
   somewhere safe. **Never** paste these into any code file or share them.

## Step 2 — Put the keys in environment variables

The bot reads keys from your environment, never from a file, so they never get
committed to git or seen by anyone.

**macOS / Linux:**
```bash
export MEXC_API_KEY="your_api_key_here"
export MEXC_API_SECRET="your_secret_key_here"
```
(To make them stick between terminals, add those lines to `~/.bashrc` or
`~/.zshrc`.)

**Windows (PowerShell):**
```powershell
setx MEXC_API_KEY "your_api_key_here"
setx MEXC_API_SECRET "your_secret_key_here"
```
(Then open a **new** terminal so the values load.)

## Step 3 — Prove it works, trading nothing

```bash
python3 check_mexc.py
```

This runs three checks — fetch a price, read your balance, and **validate** a
tiny test order using MEXC's official `/order/test` endpoint (which places
nothing). If all three pass, the connection is correct and you still haven't
traded. If something fails, the script tells you what to fix.

---

## How the safety design protects you

- **`dry_run` is ON by default** (`mexc.py`). While on, every "buy"/"sell" is
  only *validated* against MEXC — no real order is placed.
- **`MAX_ORDER_USD`** caps the size of any single order, so a bug can't place a
  large trade.
- **Keys live only in your environment**, with **no withdrawal permission**.

## Going live (only when you're truly ready)

Do **not** do this until you've paper-traded for weeks and passed Step 3.

1. Start with the **smallest amount MEXC allows**, not the full $20.
2. We turn `dry_run` off *together*, watch the very first real order by hand,
   and confirm it on the MEXC website.
3. Keep `MAX_ORDER_USD` tight. Raise limits only slowly, deliberately.

The next coding step (once Step 3 passes for you) is to wire this MEXC client
into the daily bot as a selectable "broker," so the same `pro` strategy you've
been paper-testing can run against the real account — still gated behind
`dry_run`. Tell me when `check_mexc.py` passes and we'll do that part.
