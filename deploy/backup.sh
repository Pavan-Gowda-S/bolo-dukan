#!/usr/bin/env bash
# Daily backup of the Bolo Dukaan database and uploads. Keeps 14 days. Restore: see DEPLOY.md.
set -euo pipefail
APP_DIR=/opt/bolo-dukaan
DEST=/var/backups/bolo-dukaan
STAMP="$(date +%Y-%m-%d_%H%M)"
mkdir -p "$DEST"
# .backup is safe while the app is running (consistent copy, no lock problems)
sqlite3 "$APP_DIR/data/bolo_dukaan.db" ".backup '$DEST/db-$STAMP.sqlite'"
gzip -f "$DEST/db-$STAMP.sqlite"
if [ -d "$APP_DIR/data/uploads" ]; then tar -czf "$DEST/uploads-$STAMP.tar.gz" -C "$APP_DIR/data" uploads; fi
cp "$APP_DIR/data/secret.key" "$DEST/secret.key" 2>/dev/null || true
chmod 600 "$DEST"/* 2>/dev/null || true
find "$DEST" -name 'db-*.sqlite.gz' -mtime +14 -delete
find "$DEST" -name 'uploads-*.tar.gz' -mtime +14 -delete
echo "Backup done: $DEST/db-$STAMP.sqlite.gz"
