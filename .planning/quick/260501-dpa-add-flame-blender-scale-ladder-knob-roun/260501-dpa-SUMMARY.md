---
quick_id: 260501-dpa
status: complete
verdict: SHIPPED — round-trip parity bit-exact for positions, float-epsilon for rotations
mode: quick
type: execute
wave: 1
depends_on: []
started: "2026-05-01T16:51:56Z"
completed: "2026-05-01T17:10:00Z"
duration_min: 14
files_modified:
  - tools/blender/bake_camera.py
  - forge_flame/camera_io.py
  - tests/test_bake_camera.py
  - tests/test_camera_io.py
  - tests/test_blender_roundtrip.py
key_findings:
  - JSON contract (v5) is the right surface for the scale knob — extract side already had a _resolve_scale helper via forge_bake_scale custom property, no extract changes needed
  - Round-trip parity at all 5 ladder stops is bit-exact (max |delta| = 0.0e+00) for positions; rotations show 1.78e-15 float-epsilon floor
  - Out-of-ladder values (0.5, 2.0, 0.05, 1000.0, -1.0, 0.0) raise SystemExit with the value + full ladder list — no silent snap-to-nearest
  - Existing scale=1000.0 viewport-nav hack at flame/camera_match_hook.py:2912 is byte-identical (untouched)
  - Hook integration + PySide2 ladder dropdown UI + calibrated reference-distance UI are explicitly NEXT-PHASE work (out of scope here)
---

# Quick Task 260501-dpa — Flame↔Blender Scale Ladder Knob — Summary

## One-liner

`flame_to_blender_scale` ladder knob added to the v5 JSON contract — discrete log10 stops `{0.01, 0.1, 1.0, 10.0, 100.0}`, default `1.0`, bake-side validates and applies, extract-side already round-trips via the existing `forge_bake_scale` custom property. Bit-exact position parity, float-epsilon rotation parity, 29 new tests guarding the contract.

## Verdict

**SHIPPED.** Two atomic commits, full test suite green (486 passed / 0 failed / 2 skipped — was 457/0/2 baseline → +29 net new tests). Round-trip correctness property enforced at `atol=1e-9, rtol=0`.

## What was built

**Two commits:**

| # | Commit | Description |
|---|--------|-------------|
| 1 | `7d448e8` | `feat(quick-260501-dpa): add flame_to_blender_scale ladder knob to v5 JSON contract` — bake-side validation + JSON-field-precedence; camera_io.py emit-block |
| 2 | `76d88fa` | `test(quick-260501-dpa): round-trip parity for flame_to_blender_scale ladder` — 12 round-trip tests + parametric scale handling on test helpers |

**Files modified (5):**

| File | Lines | What |
|------|-------|------|
| `tools/blender/bake_camera.py` | +44 | Ladder constant `_FLAME_TO_BLENDER_SCALE_LADDER`, `_validate_flame_to_blender_scale` helper, JSON-field-precedence block in `_bake` (precedence: JSON field > CLI `--scale` > 1.0 default) |
| `forge_flame/camera_io.py` | +24 | New optional `flame_to_blender_scale` kwarg + docstring + `is not None` emit block (so `1.0` is recorded explicitly when set, not silently elided) |
| `tests/test_bake_camera.py` | +54 | `TestFlameToBlenderScaleLadder` — 13 cases (in-ladder accept × 5, out-of-ladder reject × 6, plus default-behavior + JSON-overrides-CLI guards) |
| `tests/test_camera_io.py` | +99 | `TestFlameToBlenderScaleField` — 4 cases on the JSON serializer kwarg behavior (default omit, explicit emit, round-trip survival) |
| `tests/test_blender_roundtrip.py` | +172 | `TestScaleLadderRoundTrip` — 12 cases (5 static + 5 animated × 5-keyframe + 1 byte-identity at scale=1.0 + 1 focal/film_back invariance) |

**Files NOT touched (preserved):**
- `flame/camera_match_hook.py:2912` — the existing `scale=1000.0` viewport-nav hack stays byte-identical (verified via the planner's pre-investigation; executor explicitly avoided this file)
- `tools/blender/extract_camera.py` — no changes needed; `_resolve_scale` already walks any `forge_bake_scale` custom property the bake stamps
- `tools/blender/forge_sender/flame_math.py` — no changes; the version-tolerant fcurves walk from 260429-gde stays as-is

## Round-trip parity result

The central correctness property: bake at scale S, extract, must return to original Flame coords within `atol=1e-9`.

| Scale | Position max \|delta\| | Rotation max \|delta\| | Verdict |
|-------|---------------------|---------------------|---------|
| 0.01  | 0.0e+00             | 1.78e-15            | bit-exact / float-eps |
| 0.1   | 0.0e+00             | 1.78e-15            | bit-exact / float-eps |
| 1.0   | 0.0e+00             | 1.78e-15            | bit-exact / float-eps |
| 10.0  | 0.0e+00             | 1.78e-15            | bit-exact / float-eps |
| 100.0 | 0.0e+00             | 1.78e-15            | bit-exact / float-eps |

Position deltas are zero because powers-of-10 are exact float reciprocals (`10 * x / 10` is byte-identical in IEEE-754). Rotation deltas show the standard `~1e-15` float epsilon floor from the matrix composition path — ~10⁶× below the `1e-9` test gate. Animated 5-keyframe parity holds with the same numbers per keyframe.

## Out-of-ladder rejection

Six parametrized rejection cases all raise `SystemExit` with a clear message containing both the offending value and the full ladder:

- `0.5` (between 0.1 and 1.0) → rejected
- `2.0` (between 1.0 and 10.0) → rejected
- `0.05` (between 0.01 and 0.1) → rejected
- `1000.0` (above ladder) → rejected
- `-1.0` (negative) → rejected
- `0.0` (zero) → rejected

**Why no snap-to-nearest:** snap-to-nearest is the silent precision drift that the ladder exists to prevent. Hard rejection forces the caller (and the future PySide2 UI dropdown) to be explicit about which scale was chosen.

## Out of scope (deliberate, for a future phase)

- **Hook integration** — `flame/camera_match_hook.py:2912` still uses `scale=1000.0` as a viewport-nav hack. Wiring the new JSON-field path into the actual user flow is the next phase's work.
- **PySide2 ladder dropdown UI** — artist-facing surface for picking the scale. Belongs in the calibrator UI work.
- **Calibrated reference-distance UI** — artist drags a known-length line, derives scale from photogrammetry math. Mentioned as the "right answer" earlier; lands in a separate phase per the strategic discussion.
- **Geometry scaling** — only camera positions are scaled. Reference geometry import scaling is its own decision.
- **Matchbox-side changes** — matchbox direction is shelved (see memory `matchbox_direction_shelved.md`).

## Tests added (29 net new)

- `TestFlameToBlenderScaleLadder` (test_bake_camera.py) — 13 cases
- `TestFlameToBlenderScaleField` (test_camera_io.py) — 4 cases
- `TestScaleLadderRoundTrip` (test_blender_roundtrip.py) — 12 cases

**Test suite: 486 passed / 0 failed / 2 skipped** (baseline 457/0/2). Run with `pytest -p no:pytest-blender tests/` per memory `forge_pytest_blender_session_exit.md`.

## Files NOT modified (verified)

`git status --short` post-execution showed only `?? .planning/quick/260501-dpa-...` (untracked planning dir). All five modified source files are tracked + clean post-commit. No orphan files in repo root or unrelated dirs.

## Self-check

- [x] Verdict written: SHIPPED
- [x] Round-trip parity bit-exact at every ladder stop (positions); float-epsilon for rotations
- [x] Out-of-ladder rejection works (6 cases)
- [x] Existing viewport-nav scale=1000.0 hack preserved untouched
- [x] Two atomic commits, each passing tests independently
- [x] +29 tests landed; full suite green
- [x] No new dependencies (numpy + bpy/mathutils already present)
- [x] No production code touched outside the three target files; no test infrastructure beyond the existing duck-typed Blender mock pattern

## Next planning step

The natural follow-up is a planned phase (not a quick) that:

1. **Wires the JSON field through the existing hook.** The `camera_match_hook.py:2912` viewport-nav `scale=1000.0` hack is currently independent of the new `flame_to_blender_scale` field. The phase reconciles the two — likely by making the hack a special case of the ladder (and bumping the hack's value into the ladder set if 1000.0 is needed as a real scale).
2. **Adds the artist UI** — PySide2 dropdown in the calibrator that lists the 5 ladder stops and writes the chosen value into the JSON before invoking the bake.
3. **Documents the choice for artists** — what each stop means in physical terms (0.01 = treat Flame pixels as cm; 0.1 = decimeters; 1.0 = treat 1 pixel as 1 m; 10.0/100.0 for very small / very large scenes).

Subsequently, a second phase (calibrated reference-distance UI) supersedes manual ladder picking with photogrammetric scale derivation, but the ladder remains as the fallback when no measurement is provided.
