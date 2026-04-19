# External Integrations

**Analysis Date:** 2026-04-19

## APIs & External Services

**Autodesk Wiretap (In-Process):**
- Wiretap CLI and Python SDK - Media frame access and colour-space tagging
  - CLI: `/opt/Autodesk/wiretap/tools/current/wiretap_rw_frame` - Single-frame byte extraction
  - SDK path: `/opt/Autodesk/wiretap/tools/current/python` - `adsk.libwiretapPythonClientAPI` import
  - Implementation: `forge_flame/wiretap.py` - `get_clip_colour_space(clip)` and `extract_frame_bytes(clip, frame_num)`
  - Used for: Reading one frame from a Flame clip without triggering PyExporter (which fails on MXF/Sony media)

**Autodesk Flame Python API (In-Process):**
- PyClipNode, PyActionNode, PyCoNode objects - Camera and batch node manipulation
  - Import: Flame process global (no package name)
  - Implementation: `flame/camera_match_hook.py` - Batch menu registration, action access
  - Implementation: `forge_flame/camera_io.py` - Single-frame camera read/write via PyAttribute
  - Implementation: `forge_flame/fbx_io.py` - FBX export/import with Perspective camera filtering
  - Used for: Batch UI menu hooks, camera parameter access, FBX I/O

**Autodesk OpenColorIO (In-Process, Flame-bundled):**
- PyOpenColorIO module - OCIO colour-space conversion and display pipeline
  - Source: Flame's bundled Python (not pip-installable in forge env due to version conflicts)
  - Path: `/opt/Autodesk/python/*/lib/python3.11/site-packages/PyOpenColorIO`
  - Implementation: `forge_core/colour/ocio.py` - `OcioPipeline` class wrapping Config + DisplayViewTransform
  - Config location: `/opt/Autodesk/colour_mgmt/configs/flame_configs/*/aces2.0_config/config.ocio` (glob-resolved, auto-upgrades with Flame)
  - Used for: Preview window tonemapping (RRT + ODT, soft highlight rolloff for marking lines on bright plates)

**PySide6 (Flame-bundled):**
- QtWidgets, QtGui, QtCore - UI toolkit for the line-drawing window
  - Import: From Flame's bundled Python
  - Implementation: `flame/camera_match_hook.py` - VP line-drawing canvas, dialogs, overlays
  - Used for: Interactive VP line tool interface, error dialogs, parameter input dialogs

## Data Storage

**Media Input:**
- Source: Flame clip nodes (PyClipNode) - Video/image frames accessed via Wiretap
- Format: Depends on source media (Alexa LogC4, ProRes, etc.)
- Read via: `forge_flame/wiretap.extract_frame_bytes()` → raw RGB bytes → `forge_core/image/buffer.py`

**Intermediate Serialization:**
- Format: JSON v5 contract (camera parameters + keyframe data)
  - Spec: Documented in `PASSOFF.md` v5 section and bake_camera.py docstring
  - Structure: width, height, film_back_mm, frames array with position/rotation/focal per frame
  - Example files: `/tmp/forge_camera_match_*.json` (written during export, read during import)
  - Implementation: `forge_flame/camera_io.py` (single-frame), `forge_flame/fbx_ascii.py` (multi-frame via FBX intermediate)

**FBX Binary Format (Animated Camera Round-Trip):**
- Format: ASCII FBX 7.7.0 (Flame's export format; binary not supported via Python API)
- Scope: Cameras + AnimCurve keyframes only (no meshes, lights, materials)
- Temporary files: `/tmp/forge_camera_match_*.fbx` (intermediate between Flame export and custom parser)
- Custom parser: `forge_flame/fbx_ascii.py` - Tokenizer, recursive-descent parser, template-driven writer
- Template: `forge_flame/templates/camera_baked.fbx` - Real Flame-emitted FBX used as structural blueprint for writer
- Implementation: `forge_flame/fbx_io.py` wraps `PyActionNode.export_fbx()` + `fbx_ascii.fbx_to_v5_json()` for reads; reads wrap `fbx_ascii.v5_json_to_fbx()` + `PyActionNode.import_fbx()` for writes

**Blender .blend File Format:**
- Format: Blender 4.x binary (not parsed; manipulated via bpy subprocess API)
- Creation: `tools/blender/bake_camera.py --out path.blend` - Creates or updates camera in .blend file
- Extraction: `tools/blender/extract_camera.py --in path.blend` - Reads camera back to JSON
- Round-trip: JSON → bake → .blend → (user edits in Blender) → extract → JSON → import

**Temporary Storage:**
- Location: `/tmp/` (typically; user can override via dialog)
- Cleanup: Not yet automated (GSD v6.2 TODO: migrate to `tempfile.mkdtemp()` with auto-cleanup on success)
- Files: `.json`, `.fbx`, `.blend` intermediates during export/import cycle

**File Storage (Output):**
- Destination: User's file system via file dialogs
- Format: Blender .blend files for export; Flame Actions (internal) for import
- Reveal: `forge_flame/blender_bridge.reveal_in_file_manager()` shows result in macOS Finder / Linux xdg-open

## Authentication & Identity

**None Implemented**

The tool operates entirely within Autodesk Flame's security boundary. No external API keys, OAuth, or service authentication required. Wiretap access is implicit (SDK is in-process; Flame's permission model applies). Flame's batch UI menu dispatch is tied to the hook registration only.

## Monitoring & Observability

**Error Tracking:**
- None configured

**Logging:**
- Trace file: `/tmp/forge_camera_match_trace.json` - Solver state dump written by `forge_flame/adapter.solve_for_flame()` on every solve
  - Purpose: Post-mortem debugging of line-fitting and rotation composition
  - Consumed by: `flame/camera_match_hook.py` "Open trace" affordance (reads and displays in dialog)
- Subprocess stderr: `forge_flame/blender_bridge` captures and surfaces Blender subprocess output on error
- Console print: Debug output to Flame's Python console (stderr/stdout available in session log)

**Performance:**
- No profiling infrastructure; solver runs live on user drag (expected <100ms per frame on modern hardware)
- FBX ASCII tokenizer performance not monitored; empirically fast for multi-frame bakes

## CI/CD & Deployment

**Hosting:**
- In-process: Flame application (no remote hosting)
- Subprocess: Blender invocation (binary path via env override or platform defaults)

**Future Integration:**
- forge-bridge HTTP endpoint `127.0.0.1:9999/exec` mentioned in `PASSOFF.md` v6.2 open items for Blender addon "Send to Flame" button
  - Not yet deployed; scoped under GSD milestone "seamless Blender↔Flame bridge"
  - Expected use: Blender addon POSTs extracted camera JSON + metadata to Flame for direct import (no user alt-tab needed)

**CI Pipeline:**
- None implemented
- Local pytest execution only
- Test count: 264 tests across solver math, FBX I/O, hook parity, adapter math, Blender round-trip

## Environment Configuration

**Required Environment Variables:**
- `FORGE_ENV` - Path to conda environment with numpy + opencv-python (defaults to `~/miniconda3/envs/forge`)

**Optional Environment Variables:**
- `FORGE_BLENDER_BIN` - Override Blender binary path (else platform defaults or PATH)
- `FORGE_BLENDER_SCRIPTS` - Override bake/extract script directory (else dev checkout or installed path)

**Secrets Location:**
- None; no credentials required

**Installation Validation:**
- `install.sh` performs preflight checks (see STACK.md) but stores no secrets or tokens

## Webhooks & Callbacks

**None Implemented**

The tool is synchronous and request-response only:
1. User right-clicks clip in Batch → menu handler invoked
2. Solve happens on line drag (live, no callbacks)
3. User clicks Apply → camera written back to Action
4. User exports to Blender → CLI subprocess spawned, waits for completion
5. User imports from Blender → subprocess exits, result ingested

No async webhooks, push notifications, or event subscriptions. Flame batch menu dispatch is the only "callback" mechanism, and it's Flame's internal event system, not external.

---

*Integration audit: 2026-04-19*
