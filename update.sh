#!/usr/bin/env bash
# update.sh -- pull the latest bot code in one command.
#
# Your settings and keys are SAFE: they all live in keys.env (which is
# gitignored), not in the tracked code files -- so an update never overwrites
# them. After this, just keep using the bot as before.

set -euo pipefail
cd "$(dirname "$0")"

echo "Fetching the latest version..."
git pull --ff-only
chmod +x run_daily.sh setup_schedule.sh update.sh 2>/dev/null || true
echo ""
echo "Updated. Your keys.env and settings were left untouched."
echo "If the bot is scheduled, the next run uses the new code automatically."
