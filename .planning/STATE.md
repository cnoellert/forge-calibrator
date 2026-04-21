---
gsd_state_version: 1.0
milestone: v6.3
milestone_name: milestone
status: executing
stopped_at: Phase 2 Wave 1 complete — probes done
last_updated: "2026-04-21T22:55:00.000Z"
last_activity: 2026-04-21 -- Phase 02 Wave 1 complete
progress:
  total_phases: 5
  completed_phases: 1
  total_plans: 8
  completed_plans: 4
  percent: 50
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-19)

**Core value:** The solved camera must be geometrically faithful to the plate, and the Flame↔Blender round-trip must preserve that fidelity end-to-end.
**Current focus:** Phase 02 — blender-addon

## Current Position

Phase: 02 (blender-addon) — EXECUTING
Plan: 1 of 4 complete (Wave 1 done — D-19 locked, FOLDED-01 closed)
Status: Executing Phase 02
Last activity: 2026-04-21 -- Phase 02 Wave 1 complete

Progress: [██░░░░░░░░] 25%

## Performance Metrics

**Velocity:**

- Total plans completed: 4
- Average duration: —
- Total execution time: —

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01 | 4 | - | - |

**Recent Trend:**

- Last 5 plans: —
- Trend: —

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- forge-bridge runs as Flame-spawned subprocess (Option B) — no launchd/systemd complexity; lifecycle tied to Flame session
- Blender auto-launch defaults to no-focus-steal; configurable in `.planning/config.json`
- Intermediate `.fbx` / `.json` files go to `tempfile.mkdtemp()` and are removed on success; only `.blend` stays visible
- D-19 triggered: `flame.batch.frame_rate` is a plain `NoneType` slot (not a `PyAttribute`), returned `None` under all tested conditions including with a Batch + clip + Action loaded. Recovery ladder adopted: (1) read `cam["forge_bake_frame_rate"]` custom prop on the Blender camera, (2) fall back to `bpy.context.scene.render.fps / fps_base`, (3) popup asking the user. Plan 02-02's `v5_json_str_to_fbx` takes `frame_rate` as a caller-provided kwarg; Plan 02-03's addon owns the ladder. See `memory/flame_batch_frame_rate.md`.
- FOLDED-01 closed: multi-camera picker 4-check sweep PASSED all checks. Perspective correctly filtered, dropdown order deterministic, Cancel path clean, picker→stamp integrity verified via JSON `forge_bake_camera_name`. See `.planning/todos/completed/2026-04-21-verify-multi-camera-picker-in-live-uat.md`.

### Pending Todos

- Phase 1 supplement: stamp `forge_bake_frame_rate` in `tools/blender/bake_camera.py` (D-19 recovery — sourced from `bpy.context.scene.render.fps / fps_base` at bake time). Low priority: Plan 02-03's addon ladder has fallback #2 covering this case, so this is additive robustness not a blocker.

### Blockers/Concerns

- `flame/camera_match_hook.py` is a 2100-LOC monolith; menu handler changes require a full Flame restart to take effect (not a blocker for shipping but slows iteration)
- forge-bridge is a separate repo; this milestone integrates it as a production dependency without owning its internals — coordinate on the auto-start interface contract before Phase 3 execution
- Phase 1 must resolve how `resolution` is read from the Action node (PyAttribute shape for Action.resolution not confirmed in existing tests — probe needed)

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260420-uzv | Preserve Flame batch start frame in FBX bake (frame_offset) | 2026-04-21 | 9c7f109 | [260420-uzv-preserve-flame-batch-start-frame-in-fbx-](./quick/260420-uzv-preserve-flame-batch-start-frame-in-fbx-/) |
| 260421-bhg | Clip FBX bake trailing frame to Flame batch end_frame | 2026-04-21 | cf0e002 | [260421-bhg-clip-fbx-bake-trailing-frame-to-flame-ba](./quick/260421-bhg-clip-fbx-bake-trailing-frame-to-flame-ba/) |
| 260421-c1w | Fix FBX bake pre-roll frame shift (frame_start clip + offset-1) | 2026-04-21 | 61b3e8c | [260421-c1w-fix-fbx-bake-pre-roll-frame-shift-frame-](./quick/260421-c1w-fix-fbx-bake-pre-roll-frame-shift-frame-/) |

## Deferred Items

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| v2 scope | MULT-01: Round-trip multiple cameras in one operation | Deferred | v6.3 requirements |
| v2 scope | POLISH-01: "Last .blend per Action" memory | Deferred | v6.3 requirements |
| v2 scope | POLISH-02: Stamp bridge + hook versions in custom properties | Deferred | v6.3 requirements |

## Session Continuity

Last session: 2026-04-21T22:55:00.000Z
Stopped at: Phase 2 Wave 1 complete — probes done
Resume file: .planning/phases/02-blender-addon/02-01-SUMMARY.md
