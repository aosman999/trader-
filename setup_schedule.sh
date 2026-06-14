#!/usr/bin/env bash
# setup_schedule.sh -- set up the bot to run automatically once a day (macOS/Linux).
#
# It adds a "cron job": a line that tells your computer to run the bot at a set
# time daily. Safe to run more than once -- it replaces its own entry instead of
# piling up duplicates. Windows users: see SCHEDULING.md instead.
#
# Usage:
#   ./setup_schedule.sh            # run daily at 09:00 (default)
#   ./setup_schedule.sh 18 30      # run daily at 18:30
#   ./setup_schedule.sh hourly     # run every hour (for INTERVAL="1h")
#   ./setup_schedule.sh minute     # run every minute (for INTERVAL="1m")
#   ./setup_schedule.sh --remove   # stop the scheduled runs

set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
RUNNER="$DIR/run_daily.sh"
TAG="# crypto-paper-bot ($DIR)"   # marker so we can find/replace our own line

# Remove any existing entry we previously added.
current="$(crontab -l 2>/dev/null | grep -v -F "$TAG" || true)"

if [ "${1:-}" = "--remove" ]; then
  printf '%s\n' "$current" | crontab -
  echo "Removed the daily schedule. The bot will no longer run on its own."
  exit 0
fi

chmod +x "$RUNNER"

if [ "${1:-}" = "minute" ]; then
  # every minute (cron's fastest). Match with INTERVAL="1m" in config.py.
  schedule="* * * * *"
  human="every minute"
elif [ "${1:-}" = "hourly" ]; then
  # minute=0, every hour -> runs at the top of every hour, every day.
  schedule="0 * * * *"
  human="every hour, on the hour"
else
  HOUR="${1:-9}"
  MIN="${2:-0}"
  schedule="$MIN $HOUR * * *"          # every day at HOUR:MIN
  human="$(printf 'every day at %02d:%02d' "$HOUR" "$MIN")"
fi

# Quote the runner path so a folder name containing spaces still works.
new_line="$schedule \"$RUNNER\" $TAG"
printf '%s\n%s\n' "$current" "$new_line" | grep -v '^$' | crontab -

echo "Scheduled: the bot will run $human."
echo "Output is appended to: $DIR/bot.log"
echo "To stop it later:  ./setup_schedule.sh --remove"
echo "To see the schedule:  crontab -l"
