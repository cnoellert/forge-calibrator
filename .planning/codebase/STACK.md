# Technology Stack

**Analysis Date:** 2026-04-19

## Languages

**Primary:**
- Python 3.11.5 - Flame 2026.2.1 bundles this; the hook and all production code targets 3.11
- Python 3.12+ - Supported for testing and development (test suite runs on both 3.11 and 3.12)
- Bash - Installation and utility scripts (`install.sh`)

## Runtime

**Primary Host:**
- Flame 2026.2.1 - VFX compositor where the Camera Match hook is installed and executed
  - Bundles Python 3.11.5
  - Includes PySide6 for UI widgets
  - Includes PyOpenColorIO (Autodesk ACES 2.0 config)
  - Includes Wiretap SDK for media access

**Secondary Hosts:**
- macOS/Linux development machines - For testing and development with pytest

## Package Managers

**Runtime:**
- conda (forge environment) - Creates an isolated Python 3.11 environment with:
  - `numpy` - Math solver, coordinate transforms, matrix operations
  - `opencv-python` (cv2) - GUI overlay rendering, image buffer operations
  - `PyOpenColorIO` - NOT installed in forge env; sourced from Flame's bundled Python instead (version conflict risk if both installed)

**Build/Test:**
- pytest - Framework for 264 unit tests covering solver math, FBX I/O, hook parity, adapter math

**Installation:**
- rsync or cp - For syncing production code to `/opt/Autodesk/shared/python/`

## Frameworks

**Core Frameworks:**
- PySide6 - UI toolkit for the Camera Match line-drawing window (bundled with Flame)

**Testing:**
- pytest - Test runner and assertion library
- Python standard `unittest.mock` - Mock objects for Flame API simulation

## Key Dependencies

**Critical (forge environment):**
- numpy - Solver math: 2VP intersection, FOV/focal conversion, rotation composition (Euler ZYX), matrix transforms.
- opencv-python (cv2) - GUI overlay rendering in `camera_match_hook.py`; frame preview/annotation on the VP line tool window

**Flame-bundled (NOT to be installed in forge):**
- PyOpenColorIO - OCIO pipeline for ACES 2.0 colour management (preview tonemapping, DisplayViewTransform)
- Wiretap SDK - Single-frame media extraction from clips; colour-space tagging lookup

## Configuration

**Environment Variables:**
- `FORGE_ENV` - Path to conda forge environment; defaults to `$HOME/miniconda3/envs/forge` if unset (used by `install.sh`)

**Runtime Paths (Hard-coded):**
- `/opt/Autodesk/wiretap/tools/current/wiretap_rw_frame` - CLI for single-frame reads (version-safe symlink)
- `/opt/Autodesk/wiretap/tools/current/python` - Wiretap Python SDK path
- `/opt/Autodesk/colour_mgmt/configs/flame_configs/*/aces2.0_config/config.ocio` - OCIO config (glob-resolved, auto-tracks Flame upgrades)
- `/opt/Autodesk/python/*/lib/python3.11/site-packages/PyOpenColorIO` - Flame's bundled OCIO (glob-resolved)

**Installation Paths (Hard-coded):**
- `/opt/Autodesk/shared/python/camera_match/` - Hook installation target
- `/opt/Autodesk/shared/python/forge_core/` - Host-agnostic library installation
- `/opt/Autodesk/shared/python/forge_flame/` - Flame-specific adapters installation

**Colour Management:**
- Flame ACES 2.0 config - Preview DisplayViewTransform (RRT + ODT) for soft highlight rolloff on bright plates
- sRGB display target - Standard output for preview

## Build & Deployment

**Build Tools:**
- `install.sh` - Bash installer with preflight checks for:
  - Forge conda env and Python 3.11
  - numpy + opencv-python availability
  - Wiretap CLI presence and executability
  - Flame-bundled PyOpenColorIO
  - OCIO aces2.0_config availability

**Deployment:**
- Target: `/opt/Autodesk/shared/python/` (sibling directory layout)
- Copies: `camera_match/`, `forge_core/`, `forge_flame/`
- Stub `__init__.py` in camera_match to prevent Flame's namespace-package loader drift
- __pycache__ purged post-install to prevent stale bytecode

**CI/CD:**
- None detected; pytest suite runs locally on developer machines

## Platform Requirements

**Development:**
- macOS or Linux
- Flame 2026.2.1 with Wiretap SDK
- Python 3.11 or 3.12
- conda with forge environment initialized
- Pytest for test execution

**Production (Inside Flame):**
- Flame 2026.2.1 (locked; older versions untested; newer versions may have API changes)
- `/opt/Autodesk/wiretap/tools/current/` - Wiretap installation
- `/opt/Autodesk/colour_mgmt/configs/flame_configs/` - OCIO config directory
- Forge conda environment on the same machine as Flame

---

*Stack analysis: 2026-04-19*
