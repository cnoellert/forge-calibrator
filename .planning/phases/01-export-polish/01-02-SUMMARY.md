---
phase: 01-export-polish
plan: "02"
subsystem: fbx-json-schema
tags:
  - fbx
  - v5-json
  - blender
  - schema
  - custom-properties
dependency_graph:
  requires: []
  provides:
    - "fbx_to_v5_json accepts custom_properties kwarg and emits top-level key"
    - "_stamp_metadata applies caller-supplied dict to bpy camera ID-block"
  affects:
    - "forge_flame/fbx_ascii.py (fbx_to_v5_json signature + payload block)"
    - "tools/blender/bake_camera.py (_stamp_metadata + _bake caller)"
    - "tests/test_fbx_ascii.py (4 new regression tests)"
tech_stack:
  added: []
  patterns:
    - "Optional[dict] keyword-only arg with falsy guard (if custom_properties:)"
    - "dict(custom_properties) shallow-copy defense against caller mutation"
    - "data.get('custom_properties') passthrough from v5 JSON into bpy ID-block"
key_files:
  created: []
  modified:
    - forge_flame/fbx_ascii.py
    - tools/blender/bake_camera.py
    - tests/test_fbx_ascii.py
decisions:
  - "Option A (additive kwarg to fbx_to_v5_json) chosen over Option B (post-hoc stamp) — keeps JSON write atomic and honors 'extend the v5 contract, do not bypass'"
  - "Empty dict (custom_properties={}) treated identically to None via falsy guard — empty key is noise, matches PATTERNS.md §3"
  - "Shallow copy via dict(custom_properties) mirrors list(action.selected_nodes.get_value()) style in fbx_io.py:81"
metrics:
  duration: "~12 minutes"
  completed: "2026-04-19"
  tasks_completed: 2
  tasks_total: 2
  files_modified: 3
---

# Phase 01 Plan 02: v5 JSON custom_properties + Blender consumer Summary

**One-liner:** Added `custom_properties: Optional[dict]` kwarg to `fbx_to_v5_json` and extended `bake_camera.py::_stamp_metadata` to apply the dict onto the bpy camera ID-block, enabling Plan 04's handler to stamp `forge_bake_action_name` + `forge_bake_camera_name` into the round-trip pipeline.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Extend fbx_to_v5_json with custom_properties kwarg + regression test | bc87ebf | forge_flame/fbx_ascii.py, tests/test_fbx_ascii.py |
| 2 | Extend bake_camera.py _stamp_metadata to apply custom_properties onto bpy camera data-block | ccc272f | tools/blender/bake_camera.py |

## Implementation Details

### Task 1 — fbx_to_v5_json extension

**Signature change (line 719):**
```python
custom_properties: Optional[dict] = None,
```
Added after `camera_name: Optional[str] = None,` in the keyword-only block.

**Payload conditional (lines 781-782):**
```python
if custom_properties:
    payload["custom_properties"] = dict(custom_properties)
```
Inserted after the base `payload` dict construction at lines 777-780. The falsy guard handles both `None` and `{}`. `dict(custom_properties)` is the shallow-copy defense.

**Docstring:** Args block extended at lines 742-748 with a `custom_properties:` bullet in Google style.

**FBX fixture used:** `tests/fixtures/forge_fbx_baked.fbx` — live Flame 2026.2.1 export with `bake_animation=True`. Camera name in the fixture is `"Default"` (the `Model::Default` node). Tests use `camera_name="Default"` to filter to that camera.

**Tests added (TestFbxToV5JsonCustomProperties, 4 tests):**
- Test A: round-trips `{"forge_bake_action_name": "Action_01", "forge_bake_camera_name": "Cam_01"}` — checks both returned dict and on-disk JSON
- Test B: omitting kwarg produces no `custom_properties` key in JSON
- Test C: `custom_properties={}` also produces no key
- Test D: mutating input dict after call does not affect on-disk JSON

All 55 tests in `test_fbx_ascii.py` pass.

### Task 2 — bake_camera.py extension

**Import added (line 63):**
```python
from typing import Optional
```
Placed alphabetically in the stdlib block after `import sys`, before the blank line separating stdlib from third-party `bpy`. No `from __future__ import annotations` added (intentional — bpy-standalone script).

**_stamp_metadata signature (line 149):**
```python
custom_properties: Optional[dict] = None,
```
Fourth parameter added. Full Google-style docstring written explaining the `cam.data` vs. `cam` distinction and the v5 contract type restriction.

**_stamp_metadata body (lines 171-172):**
```python
if custom_properties:
    for key, value in custom_properties.items():
        cam_data[key] = value
```
Applied after the four fixed keys. Same falsy guard pattern as Task 1.

**Caller update (line 225):**
```python
_stamp_metadata(cam.data, scale, args.in_path, data.get("custom_properties"))
```
`data` is the already-parsed v5 JSON dict. `data.get("custom_properties")` returns `None` when absent — matches the guard in `_stamp_metadata`.

**Verification:** AST parse confirms `_stamp_metadata` now has exactly four positional args: `cam_data, scale, source_path, custom_properties`. All four existing stamp keys preserved.

## Discoveries for Plan 04

- **Camera name in baked FBX fixture is `"Default"`**, not `"Camera"`. When Plan 04 calls `fbx_to_v5_json` with `camera_name=_val(cam.name)`, the name must exactly match the FBX `Model::<name>` token — verify that `_val(cam.name)` returns the same string Flame embeds in the FBX.
- **`forge_fbx_baked.fbx` has `bake_animation=True`** (two-keyframe endpoints). The `fbx_to_v5_json` call in the export handler will work correctly with this fixture since `custom_properties` passthrough is payload-level, not frame-level.
- **No existing reader for `.planning/config.json` in any Python file** — Plan 04 will need the `_read_launch_focus_steal` helper from PATTERNS.md §4 when it implements the Blender launch spawn.

## Deviations from Plan

None — plan executed exactly as written. Option A (additive kwarg) was chosen as recommended and matches the plan's `key_links` specification exactly.

## Known Stubs

None — both changes are fully wired. `fbx_to_v5_json` emits the key when given a non-empty dict; `_stamp_metadata` applies it to the bpy ID-block. Plan 04 is the caller that will populate `forge_bake_action_name` + `forge_bake_camera_name`.

## Threat Flags

None — no new network endpoints, auth paths, file access patterns, or schema changes at trust boundaries beyond what the plan's threat model already covers (T-02-01 through T-02-04).

## Self-Check: PASSED

- `forge_flame/fbx_ascii.py` modified and committed at bc87ebf
- `tests/test_fbx_ascii.py` modified and committed at bc87ebf
- `tools/blender/bake_camera.py` modified and committed at ccc272f
- All 55 tests in `test_fbx_ascii.py` pass
- AST check of `bake_camera.py` confirms `_stamp_metadata` signature
- `grep` acceptance criteria all match
