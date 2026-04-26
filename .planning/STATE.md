---
gsd_state_version: 1.0
milestone: v6.3
milestone_name: milestone
status: verifying
stopped_at: Completed 04.3-01-PLAN.md — aim-rig Euler convention fix shipped, Camera1 within 0.006° of Flame ground truth
last_updated: "2026-04-25T17:29:56.850Z"
last_activity: 2026-04-25
progress:
  total_phases: 9
  completed_phases: 7
  total_plans: 19
  completed_plans: 19
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-19)

**Core value:** The solved camera must be geometrically faithful to the plate, and the Flame↔Blender round-trip must preserve that fidelity end-to-end.
**Current focus:** Phase 04.3 — aim-rig-euler-convention-fix-adopt-xyz-sign-flip-end-to-end

## Current Position

Phase: 999.1
Plan: Not started
Status: Phase complete — ready for verification
Last activity: 2026-04-25

Progress: [██████░░░░] 60% (3 of 5 phases complete)

## Performance Metrics

**Velocity:**

- Total plans completed: 13
- Average duration: —
- Total execution time: —

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01 | 4 | - | - |
| 02 | 4 | - | - |
| 03 | 2 | - | - |
| 04 | 2 | - | - |
| 04.3 | 1 | - | - |

**Recent Trend:**

- Last 5 plans: —
- Trend: —

*Updated after each plan completion*
| Phase 04.3 P01 | 14min | 5 tasks | 10 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- forge-bridge runs as Flame-spawned subprocess (Option B) — no launchd/systemd complexity; lifecycle tied to Flame session
- Blender auto-launch defaults to no-focus-steal; configurable in `.planning/config.json`
- Intermediate `.fbx` / `.json` files go to `tempfile.mkdtemp()` and are removed on success; only `.blend` stays visible
- D-19 triggered: `flame.batch.frame_rate` is a plain `NoneType` slot (not a `PyAttribute`), returned `None` under all tested conditions including with a Batch + clip + Action loaded. Recovery ladder adopted: (1) read `cam["forge_bake_frame_rate"]` custom prop on the Blender camera, (2) fall back to `bpy.context.scene.render.fps / fps_base`, (3) popup asking the user. Plan 02-02's `v5_json_str_to_fbx` takes `frame_rate` as a caller-provided kwarg; Plan 02-03's addon owns the ladder. See `memory/flame_batch_frame_rate.md`.
- FOLDED-01 closed: multi-camera picker 4-check sweep PASSED all checks. Perspective correctly filtered, dropdown order deterministic, Cancel path clean, picker→stamp integrity verified via JSON `forge_bake_camera_name`. See `.planning/todos/completed/2026-04-21-verify-multi-camera-picker-in-live-uat.md`.
- Phase 2 shipped (2026-04-21): Forge Sender v1.0.0 addon, all IMP-01..IMP-06 verified live. Two hotfix commits landed during UAT (permissive operator poll(); bridge _result surfacing via trailing expression + ast.literal_eval). Four Phase 4 polish follow-ups captured in 02-04-SUMMARY: plural popup filter, Flame FBX stereo-rig expansion investigation, Blender reload discipline, single uncaptured Flame crash. Code review: 0 blockers, 2 warnings (fidelity-discipline on D-19 ladder fall-through), 3 info.
- [Phase 04.3]: Adopted R = Rz(-rz)·Ry(-ry)·Rx(-rx) (Z·Y·X product, all 3 signs negated) for aim-rig pipeline; coupled with rotation_matrix_from_look_at L167 +roll_deg sign flip. Camera1 fixture lands within 0.006° of Flame viewport ground truth.
- [Phase 04.3]: Pipeline-symmetric atomic landing: 7-file commit covers reader + bake + flame_math + look-at L167 + 3 lockstep tests. Mitigates Phase 04.2 importToActionFBX hard-crash class of failures.
- [Phase 04.3]: Plan amendment §A's symbolic derivation was empirically wrong (claimed X·Y·Z product; correct form is Z·Y·X — extrinsic xyz means Rz·Ry·Rx in matrix product, not Rx·Ry·Rz). Auto-applied Rule 1 fix in Task 3. Original plan's <symbolic_derivation> block was actually correct.

### Pending Todos

All "Phase 4 polish" items previously listed here have been bucketed into **Phase 4.1** (inserted 2026-04-22 after Phase 4 discuss-phase). See `.planning/ROADMAP.md` §"Phase 4.1: Phase 4 polish items (INSERTED)" for the canonical list. Phase 4 itself stays scoped to DOC-01 (E2E smoke test) + DOC-02 (user docs) only.

### Roadmap Evolution

- Phase 4.1 inserted after Phase 4 on 2026-04-22: Phase 4 polish items bucket (stereo-rig filter, empty-camera UX, crash repro, code-review warnings, fps stamping). Rationale: Phase 4's discuss-phase locked scope to docs+validation only; pre-existing polish items tagged "Phase 4" in Phase 1-2 summaries needed a home that doesn't bloat Phase 4. Priority set after Phase 4 smoke test surfaces which polish items actually block v6.3 ship.
- Phase 4.3 inserted after Phase 4 on 2026-04-24: Aim-rig Euler convention fix — adopt XYZ-sign-flip end-to-end (URGENT). Rationale: diagnostic trace (`/tmp/forge_pipeline_trace.py`) proved Phase 4.2's aim-rig math emits an Euler convention (ZYX-with-X,Y-negated) that is NOT equivalent to Flame's UI-rotation convention (XYZ-with-X,Y-sign-flip = Rxyz(-rx,-ry,rz) per FBX Lcl + Ry(+90°) PostRotation formula). Current pipeline shows 0.069 forward-vector mismatch on Default camera, growing to 0.38 for mixed rotations; this is the "visible CG registration slip" the user reported. Scoped fix would break the compose/decompose self-inverse pair, so full fix required: coordinated change across `forge_core/math/rotations.py`, `tools/blender/bake_camera.py`, `tools/blender/forge_sender/flame_math.py`, `tools/blender/extract_camera.py` plus test updates. Anchor A non-circular test added: given R_lcl for UI (27.324, -24.298, 0.736), `compute_flame_euler_zyx(R_lcl)` must return that triple to float precision.
- Phase 04.4 inserted after Phase 4 on 2026-04-25: Tester-rollout polish — forge UI style on multi-camera picker, right-click on camera nodes inside Action, bidirectional Blender import (live session + .blend file), menu reorganization to FORGE/Camera/{Camera Calibrator, Export Camera to Blender, Import Camera from Blender} (URGENT — pre-tester rollout). Rationale: Phase 04.3 + v1.2.0 addon shipped and verified; before sending to testers (flame-01 cold-install in progress), tighten the user-visible Batch right-click menu surface. All four items are cohesive UX polish on the hook layer. Folds in backlog item 999.1 (multi-camera picker UX) since the picker restyle naturally addresses it. Bidirectional Blender import is the largest item — adds the option to pull a camera from a live Blender session (not just a saved .blend), closing the loop for cameras born in Blender that were never originally Flame cameras.

### Blockers/Concerns

- `flame/camera_match_hook.py` is a 2100-LOC monolith; menu handler changes require a full Flame restart to take effect (not a blocker for shipping but slows iteration)
- forge-bridge is a separate repo; this milestone integrates it as a production dependency without owning its internals — coordinate on the auto-start interface contract before Phase 3 execution
- Phase 1 must resolve how `resolution` is read from the Action node (PyAttribute shape for Action.resolution not confirmed in existing tests — probe needed)
- Phase 04.3 Task 1 spike returned Branch B with max |delta| > 0.05° on rz axis (2.504°). Plan's symbolic _xyz derivation does not reproduce CONTEXT.md hand-decomposed (1.814°, 1.058°, 1.252°) from look-at output. Executor PAUSED before Task 2 — see 04.3-SPIKE.md for three remediation options.

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

Last session: 2026-04-25T16:33:10.639Z
Stopped at: Completed 04.3-01-PLAN.md — aim-rig Euler convention fix shipped, Camera1 within 0.006° of Flame ground truth
Resume file: None
