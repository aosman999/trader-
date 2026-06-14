"""
mexc_futures.py  --  safety-first client for MEXC FUTURES (perpetual contracts).
===============================================================================

Futures are LEVERAGED. That means liquidation: a relatively small move against
you can wipe out your whole margin automatically. This client is built to keep
that danger boxed in:

  * Keys come from environment variables (MEXC_API_KEY / MEXC_API_SECRET).
  * LEVERAGE IS HARD-CAPPED AT 10x in code (MAX_LEVERAGE). No setting can exceed
    it. At 10x, roughly a 10% move against you liquidates the position.
  * ISOLATED margin only -- a loss can never reach beyond the margin you put on
    a single trade (it can't pull in the rest of your balance).
  * LONG-ONLY -- it never sells short. (Shorting adds a whole second way to lose.)
  * DRY-RUN by default -- it builds and logs the order but sends NOTHING until
    you deliberately turn dry-run off.
  * A hard MAX_MARGIN_USD cap on how much margin any one trade can use.

NOTE: MEXC's futures API is separate from spot (different server + signing), and
MEXC has at times restricted futures order placement via API. check_mexc_futures.py
verifies whether your account can actually use it -- without placing any trade.
"""

import hashlib
import hmac
import json
import os
import time
import urllib.parse
import urllib.request

BASE_URL = "https://contract.mexc.com"

# ---- Hard safety limits (the whole point of this file) ----------------------
MAX_LEVERAGE = 10        # absolute ceiling; nothing may exceed this
DRY_RUN_DEFAULT = True   # True = build/log orders but send nothing
MAX_MARGIN_USD = 10.0    # most margin any single trade may use
ISOLATED = 1             # openType 1 = isolated margin (2 = cross; we never use)

# MEXC futures order "side" codes:
OPEN_LONG = 1
CLOSE_LONG = 4
MARKET = 5               # order type: market


class MexcFuturesError(Exception):
    pass


class MexcFuturesClient:
    def __init__(self, api_key=None, api_secret=None, dry_run=None,
                 leverage=3, max_margin_usd=MAX_MARGIN_USD):
        self.api_key = api_key or os.environ.get("MEXC_API_KEY", "")
        self.api_secret = api_secret or os.environ.get("MEXC_API_SECRET", "")
        self.dry_run = DRY_RUN_DEFAULT if dry_run is None else dry_run
        # Clamp leverage into 1..MAX_LEVERAGE no matter what was passed in.
        self.leverage = max(1, min(int(leverage), MAX_LEVERAGE))
        self.max_margin_usd = max_margin_usd

    # -- signing & requests ---------------------------------------------------

    def _sign(self, req_time, param_str):
        target = self.api_key + str(req_time) + param_str
        return hmac.new(self.api_secret.encode(), target.encode(),
                        hashlib.sha256).hexdigest()

    def _request(self, method, path, params=None, signed=False):
        params = params or {}
        url = f"{BASE_URL}{path}"
        data = None
        headers = {}

        if method == "GET":
            # For signing, GET params are sorted "k=v&..." with no URL-encoding.
            param_str = "&".join(f"{k}={params[k]}" for k in sorted(params))
            if params:
                url = f"{url}?{urllib.parse.urlencode(params)}"
        else:  # POST: body is compact JSON, and that exact string is signed.
            param_str = json.dumps(params, separators=(",", ":"))
            data = param_str.encode()
            headers["Content-Type"] = "application/json"

        if signed:
            if not self.api_key or not self.api_secret:
                raise MexcFuturesError(
                    "Missing API keys. Set MEXC_API_KEY and MEXC_API_SECRET "
                    "(see FUTURES_SETUP.md).")
            req_time = int(time.time() * 1000)
            headers["ApiKey"] = self.api_key
            headers["Request-Time"] = str(req_time)
            headers["Signature"] = self._sign(req_time, param_str)

        req = urllib.request.Request(url, data=data, method=method,
                                     headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = resp.read().decode()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")
            raise MexcFuturesError(f"MEXC futures {method} {path} failed "
                                   f"({exc.code}): {detail}") from exc
        payload = json.loads(body) if body else {}
        # MEXC wraps responses as {"success": bool, "code": int, "data": ...}
        if isinstance(payload, dict) and payload.get("success") is False:
            raise MexcFuturesError(f"MEXC futures error on {path}: {payload}")
        return payload

    # -- public market data (no keys) ----------------------------------------

    def get_price(self, symbol):
        """Last traded price for e.g. 'BTC_USDT'."""
        data = self._request("GET", "/api/v1/contract/ticker",
                             {"symbol": symbol})
        return float(data["data"]["lastPrice"])

    # How MEXC futures spells the timeframes we support.
    _INTERVALS = {"1h": "Min60", "4h": "Hour4", "1d": "Day1"}

    def get_closes(self, symbol, interval, limit):
        """Closing prices (oldest first) for the strategy to read."""
        data = self._request("GET", f"/api/v1/contract/kline/{symbol}",
                             {"interval": self._INTERVALS[interval]})
        closes = [float(c) for c in data["data"]["close"]]
        return closes[-limit:]

    def contract_size(self, symbol):
        """How much of the coin one contract represents (e.g. 0.0001 BTC)."""
        data = self._request("GET", "/api/v1/contract/detail",
                             {"symbol": symbol})
        return float(data["data"]["contractSize"])

    # -- private reads (keys needed, no trading) -----------------------------

    def usdt_balance(self):
        """Available USDT in your futures wallet."""
        data = self._request("GET", "/api/v1/private/account/assets",
                             signed=True)
        for asset in data.get("data", []):
            if asset.get("currency") == "USDT":
                return float(asset.get("availableBalance", 0))
        return 0.0

    def long_position(self, symbol):
        """Return (contracts_held, average_entry_price) for an open LONG, or
        (0, 0.0) if none."""
        data = self._request("GET", "/api/v1/private/position/open_positions",
                             {"symbol": symbol}, signed=True)
        for pos in data.get("data", []):
            # positionType 1 = long
            if pos.get("positionType") == 1 and float(pos.get("holdVol", 0)) > 0:
                return float(pos["holdVol"]), float(pos.get("holdAvgPrice", 0))
        return 0.0, 0.0

    def any_long_position(self):
        """Find the single open LONG across the WHOLE account (any symbol), so
        the bot always knows what it's holding. Returns (pair, contracts, entry)
        or (None, 0, 0.0)."""
        data = self._request("GET", "/api/v1/private/position/open_positions",
                             signed=True)
        for pos in data.get("data", []):
            if pos.get("positionType") == 1 and float(pos.get("holdVol", 0)) > 0:
                return (pos.get("symbol"), float(pos["holdVol"]),
                        float(pos.get("holdAvgPrice", 0)))
        return None, 0.0, 0.0

    # -- orders (can cost money) ---------------------------------------------

    def _submit(self, params, margin_usd):
        if margin_usd > self.max_margin_usd:
            raise MexcFuturesError(
                f"Refusing trade: margin ~${margin_usd:.2f} exceeds "
                f"MAX_MARGIN_USD ${self.max_margin_usd:.2f}.")
        if self.dry_run:
            return {"dry_run": True, "would_send": params}
        return self._request("POST", "/api/v1/private/order/submit",
                             params, signed=True)

    def open_long(self, symbol, vol, margin_usd):
        """Open a LONG position of `vol` contracts at market, isolated margin."""
        params = {"symbol": symbol, "vol": int(vol), "side": OPEN_LONG,
                  "type": MARKET, "openType": ISOLATED, "leverage": self.leverage}
        return self._submit(params, margin_usd)

    def close_long(self, symbol, vol, margin_usd=0.0):
        """Close an existing LONG position at market."""
        params = {"symbol": symbol, "vol": int(vol), "side": CLOSE_LONG,
                  "type": MARKET, "openType": ISOLATED, "leverage": self.leverage}
        return self._submit(params, margin_usd)
