#!/usr/bin/env python3
"""
talk.py -- talk to your bot.

Run it in your terminal:   python3 talk.py
Then just type things, e.g.:
    i entered SOL long 170 tp 200 sl 165 lev 5
    exited SOL
    positions
    help
    quit

It records the FUTURES trades you place by hand (off the bot's signals) so the
scheduled bot can watch them and TEXT YOU the moment price hits your take-profit
or stop-loss. (Your spot trades are automatic and already tracked -- this is for
the manual futures ones.)
"""

import json
import os

POS_FILE = "manual_positions.json"


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


def _entered(words):
    if len(words) < 3:
        return ("Tell me: entered <COIN> <long|short> <entry> "
                "[tp <price>] [sl <price>] [lev <x>]\n"
                "e.g.  i entered SOL long 170 tp 200 sl 165 lev 5")
    coin = words[0].upper()
    side = words[1].lower()
    if side not in ("long", "short"):
        return "Is it a long or a short? e.g. 'i entered SOL long 170'"
    try:
        entry = float(words[2])
    except ValueError:
        return f"'{words[2]}' isn't a number -- give me the entry price."
    pos = {"coin": coin, "side": side, "entry": entry,
           "tp": None, "sl": None, "lev": None}
    rest = words[3:]
    i = 0
    while i < len(rest) - 1:
        key, val = rest[i].lower(), rest[i + 1]
        try:
            if key in ("tp", "takeprofit", "take-profit"):
                pos["tp"] = float(val)
            elif key in ("sl", "stop", "stoploss", "stop-loss"):
                pos["sl"] = float(val)
            elif key in ("lev", "leverage", "x"):
                pos["lev"] = float(val.rstrip("x"))
        except ValueError:
            pass
        i += 2
    positions = [p for p in _load() if p["coin"] != coin]   # replace if exists
    positions.append(pos)
    _save(positions)
    bits = []
    if pos["tp"]:
        bits.append(f"TP ${pos['tp']:g}")
    if pos["sl"]:
        bits.append(f"SL ${pos['sl']:g}")
    if pos["lev"]:
        bits.append(f"{pos['lev']:g}x")
    tail = f" ({', '.join(bits)})" if bits else ""
    return (f"Got it -- watching your {coin} {side} from ${entry:g}{tail}. "
            f"I'll text you the moment it hits TP or SL.")


def _exited(words):
    if not words:
        return "Which one? e.g. 'exited SOL'"
    coin = words[0].upper()
    positions = _load()
    kept = [p for p in positions if p["coin"] != coin]
    if len(kept) == len(positions):
        return f"I wasn't tracking a {coin} position."
    _save(kept)
    return f"Done -- closed {coin}, no longer watching it."


def _positions():
    positions = _load()
    if not positions:
        return "Not watching any manual positions right now."
    lines = ["Watching your manual futures positions:"]
    for p in positions:
        s = f"  {p['coin']} {p['side']} from ${p['entry']:g}"
        if p.get("tp"):
            s += f", TP ${p['tp']:g}"
        if p.get("sl"):
            s += f", SL ${p['sl']:g}"
        if p.get("lev"):
            s += f", {p['lev']:g}x"
        lines.append(s)
    return "\n".join(lines)


HELP = """I can track the futures trades you place by hand. Try:
  i entered SOL long 170 tp 200 sl 165 lev 5
  exited SOL
  positions          (what I'm watching)
  help
  quit"""


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
    return "Didn't catch that. Type 'help' to see what I understand."


def main():
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


if __name__ == "__main__":
    main()
