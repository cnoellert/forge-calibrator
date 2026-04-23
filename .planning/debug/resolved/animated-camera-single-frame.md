---
status: resolved
trigger: "User reports: Animated cameras appear to only bake a single frame when passed to Blender from Flame. Expected multi-frame animation to land in Blender; only one frame of motion survives the export."
created: 2026-04-23T12:00:00Z
updated: 2026-04-23T12:30:00Z
---

## Current Focus

hypothesis: CONFIRMED. `_is_animated_camera()` in `flame/camera_match_hook.py` was always returning `False` due to a wrong API call, silently routing every animated camera through the static single-frame JSON path.

Root cause: The probe called `action.export_fbx(path=scratch_fbx, cameras=[cam], bake_animation=True)`. Flame's C-extension does NOT accept a `cameras=` keyword argument — only `only_selected_nodes`, `bake_animation`, `pixel_to_units`, `frame_rate`, `export_axes`. This caused a `TypeError` which was caught by the outer `except Exception: return False`, making `_is_animated_camera` always return `False`. All cameras (static and animated) were then routed through the static-JSON path which emits exactly 1 frame by design.

Also fixed: the probe's frame-count threshold was `>= 2`, but static cameras baked with `bake_animation=True` also produce 2 frames (pre-roll + trailing artifact, per flame_fbx_bake_semantics.md). Threshold corrected to `> 2` so static cameras are correctly identified as static.

next_action: DONE — fix applied and verified GREEN.

reasoning_checkpoint: null
tdd_checkpoint: null

## Symptoms

expected: Right-clicking an animated Action camera (multi-keyframe — e.g. a camera with a 20-frame position/rotation animation) → Camera Match → Export Camera to Blender should produce a `.blend` in which the Blender camera has the same N frames of animation as the original Flame camera. The tool's core value per CLAUDE.md: "The solved camera must be geometrically faithful to the plate, and the Flame↔Blender round-trip must preserve that fidelity end-to-end."

actual: The Blender camera ends up with only a SINGLE frame after the export. The animation is lost/flattened. Observation from live Flame 2026.2.1 test on 2026-04-23.

errors: No error dialog — the export completes without raising. The bug is silent/numeric (just missing frames).

reproduction: 1) Flame 2026.2.1 with current HEAD installed (via install.sh --force — confirm install is current before probing). 2) Open a Batch, create an Action with a multi-keyframe animated camera (not a Camera Match solve — this could be a manually keyed camera or any camera with >1 distinct keyframe per channel). 3) Right-click the animated Action → Camera Match → Export Camera to Blender. 4) Open the resulting `.blend` in Blender. 5) Inspect the camera's animation — expected N frames, actual 1 frame.

started: Observed 2026-04-23 after Phase 04.1 execution completed and rotation hotfix (commit 49bbe43) landed. Likely regression from Phase 04.1 Plan 02's new detect-and-route (introduced `_is_animated_camera`, added the static JSON path that can now silently consume an animated camera). Pre-04.1-02 code always went through the FBX bake path, which handled animated cameras correctly.

## Eliminated

- Rotation bug (fixed in 49bbe43, live-verified and pinned by TestFlameRotationNegationContract). Frame count is independent of the rotation negation fix.
- frame_rate mismatch (23.976 vs 24fps): not the cause. Even with wrong frame_rate, 10 distinct KTimes still produce 10 distinct integer frames at any reasonable fps.
- frame_start/frame_end clipping in probe: not the cause. The probe doesn't clip, which means ALL frames from the bake survive into `frames`. The real cause was upstream — `export_fbx` never ran at all.

## Evidence

- timestamp: 2026-04-23T12:00:00Z
  checked: User-reported symptom + live test result
  found: Animated Flame camera → Export Camera to Blender → resulting .blend has only 1 frame of animation.
  implication: The new static-JSON path added in 04.1-02 is being taken for an actually-animated camera.

- timestamp: 2026-04-23T12:00:00Z
  checked: Cross-reference with WR-01 in 04.1-REVIEW.md
  found: WR-01 flagged that `_is_animated_camera` misclassifies *static* cameras as animated. The *reverse* is the actual regression.
  implication: The probe's design weakness is confirmed but the specific bug is the API call shape, not the frame-count threshold alone.

- timestamp: 2026-04-23T12:15:00Z
  checked: Source code of `_is_animated_camera` lines 1756-1760 (pre-fix)
  found: `action.export_fbx(path=scratch_fbx, cameras=[cam], bake_animation=True)` — `cameras=` is not a valid kwarg for Flame's `action.export_fbx`. The correct pattern (from `fbx_io.export_action_cameras_to_fbx`) is to set `action.selected_nodes.set_value([cam])` then call `action.export_fbx(scratch_fbx, only_selected_nodes=True, bake_animation=True)`.
  implication: TypeError raised on every probe call → caught by outer except → return False → all cameras go through static path.

- timestamp: 2026-04-23T12:20:00Z
  checked: RED test H7 (new) with _StrictFakeAction that rejects cameras= kwarg
  found: Both H7 tests FAIL RED — export_fbx_calls is empty (TypeError was caught, function returned False).
  implication: Bug reproduced in unit test, confirming root cause.

- timestamp: 2026-04-23T12:25:00Z
  checked: GREEN after fix — correct API call with only_selected_nodes=True + new forge_fbx_animated.fbx fixture (3-frame camera, TX animates 0→100→200)
  found: Both H7 tests PASS GREEN. Full suite: 354 passed, 2 skipped (was 352 + 2 before).
  implication: Fix is correct and doesn't break any existing tests.

## Resolution

root_cause: `_is_animated_camera` in `flame/camera_match_hook.py` called `action.export_fbx(path=scratch_fbx, cameras=[cam], bake_animation=True)`. Flame's C-extension `export_fbx` does not accept a `cameras=` kwarg — only `only_selected_nodes`, `bake_animation`, `pixel_to_units`, `frame_rate`, `export_axes`. This caused a TypeError on every invocation, which was silently caught by `except Exception: return False`, making the function always return False and route every animated camera through the static single-frame JSON path.

fix: Two changes to `_is_animated_camera` (flame/camera_match_hook.py lines ~1776-1782): (1) replaced `action.export_fbx(path=scratch_fbx, cameras=[cam], bake_animation=True)` with the correct pattern: `action.selected_nodes.set_value([cam]); action.export_fbx(scratch_fbx, only_selected_nodes=True, bake_animation=True)` wrapped in a try/finally that restores prior selection. (2) Corrected the frame-count threshold from `>= 2` to `> 2` because static cameras baked with `bake_animation=True` always produce exactly 2 frames (pre-roll + trailing artifact). New 3-frame animated FBX fixture added at `tests/fixtures/forge_fbx_animated.fbx`.

verification: 2 new RED→GREEN tests (H7) in `tests/test_hook_export_camera_to_blender.py::TestIsAnimatedCameraProbeApiContract`. Full suite: 354 passed, 2 skipped. Rotation negation contract (TestFlameRotationNegationContract) still passes. Static camera path unchanged (returns False when probe yields <= 2 frames).

files_changed:
  - flame/camera_match_hook.py  # _is_animated_camera: correct export_fbx API call + threshold
  - tests/test_hook_export_camera_to_blender.py  # add H7 RED→GREEN tests
  - tests/fixtures/forge_fbx_animated.fbx  # new 3-frame animated camera fixture
