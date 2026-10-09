#!/usr/bin/env bash
# Deploy the Mazh IVR into the live Asterisk configuration.
# Run with: sudo bash asterisk/deploy.sh
#
# Safe by design:
#   - Backs up the live dialplan and AGI before touching anything.
#   - Installs the Mazh contexts as /etc/asterisk/extensions_mazh.conf and
#     strips only the old [from-provider]/[mazh-speak] contexts from the live
#     extensions.conf, leaving everything else (echo test 600, etc.) intact.
#   - Reloads the dialplan only; never restarts the Asterisk service.
set -euo pipefail

[[ $EUID -eq 0 ]] || { echo "ERROR: run with sudo (needs write access to /etc/asterisk and /var/lib/asterisk)"; exit 1; }

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TS="$(date +%Y%m%d-%H%M%S)"
LIVE_DIALPLAN=/etc/asterisk/extensions.conf
MAZH_DIALPLAN=/etc/asterisk/extensions_mazh.conf
AGI_DST=/usr/share/asterisk/agi-bin/mazh_weather.py

echo "== 1. Backups =="
cp -a "$LIVE_DIALPLAN" "${LIVE_DIALPLAN}.bak-${TS}"
[ -f "$AGI_DST" ] && cp -a "$AGI_DST" "${AGI_DST}.bak-${TS}"

echo "== 2. Piper TTS at /opt/piper =="
if [ ! -x /opt/piper/piper ]; then
    install -d /opt/piper
    if [ ! -f /tmp/piper.tar.gz ]; then
        curl -L --retry 5 -o /tmp/piper.tar.gz \
            https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_x86_64.tar.gz
    fi
    tar xzf /tmp/piper.tar.gz -C /opt/piper --strip-components=1
fi
if [ ! -f /opt/piper/voices/en_US-lessac-medium.onnx ]; then
    install -d /opt/piper/voices
    curl -L --retry 5 -o /opt/piper/voices/en_US-lessac-medium.onnx \
        https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/medium/en_US-lessac-medium.onnx
    curl -L --retry 5 -o /opt/piper/voices/en_US-lessac-medium.onnx.json \
        https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json
fi
chmod -R a+rX /opt/piper
echo "piper: $(/opt/piper/piper --version 2>/dev/null | head -1 || echo 'installed at /opt/piper/piper')"

echo "== 3. AGI script =="
install -o asterisk -g asterisk -m 0755 "$REPO_DIR/asterisk/agi/mazh_weather.py" "$AGI_DST"
# The AGI reads this env file itself as a fallback; keep it group-readable
# by asterisk only (it holds the phone API key).
[ -f /etc/asterisk/mazh.env ] && chown root:asterisk /etc/asterisk/mazh.env && chmod 640 /etc/asterisk/mazh.env

echo "== 4. Prompt recordings + TTS cache dir =="
# Playback() resolves prompts under <astdatadir>/sounds/<language>/ (en by default).
SOUNDS_DIR=/usr/share/asterisk/sounds/en/mazh
install -d -o asterisk -g asterisk -m 0755 "$SOUNDS_DIR/generated"
for wav in "$REPO_DIR"/asterisk/sounds/mazh/*.wav; do
    install -o asterisk -g asterisk -m 0644 "$wav" "$SOUNDS_DIR/$(basename "$wav")"
done

echo "== 5. Dialplan =="
install -m 0644 "$REPO_DIR/asterisk/extensions.conf" "$MAZH_DIALPLAN"
# Strip old Mazh contexts from the live dialplan (everything from the context
# header to the next context header / EOF), preserving all other contexts.
if grep -Eq '^\[(from-provider|mazh-speak)\]' "$LIVE_DIALPLAN"; then
    awk '
        /^\[(from-provider|mazh-speak)\]/ { skip=1; next }
        /^\[/ { skip=0 }
        !skip { print }
    ' "${LIVE_DIALPLAN}.bak-${TS}" > "$LIVE_DIALPLAN"
fi
if ! grep -q '#include extensions_mazh.conf' "$LIVE_DIALPLAN"; then
    printf '\n#include extensions_mazh.conf\n' >> "$LIVE_DIALPLAN"
fi

echo "== 6. Sanity checks =="
asterisk -rx 'core show application Playback' >/dev/null || { echo "ERROR: cannot reach Asterisk CLI"; exit 1; }
grep -q 'exten => 600' "$LIVE_DIALPLAN" && echo "OK: echo test 600 still present in live dialplan"
grep -q '^\[from-provider\]' "$MAZH_DIALPLAN" && echo "OK: Mazh contexts installed in $MAZH_DIALPLAN"

echo "== 7. Dialplan reload (no service restart; active calls unaffected) =="
asterisk -rx 'dialplan reload'

echo "Deploy complete. Backups: ${LIVE_DIALPLAN}.bak-${TS}"
