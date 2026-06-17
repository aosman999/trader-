#!/usr/bin/env python3
"""
talk.py -- talk to your bot in plain English.
=============================================

Run it in your terminal:   python3 talk.py
Then just say things naturally, e.g.:

    i entered xpl and ethfi 2x leverage, 50% of my money on each.
        pnl for ethfi is -0.25%, xpl is +0.51%
    i'm out of sol
    how are my trades doing?
    what should i keep an eye on?

It records the FUTURES trades you place by hand (off the bot's signals) into
manual_positions.json, so the scheduled bot can watch them and TEXT YOU the
moment price hits your take-profit / stop-loss -- OR when the setup breaks down
and you should think about exiting early. (Your spot trades are automatic and
already tracked -- this is for the manual futures ones.)

TWO MODES, automatically:
  * If you've set ANTHROPIC_API_KEY (in keys.env), you get a real conversation --
    a Claude "brain" that understands free-form English and records/closes your
    trades for you. This costs a fraction of a cent per message.
  * If you haven't, it falls back to a simple command mode (still works fine):
        i entered SOL long 170 tp 200 sl 165 lev 5
        exited SOL
        positions
"""

import json
import os

POS_FILE = "manual_positions.json"


# ---------------------------------------------------------------------------
# Storage + the underlying actions (shared by both the AI and the fallback).
# ---------------------------------------------------------------------------

def _load():
    if os.path.exists(POS_FILE):
        try:
            with open(POS_FILE) as f:
                return json.load(f)
        except Exception:  # noqa: BLE001
            return []
    return []


def _save(positions):
    with open(POS_FILE, "w") as f:
        json.dump(positions, f, indent=2)


def record_trade(coin, side, entry=None, tp=None, sl=None, lev=None, pnl=None):
    """Record (or replace) a manual futures position so the bot watches it."""
    coin = coin.upper()
    side = (side or "long").lower()
    if side not in ("long", "short"):
        side = "long"
    pos = {"coin": coin, "side": side,
           "entry": float(entry) if entry not in (None, "") else None,
           "tp": float(tp) if tp not in (None, "") else None,
           "sl": float(sl) if sl not in (None, "") else None,
           "lev": float(lev) if lev not in (None, "") else None}
    if pnl not in (None, ""):
        pos["pnl"] = float(pnl)
    positions = [p for p in _load() if p["coin"] != coin]   # replace if exists
    positions.append(pos)
    _save(positions)
    return pos


def close_position(coin):
    """Stop watching a position. Returns True if one was removed."""
    coin = coin.upper()
    positions = _load()
    kept = [p for p in positions if p["coin"] != coin]
    if len(kept) == len(positions):
        return False
    _save(kept)
    return True


def _describe(p):
    s = f"{p['coin']} {p['side']}"
    if p.get("entry"):
        s += f" from ${p['entry']:g}"
    if p.get("tp"):
        s += f", TP ${p['tp']:g}"
    if p.get("sl"):
        s += f", SL ${p['sl']:g}"
    if p.get("lev"):
        s += f", {p['lev']:g}x"
    if p.get("pnl") is not None:
        s += f", PnL {p['pnl']:+g}%"
    return s


# ---------------------------------------------------------------------------
# A little live market read, so the assistant can answer "how's my XPL?" and
# "should I exit?". Best-effort -- needs the broker/keys, but never crashes.
# ---------------------------------------------------------------------------

def market_read(coin):
    """Current price + a quick trend read for one coin. Returns a dict."""
    try:
        import broker as broker_mod
        import config
        import strategy
        broker = broker_mod.make_broker()
        price = broker.get_prices(coin.upper(), config.INTERVAL)[-1]
        ups = downs = 0
        for tf in ("5m", "15m", "1h"):
            try:
                prices = broker.get_prices(coin.upper(), tf)
            except Exception:  # noqa: BLE001
                continue
            if strategy.trend_up(prices):
                ups += 1
            elif strategy.trend_down(prices):
                downs += 1
        trend = ("up" if ups > downs else "down" if downs > ups else "sideways")
        return {"coin": coin.upper(), "price": price, "trend": trend,
                "timeframes_up": ups, "timeframes_down": downs}
    except Exception as exc:  # noqa: BLE001
        return {"coin": coin.upper(), "error": str(exc).splitlines()[0][:120]}


def account_status():
    """Spot cash + futures equity, best-effort. Returns a dict."""
    out = {}
    try:
        import broker as broker_mod
        broker = broker_mod.make_broker()
        out["spot_cash_usdt"] = round(broker.cash(), 2)
    except Exception as exc:  # noqa: BLE001
        out["spot_error"] = str(exc).splitlines()[0][:120]
    try:
        import mexc_futures
        out["futures_equity_usdt"] = round(
            mexc_futures.MexcFuturesClient().usdt_equity(), 2)
    except Exception as exc:  # noqa: BLE001
        out["futures_error"] = str(exc).splitlines()[0][:120]
    out["watching"] = [_describe(p) for p in _load()]
    return out


# ---------------------------------------------------------------------------
# Fallback: simple command parser (used when there's no ANTHROPIC_API_KEY).
# ---------------------------------------------------------------------------

def _entered(words):
    if len(words) < 3:
        return ("Tell me: entered <COIN> <long|short> <entry> "
                "[tp <price>] [sl <price>] [lev <x>]\n"
                "e.g.  i entered SOL long 170 tp 200 sl 165 lev 5")
    coin, side = words[0], words[1].lower()
    if side not in ("long", "short"):
        return "Is it a long or a short? e.g. 'i entered SOL long 170'"
    try:
        entry = float(words[2])
    except ValueError:
        return f"'{words[2]}' isn't a number -- give me the entry price."
    kw = {"tp": None, "sl": None, "lev": None}
    rest = words[3:]
    i = 0
    while i < len(rest) - 1:
        key, val = rest[i].lower(), rest[i + 1]
        try:
            if key in ("tp", "takeprofit", "take-profit"):
                kw["tp"] = float(val)
            elif key in ("sl", "stop", "stoploss", "stop-loss"):
                kw["sl"] = float(val)
            elif key in ("lev", "leverage", "x"):
                kw["lev"] = float(val.rstrip("x"))
        except ValueError:
            pass
        i += 2
    pos = record_trade(coin, side, entry, **kw)
    return f"Got it -- watching {_describe(pos)}. I'll text you on TP/SL or a breakdown."


def _exited(words):
    if not words:
        return "Which one? e.g. 'exited SOL'"
    coin = words[0].upper()
    if close_position(coin):
        return f"Done -- closed {coin}, no longer watching it."
    return f"I wasn't tracking a {coin} position."


def _positions():
    positions = _load()
    if not positions:
        return "Not watching any manual positions right now."
    return "Watching your manual futures positions:\n" + \
        "\n".join("  " + _describe(p) for p in positions)


HELP = """I can track the futures trades you place by hand. Try:
  i entered SOL long 170 tp 200 sl 165 lev 5
  exited SOL
  positions          (what I'm watching)
  help
  quit
(Set ANTHROPIC_API_KEY in keys.env to just talk to me in plain English instead.)"""


def handle(line):
    parts = line.split()
    if parts and parts[0].lower() in ("i", "ive", "i've"):
        parts = parts[1:]                       # allow "i entered ..."
    if not parts:
        return ""
    cmd, args = parts[0].lower(), parts[1:]
    if cmd in ("entered", "enter", "took", "bought", "opened"):
        return _entered(args)
    if cmd in ("exited", "exit", "closed", "close", "out", "sold"):
        return _exited(args)
    if cmd in ("positions", "position", "status", "list", "watching"):
        return _positions()
    if cmd in ("help", "?", "commands"):
        return HELP
    return "Didn't catch that. Type 'help', or set ANTHROPIC_API_KEY to just talk."


# ---------------------------------------------------------------------------
# The AI brain (used when ANTHROPIC_API_KEY is set and the SDK is installed).
# ---------------------------------------------------------------------------

MODEL = "claude-opus-4-8"

SYSTEM = """You are the user's personal crypto trading assistant, living in their \
terminal. The user trades MEXC futures BY HAND (MEXC blocks futures orders over \
the API), while a separate automated bot trades spot. Your job is to let them \
talk to that bot in plain English.

When the user tells you about a futures trade they placed, CALL log_trade so the \
bot starts watching it -- it will text them when price hits take-profit / \
stop-loss, or when the trend turns against the position. If they mention several \
trades in one message, call log_trade once per coin. When they say they've closed \
or exited a trade, call close_trade. Use list_positions, market_read and \
account_status to answer questions about how things are going.

Be brief, concrete and friendly -- this is a chat, not an essay. It's fine to \
record a trade with only partial info (e.g. just leverage and PnL, no entry); \
record what you have and gently ask for a stop-loss if they didn't give one, \
since without it the bot can't warn them. NEVER promise profits or certainty. If \
the user asks whether to exit, give your honest read of the trend from \
market_read, but make clear the decision is theirs."""

TOOLS = [
    {"name": "log_trade",
     "description": "Record a manual futures trade so the bot watches it for "
                    "TP/SL and trend breaks. Replaces any existing trade on the "
                    "same coin.",
     "input_schema": {"type": "object", "properties": {
         "coin": {"type": "string", "description": "Base symbol, e.g. XPL, SOL, ETHFI"},
         "side": {"type": "string", "enum": ["long", "short"]},
         "entry": {"type": "number", "description": "Entry price (omit if unknown)"},
         "tp": {"type": "number", "description": "Take-profit price (optional)"},
         "sl": {"type": "number", "description": "Stop-loss price (optional)"},
         "leverage": {"type": "number", "description": "Leverage, e.g. 2 for 2x"},
         "pnl": {"type": "number", "description": "Current PnL percent, if known"}},
         "required": ["coin", "side"]}},
    {"name": "close_trade",
     "description": "Stop watching a position the user has exited/closed.",
     "input_schema": {"type": "object", "properties": {
         "coin": {"type": "string"}}, "required": ["coin"]}},
    {"name": "list_positions",
     "description": "List the manual positions the bot is currently watching.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "market_read",
     "description": "Current price and a quick multi-timeframe trend read for one "
                    "coin. Use to answer 'how's my X doing' or 'should I exit'.",
     "input_schema": {"type": "object", "properties": {
         "coin": {"type": "string"}}, "required": ["coin"]}},
    {"name": "account_status",
     "description": "Spot cash, futures equity, and what's being watched.",
     "input_schema": {"type": "object", "properties": {}}},
]


def _run_tool(name, inp):
    """Dispatch a tool call to the real function; return a JSON-able result."""
    if name == "log_trade":
        pos = record_trade(inp["coin"], inp.get("side", "long"),
                           entry=inp.get("entry"), tp=inp.get("tp"),
                           sl=inp.get("sl"), lev=inp.get("leverage"),
                           pnl=inp.get("pnl"))
        return {"recorded": _describe(pos),
                "has_stop_loss": pos.get("sl") is not None}
    if name == "close_trade":
        return {"closed": close_position(inp["coin"]), "coin": inp["coin"].upper()}
    if name == "list_positions":
        return {"watching": [_describe(p) for p in _load()]}
    if name == "market_read":
        return market_read(inp["coin"])
    if name == "account_status":
        return account_status()
    return {"error": f"unknown tool {name}"}


def ai_main(client):
    print("\nTalk to your bot in plain English. Type 'quit' to leave.\n")
    history = []
    while True:
        try:
            line = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nbye"); return
        if line.lower() in ("quit", "q", "bye", "leave", "exit"):
            print("bye"); return
        if not line:
            continue
        history.append({"role": "user", "content": line})

        # Tool-use loop: keep calling tools until Claude gives a final answer.
        while True:
            resp = client.messages.create(model=MODEL, max_tokens=1024,
                                          system=SYSTEM, tools=TOOLS,
                                          messages=history)
            history.append({"role": "assistant", "content": resp.content})
            tool_results = []
            said = []
            for block in resp.content:
                if block.type == "text":
                    said.append(block.text)
                elif block.type == "tool_use":
                    result = _run_tool(block.name, block.input or {})
                    tool_results.append({"type": "tool_result",
                                         "tool_use_id": block.id,
                                         "content": json.dumps(result)})
            if said:
                print("bot> " + "\n".join(said).replace("\n", "\n     "))
            if resp.stop_reason == "tool_use" and tool_results:
                history.append({"role": "user", "content": tool_results})
                continue   # let Claude react to the tool results
            break


def _make_client():
    """Return an Anthropic client if possible, else None (-> fallback mode)."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    try:
        import anthropic
        return anthropic.Anthropic()
    except ImportError:
        print("(To chat in plain English: pip install anthropic. "
              "Using simple command mode for now.)")
        return None
    except Exception as exc:  # noqa: BLE001
        print(f"(Couldn't start the AI brain: {str(exc).splitlines()[0][:100]}. "
              f"Using simple command mode.)")
        return None


def fallback_main():
    print("\nTalk to your bot. Type 'help' for commands, 'quit' to leave.\n")
    while True:
        try:
            line = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nbye"); return
        if line.lower() in ("quit", "q", "bye", "leave"):
            print("bye"); return
        reply = handle(line)
        if reply:
            print("bot> " + reply.replace("\n", "\n     "))


def main():
    client = _make_client()
    if client is not None:
        ai_main(client)
    else:
        fallback_main()


if __name__ == "__main__":
    main()
