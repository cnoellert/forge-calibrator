# forge-calibrator

## What This Is

A vanishing-point camera calibration tool that lives inside Autodesk Flame. A VFX
artist draws 2-3 reference lines along orthogonal scene edges in a plate; the tool
solves a camera (position, rotation, FOV, focal length) and applies it to a Flame
Action node.

Calibrator is **single-purpose — VP solve** (see [README.md](../README.md)). Flame↔Blender
camera round-trip, FBX pipeline, and related surfaces that lived in this repo through
v6.2 were **removed** in quick-260505-tb3 (Phase A2); export/import work continues in
**forge-blender** (Phase 6 cherry-pick from this repo’s history). See
`forge_flame/__init__.py` and `.planning/notes/blender-strip-pending.md`.

## Core Value

**The solved camera must be geometrically faithful to the plate.** Everything else —
UX polish, seamless workflows, automation — is secondary. If the numbers are wrong,
the compositing CG won't glue to the plate and the tool fails its purpose.

## Requirements

### Validated

- ✓ User can draw 2 or 3 vanishing-point lines on a plate and produce a Flame camera solve
- ✓ Per-line residual labels (`Δ<N>px`) in 3-line mode
- ✓ Apply solved camera to a user-picked Action camera, with optional axis drops at VP line endpoints
- ✓ Wiretap-based single-frame media reader (Sony / ARRI MXF, colour-space tagging)
- ✓ ACES 2.0 OCIO `DisplayViewTransform` preview (RRT + ODT + sRGB display)
- ✓ `install.sh` — preflight for forge conda env, Wiretap CLI, Flame-bundled PyOpenColorIO, OCIO config; copies `camera_match`, `forge_core`, `forge_flame`; purges stale Matchbox / Blender-era artifacts under the install tree
- ✓ `forge_core` / `forge_flame` split — numpy-only core; Flame adapters (`adapter.py`, `wiretap.py`) only
- ✓ pytest suite (191 tests): solver, rotations, hook parity, image buffer, hook helpers

### Previously in-tree (removed 2026-05; forge-blender / history)

The following shipped in this repo before Phase A2 and remains documented in
[PASSOFF.md](../PASSOFF.md) and archived `.planning/phases/` for traceability:

- Flame ↔ Blender static/animated camera round-trip (JSON + ASCII FBX, `fbx_ascii`, `blender_bridge`, Batch menu export/import)
- Larger pytest surface (FBX I/O, Blender CLI tests) — superseded by the stripped 191-test set above

### Active

<!-- Calibrator maintenance + host compatibility; round-trip lives in forge-blender. -->

- [ ] Keep VP solve + Apply path correct against new Flame releases (API / OCIO / Wiretap paths)
- [ ] Keep `install.sh` + preflight aligned with Autodesk path conventions on macOS/Linux
- [ ] Round-trip / Send-to-Flame / forge-bridge autostart — **out of scope for this repo**; track in forge-blender + forge-bridge

### Out of Scope

- **This repo as the home for Blender round-trip or ASCII FBX camera I/O** — migrated intent to forge-blender
- **Bundling forge-bridge in `install.sh`** — Tier-3 dev RPC; install from the forge-bridge repo if needed (`127.0.0.1` only)
- **Lights / meshes / materials** beyond camera solve context
- **Real-time bidirectional sync** between Flame and external DCCs
- **Windows** — Flame does not run there

## Context

- **PASSOFF.md** at repo root holds v4→v6.2 session history (including pre-strip round-trip).
- **`.planning/codebase/`** — STACK, ARCHITECTURE, STRUCTURE, etc. Prefer these + README for *current* behaviour.
- **`.planning/phases/`** — historical phase plans; grep anchors and install steps may describe **pre-strip** `install.sh` (e.g. `> forge-bridge`). Authoritative installer behaviour is the **current** [install.sh](../install.sh) and README.
- **Known fragility:** `flame/camera_match_hook.py` is large; batch menu callbacks are captured at registration — full Flame restart for menu handler changes.
- **forge-bridge** — separate repo; optional dev-time HTTP `/exec` into Flame. Not a calibrator runtime dependency; the hook does not import it (see CLAUDE.md / `memory/forge_family_tier_model.md`).

## Constraints

- **Tech stack:** Python 3.11 (Flame-bundled) for production hook code.
- **Runtime dependencies:** numpy + opencv-python in conda `forge` (dev-side); PyOpenColorIO from Flame’s bundled Python (do not install in forge); Wiretap SDK from Flame.
- **Dev-only:** forge-bridge — Tier-3 probe (like pytest); **not** installed by this repo’s `install.sh`.
- **Platform:** macOS + Linux. **Compatibility:** Flame 2026.2.1 primary target.
- **Security:** Internal post tool; forge-bridge (when used) binds to `127.0.0.1` only.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Strip Blender / FBX / bridge from calibrator (quick-260505-tb3) | Core value = VP solve fidelity; round-trip surface moved to forge-blender | ✓ Current — `forge_flame` is adapter + wiretap only |
| `install.sh` does not deploy forge-bridge | Bridge is dev tooling, not calibrator runtime; avoids curl\|bash sibling install in production path | ✓ Current |
| Menu handler changes require full Flame restart | Flame caches `get_batch_custom_ui_actions()` at registration | ⚠️ Dev iteration cost; unchanged |
| Host-agnostic math in `forge_core` | numpy-only solver reusable outside Flame | ✓ Ongoing |

Historical decisions (ASCII FBX writer, v5 JSON, animated FBX route, forge-bridge subprocess design) remain in PASSOFF.md and archived phase docs for the pre-strip era.

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):

1. Requirements invalidated? → Move to Out of Scope or **Previously in-tree** with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

---

*Last updated: 2026-05-12 — PROJECT realigned post install.sh bridge removal and Phase A2 strip; pytest count 191.*
