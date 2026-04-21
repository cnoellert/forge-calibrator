---
mode: quick
slug: 260420-uzv-preserve-flame-batch-start-frame-in-fbx-
type: execute
status: complete
completed: 2026-04-20
requirements:
  - QUICK-260420-uzv-FRAMENUM
key-files:
  modified:
    - forge_flame/fbx_ascii.py
    - flame/camera_match_hook.py
    - tests/test_fbx_ascii.py
commit: 9c7f109
metrics:
  tests_before: 268
  tests_after: 272
  tests_delta: +4
  test_fbx_ascii_before: 55
  test_fbx_ascii_after: 59
---

# Quick Task 260420-uzv: Preserve Flame Batch start_frame in FBX-derived v5 JSON — Summary

**One-liner:** Threaded a `frame_offset` kwarg through `fbx_to_v5_json` -> `_merge_curves` and wired the Flame hook to read `flame.batch.start_frame.get_value()` defensively, restoring real plate frame numbers (e.g., 1001..1100) on the Flame -> FBX -> v5 JSON path that `action.export_fbx(bake_animation=True)` had zero-based.

## What Changed (Three Coordinated Edits)

### 1. `forge_flame/fbx_ascii.py`

- **`_merge_curves`** (lines ~611-673): added keyword-only `frame_offset: int = 0`.
  - Static-fallback path (line 643): `frame = 0` -> `frame = frame_offset`.
  - Keyed loop (line 665): `frame = frame_from_ktime(ktime, frame_rate)` -> `frame = frame_from_ktime(ktime, frame_rate) + frame_offset`.
  - Docstring updated to explain the `bake_animation=True` zero-basing behavior the offset compensates for.
- **`fbx_to_v5_json`** (lines ~710-789): added keyword-only `frame_offset: int = 0` after `custom_properties`. Threads through to `_merge_curves` at line 787:
  ```python
  frames = _merge_curves(cam, tree, frame_rate, frame_offset=frame_offset)
  ```
  Docstring `Args:` block extended with a `frame_offset` entry.

### 2. `flame/camera_match_hook.py` (`_export_camera_to_blender`, lines ~2105-2138)

Defensive block inserted immediately before the `fbx_ascii.fbx_to_v5_json(...)` call:

```python
frame_offset = 0
try:
    sf = flame.batch.start_frame.get_value()
    frame_offset = int(float(sf))
except Exception:
    frame_offset = 0  # silent fallback; do not surface to user
```

The `int(float(x))` coercion handles all PyAttribute return shapes (int, float, numeric string). The blanket `except Exception` matches the established pattern in `_infer_plate_resolution` (lines 1894, 1904). The existing `import flame` at line 2021 is reused — no new import added.

The `fbx_to_v5_json(...)` call site now includes `frame_offset=frame_offset,` as a kwarg.

### 3. `tests/test_fbx_ascii.py`

Added `TestFbxToV5JsonFrameOffset` (4 tests) immediately after `TestFbxToV5JsonCustomProperties`, mirroring its `_FIXTURE` / `_COMMON_KWARGS` pattern. All four tests use the live-Flame `forge_fbx_baked.fbx` fixture (keyed branch of `_merge_curves`):

| Test | Asserts |
| ---- | ------- |
| `test_a_offset_shifts_frames` | `frame_offset=1001` -> `frames[0]["frame"] == 1001` AND every entry `>= 1001`. |
| `test_b_default_offset_is_zero` | Calling without `frame_offset` produces identical frame fields to `frame_offset=0` (regression guard). |
| `test_c_on_disk_parity` | `frame_offset=1001` survives `json.dump`/`json.load` round-trip on disk. |
| `test_d_large_negative_offset` | `frame_offset=-50` shifts the first frame by exactly -50 vs the no-offset baseline (proves "plain integer add", no clamping). |

## Test Counts

| Scope | Before | After | Delta |
| ----- | -----: | ----: | ----: |
| Full suite (`pytest tests/ -q`) | 268 | **272** | +4 |
| `tests/test_fbx_ascii.py` | 55 | **59** | +4 |
| `test_fbx_io.py + test_solver.py + test_hook_parity.py` (untouched modules, regression check) | 116 | 116 | 0 |

`python -m py_compile flame/camera_match_hook.py` exits 0.

## Untouched (Per Plan Non-Goals)

- **`bake_animation=True`** — kept; the 101-key density on a 1001..1100 range is the desired behavior. Only the numbering was wrong.
- **`tools/blender/bake_camera.py`** — kept; it already derives scene start/end from JSON `frames[*].frame` via min/max. Fixing the source numbers in the v5 JSON makes the Blender side consume them correctly with no Blender-side changes.

## Deviations from Plan

None — plan executed exactly as written. RED -> GREEN -> commit, three coordinated edits across the planned files, all four behavior tests pass on first GREEN run.

## Defensive Fallback — Manual Trace (cannot unit-test without mocking `flame`)

| Scenario | Path | Outcome |
| -------- | ---- | ------- |
| `flame.batch.start_frame` missing | `AttributeError` raised | caught -> `frame_offset = 0` |
| `get_value()` returns `1001` (int) | `int(float(1001))` | `1001` |
| `get_value()` returns `"1001"` (str) | `int(float("1001"))` | `1001` |
| `get_value()` returns `1001.0` (float) | `int(float(1001.0))` | `1001` |
| `get_value()` returns `None` | `float(None)` raises `TypeError` | caught -> `frame_offset = 0` |
| `get_value()` raises | exception propagates into `try` | caught -> `frame_offset = 0` |

A `0` offset reproduces pre-fix behavior, so the fallback degrades gracefully — Blender frames stay zero-based, the export still completes.

## Deployment & UAT

`./install.sh` is **owned by the user**, not this plan. Per the user's explicit non-goal, no deploy command was run. User-side UAT against a live Flame batch (e.g., 1001..1100) will confirm:

1. Open an Action with a baked animated camera in a Flame batch starting at frame 1001.
2. Right-click Action -> Camera Match -> Export Camera to Blender.
3. Open the resulting `.blend` and verify the camera's keyframes land on frames 1001..1100, not 0..99.
4. Verify Blender's scene `frame_start` / `frame_end` reflect the source plate range (set by `bake_camera.py:218-219` from `min(frame)` / `max(frame)`).

## Self-Check: PASSED

**Files exist:**
- `forge_flame/fbx_ascii.py` (modified, contains `frame_offset` 7x via grep)
- `flame/camera_match_hook.py` (modified, contains `frame_offset` 4x + `start_frame` defensive read)
- `tests/test_fbx_ascii.py` (modified, contains `TestFbxToV5JsonFrameOffset` class)
- `.planning/quick/260420-uzv-preserve-flame-batch-start-frame-in-fbx-/260420-uzv-SUMMARY.md` (this file)

**Commit exists:** `9c7f109` — `git log --oneline -1` shows
`feat(quick-260420-uzv): preserve Flame batch start_frame in FBX-derived v5 JSON`.

**All success criteria from PLAN.md met:**
- [x] `_merge_curves` and `fbx_to_v5_json` both accept `frame_offset: int = 0` (keyword-only).
- [x] BOTH `_merge_curves` paths apply `frame_offset` to the emitted `frame` field.
- [x] `fbx_to_v5_json` threads `frame_offset` to `_merge_curves`.
- [x] `_export_camera_to_blender` reads `flame.batch.start_frame.get_value()` defensively, coerces via `int(float(...))`, falls back to 0 on any exception.
- [x] The `fbx_ascii.fbx_to_v5_json(...)` call now includes `frame_offset=frame_offset`.
- [x] `TestFbxToV5JsonFrameOffset` class with 4 tests covering all required behaviors.
- [x] `pytest tests/ -x -q` passes (272 / 272).
- [x] `pytest tests/test_fbx_ascii.py -x -q` passes (59 / 59).
- [x] Docstrings updated on `_merge_curves` and `fbx_to_v5_json`.
- [x] No changes to `bake_animation=True`, no changes to `tools/blender/bake_camera.py`, no `./install.sh`.
