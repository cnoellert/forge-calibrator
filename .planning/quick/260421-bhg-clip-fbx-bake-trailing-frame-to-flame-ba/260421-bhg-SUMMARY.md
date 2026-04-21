---
mode: quick
slug: 260421-bhg-clip-fbx-bake-trailing-frame-to-flame-ba
type: execute
status: complete
completed: 2026-04-21
requirements:
  - QUICK-260421-bhg-FRAMEEND
key-files:
  modified:
    - forge_flame/fbx_ascii.py
    - flame/camera_match_hook.py
    - tests/test_fbx_ascii.py
commit: cf0e002
metrics:
  tests_before: 272
  tests_after: 276
  tests_delta: +4
  test_fbx_ascii_before: 59
  test_fbx_ascii_after: 63
---

# Quick Task 260421-bhg: Clip Trailing `bake_animation` Frame via `frame_end` — Summary

**One-liner:** Threaded a `frame_end` kwarg (INCLUSIVE upper bound, applied AFTER `frame_offset`) through `fbx_to_v5_json` -> `_merge_curves` and wired the Flame hook to read `flame.batch.end_frame.get_value()` defensively — drops the single errant keyframe that `action.export_fbx(bake_animation=True)` bakes one frame past the user's batch range (UAT on 260420-uzv: 1001..1100 batch was yielding a stray 1101 keyframe in Blender).

## What Changed (Three Coordinated Edits)

### 1. `forge_flame/fbx_ascii.py`

- **`_merge_curves`** (lines ~611-694): added keyword-only `frame_end: Optional[int] = None` after `frame_offset`.
  - Static-fallback path (line ~643): after `frame = frame_offset`, a guard `if frame_end is not None and frame > frame_end: return []` short-circuits the film-back math when the single static frame would exceed the bound. Symmetric with the keyed path (degenerate in practice for static cams, but defensive).
  - Keyed loop (line ~688): immediately after `frame = frame_from_ktime(ktime, frame_rate) + frame_offset`, a `if frame_end is not None and frame > frame_end: continue` drops any key whose POST-OFFSET frame exceeds the bound.
  - Ordering is locked: clip runs AFTER `frame_offset` is added, because `frame_end` is a user-facing plate frame number (from `flame.batch.end_frame`), not a raw FBX KTime index.
  - Docstring extended to explain the INCLUSIVE semantic and the `(end - start + 1)` overshoot cause.
- **`fbx_to_v5_json`** (lines ~718-830): added keyword-only `frame_end: Optional[int] = None` after `frame_offset`. Threads through to `_merge_curves` at the inner call:
  ```python
  frames = _merge_curves(
      cam, tree, frame_rate,
      frame_offset=frame_offset,
      frame_end=frame_end,
  )
  ```
  Docstring `Args:` block extended with a `frame_end` entry.

### 2. `flame/camera_match_hook.py` (`_export_camera_to_blender`, lines ~2127-2156)

Symmetric defensive block inserted immediately after the existing `start_frame` read (260420-uzv) and BEFORE the `fbx_ascii.fbx_to_v5_json(...)` call:

```python
frame_end = None
try:
    ef = flame.batch.end_frame.get_value()
    frame_end = int(float(ef))
except Exception:
    frame_end = None  # silent fallback; None = no clip
```

The `int(float(x))` coercion mirrors the `start_frame` path to handle any PyAttribute return shape (int, float, numeric string). The blanket `except Exception` matches the established pattern in `_infer_plate_resolution` (lines 1894, 1904) and the 260420-uzv start_frame block.

**Fallback is `None`, not `0`:** This matches the `Optional[int]` signature semantic — `None` means "don't clip", preserving pre-fix behavior on any error. Using `0` as the fallback would incorrectly drop every frame (offset-adjusted frames are all `>= start_frame >= 1` in real batches), which is a strictly worse failure mode than "offset applied, no clip".

The `fbx_to_v5_json(...)` call site now includes `frame_end=frame_end,` as a kwarg alongside the existing `frame_offset=frame_offset,`.

### 3. `tests/test_fbx_ascii.py`

Added `TestFbxToV5JsonFrameEnd` (4 tests) immediately after `TestFbxToV5JsonFrameOffset`, mirroring its `_FIXTURE` / `_COMMON_KWARGS` pattern. All four tests use the live-Flame `forge_fbx_baked.fbx` fixture (keyed branch of `_merge_curves`):

| Test | Asserts |
| ---- | ------- |
| `test_a_offset_plus_end_clip_drops_trailing_frame` | UAT scenario: `frame_offset=1001, frame_end=1001 + baseline_last - 1` yields exactly `(baseline_count - 1)` frames with max frame == boundary (proves inclusive upper bound + single trailing drop). Uses a no-offset baseline read first to discover the fixture's natural range at runtime. |
| `test_b_none_default_is_no_op` | `frame_end=None` (explicit) is identical to omitting the kwarg (regression guard — preserves the 260420-uzv post-state). |
| `test_c_frame_end_below_min_yields_empty` | `frame_offset=1001, frame_end=0` drops everything -> `frames == []` (no crash, no None — empty is legitimate). |
| `test_d_inclusive_boundary_keeps_first_frame` | `frame_offset=1001, frame_end=1001 + baseline_first` yields exactly one frame at the boundary — locks in STRICT `>` drop semantics (if someone "helpfully" changes `>` to `>=`, this test goes red). |

## Test Counts

| Scope | Before | After | Delta |
| ----- | -----: | ----: | ----: |
| Full suite (`pytest tests/ -q`) | 272 | **276** | +4 |
| `tests/test_fbx_ascii.py` | 59 | **63** | +4 |
| `test_fbx_io.py + test_solver.py + test_hook_parity.py` (untouched modules, regression check) | 116 | 116 | 0 |

`python -m py_compile flame/camera_match_hook.py` exits 0.

## Static Verification (grep checks from PLAN.md)

- `forge_flame/fbx_ascii.py`: `frame_end` appears on both signatures (lines 617, 753), in both drop-guards (lines 660, 688), and in the inner call (line 824).
- `flame/camera_match_hook.py`: `end_frame` / `frame_end` appear in the defensive read block (lines 2136-2141) and the `fbx_to_v5_json` kwarg (line 2155).
- STRICT `frame > frame_end` (not `>=`) appears at lines 660 and 688. INCLUSIVE boundary locked.
- Clip-after-offset ordering confirmed: in both code paths, `frame` has `frame_offset` already added BEFORE the `frame_end` comparison.

## Untouched (Per Plan Non-Goals)

- **`bake_animation=True`** — kept; the 101-key density on a 1001..1100 range is the desired behavior per the user. Only the trailing overshoot was wrong.
- **`tools/blender/bake_camera.py`** — kept; it derives scene `frame_start` / `frame_end` from JSON `min(frame)` / `max(frame)`, so trimming the trailing key in the v5 JSON automatically tightens the Blender scene range with no Blender-side changes.
- **`./install.sh`** — user owns deployment; plan ended at "tests pass".
- **`frame_offset` wiring** (from 260420-uzv) — not re-touched; this fix builds on it.

## Deviations from Plan

None — plan executed exactly as written. RED -> GREEN -> commit. The four behavior tests went red on first run with the expected `TypeError: unexpected keyword argument 'frame_end'`, then went green on first GREEN run with no iteration.

## Inclusive Semantic — Enforced by Test D

The drop condition is `frame > frame_end` (STRICT greater-than). For a 1001..1100 batch the output contains frames 1001, 1002, ..., 1100 (the boundary is KEPT). If someone later changes the condition to `frame >= frame_end`, Test D fails immediately (0 surviving frames instead of 1 at the boundary). This is belt-and-braces correctness protection — the semantic lives in code, docstring, AND a dedicated test.

## Defensive Fallback — Manual Trace (cannot unit-test without mocking `flame`)

Same rationale as 260420-uzv — `flame` is a runtime singleton the test harness doesn't mock.

| Scenario | Path | Outcome |
| -------- | ---- | ------- |
| `flame.batch.end_frame` missing | `AttributeError` raised | caught -> `frame_end = None` (no clip) |
| `get_value()` returns `1100` (int) | `int(float(1100))` | `1100` (clip to inclusive 1100) |
| `get_value()` returns `"1100"` (str) | `int(float("1100"))` | `1100` |
| `get_value()` returns `1100.0` (float) | `int(float(1100.0))` | `1100` |
| `get_value()` returns `None` | `float(None)` raises `TypeError` | caught -> `frame_end = None` |
| `get_value()` raises | exception propagates into `try` | caught -> `frame_end = None` |

`frame_end = None` reproduces pre-fix behavior (offset applied, no clip — the 260420-uzv post-state), so the fallback degrades gracefully. Blender still gets real plate frame numbers, just with the one errant trailing frame still present — strictly better than crashing a working export.

## Deployment & UAT

`./install.sh` is **owned by the user**, not this plan. Per the constraint, no deploy command was run. User-side UAT against the same 1001..1100 batch that surfaced the bug will confirm:

1. Open an Action with a baked animated camera in a Flame batch spanning 1001..1100.
2. Right-click Action -> Camera Match -> Export Camera to Blender.
3. Open the resulting `.blend` and verify the camera's keyframes land on frames 1001..1100 (exactly 100 keys), with **no** errant key at 1101.
4. Verify Blender's scene `frame_start=1001` and `frame_end=1100` (set by `bake_camera.py:218-219` from the tightened `min(frame)` / `max(frame)` of the clipped v5 JSON).

## Self-Check: PASSED

**Files exist:**
- `forge_flame/fbx_ascii.py` (modified; `frame_end` appears 11x via grep — signature, docstring, guards, inner call)
- `flame/camera_match_hook.py` (modified; `end_frame` / `frame_end` appear 5x — defensive read block + kwarg)
- `tests/test_fbx_ascii.py` (modified; `TestFbxToV5JsonFrameEnd` class with 4 tests)
- `.planning/quick/260421-bhg-clip-fbx-bake-trailing-frame-to-flame-ba/260421-bhg-SUMMARY.md` (this file)

**Commit exists:** `cf0e002` — `git log --oneline -1` shows
`feat(quick-260421-bhg): clip trailing bake_animation frame via frame_end`.

**All success criteria from PLAN.md met:**
- [x] `_merge_curves` and `fbx_to_v5_json` both accept `frame_end: Optional[int] = None` (keyword-only, after `frame_offset`).
- [x] BOTH code paths apply `frame_end` AFTER `frame_offset` is added to `frame`.
- [x] Drop condition uses STRICT `frame > frame_end` (inclusive upper bound).
- [x] `fbx_to_v5_json` threads `frame_end` to the inner `_merge_curves` call.
- [x] `_export_camera_to_blender` reads `flame.batch.end_frame.get_value()` defensively, coerces via `int(float(...))`, falls back to `None` on ANY exception.
- [x] The `fbx_ascii.fbx_to_v5_json(...)` call includes `frame_end=frame_end` alongside `frame_offset=frame_offset`.
- [x] `TestFbxToV5JsonFrameEnd` class with 4 tests covering UAT scenario, None-default regression, empty-result edge, inclusive boundary.
- [x] `pytest tests/ -x -q` passes (276 / 276).
- [x] `pytest tests/test_fbx_ascii.py -x -q` passes (63 / 63).
- [x] Docstrings updated on `_merge_curves` and `fbx_to_v5_json`.
- [x] No changes to `bake_animation=True`, no changes to `tools/blender/bake_camera.py`, no `./install.sh`.
