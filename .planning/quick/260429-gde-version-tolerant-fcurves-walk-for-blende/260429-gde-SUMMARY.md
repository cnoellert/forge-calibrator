---
phase: quick-260429-gde
plan: 01
subsystem: blender-integration
tags: [blender, slotted-actions, fcurves, bpy_extras, anim_utils, version-tolerance, addon, extract_camera, forge_sender]

# Dependency graph
requires:
  - phase: 04.4-04
    provides: forge_sender addon v1.3.0 with the original _drain implementation that broke on Blender 5.x
provides:
  - "_iter_action_fcurves(action, anim_data) helper in tools/blender/forge_sender/flame_math.py — three-tier version-tolerant fcurves walk for Blender 4.5..5.x"
  - "Rewritten _drain inside _camera_keyframe_set that consumes the helper instead of action.fcurves directly"
  - "FCV-01..FCV-07 duck-typed bpy-free unit tests in tests/test_forge_sender_fcurves_walk.py"
  - "Memory crumb at memory/blender_slotted_actions_fcurves_api.md documenting the slotted-actions migration, three-tier pattern, version cutoffs, and writer-side rationale"
affects: [Phase 04.4 follow-up UAT, future Blender API version bumps, addon zip repackage workflow]

# Tech tracking
tech-stack:
  added: []  # No new dependencies — bpy_extras.anim_utils ships with Blender 4.4+
  patterns:
    - "Three-tier version-tolerant API walk (preferred → fallback → legacy) via getattr + try/except"
    - "Lazy import of bpy_extras.anim_utils inside Tier 1 branch (preserves bpy-free unit tests)"
    - "Test isolation: stub bpy/mathutils into sys.modules just long enough to import flame_math, then remove the stubs so subsequent test modules' importorskip(\"bpy\") still sees the env's real (absent) state"

key-files:
  created:
    - "tests/test_forge_sender_fcurves_walk.py"
    - "memory/blender_slotted_actions_fcurves_api.md (~/.claude/projects/.../forge-calibrator/memory/)"
  modified:
    - "tools/blender/forge_sender/flame_math.py (added _iter_action_fcurves; rewrote _drain)"
    - "memory/MEMORY.md (one-line index entry for the new crumb)"

key-decisions:
  - "Tests live in a sibling file (tests/test_forge_sender_fcurves_walk.py) rather than extending tests/test_forge_sender_flame_math.py — the existing file's module-level pytest.importorskip(\"bpy\") would skip the new bpy-free tests too, and refactoring that gate would have been invasive."
  - "The bpy_extras.anim_utils import is lazy (inside the Tier 1 branch), not module-scope. Keeps the bpy-free unit tests portable on the forge env (macOS dev) where bpy_extras isn't installed."
  - "No stderr warning on Tier 2/3 fallback. RESEARCH §Q2 considered it; rejected for v1 quick fix because forge-produced .blends always hit Tier 1, and the silent fall-through is fine for the user's manual UAT plan on flame-01."
  - "Tier 3 (legacy action.fcurves) retained even though it's harmless dead code on Blender 5.0+. Removing it would break Blender 4.5 actions still in legacy-proxy mode. Defense in depth costs nothing."

patterns-established:
  - "Three-tier version-tolerant API walk: try the official helper, fall back to manual walk, fall back finally to legacy attribute"
  - "Stub-then-remove sys.modules pattern for bpy/mathutils-dependent imports in unit tests"

requirements-completed: [FCV-01, FCV-02, FCV-03, FCV-04, FCV-05, FCV-06, FCV-07, MEM-01]

# Metrics
duration: 4min
completed: 2026-04-29
---

# Quick Task 260429-gde: Version-Tolerant fcurves Walk for Blender Slotted-Actions API Summary

**Three-tier `_iter_action_fcurves` helper unblocks Blender 5.1 `Send to Flame` round-trips by replacing the bare `action.fcurves` walk with `bpy_extras.anim_utils.action_get_channelbag_for_slot` (Tier 1) → manual layers/strips/channelbags walk (Tier 2) → legacy `action.fcurves` fallback (Tier 3).**

## Performance

- **Duration:** 4 min
- **Started:** 2026-04-29T19:07:12Z
- **Completed:** 2026-04-29T19:11:50Z
- **Tasks:** 3 (RED tests → GREEN helper → memory crumb)
- **Files modified:** 4 (1 new test, 1 source patch, 1 new memory crumb, 1 MEMORY.md index)

## Accomplishments

- `_iter_action_fcurves(action, anim_data=None)` helper landed in `tools/blender/forge_sender/flame_math.py` with the locked three-tier RESEARCH Pattern 2 body and a docstring explaining the WHY, version cutoffs, and the cross-reference to the memory crumb.
- `_drain` inside `_camera_keyframe_set` now consumes the helper — no direct `action.fcurves` access remains in this module. Public signature and return contract unchanged (sorted list of unique int frames; falls back to `scene.frame_current` if empty).
- 7 duck-typed bpy-free unit tests in `tests/test_forge_sender_fcurves_walk.py` cover FCV-01..FCV-07 (Tier 1 / Tier 2 / Tier 3 / empty-slotted / None-action / helper-AttributeError-fallthrough / `_camera_keyframe_set` regression).
- Memory crumb at `~/.claude/projects/-Users-cnoellert-Documents-GitHub-forge-calibrator/memory/blender_slotted_actions_fcurves_api.md` documents the migration spec, three-tier pattern (verbatim code), Blender 4.3..5.1 version cutoff table, writer-side rationale, pitfalls, and sources.
- MEMORY.md index updated with a one-line link near `flame_keyframe_api.md` (animation-data crumb cluster).
- `tools/blender/extract_camera.py` and `tools/blender/bake_camera.py` are untouched — extract_camera.py inherits the fix transitively via its existing `from flame_math import _camera_keyframe_set, build_v5_payload` line, and bake_camera.py's `keyframe_insert` autocreates slotted plumbing on every supported Blender version.
- `CLAUDE.md` is untouched (planning constraint — Blender 4.5+ minimum is preserved; the patch is additive).

## Task Commits

Each task was committed atomically:

1. **Task 1: Add bpy-free duck-typed tests for `_iter_action_fcurves` (RED)** — `a3cf531` (test)
2. **Task 2: Implement `_iter_action_fcurves` and rewrite `_drain` (GREEN)** — `f064824` (fix)
3. **Task 3: Memory crumb + MEMORY.md index entry** — no commit (file lives outside the repo at `~/.claude/projects/.../memory/`; not version-controlled here)

_Note: TDD plan-level gates verified — `test(...)` commit precedes `fix(...)` commit. No `refactor(...)` needed; the helper as written was already minimal._

## Files Created/Modified

- `tests/test_forge_sender_fcurves_walk.py` — **NEW** (~373 lines). 7 unit tests + duck-typed fakes (`_KP`, `_FCurve`, `_Channelbag`, `_Strip`, `_Layer`, `_SlottedAction`, `_LegacyAction`, `_Slot`, `_AnimData`, `_CamObject`, `_CamData`) + sys.modules stub-and-remove helper for the `bpy`/`mathutils` import-time dance.
- `tools/blender/forge_sender/flame_math.py` — **MODIFIED** (now ~311 lines). Added `_iter_action_fcurves(action, anim_data=None)` (~80 lines including docstring) immediately above `_camera_keyframe_set`. Rewrote `_drain` to consume the helper. Updated `_camera_keyframe_set`'s docstring to cross-reference the helper and the memory crumb.
- `~/.claude/projects/-Users-cnoellert-Documents-GitHub-forge-calibrator/memory/blender_slotted_actions_fcurves_api.md` — **NEW** (~70 lines). Frontmatter + summary + why-this-matters + three-tier code block + version cutoff table + writer-side note + pitfalls + sources.
- `~/.claude/projects/-Users-cnoellert-Documents-GitHub-forge-calibrator/memory/MEMORY.md` — **MODIFIED** (one new index line near `flame_keyframe_api.md`).

**Untouched (verified by `git diff --stat HEAD~2 HEAD -- ...`):**
- `tools/blender/extract_camera.py` — inherits the fix via existing `from flame_math import` line (RESEARCH A5).
- `tools/blender/bake_camera.py` — writer-side `keyframe_insert` autocreates slotted plumbing on Blender 4.4+ (RESEARCH A2).
- `CLAUDE.md` — no Blender minimum bump; the patch is additive across 4.5..5.x.

## Decisions Made

- **Sibling test file over extension.** Plan offered both options; sibling won because the existing `test_forge_sender_flame_math.py` has a module-level `pytest.importorskip("bpy")` that would skip the bpy-free iterator tests too. Refactoring that gate would have been invasive and risked silently breaking the existing rotation-math tests.
- **Lazy `from bpy_extras import anim_utils` inside Tier 1.** Module-scope import would fail at test-collection time on the forge env (macOS dev) where `bpy_extras` isn't installed; the lazy import keeps the bpy-free unit tests portable.
- **No stderr warning on Tier 2/3 fall-through.** RESEARCH §Q2 had this as a maybe; the user's UAT plan is manual flame-01 retest, and forge-produced .blends always hit Tier 1, so silent fall-through on the rare case is fine for the v1 quick fix. If flame-01 UAT surfaces unexpected fallback firings, a follow-up quick task can add the warning.
- **Tier 3 retained as harmless dead code on 5.0+.** Removing the legacy `action.fcurves` fallback would break Blender 4.5 actions still in legacy-proxy mode. Defense in depth costs nothing.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] Test isolation: `bpy`/`mathutils` stubs leaking across test modules**

- **Found during:** Task 2 (full-suite regression check after the GREEN tests passed in isolation)
- **Issue:** The new test file installed fake `bpy` and `mathutils` modules into `sys.modules` at module-import time so it could import `flame_math`. Pytest's collection visited the new file first (alphabetical: `fcurves` < `flame`), the stubs persisted, and then `tests/test_forge_sender_flame_math.py`'s `pytest.importorskip("bpy")` saw the stubs and proceeded to run the rotation-math tests against my fake `Matrix.Rotation` — 26 cascading failures.
- **Fix:** Restructured the test file's stub installer into `_import_flame_math_with_stubs()` which (1) tracks exactly which keys it adds to `sys.modules`, (2) imports `flame_math` so the source module captures its own references to the stubs via its closure, and (3) removes the stubs from `sys.modules` in a `try/finally` block. After import, `flame_math.bpy` and `flame_math.mathutils` still point to the stubs (used inside `_camera_keyframe_set`'s fallback path, never exercised by the iterator tests), but `sys.modules['bpy']` is gone — so `test_forge_sender_flame_math.py`'s `importorskip("bpy")` correctly skips again.
- **Files modified:** `tests/test_forge_sender_fcurves_walk.py` (only — the source `flame_math.py` is unaffected)
- **Verification:** Full suite went from 26 failed / 457 passed back to 0 failed / 457 passed / 2 skipped. Verified the existing `test_forge_sender_flame_math.py` skips correctly when run after the new file via the full `pytest tests/` invocation.
- **Committed in:** `f064824` (folded into the Task 2 GREEN commit alongside the helper)

---

**Total deviations:** 1 auto-fixed (Rule 3 — blocking)
**Impact on plan:** Necessary for the new tests to coexist with the existing skip-gated tests in the forge env. No scope creep — the fix stays inside the new test file.

## Issues Encountered

- One blocking test-isolation issue (documented above as a Rule 3 auto-fix). No other surprises.

## Next Session UAT Plan (out of scope for this executor)

Per RESEARCH §"Phase Requirements → Test Map", the following manual gates run on flame-01 with Blender 5.1:

- **FCV-08 (round-trip diff):**
  ```bash
  blender --background --python tools/blender/bake_camera.py -- \
    --in tools/blender/sample_camera.json \
    --out /tmp/forge_rt.blend \
    --scale 1000 --create-if-missing
  blender --background /tmp/forge_rt.blend \
    --python tools/blender/extract_camera.py -- \
    --out /tmp/forge_rt.json
  diff tools/blender/sample_camera.json /tmp/forge_rt.json
  ```
  Expected: empty diff.

- **FCV-09 (live `Send to Flame` smoke test):** Run the `forge_sender` v1.3.0 addon's "Send to Flame" operator from the N-panel on a real animated camera in Blender 5.1; confirm no `AttributeError` and that the camera lands in Flame with the right frames.

- **Pre-UAT:** Reinstall the forge_sender addon zip on flame-01 after the patch lands (sibling pycache concern from `flame_install_pycache_gap.md` — addon zip reinstall is the standard cure).

The pending todo at `.planning/todos/pending/2026-04-29-blender-51-slotted-actions-fcurves-api-migration.md` is **ready to move to `completed/`** once FCV-08 + FCV-09 pass on flame-01. Do NOT move it now — UAT is the gate, not pytest.

## Self-Check: PASSED

- `tools/blender/forge_sender/flame_math.py` — exists, contains `_iter_action_fcurves` and rewritten `_drain` (verified via `git log -p` on commit `f064824`).
- `tests/test_forge_sender_fcurves_walk.py` — exists, 7 tests collected, all passing (`pytest tests/test_forge_sender_fcurves_walk.py -p no:pytest-blender` → 7 passed).
- `~/.claude/projects/.../memory/blender_slotted_actions_fcurves_api.md` — exists, contains `action_get_channelbag_for_slot` (`grep` returns match).
- `~/.claude/projects/.../memory/MEMORY.md` — index line for `blender_slotted_actions_fcurves_api.md` present (`grep` returns match).
- Commit `a3cf531` — found in `git log` (Task 1 RED).
- Commit `f064824` — found in `git log` (Task 2 GREEN, includes the test-isolation Rule 3 fix).
- `tools/blender/extract_camera.py`, `tools/blender/bake_camera.py`, `CLAUDE.md` — empty `git diff` (untouched).
- Full suite: 457 passed, 2 skipped (was 450/2 → +7 new, no regressions).

---
*Quick task: 260429-gde*
*Completed: 2026-04-29*
