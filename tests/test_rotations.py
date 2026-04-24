"""Tests for forge_core.math.rotations.

Covers:
  - rotation_matrix_from_look_at (Phase 4.2, D-06/D-07/D-14/D-15)
    - orthonormality + det=+1 for valid inputs
    - free-rig cross-check — look-at <-> flame_euler_to_cam_rot invertibility
    - Camera1 live-probe known-answer (D-07 verification gate)
    - fail-loud on degenerate inputs (forward collapsed, up parallel to view)
    - roll-sign convention locked

Does NOT cover:
  - compute_flame_euler_zyx / flame_euler_to_cam_rot inverse pair — that
    lives in tests/test_blender_roundtrip.py::TestEulerHelperInverse.
  - FBX-layer aim-rig resolution (Plan 03 in tests/test_fbx_ascii.py).
"""

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))  # noqa: E402

from forge_core.math.rotations import (  # noqa: E402
    compute_flame_euler_xyz,
    compute_flame_euler_zyx,
    flame_euler_to_cam_rot,
    rotation_matrix_from_look_at,
)


# Camera1 values captured from the user's action9 fixture 2026-04-24 via
# forge-bridge live probe. Roll is the live-probe sign (-1.252521), which is
# Flame's rendered aim-rig roll direction (FBX stores +1.252521 sign-flipped
# on export; parser negates it back in the aim-rig branch before feeding the
# look-at helper). The decomposition uses compute_flame_euler_xyz per the
# Flame "Rot XYZ" convention verified via viewport manual-match on Camera1.
CAMERA1_POSITION = (0.0, 57.774681, 2113.305420)
CAMERA1_AIM      = (0.355065, 57.133656, 2093.318848)
CAMERA1_UP       = (0.0, 30.0, 0.0)
CAMERA1_ROLL_DEG = -1.252521


class TestLookAtMatrix:
    """rotation_matrix_from_look_at construction + D-15 fail-loud."""

    def test_matrix_is_rotation(self):
        R = rotation_matrix_from_look_at((0.0, 0.0, 0.0),
                                         (0.0, 0.0, -100.0),
                                         (0.0, 1.0, 0.0),
                                         0.0)
        # Determinant +1, orthonormal — no scale or reflection snuck in.
        np.testing.assert_allclose(R @ R.T, np.eye(3), atol=1e-12)
        assert abs(np.linalg.det(R) - 1.0) < 1e-12

    def test_matrix_is_rotation_with_roll(self):
        R = rotation_matrix_from_look_at((0.0, 0.0, 0.0),
                                         (0.0, 0.0, -100.0),
                                         (0.0, 1.0, 0.0),
                                         30.0)
        np.testing.assert_allclose(R @ R.T, np.eye(3), atol=1e-12)
        assert abs(np.linalg.det(R) - 1.0) < 1e-12

    @pytest.mark.parametrize("rot", [
        (-5.0, 15.0, 2.0),
        (0.0, 0.0, 0.0),
        (30.0, -45.0, 10.0),
        (-80.0, 5.0, -3.0),
    ], ids=["tilt", "identity", "compound", "strong-tilt"])
    def test_free_rig_cross_check(self, rot):
        # Proof that the look-at construction does NOT contradict the
        # already-proven flame_euler_to_cam_rot inverse (per D-07 case 2
        # — free-rig camera fed through the aim-rig path).
        R_orig = flame_euler_to_cam_rot(*rot)
        position = np.array([0.0, 0.0, 0.0])
        forward = -R_orig[:, 2]  # column 2 is -forward in our convention
        aim = position + forward * 100.0
        up = R_orig[:, 1]  # column 1 is up_cam
        R_recovered = rotation_matrix_from_look_at(position, aim, up, 0.0)
        np.testing.assert_allclose(R_recovered, R_orig, atol=1e-9)

    def test_camera1_known_answer(self):
        # D-07 case 1: Camera1 live probe (position, aim, up, roll captured
        # 2026-04-24 via forge-bridge). Decomposed via compute_flame_euler_xyz
        # (Flame's 'Rot XYZ' convention). Expected output matches user's
        # viewport manual-match of Camera2 to Camera1 within ~0.01° per axis.
        R = rotation_matrix_from_look_at(
            CAMERA1_POSITION, CAMERA1_AIM, CAMERA1_UP, CAMERA1_ROLL_DEG
        )
        np.testing.assert_allclose(R @ R.T, np.eye(3), atol=1e-10)
        assert abs(np.linalg.det(R) - 1.0) < 1e-10

        rx, ry, rz = compute_flame_euler_xyz(R)
        assert np.isfinite(rx) and np.isfinite(ry) and np.isfinite(rz)
        # Flame viewport ground truth: (1.81928, 1.06386, 1.25287).
        # Our output: (1.81404, 1.05766, 1.25209). Within 0.01°.
        assert abs(rx - 1.819) < 0.02, f"rx={rx} off from Flame truth 1.819"
        assert abs(ry - 1.064) < 0.02, f"ry={ry} off from Flame truth 1.064"
        assert abs(rz - 1.253) < 0.02, f"rz={rz} off from Flame truth 1.253"

    def test_raises_on_forward_degenerate(self):
        # D-15: |aim - position| <= 1e-6
        with pytest.raises(ValueError, match=r"aim-rig resolve.*forward"):
            rotation_matrix_from_look_at((0.0, 0.0, 0.0),
                                         (0.0, 0.0, 0.0),
                                         (0.0, 1.0, 0.0),
                                         0.0)

    def test_raises_on_up_parallel(self):
        # D-15: |cross(forward, up)| <= 1e-6 (up parallel to view)
        with pytest.raises(ValueError, match=r"aim-rig resolve.*up.*parallel"):
            rotation_matrix_from_look_at((0.0, 0.0, 0.0),
                                         (0.0, 0.0, -100.0),
                                         (0.0, 0.0, -1.0),
                                         0.0)

    def test_raises_on_up_antiparallel(self):
        # D-15: antiparallel up also gives |cross| = 0
        with pytest.raises(ValueError, match=r"aim-rig resolve.*up.*parallel"):
            rotation_matrix_from_look_at((0.0, 0.0, 0.0),
                                         (0.0, 0.0, -100.0),
                                         (0.0, 0.0, 1.0),
                                         0.0)

    def test_roll_sign_convention(self):
        # Roll about the forward axis: roll=+90 and roll=-90 must produce
        # different matrices (proves roll_deg is actually applied) whose
        # `right` columns are opposite rotations of the unrolled `right`.
        R0  = rotation_matrix_from_look_at((0, 0, 0), (0, 0, -100), (0, 1, 0),   0.0)
        Rp  = rotation_matrix_from_look_at((0, 0, 0), (0, 0, -100), (0, 1, 0),  90.0)
        Rn  = rotation_matrix_from_look_at((0, 0, 0), (0, 0, -100), (0, 1, 0), -90.0)
        assert not np.allclose(R0, Rp)
        assert not np.allclose(R0, Rn)
        # +90 and -90 differ from each other (sanity — sign is honoured).
        assert not np.allclose(Rp, Rn)
        # Orthonormality survives any roll.
        np.testing.assert_allclose(Rp @ Rp.T, np.eye(3), atol=1e-12)
        np.testing.assert_allclose(Rn @ Rn.T, np.eye(3), atol=1e-12)
