# Roadmap: forge-calibrator — Seamless Blender↔Flame Bridge (v6.3)

## Overview

v6.2 delivered a working animated camera round-trip via ASCII FBX, but the UX still requires the user to alt-tab back to Flame's batch menu to trigger the import. v6.3 closes that loop: the export handler is polished (zero dialogs, temp-file cleanup, metadata stamping), a Blender addon handles the return trip entirely from inside Blender, forge-bridge becomes a production auto-starting subprocess, and the full cycle is validated end-to-end.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Export Polish** - Rework the Flame-side export handler for zero-dialog launch, temp-file cleanup, and metadata stamping
- [ ] **Phase 2: Blender Addon** - Build the "Send to Flame" addon that reads stamped metadata and POSTs the return trip to forge-bridge
- [ ] **Phase 3: forge-bridge Deploy** - Wire forge-bridge as a Flame-spawned production subprocess with install.sh support
- [ ] **Phase 4: E2E Validation + Docs** - Validate the full bake→edit→send loop end-to-end and write user-facing documentation

## Phase Details

### Phase 1: Export Polish
**Goal**: Users can right-click an Action and launch Blender on the target camera without any dialogs, with temp files cleaned up automatically and metadata stamped on the camera for the return trip
**Depends on**: Nothing (first phase)
**Requirements**: EXP-01, EXP-02, EXP-03, EXP-04, EXP-05
**Success Criteria** (what must be TRUE):
  1. Right-clicking an Action and selecting "Export Camera to Blender" opens Blender on the target camera without presenting any width/height or save-path dialog
  2. The plate resolution is inferred from the Action node's `resolution` attribute — no manual entry required
  3. After a successful export, only the `.blend` file remains visible; the intermediate `.fbx` and `.json` temp files are gone
  4. The exported Blender camera has `forge_bake_action_name` and `forge_bake_camera_name` custom properties stamped on it with the correct Flame Action and camera names
  5. Blender launches without stealing focus by default; a `blender_launch_focus_steal` key in `.planning/config.json` lets the user opt into focus-steal mode
**Plans**: TBD

### Phase 2: Blender Addon
**Goal**: Users can send an edited camera back to Flame entirely from inside Blender by clicking a single button in the 3D viewport sidebar, with success or failure reported in a Blender popup — no trip to Flame's batch menu required
**Depends on**: Phase 1
**Requirements**: IMP-01, IMP-02, IMP-03, IMP-04, IMP-05, IMP-06
**Success Criteria** (what must be TRUE):
  1. A "Send to Flame" button is visible in the N-panel (3D viewport sidebar) after installing the addon via Blender's standard addon install flow
  2. Clicking "Send to Flame" with a camera that lacks forge metadata shows an error popup naming the missing property rather than crashing or silently failing
  3. Clicking "Send to Flame" on a properly stamped camera extracts per-frame T / R / focal / film-back and delivers the camera to the target Flame Action without the user touching Flame's UI
  4. The result (new camera name on success, or error traceback on failure) appears in a Blender info popup immediately after the button press
**Plans:** 4 plans
Plans:
- [x] 02-01-PLAN.md — Pre-work probes (D-18 frame_rate shape + FOLDED-01 multi-camera picker sweep)
- [x] 02-02-PLAN.md — v5_json_str_to_fbx sibling + shared flame_math.py extraction + extract_camera.py refactor
- [x] 02-03-PLAN.md — Addon scaffolding: preflight.py + transport.py + __init__.py (bl_info, Panel, Operator)
- [x] 02-04-PLAN.md — Build installable zip + live E2E validation (happy path + Tier 1/2/3 failure paths)
**UI hint**: yes

### Phase 3: forge-bridge Deploy
**Goal**: forge-bridge starts automatically when Flame boots and shuts down cleanly when Flame quits, with install.sh wiring the entire lifecycle so a fresh install works without manual bridge setup
**Depends on**: Phase 1
**Requirements**: BRG-01, BRG-02, BRG-03, BRG-04
**Success Criteria** (what must be TRUE):
  1. Relaunching Flame causes forge-bridge to start listening on `127.0.0.1:9999` without any manual user action
  2. Quitting Flame leaves no orphan bridge process and no stale port binding — the next Flame boot starts the bridge cleanly
  3. forge-bridge never binds to any interface other than `127.0.0.1` (confirmed by `netstat` or equivalent)
  4. Running `install.sh` on a clean machine deploys the forge-bridge launcher alongside the hook so that the next Flame start triggers the bridge automatically
**Plans:** 2 plans
Plans:
- [x] 03-01-PLAN.md — install.sh plumbing: forge-bridge constants (v1.3.0 pin), env-var reads (FORGE_BRIDGE_REPO / FORGE_BRIDGE_VERSION), source-resolver + --force helpers, --help docstring sync
- [x] 03-02-PLAN.md — install.sh `> forge-bridge` section before `> Install`: invoke sibling installer, D-15 post-install sanity check, D-10 warn-and-continue on failure per D-09/D-11, Done-section bridge-aware next-steps

### Phase 4: E2E Validation + Docs
**Goal**: The complete right-click→edit→send loop is validated on the production stack, and users have documentation covering what changed, how to install, and how to troubleshoot
**Depends on**: Phase 2, Phase 3
**Requirements**: DOC-01, DOC-02
**Success Criteria** (what must be TRUE):
  1. A smoke test starting from a fresh Flame session passes the full cycle: right-click Action → Blender opens on camera → edit camera → click "Send to Flame" → new camera with keyframes appears in the target Action — without visiting Flame's batch menu for the return trip
  2. A user reading the documentation (README section or `docs/seamless-bridge.md`) can install the Blender addon, understand how the forge-bridge autostart works, and follow at least three troubleshooting recipes (bridge not running, addon missing metadata, import failure)
**Plans:** 2 plans
Plans:
- [x] 04-01-PLAN.md — User-facing docs: README.md (repo root) + docs/seamless-bridge.md (canonical guide, install TD+artist, autostart, Send-to-Flame walkthrough, 5 grep-anchored troubleshooting recipes) — DOC-02
- [x] 04-02-PLAN.md — E2E smoke-test script: tools/smoke-test/seamless-bridge-smoke.sh (hybrid [mech]+[human], 10 steps, folds Phase 3 HUMAN-UAT Test 3) — DOC-01

### Phase 04.4: Tester-rollout polish: forge UI style on multi-camera picker, right-click on camera nodes inside Action, bidirectional Blender import (live session + .blend file), and menu reorganization to FORGE/Camera/{Camera Calibrator, Export Camera to Blender, Import Camera from Blender} (INSERTED)

**Goal:** Pre-tester UX polish on the Flame Batch right-click menu surface plus a coupled Blender-addon scope expansion. Four cohesive items: FORGE-styled multi-camera picker (folds 999.1), camera-node-scope right-click entry point in Action schematics (new `get_action_custom_ui_actions`), removal of Flame-side "Import Camera from Blender" + extension of forge_sender addon to push cameras without bake metadata (new `FORGE_OT_send_to_flame_choose_action` operator), and menu reorganization under a new top-level `FORGE` group (`FORGE > {Open Camera Calibrator, Export Camera to Blender}` flat per RESEARCH §P-01 — two-level nesting unsupported on Flame 2026.2.1). User-visible label rename "Camera Match" → "Camera Calibrator" / "FORGE" (D-13: internal filenames + install paths unchanged). Verified pre-plan via live forge-bridge probes against Flame 2026.2.1 (P-01/P-02/P-03 all resolved, including the D-09 correction that Flame raises `RuntimeError` on Action-name collision rather than auto-suffixing).
**Requirements**: D-01..D-15 from 04.4-CONTEXT.md (no formal REQ-IDs — rollout polish phase)
**Depends on:** Phase 4
**Plans:** 4/5 plans executed

Plans:
- [x] 04.4-01-PLAN.md — Wave 0 test stubs: 14 stub tests across tests/test_forge_sender_transport.py, tests/test_forge_sender_preflight.py, tests/test_camera_match_hook.py (NEW); covers list_batch_actions/make_create_code repr() injection canary, _scope_action_camera Pitfall-1 guard, R-08 string-rename gate
- [x] 04.4-02-PLAN.md — Wave 1 hook refactor (no menu): hoist _FORGE_SS to module level, replace _pick_camera with FORGE-styled QDialog, add _scope_action_camera + _first_camera_in_action_selection + _export_camera_from_action_selection + extracted _export_camera_pipeline (D-01/D-03/D-05/P-02)
- [x] 04.4-03-PLAN.md — Wave 2 menu surface: restructure get_batch_custom_ui_actions to flat FORGE group, add get_action_custom_ui_actions, delete _import_camera_from_blender, R-08 user-visible string updates inside the hook (D-06/D-11/D-12/D-13/D-14/D-15/P-01/P-02/R-08)
- [x] 04.4-04-PLAN.md — Wave 3 Blender addon (parallel): add transport.list_batch_actions + transport.make_create_code (repr-injection-safe), new FORGE_OT_send_to_flame_choose_action operator with invoke()/draw()/execute() (handles pick-existing AND create-new with name-collision detection), panel extension, preflight R-08 update, bl_info v1.2.0 → v1.3.0 (D-07/D-08/D-09 corrected/D-10/P-03/R-06/R-08)
- [ ] 04.4-05-PLAN.md — Wave 3 docs (parallel): R-08 string updates to docs/seamless-bridge.md (FORGE menu paths, Camera Calibrator brand, drop Flame-side Import workflow references)

### Phase 04.3: Aim-rig Euler convention fix: adopt XYZ-sign-flip end-to-end (INSERTED)

**Goal:** Close the Phase 04.2 known limitation — aim-rig camera round-trip lands ~0.087° off on `ry` for the Camera1 fixture because Euler decomposition uses the wrong rotation convention. Adopt the correct convention (`R = Rz(-rz)·Ry(-ry)·Rx(-rx)` — XYZ matrix order with all three Euler signs negated) in every place the aim-rig Euler math touches, in sync, in one wave of commits that leaves the tree consistent on every intermediate revision. Verified 2026-04-24 via forge-bridge probe + viewport manual-match.
**Requirements**: None (no formal requirement IDs — this phase closes a known limitation from Phase 04.2; de-facto requirements are CONTEXT.md decisions D-CONV / D-ADD / D-KEEP / D-READER / D-BAKE / D-EXTR / D-DOCXR / D-SYNC / D-TEST, all captured in 04.3-01-PLAN.md frontmatter).
**Depends on:** Phase 4
**Plans:** 1/1 plans complete

Plans:
- [x] 04.3-01-PLAN.md — Pipeline-symmetric XYZ-signflip swap: add `_xyz` rotation pair in `forge_core/math/rotations.py`, swap aim-rig FBX reader + Blender bake + extract + addon-side flame_math, update lockstep tests, full pytest gate (target: Camera1 within 0.01° of Flame viewport truth)

### Phase 4.1: Phase 4 polish items (INSERTED)

**Goal:** Bucket for polish items captured during Phases 1-3 that were tagged "Phase 4 polish" in SUMMARY/REVIEW artifacts but don't belong in Phase 4's docs+validation scope. Run the Phase 4 E2E smoke test first; any items it surfaces as blocking for v6.3 ship get prioritized, others ride to v2.

**Polish items already captured (not exhaustive — Phase 4 smoke test may add more):**
1. Filter `import_fbx_to_action` return list before popup enumeration (drop FBX-internal nodes like `RootNode_Scene5` and stereo-rig siblings) — Phase 2 02-04-SUMMARY follow-up
2. Empty-camera Flame→Blender bake UX (currently fails loud with "no frames in JSON"; emit single-frame static keyframe or surface clearer message) — Phase 2 follow-up
3. Reproduce the Task 5 Flame crash with fresh batch + clean state; capture the error dialog — Phase 2 investigation
4. Address 2 warnings from Phase 2 code review (02-REVIEW.md) — fail-loud on stamped-but-unsupported `forge_bake_frame_rate`, defense-in-depth fps validation in Flame-side template. Auto-fix path: `/gsd-code-review-fix 02`
5. Phase 1 supplement: stamp `forge_bake_frame_rate` in `tools/blender/bake_camera.py` (D-19 recovery — source from `bpy.context.scene.render.fps / fps_base` at bake time). Additive robustness; Plan 02-03 addon fallback #2 already covers this.

**Requirements**: None (no formal requirement IDs — these are polish / defense-in-depth items). Success criterion is "the smoke-test-surfaced blocking subset is addressed before v6.3 ships; the rest is documented as deferred-to-v2."
**Depends on:** Phase 4 (needs Phase 4 smoke test results to prioritize; can run in parallel with Phase 4 docs if useful)
**Plans:** 3 plans

Plans:
- [x] 04.1-01-PLAN.md — Item 1 (GA-3) stereo-rig filter in _FLAME_SIDE_TEMPLATE + D-07 revisit probe
- [x] 04.1-02-PLAN.md — Items 2+5 (GA-2/GA-5): detect-and-route in Export Camera to Blender + forge_bake_frame_rate stamp in bake_camera.py
- [x] 04.1-03-PLAN.md — Item 3 (GA-4) Task 5 crash instrumentation in _FLAME_SIDE_TEMPLATE + N=5 live repro attempt

### Phase 4.2: Aim/Target-rig camera orientation round-trip

**Goal:** Aim/Target-rig cameras must round-trip through Blender with their orientation preserved. Today they lose it — Flame's `action.export_fbx(bake_animation=True)` writes `rotation=(0,0,0)` for every frame on aim-rig cameras, discarding the aim+up+roll that defines the camera's real orientation, and the returned camera ends up as a Free-rig camera with rotation=0 (looking straight down -Z regardless of where the original was pointing).

**Scope (REQUIRED per user 2026-04-23 — not backlog):** Aim-rig cameras are a first-class supported workflow. The v6.3 ship must handle them.

**Context:** Observed live 2026-04-23 during phase 04.1 closing UAT. Camera1 on the user's batch had aim=(0.35, 57.13, 2093.32), up=(0, 30, 0), roll=-1.25°, rotation=(0, 0, 0). Round-trip through Blender returned a camera at the correct position with correct focal/FOV/filmback but pointing the wrong direction (aim=(0, 0, 0) default, looking at origin). Every other core-value invariant from phase 04.1 holds — rotation math, frame preservation, unit scaling, filmback — this is purely about aim/up/roll semantics.

**Approach (locked per 04.2-CONTEXT.md D-01/D-02):** Read the aim-rig semantics out of the FBX Flame already writes, and resolve them to Euler rotation inside the FBX→JSON converter (`forge_flame/fbx_ascii.py`). No Flame-side rig-toggle, no pre-export state mutation, no Blender-side constraint machinery. Approach A (toggle `cam.target_mode=False`) was REJECTED per D-03 — Flame 2026.2.1 PyCoNode has no `target_mode` attribute (confirmed via 39-element live-probe `cam.attributes` scan).

**Acceptance:** Export an Aim/Target-rig camera from Flame → open the .blend in Blender → the Blender camera points at the same world-space target as the Flame original. Send back to Flame → the returned camera's rendered orientation matches the original's to within 0.1° on all three Euler axes.

**Requirements:** None (no mapped REQ-IDs; ROADMAP phase goal + acceptance criterion are the must-haves source per 04.2-CONTEXT.md).

**Plans:** 3 plans

Plans:
- [x] 04.2-01-PLAN.md — Add `rotation_matrix_from_look_at` helper to `forge_core/math/rotations.py` + `tests/test_rotations.py` (Wave 1; D-06, D-07 case-2 gate, D-15 fail-loud)
- [x] 04.2-02-PLAN.md — Fix D-10 latent `target_mode.set_value(False)` bugs in `flame/camera_match_hook.py:1511+1578` and `forge_flame/camera_io.py:234` (Wave 1; independent of 01 and 03)
- [x] 04.2-03-PLAN.md — Aim-rig branch in `forge_flame/fbx_ascii.py` (_extract_cameras + _merge_curves) + `tests/fixtures/forge_fbx_aimrig.fbx` + `TestAimRigFixture` / `TestAimRigFailLoud` in `tests/test_fbx_ascii.py` (Wave 2; depends on 01; D-07 case-1 integration gate)

## Backlog

### Phase 999.1: Improve multi-camera picker UX (BACKLOG)

**Goal:** Replace the bare `QInputDialog.getItem` text dropdown in `_pick_camera` (`flame/camera_match_hook.py:1783-1794`) with a richer picker suited to a professional VFX tool. Current implementation works but is minimal.

**Polish opportunities:**
1. Thumbnail previews of each camera's current-frame render (Wiretap single-frame read into a small QPixmap grid)
2. Mark the currently-active-in-viewport camera with an indicator so the user knows their default
3. Deterministic sort order — alphabetical? creation order? most-recently-solved first?
4. Better disambiguation when two cameras share a name across different Actions
5. Remember last-picked camera per Action

**Scope note:** v2 polish. The current minimal picker is acceptable for initial users and Phase 02's round-trip semantics don't depend on the UX — only on the camera actually selected.

**Requirements:** TBD

**Plans:**
- [ ] TBD (promote with /gsd-review-backlog when ready)

### Phase 999.2: Blender→Flame filmback preservation (RESOLVED in 04.1)

**Resolved 2026-04-23 in phase 04.1 via commit `228387a`.** The hook was hardcoding `film_back_mm=36.0` in both the static-JSON and FBX call sites, throwing away Flame's true filmback at the moment of export. Both sites now pass `film_back_mm=None`, letting the downstream functions derive the real filmback from Flame's own `(fov, focal)` or the FBX `FilmHeight` property. Round-trip verified: focal + FOV + filmback all match the original.

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Export Polish | 0/? | Not started | - |
| 2. Blender Addon | 0/? | Not started | - |
| 3. forge-bridge Deploy | 0/2 | Not started | - |
| 4. E2E Validation + Docs | 0/? | Not started | - |
