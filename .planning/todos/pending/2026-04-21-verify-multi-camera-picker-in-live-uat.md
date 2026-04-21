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
