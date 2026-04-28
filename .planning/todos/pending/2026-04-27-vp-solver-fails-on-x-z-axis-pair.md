---
created: 2026-04-27T20:00:00Z
title: VP solver fails on X-axis + Z-axis vanishing-point pair (Y omitted)
area: solver
files:
  - forge_core/solver/solver.py        # solve_2vp entry point
  - forge_core/solver/coordinates.py   # axis-pair → rotation logic
  - forge_flame/adapter.py              # solve_for_flame adapter
  - flame/camera_match_hook.py:1502    # _solve_lines call site (line-tool UI)
---

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
