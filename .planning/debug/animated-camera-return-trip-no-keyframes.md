---
status: investigating
trigger: "User reports: After the animated-camera Flame→Blender fix (3d9e8b2) landed and was verified live, the return trip (Blender→Flame via Send to Flame) produces a camera in Flame with no keyframes — only a static pose, even though the Blender camera has the full N-frame animation."
created: 2026-04-23T13:00:00Z
updated: 2026-04-23T13:00:00Z
---

## Current Focus

hypothesis: `tools/blender/extract_camera.py` reads the Blender camera's current-frame transform only (e.g. `cam.matrix_world`, `cam.data.lens` at the current scene frame) and emits a single-frame v5 JSON. Blender's fcurves — the authoritative source for keyframed animation — are not being walked to produce multi-frame samples.

Alternative hypotheses:
- `extract_camera.py` DOES walk fcurves, but an off-by-one or frame-range bug produces a degenerate frames list
- `v5_json_str_to_fbx` receives a correctly-multi-framed payload but fails to write AnimCurveNode connections for animated rotation/position, so Flame's `import_fbx` sees only the static `Lcl Rotation` + `Lcl Translation` defaults and creates a non-keyed camera
- `action.import_fbx` in Flame requires additional FBX structure (e.g. AnimationStack `LocalTime` must match the curve KTime range) to create keyframes on the action camera — the existing path works for Flame's own export_fbx round-trips but not for our synthesized FBX

test: 1) Read `tools/blender/extract_camera.py` and confirm whether it walks fcurves or samples the current frame only. 2) Read `forge_flame/fbx_ascii.py::v5_json_str_to_fbx` and trace how multi-frame payloads write AnimCurves. 3) Check whether the animated FBX fixture (`tests/fixtures/forge_fbx_animated.fbx`) round-trips through v5_json_str_to_fbx correctly at the unit level. 4) Look for evidence in `bake_camera.py` or Blender scripts of how keyframes are meant to be preserved. 5) If extract_camera.py is single-frame, check whether there's a separate "extract with keyframes" path that isn't being called.

expecting: Most likely finding — `extract_camera.py` samples current frame only, with no fcurve walk. Fix will be to iterate scene frames (or walk fcurves directly), build per-frame v5 JSON entries, and emit the full frames list.

next_action: Read `tools/blender/extract_camera.py` and confirm single-frame vs. multi-frame semantics. Then read `transport.py::_BLENDER_SIDE_TEMPLATE` (or equivalent) to see which extract path is invoked from the Send-to-Flame flow.

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

## Evidence

- timestamp: 2026-04-23T13:00:00Z
  checked: User-reported symptom after 3d9e8b2 live verification
  found: Animated camera successfully reaches Blender with all frames; Send-to-Flame returns the camera to Flame without any keyframes.
  implication: The animated-data path breaks on the Blender→Flame direction. The three candidate locations are extract_camera.py (Blender-side JSON emission), v5_json_str_to_fbx (Flame-side JSON→FBX conversion), and action.import_fbx (Flame's FBX consumer). The first candidate is most likely since it's the least-tested of the three (v5_json_str_to_fbx has round-trip tests for multi-frame data; extract_camera.py tests focus on static cameras per test_extract_camera.py).

## Resolution

root_cause:
fix:
verification:
files_changed: []
