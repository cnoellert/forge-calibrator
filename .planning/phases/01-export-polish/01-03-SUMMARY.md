---
phase: 01-export-polish
plan: "03"
subsystem: config-surface
tags:
  - config
  - flame-hook
  - blender-launch
dependency_graph:
  requires: []
  provides:
    - blender_launch_focus_steal config key (default false)
    - _read_launch_focus_steal() helper in camera_match_hook.py
  affects:
    - Plan 04 (_export_camera_to_blender wiring)
tech_stack:
  added: []
  patterns:
    - per-invocation config read (no module-state caching)
    - os.path.__file__-relative repo_root derivation (matches existing _ensure_forge_core_on_path idiom)
key_files:
  created: []
  modified:
    - .planning/config.json
    - flame/camera_match_hook.py
decisions:
  - "Placed _read_launch_focus_steal between _pick_camera and _export_camera_to_blender (line 1793) to group with export-related module-level helpers"
  - "import json kept inline (lazy) per module convention; os already at module level"
  - "No unit test added — helper is a one-liner wrap over json.load(...).get(...) with blanket except; test would exceed helper size (per CONTEXT.md simplicity bias)"
metrics:
  duration: "~5 minutes"
  completed: "2026-04-19"
  tasks_completed: 2
  files_modified: 2
---

# Phase 01 Plan 03: Config Surface + Focus-Steal Reader Helper Summary

One-liner: Added `blender_launch_focus_steal: false` to config.json and a tolerant per-invocation reader helper `_read_launch_focus_steal()` in the hook module for Plan 04 to call before spawning Blender.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add blender_launch_focus_steal key to config.json | 8e83a4f | .planning/config.json |
| 2 | Add _read_launch_focus_steal helper to camera_match_hook.py | 4065d10 | flame/camera_match_hook.py |

## Implementation Details

### Task 1: config.json

Added one top-level boolean key after `"search_gitignored": false`:

```json
"blender_launch_focus_steal": false,
```

The value is the JSON boolean `false` (Python loads it as `bool(False)`). All existing keys and values are unchanged. File remains valid JSON with 2-space indentation.

### Task 2: _read_launch_focus_steal helper

Inserted at **line 1793** in `flame/camera_match_hook.py`, between `_pick_camera` (ends line 1790) and `_export_camera_to_blender` (now starts line 1818). The helper is 22 lines including docstring and blank lines.

Key properties:
- Module-level function with `-> bool` return annotation
- Uses `os.path.dirname(os.path.abspath(__file__))` to derive `repo_root` — mirrors the existing idiom in `_ensure_forge_core_on_path` (line 51)
- `import json` is inline (lazy) per this file's convention for deferring heavy imports
- Entire read wrapped in `except Exception: return False` — satisfies T-03-02 (malformed JSON DoS mitigation)
- Returns `bool(...)` to coerce any truthy JSON value to Python bool
- On installed deployments (`/opt/Autodesk/shared/python/camera_match/`) there is no `.planning/` sibling; the try/except returns `False` (correct documented default per D-02)

## Note for Plan 04

The helper `_read_launch_focus_steal` exists at module scope in `flame/camera_match_hook.py`. Plan 04 calls it directly from `_export_camera_to_blender` — no import needed (same module). The call site pattern is:

```python
focus_steal = _read_launch_focus_steal()
# then use focus_steal to decide macOS `open -a [-g]` flag
```

## Deviations from Plan

None — plan executed exactly as written.

## Self-Check: PASSED

- `.planning/config.json` contains `blender_launch_focus_steal: false` — FOUND
- `_read_launch_focus_steal` defined at line 1793 in camera_match_hook.py — FOUND
- `python -m py_compile flame/camera_match_hook.py` exits 0 — PASSED
- AST confirms `-> bool` annotation — PASSED
- `_export_camera_to_blender` unchanged (only additive lines inserted before it) — CONFIRMED
- Commit 8e83a4f (config.json) — FOUND
- Commit 4065d10 (hook helper) — FOUND
