#!/usr/bin/env python3
"""
check_mexc_futures.py  --  prove the MEXC FUTURES connection works, trade NOTHING.
=================================================================================

Run this AFTER following FUTURES_SETUP.md (creating futures-enabled API keys and
setting MEXC_API_KEY / MEXC_API_SECRET).

It runs read-only checks and places NO orders:

  1. PUBLIC   : fetch the futures price            -> internet + MEXC reachable
  2. PUBLIC   : fetch the contract size            -> needed to size trades
  3. PRIVATE  : read your futures USDT balance      -> proves keys work
  4. PRIVATE  : read your open positions            -> proves futures permission

Important: MEXC has at times restricted futures ORDER placement via API. These
checks tell you whether your account can even read futures data with your keys.
If check 3 or 4 fails with a permission error, your account likely can't trade
futures via API -- and no amount of code changes that; it's a MEXC account setting.

    python3 check_mexc_futures.py
"""

import sys

import mexc_futures

SYMBOL = "BTC_USDT"   # futures pairs use an underscore


def main():
    client = mexc_futures.MexcFuturesClient()  # keys from env, dry-run ON

    print("\n=== MEXC FUTURES connection check (no trades placed) ===\n")

    try:
        price = client.get_price(SYMBOL)
        print(f"  [1/4] PUBLIC  ok  -- {SYMBOL} price ${price:,.2f}")
    except Exception as exc:  # noqa: BLE001
        print(f"  [1/4] PUBLIC  FAILED -- {exc}")
        return 1

    try:
        size = client.contract_size(SYMBOL)
        print(f"  [2/4] PUBLIC  ok  -- 1 contract = {size} {SYMBOL.split('_')[0]}")
    except Exception as exc:  # noqa: BLE001
        print(f"  [2/4] PUBLIC  FAILED -- {exc}")
        return 1

    try:
        usdt = client.usdt_balance()
        print(f"  [3/4] PRIVATE ok  -- futures USDT balance: ${usdt:,.2f}")
    except Exception as exc:  # noqa: BLE001
        print(f"  [3/4] PRIVATE FAILED -- {exc}")
        print("        Keys missing/wrong, or your account lacks FUTURES API")
        print("        permission. See FUTURES_SETUP.md.")
        return 1

    try:
        vol, avg = client.long_position(SYMBOL)
        if vol > 0:
            print(f"  [4/4] PRIVATE ok  -- open long: {vol} contracts @ ${avg:,.2f}")
        else:
            print("  [4/4] PRIVATE ok  -- no open position (clean slate)")
    except Exception as exc:  # noqa: BLE001
        print(f"  [4/4] PRIVATE FAILED -- {exc}")
        return 1

    print("\n  All checks passed and nothing was traded.")
    print(f"  Leverage is hard-capped at {mexc_futures.MAX_LEVERAGE}x; dry-run is")
    print("  still ON, so the bot won't place real orders until you turn it off.")
    print("  Next: read the 'Going live' section of FUTURES_SETUP.md.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
