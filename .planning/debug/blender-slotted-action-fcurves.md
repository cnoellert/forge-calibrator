---
status: investigating
trigger: "After the Takes LocalTime fix (45fb7fd) landed and install.sh --force was run, user re-tested Blender→Flame and still got no keyframes on the returned camera. Blender→Flame animation is still being dropped despite the Takes fix being confirmed installed in /opt/Autodesk/shared/python/forge_flame/fbx_ascii.py."
created: 2026-04-23T14:45:00Z
updated: 2026-04-23T14:45:00Z
---

## Current Focus

hypothesis: The Blender add-on's `_camera_keyframe_set` in `tools/blender/forge_sender/flame_math.py` walks `cam.animation_data.action.fcurves` directly. In Blender 4.4+ (user is on 4.5), newly-created actions use the "slotted actions" data model — fcurves live under `action.slots[slot_handle].fcurves` (or `action.layers[0].strips[0].channelbag(slot).fcurves` in the internal layered-action model). `action.fcurves` is maintained as a backward-compat shim but may return an empty collection when the action was created by `keyframe_insert()` on Blender 4.4+ because those actions are slotted.

If `_camera_keyframe_set` sees empty fcurves, it falls back to `scene.frame_current` — producing a single-frame payload. Multi-frame animation is then never sent to Flame.

Evidence this is plausible:
- Existing tests for `build_v5_payload` (`tests/test_forge_sender_flame_math.py`) use `_FakeCamera` with `animation_data = None` — they only exercise the fallback path, never the fcurve walk.
- Recent Takes LocalTime fix (45fb7fd) addresses a real downstream bug (we verified LocalTime was hard-coded to 1 frame), but if the incoming payload is already single-frame, Takes LocalTime is a moot point.
- User live-verified that `bake_camera.py` produces animated .blend files (keyframes visible in Blender). So the keyframes DO exist in the action. The question is how to read them in 4.4+.

Alternative hypotheses (less likely given the evidence):
- The Blender add-on zip (v1.0.0, Apr 21) the user reinstalled is substantially stale (transport.py only, not flame_math.py — already confirmed identical to source). Ruled out.
- Flame's `import_fbx` needs something beyond Takes LocalTime (e.g. AnimationStack connections). Possible but should only bite if a correct multi-frame FBX reaches it, and we can't know that without confirming the payload itself is multi-frame first.

test: 1) Confirm `_camera_keyframe_set` only walks `action.fcurves`. 2) Research Blender 4.4+ slotted-actions API for the correct way to enumerate keyframes. 3) Patch `_drain` to also walk slots/layers and re-test.

expecting: Patching `_drain` to iterate both `action.fcurves` and `action.slots[*].fcurves` (or equivalent) will produce a multi-frame payload, and combined with the Takes LocalTime fix already shipped, the Blender→Flame animated roundtrip will finally work end-to-end.

next_action: Read Blender 4.4+ slotted-actions docs (via WebSearch or context7 if MCP available). Write a defensive `_drain` that tries both legacy `action.fcurves` and slotted `action.slots[*].fcurves` (or whichever API is correct in 4.5), plus unit tests covering the slotted-action path using a `_FakeAction` fixture with populated slots.

reasoning_checkpoint: null
tdd_checkpoint: null

## Symptoms

expected: User sends an animated camera back from Blender via Send-to-Flame. Camera lands in Flame with all N keyframes.

actual: Camera lands in Flame with no keyframes (static pose only), even after install.sh --force and Blender addon reinstall. Both the rotation fix (49bbe43), the _is_animated_camera fix (3d9e8b2), and the Takes LocalTime fix (45fb7fd) are deployed and live-verified at the installed file level.

errors: Silent — no traceback or warning.

reproduction: Flame 2026.2.1 + Blender 4.5 + current HEAD. Export animated camera Flame→Blender (works end-to-end post-3d9e8b2). Click Send to Flame in addon. Returned camera in Flame has no keys.

started: 2026-04-23 during live UAT after all three prior hotfixes deployed. Likely a pre-existing bug in `_camera_keyframe_set` exposed now that the upstream chain (_is_animated_camera, Takes LocalTime) works correctly — earlier tests may have been routing animated data through the FBX bake path (bypassing Blender-side extraction), so `_camera_keyframe_set`'s slotted-action blind spot was never hit in live flow.

## Eliminated

- Takes LocalTime hard-coded — fixed in 45fb7fd, verified installed (/opt/Autodesk/shared/python/forge_flame/fbx_ascii.py matches source as of 14:30).
- `_is_animated_camera` API call shape — fixed in 3d9e8b2.
- Rotation sign convention — fixed in 49bbe43.
- Install.sh deployment gap — Flame-side fbx_ascii.py IS current per direct file comparison.
- Blender addon zip drift — only transport.py differs (instrumentation + stereo filter additions); flame_math.py is identical in both.

## Evidence

- timestamp: 2026-04-23T14:45:00Z
  checked: Direct comparison of installed fbx_ascii.py vs source
  found: `diff forge_flame/fbx_ascii.py /opt/Autodesk/shared/python/forge_flame/fbx_ascii.py` returns no output — identical. Takes LocalTime fix IS deployed.
  implication: The Takes fix didn't solve the problem, so the bug is not in LocalTime. The payload arriving at Flame is likely single-frame upstream — focus shifts to the Blender-side payload construction.

- timestamp: 2026-04-23T14:45:00Z
  checked: `tools/blender/forge_sender/flame_math.py::_camera_keyframe_set` (lines 80-102)
  found: Walks `anim.action.fcurves` directly. Falls back to `scene.frame_current` if fcurves are empty or action is None.
  implication: In Blender 4.4+, `action.fcurves` may be empty for actions created by `keyframe_insert()` due to the slotted-actions data model. If so, every Blender→Flame export would get `scene.frame_current` only — a single frame.

- timestamp: 2026-04-23T14:45:00Z
  checked: Existing tests for `build_v5_payload`
  found: All use `animation_data = None` — they exercise only the fallback path, never the fcurve walk.
  implication: Zero unit coverage for the actual fcurve iteration. The bug would never be caught by the existing test suite.

## Resolution

root_cause:
fix:
verification:
files_changed: []
