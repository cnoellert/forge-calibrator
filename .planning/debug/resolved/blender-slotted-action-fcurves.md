---
status: resolved
trigger: "After the Takes LocalTime fix (45fb7fd) landed and install.sh --force was run, user re-tested Blender→Flame and still got no keyframes on the returned camera. Blender→Flame animation is still being dropped despite the Takes fix being confirmed installed in /opt/Autodesk/shared/python/forge_flame/fbx_ascii.py."
created: 2026-04-23T14:45:00Z
updated: 2026-04-23T16:30:00Z
---

## Current Focus

hypothesis: DISPROVEN. The original hypothesis (Blender 4.5 slotted-action `action.fcurves` returning empty) is incorrect. Live Blender 4.5 testing confirmed that `action.fcurves` returns the OB-slot fcurves via a backward-compat shim even for layered actions (`is_action_legacy: False`). The 7 object-level fcurves (location + rotation_quaternion) are correctly returned and `_camera_keyframe_set` correctly discovers frames. The Blender side of the pipeline is fine.

Actual root cause: `_mutate_template_with_payload` in `forge_flame/fbx_ascii.py` updates `Takes::LocalTime`/`ReferenceTime` (fixed in 45fb7fd) but leaves `GlobalSettings::TimeSpanStop` at the template's hardcoded value of `46186158000` (= frame 24 at 24 fps). Flame uses `TimeSpanStop` as a secondary clip boundary in addition to `LocalTime`. For VFX-style shot ranges (e.g. frames 1001–1024), every keyframe KTime exceeds `46186158000`, so ALL keyframes are silently dropped by Flame's importer — the camera arrives with no animation.

test: Verified via Python simulation: for frames 1001–1024 at 24fps, `ktime_from_frame(1001, '24 fps') = 1926347673250 > 46186158000`. The Takes fix correctly set LocalTime to `0,1970609408000` but TimeSpanStop stayed at `46186158000`. Any Flame clip of keyframes at min(LocalTime, TimeSpanStop) would drop all 1001–1024 keyframes.

expecting: Updating `GlobalSettings::TimeSpanStop = last_ktime` (same value as LocalTime end) in `_mutate_template_with_payload` will resolve the no-keyframes symptom for VFX-range shots.

next_action: DONE — fix applied and tested.

reasoning_checkpoint: null
tdd_checkpoint: null

## Symptoms

expected: User sends an animated camera back from Blender via Send-to-Flame. Camera lands in Flame with all N keyframes.

actual: Camera lands in Flame with no keyframes (static pose only), even after install.sh --force and Blender addon reinstall. Both the rotation fix (49bbe43), the _is_animated_camera fix (3d9e8b2), and the Takes LocalTime fix (45fb7fd) are deployed and live-verified at the installed file level.

errors: Silent — no traceback or warning.

reproduction: Flame 2026.2.1 + Blender 4.5 + current HEAD. Export animated camera Flame→Blender (works end-to-end post-3d9e8b2). Click Send to Flame in addon. Returned camera in Flame has no keys.

started: 2026-04-23 during live UAT after all three prior hotfixes deployed.

## Eliminated

- Takes LocalTime hard-coded — fixed in 45fb7fd, verified installed (/opt/Autodesk/shared/python/forge_flame/fbx_ascii.py matches source as of 14:30).
- `_is_animated_camera` API call shape — fixed in 3d9e8b2.
- Rotation sign convention — fixed in 49bbe43.
- Install.sh deployment gap — Flame-side fbx_ascii.py IS current per direct file comparison.
- Blender addon zip drift — only transport.py differs (instrumentation + stereo filter additions); flame_math.py is identical in both.
- Blender 4.5 slotted-action `action.fcurves` empty — DISPROVEN. Live Blender 4.5 testing showed legacy shim returns correct OB-slot fcurves. `_camera_keyframe_set` correctly discovers frames for VFX-range shots (1001-1024). See /tmp/inspect_fcurves2.py through /tmp/test_addon_context.py for test runs.

## Evidence

- timestamp: 2026-04-23T14:45:00Z
  checked: Direct comparison of installed fbx_ascii.py vs source
  found: Identical. Takes LocalTime fix IS deployed.
  implication: The Takes fix didn't solve the problem, so a second bug exists.

- timestamp: 2026-04-23T16:00:00Z
  checked: Live Blender 4.5 testing of `_camera_keyframe_set` via `action.fcurves` shim
  found: `action.fcurves` returns 7 OB-slot fcurves (location + rotation_quaternion) correctly. `action.is_action_legacy: False` but shim still works. `_camera_keyframe_set` returns correct frames [1001, 1012, 1024] for VFX-range shots. `build_v5_payload` produces correct 3-frame payload.
  implication: Original hypothesis is wrong. Blender side is fine. Bug is on Flame side.

- timestamp: 2026-04-23T16:15:00Z
  checked: `GlobalSettings::TimeSpanStop` in generated FBX for frames 1001-1024 at 24fps
  found: `TimeSpanStop: 46186158000` (template default = frame 24 at 24fps). First keyframe KTime for frame 1001 at 24fps = `1926347673250 > 46186158000`. ALL keyframes exceed TimeSpanStop.
  implication: Flame clips keyframes at `min(LocalTime, TimeSpanStop)`. Takes LocalTime was fixed but TimeSpanStop wasn't updated. For any VFX-range shot, all keyframes exceed TimeSpanStop and are dropped. This is the second bug.

- timestamp: 2026-04-23T16:20:00Z
  checked: `forge_fbx_animated.fbx` test fixture (3-frame animation at KTimes 0, 1926347345, 3852694690)
  found: `TimeSpanStop: 3852694690 = last_ktime` — the fixture creator set TimeSpanStop to match the animation end.
  implication: Confirms the hypothesis: TimeSpanStop must equal last_ktime for Flame's importer to accept the full animation range.

## Resolution

root_cause: `_mutate_template_with_payload` in `forge_flame/fbx_ascii.py` updates `Takes::LocalTime`/`ReferenceTime` (fixed in 45fb7fd) but does NOT update `GlobalSettings::TimeSpanStop`. The template hardcodes `TimeSpanStop = 46186158000` (= frame 24 at 24 fps). For VFX-style shot ranges where all keyframe KTimes exceed this value, Flame silently drops every keyframe on import. This is a second independent bug alongside the LocalTime fix — both must be correct for the round-trip to work on any frame range.

fix: Added `_set_property70(global_settings, "TimeSpanStop", "KTime", "Time", "", [last_ktime])` at the end of `_mutate_template_with_payload`, immediately after the existing Takes update. `last_ktime = times[-1]` is already computed by the Takes fix. The `GlobalSettings` node is found with `next((n for n in tree if n.name == "GlobalSettings"), None)`.

verification: 4 new unit tests in `TestWriterGlobalSettingsTimeSpan` (tests/test_fbx_ascii.py):
  - E: VFX frames 1001–1024 at 24fps → TimeSpanStop = ktime_from_frame(1024, "24 fps") = 1970609408000
  - F: Standard frames 1–10 at 24fps → TimeSpanStop updated (not left at template default)
  - G: 5 frames at 25fps → correct frame_rate used in TimeSpanStop KTime
  - H: TimeSpanStop == Takes::LocalTime end for all cases (parity check)
Full suite: 363 passed, 2 skipped.

files_changed:
  - forge_flame/fbx_ascii.py
  - tests/test_fbx_ascii.py
