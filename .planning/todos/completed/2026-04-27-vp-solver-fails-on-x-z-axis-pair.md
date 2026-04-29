---
created: 2026-04-27T20:00:00Z
resolved: 2026-04-28T23:50:00Z
status: obsoleted_by_two_fixes
title: VP solver fails on X-axis + Z-axis vanishing-point pair (Y omitted)
area: solver
resolved_commits:
  - 1412555  # restore cam.target_mode.set_value(False) — Target-rig regression in calibrator apply
  - 32c7bfc  # _plane_basis returns +missing_axis (calibrator overlay third-axis arrow direction)
files:
  - forge_core/solver/solver.py        # solve_2vp entry point
  - forge_core/solver/coordinates.py   # axis-pair → rotation logic
  - forge_flame/adapter.py              # solve_for_flame adapter
  - flame/camera_match_hook.py:1502    # _solve_lines call site (line-tool UI)
---

## Resolution (2026-04-28)

**Not a solver bug.** Live testing on portofino at HEAD `32c7bfc` with VP1=-X, VP2=-Z confirmed: the solver produces a correctly-oriented upright Y-up camera (rotation `(27.86, -23.88, 0.49)`, position with positive y, dropped triad showing green +Y handle pointing UP through the applied camera).

The original "X+Z fails" report was the visual stacking of two unrelated regressions on the flame-01 cold-install session:

1. **Layer-4 Target-rig regression (closed by `1412555`)** — every calibrator-applied camera was being created in Target-rig mode, with `position`/`rotation`/`fov` interpreted relative to an aim target rather than as absolute world transforms. This silently produced wildly wrong cameras for any VP setup, anti-cyclic or otherwise. The X+Z case was just the most visually obvious because the user happened to test it.

2. **Calibrator overlay third-axis arrow direction (closed by `32c7bfc`)** — `_plane_basis` returned `cross(a, b)` for the third-axis preview vector, but the label downstream hardcoded `+missing_axis`. On anti-cyclic letter pairs (X-Z, Y-X, Z-Y) the cross gives `-missing_axis` so the arrow drew opposite to its label. This made the calibrator preview LOOK wrong on X+Z even when the underlying solver math was correct. The label-vs-direction mismatch is what created the perception of "X+Z is broken at the math level."

The solver's own world-axis math (`forge_core/solver/solver.py:axis_assignment_matrix`) is RH-self-consistent (`det(R @ A) = +1` for all valid input pairs) and produces correct upright cameras even on anti-cyclic VP pairs. Don't refactor it.

Closing this todo as obsoleted. The detailed reasoning chain (LH-cross hypothesis tested and rejected; stale `/tmp/forge_camera_match_trace.json` reads led to a misdiagnosis cycle) is captured in `memory/flame_calibrator_overlay_axis_label_vs_cross_sign.md`.

---

## Original problem (kept for context)


## Problem

Reported by user 2026-04-27 during flame-01 cold-install verification:
**"the VP solver seems to be failing on X and Z pairs"**.

Interpretation: when the artist marks vanishing-point lines for the X
axis and Z axis (and omits Y, which is the conventional vertical axis
in Flame world space), the solver fails to produce a usable camera. The
ground-plane two-axis case (X+Z, no vertical reference) is one of the
two most common 2VP scenarios in real artist plates — alongside Y+Z
for street-corner / building-elevation plates.

User-visible symptom shape unknown (no error dialog content captured
yet). Possible failure modes:

- Solver returns `None` from `solve_2vp` and the UI surfaces "unable
  to solve"
- Solver returns a degenerate camera with NaN/inf in position or
  rotation
- Solver returns a numerically valid but geometrically wrong camera
  (focal length flipped, rotation 180° off, etc.)

## Diagnosis (current understanding)

The 2VP solver in `forge_core/solver/solver.py` should be axis-symmetric
in principle — given any two of (X, Y, Z) lines, it computes camera
focal length + rotation from the two vanishing points + image center.
The math doesn't intrinsically prefer Y as the vertical reference.

However, there's likely an axis-orientation assumption baked into the
adapter (`forge_flame/adapter.py`'s `solve_for_flame`) or the
coordinate-frame logic (`forge_core/solver/coordinates.py`) that
implicitly treats the third axis as vertical. If the user marks X+Z
without Y, the third (synthesized) axis would be Y — but the math may
hard-code Y as up rather than treating "the omitted axis" as up.

**What we don't know yet:**

- Which two of (X, Y, Z) drop-downs the artist selected for their
  reference lines.
- Whether the failure is a hard error (solver returns None) or a
  silent geometric regression (camera applied but wrong).
- Whether other axis pairs (X+Y, Y+Z) work correctly on the same
  plate — this would localize the bug to "X+Z specifically" vs
  "any pair without Y".

## Reproduction (placeholder — needs user clarification)

1. Open a plate with visible X-axis and Z-axis edges (e.g., a
   ground-plane shot of a road or floor, no clear vertical column).
2. In the Camera Match line tool, mark VP lines for X and Z only
   (no Y lines).
3. Click Apply Camera.
4. Observe: solver fails / produces wrong camera / surfaces error.

## Next steps

1. **Clarify with user**: get the exact axis assignment used (which
   dropdown values for line 1 and line 2 did the artist pick?), the
   plate dimensions, and the failure shape (dialog text? wrong camera?
   silent failure?).
2. **Reproduce in test fixture**: construct a synthetic 2VP plate with
   known X+Z geometry (no Y reference) and run `solve_2vp` directly
   to see if the math layer fails or just the adapter glue.
3. **Audit the adapter**: read `forge_flame/adapter.py:solve_for_flame`
   for any hard-coded Y-up assumption that breaks X+Z input.
4. **Add coverage**: the test suite covers Y+Z and X+Y common cases;
   if X+Z is broken, an X+Z regression test belongs in
   `tests/test_solver.py` next to the existing axis-pair coverage.

## Scope

The Camera Match line tool is the primary user-facing solve path —
not a 04.4 deliverable but the foundation everything else builds on.
A solver bug that produces a wrong camera silently violates the
project's Core Value as stated in CLAUDE.md ("The solved camera must
be geometrically faithful to the plate"). Treat as high-priority for
the next solve cycle.
