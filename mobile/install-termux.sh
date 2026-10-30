#!/data/data/com.termux/files/usr/bin/bash
set -eu
export TZ=America/Vancouver
cd "$HOME"
if ! command -v proot-distro >/dev/null; then echo "ERROR: proot-distro not installed"; exit 1; fi
if ! command -v crontab >/dev/null; then echo "ERROR: cronie not installed"; exit 1; fi
if [ ! -f "$HOME/-fi_llauto/mobile/smartsheet-run.sh" ]; then echo "ERROR: run git pull in ~/ -fi_llauto first"; exit 1; fi
cp "$HOME/-fi_llauto/mobile/smartsheet-run.sh" "$HOME/smartsheet-run.sh"
chmod 700 "$HOME/smartsheet-run.sh"
printf 'test\n' > "$HOME/.smartsheet-mode"
chmod 600 "$HOME/.smartsheet-mode"
# Preserve unrelated crontab entries and make repeated installation idempotent.
(crontab -l 2>/dev/null || true) | grep -v '# SMARTSHEET_SAMSUNG' > "$HOME/.smartsheet-crontab.tmp" || true
printf '%s\n' '0,5,10,15,20,25,30,35 7 * * * /data/data/com.termux/files/home/smartsheet-run.sh # SMARTSHEET_SAMSUNG' >> "$HOME/.smartsheet-crontab.tmp"
crontab "$HOME/.smartsheet-crontab.tmp"
rm -f "$HOME/.smartsheet-crontab.tmp"
echo "Installed in TEST MODE. Scheduled 07:00-07:35 local phone time."
echo "Current time: $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "Check: crontab -l"
echo "Test now: ~/smartsheet-run.sh && tail -n 20 ~/smartsheet-cron.log"
echo "IMPORTANT: live submission is NOT enabled."
