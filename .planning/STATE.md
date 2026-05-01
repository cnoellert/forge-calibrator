---
gsd_state_version: 1.0
milestone: v6.3
milestone_name: milestone
status: between_phases
stopped_at: Phase 04.4 complete (HUMAN-UAT pass + 6 GAP-04.4-UAT-* closures); cold-install verification on flame-01 surfaced 4 next-cycle todos to triage
last_updated: "2026-04-28T15:48:22.645Z"
last_activity: 2026-04-28
progress:
  total_phases: 10
  completed_phases: 8
  total_plans: 26
  completed_plans: 26
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-19)

**Core value:** The solved camera must be geometrically faithful to the plate, and the Flame↔Blender round-trip must preserve that fidelity end-to-end.
**Current focus:** Triage 4 cold-install todos surfaced on flame-01 (camera-scope NoneType regression, VP solver X+Z pair, preview channel-order cast, wiretap "No route to host"); 999.x backlog deferred until triage routes work into a numbered phase.

## Current Position

Phase: 04.4 complete; between phases
Plan: —
Status: 04.4 closed (HUMAN-UAT pass, 6 GAP-04.4-UAT-* closed); next: triage cold-install todos
Last activity: 2026-05-01 -- Completed quick task 260501-dpa: Flame↔Blender scale ladder knob shipped — bit-exact round-trip parity, +29 tests; matchbox direction shelved 2026-05-01

Progress: [██████████] 100% (8 of 8 numbered phases complete; 999.x backlog remaining)

## Performance Metrics

**Velocity:**

- Total plans completed: 20
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
| 04.4 | 7 | - | - |

**Recent Trend:**

- Last 5 plans: —
- Trend: —

*Updated after each plan completion*
| Phase 04.3 P01 | 14min | 5 tasks | 10 files |
| Phase 04.4 P01 | 4min | 3 tasks | 3 files |
| Phase 04.4 P02 | 6min | 3 tasks | 2 files |
| Phase 04.4 P03 | 5min | 3 tasks | 1 files |
| Phase 04.4 P04 | 5min | 3 tasks | 4 files |

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
- [Phase 04.4]: Wave 0 (Plan 04.4-01) — 14 test stubs across 3 files; skip-gated with wave-pointer reasons; Pitfall-1 canary in place for _scope_action_camera; R-08 source-text canary auto-flips when rename lands
- [Phase 04.4]: Plan 04.4-02 / Task 1: hoisted _FORGE_SS to module scope so _pick_camera (and any future module-level dialog) can reference it without NameError. Original definition at line ~301 inside _open_camera_match's body migrated to line 251.
- [Phase 04.4]: Plan 04.4-02 / Task 1: replaced QInputDialog.getItem in _pick_camera with FORGE-styled QDialog (UI-SPEC §A-1). QListWidget over QComboBox per RESEARCH Pattern 1; em-dash window title 'FORGE — <title>'; double-click-to-accept wired.
- [Phase 04.4]: Plan 04.4-02 / Task 2: added _scope_action_camera + _first_camera_in_action_selection at module level. Both use direct string equality on item.type (RESEARCH Pitfall 1 — item.type is plain str in action-callback context, not PyAttribute). Wave 0 test infrastructure required _KEEP_INSTALLED set so the helper's lazy  finds the fake at test runtime.
- [Phase 04.4]: Plan 04.4-02 / Task 3: extracted _export_camera_pipeline (PATTERNS Shape A) so the Camera-scope handler can bypass _pick_camera and feed the resolved (action_node, cam_node) triple straight into the bake/launch tail. Label format uses '>' separator to match _find_action_cameras (line 1812), not the em-dash specified in the plan body — Rule 1 deviation tracked.
- [Phase 04.4]: Plan 04.4-03 / Wave 2: flat FORGE group landed (no nested submenus per P-01). get_action_custom_ui_actions registered as a sibling hook for Camera-node right-clicks (root-level via hierarchy: []). _import_camera_from_blender + Import Camera from Blender menu entry deleted (D-06 hard cut). Apply Camera picker also flipped to _pick_camera via Create-new-Action sentinel tuple — every camera picker in the hook is now FORGE-styled. Wave 2 awaits Flame-restart UAT (Task 4 human-verify checkpoint).
- [Phase 04.4]: Plan 04.4-04: extended Blender forge_sender addon to v1.3.0 — added list_batch_actions/make_create_code transport (repr() injection-safe), FORGE_OT_send_to_flame_choose_action operator with live Action dropdown, panel extension for no-metadata state, and R-08 preflight string updates. All 8 Wave-0 stubs flipped SKIP→PASS.

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
| 260428-q8c | Fix Wiretap channel-order decoding to be per-bit-depth (channel_order={RGB,GBR,BRG} keyed off bit_depth) | 2026-04-29 | 6a6df75 | [260428-q8c-fix-wiretap-channel-order-decoding-to-be](./quick/260428-q8c-fix-wiretap-channel-order-decoding-to-be/) |
| 260429-ebd | Add 10-bit + 12-bit decode support to decode_raw_rgb_buffer + bit-depth-unsupported warning | 2026-04-29 | c25e542 | [260429-ebd-add-10-bit-12-bit-decode-support-to-deco](./quick/260429-ebd-add-10-bit-12-bit-decode-support-to-deco/) |
| 260429-fk5 | Glob-expand Blender binary defaults to cover /opt/ sideloads + backlog UI todo | 2026-04-29 | 969198d | [260429-fk5-glob-expand-blender-binary-defaults-to-c](./quick/260429-fk5-glob-expand-blender-binary-defaults-to-c/) |
| 260429-gde | Version-tolerant fcurves walk for Blender slotted-actions API (5.x compat fix in flame_math.py) | 2026-04-29 | f064824 | [260429-gde-version-tolerant-fcurves-walk-for-blende](./quick/260429-gde-version-tolerant-fcurves-walk-for-blende/) |
| 260430-ddi | Matchbox calibrator architecture spike — Path A/B not viable, Snapshot path (PyExporter) recommended | 2026-04-30 | research-only | [260430-ddi-spike-matchbox-calibrator-architecture-t](./quick/260430-ddi-spike-matchbox-calibrator-architecture-t/) |
| 260430-e5y | PyExporter().export() smoke-test — WORKED, 25-LOC recipe ready for Wiretap replacement | 2026-04-30 | research-only | [260430-e5y-smoke-test-pyexporter-export-end-to-end-](./quick/260430-e5y-smoke-test-pyexporter-export-end-to-end-/) |
| 260430-hn7 | Frame-parking validation PARTIAL — no PyClip parking API in Flame 2026.2.1; recipe needs Route A/B/C strategy | 2026-04-30 | research-only | [260430-hn7-frame-parking-validation-for-pyexporter-](./quick/260430-hn7-frame-parking-validation-for-pyexporter-/) |
| 260430-iv3 | Matchbox uniform readback spike KILLED — uniforms not Python-readable at any layer; pivot to pixel-encoded inputs + snapshot decode (SHELVED 2026-05-01) | 2026-04-30 | research-only | [260430-iv3-spike-matchbox-uniform-readback-via-flam](./quick/260430-iv3-spike-matchbox-uniform-readback-via-flam/) |
| 260501-dpa | Flame↔Blender scale ladder knob — `flame_to_blender_scale` on v5 JSON contract, log10 stops {0.01, 0.1, 1, 10, 100}, bit-exact round-trip parity, +29 tests | 2026-05-01 | 76d88fa | [260501-dpa-add-flame-blender-scale-ladder-knob-roun](./quick/260501-dpa-add-flame-blender-scale-ladder-knob-roun/) |

## Deferred Items

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| v2 scope | MULT-01: Round-trip multiple cameras in one operation | Deferred | v6.3 requirements |
| v2 scope | POLISH-01: "Last .blend per Action" memory | Deferred | v6.3 requirements |
| v2 scope | POLISH-02: Stamp bridge + hook versions in custom properties | Deferred | v6.3 requirements |

## Session Continuity

Last session: 2026-04-27T01:36:21.489Z
Stopped at: Completed 04.4-04-PLAN.md (Wave 3 addon extension); Task 4 awaiting human UAT — 11 scenarios after v1.3.0 zip repackage + reinstall
Resume file: None
