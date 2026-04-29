---
phase: quick-260429-gde
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - tools/blender/forge_sender/flame_math.py
  - tests/test_forge_sender_flame_math.py
  - /Users/cnoellert/.claude/projects/-Users-cnoellert-Documents-GitHub-forge-calibrator/memory/blender_slotted_actions_fcurves_api.md
autonomous: true
requirements:
  - FCV-01  # Tier 1: bound-slot fcurves via bpy_extras.anim_utils
  - FCV-02  # Tier 2: unbound-slot manual layers/strips/channelbags walk
  - FCV-03  # Tier 3: legacy action.fcurves fallback (4.5 legacy-mode actions)
  - FCV-04  # empty slotted action yields nothing, no exception
  - FCV-05  # None action yields nothing, no exception
  - FCV-06  # bpy_extras.anim_utils missing/AttributeError falls through to Tier 2
  - FCV-07  # _camera_keyframe_set still combines object-level + camera-data-level fcurves
  - MEM-01  # Memory crumb published at memory/blender_slotted_actions_fcurves_api.md

must_haves:
  truths:
    - "Send to Flame from the Blender 5.1 addon no longer raises AttributeError on action.fcurves"
    - "_iter_action_fcurves() yields fcurves from a slotted Action when a slot is bound (Tier 1)"
    - "_iter_action_fcurves() yields fcurves from a slotted Action when no slot is bound (Tier 2 manual walk)"
    - "_iter_action_fcurves() falls back to action.fcurves on legacy-mode actions (Tier 3)"
    - "_camera_keyframe_set() returns the same merged frame set on slotted and legacy actions (regression-safe)"
    - "extract_camera.py CLI path is fixed by the same patch (it imports from flame_math)"
    - "bake_camera.py needs no change (writer-side keyframe_insert auto-creates slotted plumbing on 4.4+)"
    - "Memory crumb at memory/blender_slotted_actions_fcurves_api.md documents the iterator pattern, cutoff versions, and writer no-change rationale"
  artifacts:
    - path: "tools/blender/forge_sender/flame_math.py"
      provides: "_iter_action_fcurves() helper + rewritten _drain() that consumes it"
      contains: "_iter_action_fcurves"
    - path: "tests/test_forge_sender_flame_math.py"
      provides: "Bpy-free duck-typed unit tests for FCV-01..FCV-07"
      contains: "TestIterActionFcurves"
    - path: "/Users/cnoellert/.claude/projects/-Users-cnoellert-Documents-GitHub-forge-calibrator/memory/blender_slotted_actions_fcurves_api.md"
      provides: "Memory crumb documenting Blender 4.4+ slotted-actions API + three-tier iterator pattern"
      contains: "action_get_channelbag_for_slot"
  key_links:
    - from: "tools/blender/forge_sender/flame_math.py::_drain"
      to: "tools/blender/forge_sender/flame_math.py::_iter_action_fcurves"
      via: "for fc in _iter_action_fcurves(anim.action, anim_data=anim)"
      pattern: "_iter_action_fcurves"
    - from: "tools/blender/extract_camera.py"
      to: "tools/blender/forge_sender/flame_math.py::_camera_keyframe_set"
      via: "from flame_math import _camera_keyframe_set, build_v5_payload"
      pattern: "from flame_math import"
    - from: "tests/test_forge_sender_flame_math.py::TestIterActionFcurves"
      to: "tools/blender/forge_sender/flame_math.py::_iter_action_fcurves"
      via: "duck-typed fakes + monkeypatch on bpy_extras.anim_utils import"
      pattern: "_iter_action_fcurves"
---

<objective>
Fix the Blender 5.1 round-trip blocker: `Action.fcurves` was removed in
Blender 5.0 alongside the slotted-actions migration. The forge_sender
addon's "Send to Flame" operator (and the `extract_camera.py` CLI, which
imports from the same module) crashes with `AttributeError` against any
.blend opened in Blender 5.x. Replace `_drain`'s direct `action.fcurves`
walk with a version-tolerant `_iter_action_fcurves()` helper that uses
the official `bpy_extras.anim_utils.action_get_channelbag_for_slot` for
the bound-slot case, falls back to a manual layers/strips/channelbags
walk for unbound-slot edge cases, and finally falls back to legacy
`action.fcurves` for any 4.5 actions still in legacy-proxy mode.

Purpose: Unblocks the Flame↔Blender round-trip on flame-01 (Blender 5.1)
and on portofino once 5.1 is sideloaded there. This is a precondition
for round-trip fidelity — a dropped fcurve walk silently drops keyframes,
violating forge's core value that "the round-trip must preserve fidelity
end-to-end." Writer side (`bake_camera.py`) needs no change per
RESEARCH.md A-map ("Blender does all the layer/strip/slot/channelbag
plumbing automatically on first keyframe_insert").

Output:
- Patched `tools/blender/forge_sender/flame_math.py` with new
  `_iter_action_fcurves()` helper and rewritten `_drain()`.
- Extended `tests/test_forge_sender_flame_math.py` with duck-typed
  bpy-free tests covering FCV-01..FCV-07.
- New memory crumb at
  `memory/blender_slotted_actions_fcurves_api.md` so the next contributor
  who touches fcurves walks on a Blender data-block gets it right
  the first time.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@./CLAUDE.md
@.planning/STATE.md
@.planning/quick/260429-gde-version-tolerant-fcurves-walk-for-blende/260429-gde-RESEARCH.md
@.planning/todos/pending/2026-04-29-blender-51-slotted-actions-fcurves-api-migration.md
@tools/blender/forge_sender/flame_math.py
@tools/blender/extract_camera.py
@tests/test_forge_sender_flame_math.py

<interfaces>
<!-- Key contracts the executor needs. Embed these directly so no codebase
     exploration is required during execution. -->

From tools/blender/forge_sender/flame_math.py (CURRENT _drain — to be replaced):
```python
def _camera_keyframe_set(cam: bpy.types.Object) -> list:
    frames = set()

    def _drain(anim):
        if anim is None or anim.action is None:
            return
        for fcurve in anim.action.fcurves:           # <-- crashes on 5.x
            for kp in fcurve.keyframe_points:
                frames.add(int(round(kp.co[0])))

    _drain(cam.animation_data)
    _drain(cam.data.animation_data)

    if not frames:
        frames.add(int(bpy.context.scene.frame_current))
    return sorted(frames)
```

From tools/blender/extract_camera.py:68-74 (CLI imports — confirms one
fix covers both addon AND CLI extract path; do NOT touch this file):
```python
from flame_math import (  # noqa: E402
    _rot3_to_flame_euler_deg,
    _R_Z2Y,
    _camera_keyframe_set,
    _resolve_scale,
    build_v5_payload,
)
```

From tests/test_forge_sender_flame_math.py (CURRENT skip-gate at top —
the new tests SHOULD NOT use this skip gate; they are bpy-free and run
in the forge env unconditionally):
```python
pytest.importorskip("mathutils")
pytest.importorskip("bpy")
```

Three-tier iterator pattern (LOCKED — RESEARCH.md Pattern 2; do not
re-open):
```python
def _iter_action_fcurves(action, anim_data=None):
    """Tier 1: bpy_extras.anim_utils.action_get_channelbag_for_slot
       Tier 2: manual layers[*].strips[*].channelbags walk
       Tier 3: legacy action.fcurves (4.5 legacy-proxy mode)"""
    if action is None:
        return
    # Tier 1: official helper, when slot is bound
    slot = getattr(anim_data, "action_slot", None) if anim_data else None
    if slot is not None:
        try:
            from bpy_extras import anim_utils
            cbag = anim_utils.action_get_channelbag_for_slot(action, slot)
        except (ImportError, AttributeError):
            cbag = None
        if cbag is not None:
            for fc in cbag.fcurves:
                yield fc
            return
    # Tier 2: manual slotted walk
    layers = getattr(action, "layers", None)
    if layers:
        emitted = False
        for layer in layers:
            for strip in getattr(layer, "strips", ()):
                for cbag in getattr(strip, "channelbags", ()):
                    for fc in cbag.fcurves:
                        emitted = True
                        yield fc
        if emitted:
            return
    # Tier 3: legacy proxy
    legacy = getattr(action, "fcurves", None)
    if legacy:
        for fc in legacy:
            yield fc
```
</interfaces>

<test_runner_convention>
The forge env's `pytest-blender` plugin exits the session before
collection if a Blender binary isn't on PATH (memory crumb
`forge_pytest_blender_session_exit.md`). ALL pytest invocations in this
plan MUST pass `-p no:pytest-blender` (hyphen, not underscore).
</test_runner_convention>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add bpy-free duck-typed tests for _iter_action_fcurves (RED first, then GREEN in Task 2)</name>
  <files>tests/test_forge_sender_flame_math.py</files>
  <behavior>
    Add a new top-level test class `TestIterActionFcurves` to
    tests/test_forge_sender_flame_math.py. These tests are duck-typed
    against fakes (no bpy/mathutils import), so they must NOT live under
    the `pytest.importorskip("bpy")` gate at the top of the file.
    Restructure the imports so the existing bpy-gated tests still skip
    cleanly while the new tests run unconditionally — typical pattern is
    to keep the importorskip line, but import `_iter_action_fcurves`
    BEFORE the skip line, OR put the new test class in a sibling test
    file that doesn't carry the skip gate. Pick whichever is cleanest;
    research recommends extending the existing file via a deferred import
    (import the helper inside the test methods or via a module-level
    `from flame_math import _iter_action_fcurves` placed BEFORE the
    pytest.importorskip lines so the import only pulls in pure Python,
    no bpy) — confirm this works with the existing file structure.

    If extending the file makes the import order awkward, create
    `tests/test_forge_sender_fcurves_walk.py` as a sibling (RESEARCH.md
    explicitly allows this).

    Test cases (RED — must fail before Task 2 lands the helper):

    - Test 1 (FCV-01): `test_tier1_bound_slot_uses_helper` —
      construct a fake `_SlottedAction` with one layer / one strip /
      two channelbags (slot_handle=42 with 3 fcurves; slot_handle=99
      with 2 fcurves). Construct a fake `_AnimData` with
      `action_slot=_Slot(handle=42)`. Monkeypatch the
      `bpy_extras.anim_utils` import inside `flame_math` (or pass an
      injectable hook if you went that route in Task 2 — see Task 2's
      action) so the helper resolves slot_handle=42 to the first
      channelbag. Assert `list(_iter_action_fcurves(action, anim_data))`
      yields exactly the 3 fcurves from slot_handle=42, NOT the 2 from
      slot_handle=99.
    - Test 2 (FCV-02): `test_tier2_no_slot_walks_all_channelbags` —
      same fake action, but `_AnimData.action_slot=None`. Assert all
      5 fcurves yield (Tier 2 emits everything when no slot is bound).
    - Test 3 (FCV-03): `test_tier3_legacy_action_fcurves` —
      `_LegacyAction(fcurves=[fc1, fc2], layers=[])`. Tier 1 skips (no
      slot or slot with no helper match), Tier 2 skips (empty layers),
      Tier 3 yields fc1, fc2.
    - Test 4 (FCV-04): `test_empty_slotted_action_yields_nothing` —
      slotted action with empty layers list, no `fcurves` attr. Helper
      yields nothing, raises nothing.
    - Test 5 (FCV-05): `test_none_action_yields_nothing` —
      `_iter_action_fcurves(None, None)` → empty iterator, no exception.
    - Test 6 (FCV-06): `test_helper_attribute_error_falls_through` —
      bound slot present, but `bpy_extras.anim_utils` import raises
      ImportError OR `action_get_channelbag_for_slot` raises
      AttributeError. Helper should silently fall through to Tier 2 and
      yield from the manual walk. Assert all 5 fcurves yield (Tier 2
      fired) — NOT just the bound-slot 3.
    - Test 7 (FCV-07): `test_camera_keyframe_set_combines_object_and_data` —
      construct a fake camera object whose `.animation_data` has 2
      keyframes at frames {1, 5} on a slotted action AND
      `.data.animation_data` has 2 keyframes at frames {1, 10} on a
      different slotted action. Assert
      `_camera_keyframe_set(cam) == [1, 5, 10]` (sorted, unique merge).
      This is the regression test that proves the rewritten `_drain` still
      walks both call sites correctly. NOTE: `_camera_keyframe_set`
      calls `bpy.context.scene.frame_current` as a fallback — for this
      test the fake camera HAS frames so the fallback is never hit;
      no need to monkeypatch `bpy.context`.

    Test fakes to add (per RESEARCH.md "Test fakes" section):
    `_KP`, `_FCurve`, `_Channelbag`, `_Strip`, `_Layer`, `_SlottedAction`,
    `_LegacyAction`, `_Slot`, `_AnimData`. Keep them at module scope of
    the test file (or inside the new test class as nested classes).

    Run after each test write:
    `pytest tests/test_forge_sender_flame_math.py::TestIterActionFcurves -x -p no:pytest-blender`
    — should fail with `ImportError: cannot import name '_iter_action_fcurves'` (RED).
  </behavior>
  <action>
    1. Open `tests/test_forge_sender_flame_math.py`.
    2. Decide structure: extending the existing file vs. new sibling.
       Default to EXTENDING the existing file unless the import-order
       constraints below make it ugly:
       - The new tests must NOT skip when `bpy`/`mathutils` are absent
         (forge env on macOS dev). They are pure-Python iterator tests.
       - The existing tests rely on `pytest.importorskip("bpy")` at the
         module top — that skip applies to the WHOLE module.
       - Resolution: move the `pytest.importorskip` calls to be INSIDE the
         existing test classes that need them (or guard their imports of
         `_rot3_to_flame_euler_deg`, `_R_Z2Y`, `build_v5_payload`,
         `Matrix` with `try/except ImportError` + a class-level skip
         decorator). The `_iter_action_fcurves` import is bpy-free and
         can stay at module scope unconditionally.
       - If this restructure feels invasive, fall back to creating
         `tests/test_forge_sender_fcurves_walk.py` as a clean sibling.
         RESEARCH.md §"Wave 0 Gaps" explicitly allows either path.
    3. Add the test fakes (`_KP`, `_FCurve`, `_Channelbag`, `_Strip`,
       `_Layer`, `_SlottedAction`, `_LegacyAction`, `_Slot`, `_AnimData`)
       per the shapes documented in RESEARCH.md §"Code Examples → Test
       fakes". For Tier 1 testing, you also need a way to make the
       `bpy_extras.anim_utils.action_get_channelbag_for_slot` call do
       the lookup against your fake `_Strip`. Two options:
       (a) `monkeypatch.setattr(flame_math, "_get_channelbag_for_slot", fake_helper)`
           if Task 2 exposes an injectable seam; or
       (b) install a fake `bpy_extras.anim_utils` module into
           `sys.modules` before the helper imports it (Task 2's helper
           does a lazy `from bpy_extras import anim_utils` inside the
           Tier 1 branch — this option works with no extra seam).
       Prefer (b) because it doesn't require Task 2 to add a hook
       parameter — RESEARCH.md §"Open Questions Q1" recommends keeping
       the helper signature `(action, anim_data=None)`.
    4. Write tests 1–7 listed in `<behavior>`. Keep them tight; one
       AAA block per test, no class-level fixtures unless trivially
       reusable.
    5. Run `pytest tests/test_forge_sender_flame_math.py::TestIterActionFcurves -x -p no:pytest-blender`
       and confirm RED (ImportError or NameError). This is the gate.

    DO NOT attempt to make the tests pass in this task — that's Task 2.
    The point of writing them first is to lock the contract.
  </action>
  <verify>
    <automated>cd /Users/cnoellert/Documents/GitHub/forge-calibrator && pytest tests/test_forge_sender_flame_math.py::TestIterActionFcurves --collect-only -p no:pytest-blender 2>&1 | tail -20</automated>
  </verify>
  <done>
    - `TestIterActionFcurves` class added to existing test file (or new
      sibling file `tests/test_forge_sender_fcurves_walk.py`).
    - 7 test methods present (FCV-01..FCV-07).
    - Tests fail RED with ImportError/NameError on `_iter_action_fcurves`
      (helper not yet implemented). If you commit Task 1 separately,
      mark the tests with `@pytest.mark.xfail(reason="Task 2 not landed")`
      OR include a stub `_iter_action_fcurves` in flame_math that
      `raise NotImplementedError` — either works; pick whichever you
      reach for naturally. If you commit Task 1 + Task 2 together (a
      single GREEN commit) you can skip the xfail dance.
    - Existing bpy-gated tests in the file still skip cleanly when run
      from the forge env (no regression in collection).
    - Confirm by running the FULL existing forge_sender test file:
      `pytest tests/test_forge_sender_flame_math.py -p no:pytest-blender`
      — pre-existing tests should still collect-and-skip; new tests
      should collect-and-fail-RED (or xfail if you went that route).
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Implement _iter_action_fcurves and rewrite _drain (GREEN)</name>
  <files>tools/blender/forge_sender/flame_math.py</files>
  <behavior>
    Add `_iter_action_fcurves(action, anim_data=None)` to
    `tools/blender/forge_sender/flame_math.py` per the LOCKED three-tier
    pattern in `<interfaces>` above (Tier 1: bpy_extras.anim_utils,
    Tier 2: manual layers/strips/channelbags walk, Tier 3: legacy
    `action.fcurves`). Rewrite `_drain` inside `_camera_keyframe_set` to
    consume the helper. Add a docstring per CLAUDE.md "explain WHY"
    convention referencing the slotted-actions migration and the
    upcoming memory crumb. Keep `_camera_keyframe_set`'s public
    signature and return contract identical (sorted list of unique int
    frames, fallback to scene.frame_current if empty).

    All 7 tests from Task 1 must turn GREEN.
  </behavior>
  <action>
    1. Open `tools/blender/forge_sender/flame_math.py`.
    2. Insert `_iter_action_fcurves(action, anim_data=None)` immediately
       above `_camera_keyframe_set` (line ~98). Body verbatim from
       `<interfaces>` Pattern 2 above. Docstring must:
       - Explain WHY: legacy `action.fcurves` removed in Blender 5.0
         (slotted-actions migration); helper supports 4.5 (legacy proxy)
         + 5.x (slotted-only).
       - Reference the official utility:
         `bpy_extras.anim_utils.action_get_channelbag_for_slot`.
       - Cross-reference the upcoming memory crumb:
         `see memory/blender_slotted_actions_fcurves_api.md`.
       - Note Tier-3 is harmless dead code on 5.0+ (intentional —
         removing it would break 4.5 legacy-mode actions).
    3. Rewrite `_drain` inside `_camera_keyframe_set` (currently lines
       108–113) to use the helper:
       ```python
       def _drain(anim):
           if anim is None or anim.action is None:
               return
           for fc in _iter_action_fcurves(anim.action, anim_data=anim):
               for kp in fc.keyframe_points:
                   frames.add(int(round(kp.co[0])))
       ```
       Keep the rest of `_camera_keyframe_set` intact (the empty-set
       fallback to `scene.frame_current` and the `sorted(frames)` return
       at the bottom).
    4. Verify the lazy `from bpy_extras import anim_utils` is INSIDE the
       Tier 1 branch (not at module scope) — module scope would import
       at test-collection time on the forge env where `bpy_extras`
       isn't available, breaking the bpy-free unit tests.
    5. Run `pytest tests/test_forge_sender_flame_math.py::TestIterActionFcurves -x -p no:pytest-blender`
       — all 7 tests should turn GREEN.
    6. Run the existing test suite to confirm no regression:
       `pytest tests/ -p no:pytest-blender`. Pre-existing tests stay
       green (they still skip on bpy-import-fail in the forge env, but
       that's pre-existing behavior — unchanged).

    Refactor pass (only if needed): the helper as written is already
    minimal. Skip refactor unless the test fakes forced an awkward
    seam. Resist the temptation to add a stderr warning when Tier 2 or
    Tier 3 fires — RESEARCH.md §"Open Questions Q2" recommends it but
    the user's UAT plan is manual flame-01 retest, and silent
    fall-through on the rare case is fine for a quick fix. (If the
    executor disagrees and adds the stderr warning, that's allowed —
    document the deviation in the SUMMARY.)
  </action>
  <verify>
    <automated>cd /Users/cnoellert/Documents/GitHub/forge-calibrator && pytest tests/test_forge_sender_flame_math.py::TestIterActionFcurves -x -p no:pytest-blender 2>&1 | tail -15 && echo "---FULL SUITE---" && pytest tests/ -p no:pytest-blender 2>&1 | tail -10</automated>
  </verify>
  <done>
    - `_iter_action_fcurves(action, anim_data=None)` exists in
      `tools/blender/forge_sender/flame_math.py` with the three-tier
      body verbatim from RESEARCH.md Pattern 2.
    - `_drain` (inside `_camera_keyframe_set`) calls the helper instead
      of `anim.action.fcurves`.
    - `from bpy_extras import anim_utils` is INSIDE Tier 1 branch (lazy),
      NOT at module scope.
    - All 7 `TestIterActionFcurves` tests are GREEN.
    - Full pytest suite (`pytest tests/ -p no:pytest-blender`) is GREEN
      with no regressions vs. the pre-task baseline.
    - `tools/blender/extract_camera.py` is UNTOUCHED (the import-from
      relationship at lines 68–74 means it inherits the fix
      automatically).
    - `tools/blender/bake_camera.py:325-335` is UNTOUCHED (writer-side
      `keyframe_insert` auto-creates slotted plumbing on 4.4+ per
      RESEARCH A2; smoke-test gate is the manual UAT, not this task).
  </done>
</task>

<task type="auto">
  <name>Task 3: Write the memory crumb at memory/blender_slotted_actions_fcurves_api.md</name>
  <files>/Users/cnoellert/.claude/projects/-Users-cnoellert-Documents-GitHub-forge-calibrator/memory/blender_slotted_actions_fcurves_api.md</files>
  <action>
    Create the memory crumb so the next contributor who touches a
    Blender Action's fcurves (or writes a new one) gets the
    slotted-actions API right the first time.

    Path (use this exact absolute path — memory/ lives in
    ~/.claude/projects/, NOT in the repo):
    `/Users/cnoellert/.claude/projects/-Users-cnoellert-Documents-GitHub-forge-calibrator/memory/blender_slotted_actions_fcurves_api.md`

    Use the same brief style as sibling crumbs in that directory
    (`flame_rotation_convention.md`, `flame_keyframe_api.md`,
    `flame_install_pycache_gap.md`). Structure:

    1. **One-line summary** (matches the format of MEMORY.md's index
       line): "Blender 4.4+ replaced flat action.fcurves with slotted
       actions; Blender 5.0 removed the legacy proxy. Walk via
       bpy_extras.anim_utils.action_get_channelbag_for_slot, fall back
       to manual layers/strips/channelbags, fall back finally to legacy
       action.fcurves for 4.5 legacy-mode actions. Writer-side
       keyframe_insert is unchanged — Blender autocreates the slotted
       plumbing."

    2. **Why this matters** (1 paragraph): cite the symptom
       (`AttributeError: 'Action' object has no attribute 'fcurves'`
       on flame-01 / Blender 5.1), the root cause (slotted-actions
       migration in 4.4, legacy proxy removed in 5.0), and where the
       fix lives (`tools/blender/forge_sender/flame_math.py::_iter_action_fcurves`).

    3. **The three-tier iterator pattern** (code block — copy verbatim
       from `<interfaces>` Pattern 2 above, including docstring).

    4. **Version cutoffs**:
       - 4.3 and earlier: only legacy `action.fcurves` (forge no longer
         supports this).
       - 4.4: slotted introduced; `action.fcurves` retained as proxy.
       - 4.5 LTS: same as 4.4.
       - 5.0+: slotted-only; `action.fcurves`/`action.groups`/
         `action.id_root` removed.

    5. **Writer-side note**: `obj.keyframe_insert(data_path, frame=N)`
       handles slot/layer/strip/channelbag creation automatically on
       all supported Blender versions. `bake_camera.py` is correct
       as-is and needs no slotted-actions changes.

    6. **Pitfalls to remember**:
       - Don't access `action.fcurves` directly — use the helper.
       - Don't set `anim_data.action_slot_handle` directly — set
         `anim_data.action_slot` (per Blender migration guide).
       - Multi-slot Actions can hold animation for multiple data-blocks
         — always pass `anim_data` to the helper so Tier 1 filters to
         the bound slot.

    7. **Sources**:
       - [Slotted Actions Migration Guide (4.4)](https://developer.blender.org/docs/release_notes/4.4/upgrading/slotted_actions/)
       - [Blender 5.0 Python API Release Notes](https://developer.blender.org/docs/release_notes/5.0/python_api/)
       - This repo's RESEARCH.md:
         `.planning/quick/260429-gde-version-tolerant-fcurves-walk-for-blende/260429-gde-RESEARCH.md`

    After writing the crumb, append a one-line entry to MEMORY.md
    (same directory) following the existing style:
    `- [Blender 4.4+ slotted actions: fcurves moved off Action](blender_slotted_actions_fcurves_api.md) — action.fcurves removed in 5.0; walk via bpy_extras.anim_utils.action_get_channelbag_for_slot with three-tier fallback; writer-side keyframe_insert unchanged`

    Insert that line in MEMORY.md alphabetically/contextually near the
    other Blender / Flame I/O crumbs (e.g. near
    `flame_keyframe_api.md` and `flame_fbx_bake_semantics.md` — group
    with animation-data crumbs).
  </action>
  <verify>
    <automated>test -f /Users/cnoellert/.claude/projects/-Users-cnoellert-Documents-GitHub-forge-calibrator/memory/blender_slotted_actions_fcurves_api.md && grep -q "action_get_channelbag_for_slot" /Users/cnoellert/.claude/projects/-Users-cnoellert-Documents-GitHub-forge-calibrator/memory/blender_slotted_actions_fcurves_api.md && grep -q "blender_slotted_actions_fcurves_api.md" /Users/cnoellert/.claude/projects/-Users-cnoellert-Documents-GitHub-forge-calibrator/memory/MEMORY.md && echo OK</automated>
  </verify>
  <done>
    - `memory/blender_slotted_actions_fcurves_api.md` exists at the
      expected absolute path under
      `~/.claude/projects/-Users-cnoellert-Documents-GitHub-forge-calibrator/memory/`.
    - File contains the one-line summary, why-this-matters, the
      three-tier iterator code block (verbatim), version cutoff table,
      writer-side note, pitfalls, and sources.
    - MEMORY.md index updated with a one-line link to the new crumb,
      placed near the other animation/Flame-I/O crumbs.
    - `grep "action_get_channelbag_for_slot" memory/blender_slotted_actions_fcurves_api.md`
      and `grep "blender_slotted_actions_fcurves_api.md" memory/MEMORY.md`
      both return matches.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Blender subprocess → Flame via forge-bridge | Blender subprocess writes a JSON payload (built by `build_v5_payload`) and the addon POSTs it to forge-bridge on `127.0.0.1`. The fcurves walk feeds frame data into that payload. |
| .blend file → Blender subprocess | A user-supplied or forge-produced .blend is opened by Blender; `flame_math` reads its Action data via the new iterator. |

This is an internal VFX post-production tool with no untrusted-input
surface (per CLAUDE.md security posture). The threat model below covers
correctness/integrity threats, not adversarial security threats.

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-quick-260429-gde-01 | Tampering (data integrity) | `_iter_action_fcurves` Tier 2 fallback on a multi-slot Action | mitigate | Tier 1 (bpy_extras helper) is the always-fires path when `anim_data.action_slot` is bound, which is the case for every forge-produced .blend. Tier 2 only fires when no slot is bound — a non-forge-produced .blend or a manually edited Action. Test FCV-01 asserts cross-slot fcurves are NOT yielded when a slot is bound. |
| T-quick-260429-gde-02 | Information Disclosure (silent data drop) | `_iter_action_fcurves` returning early when `bpy_extras.anim_utils` raises | mitigate | Tier 1 catches `(ImportError, AttributeError)` and falls through to Tier 2 (FCV-06 covers this). The fall-through is silent by design (RESEARCH §"Open Questions Q2" — stderr warning rejected for v1 quick fix); manual UAT on flame-01 + diff against pre-fix baseline catches any unexpected behavior. |
| T-quick-260429-gde-03 | Denial of Service (infinite loop on cyclic action structure) | Manual layers/strips/channelbags walk in Tier 2 | accept | Blender's data-block hierarchy is acyclic by construction (an Action contains layers contains strips contains channelbags contains fcurves; no back-pointers). No cycle possible. |
| T-quick-260429-gde-04 | Repudiation (test fake doesn't match live API) | Bpy-free duck-typed unit tests | mitigate | Manual UAT gate on flame-01 with Blender 5.1 (FCV-08, FCV-09 from RESEARCH) is the integration gate; unit tests here cover iterator branch logic. The user explicitly scoped the manual retest to the next session — out of scope for this plan's verify step but documented in `<success_criteria>` as the milestone-level gate. |
| T-quick-260429-gde-05 | Elevation of Privilege | N/A | accept | No privilege boundary touched. Pure Python iterator; runs inside Blender subprocess and addon, both with the same trust level as the user's Blender install. |

</threat_model>

<verification>
## Local (this plan's automated gate)

```bash
cd /Users/cnoellert/Documents/GitHub/forge-calibrator
# 1. New iterator tests are GREEN
pytest tests/test_forge_sender_flame_math.py::TestIterActionFcurves -x -p no:pytest-blender
# 2. Full suite — no regression
pytest tests/ -p no:pytest-blender
# 3. Memory crumb exists and is indexed
test -f /Users/cnoellert/.claude/projects/-Users-cnoellert-Documents-GitHub-forge-calibrator/memory/blender_slotted_actions_fcurves_api.md
grep -q "blender_slotted_actions_fcurves_api.md" /Users/cnoellert/.claude/projects/-Users-cnoellert-Documents-GitHub-forge-calibrator/memory/MEMORY.md
```

## Out of scope (next session — user's UAT plan)

The following are explicitly OUT OF SCOPE for this executor and stay
with the user / next session:

- FCV-08 (RESEARCH §"Phase Requirements → Test Map"): full bake →
  extract round-trip diff on Blender 5.1 (`tools/blender/sample_camera.json`
  → `/tmp/forge_rt.blend` → `/tmp/forge_rt.json` → `diff`). Requires a
  flame-01 session with Blender 5.1.
- FCV-09: Live "Send to Flame" operator from the addon's N-panel on
  flame-01, end-to-end round-trip succeeds, no AttributeError.
- Reinstall the addon zip on flame-01 after the patch lands (sibling
  pycache concern from `flame_install_pycache_gap.md`; addon zip
  reinstall is the standard cure).
</verification>

<success_criteria>
This plan is COMPLETE when:

- [ ] `_iter_action_fcurves(action, anim_data=None)` exists in
      `tools/blender/forge_sender/flame_math.py` with the three-tier
      body and a WHY-explaining docstring referencing the new memory
      crumb.
- [ ] `_drain` inside `_camera_keyframe_set` consumes the helper
      (no direct `action.fcurves` access remains in this module).
- [ ] `tests/test_forge_sender_flame_math.py` (or new sibling file)
      contains `TestIterActionFcurves` with FCV-01..FCV-07 — all GREEN.
- [ ] `pytest tests/ -p no:pytest-blender` is GREEN with no regressions
      vs. pre-task baseline.
- [ ] `tools/blender/extract_camera.py` is UNTOUCHED (inherits fix via
      shared import).
- [ ] `tools/blender/bake_camera.py` is UNTOUCHED (writer side
      auto-handles slotted plumbing on 4.4+).
- [ ] CLAUDE.md is UNTOUCHED — the project still supports Blender 4.5;
      the patch is additive (do not bump the "Blender 4.5+" line per
      planning constraint).
- [ ] Memory crumb at
      `~/.claude/projects/-Users-cnoellert-Documents-GitHub-forge-calibrator/memory/blender_slotted_actions_fcurves_api.md`
      exists, contains the three-tier code block + version cutoffs +
      writer-side note + pitfalls + sources.
- [ ] MEMORY.md index updated with one-line link to the new crumb.
- [ ] Commits follow the GSD quick-task style:
      `fix(quick-260429-gde): version-tolerant fcurves walk for Blender slotted-actions API`
      and `docs(memory): blender_slotted_actions_fcurves_api crumb`
      (or equivalent split — one or two commits is fine; pick whichever
      keeps the diff legible).

**Out of scope (next session, user's UAT plan):** flame-01 retest with
Blender 5.1 — bake/extract round-trip + addon "Send to Flame" smoke
test. The executor's verify step is local pytest only.
</success_criteria>

<output>
After completion, create:
`.planning/quick/260429-gde-version-tolerant-fcurves-walk-for-blende/260429-gde-SUMMARY.md`

Include in the summary:
- Files modified (with line counts where useful).
- Confirmation that `tools/blender/extract_camera.py` and
  `tools/blender/bake_camera.py` were NOT modified.
- Test results (`pytest tests/ -p no:pytest-blender` tail output).
- Any executor deviations from the plan (e.g. if Task 1 tests were
  added in a sibling file rather than extending the existing one; if
  a stderr warning was added on Tier 2/3 fall-through; etc.).
- A one-line "next session UAT plan" reminder pointing back to the
  RESEARCH §"Phase Requirements → Test Map" rows FCV-08 and FCV-09 so
  whoever resumes this work on flame-01 has the live-API gate
  commands ready.
- Mark the original todo at
  `.planning/todos/pending/2026-04-29-blender-51-slotted-actions-fcurves-api-migration.md`
  as ready to move to `completed/` once the next-session UAT passes
  (do NOT move it in this session — UAT is the gate, not pytest).
</output>
