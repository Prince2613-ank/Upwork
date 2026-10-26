#!/bin/sh
# Schedule on the host. BACKUP_DIR should be synced to encrypted off-server storage.
set -eu
cd "$(dirname "$0")/.."
: "${BACKUP_DIR:?Set BACKUP_DIR to an encrypted backup destination}"
umask 077
mkdir -p "$BACKUP_DIR"
stamp=$(date -u +%Y%m%dT%H%M%SZ)
docker compose --env-file .env.server -f compose.server.yml exec -T db pg_dump -U flodata -d flodata -Fc > "$BACKUP_DIR/flodata-$stamp.dump.tmp"
mv "$BACKUP_DIR/flodata-$stamp.dump.tmp" "$BACKUP_DIR/flodata-$stamp.dump"
echo "Database backup created. Back up reports and browser profiles separately while workers/browsers are stopped."
