"""
Parity test: hook's inlined _solve() vs solver.solve_2vp().

The camera_match_hook ships its own _solve()/_solve_lines() that duplicates
the math in solver/solver.py. These tests assert they agree on the math
invariants — focal length, VP positions in image plane, camera rotation
matrix, principal point — on the same inputs.

If this passes, the hook's inline solver can be deleted and replaced with
a call to solver.solve_2vp() plus a thin Flame adapter that handles the
hook-specific outputs (ZYX Euler decomposition, cam_back default, trace).

Inputs mirror tests/test_cross_validate.py's fSpy reference fixture so
any divergence can be triaged against the fSpy ground truth.
"""

import json
import os
import sys
import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from flame import camera_match_hook as hook
from solver.solver import solve_2vp


W, H = 5184, 3456

# Same fSpy control points as test_cross_validate.py (relative 0..1 coords).
VP1_LINE1_P1_REL = (0.42601555503030025, 0.40415286833528946)
VP1_LINE1_P2_REL = (0.9000365618654662, 0.5454031009322207)
VP1_LINE2_P1_REL = (0.41739415081491654, 0.04953202027892652)
VP1_LINE2_P2_REL = (0.9507110122414305, 0.14287330297426987)
VP2_LINE1_P1_REL = (0.9172152342530506, 0.4082780302620597)
VP2_LINE1_P2_REL = (0.9480780284454208, 0.16349931327560732)
VP2_LINE2_P1_REL = (0.2569948727351605, 0.03775924569203336)
VP2_LINE2_P2_REL = (0.2713070131097316, 0.2613996034325672)


def _rel_to_px(rel):
    return (rel[0] * W, rel[1] * H)


# Hook uses integer axis codes (0..5 → ±X, ±Y, ±Z); solver uses string labels.
_AX_INT_TO_STR = ["+X", "-X", "+Y", "-Y", "+Z", "-Z"]


@pytest.fixture
def line_pixels():
    """8-point px list in the order _solve() expects:
    VP1 line1 start, line1 end, line2 start, line2 end,
    VP2 line1 start, line1 end, line2 start, line2 end."""
    return [
        _rel_to_px(VP1_LINE1_P1_REL),
        _rel_to_px(VP1_LINE1_P2_REL),
        _rel_to_px(VP1_LINE2_P1_REL),
        _rel_to_px(VP1_LINE2_P2_REL),
        _rel_to_px(VP2_LINE1_P1_REL),
        _rel_to_px(VP2_LINE1_P2_REL),
        _rel_to_px(VP2_LINE2_P1_REL),
        _rel_to_px(VP2_LINE2_P2_REL),
    ]


@pytest.fixture
def solver_lines():
    """Same endpoints as line_pixels, packed as ((p1, p2, p3, p4), ...) for solve_2vp."""
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


def _read_hook_trace():
    """_solve() writes its full internal state here on every call."""
    with open("/tmp/forge_camera_match_trace.json") as f:
        return json.load(f)


class TestHookVsSolverParity:
    """Run both solvers on identical inputs and assert the shared invariants
    agree. Axes chosen to match the fSpy reference: VP1 → -X (1), VP2 → -Z (5)."""

    AX1_HOOK, AX2_HOOK = 1, 5  # -X, -Z
    AX1_SOLVER, AX2_SOLVER = _AX_INT_TO_STR[1], _AX_INT_TO_STR[5]

    def test_both_converge(self, line_pixels, solver_lines):
        hook_out = hook._solve(line_pixels, W, H, ax1=self.AX1_HOOK, ax2=self.AX2_HOOK)
        solver_out = solve_2vp(
            solver_lines[0], solver_lines[1], W, H,
            axis1=self.AX1_SOLVER, axis2=self.AX2_SOLVER,
        )
        assert hook_out is not None, "hook._solve returned None"
        assert solver_out is not None, "solve_2vp returned None"

    def test_focal_length_matches(self, line_pixels, solver_lines):
        hook._solve(line_pixels, W, H, ax1=self.AX1_HOOK, ax2=self.AX2_HOOK)
        trace = _read_hook_trace()
        hook_f = trace["stages"]["f_relative"]

        solver_out = solve_2vp(
            solver_lines[0], solver_lines[1], W, H,
            axis1=self.AX1_SOLVER, axis2=self.AX2_SOLVER,
        )
        solver_f = solver_out["focal_length"]

        assert hook_f == pytest.approx(solver_f, rel=1e-9), \
            f"focal length divergence: hook={hook_f}, solver={solver_f}"

    def test_vanishing_points_match(self, line_pixels, solver_lines):
        hook._solve(line_pixels, W, H, ax1=self.AX1_HOOK, ax2=self.AX2_HOOK)
        trace = _read_hook_trace()
        hook_vp1 = np.array(trace["stages"]["vp1_imageplane"])
        hook_vp2 = np.array(trace["stages"]["vp2_imageplane"])

        solver_out = solve_2vp(
            solver_lines[0], solver_lines[1], W, H,
            axis1=self.AX1_SOLVER, axis2=self.AX2_SOLVER,
        )
        solver_vp1 = solver_out["vp1"]
        solver_vp2 = solver_out["vp2"]

        np.testing.assert_allclose(hook_vp1, solver_vp1, rtol=1e-9,
            err_msg="VP1 in image-plane coords diverged")
        np.testing.assert_allclose(hook_vp2, solver_vp2, rtol=1e-9,
            err_msg="VP2 in image-plane coords diverged")

    def test_principal_point_matches(self, line_pixels, solver_lines):
        hook._solve(line_pixels, W, H, ax1=self.AX1_HOOK, ax2=self.AX2_HOOK)
        # Hook doesn't trace pp unless vp3 is provided; when absent it's image centre.
        hook_pp = np.array([0.0, 0.0])

        solver_out = solve_2vp(
            solver_lines[0], solver_lines[1], W, H,
            axis1=self.AX1_SOLVER, axis2=self.AX2_SOLVER,
        )
        np.testing.assert_allclose(hook_pp, solver_out["principal_point"], atol=1e-12)

    def test_rotation_matrix_matches(self, line_pixels, solver_lines):
        """The hook's cam_rot_cam_to_world == solver's camera_transform[:3,:3].
        Both are the rotation taking camera-space vectors to world-space."""
        hook._solve(line_pixels, W, H, ax1=self.AX1_HOOK, ax2=self.AX2_HOOK)
        trace = _read_hook_trace()
        hook_cam_rot = np.array(trace["stages"]["cam_rot_cam_to_world"])

        solver_out = solve_2vp(
            solver_lines[0], solver_lines[1], W, H,
            axis1=self.AX1_SOLVER, axis2=self.AX2_SOLVER,
        )
        # solver's camera_transform is 4x4 when origin_px is set; 3x3 rotation (as
        # inverse of view) when not. Without origin, solver sets it to inv(view).
        # The rotation block is the same either way.
        solver_cam_rot = solver_out["camera_transform"][:3, :3]

        np.testing.assert_allclose(hook_cam_rot, solver_cam_rot, atol=1e-9,
            err_msg="cam-to-world rotation diverged")

    def test_view_rotation_matches(self, line_pixels, solver_lines):
        """Hook's view_rot_world_to_cam == solver's view_transform[:3,:3]."""
        hook._solve(line_pixels, W, H, ax1=self.AX1_HOOK, ax2=self.AX2_HOOK)
        trace = _read_hook_trace()
        hook_view = np.array(trace["stages"]["view_rot_world_to_cam"])

        solver_out = solve_2vp(
            solver_lines[0], solver_lines[1], W, H,
            axis1=self.AX1_SOLVER, axis2=self.AX2_SOLVER,
        )
        solver_view = solver_out["view_transform"][:3, :3]

        np.testing.assert_allclose(hook_view, solver_view, atol=1e-9,
            err_msg="world-to-cam view rotation diverged")


class TestAllAxisCombinations:
    """Every valid (ax1, ax2) pair with non-parallel axes should produce the
    same focal + rotation invariants in both solvers. Catches axis-mapping bugs."""

    @pytest.mark.parametrize("ax1_int,ax2_int", [
        (i, j) for i in range(6) for j in range(6)
        if i // 2 != j // 2  # different axis (not parallel)
    ])
    def test_axis_pair_parity(self, line_pixels, solver_lines, ax1_int, ax2_int):
        ax1_str = _AX_INT_TO_STR[ax1_int]
        ax2_str = _AX_INT_TO_STR[ax2_int]

        hook_out = hook._solve(line_pixels, W, H, ax1=ax1_int, ax2=ax2_int)
        trace = _read_hook_trace()

        solver_out = solve_2vp(
            solver_lines[0], solver_lines[1], W, H,
            axis1=ax1_str, axis2=ax2_str,
        )
        assert hook_out is not None and solver_out is not None

        # Focal is axis-independent; sanity-check it's stable.
        assert trace["stages"]["f_relative"] == pytest.approx(
            solver_out["focal_length"], rel=1e-9)

        # Rotation does depend on axis assignment — must match.
        hook_cam_rot = np.array(trace["stages"]["cam_rot_cam_to_world"])
        solver_cam_rot = solver_out["camera_transform"][:3, :3]
        np.testing.assert_allclose(hook_cam_rot, solver_cam_rot, atol=1e-9,
            err_msg=f"rot diverged for {ax1_str}/{ax2_str}")
