#!/usr/bin/env bash
# Instala una tarea launchd que ejecuta sync_and_push.sh cada 6 horas (y al iniciar sesión).
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PLIST="$HOME/Library/LaunchAgents/com.mil.sync.plist"
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.mil.sync</string>
  <key>ProgramArguments</key><array><string>/bin/bash</string><string>-lc</string><string>$REPO/scripts/sync_and_push.sh</string></array>
  <key>StartInterval</key><integer>21600</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>/tmp/mil-km.log</string>
  <key>StandardErrorPath</key><string>/tmp/mil-km.log</string>
</dict></plist>
PL
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "Instalado. Log en /tmp/mil-km.log. Para quitarlo: launchctl unload $PLIST && rm $PLIST"
