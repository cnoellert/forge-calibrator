---
mode: quick
slug: 260421-bhg-clip-fbx-bake-trailing-frame-to-flame-ba
type: execute
wave: 1
depends_on: []
files_modified:
  - forge_flame/fbx_ascii.py
  - flame/camera_match_hook.py
  - tests/test_fbx_ascii.py
autonomous: true
requirements:
  - QUICK-260421-bhg-FRAMEEND
must_haves:
  truths:
    - "fbx_to_v5_json accepts a `frame_end: Optional[int] = None` kwarg (INCLUSIVE upper bound); None = no clipping, preserves pre-fix behavior"
    - "_merge_curves accepts `frame_end: Optional[int] = None`, applies the clip AFTER adding frame_offset, and uses the INCLUSIVE condition `frame <= frame_end`"
    - "_merge_curves applies frame_end to BOTH the static-fallback path AND the keyed path (symmetric with frame_offset wiring from 260420-uzv)"
    - "_export_camera_to_blender reads flame.batch.end_frame.get_value() immediately after the existing start_frame block, using the same defensive int(float(x)) + except-Exception pattern, falling back to None (NOT 0 — None means don't clip, 0 would accidentally drop everything)"
    - "_export_camera_to_blender passes `frame_end=frame_end` through to fbx_ascii.fbx_to_v5_json alongside the existing frame_offset kwarg"
    - "A new test asserts a batch with frame_offset=1001 + frame_end=1100 produces exactly 100 frames with max frame == 1100 (reproduces the UAT scenario — errant 1101 keyframe is dropped)"
    - "A regression test asserts frame_end=None (default) preserves pre-fix count on the existing forge_fbx_baked.fbx fixture"
    - "An edge-case test asserts frame_end below the minimum offset-adjusted frame yields zero frames (doesn't crash, returns empty list)"
    - "A boundary test asserts frame_end equal to the minimum offset-adjusted frame yields exactly one frame (inclusive boundary)"
    - "Full pytest suite passes (272 passing pre-fix from 260420-uzv; should be 276 post-fix)"
  artifacts:
    - path: "forge_flame/fbx_ascii.py"
      provides: "frame_end kwarg threaded through fbx_to_v5_json -> _merge_curves; clip applied after frame_offset"
      contains: "frame_end"
    - path: "flame/camera_match_hook.py"
      provides: "Defensive read of flame.batch.end_frame.get_value() symmetric with existing start_frame read"
      contains: "end_frame"
    - path: "tests/test_fbx_ascii.py"
      provides: "Frame-end clip test coverage (exact UAT scenario, None default, empty-result edge, inclusive boundary)"
      contains: "frame_end"
  key_links:
    - from: "_export_camera_to_blender"
      to: "fbx_ascii.fbx_to_v5_json"
      via: "frame_end=<read from flame.batch.end_frame, fallback None>"
      pattern: "frame_end\\s*=\\s*frame_end"
    - from: "fbx_to_v5_json"
      to: "_merge_curves"
      via: "passes frame_end through"
      pattern: "_merge_curves\\(.*frame_end"
    - from: "_merge_curves keyed path"
      to: "emitted frame field"
      via: "offset applied first, then clip: `frame = frame_from_ktime(...) + frame_offset; if frame_end is not None and frame > frame_end: continue`"
      pattern: "frame_from_ktime\\([^\\n]*\\+\\s*frame_offset[\\s\\S]{0,400}frame_end"
    - from: "_merge_curves filter order"
      to: "correctness"
      via: "clip uses INCLUSIVE `frame > frame_end` (drop) — NOT `frame >= frame_end` (which would drop the last frame the user wants)"
      pattern: "frame\\s*>\\s*frame_end"
---

<objective>
Drop the single errant trailing keyframe that shows up one frame past the Flame batch's `end_frame` in the FBX-derived v5 JSON, by threading a `frame_end` clip (INCLUSIVE) through the same wiring that quick task 260420-uzv added for `frame_offset`.

Purpose: UAT on the 260420-uzv deploy confirmed the start-of-range fix works (Blender now receives frames 1001..N), but surfaced a second issue at the TAIL of the range: `action.export_fbx(bake_animation=True)` bakes `(end - start + 1)` KTimes (0..100 for an inclusive 1001..1100 batch), and after the +1001 offset that becomes 1001..1101 — one frame beyond the user's batch end. User's verbatim report: "I seem to still have a errant keyframe at 1101". The dense-key behavior is correct per the user; only the TAIL needs clipping.

Output: A `frame_end: Optional[int] = None` kwarg on `fbx_to_v5_json` (threaded to `_merge_curves`) that, when non-None, drops any frame whose POST-OFFSET value exceeds `frame_end`. The Flame-side handler populates it from `flame.batch.end_frame.get_value()` using the same defensive `int(float(x))` + blanket `except Exception` pattern the predecessor established for `start_frame`. Four new tests cover the UAT scenario, the None-default regression, the empty-result edge, and the inclusive-boundary case.

Non-goals (per user, explicit):
- Do NOT change `bake_animation=True`. The 101-key density on a 1001..1100 range is the density the user wants — the fix is a TAIL clip, not a re-baking.
- Do NOT modify `tools/blender/bake_camera.py`. It already derives scene range from JSON via min/max of `frames[*].frame`; drop the trailing frame in the v5 JSON and the Blender side reads the correct range.
- Do NOT include `./install.sh` deploy as a task. User owns deployment; plan ends at "tests pass".
- Do NOT rewire `frame_offset` — that landed in 260420-uzv and is out of scope. Build on top of it.

Semantic decision (locked): `frame_end` is INCLUSIVE. For a batch of 1001..1100 the output must contain frames 1001, 1002, ..., 1100 (100 frames). The drop condition is `frame > frame_end`, NOT `frame >= frame_end`. Clip applies AFTER `frame_offset` is added, so the comparison is against the user-facing (plate) frame number, not the raw FBX KTime index.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@CLAUDE.md
@memory/flame_keyframe_api.md
@forge_flame/fbx_ascii.py
@flame/camera_match_hook.py
@tests/test_fbx_ascii.py
@.planning/quick/260420-uzv-preserve-flame-batch-start-frame-in-fbx-/260420-uzv-PLAN.md
@.planning/quick/260420-uzv-preserve-flame-batch-start-frame-in-fbx-/260420-uzv-SUMMARY.md

<interfaces>
<!-- Key contracts the executor needs. Extracted from the codebase so no exploration is required. -->

**This plan is the symmetric follow-up to 260420-uzv.** The `frame_offset` wiring is already in place — read `260420-uzv-SUMMARY.md` first to internalize the exact shape, then mirror it for `frame_end`.

From forge_flame/fbx_ascii.py — CURRENT state (frame_offset already wired, frame_end to be added):

```python
# Line 611-617 — current signature (frame_offset already present):
def _merge_curves(
    cam: _CameraExtract,
    root: list[FBXNode],
    frame_rate: str,
    *,
    frame_offset: int = 0,
    # <-- ADD: frame_end: Optional[int] = None
) -> list[dict[str, Any]]:
    ...

# Line 642-653 — static-fallback path (frame_offset already applied):
if not any_keyed:
    frame = frame_offset
    sp = cam.static_position
    sr = cam.static_rotation
    film_back_mm = _inches_to_mm(cam.film_height_inches)
    focal_mm = _focal_from_fov_filmback(cam.field_of_view, film_back_mm)
    return [{
        "frame": frame,
        "position": [sp[0], sp[1], sp[2]],
        "rotation_flame_euler": [sr[0], sr[1], sr[2]],
        "focal_mm": focal_mm,
    }]
    # <-- ADD a guard BEFORE the return: if frame_end is not None and frame > frame_end: return []
    # (static path only emits one frame, so the guard is a "return [] or return [...]"
    # decision — apply for symmetry and defensive correctness.)

# Line 663-680 — keyed path (frame_offset already applied):
out: list[dict[str, Any]] = []
for ktime in sorted_times:
    frame = frame_from_ktime(ktime, frame_rate) + frame_offset
    # <-- ADD immediately after: if frame_end is not None and frame > frame_end: continue
    px = _sample_at(tx, ktime, cam.static_position[0])
    ...
    out.append({...})
return out

# Line 718-769 — current signature (frame_offset already present):
def fbx_to_v5_json(
    fbx_path: str,
    out_json_path: str,
    *,
    width: int = 0,
    height: int = 0,
    film_back_mm: Optional[float] = None,
    frame_rate: str = "23.976 fps",
    camera_name: Optional[str] = None,
    custom_properties: Optional[dict] = None,
    frame_offset: int = 0,
    # <-- ADD: frame_end: Optional[int] = None
) -> dict:
    ...
    # Line 787 — current call (thread frame_end through here too):
    frames = _merge_curves(cam, tree, frame_rate, frame_offset=frame_offset)
    # <-- BECOMES: _merge_curves(cam, tree, frame_rate, frame_offset=frame_offset, frame_end=frame_end)
```

From flame/camera_match_hook.py — CURRENT state (start_frame defensive read at lines 2105-2125 already in place):

```python
# Lines 2105-2125 — existing frame_offset block from 260420-uzv:
# --- Frame offset — preserve Flame batch's start_frame so the
# round-trip surfaces real plate frame numbers in Blender, not
# zero-based KTime. ... ---
frame_offset = 0
try:
    sf = flame.batch.start_frame.get_value()
    frame_offset = int(float(sf))
except Exception:
    frame_offset = 0  # silent fallback; do not surface to user

# <-- ADD IMMEDIATELY AFTER (before the fbx_to_v5_json call at line 2132):
# --- Frame end — preserve Flame batch's end_frame so we drop any
# trailing keyframe bake_animation=True emits beyond the user's
# batch range. Flame bakes (end - start + 1) KTimes which after the
# +start_frame offset lands one frame past end. Same defensive
# shape as start_frame above; fallback is NONE (not 0) — None means
# "don't clip", preserving pre-fix behavior on any error. 0 would
# incorrectly drop every frame. ---
frame_end = None
try:
    ef = flame.batch.end_frame.get_value()
    frame_end = int(float(ef))
except Exception:
    frame_end = None  # silent fallback; None = no clip

# Lines 2132-2143 — existing fbx_to_v5_json call (add frame_end=frame_end):
fbx_ascii.fbx_to_v5_json(
    fbx_path, json_path,
    width=width, height=height,
    film_back_mm=36.0,
    camera_name=raw_cam_name,
    frame_offset=frame_offset,
    frame_end=frame_end,  # <-- ADD
    custom_properties={
        "forge_bake_action_name": raw_action_name,
        "forge_bake_camera_name": raw_cam_name,
    },
)
```

**Precedent:** `flame.batch.end_frame` follows the same `PyAttribute.get_value()` shape as `flame.batch.start_frame` (already probed and working in the same function) and `flame.batch.width` / `flame.batch.height` (used in `_infer_plate_resolution` lines 1883-1905). The defensive try/except handles missing attr, raises, None, and non-numeric returns via `int(float(x))`.

From tests/test_fbx_ascii.py — CURRENT `TestFbxToV5JsonFrameOffset` class (line 807-919) already exists. Mirror its structure:

```python
# Existing pattern — line 832-838:
class TestFbxToV5JsonFrameOffset:
    _FIXTURE = os.path.join(FIXTURE_DIR, "forge_fbx_baked.fbx")
    _COMMON_KWARGS = dict(
        width=1920,
        height=1080,
        film_back_mm=36.0,
        camera_name="Default",
    )
    # ...four existing tests: test_a_offset_shifts_frames, test_b_default_offset_is_zero,
    # test_c_on_disk_parity, test_d_large_negative_offset
```

Planner decision: ADD a new sibling class `TestFbxToV5JsonFrameEnd` (do NOT extend the existing class — the existing class is about `frame_offset` semantics; `frame_end` is a separate concern that composes with `frame_offset`, and a separate class keeps the intent grep-able). Use the same `_FIXTURE` and `_COMMON_KWARGS` constants.

The `forge_fbx_baked.fbx` fixture has a small number of keyframes (two-endpoint baked animation), so to reproduce the UAT 1001..1101 -> 1001..1100 scenario we lean on the fact that the fixture's keyed frame range, combined with `frame_offset=1001 + frame_end=<fixture_last - 1>`, can produce a clipped result. The more robust approach is to compute the expected count from the no-offset baseline and assert relative behavior — see `<behavior>` in the task for exact test shapes.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Thread frame_end through fbx_to_v5_json + _merge_curves, add tests, wire hook</name>
  <files>
    forge_flame/fbx_ascii.py,
    flame/camera_match_hook.py,
    tests/test_fbx_ascii.py
  </files>
  <behavior>
    Tests to add to tests/test_fbx_ascii.py. Place a NEW sibling class
    `TestFbxToV5JsonFrameEnd` immediately after the existing
    `TestFbxToV5JsonFrameOffset` class (~line 919). Reuse the same
    `_FIXTURE` and `_COMMON_KWARGS` constants by either:
      (a) copying them at the top of the new class (simplest, mirrors
          the existing pattern), OR
      (b) referring to the constants on the existing class —
          `TestFbxToV5JsonFrameOffset._FIXTURE`. Either is acceptable;
          pick whichever reads cleanest.

    All four tests use `forge_fbx_baked.fbx` (the live-Flame
    `bake_animation=True` fixture — exercises the KEYED branch of
    `_merge_curves`):

    - **Test A — exact UAT scenario (offset + end clip):** Read the
      no-offset, no-clip baseline first to discover the fixture's
      natural last frame, call it `baseline_last`. Then call
      `fbx_to_v5_json(..., frame_offset=1001, frame_end=1001 + baseline_last - 1)`.
      Assert:
        - the returned `frames` list's max `frame` equals
          `1001 + baseline_last - 1` (proves INCLUSIVE upper bound —
          the boundary frame is KEPT, not dropped).
        - the returned `frames` list is exactly ONE shorter than the
          no-clip baseline (proves exactly one trailing frame was
          dropped — the UAT symptom).
        - every `frame` in the result satisfies `frame <= 1001 + baseline_last - 1`.
      This test is the direct analog of the user's 1001..1101 -> 1001..1100
      scenario: offset pushes the range up, clip drops the single
      trailing key that's one frame past the user's end.

    - **Test B — default (None) is no-op (regression guard):** Call
      `fbx_to_v5_json(..., **_COMMON_KWARGS)` with NO `frame_end`
      kwarg. Capture `frames`. Then call again with explicit
      `frame_end=None`. Assert the two `frames` lists are identical
      (proves the kwarg defaults to None and None is a no-op —
      260420-uzv regression protection).

    - **Test C — empty result when frame_end is below the min
      offset-adjusted frame (edge case — don't crash):** Call with
      `frame_offset=1001, frame_end=0`. Since every keyed frame has
      `frame >= 1001` after offset and `1001 > 0`, ALL frames are
      dropped. Assert `result["frames"] == []` (empty list, not a
      crash, not a None). This prevents a future "helpful" guard
      from raising on empty results — the empty case is legitimate.

    - **Test D — inclusive boundary (one-frame result):** Compute the
      no-offset baseline's FIRST frame (`baseline_first`) and call
      with `frame_offset=1001, frame_end=1001 + baseline_first`.
      Since every frame is >= `1001 + baseline_first`, and the filter
      is INCLUSIVE (`frame <= frame_end`), exactly the first frame
      survives. Assert `len(result["frames"]) == 1` AND
      `result["frames"][0]["frame"] == 1001 + baseline_first`. This
      locks in the inclusive-comparison semantics — if someone
      "helpfully" changes `>` to `>=` in the drop condition, this
      test goes red.

    All four tests will RED on a clean checkout with
    `TypeError: unexpected keyword argument 'frame_end'` — that's
    the RED state before production code is edited.
  </behavior>
  <action>
    Three coordinated edits. Write tests FIRST (TDD RED), then
    production code (GREEN), then run `pytest` once and confirm pass.

    **STEP 1 — Add TestFbxToV5JsonFrameEnd to tests/test_fbx_ascii.py** (RED).

    Place the new class immediately after `TestFbxToV5JsonFrameOffset`
    (~line 919). Use the same `FIXTURE_DIR` / `_COMMON_KWARGS` pattern.
    Add a class docstring that references the UAT cause (trailing
    frame at 1101 for a 1001..1100 batch; `bake_animation=True` emits
    `end - start + 1` KTimes which after the +start_frame offset
    overshoots by one) so future readers understand why this exists.

    Each test must do a "no-offset baseline first, then the clipped
    call" pattern so we discover the fixture's natural frame range
    at runtime instead of hard-coding it — if the fixture ever
    regenerates with a different key density, these tests still
    assert correct RELATIVE behavior. See `<behavior>` for the
    four tests.

    **STEP 2 — Edit forge_flame/fbx_ascii.py**:

    (a) Add `Optional` to the import line at the top of the file if
        not already present (grep first — it likely already is,
        since `film_back_mm: Optional[float]` exists on
        `fbx_to_v5_json`).

    (b) `_merge_curves` (~line 611-617): add a keyword-only
        `frame_end: Optional[int] = None` parameter AFTER
        `frame_offset: int = 0`. Signature becomes:

        ```python
        def _merge_curves(
            cam: _CameraExtract,
            root: list[FBXNode],
            frame_rate: str,
            *,
            frame_offset: int = 0,
            frame_end: Optional[int] = None,
        ) -> list[dict[str, Any]]:
        ```

        - Static-fallback path (~line 642-653): AFTER
          `frame = frame_offset` (line 643), add a guard that returns
          `[]` when `frame_end is not None and frame > frame_end`.
          Insert the guard BEFORE the existing `sp = cam.static_position`
          line so the early-out skips the unnecessary film-back math.
          Apply for symmetry with the keyed path even though in
          practice the static path almost never hits this (a static
          camera in a Flame batch with start_frame > end_frame is
          degenerate).

        - Keyed path (~line 663-680): the current line
          `frame = frame_from_ktime(ktime, frame_rate) + frame_offset`
          stays as-is. Immediately after it, insert:
          ```python
          if frame_end is not None and frame > frame_end:
              continue
          ```
          This is the ONLY correctness-critical ordering rule in
          this plan: the clip MUST happen AFTER the offset is added,
          because `frame_end` is a user-facing plate frame number
          (from `flame.batch.end_frame`), not a raw FBX KTime index.
          Compare against `frame` (post-offset), NOT against
          `frame_from_ktime(ktime, frame_rate)` (pre-offset).

        - Update the function docstring (~line 618-631): append a
          sentence: "If ``frame_end`` is not None, any frame whose
          POST-OFFSET value exceeds it is dropped (INCLUSIVE upper
          bound — ``frame == frame_end`` is kept; only
          ``frame > frame_end`` is dropped). This is how the Flame
          batch's ``end_frame`` trims the single trailing keyframe
          that ``action.export_fbx(bake_animation=True)`` bakes past
          the user's range — Flame emits ``(end - start + 1)`` KTimes
          which, after the +``start_frame`` offset, lands one frame
          past end. Clip applies after the offset so the comparison
          is against the user-facing plate frame number."

    (c) `fbx_to_v5_json` (~line 718-769): add
        `frame_end: Optional[int] = None` keyword-only parameter
        AFTER `frame_offset: int = 0`. Update the call at line 787:
        ```python
        frames = _merge_curves(
            cam, tree, frame_rate,
            frame_offset=frame_offset,
            frame_end=frame_end,
        )
        ```
        Update the docstring `Args:` block: add a `frame_end` entry
        explaining "Optional INCLUSIVE upper bound on emitted
        `frame` values. Applied AFTER `frame_offset`. Any frame
        whose post-offset value exceeds `frame_end` is dropped.
        Default None (no clipping — preserves pre-260421-bhg
        behavior). Set to the Flame batch's `end_frame` to trim
        the trailing keyframe that `action.export_fbx(bake_animation=True)`
        bakes past the user's range."

    **STEP 3 — Edit flame/camera_match_hook.py** (`_export_camera_to_blender`,
    immediately after the existing `start_frame` defensive block at
    line 2117-2125, BEFORE the `fbx_ascii.fbx_to_v5_json(...)` call
    at line 2132):

    Insert this symmetric block:

    ```python
    # --- Frame end — drop the single trailing keyframe that
    # bake_animation=True bakes past the user's batch range.
    # Flame emits (end - start + 1) KTimes; after the +start_frame
    # offset above, that's one frame past end. Read end_frame with
    # the same defensive shape as start_frame. Fallback is None
    # (NOT 0) — None means "don't clip", preserving pre-fix behavior
    # on any error; 0 would incorrectly drop every frame. ---
    frame_end = None
    try:
        ef = flame.batch.end_frame.get_value()
        frame_end = int(float(ef))
    except Exception:
        frame_end = None  # silent fallback; None = no clip
    ```

    Then update the `fbx_ascii.fbx_to_v5_json(...)` call (~line 2132-2143)
    to add `frame_end=frame_end,` as a kwarg alongside the existing
    `frame_offset=frame_offset,`:

    ```python
    fbx_ascii.fbx_to_v5_json(
        fbx_path, json_path,
        width=width, height=height,
        film_back_mm=36.0,
        camera_name=raw_cam_name,
        frame_offset=frame_offset,
        frame_end=frame_end,
        custom_properties={
            "forge_bake_action_name": raw_action_name,
            "forge_bake_camera_name": raw_cam_name,
        },
    )
    ```

    `flame` is already imported in this scope (same as 260420-uzv used
    it for `start_frame`); no new import needed.

    **Why fallback is None, not 0:**
    The predecessor 260420-uzv used `frame_offset = 0` as its fallback
    because 0 is the valid no-op sentinel for an integer offset. Here
    the no-op sentinel is None — the `frame_end: Optional[int] = None`
    signature says "pass None to mean don't clip". Using 0 as the
    fallback would cause an unreadable FBX to silently drop every
    frame on error, which is a worse failure mode than "offset
    applied, no clip" (which reproduces pre-fix behavior — the status
    quo we are improving on).
  </action>
  <verify>
    <automated>cd /Users/cnoellert/Documents/GitHub/forge-calibrator &amp;&amp; pytest tests/test_fbx_ascii.py -x -q</automated>
  </verify>
  <done>
    - `pytest tests/test_fbx_ascii.py -x -q` passes (was 59 tests post-260420-uzv; should be 63 post-fix — 4 new TestFbxToV5JsonFrameEnd tests).
    - `pytest tests/ -x -q` passes (full suite; was 272 passing post-260420-uzv; should be 276 post-fix).
    - `python -m py_compile flame/camera_match_hook.py` exits 0.
    - `grep -n "frame_end" forge_flame/fbx_ascii.py` shows: signature on `_merge_curves`, signature on `fbx_to_v5_json`, the static-fallback guard, the keyed-path `if frame_end is not None and frame > frame_end: continue`, and the `_merge_curves(..., frame_end=frame_end)` call at the v5 JSON entry point.
    - `grep -n "end_frame" flame/camera_match_hook.py` shows the new defensive read block inside `_export_camera_to_blender`, symmetric with the existing `start_frame` block.
    - `grep -n "frame_end" tests/test_fbx_ascii.py` shows the new `TestFbxToV5JsonFrameEnd` class with at least 4 tests.
    - The keyed-path drop condition is `frame > frame_end` (STRICT greater-than, NOT `>=`) — verified by grep and by Test D passing (inclusive boundary).
    - All four behavior tests (A: UAT scenario drops trailing frame, B: None default is no-op, C: all-dropped yields empty list, D: inclusive boundary keeps boundary frame) are present and pass.
    - No changes to `bake_animation=True`, no changes to `tools/blender/bake_camera.py`, no `./install.sh` invocation.
  </done>
</task>

</tasks>

<verification>

1. **Test suite green:**
   ```bash
   pytest tests/ -x -q
   ```
   Expected: all tests pass. Pre-fix baseline was 272 passing (per 260420-uzv SUMMARY). Post-fix baseline should be 276 passing (+4 new tests in `TestFbxToV5JsonFrameEnd`).

2. **Targeted file:**
   ```bash
   pytest tests/test_fbx_ascii.py -x -q
   ```
   Expected: previously 59, now 63. Test names visible in `-v` output should include four `TestFbxToV5JsonFrameEnd::test_*` entries covering UAT scenario, None default, empty result, inclusive boundary.

3. **Hook compiles:**
   ```bash
   python -m py_compile flame/camera_match_hook.py
   ```
   Expected: exit 0, no syntax errors.

4. **Frame-end wired end-to-end (static check):**
   ```bash
   grep -nE "frame_end|end_frame" forge_flame/fbx_ascii.py flame/camera_match_hook.py tests/test_fbx_ascii.py
   ```
   Expected matches:
   - `forge_flame/fbx_ascii.py`: signature additions on `_merge_curves` and `fbx_to_v5_json`, static-path guard, keyed-path `if frame_end is not None and frame > frame_end: continue`, the inner call threading it through.
   - `flame/camera_match_hook.py`: the new defensive read block reading `flame.batch.end_frame.get_value()` + the `frame_end=frame_end,` kwarg on `fbx_to_v5_json`.
   - `tests/test_fbx_ascii.py`: the new test class + at least one test with `frame_end=1001 + baseline_last - 1` (UAT scenario), one regression test with explicit `frame_end=None`, one edge-case test producing an empty list, and one inclusive-boundary test.

5. **INCLUSIVE semantics locked in (static check):**
   ```bash
   grep -n "frame\s*>\s*frame_end" forge_flame/fbx_ascii.py
   ```
   Expected: at least one match in `_merge_curves` using STRICT `>` (not `>=`). If someone later "helpfully" changes this to `>=`, Test D (inclusive boundary) will go red — belt and braces.

6. **Clip-after-offset ordering (static check):**
   ```bash
   grep -nE "frame_from_ktime|frame\s*=\s*frame_offset" forge_flame/fbx_ascii.py
   ```
   Confirm by eye that in both paths, the `frame` variable has `frame_offset` already added BEFORE the `frame_end` comparison line (and that the static-fallback's `frame = frame_offset` precedes its `frame_end` guard). This is the correctness-critical ordering — clip is against post-offset plate frame numbers.

7. **No regressions in untouched modules:**
   ```bash
   pytest tests/test_fbx_io.py tests/test_solver.py tests/test_hook_parity.py -q
   ```
   Expected: all green.

8. **Defensive fallback manual trace** (cannot unit-test without mocking the `flame` singleton — same rationale as 260420-uzv). Mentally verify:
   | Scenario | Path | Outcome |
   | -------- | ---- | ------- |
   | `flame.batch.end_frame` missing | `AttributeError` | caught -> `frame_end = None` (no clip) |
   | `get_value()` returns `1100` | `int(float(1100))` | `1100` (clip to 1100) |
   | `get_value()` returns `"1100"` | `int(float("1100"))` | `1100` |
   | `get_value()` returns `None` | `float(None)` raises `TypeError` | caught -> `frame_end = None` |
   | `get_value()` raises | exception propagates | caught -> `frame_end = None` |

   `frame_end = None` reproduces pre-fix behavior (offset applied, no clip), so the fallback degrades gracefully to the 260420-uzv state.

</verification>

<success_criteria>

- [ ] `forge_flame/fbx_ascii.py`: `_merge_curves` and `fbx_to_v5_json` both accept `frame_end: Optional[int] = None` (keyword-only, after `frame_offset`).
- [ ] `forge_flame/fbx_ascii.py`: BOTH code paths in `_merge_curves` apply `frame_end` AFTER `frame_offset` is added to `frame`. Static-fallback returns `[]` when the single frame exceeds the bound; keyed path uses `continue` to skip the drop.
- [ ] `forge_flame/fbx_ascii.py`: drop condition uses STRICT `frame > frame_end` (INCLUSIVE upper bound — boundary frame kept).
- [ ] `forge_flame/fbx_ascii.py`: `fbx_to_v5_json` threads `frame_end` to the inner `_merge_curves(..., frame_end=frame_end)` call.
- [ ] `flame/camera_match_hook.py`: `_export_camera_to_blender` reads `flame.batch.end_frame.get_value()` defensively, coerces via `int(float(...))`, falls back to `None` on ANY exception (note: fallback is `None`, NOT `0` — matches the `Optional[int]` signature semantic).
- [ ] `flame/camera_match_hook.py`: the `fbx_ascii.fbx_to_v5_json(...)` call now includes `frame_end=frame_end` as a kwarg alongside the existing `frame_offset=frame_offset`.
- [ ] `tests/test_fbx_ascii.py`: new `TestFbxToV5JsonFrameEnd` class (sibling of `TestFbxToV5JsonFrameOffset`) with 4 tests covering UAT scenario, None-default regression, empty-result edge, inclusive boundary.
- [ ] `pytest tests/ -x -q` passes (276 expected post-fix; 272 pre-fix + 4 new).
- [ ] `pytest tests/test_fbx_ascii.py -x -q` passes (63 expected post-fix; 59 pre-fix + 4 new).
- [ ] Docstrings updated on `_merge_curves` and `fbx_to_v5_json` to explain `frame_end` semantics (INCLUSIVE, post-offset, trims the trailing `bake_animation=True` key).
- [ ] No changes to `bake_animation=True`, no changes to `tools/blender/bake_camera.py`, no `./install.sh` invocation.

</success_criteria>

<output>
After completion, create `.planning/quick/260421-bhg-clip-fbx-bake-trailing-frame-to-flame-ba/260421-bhg-SUMMARY.md` summarizing:
- The three coordinated edits (fbx_ascii signatures + both-path clip, hook defensive end_frame read, test class).
- Test counts before/after (`pytest tests/ -q` numbers: 272 -> 276; `test_fbx_ascii.py` 59 -> 63).
- Confirmation that `bake_animation=True` and `bake_camera.py` were untouched.
- A note that the INCLUSIVE semantic (`frame > frame_end` drops, not `>=`) is enforced by Test D.
- A note that DEPLOY (running `./install.sh`) is owned by the user. User-side UAT against the same 1001..1100 batch that surfaced the bug will confirm the errant 1101 keyframe is gone.
- Defensive-fallback manual trace table (same shape as 260420-uzv summary), noting that `frame_end = None` reproduces pre-fix behavior (the 260420-uzv post-state) on any error.
</output>
