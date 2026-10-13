#!/bin/bash
# Pull the latest commit; restart the recorder only if code changed AND the tests pass.
# Run as root every 15 minutes by altscalp-update.timer. Adapted from alt-arb deploy/update.sh @ 594878f.
#
#   a game window is open (or opens within 5 min) -> do nothing; try again next run
#   docs only              -> pull, nothing to restart
#   code changed, tests ok -> reinstall, restart the recorder
#   code changed, tests fail -> roll the checkout back so disk matches the running code
set -euo pipefail

APP=/opt/alt-scalp
as_app() { runuser -u altscalp -- "$@"; }

if (cd "$APP" && as_app "$APP/.venv/bin/altscalp" busy); then
  echo "a game window is open or about to open; not updating now"
  exit 0
fi

before=$(as_app git -C "$APP" rev-parse HEAD)
as_app git -C "$APP" pull --ff-only --quiet
after=$(as_app git -C "$APP" rev-parse HEAD)
[ "$before" = "$after" ] && exit 0
echo "pulled ${before:0:7} -> ${after:0:7}"

if as_app git -C "$APP" diff --quiet "$before" "$after" -- src pyproject.toml deploy; then
  echo "docs-only change; nothing to restart"
  exit 0
fi

as_app "$APP/.venv/bin/python" -m pip install --quiet -e "$APP[dev]"
if ! (cd "$APP" && as_app "$APP/.venv/bin/python" -m pytest -q -p no:cacheprovider); then
  echo "tests FAILED at ${after:0:7}; rolling back to ${before:0:7}, recorder keeps running" >&2
  as_app git -C "$APP" reset --hard --quiet "$before"
  as_app "$APP/.venv/bin/python" -m pip install --quiet -e "$APP[dev]"
  exit 1
fi

if ! as_app git -C "$APP" diff --quiet "$before" "$after" -- deploy/*.service deploy/*.timer; then
  cp "$APP"/deploy/*.service "$APP"/deploy/*.timer /etc/systemd/system/
  systemctl daemon-reload
  echo "reinstalled systemd units"
fi
systemctl restart altscalp-recorder
echo "tests passed; recorder restarted on ${after:0:7}"
