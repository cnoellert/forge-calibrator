---
status: resolved
trigger: "`baked.json: no frames in JSON` error is still firing on Export Camera to Blender for a static camera, despite plan 04.1-02 claiming to close it via `_is_animated_camera()` detect-and-route"
created: 2026-04-22T23:05:00Z
updated: 2026-04-23T00:40:00Z
resolved: 2026-04-23T00:40:00Z
---

## Current Focus

hypothesis: CONFIRMED. The installed Flame hook is an older version that does not contain the detect-and-route code from 04.1-02. `install.sh` was last run at 13:10 on 2026-04-22, but the fix commits were merged at 16:13 on the same day. The installed file and the dev file are out of sync.
test: Checked `/opt/Autodesk/shared/python/camera_match/camera_match.py` for `_is_animated_camera` — not present. Verified installed file timestamp (13:10) predates merge commit `e708944` (16:13).
expecting: Running `install.sh --force` and restarting Flame will cause the static camera to route through `camera_io.export_flame_camera_to_json` and succeed.
next_action: Run `./install.sh --force` and restart Flame.
reasoning_checkpoint: null
tdd_checkpoint: null

## Symptoms

expected: Clicking `Action → Camera Match → Export Camera to Blender` on a static (non-animated) camera should succeed. Plan 04.1-02 claimed to close this bug by adding `_is_animated_camera()` detect-and-route that sends static cameras through `camera_io.export_flame_camera_to_json` (JSON path, no bake) and animated cameras through the FBX+bake path.

actual: Flame shows error dialog:
```
Blender bake failed (exit 1):

/bin/sh: nvidia-smi: command not found
/var/folders/30/.../T/forge_bake_8ed596zt/baked.json: no frames in JSON

Intermediate files preserved at:
/var/folders/30/.../T/forge_bake_8ed596zt
```

The `no frames in JSON` path indicates `bake_camera.py` (or the preservation pipeline) is still being called on a payload that lacks a `frames` key — i.e. the static path is NOT being taken, or the static path still routes through bake.

errors: "Blender bake failed (exit 1)" with `baked.json: no frames in JSON`. Preceded by `/bin/sh: nvidia-smi: command not found` — harmless macOS diagnostic but may indicate the Blender subprocess startup env.

reproduction: In Flame 2026.2.1 (fresh boot), open a Batch, load a plate (1920x1080 @ 16fps per screenshot), run Camera Match, solve VP, apply to Action. Right-click the Action → Camera Match → Export Camera to Blender. The static camera (no keyframes) triggers the bake failure instead of the static JSON path.

started: Error persisted AFTER merging phase 4.1 plan 02 (commits `d72ab7d..4c3ba47`) into main via `e708944` on 2026-04-22. Phase 4 also had this as an open issue (`test(04): record live-run finding — Test 1 blocked by Phase 4.1 item #2` at 5ef9046), which is what 04.1-02 was supposed to close.

## Eliminated

- The dev file `flame/camera_match_hook.py` at HEAD DOES have the correct detect-and-route code (`_is_animated_camera`, static JSON branch, animated FBX branch). The implementation is correct.
- `camera_io.export_flame_camera_to_json` always produces `"frames": [one_entry]` — it cannot produce empty frames.
- `bake_camera.py` is correct — it raises "no frames in JSON" when `frames` is empty/absent, which is the right behavior.
- The unit tests (9/9 passing) confirm the hook module logic is correct when loaded from the dev file.

## Evidence

- timestamp: 2026-04-22T23:05:00Z
  checked: whether preserved intermediate files at `/var/folders/30/.../T/forge_bake_8ed596zt/` still exist
  found: `$TMPDIR/forge_bake_*` — no matches. macOS scrubbed the tmp dir between Flame sessions (user restarted Claude).
  implication: Cannot inspect the failing `baked.json` directly. Must reason from code + reproduce to capture fresh artifacts.

- timestamp: 2026-04-22T23:05:00Z
  checked: 04.1-02-SUMMARY.md claim for route logic
  found: SUMMARY claims `_is_animated_camera()` + `_resolve_flame_project_fps_label()` were added and that "static cameras route through `camera_io.export_flame_camera_to_json` (closing the `baked.json: no frames in JSON` bug) and animated cameras through the existing FBX path".
  implication: Either (a) the implementation disagrees with the claim, (b) the implementation is correct but the classification is wrong for this camera, or (c) the static JSON path still feeds bake_camera.py downstream.

- timestamp: 2026-04-23T00:30:00Z
  checked: whether `_is_animated_camera` is present in the INSTALLED hook at `/opt/Autodesk/shared/python/camera_match/camera_match.py`
  found: NOT present. Grepping for `_is_animated_camera`, `detect-and-route`, `static branch`, `is_animated` returns no matches.
  implication: The installed file is an older pre-04.1-02 version. Flame is running old code.

- timestamp: 2026-04-23T00:30:00Z
  checked: file timestamps — installed hook vs merge commit
  found: Installed `camera_match.py` modified at `Apr 22 13:10`. Merge commit `e708944` (chore: merge executor worktree, which brought the detect-and-route code to main) landed at `2026-04-22 16:13:18`. The install predates the fix by 3+ hours.
  implication: `install.sh` was NOT re-run after merging 04.1-02. The fix code exists on disk but was never deployed to Flame.

- timestamp: 2026-04-23T00:30:00Z
  checked: installed hook's `_export_camera_to_blender` path around the FBX bake
  found: Installed version (around line 2108) calls `fbx_io.export_action_cameras_to_fbx` unconditionally for ALL cameras (no detect-and-route branch). For a static camera with 0 keyframes, Flame's `bake_animation=True` emits only the pre-roll KTime 0 (no real per-frame keyframes). After `frame_start` filtering drops the pre-roll, `frames` becomes empty. `bake_camera.py` then raises "no frames in JSON".
  implication: The deployed code never had the fix. The symptom is reproducible and expected from the installed version.

## Resolution

root_cause: The installed Flame hook (`/opt/Autodesk/shared/python/camera_match/camera_match.py`, modified 2026-04-22 13:10) is 3+ hours older than the fix commits merged into main via `e708944` at 16:13 on the same date. `install.sh` was not re-run after the merge. Flame is executing the pre-fix code that routes all cameras through the FBX bake path, which produces empty `frames` for a static (zero-keyframe) camera.
fix: Run `./install.sh --force` from the repo root to sync `flame/camera_match_hook.py` (and `forge_flame/`, `forge_core/`, `tools/blender/`) to `/opt/Autodesk/shared/python/`, then restart Flame. The detect-and-route code in the dev file is correct and unit-tested (9/9 passing).
verification: User ran `./install.sh --force` + Flame restart + retried Export Camera to Blender on the static camera. Confirmed working 2026-04-23T00:40:00Z ("approved. Appears to be working").
files_changed: []
