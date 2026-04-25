"""Tests for forge_core.math.rotations.

Covers:
  - rotation_matrix_from_look_at (Phase 4.2, D-06/D-07/D-14/D-15)
    - orthonormality + det=+1 for valid inputs
    - free-rig cross-check — look-at <-> flame_euler_to_cam_rot invertibility
    - Camera1 live-probe known-answer (D-07 verification gate)
    - fail-loud on degenerate inputs (forward collapsed, up parallel to view)
    - roll-sign convention locked
  - compute_flame_euler_xyz / flame_euler_xyz_to_cam_rot (Phase 04.3, D-ADD/D-TEST)
    - Identity, pure-axis hand-built matrices, gimbal-lock branch
    - Camera1 known-answer with hand-decomposed oracle (NON-circular)
    - Composer/decomposer invertibility on parametrised triples
    - Orthonormality + det=+1 of composer output
    - Anti-regression: _zyx pair untouched

Does NOT cover:
  - compute_flame_euler_zyx / flame_euler_to_cam_rot inverse pair on
    arbitrary triples — that lives in
    tests/test_blender_roundtrip.py::TestEulerHelperInverse.
  - FBX-layer aim-rig resolution (Plan 03 in tests/test_fbx_ascii.py).
"""

import math
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))  # noqa: E402

from forge_core.math.rotations import (  # noqa: E402
    compute_flame_euler_xyz,
    compute_flame_euler_zyx,
    flame_euler_to_cam_rot,
    flame_euler_xyz_to_cam_rot,
    rotation_matrix_from_look_at,
)


# Camera1 values captured from the user's action9 fixture (2026-04-23). The
# roll value is the FBX-stored sign (+1.252521) — verified against a Flame
# viewport manual-match on Camera1 after the 04.2 HUMAN-UAT discovered that
# forge-bridge's live-probe readout (-1.252521) did NOT reflect Flame's
# rendered aim-rig roll direction. See the static-fallback branch comment in
# forge_flame/fbx_ascii.py for the parser-side mirror of this fix.
CAMERA1_POSITION = (0.0, 57.774681, 2113.305420)
CAMERA1_AIM      = (0.355065, 57.133656, 2093.318848)
CAMERA1_UP       = (0.0, 30.0, 0.0)
CAMERA1_ROLL_DEG = 1.252521

# Phase 04.3: Camera1 ground-truth Euler under the new XYZ-signflip convention
# (R = Rx(-rx)·Ry(-ry)·Rz(-rz), X·Y·Z product order). Source: 04.3-SPIKE.md
# empirical search; reproduces Flame viewport ground truth within 0.006°.
# Hand-decomposed value used as the test oracle (NON-circular — does NOT round
# through flame_euler_xyz_to_cam_rot, which would be the composer-as-oracle
# anti-pattern that masked the Phase 04.2 bug).
CAMERA1_HAND_DECOMPOSED_XYZ = (1.814, 1.058, 1.252)        # tolerance 1e-3°
CAMERA1_FLAME_VIEWPORT_XYZ  = (1.8193, 1.0639, 1.2529)     # tolerance 0.01°


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
        # 2026-04-23). This is the anchor for Plan 03's FBX integration
        # test — whatever Euler triple Task 1's implementation produces
        # for this input is THE expected value.
        R = rotation_matrix_from_look_at(
            CAMERA1_POSITION, CAMERA1_AIM, CAMERA1_UP, CAMERA1_ROLL_DEG
        )
        # Orthonormality holds (no degenerate input).
        np.testing.assert_allclose(R @ R.T, np.eye(3), atol=1e-10)
        assert abs(np.linalg.det(R) - 1.0) < 1e-10

        rx, ry, rz = compute_flame_euler_zyx(R)
        # All finite (no silent NaN from Task 1).
        assert np.isfinite(rx) and np.isfinite(ry) and np.isfinite(rz)
        # Aim is almost directly along world -Z from position
        # (aim - pos ≈ (0.35, -0.64, -19.99)); rz should be dominated by
        # the roll (~-1.25°). Allow 1° slack for the small tilt introduced
        # by aim_y != pos_y. If this assert fails, the roll-sign
        # convention or the column convention in Task 1 is wrong.
        assert abs(rz - CAMERA1_ROLL_DEG) < 1.0, (
            f"Camera1 rz={rz:.4f}° diverges from expected "
            f"roll={CAMERA1_ROLL_DEG}° by more than 1° — roll sign or "
            f"column convention is wrong"
        )

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


class TestComputeFlameEulerXyz:
    """compute_flame_euler_xyz / flame_euler_xyz_to_cam_rot — Phase 04.3.

    Convention: R = Rx(-rx) · Ry(-ry) · Rz(-rz) — X·Y·Z matrix product order
    with all three Euler signs negated. Verified 2026-04-25 via forge-bridge
    live probe of Camera1 + Flame viewport manual-match + empirical spike
    (see 04.3-SPIKE.md, 04.3-01-PLAN-AMENDMENT.md §A).

    Anti-pattern guard: the Camera1 known-answer test uses
    rotation_matrix_from_look_at output as the input AND the hand-decomposed
    (1.814°, 1.058°, 1.252°) as the expected oracle. It does NOT use
    flame_euler_xyz_to_cam_rot to construct the input — that's the
    composer-as-decomposer-oracle anti-pattern that masked the Phase 04.2
    bug (PATTERNS.md §"Anti-Pattern to AVOID")."""

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------
    def test_identity_decomposes_to_zero(self):
        rx, ry, rz = compute_flame_euler_xyz(np.eye(3))
        assert math.isclose(rx, 0.0, abs_tol=1e-12)
        assert math.isclose(ry, 0.0, abs_tol=1e-12)
        assert math.isclose(rz, 0.0, abs_tol=1e-12)

    def test_identity_composes_to_eye(self):
        R = flame_euler_xyz_to_cam_rot(0.0, 0.0, 0.0)
        np.testing.assert_allclose(R, np.eye(3), atol=1e-12)

    # ------------------------------------------------------------------
    # Pure-axis hand-built matrices
    # ------------------------------------------------------------------
    # Under R = Rx(-rx) · Ry(-ry) · Rz(-rz), with the other two angles
    # zeroed, R reduces to a single factor whose argument is the
    # corresponding negated angle. Pure-axis matrices are convention-
    # invariant (only one factor is non-trivial) so these tests work
    # under both the old Z·Y·X form and the new X·Y·Z form. They guard
    # against accidental angle-radian/degree confusion or lost minus signs.
    def test_pure_rx_30_deg(self):
        # Pure rx=+30° → R = Rx(-30°)
        a = math.radians(-30.0)
        c, s = math.cos(a), math.sin(a)
        R = np.array([[1.0, 0.0, 0.0],
                      [0.0,   c,  -s],
                      [0.0,   s,   c]], dtype=float)
        rx, ry, rz = compute_flame_euler_xyz(R)
        assert math.isclose(rx, 30.0, abs_tol=1e-9)
        assert math.isclose(ry,  0.0, abs_tol=1e-9)
        assert math.isclose(rz,  0.0, abs_tol=1e-9)

    def test_pure_ry_30_deg(self):
        # Pure ry=+30° → R = Ry(-30°)
        b = math.radians(-30.0)
        c, s = math.cos(b), math.sin(b)
        R = np.array([[  c, 0.0,   s],
                      [0.0, 1.0, 0.0],
                      [ -s, 0.0,   c]], dtype=float)
        rx, ry, rz = compute_flame_euler_xyz(R)
        assert math.isclose(rx,  0.0, abs_tol=1e-9)
        assert math.isclose(ry, 30.0, abs_tol=1e-9)
        assert math.isclose(rz,  0.0, abs_tol=1e-9)

    def test_pure_rz_30_deg(self):
        # Pure rz=+30° → R = Rz(-30°). NOTE: this differs from _zyx where
        # pure rz=+30 builds Rz(+30°). The new _xyz convention negates
        # all three angles in the matrix product.
        g = math.radians(-30.0)
        c, s = math.cos(g), math.sin(g)
        R = np.array([[  c,  -s, 0.0],
                      [  s,   c, 0.0],
                      [0.0, 0.0, 1.0]], dtype=float)
        rx, ry, rz = compute_flame_euler_xyz(R)
        assert math.isclose(rx,  0.0, abs_tol=1e-9)
        assert math.isclose(ry,  0.0, abs_tol=1e-9)
        assert math.isclose(rz, 30.0, abs_tol=1e-9)

    # ------------------------------------------------------------------
    # Gimbal lock — hand-built X·Y·Z matrix
    # ------------------------------------------------------------------
    def test_gimbal_lock_ry_plus_90(self):
        """Hand-built gimbal test under the X·Y·Z product convention.

        Target: rx=0, ry=+90°, rz=+30°. Under R = Rx(-rx)·Ry(-ry)·Rz(-rz)
        this is R = Rx(0) @ Ry(-90°) @ Rz(-30°). Matrix entries computed
        BY HAND from the closed form (cz=cos(-30°)=√3/2, sz=sin(-30°)=-0.5;
        cy=cos(-90°)=0, sy=sin(-90°)=-1):

            Ry(-90°) = [[ 0, 0,-1], [ 0, 1, 0], [ 1, 0, 0]]
            Rz(-30°) = [[ √3/2, +0.5, 0], [-0.5, √3/2, 0], [ 0, 0, 1]]
            R = Ry(-90°) @ Rz(-30°)
              = [[ 0,    0,    -1   ],
                 [-0.5,  √3/2,  0   ],
                 [ √3/2, 0.5,   0   ]]

        Anti-regression: this test guards against a copy-paste from
        _zyx's gimbal branch. _zyx uses sqrt(R[0,0]^2 + R[1,0]^2) as the
        gimbal indicator (check R[2,0]=±1) AND atan2(-R[0,1], R[1,1]) for
        rz; both would give wrong answers on this matrix because R[0,0]
        and R[1,0] aren't simultaneously zero here, and the row/col
        indices are different under X·Y·Z. The correct _xyz gimbal
        indicator is sqrt(R[0,0]^2 + R[0,1]^2)=0 (R[0,2]=±1)."""
        sqrt3_over_2 = math.sqrt(3) / 2
        R = np.array([
            [ 0.0,          0.0,         -1.0       ],
            [-0.5,          sqrt3_over_2, 0.0       ],
            [ sqrt3_over_2, 0.5,          0.0       ],
        ], dtype=float)
        rx, ry, rz = compute_flame_euler_xyz(R)
        assert math.isclose(rx,  0.0, abs_tol=1e-3)
        assert math.isclose(ry, 90.0, abs_tol=1e-3)
        assert math.isclose(rz, 30.0, abs_tol=1e-3)

    # ------------------------------------------------------------------
    # Camera1 known-answer (NON-circular)
    # ------------------------------------------------------------------
    # NOTE: this test depends on BOTH the new _xyz decomposer (Task 2)
    # AND the L167 sign flip in rotation_matrix_from_look_at (Task 3).
    # The two changes are coupled — only the combination reproduces
    # CAMERA1_HAND_DECOMPOSED_XYZ. Marked xfail until the coupled Task 3
    # commit lands; that commit removes the xfail.
    @pytest.mark.xfail(
        strict=True,
        reason=(
            "Coupled with the L167 roll-Rodrigues sign flip in "
            "rotation_matrix_from_look_at (Phase 04.3 Task 3 atomic "
            "commit). Until that lands, look-at + _xyz decomposer "
            "produces (1.858°, 0.977°, -1.252°) — see 04.3-SPIKE.md."
        ),
    )
    def test_camera1_known_answer(self):
        """Camera1 hand-decomposed oracle (NON-circular).

        Construct R via rotation_matrix_from_look_at (independently
        proven by TestLookAtMatrix above); decompose with the new
        compute_flame_euler_xyz; assert the result matches the hand-
        decomposed (1.814°, 1.058°, 1.252°) within 1e-3°. Does NOT
        round-trip through flame_euler_xyz_to_cam_rot — that would be
        the composer-as-oracle anti-pattern."""
        R = rotation_matrix_from_look_at(
            CAMERA1_POSITION, CAMERA1_AIM, CAMERA1_UP, CAMERA1_ROLL_DEG
        )
        rx, ry, rz = compute_flame_euler_xyz(R)
        assert math.isclose(rx, CAMERA1_HAND_DECOMPOSED_XYZ[0], abs_tol=1e-3)
        assert math.isclose(ry, CAMERA1_HAND_DECOMPOSED_XYZ[1], abs_tol=1e-3)
        assert math.isclose(rz, CAMERA1_HAND_DECOMPOSED_XYZ[2], abs_tol=1e-3)

    # ------------------------------------------------------------------
    # Invertibility — composer ↔ decomposer round-trip
    # ------------------------------------------------------------------
    @pytest.mark.parametrize("tri", [
        (10.0, 20.0, 30.0),
        (-15.5, 45.0, -70.25),
        (5.0, 0.0, 0.0),
        (0.0, 30.0, 0.0),
        (0.0, 0.0, -60.0),
        (-80.0, 20.0, 45.0),
    ], ids=["compound", "neg-compound", "rx-only", "ry-only",
            "rz-only-neg", "strong-tilt"])
    def test_invertibility(self, tri):
        """compose then decompose returns the input within 1e-9°.

        This proves invertibility ONLY — not correctness against an
        external oracle. Correctness is exercised by the pure-axis,
        gimbal-lock, and Camera1 known-answer tests above."""
        R = flame_euler_xyz_to_cam_rot(*tri)
        recovered = compute_flame_euler_xyz(R)
        np.testing.assert_allclose(recovered, tri, atol=1e-9)

    # ------------------------------------------------------------------
    # Orthonormality + det(R)=+1 of composer output
    # ------------------------------------------------------------------
    @pytest.mark.parametrize("tri", [
        (10.0, 20.0, 30.0),
        (-15.5, 45.0, -70.25),
        (5.0, 0.0, 0.0),
        (0.0, 30.0, 0.0),
        (0.0, 0.0, -60.0),
        (-80.0, 20.0, 45.0),
    ], ids=["compound", "neg-compound", "rx-only", "ry-only",
            "rz-only-neg", "strong-tilt"])
    def test_orthonormality(self, tri):
        R = flame_euler_xyz_to_cam_rot(*tri)
        np.testing.assert_allclose(R @ R.T, np.eye(3), atol=1e-12)
        assert abs(np.linalg.det(R) - 1.0) < 1e-12

    # ------------------------------------------------------------------
    # Anti-regression: _zyx pair untouched
    # ------------------------------------------------------------------
    def test_anti_regression_zyx_unchanged(self):
        """_zyx pair must remain a self-inverse on identity. Phase 04.3
        is additive — the Free-rig solve path depends on _zyx's
        symmetric pass-through behavior and must not be perturbed."""
        rx, ry, rz = compute_flame_euler_zyx(np.eye(3))
        assert math.isclose(rx, 0.0, abs_tol=1e-12)
        assert math.isclose(ry, 0.0, abs_tol=1e-12)
        assert math.isclose(rz, 0.0, abs_tol=1e-12)
        R = flame_euler_to_cam_rot(0.0, 0.0, 0.0)
        np.testing.assert_allclose(R, np.eye(3), atol=1e-12)
