---
status: resolved
trigger: "User reports: After the animated-camera Flame→Blender fix (3d9e8b2) landed and was verified live, the return trip (Blender→Flame via Send to Flame) produces a camera in Flame with no keyframes — only a static pose, even though the Blender camera has the full N-frame animation."
created: 2026-04-23T13:00:00Z
updated: 2026-04-23T14:30:00Z
---

## Current Focus

hypothesis: RESOLVED — root cause confirmed in `forge_flame/fbx_ascii.py::_mutate_template_with_payload`. The `Takes` section `LocalTime` and `ReferenceTime` fields were never updated from the template's hard-coded single-frame value.

Alternative hypotheses:
- `extract_camera.py` DOES walk fcurves, but an off-by-one or frame-range bug produces a degenerate frames list — ELIMINATED: extract_camera.py delegates to flame_math.build_v5_payload which walks fcurves correctly via _camera_keyframe_set
- `v5_json_str_to_fbx` receives a correctly-multi-framed payload but fails to write AnimCurveNode connections for animated rotation/position — ELIMINATED: AnimCurves written correctly; the problem was the Takes time range
- `action.import_fbx` in Flame requires additional FBX structure (e.g. AnimationStack `LocalTime` must match the curve KTime range) — CONFIRMED: this is the mechanism, but the bug is on our write side

test: Confirmed via static analysis + RED tests: `_mutate_template_with_payload` built correct AnimCurve arrays for all frames but left Takes::Take::LocalTime and Takes::Take::ReferenceTime at the template value (KTime for 1 frame at 23.976fps = 1926347345). Flame's import_fbx clips any keyframe with KTime > LocalTime end, so only frame 0 or 1 survived.

expecting: Fix: update LocalTime and ReferenceTime to ktime_from_frame(last_frame, frame_rate) at the end of _mutate_template_with_payload.

next_action: COMPLETE — fix applied, 5 new tests GREEN, full suite 359 passed / 2 skipped.

reasoning_checkpoint: null
tdd_checkpoint: null

## Symptoms

expected: After a user edits an animated camera's keyframes in Blender (or simply re-sends an already-animated camera back from Blender unchanged), clicking "Send to Flame" in the Blender addon should produce a camera in Flame with the same N frames of animation as the Blender camera. Per CLAUDE.md core value: geometric fidelity end-to-end on the round-trip.

actual: The camera lands in Flame with NO keyframes — only a static pose (likely frame-0 or current-frame values). The animation is lost on the Blender→Flame return trip.

errors: No error dialog or log output indicating a drop — silent/numeric failure.

reproduction: 1) Flame 2026.2.1 with HEAD installed via install.sh --force. 2) Open a Batch with an animated Action camera (multi-keyframe). 3) Right-click → Camera Match → Export Camera to Blender. 4) Verify the Blender camera has the full N-frame animation (✓ confirmed working after 3d9e8b2). 5) In Blender, optionally edit keys (or save unchanged). 6) Click "Send to Flame" in the N-panel. 7) Inspect the returned camera in Flame — it has no keys, only a static pose.

started: Observed 2026-04-23 immediately after live-verification of the animated-camera-single-frame fix (3d9e8b2). The Flame→Blender direction now works end-to-end for animated cameras; this is purely a return-trip defect. Could be a pre-existing bug (the pre-04.1-02 code would have routed animated-return through the same path, but Phase 02 verification focused on static cameras per VERIFICATION.md).

## Eliminated

- Flame→Blender direction for animated cameras — confirmed working post-3d9e8b2 (user live-verified 2026-04-23).
- Rotation negation — fixed in 49bbe43, not related to frame count.
- `_is_animated_camera` probe — fixed in 3d9e8b2, only affects the Flame→Blender direction.
- `extract_camera.py` single-frame hypothesis — ELIMINATED: delegates to flame_math.build_v5_payload which correctly walks both cam.animation_data.action.fcurves and cam.data.animation_data.action.fcurves via _camera_keyframe_set.
- AnimCurve write path — ELIMINATED: _anim_curve_node_with_data produces correct multi-frame arrays; confirmed by existing round-trip tests.
- action.import_fbx bug — ELIMINATED: this function works correctly when given FBX with proper Takes time range; the bug was that our synthesized FBX had the wrong time range.

## Evidence

- timestamp: 2026-04-23T13:00:00Z
  checked: User-reported symptom after 3d9e8b2 live verification
  found: Animated camera successfully reaches Blender with all frames; Send-to-Flame returns the camera to Flame without any keyframes.
  implication: The animated-data path breaks on the Blender→Flame direction.

- timestamp: 2026-04-23T14:00:00Z
  checked: Static analysis of _mutate_template_with_payload in forge_flame/fbx_ascii.py (lines 1054-1229)
  found: The function updates Objects/AnimCurve nodes with correct per-frame KTime arrays but never touches the Takes section. The template's Takes::Take::LocalTime = 0,1926347345 (KTime for 1 frame at 23.976fps) was left unchanged. Flame's import_fbx uses LocalTime as the upper bound — keyframes beyond that KTime are silently discarded.
  implication: A 10-frame payload at 24fps would have KTimes up to 19244232500 (frame 10), but LocalTime cap of 1926347345 (frame ~1 at 23.976fps) means only the first frame survived import. Confirmed by running _mutate_template_with_payload and reading the Takes section: LocalTime stayed at 1926347345 regardless of payload frame count or frame_rate.

- timestamp: 2026-04-23T14:15:00Z
  checked: forge_fbx_animated.fbx fixture (the reference 3-frame animated FBX)
  found: Its LocalTime is 0,3852694690 (KTime for frame 2 at 23.976fps), correctly spanning the 3-frame range (frames 0, 1, 2). This confirms Flame reads LocalTime as the animation range boundary.
  implication: Fix must set LocalTime and ReferenceTime to ktime_from_frame(last_frame, frame_rate).

## Resolution

root_cause: >
  `forge_flame/fbx_ascii.py::_mutate_template_with_payload` did not update the
  `Takes::Take::LocalTime` and `Takes::Take::ReferenceTime` fields when writing
  a multi-frame payload. The template hard-codes these to the KTime for 1 frame
  at 23.976fps (1926347345). Flame's `import_fbx` treats LocalTime as the upper
  bound of the animation range — any keyframe with KTime > LocalTime end is
  silently discarded. For an N-frame camera where N > 1 (and especially at non-23.976fps
  frame rates), all frames after approximately frame 1 were dropped, leaving
  only the first-frame static pose.

fix: >
  Added a Takes section update at the end of `_mutate_template_with_payload`:
  after computing `times` (the list of KTime values for all payload frames),
  the function now walks `tree -> Takes -> Take -> LocalTime/ReferenceTime`
  and sets each node's end value to `times[-1]` (the KTime of the last frame),
  preserving the start value of 0. This ensures the FBX animation range spans
  the full set of keyframes in the payload.

verification: >
  5 new RED→GREEN tests in `TestWriterTakesLocalTime` (test_fbx_ascii.py):
  - A1: 10-frame payload at 24fps — LocalTime end = ktime_from_frame(10, "24 fps") = 19244232500
  - A2: ReferenceTime == LocalTime for 10-frame payload
  - B: single-frame payload at 24fps — LocalTime = ktime_from_frame(1, "24 fps") (not template's 23.976fps value)
  - C: 3-frame at 25fps — uses 25fps KTime, not hard-coded 24fps
  - D: frames [5, 10, 20] — LocalTime uses last frame (20), not frame count (3) or delta (15)
  Full suite: 359 passed, 2 skipped (was 354 + 2 skipped before this fix).
  All existing tests pass including TestFlameRotationNegationContract,
  TestIsAnimatedCameraProbeApiContract, static-camera round-trip tests.

files_changed:
  - forge_flame/fbx_ascii.py
  - tests/test_fbx_ascii.py
