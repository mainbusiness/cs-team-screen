#!/bin/bash
# Installs the external driver as a launchd job (user agent, UID 503). Idempotent. ~/Documents is blocked for launchd (TCC), so the
# script, the engine URLs (no secrets) and the log live in /Users/Shared/cs_driver. TOKEN_SECRET stays in the Keychain.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
DEST=/Users/Shared/cs_driver
mkdir -p "$DEST"
cp "$HERE/driver.py" "$DEST/driver.py"
python3 - "$HERE/../../deploy/deployments.json" "$DEST/engines.json" <<'PY'
import json, sys
ids = json.load(open(sys.argv[1]))
json.dump({b: "https://script.google.com/macros/s/%s/exec" % i for b, i in ids.items()}, open(sys.argv[2], "w"))
PY
PL=~/Library/LaunchAgents/com.guy.cs-driver.plist
cp "$HERE/com.guy.cs-driver.plist" "$PL"
launchctl bootout gui/503/com.guy.cs-driver 2>/dev/null || true
launchctl bootstrap gui/503 "$PL"
launchctl kickstart -k gui/503/com.guy.cs-driver
echo installed; launchctl print gui/503/com.guy.cs-driver | grep -E "state|runs|last exit" | head
