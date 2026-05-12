---
quick_id: 260512-sudo-install-env
status: complete
date: 2026-05-12
---

# Fix install.sh sudo env detection

## Summary

`install.sh` now resolves the default forge conda env from the invoking user when run via `sudo`, instead of blindly using the current `$HOME`. This avoids false failures where the script looks under `/var/root/miniconda3/envs/forge` even though the env exists under the artist or developer account.

The installer also searches common miniconda/anaconda locations in the invoking user's home, so a sudo-stripped `PATH` no longer causes a false "conda not found" preflight failure.

## Files Changed

- `install.sh`

## Verification

- `bash -n install.sh`
- `./install.sh --dry-run --yes`
- `env -i HOME=/var/root USER=root SUDO_USER=cnoellert PATH=/usr/bin:/bin:/usr/sbin:/sbin ./install.sh --dry-run --yes`
