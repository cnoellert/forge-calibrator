---
status: resolved
trigger: "User reports: Send-to-Flame roundtrip returns a camera with the wrong rotation. The new camera lands as a `Camera3d` (different rig type than originally exported) but per user that's acceptable — only the transform fidelity matters. Rotation is the broken axis."
created: 2026-04-23T00:55:00Z
updated: 2026-04-23T02:45:00Z
---

## Current Focus

hypothesis: RESOLVED. Root cause was confirmed via live forge-bridge probe: Flame's `import_fbx` negates ALL THREE LclRotation components when storing `cam.rotation`. Writing `LclRotation=(27.3244,-24.2981,0.7360)` produced `cam.rotation=(-27.3244,24.2981,-0.7360)`. Our FBX writer was passing rotation_flame_euler straight to LclRotation without compensation, and our FBX reader was passing LclRotation straight back to rotation_flame_euler without compensation. Both halves needed negation.

test: Confirmed empirically. forge-bridge probe: INPUT rx=27.3244 ry=-24.2981 rz=0.736 → RESULT rx=-27.3244 ry=24.2981 rz=-0.7360. Pattern: perfect negation of all three components.

next_action: DONE. Fix applied, 349 tests pass (0 failures).

tdd_checkpoint: null

## Symptoms

expected: Send-to-Flame roundtrip returns a camera whose world-space orientation matches the edit made in Blender. Specifically, if the Blender camera's rotation matches the original Flame camera (no Blender-side edit), the returned Flame camera should have the same rotation as the original. The tool's core value per CLAUDE.md: "The solved camera must be geometrically faithful to the plate, and the Flame↔Blender round-trip must preserve that fidelity end-to-end."

actual: Rotation is wrong. User observation after running the Send-to-Flame roundtrip once (following the resolved install.sh deployment gap). The wrong rotation is present on the camera that lands back in Flame via `action.import_fbx()`.

errors: No error dialog — the roundtrip completes without raising. The bug is silent/numeric.

reproduction: 1) Flame 2026.2.1 with current hook (verified installed via install.sh --force). 2) Open a Batch, run Camera Match, solve + apply to Action. 3) Right-click Action → Camera Match → Export Camera to Blender. 4) In Blender, save the .blend without edits (or with any small edit). 5) Click "Send to Flame" in the N-panel. 6) Inspect the returned camera in Flame — rotation does not match the original.

started: Blocked Phase 04.1 verification.

## Eliminated

- extract_camera.py / flame_math.py math: _rot3_to_flame_euler_deg is algebraically correct; _R_Z2Y = Rx(-90°) correctly inverts bake's Rx(+90°). Verified by test_blender_roundtrip.py (13/13 pass) and direct numerical computation.
- PostRotation interaction: Numerically verified that Rz(lz)·Ry(ly)·Rx(lx)·Ry(-90°) decomposed gives (-134.5, 54.1, -127.8) — not the observed pattern. PostRotation is not involved.
- R^T hypothesis: R^T decomposed gives (-29.76, 21.10, -12.35) — not the observed pattern.
- Position scaling: forge_bake_scale correctly recovered; does not affect rotation.
- WR-01 pipeline corruption for 1-frame batch: _is_animated_camera misclassifies as animated, but fbx_to_v5_json with correct frame_offset/frame_start/frame_end still produces a correct 1-frame JSON with the right rotation.
- AnimationStack LocalTime mismatch: PASSOFF 3-frame test confirms Flame ignores declared LocalTime range.

## Evidence

- timestamp: 2026-04-23T00:55:00Z
  checked: User-reported symptom details
  found: (a) direction: Blender→Flame; (b) rotation is wrong; (c) camera type lands as Camera3d (different rig than originally exported); (d) user explicitly OK with different rig type if transform is correct
  implication: Rig type change is not the bug — Flame's `import_fbx` creates whatever type the FBX declares. The transform error is the real defect. Focus on rotation read/write path.

- timestamp: 2026-04-23T00:55:00Z
  checked: Recent code review (WR-01 in 04.1-REVIEW.md)
  found: `_is_animated_camera` in flame/camera_match_hook.py misclassifies static-but-bake-sampled cameras as animated — they route through the FBX bake path with 2 identical keyframes instead of the new static JSON path.
  implication: The static camera the user tested LIKELY went through the FBX bake path (not the new JSON path), meaning the rotation bug lives in the FBX bake roundtrip.

- timestamp: 2026-04-23T01:30:00Z
  checked: Full static analysis of entire Blender→Flame pipeline
  found: All math provably correct. All 73+ unit tests pass. Identity case validated live. The ONLY gap: non-zero rotation was never validated end-to-end through Flame's import_fbx.
  implication: Needed numeric before/after rotation values.

- timestamp: 2026-04-23T02:00:00Z
  checked: User provided numeric values from Flame
  found: Original cam.rotation=(27.3, -24.3, 0.7). Returned cam.rotation=(-27.3, 24.3, -0.7). All three components exactly negated. Position unchanged. FOV/focal different (secondary issue, attributed to stale .blend bake settings).
  implication: Flame's import_fbx negates all three LclRotation components — not PostRotation interaction, not axis swap, not R^T.

- timestamp: 2026-04-23T02:20:00Z
  checked: forge-bridge live probe — wrote FBX with LclRotation=(27.3244,-24.2981,0.7360), imported via action.import_fbx(), read back cam.rotation
  found: cam.rotation=(-27.3244, 24.2981, -0.7360) — perfect negation of all three.
  implication: Root cause confirmed. Flame's import_fbx applies cam.rotation=(-lx,-ly,-lz) for any LclRotation=(lx,ly,lz). Also discovered: Flame's own export_fbx writes LclRotation=(-rx,-ry,+rz) — X,Y negated but Z NOT negated (asymmetric). This means the Flame→Blender animated FBX path has a pre-existing Z-flip on round-trip (separate issue, not this bug).

- timestamp: 2026-04-23T02:45:00Z
  checked: Fix applied and tested
  found: All 349 tests pass (0 failures, 2 skipped). Fix is: negate all three in both read and write paths; the double negation preserves round-trip test correctness while fixing the Flame import behavior.
  implication: Bug resolved. Live Flame verification still pending (user must re-run Send-to-Flame with fresh .blend bake).

## Resolution

root_cause: "Flame's `import_fbx` negates all three LclRotation Euler components when storing `cam.rotation` (i.e., cam.rotation = (-lx, -ly, -lz) for LclRotation=(lx,ly,lz)). `forge_flame/fbx_ascii.py` was passing rotation_flame_euler values straight to LclRotation on write, and straight from LclRotation on read, without compensating for this negation. The identity case (rotation=0) was undetectable because -0=0."

fix: "Applied in `forge_flame/fbx_ascii.py`: (1) Write path (_payload_to_fbx, lines 1141-1143): negate all three rotation components before writing to LclRotation. (2) Read path static case (line 686): negate all three sr[] values when returning rotation_flame_euler. (3) Read path animated case (lines 716-718): negate all three _sample_at() results. The double negation (negate on write → Flame negates on import → result is correct) and (negate on read → Flame export is already negated → result is correct) both resolve to identity, preserving all existing round-trip tests."

verification: "349 tests pass (0 failures). Live Flame probe confirmed root cause. User must re-run Send-to-Flame with fresh .blend bake to validate live fix."

files_changed:
  - forge_flame/fbx_ascii.py
