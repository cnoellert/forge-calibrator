<!-- GSD:project-start source:PROJECT.md -->
## Project

**forge-calibrator**

A vanishing-point camera calibration tool that lives inside Autodesk Flame. A VFX artist draws 2-3 reference lines along orthogonal scene edges in a plate; the tool solves a camera (position, rotation, FOV, focal length) and applies it to a Flame Action node. Recent work (v6.x) extends this with a Flame↔Blender camera round-trip so solved cameras — static or animated — can be refined in Blender and returned to Flame.

**Core Value:** **The solved camera must be geometrically faithful to the plate, and the Flame↔Blender round-trip must preserve that fidelity end-to-end.** Everything else — UX polish, seamless workflows, automation — is secondary. If the numbers are wrong, the compositing CG won't glue to the plate and the tool fails its purpose.

### Constraints

- **Tech stack**: Python 3.11 (Flame-bundled) for production code. FBX Python SDK wheel ships cp310-only — not usable in-process. Blender 4.5's FBX importer rejects ASCII FBX — motivates the custom parser in `forge_flame/fbx_ascii.py`.
- **Runtime dependencies**: numpy + opencv-python in a conda `forge` env (dev-side); PyOpenColorIO from Flame's bundled Python (NOT installed in forge — version-conflict risk); Wiretap SDK from Flame; Blender 4.5+ as a subprocess.
- **Dev-only tooling**: forge-bridge is a Tier-3 dev-time RPC probe (HTTP /exec into Flame's Python at 127.0.0.1:9999), analogous to pytest. NOT a calibrator runtime dependency — the hook never imports it. install.sh deploys it for dev convenience; see `memory/forge_family_tier_model.md`.
- **Platform**: macOS + Linux. Windows unsupported (Flame doesn't run there).
- **Compatibility**: Flame 2026.2.1 is the primary target. Older Flame versions untested; newer versions may need API re-verification.
- **Performance (non-goal this milestone)**: Wiretap single-frame reads run ~1.5s for a 4K 32-bit float MXF. Not on the hot path for this milestone's scope.
- **Security posture**: Internal VFX post-production tool. No user-facing auth surface; artifacts live on trusted storage. forge-bridge binds to `127.0.0.1` only.
<!-- GSD:project-end -->

<!-- GSD:stack-start source:codebase/STACK.md -->
## Technology Stack

## Languages
- Python 3.11.5 - Flame 2026.2.1 bundles this; the hook and all production code targets 3.11
- Python 3.12+ - Supported for testing and development (test suite runs on both 3.11 and 3.12)
- Bash - Installation and utility scripts (`install.sh`)
- Blender Python (bundled with Blender 4.5+) - Scripts run in subprocess via `blender --background --python`; uses `bpy` and `mathutils` only, no external forge imports
## Runtime
- Flame 2026.2.1 - VFX compositor where the Camera Match hook is installed and executed
- Blender 4.5+ - Subprocess invocation only; not a runtime host for the Python library
- macOS/Linux development machines - For testing and development with pytest
## Package Managers
- conda (forge environment) - Creates an isolated Python 3.11 environment with:
- pytest - Framework for 264 unit tests covering solver math, FBX I/O, hook parity, adapter math
- rsync or cp - For syncing production code to `/opt/Autodesk/shared/python/`
## Frameworks
- PySide6 - UI toolkit for the Camera Match line-drawing window (bundled with Flame)
- Blender bpy - For animated camera baking/extraction (Blender's Python API, subprocess-only)
- pytest - Test runner and assertion library
- Python standard `unittest.mock` - Mock objects for Flame API simulation
## Key Dependencies
- numpy - Solver math: 2VP intersection, FOV/focal conversion, rotation composition (Euler ZYX), matrix transforms.
- opencv-python (cv2) - GUI overlay rendering in `camera_match_hook.py`; frame preview/annotation on the VP line tool window
- PyOpenColorIO - OCIO pipeline for ACES 2.0 colour management (preview tonemapping, DisplayViewTransform)
- Wiretap SDK - Single-frame media extraction from clips; colour-space tagging lookup
- bpy - Scene graph, camera object manipulation, keyframing
- mathutils - Matrix algebra for Euler/quaternion conversions (numerically must match `numpy` on Flame side for round-trip)
## Configuration
- `FORGE_ENV` - Path to conda forge environment; defaults to `$HOME/miniconda3/envs/forge` if unset (used by `install.sh`)
- `FORGE_BLENDER_BIN` - Override Blender binary location; if unset, uses platform defaults or PATH
- `FORGE_BLENDER_SCRIPTS` - Override bake/extract script directory; if unset, tries dev checkout then installed path
- `/opt/Autodesk/wiretap/tools/current/wiretap_rw_frame` - CLI for single-frame reads (version-safe symlink)
- `/opt/Autodesk/wiretap/tools/current/python` - Wiretap Python SDK path
- `/opt/Autodesk/colour_mgmt/configs/flame_configs/*/aces2.0_config/config.ocio` - OCIO config (glob-resolved, auto-tracks Flame upgrades)
- `/opt/Autodesk/python/*/lib/python3.11/site-packages/PyOpenColorIO` - Flame's bundled OCIO (glob-resolved)
- `/opt/Autodesk/shared/python/camera_match/` - Hook installation target
- `/opt/Autodesk/shared/python/forge_core/` - Host-agnostic library installation
- `/opt/Autodesk/shared/python/forge_flame/` - Flame-specific adapters installation
- `/opt/Autodesk/shared/python/tools/blender/` - Blender scripts (bake_camera.py, extract_camera.py)
- Flame ACES 2.0 config - Preview DisplayViewTransform (RRT + ODT) for soft highlight rolloff on bright plates
- sRGB display target - Standard output for preview
## Build & Deployment
- `install.sh` - Bash installer with preflight checks for:
- Target: `/opt/Autodesk/shared/python/` (sibling directory layout)
- Copies: `camera_match/`, `forge_core/`, `forge_flame/`, `tools/blender/`
- Stub `__init__.py` in camera_match to prevent Flame's namespace-package loader drift
- __pycache__ purged post-install to prevent stale bytecode
- None detected; pytest suite runs locally on developer machines
## Platform Requirements
- macOS or Linux
- Flame 2026.2.1 with Wiretap SDK
- Blender 4.5+ (for Blender→Flame animation testing)
- Python 3.11 or 3.12
- conda with forge environment initialized
- Pytest for test execution
- Flame 2026.2.1 (locked; older versions untested; newer versions may have API changes)
- `/opt/Autodesk/wiretap/tools/current/` - Wiretap installation
- `/opt/Autodesk/colour_mgmt/configs/flame_configs/` - OCIO config directory
- Forge conda environment on the same machine as Flame
- Blender 4.5+ (not strictly locked; older versions untested for FBX compatibility)
- No external Python packages; uses bpy + mathutils only
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

## Naming Patterns
- Module files: lowercase with underscores (e.g., `fbx_ascii.py`, `camera_io.py`, `blender_bridge.py`)
- Test files: `test_<module_name>.py` (e.g., `test_fbx_io.py`, `test_solver.py`)
- Hook entry point: `camera_match_hook.py` for Flame batch hook
- Snake_case for all functions: `compute_flame_euler_zyx`, `iter_keyframable_cameras`, `px_to_image_plane`, `fit_vp_from_lines`
- Private/internal functions start with underscore: `_tokenize`, `_parse_fbx`, `_ensure_forge_env`, `_selection_restored`
- Predicates: `_is_*` or named directly as boolean (e.g., `gimbal` for gimbal lock condition)
- Snake_case for all local and module variables: `ktime_per_frame`, `principal_point`, `focal_length`
- Constants: ALL_CAPS with underscores: `FBX_KTIME_PER_SECOND`, `DEFAULT_PIXEL_TO_UNITS`, `AXIS_VECTORS`
- Loop variables: conventional short names (`x`, `y`, `i`, `p0`, `p1`, `vp1`, `vp2`)
- Type hints use full names: `np.ndarray`, `Optional[float]`, `Tuple[float, float, float]`
- Classes use PascalCase: `FBXNode`, `TestTokenizer`, `TestParser`, `_Camera`, `_Action` (fakes are uppercase too)
- Dataclasses and named tuples: PascalCase (e.g., `properties` dicts use lowercase string keys)
- Type aliases: descriptive names like `LinePx = Tuple[Tuple[float, float], Tuple[float, float]]`
## Code Style
- Line length: no strict limit observed; files go up to ~120 chars when readability demands
- Indentation: 4 spaces per level (standard Python)
- Blank lines: 1 between functions, 2 between top-level class definitions
- Trailing commas: used in multiline function calls and imports for clarity
- `from __future__ import annotations` at top of every module file (enables postponed evaluation of type hints)
- Stdlib imports first, then third-party (numpy, opencv, etc.), then local relative imports
- Relative imports use dot notation: `from .math_util import orthogonal_projection_on_line`
- All local imports grouped together after third-party, separated by blank line
- Example from `forge_flame/fbx_io.py`:
- No formal linter config (no .eslintrc, .flake8, or pyproject.toml lint section)
- Convention enforced by review: noqa: E402 used in test files when sys.path.insert needed before imports (standard pattern for modifying import path)
## Comments and Documentation
- Every module file has a detailed docstring explaining PURPOSE and SCOPE
- Example from `forge_flame/fbx_ascii.py`: 35-line docstring covering "Why this module exists", scope boundaries (cameras only, animation curves only), and key design decisions
- Example from `forge_core/math/rotations.py`: explains the Flame ZYX rotation convention with verification reference, why it lives in forge_core not forge_flame, and which modules re-export it
- Docstrings are extensive and explain the WHY, not just the WHAT
- Google-style docstrings with Args, Returns, optional Raises
- Example from `forge_core/solver/solver.py`:
- Inline comments explain GOTCHAS and non-obvious decisions
- Example from `forge_flame/fbx_io.py` — explains why Perspective camera is filtered and references external documentation: `see memory/flame_perspective_camera.md`
- Used for algorithm explanations (e.g., homogeneous line math in `fitting.py`)
- Used for platform/version-specific behavior (e.g., GBR channel reorder in Wiretap buffer)
- Used for referencing external memory/ docs: `see memory/flame_rotation_convention.md`
- Comments explain tricky numeric behavior (e.g., gimbal lock tolerance in `rotations.py`: `cb <= 1e-6`)
## Import Organization
- No aliasing used (`import numpy as np` is standard, never custom aliases)
- Relative imports use dot notation, no sys.path manipulation except in entry points
- Exception: Test files use sys.path manipulation to import parent package:
## Error Handling
- Guard clauses return early with sentinel values (None) rather than raising
- Explicit checks over exceptions when the condition is expected
- Raise on truly exceptional conditions only
- Context managers for cleanup: `@contextmanager` for save/restore patterns
## Type Hints
- Type hints present on function signatures throughout
- Return types always annotated: `-> Optional[float]`, `-> np.ndarray`, `-> None`
- Parameter types annotated: `vp1: np.ndarray`, `frame: int`, `cam_rot: np.ndarray`
- Generic types use `from typing import Optional, Tuple, Sequence`
- `from __future__ import annotations` allows forward references and cleaner syntax
- `np.ndarray` for arrays (shape noted in docstring)
- Scalar returns wrapped as float: `return float(deg[0])`
- Type coercion: `int(round(...))` for frame numbers, `float(value)` for return values
## Docstring Structure for Complex Modules
## Code Organization Within Files
- Module docstring with algorithm references
- Constants at top (keyed by problem domain)
- Functions in building-block order (low-level → high-level)
- No classes except test fakes
- Module docstring explaining why it exists and scope boundaries
- Import guards for optional dependencies (e.g., duck-typing checks)
- Context managers for cleanup patterns
- Functions in workflow order (input → processing → output)
- Cross-references to memory/ docs for non-obvious decisions
- Module docstring explaining what's tested and what's NOT tested (important!)
- Imports grouped: pytest, sys/os, then relative imports with noqa: E402
- Test fixtures/fakes defined first (e.g., `_Attr`, `_Camera`, `_Action`)
- Test classes grouped by feature (e.g., `TestTokenizer`, `TestParser`, `TestExtraction`)
- Helper methods prefixed with underscore (e.g., `_kinds`, `_values`, `_make_buffer`)
- Parametrized tests use `@pytest.mark.parametrize` with explicit test case arrays
## Duck Typing
- Flame API objects checked via `hasattr()` rather than `isinstance()`
- Example from `fbx_io.py`: `iter_keyframable_cameras` checks `hasattr(n, attr)` for `position`, `rotation`, `fov`, `focal`
- This makes the code unit-testable without importing the real flame module
- Minimal implementations: `_Attr` (just get_value/set_value), `_Camera` (has the four attributes)
- Fakes record call history in lists for assertion: `export_fbx_calls`, `selected_at_call`
- Return values configurable for testing error paths: `export_fbx_return = True`, `import_fbx_return = None`
## Numeric Precision
- Float comparisons use `math.isclose(a, b, abs_tol=1e-4)` or `np.testing.assert_allclose(a, b, atol=1e-10)`
- Gimbal lock detection uses `<= 1e-6` threshold
- VP-at-infinity detection uses `< 1e-12` threshold
- Frame rounding: `int(round(...))` to nearest integer
- Every numeric constant with domain meaning documented
- Example: `FBX_KTIME_PER_SECOND = 46186158000` (documented as FBX's fixed internal time resolution)
- Example: gimbal lock tolerance `1e-6` chosen to catch numerical underflow while avoiding false positives
## Module Structure Summary
- Every file is numpy-only; safe to import anywhere (Flame, Blender, CLI)
- Solver pipeline organized by abstraction level
- Helpers pulled out when shared (e.g., `fitting.py` shared by adapter and hook)
- Every module starts with "Why this module exists" docstring
- Non-Flame-critical logic extracted to forge_core
- Flame API calls guarded by duck-typing, not isinstance checks
- Cross-references to memory/ docs for tricky behaviors
- No Flame binary required; Flame objects mocked
- Test organization mirrors source modules: `test_fbx_io.py` tests `fbx_io.py`
- Fixtures defined in-file, no conftest.py (lightweight, self-contained)
- Each test module has a docstring explaining what's tested and why
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

## Pattern Overview
- Clean separation between host-agnostic solver/OCIO/image modules (`forge_core/`) and Flame-specific adapters (`forge_flame/`)
- Single entry point: `flame/camera_match_hook.py` (1697 LOC) registers Batch UI actions
- Data flows through pure math layers (no Flame imports) before touching Action cameras
- Multi-surface integration: PySide2 UI, subprocess orchestration to Blender, FBX round-tripping, ASCII FBX parser
## Layers
- Purpose: Vanishing-point camera calibration, image processing, OCIO color management
- Location: `forge_core/`
- Contains: Solver (2VP/1VP), coordinate transforms, line fitting, focal length computation, camera rotation matrix math, image buffer decoding, OCIO pipeline
- Depends on: numpy only
- Used by: The hook (via `forge_flame.adapter`), Blender scripts (via direct import), tests, external tools (trafFIK)
- Purpose: Bridge forge_core math to Flame's API surface (Wiretap, PyAction cameras, batch menu)
- Location: `forge_flame/`
- Contains: Solver adapter (ZYX Euler composition), Wiretap frame reader, camera I/O (JSON + FBX), FBX ASCII parser/writer, Blender subprocess orchestration
- Depends on: forge_core, Flame-bundled Python (Wiretap SDK optional)
- Used by: The hook, tests
- Purpose: Register batch UI, route user actions through solve/export/import pipelines, surface PySide2 dialogs
- Location: `flame/camera_match_hook.py`
- Contains: Entry point `get_batch_custom_ui_actions()`, VP line UI, preview pipeline, menu action handlers, frame export/capture
- Depends on: forge_core, forge_flame, Flame API (PyClip, PyAction, PyBatch, PySide2)
- Used by: Flame 2026.2.1 batch hook loader
- Purpose: Standalone camera bake/extract scripts executed via `blender --background --python`
- Location: `tools/blender/`
- Contains: `bake_camera.py` (Flame JSON → .blend), `extract_camera.py` (.blend → Flame JSON)
- Depends on: Blender's bpy (mathutils, file I/O)
- Used by: Hook via `forge_flame.blender_bridge` subprocess calls
## Data Flow
## State Management
- VP line endpoints: stored in PySide2 widget during user drawing
- Solver output: held in dict, applied to Action camera on Apply button
- Trace file: written to `/tmp/forge_camera_match_trace.json` per solve, read by diagnostic UI
- Action camera parameters: stored in Flame's Action node (PyAttribute set_value)
- Blender camera metadata: stamped via custom properties (future phase — `forge_bake_action_name`, `forge_bake_camera_name`)
- FBX fixtures: `tests/fixtures/forge_fbx_baked.fbx` (template for writer), `tests/fixtures/forge_fbx_probe.fbx` (live Flame export)
- Menu callbacks captured at hook-registration time; dynamic reload does NOT refresh them
- Module globals DO reload via gc/exec pattern (see `memory/flame_module_reload.md`)
- Requires Flame restart to pick up UI handler changes
## Key Abstractions
- Purpose: Pure 2VP camera calibration from vanishing point lines
- Examples: `forge_core/solver/solver.py:solve_2vp()`, tests in `tests/test_solver.py`
- Pattern: Takes VP lines in image-plane coords, returns focal length + rotation matrix (no Euler, no scale)
- Consumed by: `forge_flame.adapter.solve_for_flame()` which adds Euler decomposition + pixel scaling
- Purpose: Wrap solver output in Flame's conventions (ZYX Euler, pixel-unit depth)
- Examples: `forge_flame/adapter.py`, tests in `tests/test_hook_parity.py`
- Pattern: Line packing (N≥2 lines per VP → LSQ fit), multi-line-to-2-line synthesis for 3-line mode, Euler decomposition
- Consumed by: Hook UI via `_solve_lines()` call
- Purpose: Single-frame (JSON) and multi-frame (FBX) round-trips between Flame Action and JSON/FBX formats
- Examples: `forge_flame/camera_io.py`, `forge_flame/fbx_io.py`
- Pattern: Flame PyAttribute reads/writes wrapped in JSON serialization; FBX routes through ASCII parser
- Consumed by: Hook export/import handlers
- Purpose: Tokenize, parse, and emit ASCII FBX 7.7.0 without external SDK (wheels cp310-only, incompatible with Flame 3.11)
- Examples: `forge_flame/fbx_ascii.py` (tokenizer, recursive-descent parser, template writer), tests in `tests/test_fbx_ascii.py`
- Pattern: Parse → FBXNode tree → camera/AnimCurve extraction; emit via template mutation (inherits Flame's Definitions/Connections)
- Consumed by: `forge_flame.fbx_io` and camera round-trip pipeline
- Purpose: Locate Blender binary, compose CLI args, run bake/extract scripts, surface errors
- Examples: `forge_flame/blender_bridge.py`, tests in `tests/test_blender_bridge.py`
- Pattern: Env override (FORGE_BLENDER_BIN, FORGE_BLENDER_SCRIPTS) → platform defaults → PATH; CLI composition unit-testable
- Consumed by: Hook's export/import handlers
## Entry Points
- Location: `flame/camera_match_hook.py`
- Triggers: Flame loads `/opt/Autodesk/shared/python/camera_match/camera_match_hook.py` on startup
- Responsibilities: Register three menu actions (Open Camera Match on clip, Export/Import Camera on Action)
- Handler: `_launch_camera_match(selection)` (line ~1661)
- Triggers: User right-clicks Clip in Batch → "Camera Match" → "Open Camera Match"
- Responsibilities: Export frame, show PySide2 UI with VP line tool, apply solved camera to Action
- Handler: `_export_camera_to_blender(selection)` (line ~1793)
- Triggers: User right-clicks Action in Batch → "Camera Match" → "Export Camera to Blender"
- Responsibilities: Call `forge_flame.camera_io.export_flame_camera_to_json()`, run Blender bake via subprocess, reveal .blend in file manager
- Handler: `_import_camera_from_blender(selection)` (line ~1958)
- Triggers: User right-clicks Action in Batch → "Camera Match" → "Import Camera from Blender"
- Responsibilities: Run Blender extract via subprocess, read JSON, convert to FBX, call `action.import_fbx()`, create new Action camera
- `tools/blender/bake_camera.py`: Invoked as `blender --background --python -- --in JSON --out .blend`
- `tools/blender/extract_camera.py`: Invoked as `blender --background --python -- --in .blend --out JSON`
## Error Handling
- **Solver robustness:** If VP fit produces negative focal length or degenerate rotation, `solve_2vp()` returns `None`; adapter surfaces as "unable to solve" in hook UI
- **Frame export:** Wiretap CLI failures surfaced as Flame error dialogs with stderr output; image decode failures handled gracefully (passthrough black if color space unknown)
- **Blender subprocess:** Exit code + stderr captured; Flame error dialog shows command line + error text for debugging
- **FBX parsing:** Tokenizer/parser validate structure; malformed FBX raises `ValueError` with line/col context (caught by import handler)
- **Flame API:** PyAttribute operations wrapped in try-catch; graceful fallback (e.g., camera rename collision handled by Flame auto-numbering)
## Cross-Cutting Concerns
- Flame world: Y-up, 1 unit ≈ 1 image pixel, camera at distance h/(2·tan(vfov/2))
- Blender world: Z-up; Flame world is rotated 90° around X-axis to Blender coords
- Rotation: Flame ZYX-with-X,Y-negated (R = Rz(rz) · Ry(-ry) · Rx(-rx)); verified empirically via FBX export (see `memory/flame_rotation_convention.md`)
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, or `.github/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
