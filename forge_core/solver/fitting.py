"""
Vanishing-point fitting helpers. Pure numpy, no Flame / no Qt.

Two small functions we pulled out of the hook's inline solver so trafFIK
and the new forge_flame.adapter can share the same LSQ math:

    fit_vp_from_lines(lines_px) -> (vp_x, vp_y) | None
        Least-squares vanishing point from N≥2 lines in pixel coords.
        Reduces exactly to 2-line intersection when N=2, so call sites
        don't need separate 2-line and 3-line code paths.

    line_to_vp_residual_px(p0, p1, vp) -> float
        Perpendicular pixel distance from VP to the infinite line through
        p0 and p1. Zero = the user line extension hits VP exactly. Useful
        for drawing per-line residual labels in a 3-line UI: a large
        number means "this line is lying to the solver."

Why here and not in math_util.py: these are *solver-facing* helpers
(they build inputs the rest of the solver consumes), not general line /
point geometry. math_util.py stays free of fitting concerns.
"""

from __future__ import annotations

from typing import Optional, Sequence, Tuple
import numpy as np


LinePx = Tuple[Tuple[float, float], Tuple[float, float]]


def fit_vp_from_lines(lines_px: Sequence[LinePx]) -> Optional[Tuple[float, float]]:
    """Least-squares vanishing point from N≥2 lines.

    Each line is ``((x0, y0), (x1, y1))`` in pixel coordinates. Each line
    contributes a homogeneous constraint ``L_i · v = 0`` with
    ``L_i = (a, b, c)`` normalised to unit ``(a, b)`` length so all lines
    weight equally. The VP is the homogeneous point ``v`` minimising
    ``sum((L_i · v)^2)`` — i.e. the smallest right-singular vector of the
    stacked constraint matrix.

    Returns the dehomogenised pixel coordinates, or None when the VP is at
    infinity (all input lines truly parallel in the image).

    With exactly 2 lines the LSQ fit sits *exactly* on both lines, so this
    is interchangeable with a 2-line intersection for N=2. At N≥3 it
    averages over the extra constraints, producing a VP that minimises
    total perpendicular error.
    """
    M = []
    for (p0, p1) in lines_px:
        x0, y0 = float(p0[0]), float(p0[1])
        x1, y1 = float(p1[0]), float(p1[1])
        # Homogeneous line through (x0,y0,1) and (x1,y1,1): cross product.
        a = y0 - y1
        b = x1 - x0
        c = x0 * y1 - x1 * y0
        n = np.hypot(a, b) or 1.0
        M.append([a / n, b / n, c / n])
    mat = np.asarray(M, dtype=float)
    _, _, Vt = np.linalg.svd(mat)
    v = Vt[-1]
    if abs(v[2]) < 1e-12:
        return None  # VP at infinity — lines are actually parallel
    return (float(v[0] / v[2]), float(v[1] / v[2]))


def line_to_vp_residual_px(
    p0: Sequence[float], p1: Sequence[float], vp: Sequence[float],
) -> float:
    """Perpendicular pixel distance from VP to the infinite line through p0,p1.

    Signed→absolute. When the line, extended both directions, passes
    exactly through VP, this returns 0. A 10-pixel result means the line's
    infinite extension misses VP by 10 pixels perpendicular.

    Pairs with ``fit_vp_from_lines`` for UIs that want to tell the user
    which of their N lines is disagreeing most with the LSQ fit.
    """
    x0, y0 = float(p0[0]), float(p0[1])
    x1, y1 = float(p1[0]), float(p1[1])
    a = y0 - y1
    b = x1 - x0
    c = x0 * y1 - x1 * y0
    n = np.hypot(a, b) or 1.0
    return abs(a * vp[0] + b * vp[1] + c) / n
