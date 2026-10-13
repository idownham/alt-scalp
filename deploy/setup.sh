#!/bin/bash
# One-time setup of the alt-scalp recorder on a fresh Ubuntu 24.04 server. Run as root:
#
#   scp deploy/setup.sh root@<server-ip>:   then:   ssh root@<server-ip> bash setup.sh
#
# Safe to re-run. The first run creates a read-only GitHub deploy key, prints it, and stops;
# add it to the repo (Settings -> Deploy keys, leave "Allow write access" OFF), then re-run.
# Adapted from alt-arb deploy/setup.sh @ 594878f.
#
# REPO_URL overrides the clone source; SKIP_SYSTEMD=1 skips service install (used for testing).
set -euo pipefail

REPO_URL="${REPO_URL:-git@github.com:idownham/alt-scalp.git}"
APP=/opt/alt-scalp
USER_HOME=/home/altscalp
# GitHub's published SSH host key (docs.github.com "GitHub's SSH key fingerprints"), pinned so
# the first connection can't be intercepted. If GitHub rotates it, update this line.
GITHUB_HOST_KEY="github.com ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl"

as_app() { runuser -u altscalp -- "$@"; }
step() { printf '\n==> %s\n' "$*"; }

[ "$(id -u)" = 0 ] || { echo "run as root (sudo bash setup.sh)" >&2; exit 1; }

step "Installing system packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-venv git sqlite3 openssh-client chrony >/dev/null
# Snapshot timestamps are the evidence; keep the clock synced.
systemctl enable --now chrony >/dev/null 2>&1 || true

step "Creating the 'altscalp' service user"
id altscalp >/dev/null 2>&1 || useradd --system --create-home --home-dir "$USER_HOME" --shell /usr/sbin/nologin altscalp
mkdir -p "$APP" && chown altscalp:altscalp "$APP"

if [[ "$REPO_URL" == git@github.com:* ]]; then
  step "GitHub deploy key"
  install -d -m 700 -o altscalp -g altscalp "$USER_HOME/.ssh"
  grep -qxF "$GITHUB_HOST_KEY" "$USER_HOME/.ssh/known_hosts" 2>/dev/null || echo "$GITHUB_HOST_KEY" >> "$USER_HOME/.ssh/known_hosts"
  chown altscalp:altscalp "$USER_HOME/.ssh/known_hosts"
  [ -f "$USER_HOME/.ssh/id_ed25519" ] || as_app ssh-keygen -q -t ed25519 -N "" -C "alt-scalp server (read-only deploy key)" -f "$USER_HOME/.ssh/id_ed25519"
  if ! as_app git ls-remote "$REPO_URL" >/dev/null 2>&1; then
    echo
    echo "GitHub doesn't accept this server's key yet. Add it as a READ-ONLY deploy key:"
    echo "  https://github.com/idownham/alt-scalp/settings/keys/new"
    echo "  Title: alt-scalp server     Allow write access: OFF     Key:"
    echo
    cat "$USER_HOME/.ssh/id_ed25519.pub"
    echo
    echo "Then run this script again."
    exit 2
  fi
fi

step "Fetching the code"
if [ -d "$APP/.git" ]; then
  as_app git -C "$APP" pull --ff-only --quiet
else
  as_app git clone --quiet "$REPO_URL" "$APP"
fi

step "Building the Python environment"
[ -x "$APP/.venv/bin/python" ] || as_app python3 -m venv "$APP/.venv"
as_app "$APP/.venv/bin/python" -m pip install --quiet --upgrade pip
as_app "$APP/.venv/bin/python" -m pip install --quiet -e "$APP[dev]"
chmod +x "$APP/deploy/update.sh"

step "Running the offline tests"
(cd "$APP" && as_app "$APP/.venv/bin/python" -m pytest -q -p no:cacheprovider)

if [ "${SKIP_SYSTEMD:-0}" = 1 ]; then
  step "SKIP_SYSTEMD=1: not installing services"
  exit 0
fi

step "Installing and starting services"
cp "$APP"/deploy/*.service "$APP"/deploy/*.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now altscalp-recorder.service altscalp-update.timer
sleep 5
systemctl --no-pager --lines=5 status altscalp-recorder.service || true

cat <<EOF

Done. The recorder is running and will survive reboots.
  Logs:          journalctl -u altscalp-recorder -f
  Coverage:      cd $APP && sudo -u altscalp .venv/bin/altscalp status
  Auto-updates:  every 15 min, never while a game window is open (journalctl -u altscalp-update)
EOF
