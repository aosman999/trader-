#!/usr/bin/env python3
"""
check_mexc.py  --  prove the MEXC connection works WITHOUT trading.
==================================================================

Run this AFTER following MEXC_SETUP.md (creating trade-only API keys and
setting the MEXC_API_KEY / MEXC_API_SECRET environment variables).

It performs three safe checks and places NO real orders:

  1. PUBLIC  : fetch the current price        -> proves internet + MEXC reachable
  2. PRIVATE : read your account balances      -> proves your API keys work
  3. ORDER   : VALIDATE a tiny test order      -> proves order building is correct
               (uses MEXC's /order/test, which validates and places nothing)

If all three pass, the plumbing is correct and you still haven't risked a cent.

    python3 check_mexc.py
"""

import sys

import mexc

SYMBOL = "BTCUSDT"   # MEXC writes pairs without a slash, e.g. BTCUSDT, ETHUSDT


def main():
    client = mexc.MexcClient()  # reads keys from environment, dry-run ON

    print("\n=== MEXC connection check (no real trades) ===\n")

    # 1. Public price.
    try:
        price = client.get_price(SYMBOL)
        print(f"  [1/3] PUBLIC  ok  -- {SYMBOL} price ${price:,.2f}")
    except Exception as exc:  # noqa: BLE001
        print(f"  [1/3] PUBLIC  FAILED -- {exc}")
        print("        Can't even reach MEXC's public API. Check your internet.")
        return 1

    # 2. Signed account read.
    try:
        usdt = client.get_free_balance("USDT")
        print(f"  [2/3] PRIVATE ok  -- your free USDT balance: ${usdt:,.2f}")
    except Exception as exc:  # noqa: BLE001
        print(f"  [2/3] PRIVATE FAILED -- {exc}")
        print("        Your API keys are missing, wrong, or lack permission.")
        print("        See MEXC_SETUP.md. (Trade-only keys; no withdrawals.)")
        return 1

    # 3. Validate (not place) a tiny order.
    try:
        result = client.market_buy(SYMBOL, usd_amount=1.0)  # dry-run -> validate
        assert result.get("validated"), result
        print("  [3/3] ORDER   ok  -- a $1 test order VALIDATED (nothing placed)")
    except Exception as exc:  # noqa: BLE001
        print(f"  [3/3] ORDER   FAILED -- {exc}")
        print("        Order parameters were rejected. Often this is a balance,")
        print("        minimum-order-size, or symbol issue. Nothing was traded.")
        return 1

    print("\n  All checks passed. The connection works and nothing was traded.")
    print("  dry_run is still ON, so the bot will NOT place real orders until")
    print("  you deliberately turn it off. Next: read the 'Going live' section")
    print("  of MEXC_SETUP.md.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
