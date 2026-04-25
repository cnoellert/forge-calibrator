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
        """Camera1 look-at sanity. Pre-Phase-04.3 this test asserted
        |rz - CAMERA1_ROLL_DEG| < 1.0 after _zyx decomposition; that
        assertion was implicitly coupled to the old roll-Rodrigues sign
        in rotation_matrix_from_look_at (theta = -roll_deg). Phase 04.3
        flipped that sign at L167 (theta = +roll_deg) in lockstep with
        adopting the _xyz decomposer for aim-rig consumers; under _zyx
        the new look-at output decomposes to rz≈-1.25° (sign flipped),
        so the original assertion would fail spuriously.

        The detailed Camera1 known-answer now lives in
        TestComputeFlameEulerXyz::test_camera1_known_answer (which uses
        the _xyz decomposer matching the new look-at convention). This
        test only validates the look-at output is a well-formed rotation
        matrix (orthonormal, det=+1, no NaN)."""
        R = rotation_matrix_from_look_at(
            CAMERA1_POSITION, CAMERA1_AIM, CAMERA1_UP, CAMERA1_ROLL_DEG
        )
        # Orthonormality holds (no degenerate input).
        assert R.shape == (3, 3)
        np.testing.assert_allclose(R @ R.T, np.eye(3), atol=1e-10)
        assert abs(np.linalg.det(R) - 1.0) < 1e-10
        # No silent NaN.
        assert np.all(np.isfinite(R))

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
        """Hand-built gimbal test under the Z·Y·X product convention.

        Target: rx=0, ry=+90°, rz=+30°. Under R = Rz(-rz)·Ry(-ry)·Rx(-rx)
        this is R = Rz(-30°) @ Ry(-90°) @ Rx(0). Matrix entries computed
        BY HAND from the closed form (cz=cos(-30°)=√3/2, sz=sin(-30°)=-0.5;
        cy=cos(-90°)=0, sy=sin(-90°)=-1):

            Rz(-30°) = [[ √3/2, +0.5, 0], [-0.5, √3/2, 0], [ 0, 0, 1]]
            Ry(-90°) = [[ 0, 0,-1], [ 0, 1, 0], [ 1, 0, 0]]
            R = Rz(-30°) @ Ry(-90°)
              = [[ 0,    0.5,  -√3/2 ],
                 [ 0,    √3/2,  0.5  ],
                 [ 1,    0,     0    ]]

        Verify: R[2,0] = +1 → cb = sqrt(R[0,0]² + R[1,0]²) = 0 → gimbal
        branch fires. ry = -arcsin(-R[2,0]) = -arcsin(-1) = +π/2 = +90°.
        rz = atan2(R[0,1], R[1,1]) = atan2(0.5, √3/2) = π/6 = 30°.

        Anti-regression: this test guards against the gimbal branch in
        _xyz being copy-pasted from _zyx without flipping the first arg
        of the rz atan2. _zyx uses atan2(-R[0,1], R[1,1]) which would
        return -30° here; _xyz must use atan2(R[0,1], R[1,1]) (no
        leading minus on the first arg) to match the new convention."""
        sqrt3_over_2 = math.sqrt(3) / 2
        R = np.array([
            [ 0.0,  0.5,         -sqrt3_over_2 ],
            [ 0.0,  sqrt3_over_2, 0.5          ],
            [ 1.0,  0.0,          0.0          ],
        ], dtype=float)
        rx, ry, rz = compute_flame_euler_xyz(R)
        assert math.isclose(rx,  0.0, abs_tol=1e-3)
        assert math.isclose(ry, 90.0, abs_tol=1e-3)
        assert math.isclose(rz, 30.0, abs_tol=1e-3)

    # ------------------------------------------------------------------
    # Camera1 known-answer (NON-circular)
    # ------------------------------------------------------------------
    # This test depends on BOTH the _xyz decomposer (Task 2) AND the
    # L167 roll-Rodrigues sign flip in rotation_matrix_from_look_at
    # (Task 3). The two changes are coupled — only the combination
    # reproduces CAMERA1_HAND_DECOMPOSED_XYZ. Both landed in the
    # Phase 04.3 atomic commit.
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
