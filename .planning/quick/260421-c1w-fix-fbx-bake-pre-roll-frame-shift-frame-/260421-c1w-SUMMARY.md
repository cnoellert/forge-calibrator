---
mode: quick
slug: 260421-c1w-fix-fbx-bake-pre-roll-frame-shift-frame-
type: execute
status: complete
completed: 2026-04-21
requirements:
  - QUICK-260421-c1w-FRAMESTART
key-files:
  modified:
    - forge_flame/fbx_ascii.py
    - flame/camera_match_hook.py
    - tests/test_fbx_ascii.py
commit: 61b3e8c
metrics:
  tests_before: 276
  tests_after: 280
  tests_delta: +4
  test_fbx_ascii_before: 63
  test_fbx_ascii_after: 67
---

# Quick Task 260421-c1w: Drop FBX Bake Pre-roll + Correct +1 Shift via `frame_start` — Summary

**One-liner:** Threaded a symmetric `frame_start` kwarg (INCLUSIVE lower bound, applied AFTER `frame_offset`) through `fbx_to_v5_json` -> `_merge_curves`, AND modified the Flame hook's `start_frame` defensive read in place so ONE read of `flame.batch.start_frame.get_value()` now drives both `frame_offset = start_frame - 1` (shift correction for KTime 0 pre-roll) and `frame_start = start_frame` (inclusive drop of the pre-roll) — third fix in the chain (260420-uzv -> 260421-bhg -> 260421-c1w) that makes the `action.export_fbx(bake_animation=True)` round-trip geometrically faithful to the plate.

## What Changed (Three Coordinated Edits)

### 1. `forge_flame/fbx_ascii.py`

- **`_merge_curves`** (signature at line 611-619): added keyword-only `frame_start: Optional[int] = None` **between** `frame_offset` and `frame_end` for "start, end" reading order.
  - **Static-fallback path** (line ~675): added `if frame_start is not None and frame < frame_start: return []` immediately after `frame = frame_offset` and BEFORE the existing `frame_end` guard. Comment rewritten to explain that the clip applies after the offset (so the comparison is against the user-facing plate frame number) and locks STRICT `<` as the INCLUSIVE lower bound.
  - **Keyed path** (line ~709): added `if frame_start is not None and frame < frame_start: continue` immediately after `frame = frame_from_ktime(ktime, frame_rate) + frame_offset` and BEFORE the existing `frame_end` guard. The two guards drop the frame independently; filter order matches signature order.
  - **Ordering is locked:** `frame_start` and `frame_end` are both compared against `frame` AFTER `frame_offset` has been added, because both are user-facing plate frame numbers (from `flame.batch.start_frame` / `end_frame`), not raw FBX KTime indices.
  - Docstring extended with a new paragraph explaining `frame_start`'s INCLUSIVE semantic, its pairing with `frame_offset = start_frame - 1` to drop the pre-roll, and the symmetric `[frame_start, frame_end]` closed range.
- **`fbx_to_v5_json`** (signature at line 742-755): added keyword-only `frame_start: Optional[int] = None` between `frame_offset` and `frame_end`. `Args:` block extended with a `frame_start:` entry and `frame_offset:` entry rewritten to note the new `start_frame - 1` pairing (v5 JSON callers that want pre-roll drop must use `start_frame - 1`, not `start_frame`). Threaded through to `_merge_curves` at the inner call:
  ```python
  frames = _merge_curves(
      cam, tree, frame_rate,
      frame_offset=frame_offset,
      frame_start=frame_start,
      frame_end=frame_end,
  )
  ```

### 2. `flame/camera_match_hook.py` (`_export_camera_to_blender`, lines ~2105-2144)

The EXISTING `start_frame` defensive block from 260420-uzv was **modified in place** — NOT duplicated. Single read of `flame.batch.start_frame.get_value()` now drives two values:

```python
frame_offset = 0
frame_start = None
try:
    sf = flame.batch.start_frame.get_value()
    start_frame_int = int(float(sf))
    frame_offset = start_frame_int - 1  # shift for KTime 0 pre-roll
    frame_start = start_frame_int       # INCLUSIVE drop of pre-roll
except Exception:
    frame_offset = 0    # silent fallback; no shift
    frame_start = None  # silent fallback; no clip
```

Key properties:
- **ONE read of `start_frame`.** `grep -c "flame\.batch\.start_frame\.get_value" flame/camera_match_hook.py` returns **1** — the defensive try/except is NOT duplicated.
- **Shift correction.** `frame_offset = start_frame_int - 1`, not `start_frame_int` (the 260420-uzv value). This is because Flame's `bake_animation=True` emits KTime 0 as pre-roll and KTime 1 as source `start_frame`, so the shift needed to move KTime 1 to user-facing `start_frame` is `start_frame - 1`, not `start_frame`.
- **Inclusive pre-roll drop.** `frame_start = start_frame_int` drops the now-offset-shifted KTime 0 (which lands at `start_frame - 1`).
- **Composable no-op fallback.** On any error, BOTH `frame_offset=0` AND `frame_start=None`. Slightly worse than the 260420-uzv-only state (that fallback was `frame_offset=0` with no clip), but the ONLY fallback that composes cleanly — a partial fallback where `frame_start=start_frame_int` survived but `frame_offset=0` took the default would silently drop every real frame (every KTime lands at 0..N, all dropped by `frame < start_frame_int`).
- The `int(float(x))` coercion is preserved (handles int, float, numeric string).

The 260421-bhg `frame_end` block at lines 2127-2141 is **untouched** — this plan only modifies the `start_frame` block.

The `fbx_to_v5_json(...)` call site now includes `frame_start=frame_start` positioned between `frame_offset=frame_offset` and `frame_end=frame_end` (matches the new parameter order on the public signature).

### 3. `tests/test_fbx_ascii.py`

Added `TestFbxToV5JsonFrameStart` (4 tests) immediately after `TestFbxToV5JsonFrameEnd`, mirroring its `_FIXTURE` / `_COMMON_KWARGS` pattern. All four tests use the live-Flame `forge_fbx_baked.fbx` fixture (keyed branch of `_merge_curves` — exercises the real Flame `bake_animation=True` shape including the KTime 0 pre-roll).

| Test | Asserts |
| ---- | ------- |
| `test_a_uat_preroll_drop_and_shift_correction` | **The UAT regression guard.** Reads a no-offset baseline, captures the SECOND baseline frame's Xpos (the first REAL sample's pose at KTime 1). Calls with `frame_offset=1000, frame_start=1001, frame_end=1001 + baseline_last - 1` and asserts: (a) first surviving frame == 1001 (pre-roll at offset-adjusted 1000 was dropped); (b) **Xpos at frame 1001 == the KTime 1 baseline Xpos** (if someone reverts `frame_offset = start_frame - 1` back to `start_frame`, this goes red because frame 1001 would show the pre-roll pose); (c) exactly one frame (the pre-roll) was dropped; (d) every emitted frame is in `[frame_start, frame_end]`. |
| `test_b_none_default_is_no_op` | Explicit `frame_start=None` is identical to omitting the kwarg — regression guard preserving the 260421-bhg post-state. Checks both frame numbers AND positions match field-by-field. |
| `test_c_inclusive_boundary_keeps_boundary_frame` | `frame_offset=1001, frame_start=1001 + baseline_first` — the boundary equals the minimum offset-adjusted frame. Under STRICT `<`, ALL frames survive. If `<` is changed to `<=`, the boundary frame gets dropped and this goes red (baseline_count - 1 instead of baseline_count). |
| `test_d_frame_start_above_all_yields_empty` | `frame_offset=0, frame_start=baseline_last + 1` — all frames drop. Result is `[]`, not `None`, not a crash. Mirror of `TestFbxToV5JsonFrameEnd.test_c_frame_end_below_min_yields_empty`. |

## Test Counts

| Scope | Before | After | Delta |
| ----- | -----: | ----: | ----: |
| Full suite (`pytest tests/ -q`) | 276 | **280** | +4 |
| `tests/test_fbx_ascii.py` | 63 | **67** | +4 |
| `test_fbx_io.py + test_solver.py + test_hook_parity.py` (untouched modules — regression check) | 116 | 116 | 0 |

`python -m py_compile flame/camera_match_hook.py` exits 0.

## Static Verification (grep checks from PLAN.md)

- `forge_flame/fbx_ascii.py`: `frame_start` appears on both signatures (617, 776), both guards (675, 709), inner call (861), and docstrings (634-642, 817-827). STRICT `frame < frame_start` appears at lines 675 and 709 (two matches — static + keyed paths).
- `flame/camera_match_hook.py`: `frame_start` appears in the modified defensive block (init at 2133, `start_frame_int` driven assignment at 2141, except-fallback at 2144) and in the `fbx_to_v5_json` kwarg at 2174. `frame_offset = start_frame_int - 1` at line 2140 (the shift-correction regression guard). `grep -c "flame\.batch\.start_frame\.get_value\(\)" flame/camera_match_hook.py` returns **1** — single read, not duplicated.
- Clip-after-offset ordering confirmed by inspection: both paths compute `frame = (KTime/0-based) + frame_offset` BEFORE the `frame_start`/`frame_end` comparisons. Same correctness rule as 260421-bhg.

## Untouched (Per Plan Non-Goals)

- **`bake_animation=True`** — kept; the 101-KTime emit (including the pre-roll at KTime 0) is Flame's baseline behavior. This plan interprets and clips it correctly; it does NOT change what Flame bakes.
- **`tools/blender/bake_camera.py`** — kept; it derives scene `frame_start` / `frame_end` from JSON `min(frame)` / `max(frame)`, so dropping the pre-roll in the v5 JSON automatically tightens the Blender scene range with no Blender-side changes.
- **`./install.sh`** — user owns deployment; plan ended at "tests pass".
- **260421-bhg's `frame_end` block** (lines 2127-2141) — left untouched; this plan only modifies the `start_frame` block from 260420-uzv.
- **`frame_offset` semantic at the call site in `fbx_to_v5_json`** — still "added to every emitted frame value". The `start_frame - 1` logic lives entirely in the Flame hook, not in the library. Other callers (tests, future tooling) can still pass `frame_offset=N` without implicit shift behavior.

## Deviations from Plan

None — plan executed exactly as written. TDD cycle ran cleanly:

1. **RED:** Added the 4-test `TestFbxToV5JsonFrameStart` class. Ran `pytest tests/test_fbx_ascii.py::TestFbxToV5JsonFrameStart -x` — failed at Test A with the expected `TypeError: fbx_to_v5_json() got an unexpected keyword argument 'frame_start'`.
2. **GREEN:** Applied the three production edits (signatures, both-path guards, hook in-place modification, call-site kwarg thread). Re-ran — all 4 new tests passed first try.
3. **Regression check:** Full suite: 280/280 green (was 276 pre-fix).

No iteration, no auto-fixes, no deferred items.

## Inclusive Semantic — Enforced by Test C + Shift Correction Enforced by Test A

**Two regression guards are locked into the test suite:**

1. **INCLUSIVE `frame_start`** (`frame < frame_start` drop, NOT `frame <= frame_start`). If someone "helpfully" changes `<` to `<=`, Test C fails (baseline_count - 1 surviving instead of baseline_count). The semantic lives in code (both guards), docstrings (`_merge_curves` + `fbx_to_v5_json`), AND Test C.

2. **`frame_offset = start_frame - 1`** at the hook (not `start_frame`). If someone reverts the `- 1` back to the 260420-uzv value, Test A fails at the Xpos assertion — frame 1001 would then show the KTime 0 pre-roll pose instead of the KTime 1 real-sample pose. The semantic lives in hook code AND Test A's Xpos assertion.

## Defensive Fallback — Manual Trace (cannot unit-test without mocking `flame`)

Same rationale as 260420-uzv / 260421-bhg — `flame` is a runtime singleton the test harness doesn't mock. The `(frame_offset, frame_start)` pair must degrade together.

| Scenario | Path | frame_offset | frame_start |
| -------- | ---- | -----------: | ----------: |
| `flame.batch.start_frame` missing (`AttributeError`) | caught | `0` | `None` |
| `get_value()` returns `1001` (int) | `int(float(1001))` = 1001 | `1000` | `1001` |
| `get_value()` returns `"1001"` (str) | `int(float("1001"))` = 1001 | `1000` | `1001` |
| `get_value()` returns `1001.0` (float) | `int(float(1001.0))` = 1001 | `1000` | `1001` |
| `get_value()` returns `None` | `float(None)` raises `TypeError` | `0` | `None` |
| `get_value()` raises | propagates into `try` | `0` | `None` |

The paired `(0, None)` fallback reproduces the strict pre-260420-uzv state (zero-based KTime stream, no clipping). Slightly worse than the 260420-uzv-only fallback used by 260421-bhg for `frame_end` (that one kept `frame_offset=0` but let `frame_end=None`), but the ONLY composable no-op — a partial fallback where `frame_start=start_frame_int` survived while `frame_offset=0` defaulted would silently drop every real frame (offset-adjusted frames 0..N all fail `frame < 1001`). Paired no-op is the safe choice. On any error, the user's export still works — the KTime stream comes through zero-based and un-clipped, identical to the pre-260420-uzv baseline.

## Hypothesis-Driven Fix — Follow-up UAT Recommended

This fix is based on matching the user's UAT symptoms (Xpos=1552 at Blender frame 1003 when expected at 1002, apparent duplicate at 1001, missing source-1100 sample) to the bake-shape hypothesis "KTime 0 is pre-roll, real samples live at KTimes 1..N". That hypothesis explains ALL observed symptoms and matches the standard Flame `bake_animation=True` behavior, but the **sparse-key case has not been probed**.

**Recommended follow-up UAT after deploy.** Probe a batch whose user-keyframed poses do NOT start at `batch.start_frame`. Example: batch 1001..1100 with the user only keyed at source frames 1010 and 1090 (sparse keys mid-range). If the fix generalizes, the v5 JSON should show frames 1001..1100 with interpolated poses between the two keys and no stray frames. If Flame emits a different shape for sparse-key bakes (e.g., only 2 KTimes total, or a different pre-roll pose), a fourth fix may be needed — **not blocking this plan per user approval.**

## Deployment & UAT

`./install.sh` is **owned by the user**, not this plan. No deploy command was run. User-side UAT against the same 1001..1100 batch that surfaced this bug will confirm:

1. Open an Action with a baked animated camera in a Flame batch spanning 1001..1100.
2. Right-click Action -> Camera Match -> Export Camera to Blender.
3. Open the resulting `.blend`:
   - Exactly **100 keyframes** at frames **1001..1100** (no stray 1101, no stray 1000, no duplicate at 1001).
   - **Pose at Blender frame 1002 matches source frame 1002's real Xpos (=1552 per the UAT report)**, NOT the pre-roll pose that previously appeared at 1003.
   - Blender scene `frame_start = 1001`, `frame_end = 1100` (set by `bake_camera.py` from JSON `min(frame)` / `max(frame)` — tightens automatically when the v5 JSON's frame range tightens).
4. The first real-sample pose lands on frame 1001 (previously landed on 1002 because the pre-roll was occupying 1001).

Should any of these fail, the `frame_offset = start_frame - 1` hypothesis is wrong for the probed batch shape and a follow-up task is needed.

## Self-Check: PASSED

**Files exist:**
- `forge_flame/fbx_ascii.py` (modified; `frame_start` appears 17x via grep — signatures, docstrings, both guards, inner call)
- `flame/camera_match_hook.py` (modified; `frame_start` / `start_frame_int` appear 9x — init, assignment, except-fallback, kwarg; `frame_offset = start_frame_int - 1` appears exactly once)
- `tests/test_fbx_ascii.py` (modified; `TestFbxToV5JsonFrameStart` class with 4 tests at line ~1118+)
- `.planning/quick/260421-c1w-fix-fbx-bake-pre-roll-frame-shift-frame-/260421-c1w-SUMMARY.md` (this file)

**Commit exists:** `61b3e8c` — `git log --oneline -1` shows `feat(quick-260421-c1w): drop FBX bake pre-roll and correct frame shift via frame_start`.

**All success criteria from PLAN.md met:**
- [x] `_merge_curves` and `fbx_to_v5_json` both accept `frame_start: Optional[int] = None` (keyword-only, positioned BEFORE `frame_end`).
- [x] BOTH `_merge_curves` code paths (static fallback, keyed loop) apply `frame_start` AFTER `frame_offset` is added. Filter order: `frame_start` first, then `frame_end`.
- [x] Drop condition uses STRICT `frame < frame_start` (INCLUSIVE lower bound — boundary frame kept). Appears in both paths.
- [x] `fbx_to_v5_json` threads `frame_start` to the inner `_merge_curves(..., frame_start=frame_start, frame_end=frame_end)` call.
- [x] Docstrings on `_merge_curves` and `fbx_to_v5_json` explain the `frame_start` semantic, its INCLUSIVE nature, the symmetric pairing with `frame_end`, and the `frame_offset = start_frame - 1` pairing.
- [x] Hook's existing `start_frame` defensive block modified in place (NOT duplicated). One read of `flame.batch.start_frame.get_value()` drives both `frame_offset = start_frame_int - 1` AND `frame_start = start_frame_int`. `grep -c "flame\.batch\.start_frame\.get_value\(\)" flame/camera_match_hook.py` returns **1**.
- [x] Except-branch falls back to BOTH `frame_offset = 0` AND `frame_start = None` (composable no-op).
- [x] `fbx_to_v5_json(...)` call now includes `frame_start=frame_start` between `frame_offset=frame_offset` and `frame_end=frame_end`.
- [x] New `TestFbxToV5JsonFrameStart` class with 4 tests (UAT pre-roll drop + Xpos shift guard, None default no-op, inclusive boundary, empty result).
- [x] `pytest tests/ -q` passes (280 / 280; was 276).
- [x] `pytest tests/test_fbx_ascii.py -q` passes (67 / 67; was 63).
- [x] `python -m py_compile flame/camera_match_hook.py` exits 0.
- [x] No changes to `bake_animation=True`, `tools/blender/bake_camera.py`, `./install.sh`, or 260421-bhg's `frame_end` block.
