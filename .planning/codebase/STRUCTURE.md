# Codebase Structure

**Analysis Date:** 2026-04-19

## Directory Layout

```
forge-calibrator/
├── flame/                         # Flame batch hook entry point
│   ├── __init__.py
│   ├── camera_match_hook.py       # Main hook (~93KB) — entry point
│   ├── scale_picker_dialog.py     # Forge-themed PySide6 scale picker (quick-260501-knl)
│   └── rotation_diagnostic.py     # Legacy diagnostic script (review separately)
│
├── forge_core/                    # Host-agnostic math and image modules
│   ├── __init__.py
│   ├── solver/
│   │   ├── __init__.py
│   │   ├── solver.py              # 2VP/1VP camera calibration (solve_2vp, solve_1vp)
│   │   ├── fitting.py             # VP line fitting (LSQ via numpy.linalg)
│   │   ├── coordinates.py         # Pixel ↔ ImagePlane coordinate conversion
│   │   └── math_util.py           # Line intersection, orthogonal projection, etc.
│   ├── math/
│   │   ├── __init__.py
│   │   └── rotations.py           # Euler decomposition (Flame ZYX-with-negation)
│   ├── colour/
│   │   ├── __init__.py
│   │   └── ocio.py                # OCIO pipeline, config resolution
│   └── image/
│       ├── __init__.py
│       └── buffer.py              # Image decoding, OCIO application, color space mapping
│
├── forge_flame/                   # Flame-specific adapters (Wiretap, FBX, camera I/O)
│   ├── __init__.py
│   ├── adapter.py                 # Solver adapter (packing, Euler decomposition, tracing)
│   ├── wiretap.py                 # Wiretap SDK wrappers (frame reader, color space)
│   ├── camera_io.py               # Single-frame Flame camera ↔ JSON I/O
│   ├── fbx_io.py                  # Multi-frame Action ↔ FBX I/O
│   ├── fbx_ascii.py               # ASCII FBX 7.7.0 tokenizer, parser, writer (1231 LOC)
│   ├── blender_bridge.py          # Blender binary/script resolution, subprocess CLI
│   └── templates/
│       └── camera_baked.fbx       # Flame-emitted FBX template (payload mutation target)
│
├── tools/
│   └── blender/                   # Standalone Blender CLI scripts (subprocess targets)
│       ├── bake_camera.py         # JSON → .blend (runs inside Blender)
│       ├── extract_camera.py      # .blend → JSON (runs inside Blender)
│       ├── roundtrip_selftest.sh  # End-to-end validation script
│       └── sample_camera.json     # Test fixture
│
├── tests/                         # pytest suite (264 tests)
│   ├── __init__.py
│   ├── test_solver.py             # Solver math (coordinates, line intersection, focal length, rotation)
│   ├── test_hook_parity.py        # Adapter parity vs. solver; Flame Euler invariants
│   ├── test_cross_validate.py     # Solver vs. fSpy known-answer
│   ├── test_image_buffer.py       # Image decode, OCIO pipeline
│   ├── test_camera_io.py          # Flame camera ↔ JSON converters
│   ├── test_blender_roundtrip.py  # Flame → Blender → Flame, Euler/FOV invariants
│   ├── test_blender_bridge.py     # Blender binary/script resolution, CLI composition
│   ├── test_fbx_io.py             # FBX export/import wrapper (Perspective filtering, selection)
│   ├── test_fbx_ascii.py          # FBX ASCII tokenizer, parser, writer (51 tests)
│   ├── verify_flame_yup.py        # Manual rotation verification (not automated)
│   └── fixtures/
│       ├── forge_fbx_baked.fbx    # Multi-frame template (used by fbx_ascii writer)
│       └── forge_fbx_probe.fbx    # Live Flame export (test fixture)
│
├── matchbox/                      # Matchbox-related (deprecated, not active)
├── .planning/
│   └── codebase/                  # Generated documentation (this directory)
├── install.sh                     # Installer (copies hook + forge_core + forge_flame + tools/blender to /opt)
├── PASSOFF.md                     # Session history + data contracts + known issues
└── .gitignore
```

## Directory Purposes

**flame/**
- Purpose: Flame batch hook entry point; user-facing UI and orchestration
- Contains: Main hook file (1697 LOC), legacy diagnostic scripts
- Key files: `camera_match_hook.py` is the Flame-loaded hook; exports `get_batch_custom_ui_actions()` for menu registration
- Entry point called by: Flame 2026.2.1 batch hook loader

**forge_core/**
- Purpose: Host-agnostic, purely mathematical building blocks; reusable by any tool (trafFIK, notebooks, external clients)
- Contains: Vanishing-point solver, coordinate transforms, line fitting, image decode, OCIO pipeline
- Key files: `solver/solver.py` (2VP/1VP solve), `solver/fitting.py` (LSQ VP fit), `math/rotations.py` (Euler decomposition), `colour/ocio.py` (color pipeline), `image/buffer.py` (image decode)
- Dependencies: numpy only (test-safe, Blender-safe, external-tool-safe)

**forge_flame/**
- Purpose: Flame-specific adapters; bridges Flame API surface to forge_core
- Contains: Solver adapter, Wiretap frame reader, camera I/O (JSON + FBX), FBX ASCII parser/writer, Blender orchestration
- Key files: `adapter.py` (packing + Euler), `wiretap.py` (frame decode), `camera_io.py` (single-frame JSON), `fbx_io.py` (FBX wrapper), `fbx_ascii.py` (parser/writer), `blender_bridge.py` (subprocess)
- Dependencies: forge_core, Flame SDK (Wiretap optional)
- Not importable from: trafFIK or non-Flame tools

**tools/blender/**
- Purpose: Standalone scripts executed inside Blender via subprocess
- Contains: Camera bake (JSON → .blend), camera extract (.blend → JSON), end-to-end selftest
- Key files: `bake_camera.py` (run target for export), `extract_camera.py` (run target for import), `roundtrip_selftest.sh` (E2E validation)
- Execution: Via `blender --background --python <script> -- <args>`
- Dependencies: Only bpy (Blender-bundled); no numpy, no forge imports

**tests/**
- Purpose: pytest suite (264 tests covering all layers)
- Contains: Unit tests for solver, adapter, image processing, FBX parsing, Blender orchestration
- Key files: `test_solver.py` (80+ tests, bottom-up solver pipeline), `test_fbx_ascii.py` (51 tests, tokenizer/parser/writer), `test_hook_parity.py` (adapter invariants), `test_blender_roundtrip.py` (Flame→Blender→Flame)
- Fixtures: `fixtures/forge_fbx_baked.fbx` (template for writer), `fixtures/forge_fbx_probe.fbx` (live Flame export)

**.planning/codebase/**
- Purpose: Generated analysis documents for other GSD tools
- Contents: ARCHITECTURE.md, STRUCTURE.md, CONVENTIONS.md, TESTING.md (if quality focus), CONCERNS.md (if concerns focus)

## Key File Locations

**Entry Points:**
- `flame/camera_match_hook.py` (1697 LOC): Flame hook loaded on startup; exports `get_batch_custom_ui_actions()` dict with three menu actions
- `tools/blender/bake_camera.py`: Blender CLI target for export pipeline
- `tools/blender/extract_camera.py`: Blender CLI target for import pipeline

**Configuration:**
- `install.sh`: Installer; copies hook + forge_core + forge_flame + tools/blender to `/opt/Autodesk/shared/python/` and verifies dependencies
- `PASSOFF.md`: Session history, data contracts, known issues (v4→v6.2)
- `forge_flame/templates/camera_baked.fbx`: ASCII FBX template (payload mutation target for writer)

**Core Logic by Layer:**

*Solver layer (pure math):*
- `forge_core/solver/solver.py` — `solve_2vp()`, `solve_1vp()`, focal length + rotation computation
- `forge_core/solver/fitting.py` — `fit_vp_from_lines()` (LSQ vanishing point)
- `forge_core/solver/coordinates.py` — pixel ↔ ImagePlane conversion

*Adapter layer (Flame conventions):*
- `forge_flame/adapter.py` — `solve_for_flame()` (packing, Euler, tracing)
- `forge_flame/wiretap.py` — `extract_frame_bytes()`, `get_clip_colour_space()`
- `forge_flame/camera_io.py` — `export_flame_camera_to_json()`, `import_json_to_flame_camera()`
- `forge_flame/fbx_io.py` — `export_fbx_to_action()`, `import_fbx_to_action()`
- `forge_flame/fbx_ascii.py` — `parse_fbx_ascii()`, `fbx_to_v5_json()`, `v5_json_to_fbx()`, `emit_fbx_ascii()`
- `forge_flame/blender_bridge.py` — `resolve_blender_bin()`, `run_bake_camera()`, `run_extract_camera()`

*Hook orchestration:*
- `flame/camera_match_hook.py` — `_launch_camera_match()`, `_export_camera_to_blender()`, `_import_camera_from_blender()`

**Testing:**
- `tests/test_solver.py` — Solver bottom-up tests
- `tests/test_hook_parity.py` — Adapter vs. solver parity
- `tests/test_fbx_ascii.py` — FBX ASCII parsing/writing (51 tests)
- `tests/test_camera_io.py` — Flame camera I/O
- `tests/test_blender_roundtrip.py` — Full Flame→Blender→Flame invariants

## Naming Conventions

**Files:**
- Modules: `snake_case.py` (e.g., `camera_io.py`, `fbx_ascii.py`)
- Test files: `test_<module>.py` matching source module (e.g., `test_fbx_ascii.py` tests `fbx_ascii.py`)
- Scripts: `snake_case.py` (e.g., `bake_camera.py`, `extract_camera.py`)
- Hooks/entry points: `<name>_hook.py` (e.g., `camera_match_hook.py`)
- Installers: `install.sh`

**Directories:**
- Package directories: `snake_case` (e.g., `forge_core`, `forge_flame`, `tools`)
- Subpackages: `snake_case` (e.g., `forge_core/solver`, `forge_core/colour`, `forge_core/image`)
- Test directory: `tests/`
- Configuration/templates: `<name>/` or `templates/`

**Functions:**
- Public API: `snake_case` (e.g., `solve_for_flame()`, `export_flame_camera_to_json()`)
- Private (module-scoped): `_snake_case` (e.g., `_solve_lines()`, `_parse_fbx_ascii()`)
- Internal helpers: `__snake_case` (rare; prefer single underscore)

**Variables:**
- Local: `snake_case` (e.g., `vp1_lines`, `focal_length`, `cam_rot`)
- Constants: `UPPER_CASE` (e.g., `DEFAULT_CAMERA_DISTANCE_SCALE`, `SENSOR_MM`)
- Class attributes: `snake_case`

**Types:**
- Classes: `PascalCase` (e.g., `FBXNode`, `OcioPipeline`)
- Type aliases: `snake_case` (implicit via comment or variable name context)

## Where to Add New Code

**New feature (e.g., third VP mode):**
- Primary solver code: `forge_core/solver/solver.py`
- Adapter integration: `forge_flame/adapter.py`
- Hook UI handler: `flame/camera_match_hook.py` (new menu action or mode toggle)
- Tests: `tests/test_solver.py` (new solver test) + `tests/test_hook_parity.py` (adapter parity)

**New component/module (e.g., new color space handler):**
- Implementation: `forge_core/colour/<module>.py` if host-agnostic, or `forge_flame/<module>.py` if Flame-specific
- Test file: `tests/test_<module>.py`
- Re-export: Add to `forge_core/__init__.py` or `forge_flame/__init__.py` if public API

**Utilities (e.g., matrix math helper):**
- Shared solver utilities: `forge_core/solver/math_util.py`
- Shared rotation utilities: `forge_core/math/rotations.py`
- Flame-specific utilities: `forge_flame/adapter.py` or new `forge_flame/<domain>.py`

**Blender-side code:**
- New Blender CLI scripts: `tools/blender/<name>.py`
- Script dependencies: Keep imports limited to bpy (no numpy, no forge imports)
- Invocation: Via `forge_flame.blender_bridge` (register new function if subprocess pattern needed)

**Tests for new code:**
- Unit tests: Co-locate in `tests/test_<module>.py` matching the source module
- Fixtures: Store in `tests/fixtures/` if reused across multiple tests
- Naming: `test_<function>()` or `test_<Class>_<method>()` for class methods

## Special Directories

**forge_core/solver:**
- Purpose: Vanishing-point camera calibration (pure numpy, no host bindings)
- Generated: No
- Committed: Yes
- Imports: numpy only

**forge_flame/templates:**
- Purpose: FBX templates used by fbx_ascii writer
- Generated: No (manually captured from live Flame probes)
- Committed: Yes
- Contents: `camera_baked.fbx` (ASCII FBX 7.7.0 with Definitions + Connections structure)

**tests/fixtures:**
- Purpose: Test data (FBX files, JSON samples)
- Generated: Partially (some via live Flame exports)
- Committed: Yes
- Contents: `forge_fbx_baked.fbx`, `forge_fbx_probe.fbx`, sample `.json` files

**tools/blender:**
- Purpose: Standalone scripts deployed to Flame install location
- Generated: No
- Committed: Yes
- Deployed to: `/opt/Autodesk/shared/python/tools/blender/` by `install.sh`

**.planning/codebase/**
- Purpose: Generated analysis documents
- Generated: Yes (via `/gsd-map-codebase` agent)
- Committed: Yes (committed so orchestrator can load them)
- Contents: ARCHITECTURE.md, STRUCTURE.md, CONVENTIONS.md, TESTING.md, CONCERNS.md (focus-dependent)

## Deployment Structure

**Development (from repo root):**
```
forge-calibrator/
├── forge_core/        # importable as `forge_core`
├── forge_flame/       # importable as `forge_flame`
├── tools/blender/     # resolvable by blender_bridge via ../tools/blender
└── flame/
    └── camera_match_hook.py  # symlinked or copied to Flame batch hook path
```

**Installation (target: /opt/Autodesk/shared/python/):**
```
/opt/Autodesk/shared/python/
├── forge_core/              # sibling of camera_match/
├── forge_flame/             # sibling of camera_match/
├── tools/blender/           # sibling of camera_match/
└── camera_match/
    ├── __init__.py          # stub (module stability)
    ├── camera_match_hook.py # copy of flame/camera_match_hook.py
    └── (other legacy scripts)
```

**Runtime import paths:**
- Dev: Hook's `_ensure_forge_core_on_path()` adds repo root to `sys.path`
- Install: Hook's parent (`/opt/Autodesk/shared/python/`) already on path (Flame's loader)
- Blender scripts: Standalone; don't import forge modules (CLI args are the interface)

---

*Structure analysis: 2026-04-19*
