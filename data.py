"""
data.py
=======
Gets recent closing prices for a crypto coin, at a chosen timeframe
("1h", "4h", or "1d").

It tries several FREE, public price sources in order until one works (none
need an account or API key). Different networks/regions block different
exchanges, so trying several makes the bot more reliable.

It also has a "demo" generator that invents realistic-looking fake prices,
so you can run and watch the bot even with no internet (handy for testing).

Everything returns a simple list of float prices, OLDEST first, NEWEST last.
"""

import json
import math
import random
import urllib.request

# How each source spells the timeframes we support.
_BINANCE = {"1h": "1h", "4h": "4h", "1d": "1d"}
_COINBASE = {"1h": 3600, "4h": 14400, "1d": 86400}     # granularity in seconds
_KRAKEN = {"1h": 60, "4h": 240, "1d": 1440}            # interval in minutes


def _http_get_json(url):
    """Download a URL and parse it as JSON. Pretends to be a browser so more
    servers accept the request."""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.load(resp)


# --- Each function talks to one exchange and returns a list of closes ---------
# If a source is down or blocked it raises an error, and we move to the next.

def _from_binance(symbol, interval, limit):
    url = (f"https://api.binance.com/api/v3/klines?symbol={symbol}USDT"
           f"&interval={_BINANCE[interval]}&limit={limit}")
    rows = _http_get_json(url)              # oldest -> newest already
    return [float(r[4]) for r in rows]      # index 4 = closing price


def _from_coinbase(symbol, interval, limit):
    url = (f"https://api.exchange.coinbase.com/products/{symbol}-USD/candles"
           f"?granularity={_COINBASE[interval]}")
    rows = list(reversed(_http_get_json(url)))   # newest-first -> oldest-first
    return [float(r[4]) for r in rows][-limit:]  # index 4 = close


def _from_kraken(symbol, interval, limit):
    pair = ("XBT" if symbol == "BTC" else symbol) + "USD"
    url = (f"https://api.kraken.com/0/public/OHLC?pair={pair}"
           f"&interval={_KRAKEN[interval]}")
    result = _http_get_json(url)["result"]
    key = next(k for k in result if k != "last")
    rows = result[key]                      # oldest -> newest
    return [float(r[4]) for r in rows][-limit:]   # index 4 = close


def _from_cryptocompare(symbol, interval, limit):
    # CryptoCompare has per-hour and per-day endpoints; "4h" = hourly aggregated.
    endpoint = "histoday" if interval == "1d" else "histohour"
    aggregate = 4 if interval == "4h" else 1
    url = (f"https://min-api.cryptocompare.com/data/v2/{endpoint}"
           f"?fsym={symbol}&tsym=USD&limit={limit}&aggregate={aggregate}")
    rows = _http_get_json(url)["Data"]["Data"]    # oldest -> newest
    return [float(r["close"]) for r in rows]


def get_closes(symbol, interval, limit):
    """Try every source until one returns prices. Raises if all fail."""
    sources = [
        ("Binance", _from_binance),
        ("Coinbase", _from_coinbase),
        ("Kraken", _from_kraken),
        ("CryptoCompare", _from_cryptocompare),
    ]
    errors = []
    for name, fetch in sources:
        try:
            closes = fetch(symbol, interval, limit)
            if closes and len(closes) >= 2:
                print(f"  [data] {interval} prices from {name} "
                      f"({len(closes)} candles)")
                return closes
        except Exception as exc:  # noqa: BLE001 - try the next source
            errors.append(f"{name}: {exc}")
    raise ConnectionError(
        "Could not fetch prices from any source.\n  " + "\n  ".join(errors)
        + "\n  Tip: run with --demo to use offline practice data."
    )


# Backwards-compatible helper (daily).
def get_daily_closes(symbol, days):
    return get_closes(symbol, "1d", days)


def demo_closes(count, seed=None):
    """Invent a believable price history so the bot can run with no internet.

    A 'random walk' with a gentle upward drift and occasional swings -- enough
    to make the strategy act. NOT real data; for practice only.
    """
    rng = random.Random(seed)
    price = 30_000.0
    closes = []
    for i in range(count):
        drift = 0.0008
        noise = rng.gauss(0, 0.02)
        wave = 0.01 * math.sin(i / 9.0)
        price *= (1 + drift + noise + wave)
        closes.append(round(price, 2))
    return closes
