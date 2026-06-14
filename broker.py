"""
broker.py  --  one common interface for "where do trades actually happen?"
=========================================================================

The bot's decision logic (strategy.py) shouldn't care whether it's playing with
fake money or talking to a real exchange. So both live behind the same small
interface, and config.BROKER picks which one bot.py uses:

  "paper"  -> PaperBroker : fake money in portfolio.json (the safe default)
  "mexc"   -> MexcBroker  : your real MEXC account (via mexc.py)

The MEXC broker still obeys mexc.py's safety rules: keys from the environment,
DRY-RUN by default (validates orders, places nothing), and a hard size cap.
So selecting "mexc" does NOT by itself spend real money -- dry-run must be
turned off deliberately first.
"""

import json
import os

import config
import data
import portfolio


def make_broker(use_demo=False):
    """Return the broker chosen in config.BROKER."""
    if config.BROKER == "paper":
        return PaperBroker(use_demo=use_demo)
    if config.BROKER == "mexc":
        return MexcBroker()
    if config.BROKER == "mexc_futures":
        return MexcFuturesBroker()
    raise ValueError(f"Unknown BROKER {config.BROKER!r}. "
                     f"Use 'paper', 'mexc', or 'mexc_futures'.")


# Treat holdings worth less than this as "nothing" (dust left after a sell).
DUST_USD = 1.0


class PaperBroker:
    """Fake money. Prices from data.py, holdings tracked in portfolio.json."""

    label = "PAPER (fake money)"
    is_live = False

    def __init__(self, use_demo=False):
        self.use_demo = use_demo
        self.state = portfolio.load()

    def history(self):
        if self.use_demo:
            return data.demo_closes(config.HISTORY_DAYS, seed=42)
        return data.get_closes(config.SYMBOL, config.INTERVAL, config.HISTORY_DAYS)

    def cash(self):
        return self.state["cash"]

    def coin_value(self, price):
        return self.state["coins"] * price

    def holding(self, price):
        return self.coin_value(price) > DUST_USD

    def entry_price(self):
        return self.state["entry_price"]

    def buy(self, price):
        msg = portfolio.buy(self.state, price)
        portfolio.save(self.state)
        return msg

    def sell(self, price):
        msg = portfolio.sell(self.state, price)
        portfolio.save(self.state)
        return msg

    def total_value(self, price):
        return portfolio.total_value(self.state, price)


class MexcBroker:
    """Your real MEXC account. Safe by default: dry-run until you disable it."""

    label = "MEXC (REAL account)"
    is_live = True
    ENTRY_FILE = "mexc_entry.json"   # we remember our buy price; MEXC doesn't

    def __init__(self):
        import mexc  # imported lazily so paper users never need it
        self.client = mexc.MexcClient()
        self.pair = config.SYMBOL + "USDT"   # e.g. BTCUSDT
        self.base = config.SYMBOL            # e.g. BTC

    def history(self):
        return self.client.get_closes(self.pair, config.INTERVAL,
                                      config.HISTORY_DAYS)

    def cash(self):
        return self.client.get_free_balance("USDT")

    def _coins(self):
        return self.client.get_free_balance(self.base)

    def coin_value(self, price):
        return self._coins() * price

    def holding(self, price):
        return self.coin_value(price) > DUST_USD

    def entry_price(self):
        if os.path.exists(self.ENTRY_FILE):
            with open(self.ENTRY_FILE) as f:
                return json.load(f).get("entry_price", 0.0)
        return 0.0

    def _save_entry(self, price):
        with open(self.ENTRY_FILE, "w") as f:
            json.dump({"entry_price": price}, f)

    def buy(self, price):
        equity = self.total_value(price)
        risk_budget = max(0.0, equity - config.FLOOR_USD)   # protect the floor
        usd = min(self.cash() * config.TRADE_FRACTION, risk_budget)
        if usd < 1:
            return None
        result = self.client.market_buy(self.pair, usd)
        if result.get("dry_run"):
            return f"DRY-RUN: would BUY ~${usd:,.2f} of {self.base} (nothing placed)"
        self._save_entry(price)
        return f"BUY ~${usd:,.2f} of {self.base} at ~${price:,.2f} [REAL ORDER]"

    def sell(self, price):
        coins = self._coins()
        if coins * price < DUST_USD:
            return None
        result = self.client.market_sell(self.pair, coins, price_hint=price)
        if result.get("dry_run"):
            return f"DRY-RUN: would SELL {coins:.8f} {self.base} (nothing placed)"
        if os.path.exists(self.ENTRY_FILE):
            os.remove(self.ENTRY_FILE)
        return f"SELL {coins:.8f} {self.base} at ~${price:,.2f} [REAL ORDER]"

    def total_value(self, price):
        return self.cash() + self.coin_value(price)


class MexcFuturesBroker:
    """Your real MEXC FUTURES account. LEVERAGED -> can be liquidated.
    Long-only, isolated margin, leverage hard-capped at 10x, dry-run by default."""

    label = "MEXC FUTURES (REAL, leveraged)"
    is_live = True

    def __init__(self):
        import mexc_futures  # imported lazily
        self.client = mexc_futures.MexcFuturesClient(leverage=config.LEVERAGE)
        self.pair = config.SYMBOL + "_USDT"   # futures uses an underscore
        self._size = None

    def history(self):
        return self.client.get_closes(self.pair, config.INTERVAL,
                                      config.HISTORY_DAYS)

    def _contract_size(self):
        if self._size is None:
            self._size = self.client.contract_size(self.pair)
        return self._size

    def cash(self):
        return self.client.usdt_balance()

    def _position(self):
        return self.client.long_position(self.pair)   # (contracts, avg_price)

    def coin_value(self, price):
        vol, _ = self._position()
        return vol * self._contract_size() * price     # position notional value

    def holding(self, price):
        vol, _ = self._position()
        return vol > 0

    def entry_price(self):
        _, avg = self._position()                      # MEXC tracks our entry
        return avg

    def buy(self, price):
        equity = self.cash()
        risk_budget = max(0.0, equity - config.FLOOR_USD)   # protect the floor
        # Isolated margin: the most a trade can lose is its margin. Keeping margin
        # at or below (equity - FLOOR) means even a full liquidation leaves ~FLOOR.
        margin = min(equity * config.TRADE_FRACTION, risk_budget)
        if margin < 1:
            return None
        notional = margin * self.client.leverage
        vol = max(1, round(notional / (price * self._contract_size())))
        result = self.client.open_long(self.pair, vol, margin)
        lev = self.client.leverage
        if result.get("dry_run"):
            return (f"DRY-RUN: would OPEN LONG {vol} contracts "
                    f"(~${margin:,.2f} margin @ {lev}x) [nothing placed]")
        return (f"OPEN LONG {vol} contracts at ~${price:,.2f} "
                f"(~${margin:,.2f} margin @ {lev}x) [REAL ORDER]")

    def sell(self, price):
        vol, _ = self._position()
        if vol <= 0:
            return None
        result = self.client.close_long(self.pair, vol)
        if result.get("dry_run"):
            return f"DRY-RUN: would CLOSE LONG {vol} contracts [nothing placed]"
        return f"CLOSE LONG {vol} contracts at ~${price:,.2f} [REAL ORDER]"

    def total_value(self, price):
        # Wallet USDT (margin balance). Unrealized P/L on the open position is
        # shown on MEXC itself; we keep the summary simple and conservative.
        return self.cash()
