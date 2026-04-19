"""
Flame ↔ Blender camera round-trip fidelity test.

Motivation (see PASSOFF.md v5 "Sketch: Flame ↔ Blender camera round-trip"):
the bake (Flame → Blender) and extract (Blender → Flame) scripts haven't
been written yet. This test proves the *math* those scripts will share
is correct end-to-end, so when the Blender-side Python is filled in it
just has to call `mathutils.Matrix` equivalents of what's tested here.

Pipeline we validate:

    Flame JSON
      -> cam_rot           via flame_euler_to_cam_rot
      -> M_flame = T @ R   (4x4 world matrix, Y-up)
      -> M_blender = R_Y2Z @ M_flame          # bake: left-mul Rx(+90°)
      -> M_flame_back = R_Y2Z.T @ M_blender   # extract: left-mul Rx(-90°)
      -> decompose M_flame_back -> position, cam_rot
      -> compute_flame_euler_zyx(cam_rot) -> (rx, ry, rz)

Assert: recovered position and Euler triple match the input to tight
double-precision tolerance.

Both Flame and Blender cameras look down their local -Z axis, so the
world-up swap is a pure left-multiplication — no right-side camera-local
correction. This is what makes the bake a single matrix op.

Test cameras: identity-at-origin (trivial baseline), pure yaw (world-up
axis exercised), translated+rotated (all three Eulers + non-zero
translation). No near-gimbal case — Euler decomposition at ry = ±90°
is genuinely lossy and that's documented behaviour of
compute_flame_euler_zyx, not a round-trip failure.
"""

import math
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from forge_flame.adapter import (  # noqa: E402
    compute_flame_euler_zyx,
    flame_euler_to_cam_rot,
)


# =============================================================================
# Blender bake / extract — pure-numpy stand-ins for the scripts that will
# eventually run inside Blender via `mathutils.Matrix`. Math is identical;
# only the matrix type differs.
# =============================================================================


def _rx_90() -> np.ndarray:
    """4x4 rotation: Flame world (Y-up) -> Blender world (Z-up). +90° about X."""
    c, s = math.cos(math.radians(90)), math.sin(math.radians(90))
    return np.array([
        [1, 0,  0, 0],
        [0, c, -s, 0],
        [0, s,  c, 0],
        [0, 0,  0, 1],
    ])


def _pack(position: np.ndarray, cam_rot: np.ndarray) -> np.ndarray:
    """Build 4x4 world matrix from translation + 3x3 rotation."""
    M = np.eye(4)
    M[:3, :3] = cam_rot
    M[:3, 3] = position
    return M


def _unpack(M: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Split 4x4 into (position, 3x3 rotation)."""
    return M[:3, 3].copy(), M[:3, :3].copy()


def bake_flame_to_blender(position: list, rotation_flame_euler: list) -> np.ndarray:
    """Simulate what bake_camera.py will do inside Blender.

    Flame frame (Y-up) world matrix -> Blender frame (Z-up) world matrix
    via a single left-multiplication by Rx(+90°). Returns the 4x4
    cam-to-world matrix that would get assigned to `cam.matrix_world`
    in Blender."""
    cam_rot = flame_euler_to_cam_rot(*rotation_flame_euler)
    M_flame = _pack(np.asarray(position, dtype=float), cam_rot)
    return _rx_90() @ M_flame


def extract_blender_to_flame(M_blender: np.ndarray) -> tuple[list, tuple[float, float, float]]:
    """Simulate what extract_camera.py will do inside Blender.

    Blender cam.matrix_world -> Flame JSON (position, rotation_flame_euler).
    Inverse of bake_flame_to_blender: left-multiply by Rx(-90°), then
    decompose."""
    M_flame = _rx_90().T @ M_blender
    position, cam_rot = _unpack(M_flame)
    rotation_flame_euler = compute_flame_euler_zyx(cam_rot)
    return position.tolist(), rotation_flame_euler


# =============================================================================
# Known-answer cameras
# =============================================================================


CAMERAS = [
    # label,            position,                rotation_flame_euler (deg)
    ("identity_at_origin",  [0.0, 0.0, 0.0],         [0.0,  0.0, 0.0]),
    ("pure_yaw_30",         [0.0, 0.0, 0.0],         [0.0, 30.0, 0.0]),
    ("translated_rotated",  [100.0, 200.0, 5000.0],  [-5.0, 15.0, 2.0]),
]


# =============================================================================
# Round-trip tests
# =============================================================================


class TestRoundTrip:
    """Flame JSON -> bake -> extract -> Flame JSON matches input."""

    @pytest.mark.parametrize("label,position,rotation", CAMERAS,
                             ids=[c[0] for c in CAMERAS])
    def test_position_preserved(self, label, position, rotation):
        M_blender = bake_flame_to_blender(position, rotation)
        pos_out, _ = extract_blender_to_flame(M_blender)
        np.testing.assert_allclose(pos_out, position, atol=1e-9,
            err_msg=f"position drifted on round-trip for {label}")

    @pytest.mark.parametrize("label,position,rotation", CAMERAS,
                             ids=[c[0] for c in CAMERAS])
    def test_rotation_preserved(self, label, position, rotation):
        M_blender = bake_flame_to_blender(position, rotation)
        _, rot_out = extract_blender_to_flame(M_blender)
        np.testing.assert_allclose(rot_out, rotation, atol=1e-9,
            err_msg=f"rotation drifted on round-trip for {label}")


# =============================================================================
# Axis-map sanity: prove Rx(+90°) is the right swap
# =============================================================================


class TestAxisMap:
    """Spot-check the Y-up -> Z-up map PASSOFF.md claims: it should carry
    Flame's +Y (up) to Blender's +Z (up), and Flame's +Z (toward camera)
    to Blender's -Y (behind camera)."""

    def test_flame_y_maps_to_blender_z(self):
        # Point at Flame (0, 1, 0) — "up one unit".
        p_flame = np.array([0.0, 1.0, 0.0, 1.0])
        p_blender = _rx_90() @ p_flame
        np.testing.assert_allclose(p_blender[:3], [0.0, 0.0, 1.0], atol=1e-12)

    def test_flame_z_maps_to_blender_neg_y(self):
        # Point at Flame (0, 0, 1) — "toward camera by one unit".
        p_flame = np.array([0.0, 0.0, 1.0, 1.0])
        p_blender = _rx_90() @ p_flame
        np.testing.assert_allclose(p_blender[:3], [0.0, -1.0, 0.0], atol=1e-12)

    def test_flame_x_unchanged(self):
        p_flame = np.array([1.0, 0.0, 0.0, 1.0])
        p_blender = _rx_90() @ p_flame
        np.testing.assert_allclose(p_blender[:3], [1.0, 0.0, 0.0], atol=1e-12)


# =============================================================================
# Helper sanity: flame_euler_to_cam_rot is the true inverse of
# compute_flame_euler_zyx
# =============================================================================


class TestEulerHelperInverse:
    """flame_euler_to_cam_rot and compute_flame_euler_zyx must be exact
    inverses for any non-gimbal input."""

    @pytest.mark.parametrize("rot", [c[2] for c in CAMERAS],
                             ids=[c[0] for c in CAMERAS])
    def test_euler_matrix_roundtrip(self, rot):
        R = flame_euler_to_cam_rot(*rot)
        rot_recovered = compute_flame_euler_zyx(R)
        np.testing.assert_allclose(rot_recovered, rot, atol=1e-9)

    def test_matrix_is_rotation(self):
        # Determinant +1, orthonormal — no scale or reflection snuck in.
        R = flame_euler_to_cam_rot(-5.0, 15.0, 2.0)
        np.testing.assert_allclose(R @ R.T, np.eye(3), atol=1e-12)
        assert abs(np.linalg.det(R) - 1.0) < 1e-12
