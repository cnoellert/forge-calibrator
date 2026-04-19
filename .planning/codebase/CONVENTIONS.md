# Coding Conventions

**Analysis Date:** 2026-04-19

## Naming Patterns

**Files:**
- Module files: lowercase with underscores (e.g., `fbx_ascii.py`, `camera_io.py`, `blender_bridge.py`)
- Test files: `test_<module_name>.py` (e.g., `test_fbx_io.py`, `test_solver.py`)
- Hook entry point: `camera_match_hook.py` for Flame batch hook

**Functions:**
- Snake_case for all functions: `compute_flame_euler_zyx`, `iter_keyframable_cameras`, `px_to_image_plane`, `fit_vp_from_lines`
- Private/internal functions start with underscore: `_tokenize`, `_parse_fbx`, `_ensure_forge_env`, `_selection_restored`
- Predicates: `_is_*` or named directly as boolean (e.g., `gimbal` for gimbal lock condition)

**Variables:**
- Snake_case for all local and module variables: `ktime_per_frame`, `principal_point`, `focal_length`
- Constants: ALL_CAPS with underscores: `FBX_KTIME_PER_SECOND`, `DEFAULT_PIXEL_TO_UNITS`, `AXIS_VECTORS`
- Loop variables: conventional short names (`x`, `y`, `i`, `p0`, `p1`, `vp1`, `vp2`)
- Type hints use full names: `np.ndarray`, `Optional[float]`, `Tuple[float, float, float]`

**Types:**
- Classes use PascalCase: `FBXNode`, `TestTokenizer`, `TestParser`, `_Camera`, `_Action` (fakes are uppercase too)
- Dataclasses and named tuples: PascalCase (e.g., `properties` dicts use lowercase string keys)
- Type aliases: descriptive names like `LinePx = Tuple[Tuple[float, float], Tuple[float, float]]`

## Code Style

**Formatting:**
- Line length: no strict limit observed; files go up to ~120 chars when readability demands
- Indentation: 4 spaces per level (standard Python)
- Blank lines: 1 between functions, 2 between top-level class definitions
- Trailing commas: used in multiline function calls and imports for clarity

**Imports:**
- `from __future__ import annotations` at top of every module file (enables postponed evaluation of type hints)
- Stdlib imports first, then third-party (numpy, opencv, etc.), then local relative imports
- Relative imports use dot notation: `from .math_util import orthogonal_projection_on_line`
- All local imports grouped together after third-party, separated by blank line
- Example from `forge_flame/fbx_io.py`:
  ```python
  from __future__ import annotations
  import os
  from contextlib import contextmanager
  from typing import Optional
  ```

**Linting:**
- No formal linter config (no .eslintrc, .flake8, or pyproject.toml lint section)
- Convention enforced by review: noqa: E402 used in test files when sys.path.insert needed before imports (standard pattern for modifying import path)

## Comments and Documentation

**Module Docstrings:**
- Every module file has a detailed docstring explaining PURPOSE and SCOPE
- Example from `forge_flame/fbx_ascii.py`: 35-line docstring covering "Why this module exists", scope boundaries (cameras only, animation curves only), and key design decisions
- Example from `forge_core/math/rotations.py`: explains the Flame ZYX rotation convention with verification reference, why it lives in forge_core not forge_flame, and which modules re-export it
- Docstrings are extensive and explain the WHY, not just the WHAT

**Function Docstrings:**
- Google-style docstrings with Args, Returns, optional Raises
- Example from `forge_core/solver/solver.py`:
  ```python
  def compute_focal_length(
      vp1: np.ndarray, vp2: np.ndarray, principal_point: np.ndarray
  ) -> Optional[float]:
      """Compute relative focal length from two vanishing points and principal point.
      
      Uses the orthocentre relationship: if P is the principal point and VP1, VP2
      are vanishing points, the focal length f satisfies: ...
      
      Args:
          vp1: First vanishing point in ImagePlane coords [x, y]
          vp2: Second vanishing point in ImagePlane coords [x, y]
          principal_point: Principal point in ImagePlane coords [x, y]
      
      Returns:
          Relative focal length, or None if the VP configuration is degenerate
          (f^2 <= 0).
      """
  ```
- Inline comments explain GOTCHAS and non-obvious decisions
- Example from `forge_flame/fbx_io.py` — explains why Perspective camera is filtered and references external documentation: `see memory/flame_perspective_camera.md`

**Inline Comments:**
- Used for algorithm explanations (e.g., homogeneous line math in `fitting.py`)
- Used for platform/version-specific behavior (e.g., GBR channel reorder in Wiretap buffer)
- Used for referencing external memory/ docs: `see memory/flame_rotation_convention.md`
- Comments explain tricky numeric behavior (e.g., gimbal lock tolerance in `rotations.py`: `cb <= 1e-6`)

## Import Organization

**Standard Order:**
1. `from __future__ import annotations` (always first)
2. Standard library (`sys`, `os`, `json`, `math`, `contextlib`, etc.)
3. Third-party (`numpy`, `pytest`, `cv2`)
4. Local relative imports (`.math_util`, `.coordinates`, etc.)

**Path Aliases:**
- No aliasing used (`import numpy as np` is standard, never custom aliases)
- Relative imports use dot notation, no sys.path manipulation except in entry points
- Exception: Test files use sys.path manipulation to import parent package:
  ```python
  sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
  from forge_flame.fbx_io import ...  # noqa: E402
  ```

## Error Handling

**Patterns:**
- Guard clauses return early with sentinel values (None) rather than raising
  - Example: `compute_focal_length` returns None when f^2 <= 0 (degenerate VP)
  - Example: `fit_vp_from_lines` returns None when VP is at infinity
  - Example: `frame_from_ktime` silently falls back to 24.0 fps for unknown frame rates

- Explicit checks over exceptions when the condition is expected
  - Example: `hasattr(n, attr)` to check for duck-typing attributes rather than try/except
  - Example: `abs(v[2]) < 1e-12` to detect VP at infinity

- Raise on truly exceptional conditions only
  - Flame API returns checked: `export_fbx(...) and not result` raises with context
  - File existence checked before attempting operations
  - Invalid inputs (negative lengths, None where required) raise with clear message

- Context managers for cleanup: `@contextmanager` for save/restore patterns
  - Example: `_selection_restored(action)` saves and restores `action.selected_nodes`

## Type Hints

**Usage:**
- Type hints present on function signatures throughout
- Return types always annotated: `-> Optional[float]`, `-> np.ndarray`, `-> None`
- Parameter types annotated: `vp1: np.ndarray`, `frame: int`, `cam_rot: np.ndarray`
- Generic types use `from typing import Optional, Tuple, Sequence`
- `from __future__ import annotations` allows forward references and cleaner syntax

**Numpy Types:**
- `np.ndarray` for arrays (shape noted in docstring)
- Scalar returns wrapped as float: `return float(deg[0])`
- Type coercion: `int(round(...))` for frame numbers, `float(value)` for return values

## Docstring Structure for Complex Modules

**fbx_ascii.py pattern** (~1500 LOC module):
1. 35-line module docstring covering purpose, architectural decisions, scope boundaries
2. Section headers (=== delimited) for major subsystems: FBX time constants, Tokenizer, Parser, etc.
3. Dataclass definitions with field docstrings
4. Helper functions grouped by functionality
5. Each section is self-contained; internal helper details hidden behind public API

**solver.py pattern** (~400 LOC module):
1. 7-line module docstring with reference paper (Guillou et al.)
2. Module-level constants (e.g., `AXIS_VECTORS` dict)
3. Functions in dependency order: low-level math first, composed functions after
4. Each function fully documented with exact mathematical formula in docstring

## Code Organization Within Files

**Pattern 1: Pure Math (forge_core/math/, forge_core/solver/):**
- Module docstring with algorithm references
- Constants at top (keyed by problem domain)
- Functions in building-block order (low-level → high-level)
- No classes except test fakes

**Pattern 2: Adapters (forge_flame/*.py):**
- Module docstring explaining why it exists and scope boundaries
- Import guards for optional dependencies (e.g., duck-typing checks)
- Context managers for cleanup patterns
- Functions in workflow order (input → processing → output)
- Cross-references to memory/ docs for non-obvious decisions

**Pattern 3: Test Files:**
- Module docstring explaining what's tested and what's NOT tested (important!)
- Imports grouped: pytest, sys/os, then relative imports with noqa: E402
- Test fixtures/fakes defined first (e.g., `_Attr`, `_Camera`, `_Action`)
- Test classes grouped by feature (e.g., `TestTokenizer`, `TestParser`, `TestExtraction`)
- Helper methods prefixed with underscore (e.g., `_kinds`, `_values`, `_make_buffer`)
- Parametrized tests use `@pytest.mark.parametrize` with explicit test case arrays

## Duck Typing

**Pattern:**
- Flame API objects checked via `hasattr()` rather than `isinstance()`
- Example from `fbx_io.py`: `iter_keyframable_cameras` checks `hasattr(n, attr)` for `position`, `rotation`, `fov`, `focal`
- This makes the code unit-testable without importing the real flame module

**Fakes for Testing:**
- Minimal implementations: `_Attr` (just get_value/set_value), `_Camera` (has the four attributes)
- Fakes record call history in lists for assertion: `export_fbx_calls`, `selected_at_call`
- Return values configurable for testing error paths: `export_fbx_return = True`, `import_fbx_return = None`

## Numeric Precision

**Conventions:**
- Float comparisons use `math.isclose(a, b, abs_tol=1e-4)` or `np.testing.assert_allclose(a, b, atol=1e-10)`
- Gimbal lock detection uses `<= 1e-6` threshold
- VP-at-infinity detection uses `< 1e-12` threshold
- Frame rounding: `int(round(...))` to nearest integer

**Comments on Magic Numbers:**
- Every numeric constant with domain meaning documented
- Example: `FBX_KTIME_PER_SECOND = 46186158000` (documented as FBX's fixed internal time resolution)
- Example: gimbal lock tolerance `1e-6` chosen to catch numerical underflow while avoiding false positives

## Module Structure Summary

**forge_core/** — Pure math, no external adapters:
- Every file is numpy-only; safe to import anywhere (Flame, Blender, CLI)
- Solver pipeline organized by abstraction level
- Helpers pulled out when shared (e.g., `fitting.py` shared by adapter and hook)

**forge_flame/** — Flame-specific, duck-typed for testing:
- Every module starts with "Why this module exists" docstring
- Non-Flame-critical logic extracted to forge_core
- Flame API calls guarded by duck-typing, not isinstance checks
- Cross-references to memory/ docs for tricky behaviors

**tests/** — Comprehensive, offline-runnable:
- No Flame binary required; Flame objects mocked
- Test organization mirrors source modules: `test_fbx_io.py` tests `fbx_io.py`
- Fixtures defined in-file, no conftest.py (lightweight, self-contained)
- Each test module has a docstring explaining what's tested and why

---

*Convention analysis: 2026-04-19*
