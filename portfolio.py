"""
portfolio.py
============
Keeps track of the FAKE money and holdings, and remembers them between runs
by saving to a small JSON file. Also writes every trade to a CSV log.

State we track:
  cash         -- dollars not currently invested
  coins        -- how much of the coin we hold (e.g. 0.0123 BTC)
  entry_price  -- the price per coin we paid when we last bought
"""

import csv
import json
import os
from datetime import datetime, timezone

import config


def load():
    """Load saved state, or create a fresh portfolio on the very first run."""
    if os.path.exists(config.STATE_FILE):
        with open(config.STATE_FILE) as f:
            return json.load(f)
    return {"cash": config.STARTING_CASH, "coins": 0.0, "entry_price": 0.0}


def save(state):
    with open(config.STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def _log_trade(action, price, coins, value, state):
    """Append one line to trades.csv so you have a permanent record."""
    new_file = not os.path.exists(config.LOG_FILE)
    with open(config.LOG_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        if new_file:
            writer.writerow(["timestamp_utc", "action", "symbol", "price",
                             "coins", "trade_value", "cash_after",
                             "coins_after", "portfolio_value"])
        writer.writerow([
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
            action, config.SYMBOL, f"{price:.2f}", f"{coins:.8f}",
            f"{value:.2f}", f"{state['cash']:.2f}", f"{state['coins']:.8f}",
            f"{total_value(state, price):.2f}",
        ])


def total_value(state, price_now):
    """Everything we have, in dollars: cash plus the value of our coins."""
    return state["cash"] + state["coins"] * price_now


def buy(state, price):
    """Spend a fraction of cash (per config.TRADE_FRACTION) to buy the coin.
    Returns a human-readable message, or None if nothing happened."""
    spend = state["cash"] * config.TRADE_FRACTION
    if spend < 1:  # not enough cash to bother
        return None
    fee = spend * config.FEE_PCT
    coins_bought = (spend - fee) / price
    state["cash"] -= spend
    state["coins"] += coins_bought
    state["entry_price"] = price
    _log_trade("BUY", price, coins_bought, spend, state)
    return (f"BUY  {coins_bought:.8f} {config.SYMBOL} at ${price:,.2f} "
            f"(spent ${spend:,.2f}, fee ${fee:,.2f})")


def sell(state, price):
    """Sell everything we hold. Returns a message, or None if we hold nothing."""
    if state["coins"] <= 0:
        return None
    coins = state["coins"]
    proceeds = coins * price
    fee = proceeds * config.FEE_PCT
    state["cash"] += proceeds - fee
    state["coins"] = 0.0
    entry = state["entry_price"]
    state["entry_price"] = 0.0
    _log_trade("SELL", price, coins, proceeds, state)
    pnl = ""
    if entry:
        pnl = f", P/L {((price / entry) - 1) * 100:+.1f}% on this trade"
    return (f"SELL {coins:.8f} {config.SYMBOL} at ${price:,.2f} "
            f"(got ${proceeds - fee:,.2f}{pnl})")
