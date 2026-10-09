#!/usr/bin/env bash
# Fix SIP audio negotiation for endpoint 1001 (Linphone) and install the
# updated Mazh dialplan. Run with: sudo bash asterisk/mazhfix.sh
#
# - Widens endpoint 1001 codecs: allow=ulaw -> allow=ulaw,alaw,gsm
#   (Linphone's offer was not matching ulaw-only, so calls died at SDP
#   negotiation before reaching the dialplan).
# - Installs the updated extensions_mazh.conf (overrides test ext 601,
#   adds 602; the 600 echo test in extensions.conf is untouched).
# - Reloads pjsip + dialplan; never restarts the service.
set -euo pipefail

[[ $EUID -eq 0 ]] || { echo "ERROR: run with sudo"; exit 1; }
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TS="$(date +%Y%m%d-%H%M%S)"
PJSIP=/etc/asterisk/pjsip.conf
MAZH_DIALPLAN=/etc/asterisk/extensions_mazh.conf

echo "== 1. Backup =="
cp -a "$PJSIP" "${PJSIP}.bak-${TS}"
cp -a "$MAZH_DIALPLAN" "${MAZH_DIALPLAN}.bak-${TS}" 2>/dev/null || true

echo "== 2. Endpoint 1001 codecs =="
if awk '/^\[1001\]$/{f=1} f&&/^\[1001-auth\]/{exit} f&&/^allow=ulaw,alaw,gsm$/{found=1} END{exit !found}' "$PJSIP"; then
    echo "already allow=ulaw,alaw,gsm"
else
    tmp="$(mktemp)"
    awk '
        /^\[1001\]$/ && !done { inblk=1; print; next }
        inblk && /^\[1001-auth\]/ { inblk=0; done=1; print; next }
        inblk && /^allow=ulaw$/ { print "allow=ulaw,alaw,gsm"; next }
        { print }
    ' "$PJSIP" > "$tmp"
    grep -q '^allow=ulaw,alaw,gsm$' "$tmp" || { echo "ERROR: allow line not updated"; rm -f "$tmp"; exit 1; }
    cat "$tmp" > "$PJSIP" && rm -f "$tmp"
fi
sed -n '/^\[1001\]$/,/^\[1001-auth\]/p' "$PJSIP" | grep '^allow=' || {
    echo "ERROR: allow line not found/updated in [1001]"; exit 1;
}

echo "== 3. Install updated Mazh dialplan =="
install -m 0644 "$REPO_DIR/asterisk/extensions.conf" "$MAZH_DIALPLAN"

echo "== 4. Reload pjsip + dialplan (no service restart) =="
asterisk -rx 'pjsip reload'
asterisk -rx 'dialplan reload'

echo "== 5. Verify =="
asterisk -rx 'pjsip show endpoint 1001' | grep -E '^\s+allow\s' || true
asterisk -rx 'dialplan show mazh-test'
echo "Done. Backups: ${PJSIP}.bak-${TS} ${MAZH_DIALPLAN}.bak-${TS}"
