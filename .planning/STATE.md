# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-19)

**Core value:** The solved camera must be geometrically faithful to the plate, and the Flame↔Blender round-trip must preserve that fidelity end-to-end.
**Current focus:** Phase 1 — Export Polish

## Current Position

Phase: 1 of 4 (Export Polish)
Plan: 0 of ? in current phase
Status: Ready to plan
Last activity: 2026-04-19 — Roadmap created; milestone v6.3 ("Seamless Blender↔Flame Bridge") initialised at brownfield v6.2 baseline

Progress: [░░░░░░░░░░] 0%

## Performance Metrics

**Velocity:**
- Total plans completed: 0
- Average duration: —
- Total execution time: —

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| - | - | - | - |

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

### Pending Todos

None yet.

### Blockers/Concerns

- `flame/camera_match_hook.py` is a 2100-LOC monolith; menu handler changes require a full Flame restart to take effect (not a blocker for shipping but slows iteration)
- forge-bridge is a separate repo; this milestone integrates it as a production dependency without owning its internals — coordinate on the auto-start interface contract before Phase 3 execution
- Phase 1 must resolve how `resolution` is read from the Action node (PyAttribute shape for Action.resolution not confirmed in existing tests — probe needed)

## Deferred Items

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| v2 scope | MULT-01: Round-trip multiple cameras in one operation | Deferred | v6.3 requirements |
| v2 scope | POLISH-01: "Last .blend per Action" memory | Deferred | v6.3 requirements |
| v2 scope | POLISH-02: Stamp bridge + hook versions in custom properties | Deferred | v6.3 requirements |

## Session Continuity

Last session: 2026-04-19
Stopped at: Roadmap creation complete; no plans written yet
Resume file: None
