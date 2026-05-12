# Architecture

**Analysis Date:** 2026-05-12 (post Phase A2 strip + install bridge removal)

## Pattern Overview

**Overall:** Layered host-abstraction (`forge_core` + `forge_flame`) feeding a single Flame batch hook.

**Key characteristics:**

- Clean separation: numpy-only **forge_core** (solver, image, OCIO) vs **forge_flame** (adapter, Wiretap)
- Single entry point: `flame/camera_match_hook.py` registers Batch UI and hosts the VP line UI
- Solver data flows through pure math before any Flame `PyAttribute` writes
- **Removed from this repo (quick-260505-tb3):** Blender subprocess, `camera_io` / `fbx_io` / `fbx_ascii` / `blender_bridge`, Export/Import Camera menus. Round-trip intent continues in **forge-blender**; see `forge_flame/__init__.py` and PASSOFF.md

## Layers

**forge_core — Pure math, numpy-only:**

- Purpose: VP calibration, image decode, OCIO preview pipeline
- Location: `forge_core/`
- Contains: `solver/`, `math/`, `image/`, `colour/`
- Depends on: numpy only
- Used by: Hook via `forge_flame.adapter`, tests, external tools (e.g. trafFIK)

**forge_flame — Flame-facing adapters (stripped):**

- Purpose: Bridge solver output to Flame conventions; read frames via Wiretap
- Location: `forge_flame/`
- Contains: `adapter.py` (line packing, Euler, trace), `wiretap.py` (frame bytes, colour space)
- Depends on: forge_core; Wiretap CLI/SDK when running in Flame
- Used by: Hook, tests

**flame/camera_match_hook.py — Batch hook + UI:**

- Purpose: Menu registration, VP line PySide6 UI, Wiretap frame pull, OCIO tonemapped preview, Apply-to-Action
- Depends on: forge_core, forge_flame, Flame API, PySide6
- Used by: Flame batch hook loader

## Data flow

**Solve pipeline (VP lines → Action camera):**

1. UI captures line endpoints in pixels → adapter input
2. `forge_flame.adapter.solve_for_flame()` — VP fit per axis, `solve_2vp` / `solve_1vp`, Euler decomposition, default back distance
3. Hook applies position / rotation / FOV / focal on chosen `PyCoNode` camera

**Frame preview:**

1. Wiretap CLI reads one frame from clip
2. `forge_core.image.buffer` decodes container → RGB
3. `forge_core.colour.ocio.OcioPipeline` applies DisplayViewTransform
4. PySide6 widget draws plate + VP overlays

## State management

- VP lines and UI state: in-widget until Apply
- Solver trace: `/tmp/forge_camera_match_trace.json` (optional diagnostics)
- Camera parameters: persisted on Flame Action via PyAttributes
- Batch menu callbacks: fixed at hook registration — **Flame restart** required for handler code changes (see `memory/flame_module_reload.md`)

## Key abstractions

- **`forge_core.solver.solve_2vp` / `solve_1vp`** — focal + rotation matrix from VP geometry
- **`forge_flame.adapter.solve_for_flame`** — Flame ZYX Euler, pixel-scale camera back, tracing
- **`forge_flame.wiretap`** — `wiretap_rw_frame` orchestration and buffer decode hooks

## Entry points

- **`get_batch_custom_ui_actions()`** — registers **FORGE → Camera → Open Camera Calibrator** (clip scope); post-strip, no Blender export/import actions in this repo
- **`_launch_camera_match` / `_solve_lines`** — VP UI and solve/apply path (see hook source for exact symbols)

## Error handling

- Degenerate VP / negative focal: solver returns `None`; UI shows unable-to-solve
- Wiretap / decode / OCIO: user-visible errors or safe fallback (e.g. passthrough preview)
- PyAttribute writes: guarded; Flame handles rename collisions

## Cross-cutting concerns

- **Coordinates:** Flame Y-up, pixel-scale conventions per adapter
- **Rotation:** Flame ZYX with negations per `memory/flame_rotation_convention.md` (historical FBX verification referenced there; FBX code no longer in-tree)
- **Colour:** OCIO config glob under Flame install paths (see `install.sh` preflight)

---

*Architecture analysis refreshed 2026-05-12 for VP-only calibrator.*
