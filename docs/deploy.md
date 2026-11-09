# Running the recorder on a cloud server

**Current setup (2026-11-09):** the recorder runs on the shared droplet `alt-arb`, not a separate server (HQ decision
2026-10-15). It was installed with `setup.sh` from a git bundle (`REPO_URL=<bundle>`), because the server's read-only
deploy key wasn't on GitHub yet. Its `origin` now points at GitHub, so `altscalp-update` pulls once the key
(user `altscalp`, `~/.ssh/id_ed25519.pub`) is added at https://github.com/idownham/alt-scalp/settings/keys/new
with write access OFF. Step 1 below (a separate server) is superseded.

The laptop can't record with the lid closed on battery: the first test window (2026-10-13) lost 20 minutes that way
(see `journal.md`). A small always-on server is the spec's fallback for missed windows. Cost: about $5–6/month.
Adapted from alt-arb's `docs/deploy.md`.

## What runs on the server

| Piece | What it does |
| - | - |
| `altscalp-recorder` (systemd) | Runs `altscalp record`; starts at boot, restarts 5 s after any crash |
| `altscalp-update` (systemd timer, every 15 min) | `git pull`. If *code* changed, runs the tests and restarts the recorder only if they pass, otherwise rolls back. **Skips entirely while a game window is open or opens within 5 min**, so an update never puts a gap in a recording |
| `chrony` | Keeps the clock synced (snapshot timestamps are evidence) |
| Read-only deploy key | The server can read this one repo and nothing else; it can't push |

Data stays on the server in `/opt/alt-scalp/data/recordings/recordings.sqlite`.

## Steps

1. **Create a server** (Ian does this: it needs an account and payment). It must be a **separate** server from
   alt-arb's, so the two projects' Kalshi reads come from different IPs (CLAUDE.md rule 6). For example,
   DigitalOcean Basic $6/mo or Hetzner CPX11. Choose:
   - Image: **Ubuntu 24.04**
   - Region: **US East** (Kalshi is a US exchange)
   - Authentication: **SSH key**. Add your Mac's public key (`cat ~/.ssh/id_ed25519.pub`).
2. **Run the setup script** from the alt-scalp folder on your Mac:
   ```bash
   scp deploy/setup.sh root@<server-ip>:
   ssh root@<server-ip> bash setup.sh
   ```
3. **Add the deploy key.** The first run prints a public key and stops. Add it at
   https://github.com/idownham/alt-scalp/settings/keys/new with **Allow write access OFF**, then run
   `ssh root@<server-ip> bash setup.sh` again. It installs everything, runs the tests, and starts the recorder.
4. **Check that it's recording** after the next window opens (`altscalp status` below).
5. **Then stop the laptop recorder**, so there's one source of truth:
   `launchctl unload ~/Library/LaunchAgents/com.idownham.altscalp.recorder.plist`

## Day to day

```bash
ssh root@<server-ip> journalctl -u altscalp-recorder -f                    # live log
ssh root@<server-ip> 'cd /opt/alt-scalp && sudo -u altscalp .venv/bin/altscalp status'
ssh root@<server-ip> journalctl -u altscalp-update --since today           # what auto-update did
scripts/pull-recordings.sh <server-ip>                                      # copy recordings to the Mac
.venv/bin/altscalp --dir data/recordings/server status                      # coverage of the copy
```

Tested 2026-10-13: `setup.sh` (with `SKIP_SYSTEMD=1`) ran cleanly in an `ubuntu:24.04` container. All tests passed,
and `schedule`/`record`/`status` worked against the live API. The systemd units weren't tested in the container.
