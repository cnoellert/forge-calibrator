---
quick_id: 260512-sudo-install-env
status: complete
date: 2026-05-12
---

# Fix install.sh sudo env detection

## Goal

Make `install.sh` correctly find the developer's conda `forge` environment when the script is run with elevated privileges to write into `/opt/Autodesk/shared/python/`.

## Diagnosis

Running `./install.sh --dry-run --yes` as the normal user passes every preflight on this machine. The likely failing path is `sudo ./install.sh`, where `$HOME` can become `/var/root` and `PATH` can lose the user's miniconda entries. That makes the installer look for `/var/root/miniconda3/envs/forge` or fail `command -v conda`, even though `/Users/cnoellert/miniconda3/envs/forge` exists.

## Scope

- Update `install.sh` only.
- Preserve explicit `FORGE_ENV=...` overrides.
- Add dry-run verification for a simulated sudo environment.
