#!/bin/bash
# Copy the server's recordings to this Mac as data/recordings/server/recordings.sqlite.
# Uses SQLite's online backup, so it's safe while the recorder is writing.
#   scripts/pull-recordings.sh <server-ip>
set -euo pipefail
HOST="${1:?usage: scripts/pull-recordings.sh <server-ip>}"
cd "$(dirname "$0")/.."
mkdir -p data/recordings/server
ssh "root@$HOST" "sqlite3 /opt/alt-scalp/data/recordings/recordings.sqlite '.backup /tmp/recordings-copy.sqlite'"
scp "root@$HOST:/tmp/recordings-copy.sqlite" data/recordings/server/recordings.sqlite
ssh "root@$HOST" rm -f /tmp/recordings-copy.sqlite
echo "saved data/recordings/server/recordings.sqlite"
echo "coverage: .venv/bin/altscalp --dir data/recordings/server status"
