"""
portfolio.py
============
Keeps track of the FAKE money and holdings for paper trading, and remembers
them between runs in a small JSON file. Also logs every trade to a CSV.

To keep risk simple, the paper account holds AT MOST ONE coin at a time (the
same rule the live bot follows). State we track:
  cash         -- dollars not currently invested
  symbol       -- which coin we currently hold, or None if all in cash
  coins        -- how much of that coin we hold
  entry_price  -- the price per coin we paid when we bought
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
    return {"cash": config.STARTING_CASH, "symbol": None,
            "coins": 0.0, "entry_price": 0.0}


def save(state):
    with open(config.STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def _log_trade(action, symbol, price, coins, value, state):
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
            action, symbol, f"{price:.2f}", f"{coins:.8f}",
            f"{value:.2f}", f"{state['cash']:.2f}", f"{state['coins']:.8f}",
            f"{total_value(state, price):.2f}",
        ])


def total_value(state, price_now):
    """Everything we have, in dollars: cash plus the value of our held coin."""
    return state["cash"] + state["coins"] * price_now


def buy(state, symbol, price):
    """Spend a fraction of cash on `symbol`, but never risk below the floor.
    Returns a message, or None if nothing happened."""
    equity = state["cash"]                                # flat when buying
    risk_budget = max(0.0, equity - config.FLOOR_USD)     # protect the floor
    spend = min(state["cash"] * config.TRADE_FRACTION, risk_budget)
    if spend < 1:  # not enough cash to bother, or floor reached
        return None
    fee = spend * config.FEE_PCT
    coins_bought = (spend - fee) / price
    state["cash"] -= spend
    state["symbol"] = symbol
    state["coins"] = coins_bought
    state["entry_price"] = price
    _log_trade("BUY", symbol, price, coins_bought, spend, state)
    return (f"BUY  {coins_bought:.8f} {symbol} at ${price:,.2f} "
            f"(spent ${spend:,.2f}, fee ${fee:,.2f})")


def sell(state, price):
    """Sell the whole held position. Returns a message, or None if flat."""
    if state["coins"] <= 0:
        return None
    symbol = state["symbol"]
    coins = state["coins"]
    proceeds = coins * price
    fee = proceeds * config.FEE_PCT
    state["cash"] += proceeds - fee
    state["coins"] = 0.0
    entry = state["entry_price"]
    state["entry_price"] = 0.0
    state["symbol"] = None
    _log_trade("SELL", symbol, price, coins, proceeds, state)
    pnl = ""
    if entry:
        pnl = f", P/L {((price / entry) - 1) * 100:+.1f}% on this trade"
    return (f"SELL {coins:.8f} {symbol} at ${price:,.2f} "
            f"(got ${proceeds - fee:,.2f}{pnl})")
