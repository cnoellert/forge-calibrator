# Seamless Flame↔Blender bridge

## Overview

The seamless bridge connects three moving parts to close the Flame↔Blender round-trip
without requiring the artist to return to Flame's batch menu for the return leg. The
Flame hook (`camera_match_hook.py`) bakes the Action camera to a `.blend` file when the
artist right-clicks the Action. forge-bridge runs as a local HTTP endpoint
(`127.0.0.1:9999`) inside Flame's Python, starting automatically when Flame boots. The
Blender "Send to Flame" addon (N-panel → Forge tab) posts the edited camera back to the
target Action in a single click.

The user-facing flow: right-click Action → Export Camera to Blender → edit camera in
Blender → click Send to Flame → the updated camera appears in the target Action with
keyframes preserved. No alt-tab to Flame's batch menu for the return trip.

## Install

### For pipeline TDs

**One-time:** create the forge conda env from the repo recipe:

```bash
conda env create -f forge-env.yml
# or, if `forge` already exists with stale deps:
conda env update -f forge-env.yml --prune
```

The env carries Python 3.11 + numpy + opencv-python (cv2 for Camera-Match
overlay rendering, numpy for the solver). `install.sh` looks for it at
`$HOME/miniconda3/envs/forge` by default; override with
`FORGE_ENV=<absolute path> ./install.sh`.

**Per machine:** run `./install.sh` from the repo root. The installer performs
preflight checks before deploying anything:

- forge conda environment (`$FORGE_ENV`, defaults to `~/miniconda3/envs/forge`)
- Wiretap CLI at `/opt/Autodesk/wiretap/tools/current/wiretap_rw_frame`
- PyOpenColorIO from Flame's bundled Python at `/opt/Autodesk/python/`
- OCIO config resolvable under `/opt/Autodesk/colour_mgmt/configs/`

When the installer prints `> forge_core + forge_flame`, it is copying the
host-agnostic solver and Flame-specific adapters to
`/opt/Autodesk/shared/python/forge_core/` and `/opt/Autodesk/shared/python/forge_flame/`.

When it prints `> forge-bridge`, it is deploying the bridge hook to
`/opt/Autodesk/shared/python/forge_bridge/`. If forge-bridge deployment fails (network
unavailable, no local clone), the installer emits the warning in recipe 4 below and
continues — VP-solve and the static camera round-trip still work.

When it prints `> Install`, it is placing the Camera Calibrator hook at
`/opt/Autodesk/shared/python/camera_match/`.

When it prints `> tools/blender`, it is copying Blender bake and extract scripts to
`/opt/Autodesk/shared/python/tools/blender/`.

**Offline / air-gapped installs:** set `FORGE_BRIDGE_REPO=<path-to-local-clone>` before
running `./install.sh` to point the bridge installer at a local copy. Set
`FORGE_BRIDGE_VERSION` to pin the bridge version.

`install.sh` is idempotent — safe to re-run against an already-installed workstation
without `--force`.

### For artists

1. In Blender: Edit → Preferences → Add-ons → Install from file → select
   `tools/blender/forge_sender-v1.3.4.zip` from your forge-calibrator checkout.
2. Enable **Forge: Send Camera to Flame** in the Add-ons list.
3. Open the 3D viewport's N-panel (press N) — you should see a **Forge** tab with a
   **Send to Flame** button.
4. Confirm the addon panel reports version `1.3.4`. (Older v1.0.x / v1.1.x / v1.2.x
   builds carried bugs — Phase 04.3's aim-rig rotation fix shipped in v1.2.0;
   Phase 04.4's choose-Action dropdown + collision-guard hot-fix ships in v1.3.4.)
5. No further setup required. forge-bridge starts automatically when Flame boots.

## How forge-bridge autostart works

When Flame starts, it loads the Camera Calibrator hook (`camera_match_hook.py`). The hook
spawns `forge_bridge.py` as a subprocess, which binds `127.0.0.1:9999`. The bridge
lifecycle is tied to the Flame session — when Flame quits, the bridge subprocess exits.
No launchd, systemd, or manual process management is needed.

The bridge is only accessible locally. It binds `127.0.0.1` and is never exposed on
the network.

No user action is required to start or stop the bridge. Restarting Flame is the only
way to restart a crashed bridge. Hook changes also require a Flame restart to take
effect (Flame captures menu callbacks at load time; dynamic reload does not refresh
them).

To confirm the bridge is reachable after Flame boots:

```
curl -s http://localhost:9999/ -o /dev/null -w "%{http_code}\n"
# expect: 200
```

## Using Send to Flame

1. In Flame: right-click the target Action → FORGE → Camera → **Export Camera to
   Blender**. Blender opens with the baked camera. No dialog prompts, no save-path
   selection. (Or: right-click a Camera node directly inside the Action's
   schematic → FORGE → Camera → Export Camera to Blender — bypasses the picker
   when the Action has multiple cameras.)
2. In Blender: edit the camera — move it, rotate it, scrub or add keyframes.
3. Open the N-panel (N key) → **Forge** tab → click **Send to Flame**.
4. If the camera was originally baked from a Flame Action, it ships back to that
   same Action automatically (the bake stamps `forge_bake_action_name` /
   `forge_bake_camera_name` into the .blend's custom properties). For
   never-baked cameras, a dialog appears: pick a target Action from the
   dropdown, or choose `-- Create New --` and type a name.
5. On success, a popup reads `Sent to Flame: camera <name> in Action <action-name>`.
   The updated camera appears in the target Action in Flame with keyframes preserved.

You never have to return to Flame's batch menu to trigger the import. If the popup
shows an error instead of the success message, see [Troubleshooting](#troubleshooting)
below.

## Multi-camera Apply Camera flow

When the line-tool calibration window is open and the target Action contains 2+
non-Perspective cameras, clicking **Apply Camera** surfaces a FORGE-styled picker
dialog (em-dash window title `FORGE — Select Camera`, double-click-to-accept,
Enter accepts, Escape cancels). The dialog uses the FORGE palette (#282c34
background, #E87E24 accent) — no Qt default `QInputDialog` appears anywhere in
the hook flow.

When the Action has 0 or 1 non-Perspective cameras, no dialog appears.

## Troubleshooting

### Symptom: Send to Flame: forge-bridge not reachable at http://127.0.0.1:9999 — is Flame running with the Camera Calibrator hook loaded?

**Likely cause:** Flame is not running, or forge-bridge did not start when Flame
booted.

**Fix:**
1. Confirm Flame is running.
2. Probe the bridge: `curl -s http://localhost:9999/ -o /dev/null -w "%{http_code}\n"` — expect `200`.
3. If the probe returns non-200 or fails, restart Flame (the bridge starts as a
   Flame-spawned subprocess).

---

### Symptom: Flame SIGSEGVs on the very first Send to Flame after a fresh Flame launch

**Likely cause:** Flame's `importToActionFBX` C++ path appears to have a race when
called as the first significant Flame API operation after boot. The crash
signature is `signal = 11 / SIGSEGV / invalid permissions for mapped object`
near the import call. The FBX content is innocent — the same byte-for-byte FBX
imports cleanly on subsequent attempts in the same session. Reproduced
2026-04-25 across multiple cold-install verification runs.

**Workaround:** Don't make Send to Flame the first thing you do after Flame
boots. Open a batch, click a node or two, let the workspace fully load
(15–30 s after the splash screen disappears) before triggering the round-trip.

**Recovery if it crashes:**
1. Restart Flame.
2. Open the batch with your aim-rig camera.
3. Do any small UI action (open a node, scrub the timeline) — this seems to
   stabilise Flame's internal state.
4. Right-click the Action → FORGE → Camera → Export Camera to Blender, then
   Send to Flame from Blender. The second attempt typically succeeds.

This is suspected to be an Autodesk-side bug, not a forge-calibrator bug. The
math layer is verified correct end-to-end: returned camera matches original
within 0.001° per axis on Camera1 fixtures (well inside the 0.1° UAT gate).

---

### Symptom: Send to Flame: active camera is missing 'forge_bake_action_name' — this camera was not baked by forge-calibrator. Re-export from Flame via right-click → FORGE → Camera → Export Camera to Blender

**Likely cause:** The active Blender camera was not baked from Flame, or was baked by
an older tool that does not stamp metadata. (The error may name
`'forge_bake_camera_name'` instead — the missing-key slot surfaces whichever stamped
property is absent first.)

**Fix:**
1. In Flame: right-click the target Action → FORGE → Camera → Export Camera to Blender.
2. Use the freshly baked camera in Blender; the stamped metadata is attached
   automatically.

---

### Symptom: Send to Flame failed: {error}

{traceback}

**Likely cause:** The Flame-side import crashed, the FBX parse failed, or the target
Action was renamed or deleted after the bake.

**Fix:**
1. Read the top line of the traceback — it names the underlying error.
2. Most common cause: the Action was renamed after the bake. Re-bake from the current
   Action (right-click Action → FORGE → Camera → Export Camera to Blender).
3. Second most common: the Action has two cameras with the same name. Rename one to
   disambiguate, then re-send.

---

### Symptom: [WARN] forge-bridge install skipped (sibling installer exited non-zero). VP-solve and v6.2 static round-trip still work.

**Likely cause:** `install.sh` could not find a local forge-bridge clone AND the
curl-fallback to `raw.githubusercontent.com` failed (usually offline or firewalled).

**Fix:**
- If you have a local forge-bridge clone: `FORGE_BRIDGE_REPO=<path-to-clone> ./install.sh`
- If you have network access: ensure `raw.githubusercontent.com` is reachable, then
  re-run `./install.sh`.
- VP-solve and the v6.2 static-camera round-trip continue to work without the bridge;
  only Send to Flame is affected.

---

### Symptom: Send to Flame: forge-bridge not reachable at http://127.0.0.1:9999 — is Flame running with the Camera Calibrator hook loaded? (and `lsof -i :9999` shows a non-forge-bridge process listening)

**Likely cause:** Another process — a stale forge-bridge from a previous Flame session
that did not shut down cleanly, or an unrelated service — is holding port 9999.

**Fix:**
1. Find the PID: `lsof -i :9999`
2. Kill it: `kill <pid>`
3. Restart Flame — the bridge starts cleanly on the freed port.
4. If the conflict recurs, check for a second Flame instance running on the same
   workstation.

---

### Symptom: Camera-node right-click on a Camera 3D shows no FORGE → Camera menu

**Likely cause:** Pre-Phase-04.4 builds filtered cameras by exact-string match
`item.type == "Camera"`, which excluded the `"Camera 3D"` type variant — the
menu silently never appeared on 3D-camera right-clicks.

**Fix:** Update to v6.3 (Phase 04.4 or later). The post-fix filter uses an
explicit allowlist `("Camera", "Camera 3D")` in both
`_scope_action_camera` and `_first_camera_in_action_selection`. After
`./install.sh` and Flame restart, the menu surfaces on both Camera and
Camera 3D right-clicks.

---

### Symptom: Right-click → Export Camera to Blender → "Failed to write FBX: 'NoneType' object is not callable"

**Two distinct causes** share this error signature; rule out both before
escalating.

**Cause A — stale `__pycache__`:** Pre-260427 builds of `install.sh` only
purged `camera_match/__pycache__`, not the sibling `forge_core/` and
`forge_flame/` pycaches. Flame would load stale `.pyc` files for
`forge_flame.fbx_io` even after a clean re-install, masking source updates
and surfacing as a misleading NoneType error inside the export pipeline.

**Fix:** Update to v6.3 (Phase 04.4 or later). The current `install.sh` runs
a recursive `__pycache__` purge across all three sibling trees on every
deploy. Existing installs can be force-cleaned manually:

```bash
find /opt/Autodesk/shared/python/forge_flame /opt/Autodesk/shared/python/forge_core \
    -name __pycache__ -type d -exec rm -rf {} +
# then restart Flame
```

**Cause B — `PyActionFamilyNode` wrapper:** When right-clicking a Camera
inside an Action's schematic, Flame can occasionally expose the containing
Action as `PyActionFamilyNode` (a base-class wrapper that lacks
`export_fbx`). The post-Phase-04.4 fast-path filter in
`_first_camera_in_action_selection` detects this — it requires
`callable(getattr(parent, "export_fbx", None))` before accepting
`cam.parent` as the resolution result. If the broken proxy is detected,
the helper falls through to the `flame.batch.nodes` scan, which usually
returns the healthy `PyActionNode` for the same name.

**If you still see the error** after upgrading to v6.3 and re-installing,
do a full Flame restart. The `PyActionFamilyNode` exposure can be a
transient state from an earlier crash; a clean Flame boot consistently
resolves it.

---

[back to README](../README.md)
