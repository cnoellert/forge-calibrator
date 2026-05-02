---
quick_id: 260501-rus
status: complete
verdict: SHIPPED — 7-stop semantic ladder live; Interior is the new studio default; deprecated stops kept valid bake-side for back-compat
mode: quick
type: execute
wave: 1
depends_on: [260501-dpa, 260501-em8, 260501-knl]
started: "2026-05-02T03:08:00Z"
completed: "2026-05-02T03:18:00Z"
duration_min: 10
files_modified:
  - tools/blender/bake_camera.py
  - forge_flame/camera_io.py
  - forge_flame/fbx_ascii.py
  - flame/scale_picker_dialog.py
  - flame/camera_match_hook.py
  - tests/test_bake_camera.py
  - tests/test_blender_roundtrip.py
  - tests/test_scale_picker_dialog.py
  - tests/test_hook_export_camera_to_blender.py
  - .planning/todos/pending/2026-05-02-flame-blender-scale-roundtrip-uat.md
key_findings:
  - Canonical ladder widened from 5 stops to 7 — physical coverage 1.8 km → 1.8 mm in even log-decade steps
  - Studio default flipped Soundstage (100.0) → Interior (1000.0) at every default call site (3 kwarg signatures + 2 picker-wrapper defaults + 1 dialog default)
  - Deprecated stops {0.01, 0.1} kept valid bake-side via `_DEPRECATED_FLAME_TO_BLENDER_SCALE_LADDER` + validator union check; never offered in the dialog
  - Dialog re-skinned with semantic labels + unicode superscript multipliers (×10⁰..×10⁶) + physical-distance subtitles for the 4096-wide reference plate
  - Viewport-nav `, scale=1000.0,` at run_bake call site stays byte-identical; canary test G tightened (Rule 1 deviation) so the new `flame_to_blender_scale=1000.0` substrings don't false-match
  - JSON contract field `flame_to_blender_scale` value semantics unchanged — raw float divisor; only canonical stop set + default + UI labels changed
---

# Quick Task 260501-rus — Extend Flame↔Blender Scale Ladder 5 → 7 — Summary

## One-liner

Extended the canonical Flame↔Blender scale ladder from the 5-stop set shipped in 260501-dpa/i31/knl to a 7-stop semantic ladder (Landscape ×10⁰ / Outdoor ×10¹ / Soundstage ×10² / Interior ×10³ / Tabletop ×10⁴ / Product ×10⁵ / Macro ×10⁶), flipped the studio default from Soundstage (100.0) → Interior (1000.0) at every default call site, kept the deprecated 2 stops valid bake-side for back-compat with already-baked `.blend` files, and re-skinned the picker dialog with semantic labels + unicode superscripts + Interior highlighted as the default button.

## Verdict

**SHIPPED.** Four atomic commits, each green on its own. Full pytest suite green: 542 passed / 0 failed / 2 skipped (was 522/0/2 baseline → +20 net new collected items from parametrize widenings + deprecated-stop coverage).

## What was built

| Commit | One-line description |
|--------|----------------------|
| `b096ba2` | feat(quick-260501-rus): extend bake-side ladder to 7-stop canonical set + keep 2 deprecated stops valid for back-compat |
| `a70591d` | feat(quick-260501-rus): re-skin scale picker dialog with 7 semantic stops + Interior default |
| `d621e77` | feat(quick-260501-rus): flip hook studio default 100.0 (Soundstage) → 1000.0 (Interior) + extend ladder menu stops to 7-stop canonical set |
| `b6e75ca` | docs(quick-260501-rus): update UAT todo for 7-stop semantic ladder + Interior default + deprecated-stop back-compat UAT |

## Files modified

| File | Lines (Δ) | What |
|------|-----------|------|
| `tools/blender/bake_camera.py` | +13 / −7 | Split ladder into canonical (7) + deprecated (2); validator membership check on the union; error message lists both sets |
| `forge_flame/camera_io.py` | +4 / −2 | Docstring updated for new canonical set + deprecated note |
| `forge_flame/fbx_ascii.py` | +8 / −5 | Same docstring update on `fbx_to_v5_json` |
| `flame/scale_picker_dialog.py` | +21 / −21 | 7-stop semantic `_LADDER_STOPS` with unicode superscripts; default 100.0→1000.0; setMinimumWidth 560→820, per-button 96→108; subtitle copy updated |
| `tests/test_scale_picker_dialog.py` | +36 / −24 | 7-button assertion, default-Interior parity, parametrize widened 5→7 (12 collected, was 10) |
| `flame/camera_match_hook.py` | +28 / −30 | All five `=100.0` defaults flipped to `1000.0`; `_LADDER_MENU_STOPS` widened 5→7; docstrings/comments updated; viewport-nav `scale=1000.0` at run_bake byte-identical |
| `tests/test_hook_export_camera_to_blender.py` | +44 / −34 | Parametrize widening (A/B), default-value flips on wrappers (D), signature default 1000.0 (I), `_LADDER_MENU_STOPS` 7-tuple assertion (K), canary G tightened to anchor on `, scale=1000.0,` + comment backtick form |
| `tests/test_bake_camera.py` | +37 / −18 | Canonical 7-case parametrize, deprecated 2-case parametrize, widened rejection set (1000.0 dropped — now canonical); `+9` rejection cases total |
| `tests/test_blender_roundtrip.py` | +24 / −2 | `_LADDER` widened to 7; new `_DEPRECATED_LADDER` constant; new sibling parametrize over deprecated stops on the central static-camera test |
| `.planning/todos/pending/2026-05-02-flame-blender-scale-roundtrip-uat.md` | +21 / −10 | UAT 1/3/5 narratives flipped to Interior; UAT 2 rewritten (Landscape · ×10⁰ ~1.8 km replaces "1x = ~833m architectural"); NEW UAT 7 covers deprecated-stop back-compat |

**Net:** 10 files modified; +236 / −153 LOC (commits show: 87+57+78+21+ insertions vs 35+45+54+10 deletions).

## Round-trip parity tables

### Canonical 7 stops (numpy stand-in; bit-exact to mathutils path)

| Scale | Position max \|delta\| | Rotation max \|delta\| |
|-------|------------------------|------------------------|
| 1.0 | 0.0 (atol=1e-9) | 0.0 (atol=1e-9) |
| 10.0 | 0.0 (atol=1e-9) | 0.0 (atol=1e-9) |
| 100.0 | 0.0 (atol=1e-9) | 0.0 (atol=1e-9) |
| 1000.0 | 0.0 (atol=1e-9) | 0.0 (atol=1e-9) |
| 10000.0 | 0.0 (atol=1e-9) | 0.0 (atol=1e-9) |
| 100000.0 | 0.0 (atol=1e-9) | 0.0 (atol=1e-9) |
| 1000000.0 | 0.0 (atol=1e-9) | 0.0 (atol=1e-9) |

All deltas at IEEE-754 floor — bit-identical round-trip; same baseline as 260501-dpa.

### Deprecated 2 stops (back-compat coverage)

| Scale | Position max \|delta\| | Rotation max \|delta\| |
|-------|------------------------|------------------------|
| 0.01 | 0.0 (atol=1e-9) | 0.0 (atol=1e-9) |
| 0.1 | 0.0 (atol=1e-9) | 0.0 (atol=1e-9) |

Proves `.blend` files baked under the original 260501-dpa contract still round-trip cleanly.

## Test results

- `tests/test_bake_camera.py` + `tests/test_blender_roundtrip.py`: **58 passed** (Task 1 verify)
- `tests/test_scale_picker_dialog.py`: **12 passed** (Task 2 verify; was 10, +2 from parametrize widening)
- `tests/test_hook_export_camera_to_blender.py`: **30 passed** (Task 3 verify; was 26, +4 from parametrize widening on A/B)
- **Full suite:** `pytest -p no:pytest-blender tests/` → **542 passed / 0 failed / 2 skipped** (baseline 522/0/2 → +20 net new collected items)

## Deviations from plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Canary test G's substring match was false-positive on the new `flame_to_blender_scale=1000.0` defaults**
- **Found during:** Task 3
- **Issue:** The canary test asserted `source.count("scale=1000.0") == 2`, but Python's `str.count` is a substring search. After flipping `flame_to_blender_scale=100.0` → `flame_to_blender_scale=1000.0` at five default sites, the substring `scale=1000.0` now appears 7 times (5 false-matches + 1 real run_bake call + 1 explanatory comment). The plan's note that "the new flame_to_blender_scale=1000.0 occurrences are separate string literals because the kwarg name differs" was incorrect — substring containment matches the trailing portion regardless of prefix.
- **Fix:** Tightened the canary to anchor on the run_bake-specific spelling `, scale=1000.0,` (with leading comma + trailing comma — unique to the kwarg-list call site) AND the backtick-quoted reference `` `scale=1000.0` `` in the explanatory comment block. Both must remain at exactly 1. Preserves the original intent (byte-identical viewport-nav literal at run_bake) without false-positive collisions.
- **Files modified:** `tests/test_hook_export_camera_to_blender.py` (Test G updated)
- **Commit:** `d621e77`

## Out of scope (deliberate)

- **Documentation for artists** — physical-scale guide explaining each of the 7 semantic labels (separate phase, doc-only, no code).
- **Persistent last-used preference** — "remember last scale" across sessions (separate quick if needed; current dialog rebuilds fresh on each open).
- **Calibrated reference-distance UI** — the photogrammetric "right answer" where the artist drags a known-length reference and derives scale from projection math (separate phase, ~1 day, supersedes manual ladder picking).
- **Geometry scaling, matchbox direction** — both shelved per `memory/matchbox_direction_shelved.md`.
- **Auto-promotion of deprecated stops to canonical** — none planned; `0.01` / `0.1` remain "deprecated but valid bake-side" indefinitely so already-baked `.blend` files round-trip cleanly.

## Manual UAT pointer

Updated UAT todo: `.planning/todos/pending/2026-05-02-flame-blender-scale-roundtrip-uat.md` — now **7 UAT items** (was 6):

- UAT 1: Static round-trip at default scale (Interior · ×10³) — REGRESSION HEADLINE
- UAT 2: Static round-trip at non-default scale (Landscape · ×10⁰)
- UAT 3: Animated camera round-trip (default Interior pick)
- UAT 4: ESC/cancel hygiene (no .blend, no orphan Blender)
- UAT 5: Default-button parity (Enter vs explicit Interior click)
- UAT 6: Camera-node surface (Action-schematic right-click)
- **UAT 7 (NEW):** Deprecated-stop back-compat — proves existing `.blend` files baked at 0.01/0.1 still round-trip cleanly

## Self-check

- [x] Verdict written: SHIPPED
- [x] 4 atomic commits land in order; each green on its own
- [x] `_FLAME_TO_BLENDER_SCALE_LADDER == (1.0, 10.0, 100.0, 1000.0, 10000.0, 100000.0, 1000000.0)`
- [x] `_DEPRECATED_FLAME_TO_BLENDER_SCALE_LADDER == (0.01, 0.1)`
- [x] Validator accepts every value in either tuple; rejects values in neither
- [x] Dialog presents 7 semantic buttons; deprecated stops never offered; Interior is the default (`setDefault(True)` + `objectName='primary'` + Enter shortcut)
- [x] `pick_scale(default=1000.0)` highlights Interior
- [x] All five `flame_to_blender_scale=100.0` default sites flipped to `1000.0`
- [x] `_LADDER_MENU_STOPS == (1.0, 10.0, 100.0, 1000.0, 10000.0, 100000.0, 1000000.0)`
- [x] Viewport-nav `, scale=1000.0,` at run_bake byte-identical (verified: 1 occurrence in source)
- [x] Round-trip parity at all 7 canonical + both deprecated stops bit-exact (atol=1e-9, all 0.0)
- [x] JSON contract field semantics unchanged — `flame_to_blender_scale` still a raw float, written via `is not None` semantics
- [x] UAT todo updated; UAT 7 added; "1x = ~833m architectural" wording purged
- [x] Full pytest suite green: 542 passed / 0 failed / 2 skipped

## Self-Check: PASSED

Verified all created files / commits:

```
FOUND: tools/blender/bake_camera.py (modified)
FOUND: forge_flame/camera_io.py (modified)
FOUND: forge_flame/fbx_ascii.py (modified)
FOUND: flame/scale_picker_dialog.py (modified)
FOUND: flame/camera_match_hook.py (modified)
FOUND: tests/test_bake_camera.py (modified)
FOUND: tests/test_blender_roundtrip.py (modified)
FOUND: tests/test_scale_picker_dialog.py (modified)
FOUND: tests/test_hook_export_camera_to_blender.py (modified)
FOUND: .planning/todos/pending/2026-05-02-flame-blender-scale-roundtrip-uat.md (modified)
FOUND: b096ba2 (Task 1 commit)
FOUND: a70591d (Task 2 commit)
FOUND: d621e77 (Task 3 commit)
FOUND: b6e75ca (Task 4 commit)
```
