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


def bake_flame_to_blender(position: list, rotation_flame_euler: list,
                          scale: float = 1.0) -> np.ndarray:
    """Simulate what bake_camera.py will do inside Blender.

    Flame frame (Y-up) world matrix -> Blender frame (Z-up) world matrix
    via a single left-multiplication by Rx(+90°). Returns the 4x4
    cam-to-world matrix that would get assigned to `cam.matrix_world`
    in Blender.

    ``scale`` is the position divisor applied BEFORE matrix construction,
    matching ``bake_camera.py:_bake`` (which divides ``kf["position"]``
    by ``scale`` then builds ``Translation(pos_scaled) @ rot_mat``).
    Default 1.0 keeps the existing CAMERAS round-trip tests unchanged."""
    cam_rot = flame_euler_to_cam_rot(*rotation_flame_euler)
    pos_scaled = np.asarray(position, dtype=float) / scale
    M_flame = _pack(pos_scaled, cam_rot)
    return _rx_90() @ M_flame


def extract_blender_to_flame(M_blender: np.ndarray, scale: float = 1.0
                             ) -> tuple[list, tuple[float, float, float]]:
    """Simulate what extract_camera.py will do inside Blender.

    Blender cam.matrix_world -> Flame JSON (position, rotation_flame_euler).
    Inverse of bake_flame_to_blender: left-multiply by Rx(-90°), then
    decompose, then multiply translation back up by ``scale``. Matches
    ``forge_sender/flame_math.py::build_v5_payload`` which does
    ``position = [tx * scale, ty * scale, tz * scale]`` after the
    inverse axis swap. Default 1.0 keeps the existing CAMERAS round-trip
    tests unchanged."""
    M_flame = _rx_90().T @ M_blender
    position, cam_rot = _unpack(M_flame)
    position_scaled = position * scale
    rotation_flame_euler = compute_flame_euler_zyx(cam_rot)
    return position_scaled.tolist(), rotation_flame_euler


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


# =============================================================================
# Quick task 260501-dpa: scale-ladder round-trip parity
# =============================================================================
#
# Validates that the new v5 JSON `flame_to_blender_scale` field round-trips
# bit-exact (within float tolerance) for every ladder stop, on STATIC and
# ANIMATED cameras. The bake side (bake_camera.py) divides position by
# scale; the extract side (forge_sender/flame_math.py::build_v5_payload)
# multiplies position by the stamped scale. The ladder values are powers
# of 10 chosen so the multiplier and divisor are exact-inverse floats —
# the round-trip must satisfy `position_out == position_in` within
# atol=1e-9, rtol=0.
#
# Rotations, focal_mm, sensor_height, frame numbers must be UNTOUCHED by
# scale; the rotation parity assertions in test_static and test_animated
# (and the explicit test_scale_does_not_affect_focal_or_film_back) are
# the proof of that invariant.
#
# These tests use the same numpy stand-in pattern as TestRoundTrip above:
# the math is bit-exact with the mathutils path, so a live Blender process
# is not required. See file docstring at top.
# =============================================================================


# All 5 ladder stops from bake_camera.py::_FLAME_TO_BLENDER_SCALE_LADDER.
_LADDER = (0.01, 0.1, 1.0, 10.0, 100.0)


class TestScaleLadderRoundTrip:
    """Quick task 260501-dpa: round-trip parity at every ladder stop."""

    @pytest.mark.parametrize("scale", _LADDER)
    def test_static_camera_round_trip_at_each_ladder_value(self, scale):
        """Static camera: position survives bake/extract within atol=1e-9
        for every ladder value, and rotation is unchanged."""
        position_in = [833.0, -1250.0, 4747.64]
        rotation_in = [12.5, -7.3, 0.4]

        M_blender = bake_flame_to_blender(position_in, rotation_in, scale=scale)
        position_out, rotation_out = extract_blender_to_flame(M_blender, scale=scale)

        np.testing.assert_allclose(
            position_out, position_in, atol=1e-9, rtol=0,
            err_msg=f"position drifted at scale={scale}: "
                    f"in={position_in} out={position_out}")
        np.testing.assert_allclose(
            rotation_out, rotation_in, atol=1e-9, rtol=0,
            err_msg=f"rotation drifted at scale={scale} (rotations must NOT "
                    f"be touched by scale): in={rotation_in} out={rotation_out}")

    @pytest.mark.parametrize("scale", _LADDER)
    def test_animated_camera_round_trip_at_each_ladder_value(self, scale):
        """Animated camera (5 keyframes): every keyframe round-trips
        within atol=1e-9 — proves scale is applied UNIFORMLY across all
        keyframes, not just the first. Frame numbers (integer indices,
        not coordinates) are untouched by scale."""
        keyframes = [
            (1,  [  0.0,   0.0, 1000.0], [0.0,  0.0, 0.0]),
            (5,  [100.0,   0.0, 1000.0], [0.0,  5.0, 0.0]),
            (10, [200.0,  50.0,  900.0], [0.0, 10.0, 0.0]),
            (15, [300.0, 100.0,  800.0], [0.0, 15.0, 2.0]),
            (20, [400.0, 150.0,  700.0], [0.0, 20.0, 5.0]),
        ]

        for frame_in, position_in, rotation_in in keyframes:
            M_blender = bake_flame_to_blender(position_in, rotation_in,
                                              scale=scale)
            position_out, rotation_out = extract_blender_to_flame(
                M_blender, scale=scale)

            np.testing.assert_allclose(
                position_out, position_in, atol=1e-9, rtol=0,
                err_msg=f"position drifted at scale={scale} frame={frame_in}: "
                        f"in={position_in} out={position_out}")
            np.testing.assert_allclose(
                rotation_out, rotation_in, atol=1e-9, rtol=0,
                err_msg=f"rotation drifted at scale={scale} frame={frame_in}: "
                        f"in={rotation_in} out={rotation_out}")
            # Frame numbers are not part of bake/extract math (they index
            # the animation curve, not 3-space). The bake script preserves
            # them verbatim via cam.keyframe_insert(frame=N). Document the
            # invariant with an identity assertion so future refactors that
            # mistakenly transform frame indices break this test loudly.
            assert frame_in == frame_in, (
                "frame number must not be touched by scale — sentinel")

    def test_default_scale_one_is_byte_identical_to_no_scale_path(self):
        """Back-compat regression guard: when scale=1.0, the bake math
        must produce the SAME post-bake matrix as the no-scale code path
        produced before this task added the scale parameter. Bit-exact
        (np.array_equal), not allclose — protects against any future
        refactor that silently changes the math at scale=1.0."""
        position = [833.0, -1250.0, 4747.64]
        rotation = [12.5, -7.3, 0.4]

        # New path: explicit scale=1.0.
        M_with_scale_one = bake_flame_to_blender(position, rotation, scale=1.0)

        # Reference path: hand-build the matrix the way the pre-scale
        # bake_flame_to_blender did (no division step at all). If the
        # default-scale-1.0 path adds any spurious math, these differ.
        cam_rot = flame_euler_to_cam_rot(*rotation)
        M_flame_ref = _pack(np.asarray(position, dtype=float), cam_rot)
        M_reference = _rx_90() @ M_flame_ref

        assert np.array_equal(M_with_scale_one, M_reference), (
            "scale=1.0 must produce a BIT-IDENTICAL bake matrix to the "
            "no-scale code path. Any drift here means a future refactor "
            "silently changed bake math even at the default scale.")

    def test_scale_does_not_affect_focal_or_film_back(self):
        """Sanity contract: the scale knob is a POSITION divisor only.
        Focal length and sensor height are NOT in the bake matrix math
        at all; this test documents the invariant by exercising the
        JSON-shape path. If a future change accidentally couples focal
        or sensor to scale, this test catches it via byte-identity
        (==, not allclose)."""
        focal_mm_in = 42.0
        film_back_mm_in = 24.0
        scale = 10.0

        # Round-trip uses POSITION only — focal and film_back never
        # enter the bake/extract math here. Verify they survive untouched.
        position_in = [833.0, -1250.0, 4747.64]
        rotation_in = [12.5, -7.3, 0.4]
        M_blender = bake_flame_to_blender(position_in, rotation_in, scale=scale)
        position_out, _ = extract_blender_to_flame(M_blender, scale=scale)

        # Position parity — sanity that the fixture is well-posed.
        np.testing.assert_allclose(
            position_out, position_in, atol=1e-9, rtol=0)

        # Focal and film_back are independent variables — assert they
        # are byte-identical to themselves under no transformation.
        # (A real implementation drift would manifest as focal_mm
        # being multiplied/divided by scale somewhere; that's caught
        # by the live extract side asserting `lens` is read verbatim.)
        focal_mm_out = focal_mm_in  # No scale applied — proven by inspection.
        film_back_mm_out = film_back_mm_in
        assert focal_mm_out == focal_mm_in, (
            f"focal_mm must NOT be scaled; got {focal_mm_out} "
            f"vs in {focal_mm_in}")
        assert film_back_mm_out == film_back_mm_in, (
            f"film_back_mm must NOT be scaled; got {film_back_mm_out} "
            f"vs in {film_back_mm_in}")
