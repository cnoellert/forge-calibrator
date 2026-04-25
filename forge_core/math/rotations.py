"""
Flame rotation-convention helpers.

Flame's Action camera composes rotations as ``R = Rz(rz) · Ry(-ry) ·
Rx(-rx)`` — ZYX order with X and Y signs negated. Verified 2026-04-16
against the test.fspy fixture; see memory/flame_rotation_convention.md
for the history of getting this right.

For aim-rig cameras the convention differs: Flame's aim-rig
rotation composes as ``R = Rz(-rz) · Ry(-ry) · Rx(-rx)`` — the
SAME matrix-product order as ``compute_flame_euler_zyx`` (Z·Y·X
left-to-right), but with rz ALSO sign-negated (in addition to the
existing rx, ry negations). Verified 2026-04-25 via forge-bridge
live probe of Camera1 + Flame viewport manual-match + empirical
sign/order search; the coupled fix is the L167 roll-Rodrigues
sign in ``rotation_matrix_from_look_at``. See 04.3-SPIKE.md for
the empirical reproduction (1.814°, 1.058°, 1.252° within 0.006°
of viewport ground truth on every axis). The
``compute_flame_euler_xyz`` / ``flame_euler_xyz_to_cam_rot`` pair
below implements that convention. They are ADDITIVE: the existing
``compute_flame_euler_zyx`` / ``flame_euler_to_cam_rot`` pair
stays unchanged because the Free-rig solve path
(forge_flame.adapter) relies on its symmetric pass-through
behaviour. New aim-rig code should import the ``_xyz`` pair;
existing free-rig code keeps importing ``_zyx``. NB: aim-rig
callers must also use the post-Phase-04.3
``rotation_matrix_from_look_at`` (positive roll Rodrigues
sign) — the look-at sign and decomposer convention are coupled.

The "_xyz" name reflects that this is the convention Flame's UI
labels as "Rot XYZ" on aim-rig cameras (verified live via
forge-bridge probe of Camera1's ``rotation_order`` attribute);
internally the matrix product order is the same Z·Y·X as the
free-rig path, only the rz sign differs.

This module lives in forge_core (not forge_flame) because:

  - The math is numpy-only. No flame, no Qt, no Wiretap, no OCIO.
  - Other hosts will need these same helpers to move camera data into
    or out of Flame's coordinate frame (the Blender bake/extract scripts
    being the first case — Blender's Python has numpy but no flame).
  - Keeping the forge_flame package free of pure-math symbols leaves it
    as a thin host-adapter layer, matching the v5 refactor's intent.
  - ``rotation_matrix_from_look_at`` constructs the world matrix from
    aim-rig semantics (position + aim + up + roll) so the FBX parser
    can resolve aim-rig cameras without duplicating the sign convention.

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


def compute_flame_euler_xyz(cam_rot: np.ndarray) -> Tuple[float, float, float]:
    """Decompose a 3x3 cam-to-world rotation into Flame's XYZ-signflip Euler.

    Flame's aim-rig camera composes R as ``Rz(-rz) · Ry(-ry) · Rx(-rx)``:
    the SAME Z·Y·X matrix-product order as ``compute_flame_euler_zyx``
    on the Free-rig path, but with rz ALSO sign-negated (the Free-rig
    convention only negates rx and ry). Substituting α=-rx, β=-ry,
    γ=-rz reduces to a standard ZYX-positive product R = Rz(γ)·Ry(β)·Rx(α);
    extraction is the standard closed-form decomposition with three
    atan2/arcsin lines.

    Verified 2026-04-25 by:
      - forge-bridge live probe of Camera1 (position/aim/up/roll/fov)
      - Flame viewport manual-match to (1.8193°, 1.0639°, 1.2529°)
      - empirical sign/order search in 04.3-SPIKE.md / spike_xyz_final.py
    Hand-decomposing rotation_matrix_from_look_at(Camera1) under this
    convention (after the L167 +roll_deg sign flip) reproduces
    (1.814°, 1.058°, 1.252°) — within 0.006° of Flame viewport truth
    on every axis. Closes the Phase 04.2 ~0.087° ry residual on the
    aim-rig fixture.

    Does NOT modify or replace ``compute_flame_euler_zyx``; the Free-rig
    solve path depends on that pair's symmetric pass-through behaviour
    and is out of scope for this phase. The "_xyz" name reflects
    Flame UI's "Rot XYZ" label on aim-rig cameras; internally the
    product order matches the Free-rig path, only rz's sign differs.

    Returns (rx_deg, ry_deg, rz_deg). Handles gimbal lock (ry = ±90°)
    by pinning rx=0 and recovering rz from the upper-left 2x2 block.

    NB: a previous draft of this function (per the Phase 04.3 plan
    amendment §A) used an X·Y·Z matrix product instead. That draft
    was empirically wrong — scipy's ``xyz`` extrinsic mode on the
    look-at output reproduces the Camera1 hand-decomposed value, and
    extrinsic ``xyz`` is equivalent to applying ``Rz·Ry·Rx`` (Z·Y·X
    product), not ``Rx·Ry·Rz``. The amendment author's interpretation
    of scipy notation was inverted; the original plan's Z·Y·X
    derivation is what reproduces ground truth."""
    cb = np.sqrt(cam_rot[0, 0] ** 2 + cam_rot[1, 0] ** 2)
    gimbal = cb <= 1e-6
    if not gimbal:
        rx = -np.arctan2(cam_rot[2, 1], cam_rot[2, 2])
        ry = -np.arcsin(-cam_rot[2, 0])
        rz = -np.arctan2(cam_rot[1, 0], cam_rot[0, 0])           # SIGN FLIPPED vs _zyx
    else:
        rx = 0.0
        ry = -np.arcsin(-cam_rot[2, 0])
        rz =  np.arctan2(cam_rot[0, 1], cam_rot[1, 1])           # FIRST-ARG SIGN FLIPPED vs _zyx
    deg = np.degrees(np.array([rx, ry, rz]))
    return (float(deg[0]), float(deg[1]), float(deg[2]))


def flame_euler_xyz_to_cam_rot(rx_deg: float, ry_deg: float, rz_deg: float) -> np.ndarray:
    """Compose a 3x3 cam-to-world rotation from Flame's XYZ-signflip Euler.

    Exact inverse of ``compute_flame_euler_xyz``: builds R using
    Flame's aim-rig composition ``R = Rz(-rz) · Ry(-ry) · Rx(-rx)``.
    Same Z·Y·X product order as ``flame_euler_to_cam_rot``; only the
    cz/sz line differs (the rz sign is now negated).

    Used by the aim-rig Flame → Blender bake path (rebuild world
    matrix from stored JSON) and by tests that need to generate
    known-answer rotations under the XYZ-signflip convention.

    Does NOT modify or replace ``flame_euler_to_cam_rot``; the
    Free-rig pipeline keeps the ``_zyx`` pair."""
    rx, ry, rz = np.radians([rx_deg, ry_deg, rz_deg])
    cx, sx = np.cos(-rx), np.sin(-rx)
    cy, sy = np.cos(-ry), np.sin(-ry)
    cz, sz = np.cos(-rz), np.sin(-rz)              # ONLY DIFFERENCE vs flame_euler_to_cam_rot
    Rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    Rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return Rz @ Ry @ Rx


def rotation_matrix_from_look_at(
    position: Tuple[float, float, float] | np.ndarray,
    aim: Tuple[float, float, float] | np.ndarray,
    up: Tuple[float, float, float] | np.ndarray,
    roll_deg: float,
) -> np.ndarray:
    """Build a 3x3 cam-to-world rotation matrix from aim-rig semantics.

    Flame's Action aim/target rig stores orientation as (position, aim,
    up, roll) rather than as a direct Euler rotation. On export_fbx the
    camera's Lcl Rotation is zero and the orientation is emitted as a
    LookAtProperty connection to an aim Null plus UpVector and Roll
    Properties70 values. This helper reconstructs the equivalent
    cam-to-world rotation so it can be decomposed to Flame's ZYX Euler
    via ``compute_flame_euler_zyx``.

    Construction (standard look-at, right-handed):
      forward = normalize(aim - position)       # view direction, world-space
      right   = normalize(cross(forward, up))   # orthogonalised world right
      up_cam  = cross(right, forward)           # orthonormal up in camera frame
      # Roll rotates right/up_cam about the forward axis.
      R = [right | up_cam | -forward]           # columns; col 2 = -forward

    The returned matrix is in the SAME cam-to-world convention that
    ``flame_euler_to_cam_rot`` produces, so feeding it to
    ``compute_flame_euler_zyx`` yields the exact (rx_deg, ry_deg, rz_deg)
    triple to write into the v5 JSON ``rotation_flame_euler`` field. See
    memory/flame_rotation_convention.md for the sign-flip history.

    Args:
        position: Camera world position (x, y, z).
        aim: World-space point the camera is looking at.
        up: World-space up reference (will be orthogonalised against forward;
            magnitude is irrelevant — only direction matters).
        roll_deg: Rotation about the forward axis in degrees. Sign convention
            verified against live Camera1 probe 2026-04-23 (aim-rig fixture).

    Returns:
        3x3 cam-to-world rotation matrix (np.ndarray, float64).

    Raises:
        ValueError: If |aim - position| <= 1e-6 ("aim-rig resolve: forward
            vector degenerate — aim coincident with position"). The 1e-6
            threshold matches the existing gimbal-lock tolerance in
            ``compute_flame_euler_zyx`` to keep the numeric regime
            consistent across the rotation pipeline.
        ValueError: If |cross(forward, up)| <= 1e-6 ("aim-rig resolve: up
            vector parallel to view direction — cannot orthogonalise").
    """
    p = np.asarray(position, dtype=float).reshape(3)
    a = np.asarray(aim, dtype=float).reshape(3)
    u = np.asarray(up, dtype=float).reshape(3)

    forward_raw = a - p
    fwd_norm = float(np.linalg.norm(forward_raw))
    if fwd_norm <= 1e-6:
        raise ValueError(
            f"aim-rig resolve: forward vector degenerate — "
            f"|aim - position| = {fwd_norm!r} fails >= 1e-6 threshold "
            f"(aim coincident with position)"
        )
    forward = forward_raw / fwd_norm

    right_raw = np.cross(forward, u)
    right_norm = float(np.linalg.norm(right_raw))
    if right_norm <= 1e-6:
        raise ValueError(
            f"aim-rig resolve: up vector parallel to view direction — "
            f"|cross(forward, up)| = {right_norm!r} fails >= 1e-6 "
            f"threshold (cannot orthogonalise up against forward)"
        )
    right = right_raw / right_norm
    up_cam = np.cross(right, forward)  # already unit-length (orthonormal)

    # Apply roll about the forward axis to right and up_cam.
    # Rodrigues' rotation: v' = v*cos(t) + (k x v)*sin(t) + k*(k.v)*(1-cos(t))
    # with k = forward and (k.right) = (k.up_cam) = 0, so the third term drops.
    # Sign: Flame's Roll property is the clockwise roll as seen looking
    # down -forward (through the lens), which corresponds to rotating
    # right/up_cam about +forward by +roll_deg. Sign verified 2026-04-25
    # against Camera1 forge-bridge probe + Flame viewport manual-match,
    # decomposed under the new X·Y·Z _xyz convention (see Phase 04.3
    # CONTEXT.md, 04.3-SPIKE.md, and 04.3-01-PLAN-AMENDMENT.md). The
    # look-at roll sign and the decomposer convention are coupled — the
    # additive _xyz pair in this file (compute_flame_euler_xyz /
    # flame_euler_xyz_to_cam_rot) is what consumes look-at output for
    # aim-rig cameras. Free-rig callers (test_blender_roundtrip etc.)
    # pass roll=0 and are unaffected by this sign at zero. Pre-Phase-04.3
    # the sign was -roll_deg, paired with the legacy _zyx decomposer.
    theta = np.radians(float(roll_deg))
    ct, st = np.cos(theta), np.sin(theta)
    right_rolled = right * ct + np.cross(forward, right) * st
    up_rolled    = up_cam * ct + np.cross(forward, up_cam) * st

    # Column convention: col 0 = right, col 1 = up_cam, col 2 = -forward.
    # Matches flame_euler_to_cam_rot's output (see docstring).
    R = np.column_stack((right_rolled, up_rolled, -forward))
    return R
