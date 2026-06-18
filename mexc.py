"""
mexc.py  --  a careful, safety-first client for the MEXC crypto exchange.
========================================================================

This is the bridge between the bot and your REAL MEXC account. Because real
money is involved, it is built to be SAFE BY DEFAULT:

  * It reads your API keys from ENVIRONMENT VARIABLES, never from code. Your
    keys stay on your machine; they are never written into any file here.
  * It starts in DRY-RUN mode. In dry-run, "place an order" does NOT trade --
    it asks MEXC's official /order/test endpoint to VALIDATE the order and
    places nothing. You must deliberately turn dry-run off to trade for real.
  * It enforces a hard MAX_ORDER_USD cap, so even a bug can't place a huge
    order.

Read MEXC_SETUP.md before using this. Use API keys with SPOT TRADING permission
ONLY -- never enable withdrawals on a key a bot uses.
"""

import hashlib
import hmac
import json
import math
import os
import time
import urllib.parse
import urllib.request

BASE_URL = "https://api.mexc.com"

# ---- Hard safety limits (change deliberately, with your eyes open) ----------
# Dry-run is ON unless you set  export DRY_RUN="false"  in keys.env.
DRY_RUN_DEFAULT = os.environ.get("DRY_RUN", "true").strip().lower() not in (
    "false", "0", "no", "off")
MAX_ORDER_USD = float(os.environ.get("MAX_ORDER_USD", "10"))  # refuse bigger


class MexcError(Exception):
    pass


class MexcClient:
    def __init__(self, api_key=None, api_secret=None, dry_run=None,
                 max_order_usd=MAX_ORDER_USD):
        # Keys come from the environment by default. Never hard-code them.
        self.api_key = api_key or os.environ.get("MEXC_API_KEY", "")
        self.api_secret = api_secret or os.environ.get("MEXC_API_SECRET", "")
        self.dry_run = DRY_RUN_DEFAULT if dry_run is None else dry_run
        self.max_order_usd = max_order_usd
        self._precisions = {}   # cache: symbol -> how many decimals it allows

    # -- low-level request helpers -------------------------------------------

    def _request(self, method, path, params=None, signed=False):
        params = dict(params or {})
        if signed:
            if not self.api_key or not self.api_secret:
                raise MexcError(
                    "Missing API keys. Set MEXC_API_KEY and MEXC_API_SECRET "
                    "environment variables (see MEXC_SETUP.md).")
            params["timestamp"] = int(time.time() * 1000)
            params["recvWindow"] = 5000
            query = urllib.parse.urlencode(params)
            signature = hmac.new(self.api_secret.encode(), query.encode(),
                                 hashlib.sha256).hexdigest()
            query = f"{query}&signature={signature}"
        else:
            query = urllib.parse.urlencode(params)

        url = f"{BASE_URL}{path}"
        if query:
            url = f"{url}?{query}"
        req = urllib.request.Request(url, method=method)
        # IMPORTANT: only attach the API key on SIGNED calls. MEXC rejects public
        # endpoints (klines, ticker) with "signature not sent" if the key header
        # is present without a signature -- which silently blinded the bot to all
        # price data.
        if signed and self.api_key:
            req.add_header("X-MEXC-APIKEY", self.api_key)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = resp.read().decode()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")
            raise MexcError(f"MEXC {method} {path} failed "
                            f"({exc.code}): {detail}") from exc
        return json.loads(body) if body else {}

    # -- public (no keys needed) ---------------------------------------------

    def get_price(self, symbol):
        """Latest price for e.g. 'BTCUSDT'. Public, proves connectivity."""
        data = self._request("GET", "/api/v3/ticker/price",
                             {"symbol": symbol})
        return float(data["price"])

    # How MEXC spot spells the timeframes we support.
    _INTERVALS = {"1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
                  "1h": "60m", "4h": "4h", "1d": "1d", "1w": "1W"}

    def get_closes(self, symbol, interval, limit):
        """Closing prices (oldest first) straight from MEXC. Public.
        Used so the strategy decides on MEXC's own prices."""
        rows = self._request("GET", "/api/v3/klines",
                            {"symbol": symbol,
                             "interval": self._INTERVALS[interval],
                             "limit": limit})
        return [float(r[4]) for r in rows]   # index 4 = close

    # -- private (keys needed) -----------------------------------------------

    def list_usdt_symbols(self, top=None):
        """Every USDT spot coin on MEXC, MOST-ACTIVE first (by 24h quote volume).
        Returns base symbols like ['BTC', 'ETH', ...]."""
        data = self._request("GET", "/api/v3/ticker/24hr")    # all symbols
        rows = data if isinstance(data, list) else []
        usdt = [r for r in rows if str(r.get("symbol", "")).endswith("USDT")]
        usdt.sort(key=lambda r: float(r.get("quoteVolume", 0) or 0), reverse=True)
        syms = [r["symbol"][:-4] for r in usdt]               # strip "USDT"
        return syms[:top] if top else syms

    def buy_power(self, symbol, interval, limit):
        """Buying vs selling pressure over recent candles: volume on up-candles
        divided by total volume (0-1). >0.5 = buyers in control. Public."""
        rows = self._request("GET", "/api/v3/klines",
                            {"symbol": symbol,
                             "interval": self._INTERVALS[interval],
                             "limit": limit})
        up = tot = 0.0
        for r in rows:
            o, c, v = float(r[1]), float(r[4]), float(r[5])  # open, close, volume
            tot += v
            if c >= o:
                up += v
        return up / tot if tot > 0 else 0.5

    def volume_ratio(self, symbol, interval, limit):
        """Recent volume vs its average: mean of the last 3 candles / mean over
        the window. >1 = activity picking up. Public."""
        rows = self._request("GET", "/api/v3/klines",
                            {"symbol": symbol,
                             "interval": self._INTERVALS[interval],
                             "limit": limit})
        vols = [float(r[5]) for r in rows]
        if len(vols) < 5:
            return 1.0
        avg = sum(vols) / len(vols)
        recent = sum(vols[-3:]) / 3
        return recent / avg if avg > 0 else 1.0

    def get_account(self):
        """Your balances. A signed READ -- proves your keys work. Trades nothing."""
        return self._request("GET", "/api/v3/account", signed=True)

    def get_free_balance(self, asset):
        """How much of one asset (e.g. 'USDT') is available to trade."""
        for bal in self.get_account().get("balances", []):
            if bal["asset"] == asset:
                return float(bal["free"])
        return 0.0

    # -- orders (the part that can cost money) -------------------------------

    def _place(self, params, usd_estimate):
        """Internal: enforce the cap, then either VALIDATE (dry-run) or send."""
        if usd_estimate > self.max_order_usd:
            raise MexcError(
                f"Refusing order ~${usd_estimate:.2f}: exceeds MAX_ORDER_USD "
                f"${self.max_order_usd:.2f}. Raise the cap deliberately if you "
                f"really mean it.")
        if self.dry_run:
            # /order/test validates the order against MEXC and places NOTHING.
            self._request("POST", "/api/v3/order/test", params, signed=True)
            return {"dry_run": True, "validated": True, "would_send": params}
        # Live: this actually places a real order with real money.
        return self._request("POST", "/api/v3/order", params, signed=True)

    def market_buy(self, symbol, usd_amount):
        """Buy `usd_amount` worth of `symbol` at market price."""
        params = {"symbol": symbol, "side": "BUY", "type": "MARKET",
                  "quoteOrderQty": round(usd_amount, 2)}
        return self._place(params, usd_amount)

    def _base_precision(self, symbol):
        """How many decimal places this symbol allows for the base quantity. We
        must round a SELL down to this, or MEXC rejects it as 'Oversold' (it reads
        the extra decimals as selling more than you hold). Cached; None if unknown."""
        if symbol in self._precisions:
            return self._precisions[symbol]
        prec = None
        try:
            data = self._request("GET", "/api/v3/exchangeInfo", {"symbol": symbol})
            syms = data.get("symbols") or []
            if syms:
                s = syms[0]
                if s.get("baseAssetPrecision") is not None:
                    prec = int(s["baseAssetPrecision"])
                for f in s.get("filters", []):     # LOT_SIZE is more restrictive
                    if f.get("filterType") == "LOT_SIZE" and f.get("stepSize"):
                        step = f["stepSize"].rstrip("0").rstrip(".")
                        sp = len(step.split(".")[1]) if "." in step else 0
                        prec = sp if prec is None else min(prec, sp)
        except Exception:  # noqa: BLE001
            prec = None
        self._precisions[symbol] = prec
        return prec

    def market_sell(self, symbol, quantity, price_hint=0.0):
        """Sell `quantity` of the base asset (e.g. BTC) at market price. Rounds the
        quantity DOWN to the symbol's allowed precision so it never exceeds the
        balance (which MEXC rejects as 'Oversold')."""
        prec = self._base_precision(symbol)
        if prec is None:                  # unknown -> be conservative
            prec, quantity = 6, quantity * 0.999
        factor = 10 ** prec
        qty = math.floor(quantity * factor) / factor
        if qty <= 0:
            raise MexcError(f"{symbol}: holding too small to sell ({quantity}).")
        qstr = f"{qty:.{prec}f}"
        if "." in qstr:
            qstr = qstr.rstrip("0").rstrip(".")
        params = {"symbol": symbol, "side": "SELL", "type": "MARKET",
                  "quantity": qstr}
        return self._place(params, qty * price_hint)
