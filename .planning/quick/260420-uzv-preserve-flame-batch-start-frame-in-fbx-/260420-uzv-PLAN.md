---
mode: quick
slug: 260420-uzv-preserve-flame-batch-start-frame-in-fbx-
type: execute
wave: 1
depends_on: []
files_modified:
  - forge_flame/fbx_ascii.py
  - flame/camera_match_hook.py
  - tests/test_fbx_ascii.py
autonomous: true
requirements:
  - QUICK-260420-uzv-FRAMENUM
must_haves:
  truths:
    - "fbx_to_v5_json accepts a frame_offset kwarg (default 0) and adds it to every emitted `frame` value"
    - "_merge_curves applies frame_offset to BOTH the static-fallback path AND the keyed path"
    - "_export_camera_to_blender reads flame.batch.start_frame.get_value() and passes it through; if the read raises or returns a non-int it falls back to 0 and never crashes the export"
    - "A new test asserts a Flame batch starting at 1001 produces v5 JSON whose `frames[0].frame == 1001` (not 0)"
    - "A regression test asserts frame_offset=0 (default) preserves pre-fix behavior on the existing fixture"
    - "Full pytest suite passes (was 268 passing pre-fix; should be 270 post-fix)"
  artifacts:
    - path: "forge_flame/fbx_ascii.py"
      provides: "frame_offset kwarg threaded through fbx_to_v5_json -> _merge_curves"
      contains: "frame_offset"
    - path: "flame/camera_match_hook.py"
      provides: "Defensive read of flame.batch.start_frame.get_value() before fbx_to_v5_json call"
      contains: "start_frame"
    - path: "tests/test_fbx_ascii.py"
      provides: "TestFbxToV5JsonFrameOffset class covering offset application + zero-default regression"
      contains: "frame_offset"
  key_links:
    - from: "_export_camera_to_blender"
      to: "fbx_ascii.fbx_to_v5_json"
      via: "frame_offset=<read from flame.batch.start_frame, fallback 0>"
      pattern: "frame_offset\\s*="
    - from: "fbx_to_v5_json"
      to: "_merge_curves"
      via: "passes frame_offset through"
      pattern: "_merge_curves\\(.*frame_offset"
    - from: "_merge_curves keyed path"
      to: "emitted frame field"
      via: "frame = frame_from_ktime(...) + frame_offset"
      pattern: "frame_from_ktime\\(.*\\)\\s*\\+\\s*frame_offset"
    - from: "_merge_curves static path"
      to: "emitted frame field"
      via: "frame = frame_offset (was 0)"
      pattern: "\"frame\":\\s*frame_offset"
---

<objective>
Preserve the Flame batch's `start_frame` in the FBX-derived v5 JSON so a Flame batch with frame range 1001..1100 surfaces in Blender as frames 1001..1100, not 0..100.

Purpose: UAT on Phase 01 caught a fidelity gap that static verification missed. Flame's `action.export_fbx(bake_animation=True)` zero-bases the FBX KTime stream, so the existing read path in `_merge_curves` (via `frame_from_ktime`) emits 0..N-1. Compositors who expect to scrub on the original Flame frame numbers see misaligned frames. Round-trip fidelity — the project's stated core value — requires the frame numbers to match the source plate.

Output: A `frame_offset` kwarg on `fbx_to_v5_json` (and inner `_merge_curves`) that the Flame-side handler populates from `flame.batch.start_frame.get_value()`, with full test coverage of both the offset-applied and offset-zero (default) paths.

Non-goals (per user, explicit):
- Do NOT change `bake_animation=True`. The 101-key density on a 1001..1100 range is desired; only the frame numbering is wrong.
- Do NOT modify `tools/blender/bake_camera.py`. It already derives scene start/end from JSON `frames[*].frame` via min/max (`bake_camera.py:218-219`); fix the source numbers and the Blender side reads correctly with no changes.
- Do NOT include `./install.sh` deploy as a task. The user owns deployment; this plan ends at "tests pass".
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@CLAUDE.md
@memory/flame_keyframe_api.md
@forge_flame/fbx_ascii.py
@forge_flame/fbx_io.py
@flame/camera_match_hook.py
@tests/test_fbx_ascii.py
@.planning/phases/01-export-polish/01-VERIFICATION.md

<interfaces>
<!-- Key contracts the executor needs. Extracted from the codebase so no exploration is required. -->

From forge_flame/fbx_ascii.py:

```python
# Line ~611 — current signature, no offset:
def _merge_curves(
    cam: _CameraExtract,
    root: list[FBXNode],
    frame_rate: str,
) -> list[dict[str, Any]]:
    ...
    # Static-fallback path (~line 633-645):
    if not any_keyed:
        frame = 0                          # <-- becomes frame_offset
        ...
        return [{"frame": frame, ...}]
    ...
    # Keyed path (~line 655-672):
    for ktime in sorted_times:
        frame = frame_from_ktime(ktime, frame_rate)   # <-- add + frame_offset
        ...
        out.append({"frame": frame, ...})
    return out

# Line ~710 — current signature, no offset:
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
) -> dict:
    ...
    frames = _merge_curves(cam, tree, frame_rate)   # <-- thread frame_offset
    ...
```

From flame/camera_match_hook.py (around line 2110-2120, inside `_export_camera_to_blender`):

```python
# Existing call site — fbx is already on disk at fbx_path at this point:
fbx_ascii.fbx_to_v5_json(
    fbx_path, json_path,
    width=width, height=height,
    film_back_mm=36.0,
    camera_name=raw_cam_name,
    custom_properties={
        "forge_bake_action_name": raw_action_name,
        "forge_bake_camera_name": raw_cam_name,
    },
)
```

From flame/camera_match_hook.py (precedent for `flame.batch.<attr>.get_value()` access pattern, line ~1897-1903 in `_infer_plate_resolution`):

```python
# Same module, same Flame singleton — proves `flame.batch` PyAttribute reads:
import flame
try:
    b = flame.batch
    width = int(b.width.get_value())
    height = int(b.height.get_value())
    ...
except Exception:
    pass  # fall through
```

`flame.batch.start_frame` follows the same `PyAttribute.get_value()` shape used by
`flame.batch.width` / `flame.batch.height` above. **It is not yet probed** in
this codebase — guard the call defensively (catch ALL exceptions, validate
return is a number, fall back to 0). Do not crash the export to surface a
numbering issue.

From tests/test_fbx_ascii.py (existing fixture pattern to mirror, line ~701-799):

```python
class TestFbxToV5JsonCustomProperties:
    _FIXTURE = os.path.join(FIXTURE_DIR, "forge_fbx_baked.fbx")
    _COMMON_KWARGS = dict(
        width=1920, height=1080,
        film_back_mm=36.0,
        camera_name="Default",
    )
    def test_a_custom_properties_in_return_and_disk(self, tmp_path):
        json_path = tmp_path / "out.json"
        result = fbx_to_v5_json(self._FIXTURE, str(json_path), **self._COMMON_KWARGS, custom_properties=...)
        ...
```

The fixture `tests/fixtures/forge_fbx_baked.fbx` is the canonical
`bake_animation=True` baseline — it has two keyframe endpoints on each
curve, so `_merge_curves` exercises the **keyed** path (not the static
fallback). Both fixtures (`forge_fbx_baked.fbx`, `forge_fbx_probe.fbx`)
are present in `tests/fixtures/`.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Thread frame_offset through fbx_to_v5_json + _merge_curves, add tests, wire hook</name>
  <files>
    forge_flame/fbx_ascii.py,
    flame/camera_match_hook.py,
    tests/test_fbx_ascii.py
  </files>
  <behavior>
    Tests to add to tests/test_fbx_ascii.py (mirror the TestFbxToV5JsonCustomProperties
    pattern exactly — same _FIXTURE constant, same _COMMON_KWARGS, same tmp_path fixture):

    Add a new class `TestFbxToV5JsonFrameOffset` with:

    - Test A — offset_shifts_frames: call `fbx_to_v5_json(..., frame_offset=1001)`
      against `forge_fbx_baked.fbx`. Assert that the returned dict's `frames`
      list is non-empty AND `frames[0]["frame"] == 1001`. Assert that
      EVERY frame's number is `>= 1001` (defends against the +offset being
      applied to only some keys).

    - Test B — default_offset_is_zero (regression guard): call
      `fbx_to_v5_json(..., **_COMMON_KWARGS)` with NO frame_offset kwarg.
      Capture `frames[0]["frame"]`. Then call again WITH `frame_offset=0`.
      Assert the two results have identical `frame` fields (proves the
      kwarg defaults to 0 and that 0 is a no-op).

    - Test C — on-disk parity: same as Test A but ALSO read the on-disk JSON
      file (via `json.load`) and assert its `frames[0]["frame"] == 1001`. This
      proves the offset survives the full serialization path, not just the
      in-memory return.

    - Test D — large negative offset is honored (defensive numerics): call
      with `frame_offset=-50` and assert that the first emitted frame is
      shifted by -50 from the no-offset baseline. Negative offsets aren't
      a real production case but proving "the kwarg is a plain integer add,
      no clamping" prevents future regressions where someone "helpfully"
      adds `max(0, ...)`.

    All four tests use the existing `forge_fbx_baked.fbx` fixture which has
    real keyframe data → exercises the KEYED branch of `_merge_curves`.
  </behavior>
  <action>
    Make three coordinated edits. Implementation in this order so the test
    suite never goes red on a clean checkout (TDD: write tests first, then
    the production change, then run tests once and confirm all pass):

    **STEP 1 — Add the test class to tests/test_fbx_ascii.py** (write tests
    BEFORE the production edits below; they will fail with TypeError
    "unexpected keyword argument 'frame_offset'" — that's the RED state).

    Place `TestFbxToV5JsonFrameOffset` immediately after the existing
    `TestFbxToV5JsonCustomProperties` class (~line 800). Use the exact
    `_FIXTURE` and `_COMMON_KWARGS` pattern from that class. Each test
    receives `tmp_path` from pytest. See `<behavior>` for the four tests.

    **STEP 2 — Edit forge_flame/fbx_ascii.py**:

    (a) `_merge_curves` (~line 611): add `frame_offset: int = 0` as a
        keyword-only argument (place after `frame_rate` with `*` separator
        if not already keyword-only; check existing signature — if all
        positional, append as positional with default).

        - Static-fallback path (~line 635): change `frame = 0` to
          `frame = frame_offset`.
        - Keyed path (~line 657): change
          `frame = frame_from_ktime(ktime, frame_rate)` to
          `frame = frame_from_ktime(ktime, frame_rate) + frame_offset`.
        - Update the function docstring (~line 616-623): add a sentence:
          "If `frame_offset` is non-zero it is added to every emitted
          `frame` value (both the static-fallback and keyed paths). This
          is how the Flame batch's `start_frame` survives the FBX
          round-trip — `action.export_fbx(bake_animation=True)` zero-bases
          the KTime stream, so the offset must be reapplied on read."

    (b) `fbx_to_v5_json` (~line 710): add `frame_offset: int = 0` keyword-only
        argument (after `custom_properties`). Pass it through to
        `_merge_curves` at line 770:
        `frames = _merge_curves(cam, tree, frame_rate, frame_offset=frame_offset)`.
        Update the docstring `Args:` block: add a `frame_offset` entry
        explaining "Integer added to every `frame` value in the output.
        Default 0 (preserves Flame's zero-based KTime). Set to the Flame
        batch's `start_frame` to keep round-trip frame numbers aligned
        with the source plate."

    **STEP 3 — Edit flame/camera_match_hook.py** (inside `_export_camera_to_blender`,
    immediately BEFORE the existing `fbx_ascii.fbx_to_v5_json(...)` call at
    line ~2110-2120):

    Insert this defensive block — read `flame.batch.start_frame`, fall back
    to 0 on ANY failure, never crash the export:

    ```python
    # --- Frame offset — preserve Flame batch's start_frame so the round-trip
    # surfaces real plate frame numbers in Blender, not zero-based KTime. ---
    # action.export_fbx(bake_animation=True) emits FBX KTimes starting at 0
    # regardless of the batch's start_frame, so we must thread the offset
    # through the FBX-to-JSON read. flame.batch.start_frame is a PyAttribute
    # that has not been previously probed in this codebase; guard ALL failure
    # modes (missing attr, raises, returns non-numeric) and degrade to 0.
    # A 0-offset reproduces pre-fix behavior — the only user-visible cost of
    # the fallback is that Blender frames stay zero-based, which is the
    # status quo we are improving on. NEVER let an unknown PyAttribute shape
    # crash a working export.
    frame_offset = 0
    try:
        sf = flame.batch.start_frame.get_value()
        # PyAttribute may return int, float, or string depending on attr type;
        # coerce defensively. int(float(x)) handles "1001", 1001, 1001.0.
        frame_offset = int(float(sf))
    except Exception:
        frame_offset = 0  # silent fallback; do not surface to user
    ```

    Then update the `fbx_ascii.fbx_to_v5_json(...)` call (~line 2111) to add
    `frame_offset=frame_offset,` as a kwarg alongside the existing
    `custom_properties=...`:

    ```python
    fbx_ascii.fbx_to_v5_json(
        fbx_path, json_path,
        width=width, height=height,
        film_back_mm=36.0,
        camera_name=raw_cam_name,
        frame_offset=frame_offset,
        custom_properties={
            "forge_bake_action_name": raw_action_name,
            "forge_bake_camera_name": raw_cam_name,
        },
    )
    ```

    Why import-style: `flame` is ALREADY imported in this scope (the file
    is the Flame batch hook; `flame` is the Flame-bundled module imported
    at top). Do NOT add a new `import flame` here — use the module-level
    one. If `flame` is not module-level imported (verify with grep), add
    the local `import flame` inline matching the precedent in
    `_infer_plate_resolution` at line 1883.

    Why no logging on the fallback: this codebase does not use a logging
    framework in the hook handler; existing `except Exception: pass`
    patterns (line 1894, 1904) are the established convention. Adding a
    print would diverge stylistically. The trace fixture at
    `/tmp/forge_camera_match_trace.json` is solver-only, not export-flow.
  </action>
  <verify>
    <automated>cd /Users/cnoellert/Documents/GitHub/forge-calibrator &amp;&amp; pytest tests/test_fbx_ascii.py -x -q</automated>
  </verify>
  <done>
    - `pytest tests/test_fbx_ascii.py -x -q` passes (was 55 tests in this file pre-fix; should be 59 post-fix — 4 new TestFbxToV5JsonFrameOffset tests).
    - `pytest tests/ -x -q` passes (full suite; was 268 passing pre-fix; should be 272 post-fix).
    - `python -m py_compile flame/camera_match_hook.py` exits 0.
    - `grep -n "frame_offset" forge_flame/fbx_ascii.py` shows: signature on `_merge_curves`, signature on `fbx_to_v5_json`, the static-fallback `frame = frame_offset`, the keyed `+ frame_offset`, and the `_merge_curves(..., frame_offset=frame_offset)` call at the v5 JSON entry point.
    - `grep -n "start_frame" flame/camera_match_hook.py` shows the new defensive read block inside `_export_camera_to_blender`.
    - `grep -n "frame_offset" tests/test_fbx_ascii.py` shows the new `TestFbxToV5JsonFrameOffset` class with at least 4 tests.
    - All four behavior tests (A: offset shifts, B: default zero is no-op, C: on-disk parity, D: negative offset honored) are present and pass.
  </done>
</task>

</tasks>

<verification>

1. **Test suite green:**
   ```bash
   pytest tests/ -x -q
   ```
   Expected: all tests pass. Pre-fix baseline was 268 passing (per Phase 01 verification report). Post-fix baseline should be 272 passing (+4 new tests in TestFbxToV5JsonFrameOffset).

2. **Targeted file:**
   ```bash
   pytest tests/test_fbx_ascii.py -x -q
   ```
   Expected: previously 55, now 59. Test names visible in `-v` output should include `test_offset_shifts_frames`, `test_default_offset_is_zero`, `test_on_disk_parity`, `test_large_negative_offset`.

3. **Hook compiles:**
   ```bash
   python -m py_compile flame/camera_match_hook.py
   ```
   Expected: exit 0, no syntax errors.

4. **Frame-offset wired end-to-end (static check):**
   ```bash
   grep -nE "frame_offset|start_frame" forge_flame/fbx_ascii.py flame/camera_match_hook.py tests/test_fbx_ascii.py
   ```
   Expected matches:
   - `forge_flame/fbx_ascii.py`: signature additions on `_merge_curves` and `fbx_to_v5_json`, both code paths in `_merge_curves` apply the offset, the call site threads it through.
   - `flame/camera_match_hook.py`: the new defensive read block + the `frame_offset=frame_offset,` kwarg on `fbx_to_v5_json`.
   - `tests/test_fbx_ascii.py`: the new test class + at least one test with `frame_offset=1001` and one regression test.

5. **No regressions in untouched modules:**
   ```bash
   pytest tests/test_fbx_io.py tests/test_solver.py tests/test_hook_parity.py -q
   ```
   Expected: all green. (These modules don't touch frame numbering, but proving them green confirms the change didn't leak into adjacent code via shared helpers.)

6. **Defensive fallback unit-style sanity** (optional but recommended — exercise the
   fallback path WITHOUT live Flame): mentally trace the try/except in the hook
   edit. Confirm: missing `flame.batch.start_frame` attribute → `AttributeError`
   caught → `frame_offset = 0`. Confirm: `get_value()` returns string `"1001"` →
   `int(float("1001"))` = 1001. Confirm: returns `None` → `float(None)` raises
   TypeError → caught → 0. (No automated test possible without mocking the
   `flame` singleton, which is out-of-scope for this quick fix; the user
   verifies live behavior post-deploy.)

</verification>

<success_criteria>

- [ ] `forge_flame/fbx_ascii.py`: `_merge_curves` and `fbx_to_v5_json` both accept `frame_offset: int = 0` (keyword-only).
- [ ] `forge_flame/fbx_ascii.py`: BOTH code paths in `_merge_curves` (static fallback at ~line 635, keyed loop at ~line 657) apply `frame_offset` to the emitted `frame` field.
- [ ] `forge_flame/fbx_ascii.py`: `fbx_to_v5_json` threads `frame_offset` to the inner `_merge_curves(..., frame_offset=frame_offset)` call.
- [ ] `flame/camera_match_hook.py`: `_export_camera_to_blender` reads `flame.batch.start_frame.get_value()` defensively, coerces via `int(float(...))`, falls back to 0 on ANY exception (matching the established `except Exception: pass` precedent in `_infer_plate_resolution`).
- [ ] `flame/camera_match_hook.py`: the `fbx_ascii.fbx_to_v5_json(...)` call now includes `frame_offset=frame_offset` as a kwarg.
- [ ] `tests/test_fbx_ascii.py`: new `TestFbxToV5JsonFrameOffset` class with ≥4 tests covering offset application, default-zero regression, on-disk parity, negative offset.
- [ ] `pytest tests/ -x -q` passes (272 expected post-fix; 268 pre-fix + 4 new).
- [ ] `pytest tests/test_fbx_ascii.py -x -q` passes (59 expected post-fix; 55 pre-fix + 4 new).
- [ ] Docstrings updated on `_merge_curves` and `fbx_to_v5_json` to explain `frame_offset` and reference the Flame `bake_animation=True` zero-basing behavior.
- [ ] No changes to `bake_animation=True`, no changes to `tools/blender/bake_camera.py`, no `./install.sh` invocation.

</success_criteria>

<output>
After completion, create `.planning/quick/260420-uzv-preserve-flame-batch-start-frame-in-fbx-/260420-uzv-SUMMARY.md` summarizing:
- The three coordinated edits (fbx_ascii signatures, hook defensive read, test class).
- Test counts before/after (`pytest tests/ -q` numbers).
- Confirmation that bake_animation=True and bake_camera.py were untouched.
- A note that DEPLOY (running `./install.sh`) is owned by the user, not this plan, and that user-side UAT will confirm Flame batch 1001-1100 now surfaces in Blender as frames 1001-1100.
</output>
