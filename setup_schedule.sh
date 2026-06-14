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
#   ./setup_schedule.sh --remove   # stop the daily run

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

HOUR="${1:-9}"
MIN="${2:-0}"

chmod +x "$RUNNER"

# minute hour * * *  -> every day at HOUR:MIN
new_line="$MIN $HOUR * * * $RUNNER $TAG"
printf '%s\n%s\n' "$current" "$new_line" | grep -v '^$' | crontab -

printf "Scheduled: the bot will run every day at %02d:%02d.\n" "$HOUR" "$MIN"
echo "Output is appended to: $DIR/bot.log"
echo "To stop it later:  ./setup_schedule.sh --remove"
echo "To see the schedule:  crontab -l"
