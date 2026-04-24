---
phase: 02-blender-addon
fixed_at: 2026-04-24T00:24:58Z
review_path: .planning/phases/02-blender-addon/02-REVIEW.md
iteration: 1
findings_in_scope: 2
fixed: 2
skipped: 0
status: all_fixed
---

# Phase 2: Code Review Fix Report

**Fixed at:** 2026-04-24T00:24:58Z
**Source review:** `.planning/phases/02-blender-addon/02-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope: 2 (2 warnings — Info out of scope per fix_scope=critical_warning)
- Fixed: 2
- Skipped: 0

Both Core-Value-impacting warnings (silent fps fallbacks that break the Flame↔Blender fidelity contract) were resolved. Info items (IN-01 tuple-literal type hint, IN-02 duplicate fps map drift, IN-03 duck-typed node name) are out of scope for this fix pass.

Phase 4.1 connection: per `.planning/phases/04.1-phase-4-polish-items-stereo-rig-filter-empty-camera-ux-fps-s/04.1-CONTEXT.md` D-10, these fixes land BEFORE Phase 4.1 plan execution. The `fix(02-01)` and `fix(02-02)` subjects cross-reference 02-REVIEW.md so provenance is preserved.

## Fixed Issues

### WR-01: `_resolve_frame_rate` silently skips an explicitly stamped but unsupported `forge_bake_frame_rate` value

**Files modified:** `tools/blender/forge_sender/__init__.py`
**Commit:** `094c3b3`
**Applied fix:** Replaced the step-1 silent fall-through on unsupported stamp with a fail-loud guard. When `cam.data['forge_bake_frame_rate']` is present but the string-coerced value is not one of the nine labels in `_FLAME_FPS_LABELS`, `_resolve_frame_rate` now returns `(None, err_msg)` naming the bad value and listing the supported labels. The operator surfaces the message via `_popup()` and cancels the send, matching the Core Value (fidelity over frictionless UX): a stamp of `"12 fps"`, an `IDPropertyArray` coerced to `"[24]"`, or any other drift can no longer silently get replaced by the scene fps.

**Test result:** `python -m pytest tests/test_forge_sender_transport.py tests/test_forge_sender_preflight.py tests/test_forge_sender_flame_math.py -q` — **43 passed, 1 skipped** (no regression from the pre-fix baseline of 43 passed / 1 skipped). No existing test directly covered `_resolve_frame_rate`; behaviour is exercised live via the operator and the Phase 4.1 E2E bridge path.

### WR-02: `v5_json_str_to_fbx` silently falls back to 24 fps on unknown frame-rate keys — no fidelity gate above it

**Files modified:** `tools/blender/forge_sender/transport.py`, `tests/test_forge_sender_transport.py`
**Commit:** `d68b77c`
**Applied fix:**
1. Added a defense-in-depth guard inside `_FLAME_SIDE_TEMPLATE` that runs before `v5_json_str_to_fbx`. It raises `RuntimeError("Unknown Flame frame rate: %r -- expected one of %s" % (frame_rate, sorted(fbx_ascii._FPS_FROM_FRAME_RATE)))` if the caller-supplied frame-rate is not a key in `_FPS_FROM_FRAME_RATE`. The `RuntimeError` bubbles out of `_forge_send()`, through the bridge envelope, and into the operator's Remote Tier popup — the artist sees the mismatch rather than getting a silently-24-fps FBX. Used `%`-formatting (not f-strings) to stay consistent with the surrounding template style and avoid brace-escaping concerns inside the `.format()` template.
2. Updated three `_FakeFbxAscii*` fakes in `tests/test_forge_sender_transport.py` (used by the stereo-rig filter tests and the instrumentation-logging tests) to expose `_FPS_FROM_FRAME_RATE = {"24 fps": 24.0}`. Every template-exec fixture already formats the template with `frame_rate_repr=repr("24 fps")`, so providing that single key unblocks the happy paths without changing their semantics.
3. Added a new test `TestBuildPayload::test_template_guards_frame_rate_against_fps_map` — a grep anchor that asserts `fbx_ascii._FPS_FROM_FRAME_RATE` and `"Unknown Flame frame rate"` both appear in the template. Matches the existing grep-anchor pattern (`test_template_contains_duck_type_predicate`, `test_template_contains_forge_send_debug_log_filename`) and catches accidental removal of the guard during future refactors.

**Test result:**
- `python -m pytest tests/test_fbx_ascii.py -k 'v5_json_str' -q` — **3 passed, 85 deselected** (unchanged).
- `python -m pytest tests/test_forge_sender_transport.py tests/test_forge_sender_preflight.py tests/test_forge_sender_flame_math.py -q` — **44 passed, 1 skipped** (43 pre-fix + 1 new grep-anchor test).

## Skipped Issues

None — both in-scope findings were fixed cleanly.

## Notes

- Info findings IN-01, IN-02, IN-03 were explicitly scoped out by the orchestrator (fix_scope: critical_warning). Those remain as Phase 4+ polish items.
- IN-02 (duplicate frame-rate mapping between `_FLAME_FPS_LABELS` addon-side and `_FPS_FROM_FRAME_RATE` in fbx_ascii) is the drift hazard that WR-02's defense-in-depth guard directly protects against — so the WR-02 fix partially mitigates IN-02 even though IN-02 itself was not addressed structurally.
- No rollbacks were required. Both fixes passed Tier 1 (re-read) and Tier 2 (AST parse + targeted pytest) verification on first application. The test-fixture updates in WR-02 were anticipated per the orchestrator prompt ("that's an expected test update, not a regression") — the fixtures were instantiating minimal `_FakeFbxAscii` classes without the attribute the new guard references.

---

_Fixed: 2026-04-24T00:24:58Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
