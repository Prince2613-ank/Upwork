#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
: "${1:?Pass an immutable ghcr.io image reference}"
: "${BACKUP_DIR:?Set BACKUP_DIR to the backup destination}"
case "$1" in ghcr.io/*:*) ;; *) echo "Expected a GHCR image with an immutable commit tag" >&2; exit 1;; esac
docker compose --env-file .env.server -f compose.server.yml exec -T api python -m server.admin prepare-update
sh deploy/backup.sh
python3 - "$1" <<'PY'
import re
import sys
from pathlib import Path
image = sys.argv[1]
if not re.fullmatch(r'ghcr\.io/[a-z0-9_.-]+/[a-z0-9_.-]+:[a-f0-9]{40}', image):
    raise SystemExit('Use a lowercase GHCR repository and a full 40-character commit SHA tag')
path = Path('.env.server')
content = path.read_text()
line = 'FLODATA_IMAGE=' + image
updated, count = re.subn(r'^FLODATA_IMAGE=.*$', line, content, flags=re.M)
if not count:
    updated += '\n' + line + '\n'
temporary = path.with_suffix('.tmp')
temporary.write_text(updated)
temporary.chmod(0o600)
temporary.replace(path)
PY
docker compose --env-file .env.server -f compose.server.yml pull api worker scheduler browser-a browser-b
docker compose --env-file .env.server -f compose.server.yml up -d --no-build --wait --wait-timeout 180
echo "Update complete. Check login/session status and resume collection from the dashboard."
