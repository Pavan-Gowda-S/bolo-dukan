#!/usr/bin/env bash
# Get the newest version from GitHub and restart. Your .env and data/ are never touched.
#   sudo bolo-update
set -euo pipefail
APP_DIR=/opt/bolo-dukaan
[ "$(id -u)" -eq 0 ] || { echo "Run with sudo: sudo bolo-update"; exit 1; }
/usr/local/bin/bolo-backup >/dev/null && echo "Backed up first."
git -C "$APP_DIR" fetch -q origin main
git -C "$APP_DIR" reset -q --hard origin/main
"$APP_DIR/.venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"
chown -R bolo:bolo "$APP_DIR"
systemctl restart bolo-dukaan
for i in $(seq 1 20); do curl -fsS http://127.0.0.1:8000/api/health >/dev/null 2>&1 && break; sleep 1; done
curl -fsS http://127.0.0.1:8000/api/health >/dev/null && echo "Updated to: $(git -C "$APP_DIR" log --oneline -1)" || { journalctl -u bolo-dukaan -n 30 --no-pager; exit 1; }
install -m 755 "$APP_DIR/deploy/backup.sh" /usr/local/bin/bolo-backup
install -m 755 "$APP_DIR/deploy/update.sh" /usr/local/bin/bolo-update
