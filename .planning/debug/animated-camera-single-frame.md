---
status: investigating
trigger: "User reports: Animated cameras appear to only bake a single frame when passed to Blender from Flame. Expected multi-frame animation to land in Blender; only one frame of motion survives the export."
created: 2026-04-23T12:00:00Z
updated: 2026-04-23T12:00:00Z
---

## Current Focus

hypothesis: `_is_animated_camera()` in `flame/camera_match_hook.py` is returning `False` for a genuinely animated camera, so the detect-and-route sends the camera through the NEW static JSON path (`camera_io.export_flame_camera_to_json`) — which emits a single-frame JSON payload by design. The animated FBX bake path (which should handle multi-frame) is being bypassed.

Why would `_is_animated_camera()` return False for an animated camera? Most likely the probe's `fbx_to_v5_json` call uses the default `frame_rate="23.976 fps"` and no `frame_start`/`frame_end` clipping args, then interprets the result. Per the pre-roll semantics in `memory/flame_fbx_bake_semantics.md`, `export_fbx(bake_animation=True)` emits pre-roll at KTime 0 + trailing artifact at KTime end+1; both must be clipped with `frame_start`/`frame_end` to match batch range. If the probe doesn't clip them, it gets the pre-roll + 1 real frame + trailing — which might misinterpret to fewer "distinct" frames than expected in some configurations.

An alternative hypothesis: the probe's default frame_rate causes the KTime->frame conversion to round samples into the same integer frame, effectively collapsing N real frames to 1 "frame" in `len(frames)`.

Related: WR-01 in 04.1-REVIEW.md flagged that `_is_animated_camera` misclassifies static cameras as *animated* (bake always produces ≥2 frames). The reverse failure — animated misclassified as static — is the WR-01 inverse that wasn't specifically called out but shares the same probe-design weakness.

test: 1) Read `flame/camera_match_hook.py::_is_animated_camera` carefully — trace what its probe actually produces. 2) Check what values (frame_rate, frame_start, frame_end) it passes to `fbx_to_v5_json`. 3) Compare with what `_export_camera_to_blender`'s downstream FBX call passes. 4) Write a unit test that simulates a 10-frame animated camera's FBX output and asserts `_is_animated_camera` returns True — this will fail red, revealing the probe's specific failure mode. 5) Check `tools/blender/bake_camera.py` as well — confirm that when the static JSON path fires, the resulting .blend ends up with 1 frame (which matches symptom).

expecting: Either (a) `_is_animated_camera` probe is missing frame_start/frame_end clipping, rounding multi-frame animation down to 1 frame in the probe, causing `len(frames) < 2` and misclassification as static; or (b) `_is_animated_camera` works correctly and the bug is downstream in the animated FBX bake path itself (e.g. bake_camera.py losing frames).

next_action: Read `_is_animated_camera` and trace the probe path. Write a red test reproducing the 10-frame-collapses-to-1-frame symptom.

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

## Evidence

- timestamp: 2026-04-23T12:00:00Z
  checked: User-reported symptom + live test result
  found: Animated Flame camera → Export Camera to Blender → resulting .blend has only 1 frame of animation.
  implication: The new static-JSON path added in 04.1-02 is being taken for an actually-animated camera, OR the FBX bake path is dropping frames. The former is more likely given the detect-and-route was the new piece of 04.1-02 and the static JSON path is known to emit exactly 1 frame by design.

- timestamp: 2026-04-23T12:00:00Z
  checked: Cross-reference with WR-01 in 04.1-REVIEW.md
  found: WR-01 flagged that `_is_animated_camera` misclassifies *static* cameras as animated (probe always yields ≥2 frames from Flame's bake_animation=True pre-roll semantics). The *reverse* — animated misclassified as static — was not specifically called out but is a plausible failure mode of the same probe-design weakness.
  implication: The probe's specific behavior for an animated camera (is it always ≥2 frames? does it round sample times to collapse frames?) needs to be traced carefully. The hypothesis is that frame_rate/frame_start/frame_end defaults cause a real N-frame animation to yield `len(frames) < 2` in the probe output.

## Resolution

root_cause:
fix:
verification:
files_changed: []
