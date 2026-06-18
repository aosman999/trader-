"""
broker.py  --  one common interface for "where do trades actually happen?"
=========================================================================

The bot's decision logic (strategy.py) shouldn't care whether it's playing with
fake money or talking to a real exchange. So both live behind the same small
interface, and config.BROKER picks which one bot.py uses:

  "paper"        -> PaperBroker        : fake money (the safe default)
  "mexc"         -> MexcBroker          : real MEXC SPOT account
  "mexc_futures" -> MexcFuturesBroker   : real MEXC FUTURES (leveraged)

Every broker speaks the same methods, all built around holding AT MOST ONE coin
at a time (which keeps the $12 floor and position sizing simple and safe):

  get_prices(symbol)              -> recent closes for one coin
  cash()                          -> spare USD/USDT available
  current_position()             -> {symbol, amount, entry} or None
  position_value(symbol, amt, p) -> dollar value of a holding
  open(symbol, price)            -> enter a long in `symbol`
  close(symbol, amount, price)   -> exit the held position

The MEXC brokers obey their clients' safety rules (keys from the environment,
dry-run by default, size caps), so picking a real broker does NOT by itself
spend real money.
"""

import json
import os

import config
import data
import portfolio


def make_broker(use_demo=False):
    if config.BROKER == "paper":
        return PaperBroker(use_demo=use_demo)
    if config.BROKER == "mexc":
        return MexcBroker()
    if config.BROKER == "mexc_futures":
        return MexcFuturesBroker()
    raise ValueError(f"Unknown BROKER {config.BROKER!r}. "
                     f"Use 'paper', 'mexc', or 'mexc_futures'.")


# Holdings worth less than this (USD) count as "nothing" (dust after a sell).
DUST_USD = 1.0


def _demo_seed(symbol):
    """A stable per-coin seed so each watchlist coin gets its own demo series."""
    return sum(ord(c) for c in symbol)


class PaperBroker:
    """Fake money. Prices from data.py, holdings tracked in portfolio.json."""

    label = "PAPER (fake money)"
    is_live = False

    def __init__(self, use_demo=False):
        self.use_demo = use_demo
        self.state = portfolio.load()

    def universe(self):
        # Paper has no live coin list; use the watchlist or a default of majors.
        return config.WATCHLIST or ["BTC", "ETH", "SOL", "XRP", "DOGE"]

    def get_prices(self, symbol, interval=None):
        if self.use_demo:
            return data.demo_closes(config.HISTORY_DAYS, seed=_demo_seed(symbol))
        return data.get_closes(symbol, interval or config.INTERVAL,
                               config.HISTORY_DAYS)

    def buy_power(self, symbol):
        return 0.5   # paper/demo has no volume data -> neutral (passes filter)

    def volume_ratio(self, symbol):
        return 1.0   # neutral for paper/demo

    def cash(self):
        return self.state["cash"]

    def current_position(self):
        if self.state["coins"] > 0 and self.state.get("symbol"):
            return {"symbol": self.state["symbol"],
                    "amount": self.state["coins"],
                    "entry": self.state["entry_price"],
                    "high_water": self.state.get("high_water")
                    or self.state["entry_price"]}
        return None

    def update_high_water(self, symbol, entry, price):
        hw = max(self.state.get("high_water") or entry, price)
        self.state["high_water"] = hw
        portfolio.save(self.state)
        return hw

    def position_value(self, symbol, amount, price):
        return amount * price

    def open(self, symbol, price):
        msg = portfolio.buy(self.state, symbol, price)
        portfolio.save(self.state)
        return msg

    def close(self, symbol, amount, price):
        msg = portfolio.sell(self.state, price)
        portfolio.save(self.state)
        return msg


class MexcBroker:
    """Real MEXC SPOT account. You own the coin; no leverage. Safe by default."""

    label = "MEXC SPOT (REAL account)"
    is_live = True
    STATE_FILE = "mexc_spot_state.json"   # remembers which coin we hold + entry

    def __init__(self):
        import mexc
        self.client = mexc.MexcClient()

    def universe(self):
        if config.WATCHLIST:
            return config.WATCHLIST
        return self.client.list_usdt_symbols(top=config.MAX_SCAN)

    def get_prices(self, symbol, interval=None):
        return self.client.get_closes(symbol + "USDT",
                                      interval or config.INTERVAL,
                                      config.HISTORY_DAYS)

    def cash(self):
        return self.client.get_free_balance("USDT")

    def buy_power(self, symbol):
        return self.client.buy_power(symbol + "USDT", config.INTERVAL, 50)

    def volume_ratio(self, symbol):
        return self.client.volume_ratio(symbol + "USDT", config.INTERVAL, 50)

    def _load(self):
        if os.path.exists(self.STATE_FILE):
            with open(self.STATE_FILE) as f:
                return json.load(f)
        return {}

    def current_position(self):
        st = self._load()
        symbol = st.get("symbol")
        if not symbol:
            return None
        amount = self.client.get_free_balance(symbol)
        if amount <= 0:
            os.remove(self.STATE_FILE)
            return None
        return {"symbol": symbol, "amount": amount,
                "entry": st.get("entry", 0.0),
                "high_water": st.get("high_water") or st.get("entry", 0.0)}

    def update_high_water(self, symbol, entry, price):
        st = self._load()
        hw = max(st.get("high_water") or entry, price)
        st["high_water"] = hw
        with open(self.STATE_FILE, "w") as f:
            json.dump(st, f)
        return hw

    def position_value(self, symbol, amount, price):
        return amount * price

    def open(self, symbol, price):
        equity = self.cash()
        if config.RESERVE_FLOOR:
            usd = min(equity * config.TRADE_FRACTION,
                      max(0.0, equity - config.FLOOR_USD))
        else:
            usd = equity * config.TRADE_FRACTION         # deploy all cash
        if usd < 1:
            return None
        result = self.client.market_buy(symbol + "USDT", usd)
        if result.get("dry_run"):
            return f"DRY-RUN: would BUY ~${usd:,.2f} of {symbol} (nothing placed)"
        with open(self.STATE_FILE, "w") as f:
            json.dump({"symbol": symbol, "entry": price, "high_water": price}, f)
        return f"BUY ~${usd:,.2f} of {symbol} at ~${price:,.2f} [REAL ORDER]"

    def close(self, symbol, amount, price):
        result = self.client.market_sell(symbol + "USDT", amount,
                                         price_hint=price)
        if result.get("dry_run"):
            return f"DRY-RUN: would SELL {amount:.8f} {symbol} (nothing placed)"
        if os.path.exists(self.STATE_FILE):
            os.remove(self.STATE_FILE)
        return f"SELL {amount:.8f} {symbol} at ~${price:,.2f} [REAL ORDER]"


class MexcFuturesBroker:
    """Real MEXC FUTURES. LEVERAGED -> can be liquidated. Long-only, isolated
    margin, leverage hard-capped at 10x, dry-run by default."""

    label = "MEXC FUTURES (REAL, leveraged)"
    is_live = True
    HWM_FILE = "mexc_hwm.json"   # tracks the peak price since entry (for trailing)

    def __init__(self):
        import mexc_futures
        self.client = mexc_futures.MexcFuturesClient(leverage=config.LEVERAGE)
        self._sizes = {}   # cache of contract sizes per pair

    @staticmethod
    def _pair(symbol):
        return symbol + "_USDT"

    def universe(self):
        if config.WATCHLIST:
            return config.WATCHLIST
        return self.client.list_usdt_symbols(top=config.MAX_SCAN)

    def get_prices(self, symbol, interval=None):
        return self.client.get_closes(self._pair(symbol),
                                      interval or config.INTERVAL,
                                      config.HISTORY_DAYS)

    def _stored_hwm(self, symbol):
        if os.path.exists(self.HWM_FILE):
            with open(self.HWM_FILE) as f:
                d = json.load(f)
            if d.get("symbol") == symbol:
                return d.get("high_water", 0.0)
        return 0.0

    def update_high_water(self, symbol, entry, price):
        hw = max(self._stored_hwm(symbol) or entry, price)
        with open(self.HWM_FILE, "w") as f:
            json.dump({"symbol": symbol, "high_water": hw}, f)
        return hw

    def _contract_size(self, pair):
        if pair not in self._sizes:
            self._sizes[pair] = self.client.contract_size(pair)
        return self._sizes[pair]

    def cash(self):
        return self.client.usdt_balance()

    def buy_power(self, symbol):
        return self.client.buy_power(self._pair(symbol), config.INTERVAL, 50)

    def volume_ratio(self, symbol):
        return self.client.volume_ratio(self._pair(symbol), config.INTERVAL, 50)

    def current_position(self):
        pair, vol, entry = self.client.any_long_position()
        if not pair:
            return None
        symbol = pair.split("_")[0]
        return {"symbol": symbol, "amount": vol, "entry": entry,
                "high_water": self._stored_hwm(symbol) or entry}

    def position_value(self, symbol, amount, price):
        return amount * self._contract_size(self._pair(symbol)) * price

    def open(self, symbol, price):
        pair = self._pair(symbol)
        equity = self.cash()
        if config.RESERVE_FLOOR:
            margin = min(equity * config.TRADE_FRACTION,
                         max(0.0, equity - config.FLOOR_USD))
        else:
            margin = equity * config.TRADE_FRACTION       # deploy all cash
        if margin < 1:
            return None
        notional = margin * self.client.leverage
        vol = max(1, round(notional / (price * self._contract_size(pair))))
        result = self.client.open_long(pair, vol, margin)
        lev = self.client.leverage
        if result.get("dry_run"):
            return (f"DRY-RUN: would OPEN LONG {vol} {symbol} contracts "
                    f"(~${margin:,.2f} margin @ {lev}x) [nothing placed]")
        return (f"OPEN LONG {vol} {symbol} contracts at ~${price:,.2f} "
                f"(~${margin:,.2f} margin @ {lev}x) [REAL ORDER]")

    def close(self, symbol, amount, price):
        pair = self._pair(symbol)
        result = self.client.close_long(pair, amount)
        if result.get("dry_run"):
            return (f"DRY-RUN: would CLOSE {amount} {symbol} contracts "
                    f"[nothing placed]")
        if os.path.exists(self.HWM_FILE):
            os.remove(self.HWM_FILE)
        return f"CLOSE {amount} {symbol} contracts at ~${price:,.2f} [REAL ORDER]"
