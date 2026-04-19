# Codebase Concerns

**Analysis Date:** 2026-04-19

## Tech Debt

### 1. FBX Python SDK wheel incompatibility (critical workaround)
- **Issue:** Autodesk's FBX Python SDK ships as a `cp310`-only wheel; Flame 2026.2.1 bundles Python 3.11.5, so the SDK cannot load in-process.
- **Files:** `forge_flame/fbx_ascii.py` (1167 LOC custom parser/writer)
- **Impact:** We built our own narrow ASCII FBX parser rather than using the official SDK. While functional, this creates a long-term maintenance burden if FBX schema or Flame's export format evolves. The custom parser is scoped to camera + AnimCurve data only and will break if Flame adds new FBX features.
- **Fix approach:** Monitor Autodesk FBX SDK releases for Python 3.11+ support. Once available, gradually migrate reader/writer paths back to the official SDK. Until then, document the scope boundaries clearly and add integration tests against each new Flame version's FBX output.

### 2. Flame module reload pattern has incomplete refresh (batch menu cache issue)
- **Issue:** The `gc`/`exec` reload workaround documented in `memory/flame_module_reload.md` refreshes module globals but NOT Flame's internal batch menu dispatch table. After code changes, menu handler callbacks still run stale code until Flame restart.
- **Files:** `flame/camera_match_hook.py`, `memory/flame_module_reload.md`, `install.sh`
- **Impact:** Development iteration is slow — after editing a menu handler, restarting Flame is mandatory to see the change. Workaround (calling handlers directly via bridge) is fragile and not discoverable to users.
- **Fix approach:** Add `__init__.py` stub to prevent namespace-package drift (already done in install.sh). For faster iteration, consider forking a separate development Python subprocess listening on a local port (similar to forge-bridge) so code changes can be picked up without Flame restart. Document this in DEVELOPMENT.md.

### 3. Single-frame camera I/O (v1 limitation)
- **Issue:** `forge_flame/camera_io.py` is single-frame only; it reads/writes only the frame number and static camera properties (position, rotation, focal).
- **Files:** `forge_flame/camera_io.py` (226 LOC), `tests/test_camera_io.py` (159 LOC)
- **Impact:** Animated camera round-trip currently goes through FBX (via `fbx_io.py` → `fbx_ascii.py`) rather than direct JSON + PyAttribute. If Flame ever exposes a keyframe API, this v1 limitation blocks a simpler implementation path.
- **Fix approach:** Extend `export_flame_camera_to_json` to walk PyAttribute keyframes on animated cameras (requires live Flame session to confirm the PyAttribute keyframe call shape — untested territory). This is a **future** task; current animated route through FBX is stable and tested.

## Known Bugs

### 1. Flame `current_frame.set_value()` with auto_key=True crashes Flame
- **Symptoms:** Hard crash (segfault or unrecoverable hang) when attempting to programmatically scrub the timebar while auto-keying is enabled.
- **Files:** (no direct call site in current codebase; flagged in `memory/flame_keyframe_api.md`)
- **Trigger:** Call `flame.batch.current_frame.set_value(f)` with `flame.batch.auto_key.get_value() == True`.
- **Workaround:** Do NOT use this pattern. For animated I/O, use `PyActionNode.export_fbx(bake_animation=True)` instead. This call was probed twice during v6.2 development and crashed both times — not worth further investigation.

### 2. Perspective camera inclusion in FBX bake suspected to crash Flame
- **Symptoms:** Flame crash during `export_fbx` with `bake_animation=True` when the Perspective (viewport/tumble) camera is included in the export.
- **Files:** `forge_flame/fbx_io.py` (filters Perspective unconditionally), `memory/flame_perspective_camera.md`
- **Trigger:** Include the built-in `Perspective` camera node in `action.export_fbx(..., bake_animation=True)`.
- **Workaround:** `fbx_io.iter_keyframable_cameras()` and `export_action_cameras_to_fbx()` unconditionally exclude Perspective via name-check (`cam.name.get_value() != 'Perspective'`). This is non-optional and cannot be overridden by callers.

### 3. Wiretap single-frame reader produces GBR channel order (not RGB)
- **Symptoms:** Color channels appear swapped (green and blue reversed) when reading raw buffers from Wiretap CLI.
- **Files:** `forge_flame/wiretap.py`, `memory/wiretap_frame_read.md`
- **Trigger:** Use `wiretap_rw_frame` to read float buffer from MXF; raw bytes arrive as GBR despite format tag claiming RGB.
- **Workaround:** Implemented in `forge_flame/wiretap.py` — flip vertically, reorder to `[..., [2, 0, 1]]` to convert GBR → RGB. Also handles 16-byte header stripping and bottom-up (OpenGL) orientation.

## Security Considerations

### 1. forge-bridge HTTP endpoint is development-only (not production-integrated)
- **Risk:** The HTTP bridge (`127.0.0.1:9999/exec`) used for subprocess orchestration and live probing is documented as a dev dependency. It is not yet integrated into the `install.sh` production deployment story, so users deploying from a release will not have it available.
- **Files:** `forge_flame/blender_bridge.py`, `PASSOFF.md` (v6.2 "What's next" section), `/Users/cnoellert/.claude/projects/-Users-cnoellert-Documents-GitHub-forge-calibrator/memory/flame_bridge.md`
- **Current mitigation:** The Blender ↔ Flame round-trip works via subprocess calls (not the bridge), so production users are not blocked. The GSD-scoped milestone ("seamless Blender↔Flame bridge") includes forge-bridge deploy story as a required phase.
- **Recommendations:** (1) Document forge-bridge as "development only" in README until deployment is finalized. (2) When integrating into production, ensure the bridge listens only on `127.0.0.1` (already hardcoded); add firewall guidance if deployment scope expands. (3) Add authentication/token validation if the bridge ever listens on non-loopback interfaces.

### 2. No input validation on file paths in FBX round-trip
- **Risk:** `fbx_io.export_action_cameras_to_fbx()` and `import_fbx_to_action()` accept arbitrary file paths; no validation that paths are within trusted locations.
- **Files:** `forge_flame/fbx_io.py` (lines 96–165 export, 173–232 import), `forge_flame/fbx_ascii.py` (writer uses `open(path, 'w')`)
- **Current mitigation:** In production, paths are sourced from Flame's UI dialogs (user-controlled) and temp directories managed by the hook. No path traversal vectors in current use.
- **Recommendations:** If FBX paths ever come from external sources (e.g., API, configuration files), add validation: ensure paths are absolute, canonicalize them, check they don't escape a designated temp or project directory.

### 3. Flame batch menu callback has no role-based access control
- **Risk:** The Camera Match batch menu appears for any user with Flame open. No checks for production vs. non-production environments or user permissions.
- **Files:** `flame/camera_match_hook.py` (entry point `get_batch_custom_ui_actions()`, lines 2090–2111)
- **Current mitigation:** This is an internal post-production tool with trusted operator assumptions. Flame itself handles user authentication at the application level.
- **Recommendations:** If deployed to multi-user or untrusted environments in the future, add environment checks (e.g., inspect Flame project metadata) to hide the menu on production masters.

## Performance Bottlenecks

### 1. Wiretap single-frame reads are slow for long clips
- **Problem:** `wiretap_rw_frame` reads one frame at ~1.5s for a 4608×3164 32-bit float MXF. For a 1000-frame clip with manual frame selection, each frame change triggers a ~1.5s read.
- **Files:** `forge_flame/wiretap.py`, `flame/camera_match_hook.py` (frame spinner triggers re-read on change), `memory/wiretap_frame_read.md`
- **Cause:** Wiretap is I/O-bound, pulling from disk or network storage for each frame. No caching layer.
- **Improvement path:** (1) Add a simple LRU cache in `wiretap.py` to cache the last N frames in memory. (2) Preload the current frame + next/prev frames asynchronously on frame change. (3) Offer a "cache to disk" mode for power users analyzing multi-frame sequences. (4) Investigate whether Flame's internal frame cache can be queried via Python.

### 2. Large hook file (2112 LOC) makes iteration and testing harder
- **Problem:** `flame/camera_match_hook.py` contains VP solver UI, Wiretap reader, OCIO pipeline, Blender orchestration, AND the Flame batch hook logic in one file. Complex interdependencies make it hard to unit-test pieces in isolation.
- **Files:** `flame/camera_match_hook.py` (2112 LOC monolith)
- **Cause:** Historical structure (grew organically from a single-purpose tool). Refactoring risk is high because the module reload gotchas make in-Flame testing tedious.
- **Improvement path:** (1) Extract remaining Flame-agnostic UI components (ImageWidget, CameraMatchWindow) into a separate `flame/camera_match_ui.py`. (2) Move Wiretap reader into `forge_flame/wiretap.py` (already done but could be more complete). (3) Create a test double for Flame PyAttribute/PyCoNode so unit tests don't require Flame. (4) Adopt a staged refactoring: one batch menu handler per session, not all at once.

### 3. ASC II FBX parser uses recursive descent with no streaming
- **Problem:** `forge_flame/fbx_ascii.py` tokenizes the entire file into memory, then recursively parses it all. For large FBX files (multi-camera exports), this could consume significant memory.
- **Files:** `forge_flame/fbx_ascii.py` (1167 LOC), particularly the `FBXParser` class
- **Cause:** Simplicity — recursive descent is easier to reason about than streaming. Current scope (camera + AnimCurve only) keeps FBX files small in practice.
- **Improvement path:** (1) For now, document the limitation: "not intended for FBX files > 10MB". (2) If file size becomes an issue, switch to a streaming parser that processes nodes as they're encountered. (3) Add benchmarks for worst-case FBX sizes (multi-camera, multi-frame).

## Fragile Areas

### 1. Flame Perspective camera filtering is fragile (name-based detection)
- **Files:** `forge_flame/fbx_io.py` (lines 67–68: `if n.name.get_value() == "Perspective"`), `flame/camera_match_hook.py` (similar check in camera dropdown filter)
- **Why fragile:** Detection by exact string match on camera name. If Flame changes the built-in camera's name in a future version, filtering breaks silently (Perspective gets included in exports).
- **Safe modification:** Before upgrading Flame, verify the built-in camera's name hasn't changed. If it has, update the string literal in both files. Consider adding a type-based check if Flame ever exposes camera type info via Python.
- **Test coverage:** `tests/test_fbx_io.py` (19 tests) includes Perspective filtering verification, but only for duck-typed camera objects. Real Flame integration test (live Flame export) is not automated.

### 2. OCIO config path discovery via glob (fragile to Flame upgrades)
- **Files:** `flame/camera_match_hook.py` (`_resolve_ocio_config_path()`, implicit glob dependency), `install.sh` (line 43: `OCIO_GLOB="/opt/Autodesk/colour_mgmt/configs/flame_configs/*/aces2.0_config/config.ocio"`)
- **Why fragile:** Both code and install script glob for "newest" OCIO config under `/opt/Autodesk/colour_mgmt/configs/flame_configs/`. If Flame's directory structure changes, globs fail silently and OCIO reverts to passthrough (no color management).
- **Safe modification:** After each Flame upgrade, manually verify `/opt/Autodesk/colour_mgmt/configs/flame_configs/` exists and contains an `aces2.0_config/`. If structure changed, update both globs. Add a preflight check to `install.sh` or the hook's startup to warn if no config is found.
- **Test coverage:** No automated test for config discovery. The path is system-dependent and not easy to mock.

### 3. Blender script path resolution has three fallback layers (easy to misconfigure)
- **Files:** `forge_flame/blender_bridge.py` (lines 26–32 in docstring), `tests/test_blender_bridge.py` (23 tests), `install.sh` (lines 28, 40)
- **Why fragile:** Script paths are resolved via (1) env override, (2) dev checkout relative path, (3) install path. Misconfigured env var or missing install directory silently falls back to other options, masking the real problem.
- **Safe modification:** If adding new scripts (e.g., a new `verify_camera.py` tool), ensure it's present in all three locations: dev checkout, install destination, and test mocks. Run tests after adding the script.
- **Test coverage:** `tests/test_blender_bridge.py` covers path resolution and CLI composition. Blender binary discovery is tested without requiring Blender; script discovery is tested via mocking.

### 4. FBX template writer assumes static template structure is stable
- **Files:** `forge_flame/fbx_ascii.py` (lines 700–1167 in `v5_json_to_fbx()`), `forge_flame/templates/camera_baked.fbx` (template fixture)
- **Why fragile:** The writer emits FBX by mutating a real Flame-exported template (`camera_baked.fbx`). If Flame changes its FBX structure (Definitions, Properties70 sections, Connections graph), the writer will produce invalid FBX that `import_fbx` rejects.
- **Safe modification:** When upgrading Flame, re-export a test camera from Flame to disk, compare its structure to the saved template. If any new sections appear (especially Definitions or Connections), update `camera_baked.fbx` and run `tests/test_fbx_ascii.py::test_writer_round_trip` to ensure the new template round-trips correctly.
- **Test coverage:** `tests/test_fbx_ascii.py` (51 tests) includes round-trip tests that parse, emit, and re-parse. Live Flame integration test (bake→extract→re-import) is manual.

## Scaling Limits

### 1. Custom FBX parser is scoped to camera + AnimCurve data only
- **Current capacity:** Works for up to ~1000-frame animated cameras (tested with 3-frame fixture). No hard limit, but memory usage scales linearly with frame count.
- **Limit:** If a user attempts to import a multi-camera FBX with meshes, lights, or complex properties, those sections are silently ignored by the reader and NOT preserved by the writer. Round-trip loses non-camera data.
- **Scaling path:** If multi-object support is needed, extend the parser to handle full FBX structure (see `forge_flame/fbx_ascii.py` scope boundaries, lines 20–27). This is a large undertaking; prefer keeping scope narrow for now.

### 2. Wiretap reader has no parallelization (single-frame-at-a-time)
- **Current capacity:** One frame at ~1.5s for MXF sources. For a 100-frame solve proof-of-concept, expect ~150s just to load frames.
- **Limit:** If Camera Match ever supports multi-frame simultaneous solves (e.g., temporal consistency), the single-frame Wiretap reader becomes a bottleneck.
- **Scaling path:** (1) Batch Wiretap reads if possible (query Wiretap CLI for multi-frame batch mode). (2) Spawn parallel Wiretap processes (limited by I/O bandwidth). (3) Cache frames in temp storage and read directly via cv2 on subsequent accesses.

### 3. OCIO DisplayViewTransform is CPU-bound (no GPU acceleration)
- **Current capacity:** Reasonably fast for 1920×1080 sources on modern CPUs (~100ms for color transform + preview). For 8K sources, expect 200–400ms.
- **Limit:** If source plates scale to 8K or higher, OCIO transform becomes noticeable in the UI feedback loop (frame change → Wiretap read → OCIO transform → display).
- **Scaling path:** (1) Pre-calculate color transform for common sequences and cache to disk. (2) Investigate OCIO GPU implementations (not available in Flame's bundled PyOpenColorIO as of 2026.2.1). (3) Offer a "low-res preview" mode that downsamples source before transform, then upsamples for display.

## Test Coverage Gaps

### 1. Flame integration not automated (live session only)
- **What's not tested:** The full Camera Match UI flow: open clip → drag VP lines → Apply to Action → solve reaches the Flame camera. Also: Perspective filtering, Action wiring, axis drops, colour space detection.
- **Files:** `flame/camera_match_hook.py` (2112 LOC entry point), no corresponding integration test file
- **Risk:** A change to the hook could break the UI or batch menu dispatch without warning. The module reload gotchas make even manual testing tedious.
- **Priority:** **Medium** — this is a user-facing feature and should have at least smoke tests. Consider building a test double of Flame's PyFlame API so UI paths can be exercised without a running Flame instance.

### 2. Wiretap frame reading untested (system-dependent)
- **What's not tested:** Actual reads from MXF clips via `wiretap_rw_frame`. The current `tests/` suite mocks Wiretap or uses local JPEG fixtures.
- **Files:** `forge_flame/wiretap.py`, `flame/camera_match_hook.py` (calls Wiretap in `_read_source_frame`)
- **Risk:** Channel reordering, header stripping, or float quantization bugs won't surface until a user tries to read a real clip.
- **Priority:** **High** — add a fixture .MXF or .mov file to the repo and a test that reads a real frame, verifies dimensions and colour values. Alternatively, document Wiretap as "tested manually on ARRI LogC4 MXF only" until automation is feasible.

### 3. FBX round-trip not tested for non-camera properties (lights, models, meshes)
- **What's not tested:** FBX import/export of anything other than cameras and axes. Mesh deformation, light falloff, model transforms: out of scope but not tested against regression.
- **Files:** `forge_flame/fbx_ascii.py`, `forge_flame/fbx_io.py`
- **Risk:** If these features are accidentally added to the export in a future Flame version, the parser silently ignores them and they're lost on round-trip. No warning to the user.
- **Priority:** **Low** — scope is intentionally narrow. Document this in the module docstring and add a comment in the test suite explaining why non-camera tests are absent.

### 4. Blender script invocation not end-to-end tested (Blender not required)
- **What's not tested:** Actual invocation of `bake_camera.py` and `extract_camera.py` via Blender subprocess. Tests mock the scripts or test them in isolation.
- **Files:** `tools/blender/bake_camera.py`, `tools/blender/extract_camera.py`, `tests/test_blender_bridge.py` (mocks), `tools/blender/roundtrip_selftest.sh` (manual shell script)
- **Risk:** A Blender version change could break the scripts' argument parsing, math, or output format without warning in CI.
- **Priority:** **Medium** — add a CI job that installs Blender (via Docker or native) and runs `roundtrip_selftest.sh` on each commit. For now, document "tested manually with Blender 4.5 on macOS" in README.

## Dependencies at Risk

### 1. numpy — vendored in forge conda env, pinned version unclear
- **Risk:** `forge_core/` depends on numpy for solver math. The forge conda env is created with `conda create -n forge python=3.11 numpy opencv-python` (no version pin in `install.sh` line 116). If numpy's API changes in a future major release, code could break.
- **Impact:** `forge_core/solver/solver.py`, `forge_core/solver/fitting.py`, all Blender scripts
- **Migration plan:** (1) Pin numpy version explicitly in install.sh: `numpy==1.26.0` (or whatever version is tested). (2) Add a `requirements.txt` at the repo root with pinned versions. (3) Update on each Flame upgrade and test solver math against the new version.

### 2. opencv-python — used for VP line drawing, version not pinned
- **Risk:** `flame/camera_match_hook.py` uses `cv2.line()`, `cv2.circle()`, etc. to draw VP overlays. No version pinned; newer cv2 might have API changes in drawing functions.
- **Impact:** `flame/camera_match_hook.py` (ImageWidget.draw_vp_lines, etc.)
- **Migration plan:** (1) Pin cv2 in install.sh. (2) Document tested version (e.g., "opencv-python==4.8.0.74"). (3) Test drawing functions when upgrading cv2 major versions.

### 3. PyOpenColorIO — bundled with Flame, version not controlled
- **Risk:** `forge_flame/colour/ocio.py` and `flame/camera_match_hook.py` import `PyOpenColorIO`. Version depends on Flame release; forward/backward compatibility not guaranteed.
- **Impact:** OCIO pipeline (DisplayViewTransform, config loading)
- **Migration plan:** (1) Test OCIO imports and calls when upgrading Flame. (2) Document minimum Flame version required (currently 2026.2.1). (3) If OCIO API changes across Flame versions, add version detection and fallback code paths.

### 4. Blender version compatibility (bake/extract scripts)
- **Risk:** `tools/blender/bake_camera.py` and `extract_camera.py` use `bpy` API (Blender's Python). Blender major versions often break `bpy` API; scripts are tested against Blender 4.5 only.
- **Impact:** All Blender round-trip functionality
- **Migration plan:** (1) Update PASSOFF.md with tested Blender versions. (2) Add CI job or manual test for each new Blender LTS release. (3) Add `bpy.__version__` checks in scripts if APIs diverge significantly; emit clear error messages rather than cryptic crashes.

## Missing Critical Features

### 1. No integration of forge-bridge into production installer
- **Problem:** The HTTP bridge (`127.0.0.1:9999/exec`) is documented as necessary for future GSD features (Blender addon calling back to Flame). Currently, `install.sh` does NOT deploy or configure the bridge for auto-start. Only Blender subprocess invocation works in production.
- **Blocks:** GSD milestone "seamless Blender↔Flame bridge" phase #3 (forge-bridge deploy story)
- **Priority:** **Required for v6.3+**

### 2. No Blender-only install mode (skips forge env preflight)
- **Problem:** Flame users who want only the Blender round-trip (no Camera Match UI) still need to install the forge conda env (numpy, cv2) even though those are only used by the hook, not by the round-trip tools.
- **Blocks:** Frictionless deployment for users on restricted environments (no conda, no access to package mirrors)
- **Priority:** **Nice-to-have** — document workaround: deploy only `forge_core/`, `forge_flame/`, `tools/blender/` to install location, skip forge env preflight.

### 3. No automated testing framework for Flame integration (live session only)
- **Problem:** The Camera Match hook can only be tested by running it in a live Flame session. No test doubles or automation.
- **Blocks:** Confident refactoring of the 2112-line hook. CI/CD pipeline for hook changes.
- **Priority:** **High** — blocking code quality improvements. Consider building a PyFlame mock object library.

---

*Concerns audit: 2026-04-19*
