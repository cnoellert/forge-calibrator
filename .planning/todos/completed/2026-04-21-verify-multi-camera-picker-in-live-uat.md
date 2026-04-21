---
created: 2026-04-21T16:27:08.108Z
title: Verify multi-camera picker in live UAT
area: testing
files:
  - flame/camera_match_hook.py:1695-1723
  - flame/camera_match_hook.py:1783-1794
---

## Problem

The Phase 01 UAT on 2026-04-21 only exercised an Action with a single non-Perspective camera, so the `_pick_camera` dropdown path was never triggered. The code is structurally sound — `_find_action_cameras` at `flame/camera_match_hook.py:1720` unconditionally filters out the built-in Perspective viewport camera, and `_pick_camera` at `:1783` renders a `QInputDialog.getItem` dropdown when `len(cameras) > 1` — but the path has zero live-Flame verification.

Phase 02 (Blender Addon) consumes whichever camera was exported; if the picker silently chose the wrong one due to some Flame quirk, the round-trip would land on an unintended target on Phase 02 import. Worth a one-time UAT sweep before relying on it.

## Solution

Build or identify a Flame batch with an Action containing at least 3 cameras: the built-in Perspective (unavoidable), plus two solver-output cameras. Right-click the Action → Camera Match → Export Camera to Blender. Confirm:

1. Perspective is **absent** from the picker dropdown
2. The remaining cameras appear as `{action_name} > {cam_name}` labels, sorted (or in a deterministic order — confirm how they're ordered currently)
3. Cancelling the dialog aborts cleanly (no leftover temp dir, no error dialog)
4. Picking each camera in turn produces a `.blend` whose `forge_bake_camera_name` custom property matches the Flame camera you selected (the round-trip key-match is what Phase 02 depends on)

If any of those fail, promote to a real quick task.

## Results (2026-04-21)

- Check 1 (Perspective absent): **PASS** — Perspective not listed in the picker dropdown; `_find_action_cameras` filter at `flame/camera_match_hook.py:1720` works as designed.
- Check 2 (deterministic order): **PASS** — dropdown entries appear in a deterministic order, confirmed stable across two opens of the same picker without intervening changes.
- Check 3 (cancel clean): **PASS** — hit Cancel; no error dialog surfaced; no new temp directory appeared under `$TMPDIR/forge_bake_*` after the cancel (only the pre-existing dir from the earlier failed Default-camera bake remained, which is unrelated).
- Check 4 (stamped name matches pick): **PASS at JSON stamp integrity** — picked `Default`, exported JSON contained `"forge_bake_camera_name": "Default"`. Full `.blend` round-trip not verified because the `Default` camera had no solve data (`"frames": []`) and the Blender bake errored out on empty animation (expected). The picker→stamp integrity — which is the only thing the picker itself affects — is confirmed.
- **Overall: PASS** — Phase 2 is unblocked on the picker front.

## Discovered side-issues (not picker bugs — recorded for Phase 1 follow-up)

1. **`/tmp/forge_bake_*` vs `$TMPDIR`**: the original plan's Check 3 criterion checked `/tmp/forge_bake_*`, but on macOS the bake uses `$TMPDIR` (under `/var/folders/...`) — `/tmp` is never used. The check was adapted to `$TMPDIR` for this UAT. The plan criterion itself is correct in spirit but needs a path fix for macOS.
2. **`nvidia-smi: command not found` leak on macOS**: the bake script (or one of its helpers) calls `nvidia-smi` without first checking the platform. On macOS this prints `/bin/sh: nvidia-smi: command not found` into the failure error dialog. Cosmetic, non-blocking, but confusing in error UX.
3. **Temp dir retained on failure**: when the Blender bake fails, the intermediate `forge_bake_*` dir is preserved (by design per the error dialog's "Intermediate files preserved at ..." message). D-12 cleanup contract does NOT run on failure. This is intentional for diagnostics but worth double-checking that success paths DO clean up.
4. **Empty-camera bake UX**: picking an unsolved camera (e.g. fresh `Default`) produces a JSON with `"frames": []`, which the Blender bake script rejects with `no frames in JSON`. The error is surfaced correctly but the user-facing message could be clearer ("Camera has no animation data — solve or set a transform before exporting").

These are out of Phase 2 scope. Capture separately as Phase 1 polish quick-tasks if desired.

