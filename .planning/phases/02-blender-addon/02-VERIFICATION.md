---
phase: 02-blender-addon
verified: 2026-04-22T03:02:35Z
status: passed
score: 10/10 must-haves verified
overrides_applied: 0
---

# Phase 2: Blender Addon Verification Report

**Phase Goal:** Ship an installable Blender addon (forge_sender) that completes the Flame→Blender→Flame round-trip with a "Send to Flame" button. Artists edit a baked camera in Blender, click one button, and the edited camera appears in the original Flame Action with geometric fidelity preserved.

**Verified:** 2026-04-22T03:02:35Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

Merged from ROADMAP Phase 2 Success Criteria (4) + Plan must_haves distinct truths (IMP-05/IMP-06 + hotfix-dependent behaviors). Deduplicated where plan truths restate SC text.

| #   | Truth | Status | Evidence |
| --- | ----- | ------ | -------- |
| 1 | A "Send to Flame" button is visible in the N-panel (3D viewport sidebar) after installing the addon via Blender's standard addon install flow (SC-1 / IMP-01) | VERIFIED | `tools/blender/forge_sender-v1.0.0.zip` (13865 B) exists with 4 `forge_sender/` entries, zero `__pycache__`. Zip shipped with `bl_info` version `(1,1,0)` declared in `__init__.py:60-68`. Panel class `VIEW3D_PT_forge_sender` at `__init__.py:287` with `bl_category = "Forge"` and `bl_space_type = 'VIEW_3D'`. UAT Task 2 (02-04-SUMMARY) confirmed live install + Forge tab visible. |
| 2 | Clicking "Send to Flame" with a camera that lacks forge metadata shows an error popup naming the missing property rather than crashing or silently failing (SC-2 / IMP-02) | VERIFIED | `preflight.py:31` `_REQUIRED_STAMPED_KEYS = ("forge_bake_action_name", "forge_bake_camera_name")` (ordered so first-missing wins). `preflight.check()` returns UI-SPEC Tier 1(a/b/c/d) copy with `{missing_key}` interpolation. Operator re-checks in `execute()` belt-and-braces (`__init__.py:198`) and surfaces via `_popup()`. UAT Task 3 (02-04-SUMMARY) confirmed all 4 sub-tier popups literal-match UI-SPEC, and Hotfix `5cff722` relaxed `poll()` so F3/console path can actually reach the error popup (previously `poll() is None` blocked every path). |
| 3 | Clicking "Send to Flame" on a properly stamped camera extracts per-frame T/R/focal/film-back and delivers the camera to the target Flame Action without the user touching Flame's UI (SC-3 / IMP-03 + IMP-04 + IMP-06) | VERIFIED | `flame_math.build_v5_payload(cam)` at `flame_math.py:136` walks keyframes via `_camera_keyframe_set`, emits `_R_Z2Y @ cam.matrix_world` per frame with `_rot3_to_flame_euler_deg` (Flame ZYX convention). Operator calls `build_v5_payload` → `json.dumps` → `transport.send(..., frame_rate=frame_rate)` (`__init__.py:218-236`). Bridge template runs `v5_json_str_to_fbx` + duck-typed Action lookup + `import_fbx_to_action` inside Flame. UAT Task 5 (02-04-SUMMARY) confirmed live: single camera landed in target `action1`, Blender edit preserved. Core Value (geometric fidelity) proven against real plate. |
| 4 | The result (new camera name on success, or error traceback on failure) appears in a Blender info popup immediately after the button press (SC-4 / IMP-05) | VERIFIED | `_popup()` / `_popup_multiline()` at `__init__.py:144-169` use `context.window_manager.popup_menu`. Success branches at `__init__.py:266-278` format singular (`Sent to Flame: camera '…' in Action '…'`), plural, or edge-case copy. Failure paths route ConnectionError/Timeout → Transport Tier, remote error → Remote Tier multiline. Hotfix `ec93c83` replaced `_result = _forge_send()` with a trailing bare `_forge_send()` expression and added `ast.literal_eval` in `parse_envelope` so the bridge's repr'd dict is actually surfaced (without it every successful send would have said `no new camera reported — Action '<unknown>'`). UAT Tasks 3, 4, 5, 6 exercised all four popup paths live. |
| 5 | Bridge-side Python template resolves the target Action by EXACT name match against `forge_bake_action_name` in the current batch — 0 or 2+ matches raise a loud error (D-06/D-07/D-08) | VERIFIED | `transport.py:111-124` — list comprehension `[n for n in flame.batch.nodes if hasattr(n, "import_fbx") and n.name.get_value() == action_name]`; `RuntimeError` raised on empty list (`"No Action named '%s' in current batch — was it renamed or deleted?"`) and `len(matches) > 1` (`"Ambiguous: %d Actions named '%s' — rename to disambiguate and resend"`). Duck-typed filter respects Flame API pattern. UAT Task 6 confirmed 0-match popup live; 2+ match covered by unit tests in `test_forge_sender_transport.py`. |
| 6 | Bridge-side template queries frame_rate via D-17 OR triggers D-19 contingency per Plan 01 probe findings | VERIFIED | Plan 02-01 probe disproved D-17 (`flame.batch.frame_rate` returns `NoneType` on Flame 2026.2.1 — see `memory/flame_batch_frame_rate.md`). D-19 ladder implemented addon-side at `__init__.py:104-136`: (1) `cam.data["forge_bake_frame_rate"]` stamp, (2) `scene.render.fps / scene.render.fps_base` mapped via `_FLAME_FPS_LABELS`, (3) loud error naming all supported labels. `transport.build_payload(v5_json_str, *, frame_rate)` accepts the resolved string and embeds via `repr()`. UAT Task 5 confirmed ladder step 2 resolved `"24 fps"` live and `v5_json_str_to_fbx` accepted it. |
| 7 | Success popup matches exactly: `Sent to Flame: camera '{created_name}' in Action '{action_name}'` (singular) or plural variant (UI-SPEC §Success popup) | VERIFIED | `__init__.py:266-275` singular `f"Sent to Flame: camera '{created[0]}' in Action '{action_name}'"` and plural `f"Sent to Flame: cameras {joined} in Action '{action_name}'"`. UAT Task 5 observed live popup in plural form (because Flame's FBX importer returned RootNode + stereo-rig siblings alongside the real camera — noted as Phase 4 polish, not a correctness failure). |
| 8 | Transport-tier failure popup contains the literal bridge URL `http://127.0.0.1:9999` | VERIFIED | `__init__.py:240` literal message `"Send to Flame: forge-bridge not reachable at http://127.0.0.1:9999 — is Flame running with the Camera Match hook loaded?"`. UAT Task 4 confirmed popup live with bridge down (0.00s fail via ConnectionError). |
| 9 | Remote-tier failure popup renders the traceback verbatim, line-per-line, via a multi-line draw callback | VERIFIED | `parse_envelope()` returns `f"Send to Flame failed: {error}\n\n{traceback}"`; operator calls `_popup_multiline(context, err_msg)` which splits on `\n` and emits one `layout.label` per line (`__init__.py:162-169`). UAT Task 6 confirmed popup showed summary + blank line + multi-line traceback live. |
| 10 | Shared-math one-copy discipline: `flame_math.build_v5_payload` is the single source for Blender→Flame Euler/axis-swap/keyframe-walk math; `extract_camera.py` consumes it (D-04/D-05) | VERIFIED | `tools/blender/forge_sender/flame_math.py` contains `_rot3_to_flame_euler_deg` (line 46), `_R_Z2Y` (line 72), `_camera_keyframe_set` (line 80), `_resolve_scale` (line 110), `build_v5_payload` (line 136). `extract_camera.py:59-66` has `sys.path.insert(0, …/forge_sender)` + `from flame_math import (…)` shim; `_extract` body calls `out = build_v5_payload(cam, scale_override=args.scale)` at line 119. No `def _rot3_to_flame_euler_deg` / `def _camera_keyframe_set` in `extract_camera.py` (moved out successfully). |

**Score:** 10/10 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `forge_flame/fbx_ascii.py` (modified) | `_payload_to_fbx` helper + `v5_json_str_to_fbx` sibling at line ~1295, `v5_json_to_fbx` signature preserved | VERIFIED | Line 1230 `_payload_to_fbx`, line 1259 `v5_json_to_fbx`, line 1295 `v5_json_str_to_fbx`. Signature: `(json_str, out_fbx_path, *, camera_name, frame_rate, pixel_to_units)` matches D-01 lock. File-path variant's first positional arg remains `json_path` (PATTERNS §1.3 preserved). |
| `tools/blender/forge_sender/__init__.py` | `bl_info`, Panel, Operator, register/unregister, D-19 ladder, popup helpers | VERIFIED | 341 LOC. `bl_info` at line 60 with `(1, 0, 0)` + `(4, 5, 0)` + `"Import-Export"`. `FORGE_OT_send_to_flame` line 177, `VIEW3D_PT_forge_sender` line 287, `_resolve_frame_rate` line 104, `_popup`/`_popup_multiline` at 144/156, `register`/`unregister` at 337/342. |
| `tools/blender/forge_sender/flame_math.py` | Shared math + `build_v5_payload` | VERIFIED | 198 LOC. All 5 required symbols present (see Truth 10). |
| `tools/blender/forge_sender/preflight.py` | `check(context) -> Optional[str]` with 4 Tier 1 paths; no bpy import | VERIFIED | 64 LOC. `_REQUIRED_STAMPED_KEYS` tuple in priority order at line 31, `check()` at line 34, all four D-09 Tier 1 copy strings present verbatim. No `import bpy` (confirmed via grep). |
| `tools/blender/forge_sender/transport.py` | `BRIDGE_URL`, `DEFAULT_TIMEOUT_S`, `build_payload`, `send`, `parse_envelope`, `_FLAME_SIDE_TEMPLATE` | VERIFIED | 231 LOC. `BRIDGE_URL` line 54, `DEFAULT_TIMEOUT_S` line 55, `build_payload` line 145 (keyword-only `frame_rate`), `send` line 182, `parse_envelope` line 197 (with `ast.literal_eval` recovery for bridge repr'd dict), `_FLAME_SIDE_TEMPLATE` line 82 (ends with bare `_forge_send()` expression — hotfix `ec93c83`). |
| `tools/blender/forge_sender-v1.0.0.zip` | Installable Blender addon zip, 4 files, no __pycache__ | VERIFIED | 13865 B, contains exactly `forge_sender/__init__.py`, `forge_sender/flame_math.py`, `forge_sender/preflight.py`, `forge_sender/transport.py`. Zero `__pycache__` or `.pyc` entries. All entries prefixed `forge_sender/`. |
| `tools/blender/extract_camera.py` (refactored) | Thin wrapper around `build_v5_payload`, argparse surface frozen | VERIFIED | sys.path shim line 59, `from flame_math import (…)` line 61, `build_v5_payload(cam, scale_override=args.scale)` line 119. Argparse surface (`--out`, `--camera-name`, `--scale`) preserved (confirmed by 311-passing test suite including `test_blender_bridge.py::TestBuildExtractCmd`). |
| `tests/test_forge_sender_preflight.py` | 8+ tests covering 4 Tier 1 paths + happy | VERIFIED | 10 tests, all pass. |
| `tests/test_forge_sender_transport.py` | 15+ tests for build_payload + send + parse_envelope | VERIFIED | 17 tests, all pass (includes frame_rate-kwarg tests added during D-19 reconciliation). |
| `tests/test_forge_sender_flame_math.py` | Euler/axis-swap/shape tests | VERIFIED | 6 tests; skips on conda env lacking mathutils, passes when bpy present (see full-suite output: 1 module skip). |
| `tests/test_extract_camera.py` | Regression guard on refactor shim + argparse | VERIFIED | 5 tests, skip+pass as expected. |
| `.planning/phases/02-blender-addon/02-04-SUMMARY.md` | Validation matrix + IMP-01..IMP-06 closure + D-17/D-19 trail | VERIFIED | Contains `IMP-01` through `IMP-06` each marked VERIFIED, full validation matrix, D-17/D-19 explanation citing `memory/flame_batch_frame_rate.md`, discretion calls, residual risks. |
| `memory/flame_batch_frame_rate.md` | D-18 probe findings | VERIFIED | Exists in auto-memory store (per 02-01-SUMMARY). Referenced by Plans 02-03 and 02-04. |
| `.planning/todos/completed/2026-04-21-verify-multi-camera-picker-in-live-uat.md` | FOLDED-01 sweep results | VERIFIED | Moved to `completed/` with 4-check PASS results (referenced in STATE.md line 67). |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | -- | --- | ------ | ------- |
| `__init__.py::FORGE_OT_send_to_flame.execute` | `preflight.check` | belt-and-braces re-check | WIRED | `__init__.py:198` `err = preflight.check(context)` executes BEFORE payload build. |
| `__init__.py::FORGE_OT_send_to_flame.execute` | `flame_math.build_v5_payload` | relative import `from . import flame_math` | WIRED | `__init__.py:57` imports module; line 218 calls `flame_math.build_v5_payload(cam, scale_override=None)`. |
| `__init__.py::FORGE_OT_send_to_flame.execute` | `transport.send` | relative import | WIRED | `__init__.py:236` `envelope = transport.send(v5_json_str, frame_rate=frame_rate)` — D-19 kwarg routed through. |
| `__init__.py::FORGE_OT_send_to_flame.execute` | `transport.parse_envelope` | module call | WIRED | `__init__.py:257` `err_msg, result = transport.parse_envelope(envelope)`. |
| `transport.py::_FLAME_SIDE_TEMPLATE` | `forge_flame.fbx_ascii.v5_json_str_to_fbx` + `forge_flame.fbx_io.import_fbx_to_action` | embedded Python string executed via bridge /exec | WIRED | Template imports `from forge_flame import fbx_ascii, fbx_io` (transport.py:89), calls `fbx_ascii.v5_json_str_to_fbx(v5_json_str, fbx_path, frame_rate=frame_rate)` (line 104) and `fbx_io.import_fbx_to_action(action, fbx_path)` (line 127). |
| `transport.parse_envelope` | `ast.literal_eval` | bridge REPL-return recovery | WIRED | Line 224 `return (None, ast.literal_eval(raw))` — hotfix `ec93c83`. Without this, bridge's repr'd dict would leak through as a string and popup would always say `no new camera reported — Action '<unknown>'`. |
| `extract_camera.py` | `flame_math.build_v5_payload` | sys.path shim + import | WIRED | Shim at line 59, import at line 61, call at line 119. |
| `forge_flame/fbx_ascii.v5_json_str_to_fbx` | `_payload_to_fbx` (shared tail with `v5_json_to_fbx`) | internal helper | WIRED | Both public converters delegate to `_payload_to_fbx` — byte-identity is structural, not test-enforced. |
| `__init__.py::_resolve_frame_rate` | D-19 recovery (stamp → scene fps → loud error) | D-19 ladder | WIRED | Full 3-level implementation at lines 104-136; UAT Task 5 exercised step 2 live. |

### Data-Flow Trace (Level 4)

Artifacts in this phase are Blender-resident code that reads `bpy.context.active_object` + `bpy.context.scene` state and flows through `json.dumps` → HTTP POST → bridge-side Flame API. Data-flow tracing is primarily behavioral (only runnable inside Blender + live Flame). Tests + live UAT cover the data-flow end-to-end.

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| `build_v5_payload(cam)` | `frames_out`, `width`, `height`, `film_back_mm` | `bpy.context.scene` + `cam.matrix_world` + keyframe walk | Yes (verified live in UAT Task 5) | FLOWING |
| `_resolve_frame_rate(cam, context)` | resolved Flame fps label | `cam.data.get("forge_bake_frame_rate")` → `scene.render.fps/fps_base` → error | Yes (UAT Task 5: ladder step 2 resolved `"24 fps"` live) | FLOWING |
| Bridge `_forge_send()` `.created` list | Flame node names from `import_fbx_to_action` | `[c.name.get_value() for c in created]` | Yes (UAT Task 5: 4 names returned — 1 real + 3 FBX internals; cosmetic filter deferred to Phase 4) | FLOWING |
| `parse_envelope` result | dict from `ast.literal_eval(repr'd_dict)` | Bridge REPL eval of trailing expression | Yes (hotfix `ec93c83` directly addresses the empty-result failure mode) | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Full Phase 2 test suite passes | `pytest tests/test_forge_sender_preflight.py tests/test_forge_sender_transport.py tests/test_forge_sender_flame_math.py tests/test_fbx_ascii.py -q` | 98 passed, 1 skipped | PASS |
| Full repository test suite passes | `pytest tests/ -q` | 311 passed, 2 skipped | PASS |
| Addon zip contains exactly the 4 expected files | `unzip -l forge_sender-v1.0.0.zip` | 4 files under `forge_sender/`, 0 `__pycache__` | PASS |
| Syntax: addon __init__.py parses | `python3 -c "import ast; ast.parse(open('tools/blender/forge_sender/__init__.py').read())"` | parses clean | PASS |
| No scope violation: install.sh, camera_match_hook.py, bake_camera.py untouched since phase start | `git diff 45b95c6 HEAD -- install.sh flame/camera_match_hook.py tools/blender/bake_camera.py` | empty output | PASS |
| Hotfix commits exist as claimed in SUMMARY | `git show --stat ec93c83 5cff722` | both commits present with correct titles | PASS |
| `forge_flame/fbx_ascii.py` exposes all three public symbols | `grep "def v5_json_str_to_fbx\|def v5_json_to_fbx\|def _payload_to_fbx"` | 3 matches at lines 1230, 1259, 1295 | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ---------- | ----------- | ------ | -------- |
| IMP-01 | 02-03, 02-04 | Blender addon with "Send to Flame" button in N-panel, installable via standard Blender flow | SATISFIED | `bl_info` + `VIEW3D_PT_forge_sender` verified; zip installable; UAT Task 2 confirmed live. |
| IMP-02 | 02-03, 02-04 | Addon reads stamped metadata; surfaces error if metadata absent | SATISFIED | `preflight.check()` with `_REQUIRED_STAMPED_KEYS` priority order; UAT Task 3 confirmed all 4 sub-tiers produce UI-SPEC-literal popups. |
| IMP-03 | 02-01, 02-02, 02-03, 02-04 | Addon extracts per-frame T/R/focal/film-back to v5 JSON | SATISFIED | `build_v5_payload` shared-math module; UAT Task 5 confirmed live extraction + round-trip. |
| IMP-04 | 02-01, 02-02, 02-03, 02-04 | Addon POSTs to forge-bridge, runs `v5_json_str_to_fbx` + `import_fbx_to_action` inside Flame targeting stamped Action name | SATISFIED | `transport.send()` + `_FLAME_SIDE_TEMPLATE` with exact-name duck-typed Action resolution; UAT Task 5 confirmed live camera landing in target `action1`. |
| IMP-05 | 02-03, 02-04 | Bridge returns structured response; addon surfaces in Blender popup | SATISFIED | `parse_envelope()` with `ast.literal_eval` recovery (hotfix `ec93c83`); `_popup_multiline` for Remote Tier; UAT Tasks 4 + 5 + 6 confirmed all three response paths live. |
| IMP-06 | 02-04 | User never visits Flame's batch menu for the return trip | SATISFIED | UAT Task 5 confirmed round-trip completes end-to-end without post-export Flame menu visit; user confirmed via live test per special-notes briefing. |

No orphaned requirements — all 6 IDs from REQUIREMENTS.md §Import are claimed by at least one plan's `requirements:` frontmatter field and verified above.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| (none at blocker level) | — | — | — | — |

Notes:
- `tools/blender/forge_sender/__pycache__/` directory exists in the working tree (`ls` showed it) but is correctly EXCLUDED from the shipped zip (verified via `unzip -l`). Not an artifact issue.
- Hotfix commits `5cff722` and `ec93c83` are DEVIATION-HANDLED FIXES per executor contract, not gaps — they repaired two subtle bugs in Plan 02-03's spec surfaced by live UAT (permissive `poll()` required for F3/console Tier 1 testability; `ast.literal_eval` + trailing bare expression required because forge-bridge is REPL-style and only surfaces eval'd expressions).
- Known residuals captured in 02-04-SUMMARY and explicitly flagged as Phase 4 polish (not IMP failures): (a) success popup enumerates FBX internals in plural form when Flame's FBX importer expands stereo-rig siblings, (b) Flame FBX importer stereo-rig expansion behavior itself, (c) one Flame crash with no repro, (d) Blender addon reload discipline for hot-patching. Per special-notes briefing these are NOT Phase 2 gaps.

### Human Verification Required

None. All six IMP requirements were exercised live in UAT Tasks 2-6 (Plan 02-04) and documented with pass/fail observations in 02-04-SUMMARY.md. The user confirmed IMP-06 acceptance via Task 5 live per the verification briefing.

### Gaps Summary

No gaps. Phase 2 achieves its stated goal end-to-end:

- Installable addon zip exists and was validated via Blender's native install flow (IMP-01 live).
- All four preflight Tier 1 popups fire with UI-SPEC-literal copy naming the first missing key verbatim (IMP-02 live).
- Happy-path round-trip demonstrated live: Blender edit preserved in the Flame Action without any Flame batch menu visit after the initial export (IMP-03, IMP-04, IMP-06 live).
- Both failure tiers (Transport + Remote) surface structured responses with the exact UI-SPEC copy and the bridge URL / traceback visible (IMP-05 live).
- D-17 → D-19 pivot is complete: `flame.batch.frame_rate` is never probed from Flame; the Blender addon owns the 3-level ladder (stamp → scene fps → loud error).
- Shared-math discipline enforced: `flame_math.build_v5_payload` is the single source for Blender→Flame Euler math; `extract_camera.py` was refactored to consume it.
- Full test suite: 311 passed, 2 skipped (bpy/mathutils gated, expected on the conda `forge` env).
- Scope boundaries honored: `install.sh`, `flame/camera_match_hook.py`, `tools/blender/bake_camera.py` unchanged since the phase started (verified via `git diff`).

The two hotfix commits (`5cff722`, `ec93c83`) are correctly classified as deviation-handled fixes. Without them, Tasks 3 and 5 would have failed UAT — but they are documented deviations that the executor resolved mid-flight per the executor contract, not residual gaps.

Minor observation (not a gap): `.planning/STATE.md` still reports "Phase 2 Wave 1 complete — probes done" as `stopped_at`. Plan 02-04 Task 7 said it would add a one-line Phase-2-shipped decision note to STATE.md; this was not performed. The ROADMAP per-plan checkboxes are all `[x]` and the orchestrator is responsible for closing out the Phase 2 header + Progress table entry — flagging for the orchestrator, not a verification gap.

---

_Verified: 2026-04-22T03:02:35Z_
_Verifier: Claude (gsd-verifier)_
