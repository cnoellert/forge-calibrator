"""
Adapter parity + invariant tests for forge_flame.adapter.solve_for_flame.

Originally this file proved that the hook's inlined _solve()/_solve_lines()
were mathematically equivalent to forge_core.solver.solve_2vp. That
equivalence was the green light to delete the hook's copy; after Stage 4
the hook calls solve_for_flame directly.

What we assert now:

  1. Math invariants — the adapter's solve_for_flame produces the same
     focal length, VP positions in image-plane coords, and cam-to-world
     rotation matrix as solve_2vp called directly on the same inputs.
     (The adapter wraps solve_2vp, so a divergence here means we mangled
     the packing or axis conversion, not the core math.)

  2. Flame-convention invariants — the returned Flame Euler reconstructs
     the cam-to-world rotation matrix when composed as
     R = Rz(rz) · Ry(-ry) · Rx(-rx). This is Flame's actual composition
     (see memory/flame_rotation_convention.md).

  3. Scale invariant — default cam_back equals h / (2 · tan(vfov/2)),
     which is Flame's 1-unit-per-pixel native distance.

  4. Output shape — the dict the adapter returns contains every key the
     hook UI consumes, with the expected types.

  5. All axis pairs — the adapter holds across every valid (ax1, ax2)
     combination, not just the fSpy-reference (-X, -Z).

Inputs use the fSpy test.fspy fixture for grounding.
"""

import os
import sys
import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from forge_core.solver.solver import solve_2vp
from forge_flame.adapter import (
    solve_for_flame,
    compute_flame_euler_zyx,
    default_cam_back,
    AX_INT_TO_STR,
)


W, H = 5184, 3456

# Same fSpy control points as test_cross_validate.py (relative 0..1 coords).
VP1_LINE1_P1_REL = (0.42601555503030025, 0.40415286833528946)
VP1_LINE1_P2_REL = (0.9000365618654662,  0.5454031009322207)
VP1_LINE2_P1_REL = (0.41739415081491654, 0.04953202027892652)
VP1_LINE2_P2_REL = (0.9507110122414305,  0.14287330297426987)
VP2_LINE1_P1_REL = (0.9172152342530506,  0.4082780302620597)
VP2_LINE1_P2_REL = (0.9480780284454208,  0.16349931327560732)
VP2_LINE2_P1_REL = (0.2569948727351605,  0.03775924569203336)
VP2_LINE2_P2_REL = (0.2713070131097316,  0.2613996034325672)


def _rel_to_px(r):
    return (r[0] * W, r[1] * H)


@pytest.fixture
def adapter_lines():
    """Pair of line lists shaped the way the hook passes them into the adapter:
    list of ((p0_px, p1_px), ...) per VP."""
    vp1 = [
        (_rel_to_px(VP1_LINE1_P1_REL), _rel_to_px(VP1_LINE1_P2_REL)),
        (_rel_to_px(VP1_LINE2_P1_REL), _rel_to_px(VP1_LINE2_P2_REL)),
    ]
    vp2 = [
        (_rel_to_px(VP2_LINE1_P1_REL), _rel_to_px(VP2_LINE1_P2_REL)),
        (_rel_to_px(VP2_LINE2_P1_REL), _rel_to_px(VP2_LINE2_P2_REL)),
    ]
    return vp1, vp2


@pytest.fixture
def solve_2vp_lines():
    """Same endpoints packed as 4-tuples for solve_2vp()."""
    vp1 = (
        np.array(_rel_to_px(VP1_LINE1_P1_REL)),
        np.array(_rel_to_px(VP1_LINE1_P2_REL)),
        np.array(_rel_to_px(VP1_LINE2_P1_REL)),
        np.array(_rel_to_px(VP1_LINE2_P2_REL)),
    )
    vp2 = (
        np.array(_rel_to_px(VP2_LINE1_P1_REL)),
        np.array(_rel_to_px(VP2_LINE1_P2_REL)),
        np.array(_rel_to_px(VP2_LINE2_P1_REL)),
        np.array(_rel_to_px(VP2_LINE2_P2_REL)),
    )
    return vp1, vp2


# =============================================================================
# Group 1: math equivalence — adapter ≡ solve_2vp
# =============================================================================


class TestAdapterMathMatchesSolver:
    """solve_for_flame internally calls solve_2vp; these tests verify the
    wrapping (line packing, axis int→str, result dict) doesn't mangle
    anything."""

    AX1, AX2 = 1, 5  # -X, -Z (fSpy reference)

    def test_both_converge(self, adapter_lines, solve_2vp_lines):
        adapter_out = solve_for_flame(
            adapter_lines[0], adapter_lines[1], W, H, self.AX1, self.AX2)
        direct = solve_2vp(
            solve_2vp_lines[0], solve_2vp_lines[1], W, H,
            axis1=AX_INT_TO_STR[self.AX1], axis2=AX_INT_TO_STR[self.AX2])
        assert adapter_out is not None
        assert direct is not None

    def test_focal_length_matches(self, adapter_lines, solve_2vp_lines):
        a = solve_for_flame(
            adapter_lines[0], adapter_lines[1], W, H, self.AX1, self.AX2)
        d = solve_2vp(
            solve_2vp_lines[0], solve_2vp_lines[1], W, H,
            axis1=AX_INT_TO_STR[self.AX1], axis2=AX_INT_TO_STR[self.AX2])
        assert a["f_relative"] == pytest.approx(d["focal_length"], rel=1e-9)

    def test_rotation_matrix_matches(self, adapter_lines, solve_2vp_lines):
        a = solve_for_flame(
            adapter_lines[0], adapter_lines[1], W, H, self.AX1, self.AX2)
        d = solve_2vp(
            solve_2vp_lines[0], solve_2vp_lines[1], W, H,
            axis1=AX_INT_TO_STR[self.AX1], axis2=AX_INT_TO_STR[self.AX2])
        adapter_rot = np.asarray(a["cam_rot"])
        direct_rot = d["camera_transform"][:3, :3]
        np.testing.assert_allclose(adapter_rot, direct_rot, atol=1e-9)


# =============================================================================
# Group 2: Flame rotation convention — Euler → R round-trip
# =============================================================================


class TestFlameEulerRoundTrip:
    """The returned rotation triple must reconstruct cam_rot under Flame's
    ZYX-with-X,Y-negated composition: R = Rz(rz) · Ry(-ry) · Rx(-rx)."""

    def _rx(self, a): c, s = np.cos(a), np.sin(a); return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])
    def _ry(self, a): c, s = np.cos(a), np.sin(a); return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
    def _rz(self, a): c, s = np.cos(a), np.sin(a); return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])

    def _reconstruct(self, rx_deg, ry_deg, rz_deg):
        rx, ry, rz = np.radians([rx_deg, ry_deg, rz_deg])
        return self._rz(rz) @ self._ry(-ry) @ self._rx(-rx)

    def test_roundtrip_fspy_fixture(self, adapter_lines):
        out = solve_for_flame(adapter_lines[0], adapter_lines[1], W, H, 1, 5)
        R = np.asarray(out["cam_rot"])
        R_recon = self._reconstruct(*out["rotation"])
        np.testing.assert_allclose(R_recon, R, atol=1e-6)

    @pytest.mark.parametrize("ax1,ax2", [
        (i, j) for i in range(6) for j in range(6) if i // 2 != j // 2
    ])
    def test_roundtrip_all_axis_pairs(self, adapter_lines, ax1, ax2):
        out = solve_for_flame(adapter_lines[0], adapter_lines[1], W, H, ax1, ax2)
        if out is None:
            pytest.skip(f"solve didn't converge for ({ax1}, {ax2})")
        R = np.asarray(out["cam_rot"])
        R_recon = self._reconstruct(*out["rotation"])
        np.testing.assert_allclose(R_recon, R, atol=1e-6,
            err_msg=f"Euler→R round-trip failed for axes "
                    f"{AX_INT_TO_STR[ax1]}/{AX_INT_TO_STR[ax2]}")


# =============================================================================
# Group 3: scale — default cam_back
# =============================================================================


class TestDefaultCamBack:
    """Flame's native 1-unit-per-pixel scale requires camera distance
    h / (2 · tan(vfov/2))."""

    def test_formula(self):
        # vfov=60° at h=1080 → cam_back = 1080 / (2·tan(30°)) ≈ 935.307
        assert default_cam_back(1080, np.radians(60.0)) == pytest.approx(
            1080.0 / (2.0 * np.tan(np.radians(30.0))), rel=1e-12)

    def test_adapter_uses_default_when_not_supplied(self, adapter_lines):
        out = solve_for_flame(adapter_lines[0], adapter_lines[1], W, H, 1, 5)
        vfov_rad = np.radians(out["vfov_deg"])
        assert out["cam_back_dist"] == pytest.approx(
            default_cam_back(H, vfov_rad), rel=1e-9)

    def test_adapter_honours_explicit_cam_back(self, adapter_lines):
        out = solve_for_flame(
            adapter_lines[0], adapter_lines[1], W, H, 1, 5, cam_back=1234.5)
        assert out["cam_back_dist"] == pytest.approx(1234.5, rel=1e-12)


# =============================================================================
# Group 4: output shape — every key the UI consumes is present with right types
# =============================================================================


class TestResultShape:
    """Drop-in replacement for the old hook._solve return contract."""

    REQUIRED_KEYS = {
        "position", "rotation", "focal_mm", "film_back_mm",
        "hfov_deg", "vfov_deg", "cam_rot", "f_relative",
        "ax1", "ax2", "origin_px", "cam_back_dist", "principal_point_px",
    }

    def test_all_keys_present(self, adapter_lines):
        out = solve_for_flame(adapter_lines[0], adapter_lines[1], W, H, 1, 5)
        assert self.REQUIRED_KEYS.issubset(out.keys())

    def test_types(self, adapter_lines):
        out = solve_for_flame(adapter_lines[0], adapter_lines[1], W, H, 1, 5)
        assert isinstance(out["position"], tuple) and len(out["position"]) == 3
        assert isinstance(out["rotation"], tuple) and len(out["rotation"]) == 3
        assert all(isinstance(v, float) for v in out["position"])
        assert all(isinstance(v, float) for v in out["rotation"])
        assert isinstance(out["cam_rot"], list) and len(out["cam_rot"]) == 3
        assert isinstance(out["origin_px"], list) and len(out["origin_px"]) == 2
        assert out["principal_point_px"] is None  # no vp3 supplied

    def test_axis_ints_echoed(self, adapter_lines):
        out = solve_for_flame(adapter_lines[0], adapter_lines[1], W, H, 2, 4)
        assert out["ax1"] == 2 and out["ax2"] == 4


# =============================================================================
# Group 5: all-axis robustness — convergence + self-consistency
# =============================================================================


class TestAllAxisPairs:
    """For every valid axis pair, focal stays axis-independent and rotation
    stays self-consistent via the Flame-Euler reconstruction."""

    @pytest.mark.parametrize("ax1,ax2", [
        (i, j) for i in range(6) for j in range(6) if i // 2 != j // 2
    ])
    def test_converges_and_focal_stable(self, adapter_lines, ax1, ax2):
        out = solve_for_flame(adapter_lines[0], adapter_lines[1], W, H, ax1, ax2)
        assert out is not None, f"failed to converge for {AX_INT_TO_STR[ax1]}/{AX_INT_TO_STR[ax2]}"
        # Focal length is axis-independent — all pairs should produce the same
        # value (within numerical noise). Compare against the -X/-Z reference.
        if ax1 != 1 or ax2 != 5:
            ref = solve_for_flame(adapter_lines[0], adapter_lines[1], W, H, 1, 5)
            assert out["f_relative"] == pytest.approx(ref["f_relative"], rel=1e-9)
