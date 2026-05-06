# Pending: Phase A2 — strip all Blender round-trip code from calibrator

**Status:** Decided 2026-05-05, blocked on forge-blender Phase 6
**Trigger to start:** forge-blender Phase 6 (Single-camera Send, bridge-free) ships and verifies in real Flame
**Estimated effort:** /gsd-quick scope when triggered (mechanical deletion + install.sh + docs)

## Decision summary

The Flame↔Blender camera round-trip is leaving calibrator entirely. forge-blender absorbs the **export direction only** as its Phase 6 (sibling to whole-scene Send). The **import direction is retired** — no automatic Blender→Flame return. Artists who want a refined camera back use Blender's `File → Export → FBX` → Flame's native FBX import. Manual but works.

**Architectural commitment:** bridge-free. forge-bridge is reclassified as Tier-3 dev probe only (already done in calibrator via quick-260505-mrv).

The full decision chain lives at `forge-blender/.planning/notes/camera-push-architecture-decision.md`. The handoff/migration spec lives at `forge-blender/.planning/research/camera-roundtrip-migration-handoff.md`.

## What gets deleted from calibrator (when triggered)

**Source files (full delete, no migration):**
- `flame/camera_match_hook.py` lines ~2608-3081 — both `_export_camera_to_blender*` and `_import_camera_from_blender` handlers and their menu registration
- `forge_flame/blender_bridge.py`
- `forge_flame/fbx_io.py`
- `forge_flame/fbx_ascii.py`
- `forge_flame/camera_io.py` (audit usage at strip time — likely Blender-flow only)
- `tools/blender/` entire directory

**Tests:**
- `test_fbx_ascii.py`, `test_fbx_io.py`, `test_blender_bridge.py`, `test_blender_roundtrip.py`
- `test_bake_camera.py`, `test_extract_camera.py`
- `test_hook_export_camera_to_blender.py`
- `tests/fixtures/forge_fbx_*.fbx`
- Audit forge_sender tests for Blender-flow coverage

**Docs / install:**
- `install.sh` — stop copying `tools/blender/`, audit forge_flame copies
- `CLAUDE.md` — rewrite the "Recent work (v6.x) extends this with a Flame↔Blender camera round-trip" line; calibrator's identity becomes pristine VP solve, full stop
- `.planning/codebase/STACK.md` and `STRUCTURE.md` — refresh to reflect smaller surface

**Net effect:** `forge_flame/` shrinks from 6 → 2 files (`adapter.py`, `wiretap.py`). `tools/` directory disappears. Calibrator becomes a single-purpose VP-solve tool.

## Sequencing — do NOT strip before forge-blender Phase 6 ships

1. forge-blender Phase 6 lands and verifies in real Flame (single-camera Send working from Action and Batch right-click contexts)
2. Both menus coexist briefly — calibrator's old "Export Camera to Blender" + forge-blender's new "Send Camera to Blender" — confirm no collision
3. Then run Phase A2 strip on calibrator

## How to apply (for any session that touches calibrator before A2 lands)

- Do NOT extend, refactor, or fix bugs in any of the deletion-targets above unless it's a critical production bug. They're dead code walking. Spend that effort on forge-blender Phase 6 instead.
- Do NOT add new features to the Blender round-trip flow on the calibrator side.
- If forge-bridge starts looking like a runtime dep again somewhere, push back — the architectural commitment is bridge-free.
- The strip itself is mechanical once forge-blender Phase 6 verifies; treat it as a `/gsd-quick` task at that time.

Cross-reference: calibrator's auto-memory entry `phase_a2_blender_strip_pending.md` mirrors this note for memory-loaded sessions.
