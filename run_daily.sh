#!/usr/bin/env bash
# run_daily.sh -- runs the paper-trading bot once and records the output.
#
# This is the script the scheduler calls every day. It makes sure the bot runs
# from the right folder no matter where it's launched from, and appends a
# timestamped record of each run to bot.log so you can review history later.

set -euo pipefail

# Always run from the folder this script lives in.
cd "$(dirname "$0")"

# Pick a Python: prefer python3, fall back to python.
PY="$(command -v python3 || command -v python)"

{
  echo ""
  echo "########## run at $(date) ##########"
  "$PY" bot.py
} >> bot.log 2>&1

# Also print the latest run to the screen if a human is watching.
tail -n 25 bot.log
