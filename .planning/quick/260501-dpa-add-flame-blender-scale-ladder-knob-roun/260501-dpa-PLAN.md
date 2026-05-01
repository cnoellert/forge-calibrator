---
phase: quick-260501-dpa
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - tools/blender/bake_camera.py
  - tools/blender/forge_sender/flame_math.py
  - forge_flame/camera_io.py
  - tests/test_bake_camera.py
  - tests/test_camera_io.py
  - tests/test_blender_roundtrip.py
autonomous: true
requirements:
  - SCALE-01  # New v5 JSON field `flame_to_blender_scale` carrying per-camera world-scale ladder value
  - SCALE-02  # Discrete ladder {0.01, 0.1, 1.0, 10.0, 100.0}; default 1.0; out-of-ladder rejected with explicit error
  - SCALE-03  # bake_camera.py multiplies static + per-keyframe translations by JSON ladder value (precedence over CLI --scale)
  - SCALE-04  # extract_camera.py / build_v5_payload divides translations by stamped scale (existing path; verify ladder values round-trip)
  - SCALE-05  # Round-trip parity: position(in) == position(out) within atol=1e-9 across {0.01, 1.0, 10.0} for static AND animated cameras
  - SCALE-06  # Backward compat: JSON without the field behaves byte-identically to current code (no regression on existing fixtures)
  - SCALE-07  # Rotations, focal_mm, sensor_height, frame_rate, frame numbers untouched by scale
  - SCALE-08  # forge_flame.camera_io.export_flame_camera_to_json grows an optional `flame_to_blender_scale` kwarg; absent => no field emitted

must_haves:
  truths:
    - "A v5 JSON with flame_to_blender_scale=10.0 baked into Blender lands camera position multiplied by 10.0 in the .blend"
    - "Extracting that .blend back to JSON returns position values identical to the original Flame JSON within atol=1e-9 (round-trip parity)"
    - "Round-trip parity holds for ALL ladder values {0.01, 0.1, 1.0, 10.0, 100.0}, on STATIC cameras AND animated cameras (every keyframe scaled uniformly)"
    - "rotation_flame_euler, focal_mm, film_back_mm, frame_rate, and frame numbers are unchanged across the round-trip regardless of scale"
    - "A v5 JSON WITHOUT the flame_to_blender_scale field bakes/extracts byte-identically to current behavior (back-compat preserved on existing test fixtures)"
    - "A v5 JSON with an out-of-ladder value (e.g. 0.5) causes bake_camera.py to exit with a clear stderr message naming the allowed ladder; nothing is written"
    - "JSON field takes precedence over CLI --scale when both are present; CLI --scale stays as an escape-hatch for non-ladder workflows (existing hook call site uses scale=1000.0 and must keep working unchanged)"
  artifacts:
    - path: "tools/blender/bake_camera.py"
      provides: "Reads data['flame_to_blender_scale'] (when present), validates against ladder, uses it as POSITION divisor instead of CLI --scale"
      contains: "_FLAME_TO_BLENDER_SCALE_LADDER"
    - path: "tools/blender/forge_sender/flame_math.py"
      provides: "_resolve_scale already reads forge_bake_scale stamped on cam.data — no change needed beyond docstring update naming the ladder source"
      contains: "_resolve_scale"
    - path: "forge_flame/camera_io.py"
      provides: "Optional flame_to_blender_scale kwarg on export_flame_camera_to_json, emitted as top-level field when provided"
      contains: "flame_to_blender_scale"
    - path: "tests/test_bake_camera.py"
      provides: "Unit tests for ladder validation + JSON-field-vs-CLI precedence; bpy-stub-friendly (existing fakery pattern)"
      contains: "TestFlameToBlenderScaleLadder"
    - path: "tests/test_camera_io.py"
      provides: "Unit tests for the new flame_to_blender_scale kwarg on export_flame_camera_to_json (emit/suppress shape)"
      contains: "TestFlameToBlenderScaleField"
    - path: "tests/test_blender_roundtrip.py"
      provides: "Numpy round-trip parity test exercising the bake/extract math at scale ladder values for static + animated cameras"
      contains: "TestScaleLadderRoundTrip"
  key_links:
    - from: "forge_flame/camera_io.py::export_flame_camera_to_json"
      to: "tools/blender/bake_camera.py::_bake"
      via: "v5 JSON top-level key 'flame_to_blender_scale'"
      pattern: "flame_to_blender_scale"
    - from: "tools/blender/bake_camera.py::_bake"
      to: "tools/blender/forge_sender/flame_math.py::_resolve_scale"
      via: "cam.data['forge_bake_scale'] custom property stamped by _stamp_metadata"
      pattern: "forge_bake_scale"
    - from: "tools/blender/forge_sender/flame_math.py::build_v5_payload"
      to: "extract_camera.py output JSON"
      via: "position = [tx * scale, ty * scale, tz * scale]"
      pattern: "tx \\* scale"
---

<objective>
Add a single configurable, JSON-driven scale factor for the Flame↔Blender
world-space conversion. The artist sets `flame_to_blender_scale` on the v5
JSON payload (default 1.0; allowed values constrained to the log10 ladder
{0.01, 0.1, 1.0, 10.0, 100.0}); `bake_camera.py` multiplies camera
translations by it on the way INTO Blender; `extract_camera.py` already
divides by the stamped scale on the way OUT, so round-trip parity is
preserved bit-exact (within float tolerance) without any new math on the
extract side.

Purpose: Per the project's core value, "the Flame↔Blender round-trip must
preserve fidelity end-to-end." A per-camera scene-scale knob is a
prerequisite for the calibrated reference-distance UI (future phase) and
for matching plate-imaging units to Blender's mesh kit. The existing
hard-coded `scale=1000.0` in the hook (`flame/camera_match_hook.py:2912`)
is a viewport-navigation hack — that path stays alive as a CLI fallback
for non-ladder workflows, but the JSON field becomes the authoritative
per-camera source going forward.

Output:
- `tools/blender/bake_camera.py` reads `data["flame_to_blender_scale"]`
  when present, validates it against the ladder, uses it as the POSITION
  divisor (overriding CLI `--scale`).
- `forge_flame/camera_io.py` exposes an optional `flame_to_blender_scale`
  kwarg that emits the JSON field when provided.
- Three new test classes guard ladder validation, the JSON kwarg shape,
  and end-to-end round-trip parity at multiple ladder stops on both
  static and animated cameras.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@./CLAUDE.md
@.planning/STATE.md
@.planning/PROJECT.md
@tools/blender/bake_camera.py
@tools/blender/extract_camera.py
@tools/blender/forge_sender/flame_math.py
@forge_flame/camera_io.py
@forge_flame/blender_bridge.py
@tests/test_bake_camera.py
@tests/test_camera_io.py
@tests/test_blender_roundtrip.py
@tests/test_extract_camera.py

<contract_already_in_place>
The v5 JSON contract is defined informally across two files. Read these
inline locations rather than re-discovering:

1. **bake_camera.py:13-26** — JSON shape comment block (width, height,
   film_back_mm, frames[].position/rotation_flame_euler/focal_mm). The
   new field is added as a TOP-LEVEL key alongside `width`, `height`,
   `film_back_mm`, `frame_rate`, `custom_properties`.

2. **forge_flame/camera_io.py:156-178** — `export_flame_camera_to_json`
   emits the canonical payload. The new kwarg slots in here, with the
   same emit-when-truthy pattern already used by `frame_rate` and
   `custom_properties` (lines 174-177).

3. **tools/blender/forge_sender/flame_math.py:222-242** —
   `_resolve_scale` already implements the correct precedence
   (CLI override > stamped metadata > 1.0). bake_camera.py stamps
   `forge_bake_scale` via `_stamp_metadata` (line 270) — this means the
   extract side is ALREADY correct for any value bake stamps. The work
   is entirely on the bake side: pull the value from the JSON, validate
   the ladder, stamp it.

4. **flame/camera_match_hook.py:2912** — the existing hook call site
   uses `scale=1000.0` (CLI flag). This MUST keep working unchanged;
   the JSON field overrides only when present. Hook integration with
   the new field is a FUTURE phase (out of scope here).
</contract_already_in_place>

<scale_field_precedence>
LOCKED precedence order (executor: do not reinvent):

1. JSON `flame_to_blender_scale` field present → use it (validate ladder).
2. JSON field absent, CLI `--scale` present → use CLI value (no ladder
   validation; preserves hook's `scale=1000.0` call).
3. Neither → default 1.0.

The stamped `forge_bake_scale` custom property always reflects the
EFFECTIVE value used at bake time (i.e. the result of the precedence
above), so the extract side's existing `_resolve_scale` walks back the
correct number with no changes.
</scale_field_precedence>

<ladder_handling_decision>
Out-of-ladder values: REJECT with `SystemExit` and a clear message
naming the ladder. Rationale:

- "Snap to nearest" is silent precision drift — exactly the failure
  mode the ladder exists to prevent (the user's spec calls out 0.0173
  as the kind of value to avoid).
- The ladder is short (5 values). A clear error message lists them.
- The artist's normal path is "set this in a UI dropdown" (future
  phase) — the dropdown will only offer ladder values, so the only way
  to hit the validation is a hand-crafted JSON, where loud failure is
  correct.

Validation message format:
`flame_to_blender_scale={value} is not on the allowed ladder {0.01, 0.1, 1.0, 10.0, 100.0}`

Ladder constant lives at module scope of `bake_camera.py`:
```python
_FLAME_TO_BLENDER_SCALE_LADDER = (0.01, 0.1, 1.0, 10.0, 100.0)
```

Float comparison: use `value in _FLAME_TO_BLENDER_SCALE_LADDER`. The
ladder values are exact float representations (powers of 10 happen to
not be exact, but `0.1`, `0.01`, `10.0`, `100.0` parsed from JSON via
the same `json.load()` always compare equal to the same Python literals
— this is the load-then-compare contract pytest fixtures depend on).
If the executor finds an edge case where the literal comparison fails,
fall back to `any(math.isclose(value, x, rel_tol=0, abs_tol=1e-12) for x in _FLAME_TO_BLENDER_SCALE_LADDER)`
and document the deviation in the SUMMARY.
</ladder_handling_decision>

<test_runner_convention>
The forge env's `pytest-blender` plugin exits the session before
collection if a Blender binary isn't on PATH (memory crumb
`forge_pytest_blender_session_exit.md`). ALL pytest invocations in this
plan MUST pass `-p no:pytest-blender` (hyphen, not underscore).
</test_runner_convention>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add JSON ladder field to bake + camera_io export, with ladder validation</name>
  <files>tools/blender/bake_camera.py, forge_flame/camera_io.py</files>
  <behavior>
    Bake side (bake_camera.py):
    - Add module-scope constant `_FLAME_TO_BLENDER_SCALE_LADDER = (0.01, 0.1, 1.0, 10.0, 100.0)`.
    - In `_bake()`, BEFORE the existing `scale = args.scale` line, check
      for `data.get("flame_to_blender_scale")`. If present:
        - Validate it's in the ladder; on miss, `raise SystemExit(...)`
          with the exact message format from `<ladder_handling_decision>`.
        - Override `scale = float(data["flame_to_blender_scale"])`.
      If absent: keep current behavior (`scale = args.scale`).
    - The rest of `_bake` is untouched — it already divides position by
      `scale` (line 323) and stamps `forge_bake_scale = scale` via
      `_stamp_metadata` (line 270). The new field just changes what
      `scale` resolves to.

    Export side (forge_flame/camera_io.py):
    - Add an optional `flame_to_blender_scale: Optional[float] = None`
      kwarg to `export_flame_camera_to_json` (alongside `frame_rate` and
      `custom_properties`).
    - When non-None, emit it as a top-level key on the payload (mirror
      the existing `if frame_rate:` / `if custom_properties:` blocks at
      lines 174-177).
    - When None, do NOT emit the key — preserves byte-identity for
      callers that don't supply it (back-compat invariant).
    - This file does NO ladder validation. The bake script is the
      authoritative validator; camera_io.py is a thin serializer.
      (Rationale: the artist UI in a future phase will gate on a
      dropdown so invalid values can't be constructed; double-validating
      is just two places to drift apart.)

    NOTE — caller call sites stay unchanged:
    - The hook (`flame/camera_match_hook.py`) call to
      `export_flame_camera_to_json` does NOT pass `flame_to_blender_scale`.
      Out of scope to wire that up here; the hook integration is a
      future phase.

    Tests (tests/test_bake_camera.py + tests/test_camera_io.py):

    In `tests/test_bake_camera.py`, add `TestFlameToBlenderScaleLadder`
    (placed after the existing `_FakeBpy` stub block). The existing test
    fixture stubs `bpy` so the bake module imports cleanly off-Blender.
    Tests must NOT require a real Blender — duck-type the path.

    For test 1 and 2 (the validator path) you can test
    `_FLAME_TO_BLENDER_SCALE_LADDER` directly (constant exists, contains
    expected values) and the validation logic in isolation by extracting
    it into a helper `_validate_flame_to_blender_scale(value) -> float`
    in bake_camera.py — this gives the tests something to call without
    having to drive `_bake()`. Recommend that refactor; if the executor
    keeps the validation inline in `_bake()` instead, write a small
    integration-style test that monkeypatches `bpy.ops.wm.save_as_mainfile`
    + `bpy.data` enough to drive `_bake()` to the validation point.
    EXECUTOR: pick the helper-extraction route — it's cleaner.

    Test cases for `TestFlameToBlenderScaleLadder` (test_bake_camera.py):
    - `test_ladder_constant_shape` — constant exists and equals
      `(0.01, 0.1, 1.0, 10.0, 100.0)`.
    - `test_validator_accepts_each_ladder_value` — parametrize over the
      5 ladder values; each returns the input unchanged.
    - `test_validator_rejects_off_ladder` — parametrize over
      `[0.5, 2.0, 0.05, 1000.0, -1.0, 0.0]`; each raises `SystemExit`.
    - `test_validator_rejection_message_lists_ladder` — assert the
      SystemExit's args contain "0.01", "100.0", and the offending value.

    For `tests/test_camera_io.py`, add `TestFlameToBlenderScaleField`:
    - `test_omitted_when_not_passed` — call
      `export_flame_camera_to_json(...)` without the kwarg; load the
      written JSON; assert `"flame_to_blender_scale" not in payload`.
    - `test_emitted_when_passed` — call with
      `flame_to_blender_scale=10.0`; assert the loaded JSON has the key
      with the exact float value.
    - `test_emitted_when_passed_one` — `flame_to_blender_scale=1.0`
      MUST still be emitted (truthy check would drop it; use
      `is not None` semantics, NOT `if flame_to_blender_scale:`).
      THIS IS A SUBTLE TRAP — the existing `if frame_rate:` /
      `if custom_properties:` blocks use truthy semantics; for the
      scale field, 1.0 is a perfectly valid value to record explicitly,
      and 0.0 is invalid (caught by bake-side validator). Use
      `is not None`.
    - `test_other_fields_unchanged` — call with the kwarg AND
      `frame_rate="24 fps"` AND `custom_properties={"foo": "bar"}`;
      assert all three keys are present and the existing
      width/height/film_back_mm/frames structure is intact.
  </behavior>
  <action>
    1. **Edit `tools/blender/bake_camera.py`:**
       a. Add module constant after the existing `_FLAME_FPS_LABELS`
          block (around line 188):
          ```python
          # Allowed values for the v5 JSON `flame_to_blender_scale`
          # field. Discrete log10 ladder so the inverse multiplier on
          # extract is an exact float (no precision drift). Default 1.0.
          # See .planning/quick/260501-dpa-... for the spec.
          _FLAME_TO_BLENDER_SCALE_LADDER = (0.01, 0.1, 1.0, 10.0, 100.0)
          ```
       b. Add validator helper (place ABOVE `_bake`, after
          `_stamp_metadata`):
          ```python
          def _validate_flame_to_blender_scale(value: float) -> float:
              """Return value if it's on the allowed ladder; else SystemExit.

              The ladder exists so the multiplier (bake) and divisor
              (extract) are exact-inverse floats — picking arbitrary
              values like 0.0173 introduces silent precision drift in
              the round-trip. See `_FLAME_TO_BLENDER_SCALE_LADDER`."""
              v = float(value)
              if v not in _FLAME_TO_BLENDER_SCALE_LADDER:
                  ladder_str = "{" + ", ".join(
                      str(x) for x in _FLAME_TO_BLENDER_SCALE_LADDER) + "}"
                  raise SystemExit(
                      f"flame_to_blender_scale={value} is not on the "
                      f"allowed ladder {ladder_str}")
              return v
          ```
       c. In `_bake()`, REPLACE the existing block (lines 305-307):
          ```python
          scale = args.scale
          if scale <= 0:
              raise SystemExit(f"--scale must be positive, got {scale}")
          ```
          WITH:
          ```python
          # Precedence: JSON field > CLI --scale > 1.0 default.
          # JSON field is the authoritative artist-facing knob and is
          # ladder-validated; CLI --scale stays free-form for the
          # legacy hook call site (camera_match_hook.py uses 1000.0
          # as a viewport-navigation hack).
          json_scale = data.get("flame_to_blender_scale")
          if json_scale is not None:
              scale = _validate_flame_to_blender_scale(json_scale)
          else:
              scale = args.scale
              if scale <= 0:
                  raise SystemExit(f"--scale must be positive, got {scale}")
          ```

    2. **Edit `forge_flame/camera_io.py`:**
       a. Add `flame_to_blender_scale: Optional[float] = None,` to the
          `export_flame_camera_to_json` signature, placed after
          `frame_rate` (around line 102).
       b. Update the docstring (around lines 119-133) — add an
          `flame_to_blender_scale` block in the same style as
          `frame_rate` and `custom_properties`. Mention the ladder
          (`{0.01, 0.1, 1.0, 10.0, 100.0}`), that bake_camera.py
          validates the value (this serializer does not), and that
          `None` means "no field emitted" for back-compat.
       c. After the existing `if custom_properties:` / `if frame_rate:`
          blocks (line 174-177), add:
          ```python
          if flame_to_blender_scale is not None:
              payload["flame_to_blender_scale"] = float(flame_to_blender_scale)
          ```
          USE `is not None`, NOT truthy — `1.0` and `0.01` are valid
          values that must round-trip explicitly when the caller asked
          for them. (See `<behavior>` test_emitted_when_passed_one.)

    3. **Edit `tests/test_bake_camera.py`:**
       a. Add `TestFlameToBlenderScaleLadder` class after the existing
          fakery block. Imports already cover `bake_camera` (the file
          stubs bpy and imports the module at the top). Add:
          - `test_ladder_constant_shape`
          - `test_validator_accepts_each_ladder_value` (parametrized)
          - `test_validator_rejects_off_ladder` (parametrized)
          - `test_validator_rejection_message_lists_ladder`
          Reference the validator as
          `bake_camera._validate_flame_to_blender_scale` and the
          constant as `bake_camera._FLAME_TO_BLENDER_SCALE_LADDER`.

    4. **Edit `tests/test_camera_io.py`:**
       a. Add `TestFlameToBlenderScaleField` class. Use the existing
          `_FakeCam` fixture; write to `tmp_path / "cam.json"`; reload
          with `json.load`; assert key presence and value.

    5. Run:
       ```
       cd /Users/cnoellert/Documents/GitHub/forge-calibrator
       pytest tests/test_bake_camera.py tests/test_camera_io.py -x -p no:pytest-blender
       ```
       Both test files must be GREEN before moving to Task 2.
  </action>
  <verify>
    <automated>cd /Users/cnoellert/Documents/GitHub/forge-calibrator && pytest tests/test_bake_camera.py tests/test_camera_io.py -x -p no:pytest-blender 2>&1 | tail -20</automated>
  </verify>
  <done>
    - `tools/blender/bake_camera.py` has `_FLAME_TO_BLENDER_SCALE_LADDER`
      constant and `_validate_flame_to_blender_scale` helper.
    - `_bake()` reads `data.get("flame_to_blender_scale")` with the
      documented precedence over CLI `--scale`.
    - Out-of-ladder JSON values raise `SystemExit` with the ladder in
      the error message.
    - `forge_flame/camera_io.py::export_flame_camera_to_json` has the
      new optional `flame_to_blender_scale` kwarg, emitted as a top-level
      JSON key when `is not None`, omitted otherwise (back-compat).
    - All new tests in `test_bake_camera.py::TestFlameToBlenderScaleLadder`
      and `test_camera_io.py::TestFlameToBlenderScaleField` are GREEN.
    - The existing tests in both test files still pass (no regression).
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Round-trip parity test across the scale ladder for static + animated cameras</name>
  <files>tests/test_blender_roundtrip.py</files>
  <behavior>
    Add `TestScaleLadderRoundTrip` to the existing
    `tests/test_blender_roundtrip.py` (the file already validates the
    bake/extract math via numpy stand-ins for `mathutils.Matrix`; this
    extends that pattern to cover the scale ladder).

    The existing file's structure (read it first):
    - `_rx_90()` — the Y-up → Z-up axis swap as a 4x4 numpy matrix
      (the bake-side multiplier that mirrors `_R_Y2Z` in bake_camera.py).
    - `bake_flame_to_blender(position, rotation_flame_euler)` — wraps
      the math `_R_Y2Z @ (T @ R)`.
    - The numpy stand-in mirrors the mathutils path bit-exactly per
      the file's docstring; this is the supported way to test
      bake/extract math without a Blender process.

    What `bake_flame_to_blender` does today vs. what the new tests need:
    - Today: takes `position` (raw Flame coords) and rotation; returns
      the Blender-frame world matrix WITHOUT applying the scale divisor.
    - For the new tests: extend the helper (or write a new variant)
      to optionally apply `position_scaled = position / scale` BEFORE
      the matrix construction, exactly as `bake_camera.py:323` does.
    - Symmetric extract side: extend the existing extract math to
      optionally multiply translations back up by the same scale,
      exactly as `flame_math.py:286` does
      (`position = [tx * scale, ty * scale, tz * scale]`).

    Test class (`TestScaleLadderRoundTrip`) cases:

    1. `test_static_camera_round_trip_at_each_ladder_value` —
       parametrized over `scale in (0.01, 0.1, 1.0, 10.0, 100.0)`:
       - Input: position `(833.0, -1250.0, 4747.64)`, rotation
         `(12.5, -7.3, 0.4)`.
       - Bake: divide position by scale, apply axis swap.
       - Extract: invert axis swap, recover translation, multiply
         translation by scale.
       - Assert: `np.allclose(recovered_position, original_position, atol=1e-9, rtol=0)`.
       - Assert: `np.allclose(recovered_rotation_euler, original_rotation_euler, atol=1e-9, rtol=0)`
         (rotations must NOT be touched by scale).

    2. `test_animated_camera_round_trip_at_each_ladder_value` —
       parametrized over the same 5 ladder values:
       - Build a 5-keyframe animated camera: positions at
         `[(0,0,1000), (100,0,1000), (200,50,900), (300,100,800), (400,150,700)]`,
         rotations at `[(0,0,0), (0,5,0), (0,10,0), (0,15,2), (0,20,5)]`,
         frame numbers `[1, 5, 10, 15, 20]`.
       - For each frame: bake → extract → assert position parity within
         atol=1e-9 AND rotation parity within atol=1e-9 AND frame number
         unchanged (frame numbers are integer indices, not coordinates;
         scale must not touch them).
       - Assert: scale applied UNIFORMLY across every keyframe (the
         test's per-frame parity loop is the proof).

    3. `test_default_scale_one_is_byte_identical_to_no_scale_path` —
       not parametrized; this is the back-compat regression guard:
       - Run the test 1 setup with `scale=1.0`.
       - Assert: the post-bake Blender matrix is equal (`np.array_equal`,
         not `allclose`) to the result of the existing
         `bake_flame_to_blender(position, rotation)` call (no scale
         arg). Catches any future refactor where the new scale path
         silently changes the math even at scale=1.0.

    4. `test_scale_does_not_affect_focal_or_film_back` —
       a sanity assertion test (no math, just contract):
       - Round-trip a camera at scale=10.0 with focal=42.0 and
         film_back_mm=24.0.
       - Assert: the recovered focal and film_back values are
         byte-identical (use `==`, not `allclose`) to the inputs.
       - Implementation note: focal/film_back aren't part of the matrix
         math the file currently tests, so this case mostly just
         documents the invariant by exercising the JSON-shape path.
         If extending the existing helpers for focal/film_back is
         awkward, write a tiny self-contained assertion:
         "`build_v5_payload`-style dict construction does not touch
         focal_mm or film_back_mm when scale changes." Skip this test
         entirely if it forces too much scaffolding — tests 1+2+3 are
         the load-bearing ones.

    All tests must run in the forge env (numpy-only; no bpy/mathutils
    required, since the file uses numpy stand-ins per its existing
    pattern — see file docstring at lines 1-32).
  </behavior>
  <action>
    1. **Read `tests/test_blender_roundtrip.py` end-to-end** (it's
       short; ~80 lines visible in context). Confirm the
       `bake_flame_to_blender` and extract helpers exist and produce
       the matrix shapes documented above. If the file's helpers stop
       short of the extract decomposition, look at the existing tests
       further down the file (read offset ~80 onward) to find or
       extend them.

    2. **Extend the helpers** to take an optional scale parameter:
       ```python
       def bake_flame_to_blender(position, rotation_flame_euler, scale=1.0):
           # Apply the scale divisor BEFORE matrix construction (matches
           # bake_camera.py:323).
           pos_scaled = [p / scale for p in position]
           cam_rot = flame_euler_to_cam_rot(*rotation_flame_euler)
           M_flame = _pack(np.array(pos_scaled), cam_rot)
           return _rx_90() @ M_flame

       def extract_blender_to_flame(M_blender, scale=1.0):
           # Inverse axis swap, then multiply translation back up by
           # scale (matches flame_math.py:286).
           M_flame = _rx_90().T @ M_blender
           pos_blender = M_flame[:3, 3]
           pos_flame = pos_blender * scale
           cam_rot = M_flame[:3, :3]
           rotation_euler = compute_flame_euler_zyx(cam_rot)
           return pos_flame, rotation_euler
       ```
       If the existing extract helper has a different signature, adapt
       — the math is what matters. Default `scale=1.0` keeps
       `test_default_scale_one_is_byte_identical_to_no_scale_path`
       trivially happy.

    3. **Add `TestScaleLadderRoundTrip`** at the bottom of the file.
       Use `@pytest.mark.parametrize("scale", [0.01, 0.1, 1.0, 10.0, 100.0])`
       for tests 1 and 2.

    4. Run:
       ```
       cd /Users/cnoellert/Documents/GitHub/forge-calibrator
       pytest tests/test_blender_roundtrip.py::TestScaleLadderRoundTrip -x -v -p no:pytest-blender
       ```
       Then run the full suite:
       ```
       pytest tests/ -p no:pytest-blender
       ```
       Both must be GREEN. The tolerance `atol=1e-9, rtol=0` is the
       parity gate; any failure here is a real round-trip break, NOT
       a flaky tolerance.
  </action>
  <verify>
    <automated>cd /Users/cnoellert/Documents/GitHub/forge-calibrator && pytest tests/test_blender_roundtrip.py::TestScaleLadderRoundTrip -x -v -p no:pytest-blender 2>&1 | tail -20 && echo "---FULL SUITE---" && pytest tests/ -p no:pytest-blender 2>&1 | tail -10</automated>
  </verify>
  <done>
    - `tests/test_blender_roundtrip.py::TestScaleLadderRoundTrip` exists.
    - Static-camera parametrized test passes for all 5 ladder values
      with `atol=1e-9, rtol=0` parity on position AND rotation.
    - Animated-camera parametrized test (5 keyframes × 5 ladder values
      = 25 frame-level parity checks) passes.
    - Back-compat test (`test_default_scale_one_is_byte_identical...`)
      passes — proves scale=1.0 path matches the no-scale path
      bit-exactly.
    - Full pytest suite (`pytest tests/ -p no:pytest-blender`) is GREEN
      with no regressions vs. pre-task baseline.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Flame hook → v5 JSON file | Hook (or future UI) writes the JSON; `flame_to_blender_scale` is one of the fields. Untrusted-shape risk is internal-tooling-low. |
| v5 JSON file → Blender subprocess | bake_camera.py reads the JSON via `json.load`; the new field is validated against the ladder before use. |
| Blender custom property → extract path | `forge_bake_scale` is stamped on `cam.data` by bake; extract reads it via `_resolve_scale`. Stamped value is whatever bake decided to use after precedence + validation, so extract inherits the validation result. |

This is an internal VFX post-production tool with no untrusted-input
surface (per CLAUDE.md security posture). The threat model below covers
correctness/integrity threats, not adversarial security threats.

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-quick-260501-dpa-01 | Tampering (data integrity) | Hand-edited v5 JSON with off-ladder `flame_to_blender_scale` (e.g. 0.5) | mitigate | `_validate_flame_to_blender_scale` rejects with explicit ladder list in the error. Unit test `test_validator_rejects_off_ladder` enforces. |
| T-quick-260501-dpa-02 | Information Disclosure (silent precision drift) | Round-trip multiplication/division at non-power-of-10 scale values | mitigate | Ladder restricted to `{0.01, 0.1, 1.0, 10.0, 100.0}` so extract's multiplication exactly inverts bake's division. `TestScaleLadderRoundTrip` asserts `atol=1e-9` parity at every ladder value for both static + animated cameras. |
| T-quick-260501-dpa-03 | Denial of Service (regression — existing JSONs without the field stop working) | Back-compat path (JSON missing `flame_to_blender_scale`) | mitigate | `data.get("flame_to_blender_scale")` returns None for missing field; precedence falls through to CLI `--scale` (existing path). `test_default_scale_one_is_byte_identical_to_no_scale_path` and full suite re-run guards against regression. |
| T-quick-260501-dpa-04 | Repudiation (rotations or focal silently affected by scale) | bake_camera.py / flame_math.py math touching anything beyond translation | mitigate | `_bake()` only multiplies `kf["position"]`; rotation, lens, sensor untouched (verified by code inspection at line 322-326). `test_scale_does_not_affect_focal_or_film_back` documents the invariant. |
| T-quick-260501-dpa-05 | Elevation of Privilege | N/A | accept | No privilege boundary touched. Pure math + JSON I/O; runs inside Blender subprocess and Flame's own Python. |

</threat_model>

<verification>
## Local automated gate (this plan)

```bash
cd /Users/cnoellert/Documents/GitHub/forge-calibrator
# 1. New unit tests + new round-trip parity tests are GREEN
pytest tests/test_bake_camera.py tests/test_camera_io.py tests/test_blender_roundtrip.py -x -p no:pytest-blender
# 2. Full suite — no regression
pytest tests/ -p no:pytest-blender
```

## Out of scope (next session — future phases, not this quick task)

- Hook integration: `flame/camera_match_hook.py:2912` still passes
  `scale=1000.0` to `run_bake`. Wiring the hook to set
  `flame_to_blender_scale` on the JSON is a future phase; the hook
  call site stays untouched here. The CLI `--scale` precedence
  preserves current hook behavior verbatim.
- Artist UI: a dropdown UI (PySide2) exposing the ladder values to
  the artist is a future phase. The infrastructure landed here is
  the JSON contract field + bake-side validator; the UI is what
  will eventually call `export_flame_camera_to_json(...,
  flame_to_blender_scale=value)`.
- Live Blender end-to-end UAT: the new tests use numpy stand-ins per
  the existing `test_blender_roundtrip.py` pattern, which are bit-exact
  with the mathutils path. A live `blender --background` round-trip
  with the new JSON field can be added as a follow-up if desired
  (it's not required for this milestone — the math is the gate).
- Calibrated reference-distance UI (artist drags a known-length line,
  derives scale from photogrammetry): explicitly OUT OF SCOPE per the
  task spec.
- Scaling of imported geometry: explicitly OUT OF SCOPE.
- Matchbox-side changes: shelved per
  `memory/matchbox_direction_shelved.md`.
</verification>

<success_criteria>
This plan is COMPLETE when:

- [ ] `tools/blender/bake_camera.py` exposes
      `_FLAME_TO_BLENDER_SCALE_LADDER = (0.01, 0.1, 1.0, 10.0, 100.0)`
      and `_validate_flame_to_blender_scale(value)` (raises
      `SystemExit` with the ladder in the message on miss).
- [ ] `_bake()` reads `data.get("flame_to_blender_scale")` with
      precedence over CLI `--scale`; absent JSON field preserves
      current behavior verbatim.
- [ ] `forge_flame/camera_io.py::export_flame_camera_to_json` accepts
      an optional `flame_to_blender_scale: Optional[float] = None`
      kwarg; emits a top-level JSON key when `is not None`, omits
      otherwise.
- [ ] `tests/test_bake_camera.py::TestFlameToBlenderScaleLadder`:
      - Constant shape test PASSES.
      - 5 parametrized accept-each-ladder tests PASS.
      - 6 parametrized reject-off-ladder tests PASS.
      - Rejection-message-lists-ladder test PASSES.
- [ ] `tests/test_camera_io.py::TestFlameToBlenderScaleField`:
      - Omitted-when-not-passed test PASSES.
      - Emitted-when-passed test PASSES.
      - Emitted-when-passed-one (1.0) test PASSES (the `is not None`
        trap test).
      - Other-fields-unchanged test PASSES.
- [ ] `tests/test_blender_roundtrip.py::TestScaleLadderRoundTrip`:
      - Static-camera parametrized test PASSES for all 5 ladder
        values with `atol=1e-9, rtol=0` parity.
      - Animated-camera parametrized test PASSES (25 frame-level
        parity checks).
      - Back-compat byte-identity test (scale=1.0) PASSES.
- [ ] `pytest tests/ -p no:pytest-blender` is GREEN with no
      regressions vs. pre-task baseline (numerical count of pre-task
      passes ≤ post-task passes; no new failures or skips).
- [ ] `tools/blender/forge_sender/flame_math.py` is UNTOUCHED — the
      extract side already correctly walks the stamped
      `forge_bake_scale` for any value bake stamps. (Optional:
      one-line docstring tweak naming the ladder source is fine but
      not required.)
- [ ] `tools/blender/extract_camera.py` is UNTOUCHED.
- [ ] `flame/camera_match_hook.py` is UNTOUCHED — hook integration is
      a future phase.
- [ ] Commit follows GSD quick-task style:
      `feat(quick-260501-dpa): add flame_to_blender_scale ladder knob with round-trip parity tests`
</success_criteria>

<output>
After completion, create:
`.planning/quick/260501-dpa-add-flame-blender-scale-ladder-knob-roun/260501-dpa-SUMMARY.md`

Include in the summary:
- Files modified (with line counts where useful).
- Confirmation that `tools/blender/forge_sender/flame_math.py`,
  `tools/blender/extract_camera.py`, and `flame/camera_match_hook.py`
  were NOT modified.
- Test results (pass count delta vs. pre-task baseline).
- Round-trip parity numbers (the actual `np.max(np.abs(out - in))`
  observed for each ladder value, if easy to surface).
- Any executor deviations from the plan (e.g. if the validator was
  kept inline in `_bake()` instead of extracted to a helper; if the
  ladder comparison fell back to `math.isclose` instead of `in`; if
  test 4 from Task 2 was skipped per its escape clause).
- A one-line "next phase" reminder: hook integration
  (`flame/camera_match_hook.py:2912`) and artist UI (PySide2 dropdown
  exposing the ladder) are the natural follow-ups.
</output>
</content>
</invoke>