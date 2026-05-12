# Testing Patterns

**Analysis Date:** 2026-05-12

## Test framework

- **Runner:** pytest (no `pytest.ini` / `pyproject.toml` test config in repo)
- **Layout:** `tests/test_<area>.py` mirrors feature areas under `forge_core/`, `forge_flame/`, and the hook

**Commands:**

```bash
pytest
pytest tests/test_solver.py -q
pytest --tb=short
```

**Assertions:** `assert`, `numpy.testing.assert_allclose`, `math.isclose` where appropriate.

## Current test modules (post Phase A2 strip)

| Module | Focus |
|--------|--------|
| `tests/test_solver.py` | VP geometry, fitting, `solve_2vp` / `solve_1vp`, coordinates |
| `tests/test_rotations.py` | Euler / matrix conventions |
| `tests/test_hook_parity.py` | `forge_flame.adapter` vs solver outputs |
| `tests/test_cross_validate.py` | Cross-checks vs external references (e.g. fSpy) |
| `tests/test_image_buffer.py` | Decode paths, OCIO-related buffer behaviour |
| `tests/test_camera_match_hook.py` | Hook helpers, picker predicates, mocks of Flame-shaped objects |
| `tests/verify_flame_yup.py` | Manual script — not part of default `pytest` collection |

**Approximate collection size:** 191 tests (`pytest --collect-only -q` from the `forge` env).

## Module docstring convention

Each test file opens with **what is tested** and **what is not** (e.g. no live Flame, no Wiretap binary in CI).

**Example pattern** (from `test_solver.py` — illustrative):

```text
Tests are structured bottom-up matching the solver pipeline:
  coordinates → line_intersection → focal_length → rotation → full solve
```

## Fakes and duck typing

Flame types are not imported in CI. Tests use minimal objects with `hasattr`-compatible shapes (see `test_camera_match_hook.py` for batch/action fakes).

Live Flame behaviour (Wiretap reads, real `export_fbx` / `import_fbx`, batch menu dispatch) is **manual** or optional dev workflows — not asserted in pytest. Optional **forge-bridge** probes are a dev-time convenience only; they are not a test prerequisite for this repo.

## Historical note

`tests/test_fbx_io.py`, `tests/test_fbx_ascii.py`, `tests/test_blender_bridge.py`, and related fixtures were removed with the Blender/FBX strip (quick-260505-tb3). Old excerpts in prior revisions of this document referred to that suite (~264 collected tests). PASSOFF.md and git history preserve the v6.x testing story.

## Numeric tolerances

- Use documented `atol` / `rtol` for geometry; align with project norms in CONVENTIONS.md (e.g. `1e-10` class for solver, looser for image pipeline).

## What pytest does not cover

- End-to-end VP UI inside a running Flame session
- `wiretap_rw_frame` against production MXF on disk
- OCIO config discovery on arbitrary Flame installs

---

*Testing patterns doc refreshed 2026-05-12.*
