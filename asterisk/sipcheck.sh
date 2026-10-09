#!/usr/bin/env bash
# Diagnostic: show the pjsip 1001 endpoint config with secrets masked.
# Run with: sudo bash asterisk/sipcheck.sh
set -uo pipefail

CONF=/etc/asterisk/pjsip.conf
[[ -r $CONF ]] || { echo "cannot read $CONF"; exit 1; }

echo "== pjsip.conf: blocks for 1001 (passwords masked) =="
awk '
    /^\[1001/ { inblk=1 }
    inblk && /^\[/ && !/^\[1001/ { inblk=0 }
    inblk { print NR ": " $0 }
' "$CONF" | sed 's/\(password\|secret\)=.*/\1=***REDACTED***/I'

echo
echo "== live endpoint 1001 (codec/context lines) =="
asterisk -rx 'pjsip show endpoint 1001' 2>/dev/null | grep -iE 'device_state|allow|codec|context|contact' || echo "asterisk CLI unreachable"
