"""
Flame rotation-convention helpers.

Flame's Action camera composes rotations as ``R = Rz(rz) · Ry(-ry) ·
Rx(-rx)`` — ZYX order with X and Y signs negated. Verified 2026-04-16
against the test.fspy fixture; see memory/flame_rotation_convention.md
for the history of getting this right.

This module lives in forge_core (not forge_flame) because:

  - The math is numpy-only. No flame, no Qt, no Wiretap, no OCIO.
  - Other hosts will need these same helpers to move camera data into
    or out of Flame's coordinate frame (the Blender bake/extract scripts
    being the first case — Blender's Python has numpy but no flame).
  - Keeping the forge_flame package free of pure-math symbols leaves it
    as a thin host-adapter layer, matching the v5 refactor's intent.

forge_flame.adapter re-exports both names so existing imports
(``from forge_flame.adapter import compute_flame_euler_zyx``) stay
working. New code should import from here directly.
"""

from __future__ import annotations

from typing import Tuple

import numpy as np


def compute_flame_euler_zyx(cam_rot: np.ndarray) -> Tuple[float, float, float]:
    """Decompose a 3x3 cam-to-world rotation into Flame's Euler convention.

    Flame's Action camera internally composes R as ``Rz(rz) · Ry(-ry) ·
    Rx(-rx)``: ZYX order with X and Y signs negated. Substituting
    α=-rx, β=-ry, γ=rz reduces to the standard ZYX-positive decomposition
    and the extraction collapses to three atan2/arcsin lines.

    Verified 2026-04-16 against the test.fspy fixture: these angles
    align the rendered surface to the wall to single-degree precision,
    where the previously-used XYZ convention left a ~13° Z residual.

    Returns (rx_deg, ry_deg, rz_deg), the exact triple to set on
    ``PyAction.cam_node.rotation``. Handles gimbal lock (ry = ±90°) by
    pinning rx=0 and deriving rz from the upper-left 2x2 block."""
    cb = np.sqrt(cam_rot[0, 0] ** 2 + cam_rot[1, 0] ** 2)
    gimbal = cb <= 1e-6
    if not gimbal:
        rx = -np.arctan2(cam_rot[2, 1], cam_rot[2, 2])
        ry = -np.arcsin(-cam_rot[2, 0])
        rz = np.arctan2(cam_rot[1, 0], cam_rot[0, 0])
    else:
        rx = 0.0
        ry = -np.arcsin(-cam_rot[2, 0])
        rz = np.arctan2(-cam_rot[0, 1], cam_rot[1, 1])
    deg = np.degrees(np.array([rx, ry, rz]))
    return (float(deg[0]), float(deg[1]), float(deg[2]))


def flame_euler_to_cam_rot(rx_deg: float, ry_deg: float, rz_deg: float) -> np.ndarray:
    """Compose a 3x3 cam-to-world rotation from Flame's Euler triple.

    Exact inverse of ``compute_flame_euler_zyx``: builds R using Flame's
    internal composition ``R = Rz(rz) · Ry(-ry) · Rx(-rx)``. Given any
    (rx, ry, rz) that came out of the decompose, this returns the same
    rotation matrix that went in.

    Used by the Flame → Blender bake path (rebuild world matrix from
    stored JSON) and by tests that need to generate known-answer
    rotations without round-tripping through solve_2vp."""
    rx, ry, rz = np.radians([rx_deg, ry_deg, rz_deg])
    cx, sx = np.cos(-rx), np.sin(-rx)
    cy, sy = np.cos(-ry), np.sin(-ry)
    cz, sz = np.cos(rz),  np.sin(rz)
    Rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    Rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return Rz @ Ry @ Rx
