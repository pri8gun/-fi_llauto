#!/data/data/com.termux/files/usr/bin/bash
set -u
export TZ=America/Vancouver
LOG="$HOME/smartsheet-cron.log"
LOCK="$HOME/.smartsheet-run.lock"
MODE_FILE="$HOME/.smartsheet-mode"
mkdir -p "$HOME"
if ! mkdir "$LOCK" 2>/dev/null; then
  echo "$(date): another run is active; skipping" >> "$LOG"
  exit 0
fi
trap 'rmdir "$LOCK" 2>/dev/null || true' EXIT
MODE=test
if [ -f "$MODE_FILE" ]; then MODE="$(cat "$MODE_FILE")"; fi
if [ "$MODE" != "live" ]; then export TEST_MODE=true; else export TEST_MODE=false; fi
{
  echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') MODE=$MODE ==="
  proot-distro login debian -- /usr/bin/env "TEST_MODE=$TEST_MODE" /bin/bash -c '
    set -e
    cd /root/-fi_llauto
    set -a
    . /root/smartsheet.env
    set +a
    exec /root/smartsheet-venv/bin/python scripts/autofill.py
  '
  rc=$?
  echo "Exit code: $rc"
} >> "$LOG" 2>&1
exit "$rc"
