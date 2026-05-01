---
quick_id: 260501-knl
status: complete
verdict: SHIPPED — single forge-themed scale-picker dialog replaces the 5-entry ladder menu
mode: quick
type: execute
wave: 1
depends_on: [260501-i31]
started: "2026-05-01T21:52:18Z"
completed: "2026-05-01T22:08:00Z"
duration_min: 16
files_modified:
  - flame/camera_match_hook.py
  - install.sh
  - tests/test_hook_export_camera_to_blender.py
files_created:
  - flame/scale_picker_dialog.py
  - tests/test_scale_picker_dialog.py
key_findings:
  - Single Action-scoped menu entry per surface (was 6 after i31) — clutter eliminated
  - New module flame/scale_picker_dialog.py exports pick_scale(parent, default) -> Optional[float]; lazy PySide6 import mirrors the _pick_camera precedent at camera_match_hook.py:2352-2424
  - Reuses _FORGE_SS stylesheet from camera_match_hook.py (lines 271-308) — single source of truth for forge palette, no color redef
  - Default selection: 100x button has setDefault(True) + objectName="primary" highlight (matches today's hardcoded behavior)
  - ESC / cancel / X all return None → menu wrapper skips _export_camera_pipeline call cleanly
  - i31 carry-overs (_LADDER_MENU_STOPS, _make_export_callback, kw-only flame_to_blender_scale parameter) preserved — factory still callable, just not registered in menus directly
  - install.sh updated with source-presence check + cp step for the new dialog module
---

# Quick Task 260501-knl — Forge-themed Scale-Picker Dialog — Summary

## One-liner

Reverted the 5-entry ladder menu from 260501-i31 (commit 6200771) — clutter removed. Replaced with a single forge-themed PySide6 scale-picker dialog (`pick_scale()` in new module `flame/scale_picker_dialog.py`). Right-click → 1 menu entry → dialog opens with 5 ladder buttons + 100x default highlighted → pick fires export, ESC cancels.

## Verdict

**SHIPPED.** One atomic commit (`699c601`), full test suite green (522 passed / 0 failed / 2 skipped — was 508/0/2 after i31 → +14 net new collected items: +2 picker-forwards + +2 cancel-skips + +10 dialog tests).

## What was built

**One commit:**

| Commit | Description |
|--------|-------------|
| `699c601` | `feat(quick-260501-knl): replace 5-stop ladder menu with single forge-themed scale picker dialog` |

**Files created (2):**

| File | Lines | What |
|------|-------|------|
| `flame/scale_picker_dialog.py` | +150 | New module. `pick_scale(parent=None, default=100.0) -> Optional[float]` constructs a forge-themed `QDialog` with title "Export Camera to Blender — Scale", 5 buttons in HBoxLayout (`0.01x` / `0.1x` / `1x` / `10x` / `100x`) each with a small subtitle (`enormous` / `very large` / `architectural` / `large building` / `indoor room`). Default button highlighted via `setDefault(True)` + `objectName="primary"`. Lazy PySide6 import inside the function body (mirrors `_pick_camera` precedent). Reuses `_FORGE_SS` stylesheet from `camera_match_hook.py` lines 271-308. |
| `tests/test_scale_picker_dialog.py` | +209 | New test module. 10 collected items using real `QApplication` under `QT_QPA_PLATFORM=offscreen` (the existing `test_hook_export_camera_to_blender.py`'s MagicMock-stubbed PySide6 pattern is incompatible with real Qt). QTimer trampoline pattern drives dialog interactions without pytest-qt. |

**Files modified (3):**

| File | Lines | What |
|------|-------|------|
| `flame/camera_match_hook.py` | +110 / −110 (net 0) | Added 2 wrappers: `_export_camera_to_blender_with_picker(selection)` opens dialog, dispatches to `_export_camera_to_blender(selection, flame_to_blender_scale=scale)` on pick, returns silently on cancel. Same shape for camera-scope. Reverted both menu surfaces (`get_batch_custom_ui_actions` + `get_action_custom_ui_actions`) back to 1 default entry per surface, callback now points to the picker wrapper. |
| `install.sh` | +21 / 0 | Source-presence check + cp step for `flame/scale_picker_dialog.py` to `/opt/Autodesk/shared/python/camera_match/`. |
| `tests/test_hook_export_camera_to_blender.py` | +217 / −34 | Tests D rewritten + 2 cancel companions (default-entry now invokes picker wrapper, ESC cancels skip export). E/F rewritten for revert shape (1 entry per surface, was 6). J/K appended (factory + wrappers still callable). `_LADDER_LABELS_AFTER_DEFAULT` deleted — no longer relevant. |

## Resulting menu structure (post-revert)

**Action node right-click → Camera Match → Camera:**
- Open Camera Calibrator (clip-scoped, unchanged)
- **Export Camera to Blender** ← single entry, opens dialog

**Camera node inside Action's schematic → root right-click:**
- **Export Camera to Blender** ← single entry, opens dialog

## Dialog shape

```
┌─ Export Camera to Blender — Scale ──────────────────────┐
│                                                          │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ │
│  │ 0.01x  │ │  0.1x  │ │   1x   │ │  10x   │ │ 100x ★ │ │
│  │enormous│ │very    │ │archit- │ │large   │ │indoor  │ │
│  │        │ │large   │ │ectural │ │building│ │room    │ │
│  └────────┘ └────────┘ └────────┘ └────────┘ └────────┘ │
│                                                          │
│                                       [Cancel]           │
└──────────────────────────────────────────────────────────┘
```

★ = `setDefault(True)` + `objectName="primary"` highlight (matches today's hardcoded 100.0)
ESC / X / Cancel button → returns `None` → menu wrapper skips the export call cleanly

## What stayed (from prior work)

- `forge_flame.fbx_ascii.fbx_to_v5_json` accepts `flame_to_blender_scale` kwarg (commit 9265f86)
- `_export_camera_pipeline`, `_export_camera_to_blender`, `_export_camera_from_action_selection` accept the `flame_to_blender_scale: float = 100.0` kw-only parameter (commit 6200771)
- `_make_export_callback(scale, *, camera_scope=False)` factory (commit 6200771) — still callable, just not registered in menus directly anymore
- `_LADDER_MENU_STOPS` constant (commit 6200771) — used by the dialog's button factory
- Viewport-nav `scale=1000.0` at the `blender_bridge.run_bake(...)` call site — byte-identical (canary test G unchanged, asserts `source.count("scale=1000.0") == 2`)

## Tests

| Class / function | Cases | Pre-existing or new |
|------------------|-------|---------------------|
| `TestLadderMenuFactory::test_factory_dispatches_each_stop` | 5 (parametrized) | i31 — STAYS |
| `TestLadderMenuFactory::test_factory_camera_scope_dispatches_correct_helper` | 2 | i31 — STAYS |
| Default-entry regression (D + 2 cancel companions) | 4 | i31 D rewritten + 2 NEW |
| Menu shape (E + F) | 2 | i31 rewritten for revert shape |
| Viewport-nav canary (G) | 1 | i31 — STAYS |
| Closure-binding (H + I, parametrized) | 10 | i31 — STAYS |
| `test_factory_still_present` (J), `test_wrappers_exist_and_are_callable` (K) | 2 | NEW for knl |
| `test_scale_picker_dialog.py` (new module) | 10 | NEW for knl |

**Run:** `pytest -p no:pytest-blender tests/`
**Result:** 522 passed / 0 failed / 2 skipped (was 508/0/2 after i31 → +14 net new)

## Manual UAT (required before artist use)

Per `memory/flame_module_reload.md`, Flame caches `get_batch_custom_ui_actions()` and `get_action_custom_ui_actions()` at hook-registration time. Live reload via gc/exec does NOT refresh menu dispatch.

```bash
bash install.sh   # syncs scale_picker_dialog.py + camera_match_hook.py
# Quit and re-launch Flame 2026.2.1 (full restart)
```

Then verify:

1. Right-click an **Action node** → Camera Match → Camera. **Expected:** 2 entries — "Open Camera Calibrator" + "Export Camera to Blender" (no `@ Nx` siblings).
2. Click "Export Camera to Blender" → forge-themed dialog opens with 5 buttons in a row, `100x` highlighted as default (keyboard focus on `100x`).
3. **Pick `0.01x`** → dialog closes, .blend opens with camera ~83km from origin (enormous scene).
4. **Pick `100x`** → dialog closes, .blend opens with camera ~76m from origin (matches yesterday's hardcode default — the studio sweet spot).
5. Click "Export Camera to Blender" again → dialog reopens → press **ESC** → dialog closes silently, no export, no error.
6. Right-click a **Camera node inside an Action's schematic** → 1 entry "Export Camera to Blender" → same dialog → same behavior.

## Out of scope (deliberate)

- Persistent preference (last-used scale memory across sessions)
- Keyboard shortcuts inside the dialog (number keys 1-5 → buttons)
- "Remember choice" checkbox
- Calibrated reference-distance UI (separate phase — the photogrammetric "right answer")
- Geometry scaling
- Matchbox-side anything (shelved 2026-05-01)

## Self-check

- [x] Verdict written: SHIPPED
- [x] Single Action-scoped menu entry per surface (was 6 after i31)
- [x] Default selection on 100x button (matches today's hardcoded studio default)
- [x] ESC / cancel returns None → no export call (4 cancel-test guards)
- [x] Forge style applied via `_FORGE_SS` reuse (no color redef — single source of truth per `memory/forge_ui_style.md`)
- [x] Lazy PySide6 import mirrors `_pick_camera` precedent at camera_match_hook.py:2352-2424
- [x] Viewport-nav `scale=1000.0` byte-identical (canary test G)
- [x] One atomic commit; full test suite green
- [x] No new dependencies (PySide6 already used by the calibrator)
- [x] install.sh updated with source-presence check + cp step for the new dialog module

## Next planning step

Two natural follow-ups:

1. **Documentation for artists** — what each ladder stop means in physical terms. User-facing doc, no code. Could include a screenshot of the dialog.
2. **Calibrated reference-distance UI** — the photogrammetric "right answer" for scale derivation. Artist drags a known-length reference line on a known feature in the plate, enters the real distance in mm/cm/m, derives scale from the projection math. Supersedes manual ladder picking with a measured value; ladder remains as fallback when no measurement is provided. Phase-sized (~1 day), not a quick.

The matchbox direction stays shelved per `memory/matchbox_direction_shelved.md` — PySide path forward is now firmly the artist surface.
