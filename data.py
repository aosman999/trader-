"""
data.py
=======
Gets daily closing prices for a crypto coin.

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


def _http_get_json(url):
    """Download a URL and parse it as JSON. Pretends to be a browser so more
    servers accept the request."""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.load(resp)


# --- Each function below talks to one exchange and returns a list of closes ---
# If a source is down or blocked it raises an error, and we move to the next.

def _from_binance(symbol, days):
    url = (f"https://api.binance.com/api/v3/klines"
           f"?symbol={symbol}USDT&interval=1d&limit={days}")
    rows = _http_get_json(url)              # oldest -> newest already
    return [float(r[4]) for r in rows]      # index 4 = closing price


def _from_coinbase(symbol, days):
    # Coinbase returns newest-first, so we reverse it.
    url = (f"https://api.exchange.coinbase.com/products/{symbol}-USD/candles"
           f"?granularity=86400")
    rows = _http_get_json(url)
    rows = list(reversed(rows))             # now oldest -> newest
    closes = [float(r[4]) for r in rows]    # index 4 = close
    return closes[-days:]


def _from_kraken(symbol, days):
    # Kraken calls Bitcoin "XBT".
    pair = ("XBT" if symbol == "BTC" else symbol) + "USD"
    url = f"https://api.kraken.com/0/public/OHLC?pair={pair}&interval=1440"
    data = _http_get_json(url)
    result = data["result"]
    key = next(k for k in result if k != "last")  # the pair name varies
    rows = result[key]                      # oldest -> newest
    closes = [float(r[4]) for r in rows]    # index 4 = close
    return closes[-days:]


def _from_cryptocompare(symbol, days):
    url = (f"https://min-api.cryptocompare.com/data/v2/histoday"
           f"?fsym={symbol}&tsym=USD&limit={days}")
    data = _http_get_json(url)
    rows = data["Data"]["Data"]             # oldest -> newest
    return [float(r["close"]) for r in rows]


def get_daily_closes(symbol, days):
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
            closes = fetch(symbol, days)
            if closes and len(closes) >= 2:
                print(f"  [data] prices loaded from {name} "
                      f"({len(closes)} days)")
                return closes
        except Exception as exc:  # noqa: BLE001 - we want to try the next source
            errors.append(f"{name}: {exc}")
    raise ConnectionError(
        "Could not fetch prices from any source.\n  " + "\n  ".join(errors)
        + "\n  Tip: run with --demo to use offline practice data."
    )


def demo_closes(days, seed=None):
    """Invent a believable price history so the bot can run with no internet.

    It's a 'random walk' with a gentle upward drift and occasional swings --
    enough to make the strategy buy and sell. NOT real data; for practice only.
    """
    rng = random.Random(seed)
    price = 30_000.0
    closes = []
    for i in range(days):
        drift = 0.0008                       # slight long-term upward push
        noise = rng.gauss(0, 0.02)           # day-to-day randomness (~2%)
        wave = 0.01 * math.sin(i / 9.0)      # a slow up/down cycle
        price *= (1 + drift + noise + wave)
        closes.append(round(price, 2))
    return closes
