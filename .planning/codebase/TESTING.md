# Testing Patterns

**Analysis Date:** 2026-04-19

## Test Framework

**Runner:**
- pytest 9.0.2 (installed, no config file)
- No `pytest.ini`, `setup.cfg`, or `pyproject.toml` configuration
- Tests in `tests/` directory; can be run with `pytest` from repo root

**Run Commands:**
```bash
pytest                              # Run all tests
pytest tests/test_solver.py         # Run specific suite
pytest -v                           # Verbose output
pytest --tb=short                   # Brief traceback format
```

**Assertion Library:**
- pytest's built-in assertions (`assert`, `assert <expr>`)
- `numpy.testing.assert_allclose()` and `np.testing.assert_array_equal()` for numeric/array comparisons
- `math.isclose()` for single-value floating-point comparisons

## Test File Organization

**Location Pattern:**
- Co-located with source: `tests/test_<module_name>.py` parallels `<source_dir>/<module_name>.py`
- Examples:
  - `tests/test_fbx_io.py` tests `forge_flame/fbx_io.py`
  - `tests/test_solver.py` tests `forge_core/solver/solver.py` (and coordinates, math_util)
  - `tests/test_fbx_ascii.py` tests `forge_flame/fbx_ascii.py`

**File Naming:**
- Test files: `test_*.py`
- No conftest.py (each test file is self-contained)
- Utility scripts (not test suites): `verify_flame_yup.py` (manual verification script, not in normal test run)

## Test Structure

**Module Docstring:**
Every test file starts with a docstring explaining:
- What is being tested
- What is deliberately NOT tested (and why)
- Any relevant context (fixture sources, live Flame validation, etc.)

Example from `test_fbx_io.py`:
```python
"""
Unit tests for forge_flame.fbx_io.

The real flame API isn't importable outside Flame, so these tests
exercise fbx_io against duck-typed fakes. The module's own camera
detection is duck-typed (``hasattr`` on position/rotation/fov/focal), so
the fakes only need to match that shape.

What we test:
  1. ``iter_keyframable_cameras`` filters out non-cameras AND the
     built-in ``Perspective`` camera. ...
  2. ``export_action_cameras_to_fbx`` propagates correct kwargs to
     Flame's ``export_fbx``, manages selection ...
  3. ``import_fbx_to_action`` guards on missing files, ...

The live-Flame side — actually calling export_fbx/import_fbx, ... — is
covered manually via the forge-bridge probes ... (see PASSOFF.md).
"""
```

**Test Class Organization:**
- Classes group related test methods: `TestTokenizer`, `TestParser`, `TestExtraction`
- Convention: `Test<Feature>` naming
- Methods are individual test cases: `def test_<behavior>()`

Example from `test_fbx_ascii.py`:
```python
class TestTokenizer:
    """Basic lexical sanity — each token kind, edge cases on numbers,
    comment/whitespace handling."""

    def _kinds(self, text):
        return [t[0] for t in _tokenize(text)]

    def _values(self, text):
        return [t[1] for t in _tokenize(text)]

    def test_empty(self):
        assert _tokenize("") == []

    def test_whitespace_only(self):
        assert _tokenize("   \n\t  \r\n") == []
```

**Grouped Test Hierarchy:**
Tests organized in tiers for complex modules:

From `test_fbx_ascii.py` docstring:
```
Organized in three tiers:
1. Tokenizer — small string snippets exercising each token class.
2. Parser — small FBX-shaped documents covering block structure,
   Properties70 lines, and the ``*N { a: ... }`` array form.
3. Extraction — against real Flame-emitted FBX files in
   ``tests/fixtures/``, checking that known camera values land in v5 JSON.
```

From `test_solver.py` docstring:
```
Tests are structured bottom-up matching the solver pipeline:
  coordinates → line_intersection → focal_length → rotation → full solve
```

## Test Fixtures and Fakes

**In-File Fixture Classes:**
- No external fixture files; fakes defined directly in test module
- Minimal implementations: only include the attributes/methods being tested

Example `_Attr` fake from `test_fbx_io.py`:
```python
class _Attr:
    """Minimal PyAttribute fake: get_value / set_value."""

    def __init__(self, value):
        self._value = value

    def get_value(self):
        return self._value

    def set_value(self, v):
        self._value = v
        return True
```

Example `_Camera` fake from `test_fbx_io.py`:
```python
class _Camera:
    """Minimal PyCoNode fake — has the four duck-typing attrs."""

    def __init__(self, name, position=(0.0, 0.0, 0.0), rotation=(0.0, 0.0, 0.0),
                 fov=40.0, focal=22.0):
        self.name = _Attr(name)
        self.position = _Attr(position)
        self.rotation = _Attr(rotation)
        self.fov = _Attr(fov)
        self.focal = _Attr(focal)
```

**Real Fixture Files:**
- Located in `tests/fixtures/` subdirectory
- Examples:
  - `tests/fixtures/forge_fbx_probe.fbx` — static FBX export (bake_animation=False)
  - `tests/fixtures/forge_fbx_baked.fbx` — animated FBX export with 2-frame keyframes
  - `.fspy` files for camera geometry tests
- Fixture source documented in test module docstring (e.g., "Captured from Flame 2026.2.1 on 2026-04-19")

**Helper Methods:**
- Private methods in test classes start with underscore: `_kinds()`, `_values()`, `_make_buffer()`
- Used for building test inputs or extracting results
- Pattern from `test_image_buffer.py`:
  ```python
  def _make_buffer(self, w, h, header_bytes=0):
      """Build a deterministic GBR buffer where each pixel encodes its
      (row, col) position so flips and channel swaps are visible by eye."""
      arr = np.zeros((h, w, 3), dtype=np.uint8)
      for y in range(h):
          for x in range(w):
              arr[y, x, 0] = (x * 2) % 256
              ...
      return header + arr.tobytes(), arr
  ```

## Mocking Strategy

**Duck-Typing Over Mocking:**
- Flame objects replaced with simple fakes, not mock.Mock
- Fakes have just enough attributes to pass `hasattr()` checks
- Example: `_Action` fake records method calls for assertion
  ```python
  class _Action:
      def __init__(self, nodes):
          self.nodes = list(nodes)
          self.selected_nodes = _Attr([])
          self.export_fbx_calls = []        # Records calls
          self.export_fbx_return = True     # Configurable return
      
      def export_fbx(self, path, **kwargs):
          self.export_fbx_calls.append({"path": path, **kwargs})
          return self.export_fbx_return
  ```

**Monkeypatch (pytest):**
- `monkeypatch` fixture used for environment and module-level substitutions
- Example from `test_blender_bridge.py`:
  ```python
  def test_env_override_wins(self, tmp_path, monkeypatch):
      fake_bin = tmp_path / "blender"
      fake_bin.write_text("#!/bin/sh\necho fake\n")
      fake_bin.chmod(0o755)
      monkeypatch.setenv("FORGE_BLENDER_BIN", str(fake_bin))
      assert resolve_blender_bin() == str(fake_bin)
  ```

**What NOT to Mock:**
- Pure math functions (should return correct values)
- Built-in numpy operations (use real numpy)
- Type conversions and arithmetic
- File operations (use `tmp_path` fixture instead)

## Test Types and Patterns

**Unit Tests (Majority):**
- Isolated function/class behavior
- No Flame binary required
- Fast execution (milliseconds)
- Examples:
  - `test_fbx_ascii.py` — tokenizer, parser, round-trip serialization
  - `test_solver.py` — coordinate transforms, VP fitting, rotation math
  - `test_camera_io.py` — FOV/focal converters

**Parametrized Tests:**
- `@pytest.mark.parametrize` for testing multiple inputs
- Pattern from `test_camera_io.py`:
  ```python
  @pytest.mark.parametrize("focal,film_back", [
      (14.0, 24.0),
      (24.0, 36.0),
      (35.0, 36.0),
      (42.0, 36.0),
      (50.0, 36.0),
      (85.0, 24.0),
      (200.0, 36.0),
      (600.0, 36.0),
  ])
  def test_roundtrip_focal(self, focal, film_back):
      vfov = vfov_deg_from_focal(focal, film_back)
      recovered = focal_from_vfov_deg(vfov, film_back)
      assert math.isclose(recovered, focal, rel_tol=1e-12)
  ```

**Known-Answer Tests (Math):**
- Solver tests use geometrically constructed configurations
- Example from `test_solver.py`:
  ```python
  def test_centre_wide_image(self):
      """Image centre should map to (0, 0) in ImagePlane."""
      ip = px_to_image_plane(960, 540, 1920, 1080)
      np.testing.assert_allclose(ip, [0.0, 0.0], atol=1e-10)
  ```

**Round-Trip Tests (Data Contracts):**
- Verify that forward and inverse operations are exact inverses
- Example from `test_fbx_ascii.py`:
  ```python
  # frame_from_ktime and ktime_from_frame are exact inverses
  def test_roundtrip_fps(self, fps):
      for frame in range(0, 100, 10):
          ktime = ktime_from_frame(frame, fps)
          recovered = frame_from_ktime(ktime, fps)
          assert recovered == frame
  ```

**Live Fixture Tests:**
- Parse real FBX files captured from Flame
- Verify known values (position, rotation, FOV, keyframe counts)
- Example from `test_fbx_ascii.py`:
  ```python
  def test_extraction_static_fbx(self):
      fbx_path = os.path.join(FIXTURE_DIR, "forge_fbx_probe.fbx")
      with open(fbx_path) as f:
          fbx_text = f.read()
      doc = parse_fbx_ascii(fbx_text)
      camera_data = fbx_to_v5_json(doc, "24 fps")
      # Verify known camera values from Flame export
      assert camera_data["position"] == [0, 0, 4747.64]
      assert camera_data["focal_mm"] == pytest.approx(35.0, abs=0.01)
  ```

## Coverage and Gaps

**Test Count:** 264 tests passing (as of 2026-04-19)

**Test Distribution:**
- `test_fbx_ascii.py` — 51 tests (tokenizer, parser, KTime conversion, live fixtures, round-trip)
- `test_fbx_io.py` — 19 tests (Perspective filtering, selection save/restore, error handling)
- `test_solver.py` — ~50 tests (coordinates, line intersection, focal length, rotation, full solve)
- `test_camera_io.py` — 29 tests (FOV/focal converters, inverse property, film back recovery)
- `test_blender_bridge.py` — 23 tests (binary resolution, script path resolution, CLI building)
- `test_image_buffer.py` — ~20 tests (header strip, channel swap, vertical flip, OCIO passthrough)
- `test_blender_roundtrip.py` — 13 tests (axis maps, Euler inverse, bake/extract math)
- `test_cross_validate.py`, `test_hook_parity.py` — ~20 tests (adapter math, axis pairs)

**What's Well Tested:**
- Pure math: solver, coordinates, FOV/focal converters
- Data serialization: FBX ASCII parsing, round-trip
- Flame API adapters (via duck-typing fakes)
- Error handling and edge cases
- Numeric precision and rounding

**What's Intentionally NOT Tested (Per Design):**
- Live Flame execution (export_fbx/import_fbx actually running in Flame)
  - Rationale: Requires Flame binary; separate manual validation done during development
  - Reference: PASSOFF.md documents manual probes on 2026-04-19
- Blender script execution (requires Blender binary)
  - Alternative: `tools/blender/roundtrip_selftest.sh` exercises full pipeline when available
- UI/PySide2 code (camera_match_hook.py window rendering)
  - Reason: Qt/PySide2 not installed in test environment; requires live Flame session
- Subprocess shell execution (reveal_in_file_manager, blender launch)
  - Reason: Platform-specific; best-effort by design

## Common Test Patterns

**Numeric Assertions:**
```python
# Single value, relative tolerance
assert math.isclose(got, 39.59775, abs_tol=1e-4)

# Array comparison with absolute tolerance
np.testing.assert_allclose(ip, [0.0, 0.0], atol=1e-10)

# Array element-wise equality
np.testing.assert_array_equal(out, src)
```

**Error Testing (pytest.raises):**
```python
with pytest.raises(FileNotFoundError, match="Blender binary not found"):
    resolve_blender_bin()
```

**Conditional Skips:**
- Not observed in current test suite; all tests run unconditionally

**Async/Generator Testing:**
- No async code in codebase
- Generators not tested (only used internally in tokenizer)

## Test Data and Constants

**Reference Values from PASSOFF:**
- Sketch camera state: position (0, 0, 4747.64), rotation (0, 0, 0), vfov 40°, 22mm focal, film back from test fixture
- NTSC fps: 23.976 = 24000/1001 (exact rational conversion)
- FBX KTime constant: 46186158000 ticks per second (verified against Autodesk FBX SDK)
- Gimbal lock threshold: 1e-6 (controls switch to gimbal-locked Euler extraction)

**Test Plate Dimensions:**
- Wide image: 1920x1080 (16:9)
- Tall image: 1080x1920 (9:16)
- Square: 1000x1000
- Aspect-specific behavior tested for each

## Import Pattern for Tests

**Standard test file header:**
```python
"""Module docstring explaining what's tested and what's NOT."""

import os
import sys
import pytest

# Add parent dir to sys.path so forge packages are importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Now import what's being tested
from forge_flame.fbx_io import (  # noqa: E402
    DEFAULT_PIXEL_TO_UNITS,
    export_action_cameras_to_fbx,
    iter_keyframable_cameras,
)
```

**Note:** `noqa: E402` silences flake8's "module level import not at top of file" warning — necessary because sys.path manipulation must happen first.

## Test Lifecycle

**Setup/Teardown:**
- pytest fixtures: `tmp_path` for temporary files, `monkeypatch` for env overrides
- No explicit setup/teardown methods in test classes (fixtures handle cleanup)
- Context managers used in tested code (e.g., `_selection_restored`) verify cleanup via call records

**Parametrized Fixture Scope:**
- All tests parameterized with `@pytest.mark.parametrize` have function scope (default)
- No session or module-scoped fixtures

## Running Tests

**From Repository Root:**
```bash
# All tests
pytest

# Single file
pytest tests/test_solver.py

# Single test
pytest tests/test_solver.py::TestCoordinates::test_centre_wide_image

# With verbose output
pytest -v

# Stop after first failure
pytest -x

# Show print statements
pytest -s
```

**Test Count Command:**
```bash
pytest --collect-only -q | tail -1
# Output: 264 tests
```

## Future Test Considerations

**Not Yet Automated:**
- Live Flame export/import round-trip (manual PASSOFF validation)
- Blender addon button click (requires Blender GUI)
- forge-bridge POST endpoint (integration test, separate from unit tests)

**Expansion Opportunities:**
- Performance benchmarks for large FBX files
- Edge cases in KTime conversion for frame rates not in table
- Exotic aspect ratios and resolution combinations

---

*Testing analysis: 2026-04-19*
