# Architecture

**Analysis Date:** 2026-04-19

## Pattern Overview

**Overall:** Layered host-abstraction pattern (forge_core + forge_flame separation) feeding a Flame batch hook UI orchestrator.

**Key Characteristics:**
- Clean separation between host-agnostic solver/OCIO/image modules (`forge_core/`) and Flame-specific adapters (`forge_flame/`)
- Single entry point: `flame/camera_match_hook.py` (1697 LOC) registers Batch UI actions
- Data flows through pure math layers (no Flame imports) before touching Action cameras
- Multi-surface integration: PySide2 UI, subprocess orchestration to Blender, FBX round-tripping, ASCII FBX parser

## Layers

**forge_core — Pure math, numpy-only, no host bindings:**
- Purpose: Vanishing-point camera calibration, image processing, OCIO color management
- Location: `forge_core/`
- Contains: Solver (2VP/1VP), coordinate transforms, line fitting, focal length computation, camera rotation matrix math, image buffer decoding, OCIO pipeline
- Depends on: numpy only
- Used by: The hook (via `forge_flame.adapter`), Blender scripts (via direct import), tests, external tools (trafFIK)

**forge_flame — Flame-specific adapters:**
- Purpose: Bridge forge_core math to Flame's API surface (Wiretap, PyAction cameras, batch menu)
- Location: `forge_flame/`
- Contains: Solver adapter (ZYX Euler composition), Wiretap frame reader, camera I/O (JSON + FBX), FBX ASCII parser/writer, Blender subprocess orchestration
- Depends on: forge_core, Flame-bundled Python (Wiretap SDK optional)
- Used by: The hook, tests

**flame/camera_match_hook.py — Flame batch hook orchestrator:**
- Purpose: Register batch UI, route user actions through solve/export/import pipelines, surface PySide2 dialogs
- Location: `flame/camera_match_hook.py`
- Contains: Entry point `get_batch_custom_ui_actions()`, VP line UI, preview pipeline, menu action handlers, frame export/capture
- Depends on: forge_core, forge_flame, Flame API (PyClip, PyAction, PyBatch, PySide2)
- Used by: Flame 2026.2.1 batch hook loader

**tools/blender/ — Blender CLI scripts:**
- Purpose: Standalone camera bake/extract scripts executed via `blender --background --python`
- Location: `tools/blender/`
- Contains: `bake_camera.py` (Flame JSON → .blend), `extract_camera.py` (.blend → Flame JSON)
- Depends on: Blender's bpy (mathutils, file I/O)
- Used by: Hook via `forge_flame.blender_bridge` subprocess calls

## Data Flow

**Solve pipeline (user draws lines):**

1. Hook UI captures user line endpoints in pixels → `_solve_lines()`
2. `forge_flame.adapter.solve_for_flame()` receives lines + axis labels + image dimensions
3. For each VP: `forge_core.solver.fitting.fit_vp_from_lines()` produces exact VP or LSQ fit
4. `forge_core.solver.solve_2vp()` computes focal length + camera rotation (pure geometry)
5. Adapter decomposes rotation into Flame ZYX Euler (`compute_flame_euler_zyx`)
6. Adapter scales camera position using `default_cam_back()` pixel-unit convention
7. Hook receives dict: `{focal_rel, vp1_px, vp2_px, position, rotation_euler, ...}`
8. Hook applies to Action camera via `PyAttribute.set_value()`

**Frame export (preview + solve):**

1. Hook exports one frame from clip via Wiretap CLI → `wiretap_rw_frame`
2. Wiretap decodes MXF/MOV frame data to raw RGB bytes
3. Hook decodes via `forge_core.image.buffer.decode_image_container()`
4. Hook applies OCIO color transform via `forge_core.colour.ocio.OcioPipeline`
5. Hook draws VP lines and labels over preview in PySide2 window

**Camera round-trip (Flame ↔ Blender):**

**Export path:**
1. User right-clicks Action → "Export Camera to Blender"
2. Hook reads cameras from Action via `forge_flame.camera_io.export_flame_camera_to_json()`
3. Hook calls `forge_flame.blender_bridge.run_bake_camera()` (subprocess)
4. `tools/blender/bake_camera.py` runs inside Blender, creates/updates camera from JSON
5. Hook reveals .blend in Finder/file manager

**Import path:**
1. User edits camera in Blender, saves .bend
2. User right-clicks Action → "Import Camera from Blender"
3. Hook calls `forge_flame.blender_bridge.run_extract_camera()` (subprocess)
4. `tools/blender/extract_camera.py` runs inside Blender, exports JSON
5. Hook reads JSON via `forge_flame.camera_io.import_json_to_flame_camera()`
6. Hook applies to Action via `PyActionNode.import_fbx()` (creates new camera on Action)

**Animated camera round-trip (v6.2 — ASCII FBX bridge):**

**Export path:**
1. User right-clicks Action → "Export Camera to Blender"
2. Hook calls `action.export_fbx(bake_animation=True, only_selected_nodes=True)` → ASCII FBX 7.7.0
3. `forge_flame.fbx_io.export_fbx_to_action()` filters out Perspective camera, manages selection
4. `forge_flame.fbx_ascii.fbx_to_v5_json()` parses FBX, extracts AnimCurve keyframes
5. Blender scripts import via bake → Blender keyframes mirror Flame keyframe times (NTSC 23.976fps ratios)

**Import path:**
1. User edits camera in Blender, saves .blend
2. Hook calls `extract_camera.py` → JSON with multi-frame data
3. `forge_flame.fbx_ascii.v5_json_to_fbx()` writes ASCII FBX template mutation
4. Hook calls `action.import_fbx()` → Flame bakes animation from FBX AnimCurve nodes
5. New camera created on Action with keyframes matching Blender edits

## State Management

**Ephemeral state (per-solve):**
- VP line endpoints: stored in PySide2 widget during user drawing
- Solver output: held in dict, applied to Action camera on Apply button
- Trace file: written to `/tmp/forge_camera_match_trace.json` per solve, read by diagnostic UI

**Persistent state:**
- Action camera parameters: stored in Flame's Action node (PyAttribute set_value)
- Blender camera metadata: stamped via custom properties (future phase — `forge_bake_action_name`, `forge_bake_camera_name`)
- FBX fixtures: `tests/fixtures/forge_fbx_baked.fbx` (template for writer), `tests/fixtures/forge_fbx_probe.fbx` (live Flame export)

**Flame batch context:**
- Menu callbacks captured at hook-registration time; dynamic reload does NOT refresh them
- Module globals DO reload via gc/exec pattern (see `memory/flame_module_reload.md`)
- Requires Flame restart to pick up UI handler changes

## Key Abstractions

**Solver abstraction (forge_core.solver.solve_2vp):**
- Purpose: Pure 2VP camera calibration from vanishing point lines
- Examples: `forge_core/solver/solver.py:solve_2vp()`, tests in `tests/test_solver.py`
- Pattern: Takes VP lines in image-plane coords, returns focal length + rotation matrix (no Euler, no scale)
- Consumed by: `forge_flame.adapter.solve_for_flame()` which adds Euler decomposition + pixel scaling

**Adapter abstraction (forge_flame.adapter.solve_for_flame):**
- Purpose: Wrap solver output in Flame's conventions (ZYX Euler, pixel-unit depth)
- Examples: `forge_flame/adapter.py`, tests in `tests/test_hook_parity.py`
- Pattern: Line packing (N≥2 lines per VP → LSQ fit), multi-line-to-2-line synthesis for 3-line mode, Euler decomposition
- Consumed by: Hook UI via `_solve_lines()` call

**Camera I/O abstraction (forge_flame.camera_io + fbx_io):**
- Purpose: Single-frame (JSON) and multi-frame (FBX) round-trips between Flame Action and JSON/FBX formats
- Examples: `forge_flame/camera_io.py`, `forge_flame/fbx_io.py`
- Pattern: Flame PyAttribute reads/writes wrapped in JSON serialization; FBX routes through ASCII parser
- Consumed by: Hook export/import handlers

**FBX ASCII abstraction (forge_flame.fbx_ascii):**
- Purpose: Tokenize, parse, and emit ASCII FBX 7.7.0 without external SDK (wheels cp310-only, incompatible with Flame 3.11)
- Examples: `forge_flame/fbx_ascii.py` (tokenizer, recursive-descent parser, template writer), tests in `tests/test_fbx_ascii.py`
- Pattern: Parse → FBXNode tree → camera/AnimCurve extraction; emit via template mutation (inherits Flame's Definitions/Connections)
- Consumed by: `forge_flame.fbx_io` and camera round-trip pipeline

**Blender bridge abstraction (forge_flame.blender_bridge):**
- Purpose: Locate Blender binary, compose CLI args, run bake/extract scripts, surface errors
- Examples: `forge_flame/blender_bridge.py`, tests in `tests/test_blender_bridge.py`
- Pattern: Env override (FORGE_BLENDER_BIN, FORGE_BLENDER_SCRIPTS) → platform defaults → PATH; CLI composition unit-testable
- Consumed by: Hook's export/import handlers

## Entry Points

**Flame batch hook:**
- Location: `flame/camera_match_hook.py`
- Triggers: Flame loads `/opt/Autodesk/shared/python/camera_match/camera_match_hook.py` on startup
- Responsibilities: Register three menu actions (Open Camera Match on clip, Export/Import Camera on Action)

**Menu action: Open Camera Match:**
- Handler: `_launch_camera_match(selection)` (line ~1661)
- Triggers: User right-clicks Clip in Batch → "Camera Match" → "Open Camera Match"
- Responsibilities: Export frame, show PySide2 UI with VP line tool, apply solved camera to Action

**Menu action: Export Camera to Blender:**
- Handler: `_export_camera_to_blender(selection)` (line ~1793)
- Triggers: User right-clicks Action in Batch → "Camera Match" → "Export Camera to Blender"
- Responsibilities: Call `forge_flame.camera_io.export_flame_camera_to_json()`, run Blender bake via subprocess, reveal .blend in file manager

**Menu action: Import Camera from Blender:**
- Handler: `_import_camera_from_blender(selection)` (line ~1958)
- Triggers: User right-clicks Action in Batch → "Camera Match" → "Import Camera from Blender"
- Responsibilities: Run Blender extract via subprocess, read JSON, convert to FBX, call `action.import_fbx()`, create new Action camera

**Blender CLI scripts:**
- `tools/blender/bake_camera.py`: Invoked as `blender --background --python -- --in JSON --out .blend`
- `tools/blender/extract_camera.py`: Invoked as `blender --background --python -- --in .blend --out JSON`

## Error Handling

**Strategy:** Layered validation + user-facing error messages.

**Patterns:**

- **Solver robustness:** If VP fit produces negative focal length or degenerate rotation, `solve_2vp()` returns `None`; adapter surfaces as "unable to solve" in hook UI
- **Frame export:** Wiretap CLI failures surfaced as Flame error dialogs with stderr output; image decode failures handled gracefully (passthrough black if color space unknown)
- **Blender subprocess:** Exit code + stderr captured; Flame error dialog shows command line + error text for debugging
- **FBX parsing:** Tokenizer/parser validate structure; malformed FBX raises `ValueError` with line/col context (caught by import handler)
- **Flame API:** PyAttribute operations wrapped in try-catch; graceful fallback (e.g., camera rename collision handled by Flame auto-numbering)

## Cross-Cutting Concerns

**Logging:** Ad-hoc per-module (no centralized logger). Trace file at `/tmp/forge_camera_match_trace.json` written on every solve for post-mortem debugging.

**Validation:** Type hints throughout; forge_core math functions validate input ranges (focal > 0, vfov ∈ (0°, 180°), etc.); Flame camera I/O validates FOV/focal/position consistency.

**Authentication:** None (Flame's Wiretap SDK assumes local root access).

**Coordinate system conventions:**
- Flame world: Y-up, 1 unit ≈ 1 image pixel, camera at distance h/(2·tan(vfov/2))
- Blender world: Z-up; Flame world is rotated 90° around X-axis to Blender coords
- Rotation: Flame ZYX-with-X,Y-negated (R = Rz(rz) · Ry(-ry) · Rx(-rx)); verified empirically via FBX export (see `memory/flame_rotation_convention.md`)

**Color space:** OCIO pipeline applies Flame's aces2.0_config (SDR 100 nits Rec.709 view) to preview; Wiretap-decoded frame color space auto-detected from clip metadata.

**FPS handling:** NTSC 23.976 (24000/1001) used for KTime conversion to preserve frame alignment on round-trips; 24/25/30/60 fps also supported.

---

*Architecture analysis: 2026-04-19*
