# Codebase Concerns

**Analysis Date:** 2026-05-12

## Tech debt

### 1. Flame module reload vs batch menu cache

- **Issue:** `gc`/`exec` reload refreshes module globals but **not** Flame’s batch menu dispatch table; menu handler edits need a full Flame restart.
- **Files:** `flame/camera_match_hook.py`, `memory/flame_module_reload.md`, `install.sh` (stub `__init__.py`)
- **Impact:** Slow dev iteration when changing menu wiring.
- **Mitigation:** Document restart requirement; optional future note in DEVELOPMENT.md for external REPL-style tooling (not bundled with calibrator).

### 2. Large hook module

- **Issue:** `camera_match_hook.py` concentrates UI, Wiretap, OCIO, and batch glue — hard to test in isolation.
- **Mitigation:** Prefer small pure functions in `forge_core` / `forge_flame`; expand hook tests (`tests/test_camera_match_hook.py`) when touching behaviour.

## Known bugs / platform gotchas

### 1. Wiretap GBR channel order

- Raw buffers from some formats present as GBR; `wiretap.py` reorders to RGB. See `memory/wiretap_frame_read.md`.

### 2. Flame `current_frame.set_value()` with auto_key

- Documented crash pattern — see `memory/flame_keyframe_api.md`. Not used on the VP solve path.

## Security

### 1. forge-bridge (optional dev tooling)

- **By design,** this repo’s **`install.sh` does not deploy forge-bridge.** The calibrator hook does not import it at runtime (Tier-3 dev probe, analogous to pytest — see CLAUDE.md / `memory/forge_family_tier_model.md`).
- **When installed separately** from the forge-bridge repo, the HTTP server is intended to bind **`127.0.0.1` only.** Do not expose loopback bridges on shared networks without additional controls.

### 2. Batch menu has no RBAC

- Internal post tool assumption; Flame provides session-level auth.

## Performance

### 1. Wiretap single-frame latency

- ~1.5s class reads for large float MXF at 4K — documented non-goal for VP milestone; frame spinner re-reads on change.

### 2. OCIO preview CPU cost

- Scales with resolution; acceptable for HD class plates on modern CPUs.

## Fragile areas

### 1. OCIO config glob

- **Files:** `flame/camera_match_hook.py`, `install.sh` — glob under `flame_configs/*/aces2.0_config/`. Flame upgrades may move paths → preview passthrough if unresolved.

## Test coverage gaps

### 1. Live Flame integration

- Full VP UI flow and Wiretap against production MXF remain manual; unit tests mock Flame shapes.

### 2. Wiretap binary I/O

- CI does not run `wiretap_rw_frame` against real clips; rely on manual smoke on Flame machines.

## Dependencies at risk

- **numpy / opencv-python** — forge env versions not strictly pinned in `install.sh`; major upgrades could break solver or drawing APIs.
- **PyOpenColorIO** — tied to Flame release; upgrade Flame → re-verify OCIO calls.

## Missing / out of scope (intentional)

- **forge-bridge in calibrator install** — not a deliverable here; cross-repo.
- **Blender / ASCII FBX round-trip in this tree** — removed to forge-blender; historical risks (FBX parser, template drift, Blender argv) apply to that lineage, not current `main`.

## Historical note

Pre-strip concerns (custom ASCII FBX parser, `fbx_io`, `blender_bridge`, Perspective export filters, 264-test FBX surface) applied to v6.x code removed in **quick-260505-tb3**. See PASSOFF.md and archived `.planning/phases/` for detail.

---

*Concerns audit refreshed 2026-05-12.*
