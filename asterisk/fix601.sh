#!/usr/bin/env bash
# Remove the stale SayAlpha test on 601 from the live [mazh-test] context so
# the new TTS version in extensions_mazh.conf applies (Asterisk keeps the
# first definition of an extension, so the old block must go).
# Run with: sudo bash asterisk/fix601.sh
set -euo pipefail

[[ $EUID -eq 0 ]] || { echo "ERROR: run with sudo"; exit 1; }
LIVE=/etc/asterisk/extensions.conf
TS="$(date +%Y%m%d-%H%M%S)"

echo "== 1. Backup =="
cp -a "$LIVE" "${LIVE}.bak-${TS}"

echo "== 2. Remove old 601 block from [mazh-test] =="
if grep -q "^exten => 601," "$LIVE"; then
    tmp="$(mktemp)"
    awk '
        /^\[mazh-test\]/ { ctx=1 }
        ctx && /^\[/ { ctx = (/^\[mazh-test\]$/) ? 1 : 0 }
        ctx && /^exten => 601,/ { skip=1; next }
        skip && ctx { if (/Hangup/) skip=0; next }
        { print }
    ' "$LIVE" > "$tmp"
    grep -q "^exten => 601," "$tmp" && { echo "ERROR: 601 still present after edit"; rm -f "$tmp"; exit 1; }
    grep -q "exten => 600" "$tmp" || { echo "ERROR: echo test 600 would be lost - aborting"; rm -f "$tmp"; exit 1; }
    cat "$tmp" > "$LIVE" && rm -f "$tmp"
else
    echo "no old 601 block found - nothing to remove"
fi

echo "== 3. Reload dialplan =="
asterisk -rx 'dialplan reload'

echo "== 4. Verify =="
asterisk -rx 'dialplan show mazh-test'
echo "Done. Backup: ${LIVE}.bak-${TS}"
