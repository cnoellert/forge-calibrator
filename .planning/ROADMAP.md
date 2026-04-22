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
- [ ] 03-02-PLAN.md — install.sh `> forge-bridge` section before `> Install`: invoke sibling installer, D-15 post-install sanity check, D-10 warn-and-continue on failure per D-09/D-11, Done-section bridge-aware next-steps

### Phase 4: E2E Validation + Docs
**Goal**: The complete right-click→edit→send loop is validated on the production stack, and users have documentation covering what changed, how to install, and how to troubleshoot
**Depends on**: Phase 2, Phase 3
**Requirements**: DOC-01, DOC-02
**Success Criteria** (what must be TRUE):
  1. A smoke test starting from a fresh Flame session passes the full cycle: right-click Action → Blender opens on camera → edit camera → click "Send to Flame" → new camera with keyframes appears in the target Action — without visiting Flame's batch menu for the return trip
  2. A user reading the documentation (README section or `docs/seamless-bridge.md`) can install the Blender addon, understand how the forge-bridge autostart works, and follow at least three troubleshooting recipes (bridge not running, addon missing metadata, import failure)
**Plans**: TBD

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

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Export Polish | 0/? | Not started | - |
| 2. Blender Addon | 0/? | Not started | - |
| 3. forge-bridge Deploy | 0/2 | Not started | - |
| 4. E2E Validation + Docs | 0/? | Not started | - |
