"""
notify.py  --  send a phone notification when the bot trades.
============================================================

Supports two free services. You only need ONE. Set it up in keys.env so the
scheduled runs can use it too.

ntfy (easiest -- no account):
  1. Install the "ntfy" app on your phone (App Store / Google Play).
  2. In the app, "Subscribe to topic" and invent a hard-to-guess name,
     e.g.  my-trader-bot-9f3k2   (anyone who knows the name can see the alerts,
     so make it long and random).
  3. Put that name in keys.env:   export NTFY_TOPIC="my-trader-bot-9f3k2"

Telegram (more private -- needs a bot):
  1. Message @BotFather on Telegram, /newbot, copy the token.
  2. Message your new bot once, then get your chat id (e.g. via @userinfobot).
  3. In keys.env:
       export TELEGRAM_BOT_TOKEN="123456:abc..."
       export TELEGRAM_CHAT_ID="123456789"

If neither is set, notifications are simply skipped (the bot still trades).
"""

import os
import urllib.parse
import urllib.request


def send(message, title="Trading bot"):
    """Send `message` to whichever notifier is configured. Never raises --
    a failed notification must not stop the bot. Returns True if sent."""
    sent = False

    topic = os.environ.get("NTFY_TOPIC")
    if topic:
        try:
            req = urllib.request.Request(
                f"https://ntfy.sh/{topic}",
                data=message.encode("utf-8"),
                headers={"Title": title})
            urllib.request.urlopen(req, timeout=10)
            sent = True
        except Exception as exc:  # noqa: BLE001 - notifications are best-effort
            print(f"  [notify] ntfy failed: {exc}")

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if token and chat:
        try:
            data = urllib.parse.urlencode(
                {"chat_id": chat, "text": f"{title}\n{message}"}).encode()
            urllib.request.urlopen(
                urllib.request.Request(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    data=data),
                timeout=10)
            sent = True
        except Exception as exc:  # noqa: BLE001
            print(f"  [notify] telegram failed: {exc}")

    return sent
