---
created: 2026-05-02T01:44:50Z
title: UAT round-trip parity for the Flame↔Blender scaling chain (next session)
area: roundtrip
files:
  - flame/camera_match_hook.py:2767-2795 (the picker wrappers)
  - flame/scale_picker_dialog.py (the dialog)
  - tools/blender/bake_camera.py:380 (pos / scale divisor — the central correctness property)
  - tools/blender/extract_camera.py (consumes forge_bake_scale custom property for the inverse)
  - tools/blender/forge_sender/flame_math.py (Send-to-Flame side, version-tolerant fcurves walk)
  - forge_flame/fbx_ascii.py:1008 (fbx_to_v5_json with flame_to_blender_scale kwarg)
related_commits:
  - 9265f86 (feat: hardcode flame_to_blender_scale=100.0 + plumb kwarg through fbx_to_v5_json)
  - 6200771 (feat: 5-stop ladder menu — superseded by knl)
  - 699c601 (feat: scale picker dialog)
  - d926810 (fix: sys.modules lookup for _FORGE_SS — install rename)
  - <pending — quick 260501-rus commits land before this UAT runs>
status: pending
---

## Problem

Today's session shipped a substantial Flame↔Blender scaling chain — JSON contract field, ladder validator, hook integration, dialog UI, install-rename fix. Unit tests are green (522/0/2 with bit-exact position parity at all 5 ladder stops + float-epsilon rotation parity), but the **full end-to-end with real Flame + real Blender** has only been partially exercised:

**What WAS verified live this session:**
- Single static export at scale=100 (shown in Flame success dialog: `action1 > Default`, 1-frame, .blend opened)
- The dialog renders, ESC works (after the install-rename fix)

**What was NOT verified live:**
- **Bake → Send-to-Flame round-trip parity** — the central correctness property. Position must return to the original Flame coords within tolerance after the divide-on-bake, multiply-on-extract chain. Unit tests prove this in numpy; never confirmed in real Blender → real Flame.
- **Non-default scale values** through the dialog (`0.01x`, `0.1x`, `1x`, `10x`)
- **Animated cameras** — multi-keyframe round-trip (only 1-frame static was confirmed)
- **ESC/cancel doesn't leave bad state** — no orphan .blend, no orphan Blender process
- **Default-button parity** (Enter on the highlighted 100x button) vs explicit click on 100x
- **Camera-node surface** — right-click on Camera inside Action's schematic (the i31 surface that survived knl's revert)

If anything is broken, the most likely failure mode is the inverse asymmetry: `bake_camera.py:380` does `pos / scale`; extract reads the stamped `forge_bake_scale` custom property and applies the inverse. Any mismatch (e.g., extract using the wrong property name, the property not being stamped, or the hook passing the scale to fbx_to_v5_json but the bake script not seeing it) would surface as cameras landing at wrong Flame positions on round-trip — visually obvious because the Action camera would jump.

## Solution

Run the following 6 UAT items in sequence next session, before declaring the scaling work shippable:

### UAT 1: Static round-trip at default scale (Interior · ×10³) — REGRESSION HEADLINE

1. In Flame, find a batch with an Action containing a static camera (the one the artist tested today works)
2. Right-click Action → Camera Match → Camera → "Export Camera to Blender"
3. Dialog opens with `Interior · ×10³` highlighted as default
4. Hit **Enter** (or click `Interior · ×10³` explicitly) → Blender opens with the camera at room-scale (~1.8 m back for the reference 4096-wide plate; the studio sweet spot for human-scale interiors)
5. In Blender, **without touching anything**, run "Send to Flame" (forge_sender addon)
6. Back in Flame: the returned camera should land at the **same** Flame coords as the original Action camera (position, rotation, focal length)
7. Verification: visually confirm cameras overlap in the Flame Action viewport, OR query the position attributes via /exec to assert `np.isclose(returned, original, atol=1e-3)`

**FAIL CRITERIA:** if the returned camera lands at a different position, the divide/multiply asymmetry is broken. Most likely: extract isn't reading `forge_bake_scale` correctly, or the bake didn't stamp it.

### UAT 2: Static round-trip at non-default scale (Landscape · ×10⁰)

Same flow as UAT 1, but pick `Landscape · ×10⁰` from the dialog. Camera should land at landscape scale (~1.8 km back for the 4096-wide reference plate). Send-to-Flame should still return to original Flame coords. This proves the symmetry holds at a value other than the studio default — different scale values exercise the same code path with different numbers, so a bug in property-stamping logic might only surface at non-Interior values.

### UAT 3: Animated camera round-trip

1. Pick an Action with a multi-keyframe camera (10+ frames)
2. Export at scale=1000 (default dialog pick — Interior)
3. Verify Blender shows animated camera with all keyframes at the right positions
4. Send back to Flame
5. Verify all keyframes land at the original Flame positions AND the timing (frame numbers) is preserved

**FAIL CRITERIA:** keyframes land at scrambled positions, OR frame numbers shift, OR keyframes are missing. The fcurves walk in `tools/blender/forge_sender/flame_math.py` (260429-gde fix) should handle this, but it hasn't been exercised against the new scaling code path.

### UAT 4: ESC/cancel hygiene

1. Right-click Action → "Export Camera to Blender" → dialog opens
2. Hit **ESC** immediately
3. Verify: no .blend file created in `~/forge-bakes/`, no Blender process spawned (`pgrep blender` empty), no error in Flame's message log
4. Re-open the dialog, pick a button → verify the cancel didn't poison subsequent picks (next pick fires export normally)

### UAT 5: Default-button parity (Enter vs explicit click)

1. Click "Export Camera to Blender" → dialog opens with `Interior · ×10³` highlighted
2. Hit **Enter** (uses the default-button shortcut)
3. Note the .blend output path
4. Re-export the same camera, click `Interior · ×10³` explicitly with the mouse
5. Diff the two .blend files (`diff` won't work — they're binary; instead compare camera position/rotation in Blender or via bpy script). Should be byte-identical (same scale, same source camera, same code path).

### UAT 6: Camera-node surface

The i31 work added the dialog to BOTH the Action right-click AND the Camera-node right-click (inside the Action's schematic). knl reverted the menu but kept the camera-scope wrapper.

1. Open an Action's schematic view (double-click the Action node, or however Flame exposes it)
2. Right-click on a Camera node INSIDE the schematic (not the Action node itself)
3. Verify: the same single "Export Camera to Blender" entry appears (no `@ Nx` siblings)
4. Click it → same dialog → pick a scale → verify the export fires AND the resulting .blend is correct (same as UAT 1)

This is the surface that's been in the code since i31 but never hands-on-keyboard tested.

### UAT 7: Deprecated-stop back-compat (already-baked .blend round-trip)

The 260501-rus extension widened the canonical ladder to 7 semantic stops {1, 10, 100, 1000, 10000, 100000, 1000000} but kept {0.01, 0.1} as deprecated-but-valid bake-side inputs so .blend files baked under the old contract still round-trip cleanly.

1. Find a .blend baked before today (commit predates 260501-rus) — e.g. one of yesterday's bakes at scale=100 OR a hypothetical scale=0.1 bake from 260501-dpa testing. The `forge_bake_scale` custom property on the Blender camera names the original divisor.
2. Open it in Blender, run "Send to Flame" (forge_sender addon)
3. Verify: the returned camera lands at the original Flame coords. NO error about "scale not on the allowed ladder" — extract reads the stamped property and applies the inverse without re-validating against the canonical set.

**FAIL CRITERIA:** Send-to-Flame errors with "0.01 not on ladder" or "0.1 not on ladder" — would mean the deprecated-stop tolerance broke and existing artist .blend files are now stranded.

(NOTE: this UAT can be deferred or skipped if the studio has no live .blend files at deprecated scales. The unit-test parity coverage for deprecated stops in tests/test_blender_roundtrip.py is sufficient automated guard.)

## Resume signal

When UAT runs, capture results in a small note file (or as comments in this todo). If all 6 pass, move this todo to `.planning/todos/completed/` with status `closed_uat_passed`. If any fail, file a new todo for the specific failure mode and reference the commit that introduced the bug.
