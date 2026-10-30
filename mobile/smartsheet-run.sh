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
RUN_OUTPUT="$(mktemp)"
trap 'rm -f "$RUN_OUTPUT"; rmdir "$LOCK" 2>/dev/null || true' EXIT
{
  echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') MODE=$MODE ==="
  proot-distro login debian -- /usr/bin/env "TEST_MODE=$TEST_MODE" /bin/bash -c '
    set -e
    cd /root/-fi_llauto
    set -a
    . /root/smartsheet.env
    set +a
    export TEST_MODE="$1"
    exec /root/smartsheet-venv/bin/python scripts/autofill.py
  ' _ "$TEST_MODE" > "$RUN_OUTPUT" 2>&1
  rc=$?
  cat "$RUN_OUTPUT"
  echo "Exit code: $rc"
} >> "$LOG" 2>&1
if [ "$MODE" = "live" ] && command -v termux-notification >/dev/null 2>&1; then
  if grep -q "успешно отправлена и подтверждена Smartsheet" "$RUN_OUTPUT"; then
    termux-notification --id 1002 --title "Smartsheet: отправлено" --content "Форма за $(date +%F) успешно отправлена." >/dev/null 2>&1 || true
  elif [ "$rc" -ne 0 ]; then
    termux-notification --id 1003 --title "Smartsheet: ошибка" --content "Ошибка автоотправки $(date +%F). Проверь журнал Termux." >/dev/null 2>&1 || true
  fi
fi
exit "$rc"
