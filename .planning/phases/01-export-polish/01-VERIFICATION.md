---
phase: 01-export-polish
verified: 2026-04-19T00:00:00Z
status: human_needed
score: 4/5
overrides_applied: 0
human_verification:
  - test: "Right-click an Action with a single non-Perspective camera in Flame and select 'Export Camera to Blender'"
    expected: "Blender opens on the target .blend file with zero dialogs (no width/height prompt, no save-path prompt). Only a post-launch informational summary dialog appears."
    why_human: "Full happy-path requires a live Flame 2026.2.1 instance with an Action node plus a working Blender binary. The probe (Plan 01) confirmed PyActionNode.resolution shape; static code analysis confirms no QInputDialog.getText or QFileDialog.getSaveFileName in the handler body. The code path is sound but end-to-end runtime is unavailable to the verifier."
---

# Phase 1: Export Polish — Verification Report

**Phase Goal:** Users can right-click an Action and launch Blender on the target camera without any dialogs, with temp files cleaned up automatically and metadata stamped on the camera for the return trip.
**Verified:** 2026-04-19T00:00:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Right-clicking an Action and selecting "Export Camera to Blender" opens Blender without presenting any width/height or save-path dialog | ? HUMAN NEEDED | Static: `QInputDialog.getText` and `QFileDialog.getSaveFileName` are absent from `_export_camera_to_blender` body (AST-confirmed). Handler delegates to `_infer_plate_resolution` (no user prompt) and computes output path as `~/forge-bakes/{safe_action}_{safe_cam}.blend` (no prompt). A post-bake info summary dialog does appear — this is documented as intentional and not a gate dialog. End-to-end runtime cannot be confirmed without live Flame. |
| 2 | Plate resolution is inferred from the Action node's `resolution` attribute — no manual entry required | ✓ VERIFIED | `_infer_plate_resolution` implements a three-tier fallback: Tier 1 reads `action_node.resolution.get_value()` using the access pattern confirmed by Plan 01's live probe (`TIER1_DISPOSITION: use-attr-width-height`). Tier 2 reads `flame.batch.width/height`. Tier 3 reads `_scan_first_clip_metadata()`. On total failure, `PlateResolutionUnavailable` is raised and surfaced as an error dialog — never silently defaults to 1920x1080. |
| 3 | After a successful export, only the `.blend` file remains visible; the intermediate `.fbx` and `.json` temp files are gone | ✓ VERIFIED | `tempfile.mkdtemp(prefix="forge_bake_")` creates the temp dir; `shutil.rmtree(temp_dir, ignore_errors=True)` is called inside a `finally` block guarded by `if success:`. On failure, the temp dir is preserved and its path appears in every error dialog. The `.blend` lands in `~/forge-bakes/{safe_action}_{safe_cam}.blend` via `os.makedirs(out_dir, exist_ok=True)`. |
| 4 | The exported Blender camera has `forge_bake_action_name` and `forge_bake_camera_name` custom properties stamped on it with the correct Flame Action and camera names | ✓ VERIFIED | `fbx_to_v5_json` is called with `custom_properties={"forge_bake_action_name": raw_action_name, "forge_bake_camera_name": raw_cam_name}` where raw names are the unsanitized `_val(...)` results. `fbx_to_v5_json` serializes these to the v5 JSON under `"custom_properties"`. `bake_camera.py::_stamp_metadata` reads `data.get("custom_properties")` and applies each entry as `cam_data[key] = value` onto the bpy camera ID-block. Round-trip is test-verified (all 55 `test_fbx_ascii.py` tests pass including 4 new `TestFbxToV5JsonCustomProperties` tests). |
| 5 | Blender launches without stealing focus by default; a `blender_launch_focus_steal` key in `.planning/config.json` lets the user opt into focus-steal mode | ✓ VERIFIED | `.planning/config.json` contains `"blender_launch_focus_steal": false` (JSON boolean, Python `bool`). `_read_launch_focus_steal()` exists at module scope in `camera_match_hook.py`, reads the key per-invocation, returns `False` on any I/O/JSON failure (tolerant). `_export_camera_to_blender` calls `_read_launch_focus_steal()` and passes the result to `_launch_blender_on_blend(blend_path, focus_steal=focus_steal)`. On macOS: `open -a Blender <path>` when `True`, `open -a -g Blender <path>` when `False`. On Linux: `subprocess.Popen([blender_bin, blend_path], start_new_session=True)`. No `shell=True` used. |

**Score:** 4/5 truths verified; 1 requires human runtime confirmation

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `.planning/phases/01-export-polish/01-PROBE.md` | Documented shape of `action.resolution` for Plan 04 | ✓ VERIFIED | File exists. Contains Steps 1-4 headings. Exactly one `TIER1_DISPOSITION: use-attr-width-height` line. Rationale and Python access snippet present. No destructive calls. Probe C absent (gate fired at B). |
| `forge_flame/fbx_ascii.py` | Extended `fbx_to_v5_json` with `custom_properties` kwarg | ✓ VERIFIED | Signature at line 719: `custom_properties: Optional[dict] = None,`. Payload block: `if custom_properties: payload["custom_properties"] = dict(custom_properties)`. Google-style docstring updated. Backward-compatible (None/empty → no key emitted). |
| `tools/blender/bake_camera.py` | Extended `_stamp_metadata` with `custom_properties` arg | ✓ VERIFIED | `from typing import Optional` added. `_stamp_metadata` now takes 4 positional args: `cam_data, scale, source_path, custom_properties`. Body applies dict entries to `cam_data[key] = value`. Caller in `_bake` passes `data.get("custom_properties")`. All four original stamp keys preserved. No `from __future__ import annotations`. |
| `tests/test_fbx_ascii.py` | Regression tests for `custom_properties` round-trip | ✓ VERIFIED | `TestFbxToV5JsonCustomProperties` class with 4 tests (A: round-trip to disk+return; B: omit kwarg → no key; C: empty dict → no key; D: shallow-copy mutation defense). All 55 tests pass. |
| `.planning/config.json` | Top-level `blender_launch_focus_steal: false` | ✓ VERIFIED | Key present, value is JSON `false` (Python `bool(False)`). File valid JSON. All pre-existing keys and values unchanged. |
| `flame/camera_match_hook.py` | Reworked `_export_camera_to_blender` + all new helpers | ✓ VERIFIED | `_read_launch_focus_steal`, `_sanitize_name_component`, `PlateResolutionUnavailable`, `_infer_plate_resolution`, `_launch_blender_on_blend`, `_export_camera_to_blender`, `_SANITIZE_NAME_RE` all exist. `_scan_first_clip_metadata` returns `None` on miss (not 1920x1080). File compiles clean (`py_compile` exits 0). |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `fbx_to_v5_json` | v5 JSON on disk | `payload["custom_properties"] = dict(custom_properties)` | ✓ WIRED | Pattern present at line 781-782. |
| `bake_camera.py::_bake` | `_stamp_metadata` | `data.get("custom_properties")` | ✓ WIRED | Line 225: `_stamp_metadata(cam.data, scale, args.in_path, data.get("custom_properties"))`. |
| `_export_camera_to_blender` | `fbx_to_v5_json(custom_properties={...})` | Plan 02 kwarg | ✓ WIRED | Lines 2111-2119: handler passes `custom_properties={"forge_bake_action_name": raw_action_name, "forge_bake_camera_name": raw_cam_name}`. |
| `_export_camera_to_blender` | `_read_launch_focus_steal()` | Per-invocation read | ✓ WIRED | Line 2172: `focus_steal = _read_launch_focus_steal()` called before Blender spawn. |
| `_export_camera_to_blender` | `_launch_blender_on_blend` | Platform-branched spawn | ✓ WIRED | Line 2174: `_launch_blender_on_blend(blend_path, focus_steal=focus_steal)`. |
| `_read_launch_focus_steal` | `.planning/config.json` | `json.load` at runtime | ✓ WIRED | Helper reads `repo_root/.planning/config.json` via `__file__`-relative path derivation. Tolerant of any failure. |
| `_infer_plate_resolution` | `action.resolution.get_value()` | PROBE.md `use-attr-width-height` | ✓ WIRED | Lines 1889-1893: Tier 1 reads `action_node.resolution.get_value()` then `int(r.width), int(r.height)`. |
| `tempfile.mkdtemp` | `shutil.rmtree` on success | `if success: shutil.rmtree(temp_dir)` in `finally` | ✓ WIRED | Lines 2083 and 2163-2167: temp dir created then cleaned only on success. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `_export_camera_to_blender` | `width, height` | `_infer_plate_resolution(action_node)` → Tier 1: `action_node.resolution.get_value()` | Yes — live Flame PyAttribute read confirmed by Plan 01 probe | ✓ FLOWING |
| `fbx_to_v5_json` | `payload["custom_properties"]` | Caller supplies `{"forge_bake_action_name": raw_action_name, "forge_bake_camera_name": raw_cam_name}` from `_val(action_node.name)` / `_val(cam.name)` | Yes — names from live Flame PyAttribute | ✓ FLOWING |
| `bake_camera.py::_stamp_metadata` | `cam_data[key] = value` | `data.get("custom_properties")` from parsed v5 JSON | Yes — populated by `fbx_to_v5_json` and serialized to disk | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| 55 tests pass (including 4 custom_properties round-trip tests) | `pytest tests/ -x -q` | 268 passed, 0 failed | ✓ PASS |
| `fbx_to_v5_json` signature accepts `custom_properties` | `grep -E "custom_properties: Optional\[dict\] = None" forge_flame/fbx_ascii.py` | 1 match at line 719 | ✓ PASS |
| `_stamp_metadata` signature has 4 args including `custom_properties` | Python AST check | `cam_data, scale, source_path, custom_properties` confirmed | ✓ PASS |
| `config.json` valid JSON with correct bool type | `python -m json.tool` + `type()` check | `bool(False)` | ✓ PASS |
| Hook compiles without errors | `python -m py_compile flame/camera_match_hook.py` | Exit 0 | ✓ PASS |
| No resolution or save-path dialog in handler | AST source segment check | `QInputDialog.getText: False`, `QFileDialog.getSaveFileName: False` | ✓ PASS |
| Blender spawn uses argv lists, no shell=True | AST source segment check of `_launch_blender_on_blend` | `shell=True: False`, `subprocess.Popen: True`, `start_new_session: True` | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|---------|
| EXP-01 | Plan 04 | Right-click Action → Blender launches with zero dialogs | ? NEEDS HUMAN | Code path is dialog-free (AST verified). Runtime requires live Flame. |
| EXP-02 | Plans 01, 04 | Plate resolution inferred from `resolution` PyAttribute | ✓ SATISFIED | Plan 01 probe confirmed `use-attr-width-height`. Plan 04 consumes snippet verbatim. Three-tier fallback with no silent default. |
| EXP-03 | Plan 04 | Intermediate `.fbx`/`.json` removed on success; `.blend` remains | ✓ SATISFIED | `tempfile.mkdtemp` + `shutil.rmtree` on success only, in `finally` block. |
| EXP-04 | Plans 02, 04 | Custom properties `forge_bake_action_name` + `forge_bake_camera_name` stamped | ✓ SATISFIED | Full pipeline wired: `fbx_to_v5_json` kwarg → v5 JSON → `_stamp_metadata` → bpy ID-block. Test-verified. |
| EXP-05 | Plans 03, 04 | `blender_launch_focus_steal` key in config controls Blender focus | ✓ SATISFIED | Key in `config.json` (bool `false`). `_read_launch_focus_steal()` helper reads it per-invocation. Handler uses result in `_launch_blender_on_blend`. macOS `-g` flag wired correctly. |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None found | - | - | - | - |

Scanned: `flame/camera_match_hook.py` (new functions), `forge_flame/fbx_ascii.py` (modified region), `tools/blender/bake_camera.py`, `tests/test_fbx_ascii.py`. No TODO/FIXME/placeholder comments, no empty implementations, no hardcoded empty data flowing to user-visible output, no `return null` stubs.

### Human Verification Required

#### 1. Happy-path end-to-end: zero-dialog export to Blender

**Test:** On a machine with Flame 2026.2.1 and Blender installed:
1. Sync files: `rsync -av flame/ forge_flame/ forge_core/ tools/ /opt/Autodesk/shared/python/`
2. Restart Flame.
3. Open a Batch that contains an Action node with a single non-Perspective camera and a source clip.
4. Right-click the Action → "Camera Match" → "Export Camera to Blender".

**Expected:**
- No width/height dialog appears.
- No save-path dialog appears.
- Blender opens on `~/forge-bakes/{action}_{cam}.blend` in the background (no focus steal).
- The `.blend` camera's custom properties (Object Properties → Custom Properties) shows `forge_bake_action_name` and `forge_bake_camera_name` with the correct Flame names.
- Only the `.blend` remains in `~/forge-bakes/`; the temp dir under `/tmp/forge_bake_*` is gone.
- A single info summary dialog in Flame confirms the bake parameters.

**Why human:** Requires a live Flame 2026.2.1 instance with a real Action node, PyActionNode.resolution readable, and a Blender binary. The static verification (Plan 01 probe, AST checks, test suite) covers all individual components; only the full integrated path needs runtime confirmation.

### Gaps Summary

No blocking gaps found. All five success criteria are either statically verified (SC2–SC5) or pending only runtime confirmation that requires live Flame (SC1). The code delivering SC1 is clean: no dialog-triggering calls in the handler body, correct helper wiring, all 268 tests pass.

---

_Verified: 2026-04-19T00:00:00Z_
_Verifier: Claude (gsd-verifier)_
