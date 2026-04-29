---
created: 2026-04-29T18:30:00Z
title: In-UI Blender binary picker / persisted override (env+glob escape hatch)
status: backlog
priority: low
area: ui-hook
files:
  - flame/camera_match_hook.py  # add settings/preferences pane or status-line tooltip with "Browse for Blender..." affordance
  - forge_flame/blender_bridge.py  # accept a config-file override path alongside FORGE_BLENDER_BIN
---

## Problem

`resolve_blender_bin()` now covers the 95% case via `FORGE_BLENDER_BIN` plus a glob+expanduser default table:

- macOS: `/Applications/Blender.app/...`, `/Applications/Blender*.app/...`,
  `~/Applications/Blender.app/...`, `~/Applications/Blender*.app/...`
- Linux: `/usr/bin/blender`, `/usr/local/bin/blender`, `/opt/blender/blender`,
  `/opt/blender-*/blender`, `~/Apps/blender-*/blender`

Power users on weird install layouts (custom prefixes, network-mounted Blender bundles, multiple coexisting major versions where the highest sort isn't the one they want) currently have to set `FORGE_BLENDER_BIN` from a shell before launching Flame. That works but is unfriendly — most VFX artists don't edit shell rc files, and Flame's environment isn't always inherited from the user's interactive shell anyway (depends on launcher).

This todo captures the harder follow-up: surface the resolved path in the calibrator UI and let the user override it via "Browse for Blender..." without leaving Flame.

## Suggested affordance

Two non-exclusive options, in increasing implementation cost:

1. **Status-line tooltip / read-only field.** When a Blender-bound action runs (Export / Import Camera to/from Blender), show the resolved binary path in the dialog or in a transient status string. Even read-only, this gives the user immediate diagnostic info ("oh, it picked 4.4 instead of 4.5"). Cheap.

2. **"Browse for Blender..." in a settings pane.** Add a small Preferences/Settings entry to the FORGE menu (or a gear icon on the calibrator window) with a `QFileDialog`-driven binary picker. Persist the override to `.planning/config.json` (or whatever per-host config we adopt) so it survives Flame restarts. Resolution order becomes:

   `$FORGE_BLENDER_BIN` → config-file override → glob defaults → PATH

   The config file lives alongside the existing `.planning/config.json` (auto-launch focus-steal preference is already stored there per Phase 04.4 decision).

## Out of scope for the current milestone

- The env+glob defaults already cover a clean install on flame-01 (RHEL 9) and any standard macOS workstation. UAT on flame-01 cold-install is the gate that decides whether this todo gets promoted.
- Revisit when tester feedback shows env var + glob defaults aren't enough, or when we need per-host overrides for shared-fs sites where `$FORGE_BLENDER_BIN` propagation is awkward.
