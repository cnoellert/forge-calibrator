# Codebase Structure

**Analysis Date:** 2026-04-19

## Directory Layout

```
forge-calibrator/
├── flame/                         # Flame batch hook entry point
│   ├── __init__.py
│   ├── camera_match_hook.py       # Main hook (~93KB) — entry point
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
├── forge_flame/                   # Flame-specific adapters (Wiretap, solver-to-Flame)
│   ├── __init__.py
│   ├── adapter.py                 # Solver adapter (packing, Euler decomposition, tracing)
│   └── wiretap.py                 # Wiretap SDK wrappers (frame reader, color space)
│
├── tools/                         # Dev-time utilities (fSpy parser)
│   └── fspy_import.py             # fSpy project file parser (developer utility)
│
├── tests/                         # pytest suite (~191 tests post quick-260505-tb3)
│   ├── __init__.py
│   ├── test_solver.py             # Solver math (coordinates, line intersection, focal length, rotation)
│   ├── test_hook_parity.py        # Adapter parity vs. solver; Flame Euler invariants
│   ├── test_cross_validate.py     # Solver vs. fSpy known-answer
│   ├── test_image_buffer.py       # Image decode, OCIO pipeline
│   ├── test_camera_match_hook.py  # Hook scope predicates, picker, helpers
│   └── verify_flame_yup.py        # Manual rotation verification (not automated)
│
├── matchbox/                      # Matchbox-related (deprecated, not active)
├── .planning/
│   └── codebase/                  # Generated documentation (this directory)
├── install.sh                     # Installer (copies hook + forge_core + forge_flame to /opt)
├── PASSOFF.md                     # Session history + data contracts + known issues
└── .gitignore
```

## Directory Purposes

**flame/**
- Purpose: Flame batch hook entry point; user-facing UI and orchestration
- Contains: Main hook file (~2611 LOC post-strip), legacy diagnostic scripts
- Key files: `camera_match_hook.py` is the Flame-loaded hook; exports `get_batch_custom_ui_actions()` for menu registration (single action: Open Camera Calibrator)
- Entry point called by: Flame 2026.2.1 batch hook loader

**forge_core/**
- Purpose: Host-agnostic, purely mathematical building blocks; reusable by any tool (trafFIK, notebooks, external clients)
- Contains: Vanishing-point solver, coordinate transforms, line fitting, image decode, OCIO pipeline
- Key files: `solver/solver.py` (2VP/1VP solve), `solver/fitting.py` (LSQ VP fit), `math/rotations.py` (Euler decomposition), `colour/ocio.py` (color pipeline), `image/buffer.py` (image decode)
- Dependencies: numpy only (test-safe, Blender-safe, external-tool-safe)

**forge_flame/**
- Purpose: Flame-specific adapters; bridges Flame API surface to forge_core
- Contains: Solver adapter, Wiretap frame reader
- Key files: `adapter.py` (packing + Euler decomposition), `wiretap.py` (frame decode + colour-space lookup)
- Dependencies: forge_core, Flame SDK (Wiretap optional)
- Not importable from: trafFIK or non-Flame tools
- History: pre-quick-260505-tb3 also contained camera_io / fbx_io / fbx_ascii / blender_bridge for the Flame↔Blender round-trip; that surface migrated to forge-blender Phase 6

**tests/**
- Purpose: pytest suite (~191 tests post quick-260505-tb3, covering surviving layers)
- Contains: Unit tests for solver, adapter, image processing, hook scope/picker logic
- Key files: `test_solver.py` (80+ tests, bottom-up solver pipeline), `test_hook_parity.py` (adapter invariants), `test_camera_match_hook.py` (hook helpers + picker)
- Fixtures: removed in quick-260505-tb3 along with the FBX/Blender test surface

**.planning/codebase/**
- Purpose: Generated analysis documents for other GSD tools
- Contents: ARCHITECTURE.md, STRUCTURE.md, CONVENTIONS.md, TESTING.md (if quality focus), CONCERNS.md (if concerns focus)

## Key File Locations

**Entry Points:**
- `flame/camera_match_hook.py` (~2611 LOC post-strip): Flame hook loaded on startup; exports `get_batch_custom_ui_actions()` returning the FORGE > Camera > Open Camera Calibrator menu

**Configuration:**
- `install.sh`: Installer; copies hook + forge_core + forge_flame to `/opt/Autodesk/shared/python/` and verifies dependencies (also self-heals stale Matchbox-era + Blender-era artifacts)
- `PASSOFF.md`: Session history, data contracts, known issues (v4→v6.2)

**Core Logic by Layer:**

*Solver layer (pure math):*
- `forge_core/solver/solver.py` — `solve_2vp()`, `solve_1vp()`, focal length + rotation computation
- `forge_core/solver/fitting.py` — `fit_vp_from_lines()` (LSQ vanishing point)
- `forge_core/solver/coordinates.py` — pixel ↔ ImagePlane conversion

*Adapter layer (Flame conventions):*
- `forge_flame/adapter.py` — `solve_for_flame()` (packing, Euler, tracing)
- `forge_flame/wiretap.py` — `extract_frame_bytes()`, `get_clip_colour_space()`

*Hook orchestration:*
- `flame/camera_match_hook.py` — `_launch_camera_match()` (sole user-facing handler post quick-260505-tb3)

**Testing:**
- `tests/test_solver.py` — Solver bottom-up tests
- `tests/test_hook_parity.py` — Adapter vs. solver parity
- `tests/test_camera_match_hook.py` — Hook scope predicates, picker dialog, helpers

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

**tests/fixtures (removed in quick-260505-tb3):**
- Pre-strip housed `forge_fbx_baked.fbx`, `forge_fbx_probe.fbx`, etc. — all FBX fixtures supported the Flame↔Blender round-trip flow that left calibrator. Directory is gone.

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
└── flame/
    └── camera_match_hook.py  # symlinked or copied to Flame batch hook path
```

**Installation (target: /opt/Autodesk/shared/python/):**
```
/opt/Autodesk/shared/python/
├── forge_core/              # sibling of camera_match/
├── forge_flame/             # sibling of camera_match/
└── camera_match/
    ├── __init__.py          # stub (module stability)
    ├── camera_match_hook.py # copy of flame/camera_match_hook.py
    └── (other legacy scripts)
```

**Runtime import paths:**
- Dev: Hook's `_ensure_forge_core_on_path()` adds repo root to `sys.path`
- Install: Hook's parent (`/opt/Autodesk/shared/python/`) already on path (Flame's loader)
- Blender scripts: REMOVED in quick-260505-tb3 — calibrator no longer ships Blender-side code

---

*Structure analysis: 2026-04-19*
