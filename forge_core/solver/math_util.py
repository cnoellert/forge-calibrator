"""
Core math utilities for vanishing point camera calibration.

Line intersection, orthogonal projection, orthocentre computation.
"""

import numpy as np
from typing import Optional


def line_intersection(
    p1: np.ndarray, p2: np.ndarray, p3: np.ndarray, p4: np.ndarray
) -> Optional[np.ndarray]:
    """Compute intersection of two lines defined by point pairs.

    Line 1 passes through p1 and p2.
    Line 2 passes through p3 and p4.

    Args:
        p1, p2: Points defining line 1 (2D arrays)
        p3, p4: Points defining line 2 (2D arrays)

    Returns:
        Intersection point as np.ndarray [x, y], or None if lines are parallel.
    """
    # Using the determinant method
    x1, y1 = p1[0], p1[1]
    x2, y2 = p2[0], p2[1]
    x3, y3 = p3[0], p3[1]
    x4, y4 = p4[0], p4[1]

    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)

    if abs(denom) < 1e-12:
        return None  # parallel or coincident

    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom

    x = x1 + t * (x2 - x1)
    y = y1 + t * (y2 - y1)

    return np.array([x, y])


def orthogonal_projection_on_line(
    point: np.ndarray, line_p1: np.ndarray, line_p2: np.ndarray
) -> np.ndarray:
    """Project a point orthogonally onto a line defined by two points.

    Args:
        point: The point to project (2D)
        line_p1, line_p2: Two points defining the line (2D)

    Returns:
        The projected point on the line as np.ndarray [x, y]
    """
    d = line_p2 - line_p1
    d_sq = np.dot(d, d)

    if d_sq < 1e-24:
        return line_p1.copy()

    t = np.dot(point - line_p1, d) / d_sq
    return line_p1 + t * d


def orthocentre(
    k: np.ndarray, l: np.ndarray, m: np.ndarray
) -> Optional[np.ndarray]:
    """Compute the orthocentre of a triangle defined by three vertices.

    The orthocentre is the intersection of the altitudes. For vanishing point
    triangles, this gives the principal point of the camera.

    Args:
        k, l, m: Triangle vertices as 2D arrays

    Returns:
        Orthocentre point as np.ndarray [x, y], or None if degenerate.
    """
    a, b = k[0], k[1]
    c, d = l[0], l[1]
    e, f = m[0], m[1]

    N = b * c + d * e + f * a - c * f - b * e - a * d

    if abs(N) < 1e-12:
        return None  # degenerate triangle

    x = (
        (d - f) * b * b
        + (f - b) * d * d
        + (b - d) * f * f
        + a * b * (c - e)
        + c * d * (e - a)
        + e * f * (a - c)
    ) / N

    y = (
        (e - c) * a * a
        + (a - e) * c * c
        + (c - a) * e * e
        + a * b * (f - d)
        + c * d * (b - f)
        + e * f * (d - b)
    ) / N

    return np.array([x, y])
