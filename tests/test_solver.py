"""
Unit tests for the camera match solver.

Tests are structured bottom-up matching the solver pipeline:
  coordinates → line_intersection → focal_length → rotation → full solve

Known-answer tests use geometrically constructed configurations where
the expected results can be verified analytically.
"""

import numpy as np
import pytest
import sys
import os

# Add parent dir to path so solver package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from solver.coordinates import px_to_image_plane, image_plane_to_px
from solver.math_util import line_intersection, orthogonal_projection_on_line, orthocentre
from solver.solver import (
    compute_focal_length,
    compute_camera_rotation_matrix,
    axis_assignment_matrix,
    compute_view_transform,
    compute_horizontal_fov,
    compute_vertical_fov,
    solve_2vp,
    solve_1vp,
)


# ---------------------------------------------------------------------------
# Coordinate conversion tests
# ---------------------------------------------------------------------------

class TestCoordinates:
    """Test pixel <-> ImagePlane conversions."""

    def test_centre_wide_image(self):
        """Image centre should map to (0, 0) in ImagePlane."""
        ip = px_to_image_plane(960, 540, 1920, 1080)
        np.testing.assert_allclose(ip, [0.0, 0.0], atol=1e-10)

    def test_centre_tall_image(self):
        """Image centre of a tall image maps to (0, 0)."""
        ip = px_to_image_plane(540, 960, 1080, 1920)
        np.testing.assert_allclose(ip, [0.0, 0.0], atol=1e-10)

    def test_corners_wide_image(self):
        """Corners of a 1920x1080 (16:9) image."""
        W, H = 1920, 1080
        aspect = W / H

        # Top-left (0, 0)
        tl = px_to_image_plane(0, 0, W, H)
        np.testing.assert_allclose(tl, [-1.0, 1.0 / aspect], atol=1e-10)

        # Bottom-right (W, H)
        br = px_to_image_plane(W, H, W, H)
        np.testing.assert_allclose(br, [1.0, -1.0 / aspect], atol=1e-10)

    def test_corners_square_image(self):
        """Square image: x and y both span [-1, 1]."""
        ip_tl = px_to_image_plane(0, 0, 1000, 1000)
        np.testing.assert_allclose(ip_tl, [-1.0, 1.0], atol=1e-10)

        ip_br = px_to_image_plane(1000, 1000, 1000, 1000)
        np.testing.assert_allclose(ip_br, [1.0, -1.0], atol=1e-10)

    def test_corners_tall_image(self):
        """Tall image (1080x1920): x in [-aspect, aspect], y in [-1, 1]."""
        W, H = 1080, 1920
        aspect = W / H  # 0.5625

        tl = px_to_image_plane(0, 0, W, H)
        np.testing.assert_allclose(tl, [-aspect, 1.0], atol=1e-10)

        br = px_to_image_plane(W, H, W, H)
        np.testing.assert_allclose(br, [aspect, -1.0], atol=1e-10)

    def test_roundtrip_wide(self):
        """px -> ImagePlane -> px roundtrip for wide image."""
        W, H = 1920, 1080
        for px, py in [(0, 0), (960, 540), (1920, 1080), (480, 270)]:
            ip = px_to_image_plane(px, py, W, H)
            back = image_plane_to_px(ip, W, H)
            np.testing.assert_allclose(back, [px, py], atol=1e-8)

    def test_roundtrip_tall(self):
        """px -> ImagePlane -> px roundtrip for tall image."""
        W, H = 1080, 1920
        for px, py in [(0, 0), (540, 960), (1080, 1920), (270, 480)]:
            ip = px_to_image_plane(px, py, W, H)
            back = image_plane_to_px(ip, W, H)
            np.testing.assert_allclose(back, [px, py], atol=1e-8)


# ---------------------------------------------------------------------------
# Line intersection tests
# ---------------------------------------------------------------------------

class TestLineIntersection:
    """Test line-line intersection."""

    def test_perpendicular_lines(self):
        """Two perpendicular lines through the origin."""
        p = line_intersection(
            np.array([-1.0, 0.0]), np.array([1.0, 0.0]),
            np.array([0.0, -1.0]), np.array([0.0, 1.0]),
        )
        np.testing.assert_allclose(p, [0.0, 0.0], atol=1e-10)

    def test_diagonal_lines(self):
        """Two diagonal lines intersecting at (1, 1)."""
        # Line 1: y = x  (through (0,0) and (2,2))
        # Line 2: y = -x + 2  (through (0,2) and (2,0))
        p = line_intersection(
            np.array([0.0, 0.0]), np.array([2.0, 2.0]),
            np.array([0.0, 2.0]), np.array([2.0, 0.0]),
        )
        np.testing.assert_allclose(p, [1.0, 1.0], atol=1e-10)

    def test_parallel_lines(self):
        """Parallel lines should return None."""
        p = line_intersection(
            np.array([0.0, 0.0]), np.array([1.0, 0.0]),
            np.array([0.0, 1.0]), np.array([1.0, 1.0]),
        )
        assert p is None

    def test_nearly_parallel(self):
        """Nearly parallel lines at a far intersection."""
        # Lines with very small angle — should still find intersection
        p = line_intersection(
            np.array([0.0, 0.0]), np.array([1000.0, 1.0]),
            np.array([0.0, 0.1]), np.array([1000.0, 1.1]),
        )
        # These are actually parallel (same slope), so None
        assert p is None

    def test_converging_vp_lines(self):
        """Simulate two line segments converging to a vanishing point."""
        # VP at (5, 3)
        vp = np.array([5.0, 3.0])
        # Two lines through VP
        p1 = np.array([0.0, 0.0])
        p2 = vp + (vp - p1) * 0.5  # extend past VP
        p3 = np.array([1.0, 4.0])
        p4 = vp + (vp - p3) * 0.5

        result = line_intersection(p1, p2, p3, p4)
        np.testing.assert_allclose(result, vp, atol=1e-10)


# ---------------------------------------------------------------------------
# Orthogonal projection tests
# ---------------------------------------------------------------------------

class TestOrthogonalProjection:
    """Test point-onto-line projection."""

    def test_point_on_x_axis(self):
        """Project (3, 5) onto the x-axis."""
        proj = orthogonal_projection_on_line(
            np.array([3.0, 5.0]),
            np.array([0.0, 0.0]),
            np.array([1.0, 0.0]),
        )
        np.testing.assert_allclose(proj, [3.0, 0.0], atol=1e-10)

    def test_point_on_line(self):
        """A point already on the line projects to itself."""
        proj = orthogonal_projection_on_line(
            np.array([2.0, 2.0]),
            np.array([0.0, 0.0]),
            np.array([1.0, 1.0]),
        )
        np.testing.assert_allclose(proj, [2.0, 2.0], atol=1e-10)

    def test_diagonal_projection(self):
        """Project (0, 2) onto y=x line."""
        proj = orthogonal_projection_on_line(
            np.array([0.0, 2.0]),
            np.array([0.0, 0.0]),
            np.array([1.0, 1.0]),
        )
        np.testing.assert_allclose(proj, [1.0, 1.0], atol=1e-10)


# ---------------------------------------------------------------------------
# Orthocentre tests
# ---------------------------------------------------------------------------

class TestOrthocentre:
    """Test triangle orthocentre computation."""

    def test_right_triangle(self):
        """Orthocentre of a right triangle is at the right-angle vertex."""
        oc = orthocentre(
            np.array([0.0, 0.0]),
            np.array([4.0, 0.0]),
            np.array([0.0, 3.0]),
        )
        np.testing.assert_allclose(oc, [0.0, 0.0], atol=1e-10)

    def test_equilateral_triangle(self):
        """Orthocentre of an equilateral triangle is the centroid."""
        a = np.array([0.0, 0.0])
        b = np.array([2.0, 0.0])
        c = np.array([1.0, np.sqrt(3.0)])
        centroid = (a + b + c) / 3.0

        oc = orthocentre(a, b, c)
        np.testing.assert_allclose(oc, centroid, atol=1e-10)

    def test_degenerate_triangle(self):
        """Collinear points return None."""
        oc = orthocentre(
            np.array([0.0, 0.0]),
            np.array([1.0, 1.0]),
            np.array([2.0, 2.0]),
        )
        assert oc is None


# ---------------------------------------------------------------------------
# Focal length tests
# ---------------------------------------------------------------------------

class TestFocalLength:
    """Test focal length computation from vanishing points."""

    def test_symmetric_vps(self):
        """Two VPs symmetric about the principal point on the x-axis.

        If VP1 = (-d, 0) and VP2 = (d, 0) with PP = (0, 0):
          Puv = projection of (0,0) onto line from (-d,0) to (d,0) = (0, 0)
          f^2 = d * d - 0 = d^2
          f = d
        """
        d = 2.0
        vp1 = np.array([-d, 0.0])
        vp2 = np.array([d, 0.0])
        pp = np.array([0.0, 0.0])

        f = compute_focal_length(vp1, vp2, pp)
        assert f is not None
        np.testing.assert_allclose(f, d, atol=1e-10)

    def test_vps_on_horizontal(self):
        """VPs on the same horizontal line through PP — obtuse angle from PP.

        VP1 = (-5, 0), VP2 = (3, 0), PP = (0, 0).
        PP projects onto the VP1-VP2 line at itself (it's on the line).
        f^2 = |VP2-Puv| * |VP1-Puv| - |PP-Puv|^2 = 3*5 - 0 = 15
        f = sqrt(15)
        """
        vp1 = np.array([-5.0, 0.0])
        vp2 = np.array([3.0, 0.0])
        pp = np.array([0.0, 0.0])

        f = compute_focal_length(vp1, vp2, pp)
        assert f is not None
        np.testing.assert_allclose(f, np.sqrt(15.0), atol=1e-10)

    def test_known_focal_length(self):
        """Construct VPs that give a known focal length.

        VP1 = (-4, 0), VP2 = (3, 0), PP = (0, 0).
        Both on x-axis through PP. PP is between VPs.
        Puv = (0, 0) (PP is on the line).
        f^2 = 4 * 3 - 0 = 12, f = 2*sqrt(3)
        """
        vp1 = np.array([-4.0, 0.0])
        vp2 = np.array([3.0, 0.0])
        pp = np.array([0.0, 0.0])

        f = compute_focal_length(vp1, vp2, pp)
        assert f is not None
        np.testing.assert_allclose(f, 2.0 * np.sqrt(3.0), atol=1e-10)

    def test_degenerate_returns_none(self):
        """VPs that produce f^2 <= 0 should return None."""
        # VPs at (1, 0) and (0, 1) with PP at origin → f^2 = 0
        vp1 = np.array([1.0, 0.0])
        vp2 = np.array([0.0, 1.0])
        pp = np.array([0.0, 0.0])

        f = compute_focal_length(vp1, vp2, pp)
        assert f is None


# ---------------------------------------------------------------------------
# Rotation matrix tests
# ---------------------------------------------------------------------------

class TestRotationMatrix:
    """Test camera rotation matrix computation."""

    def test_rotation_is_orthonormal(self):
        """The rotation matrix should be orthonormal (R^T R = I)."""
        vp1 = np.array([-4.0, 0.0])
        vp2 = np.array([3.0, 0.0])
        pp = np.array([0.0, 0.0])
        f = compute_focal_length(vp1, vp2, pp)
        assert f is not None

        R = compute_camera_rotation_matrix(vp1, vp2, f, pp)

        np.testing.assert_allclose(R.T @ R, np.eye(3), atol=1e-10)
        np.testing.assert_allclose(np.linalg.det(R), 1.0, atol=1e-10)

    def test_columns_are_unit_vectors(self):
        """Each column of R should be a unit vector."""
        vp1 = np.array([-5.0, 0.0])
        vp2 = np.array([3.0, 0.0])
        pp = np.array([0.0, 0.0])
        f = compute_focal_length(vp1, vp2, pp)

        R = compute_camera_rotation_matrix(vp1, vp2, f, pp)

        for col in range(3):
            np.testing.assert_allclose(
                np.linalg.norm(R[:, col]), 1.0, atol=1e-10
            )


# ---------------------------------------------------------------------------
# Axis assignment tests
# ---------------------------------------------------------------------------

class TestAxisAssignment:
    """Test axis assignment matrix construction."""

    def test_default_y_up(self):
        """Default VP1→+Z, VP2→+X gives +Y as the implicit up axis."""
        A = axis_assignment_matrix("+Z", "+X")

        np.testing.assert_array_equal(A[0], [0, 0, 1])  # +Z
        np.testing.assert_array_equal(A[1], [1, 0, 0])  # +X
        # Cross product: (0,0,1) x (1,0,0) = (0,1,0) = +Y
        np.testing.assert_array_equal(A[2], [0, 1, 0])

    def test_alternative_assignment(self):
        """VP1→+X, VP2→-Z also gives +Y up."""
        A = axis_assignment_matrix("+X", "-Z")

        np.testing.assert_array_equal(A[0], [1, 0, 0])
        np.testing.assert_array_equal(A[1], [0, 0, -1])
        # (1,0,0) x (0,0,-1) = (0,1,0)
        np.testing.assert_array_equal(A[2], [0, 1, 0])

    def test_orthonormal(self):
        """Axis assignment matrix should be orthonormal."""
        A = axis_assignment_matrix("+Z", "+X")
        np.testing.assert_allclose(A @ A.T, np.eye(3), atol=1e-10)


# ---------------------------------------------------------------------------
# View transform tests
# ---------------------------------------------------------------------------

class TestViewTransform:
    """Test full view transform computation."""

    def test_view_transform_is_rigid(self):
        """The 3x3 rotation block of the view transform should be orthonormal."""
        vp1 = np.array([-5.0, 0.0])
        vp2 = np.array([3.0, 0.0])
        pp = np.array([0.0, 0.0])
        f = compute_focal_length(vp1, vp2, pp)
        assert f is not None

        view = compute_view_transform(vp1, vp2, f, pp)

        R = view[:3, :3]
        np.testing.assert_allclose(R.T @ R, np.eye(3), atol=1e-10)
        np.testing.assert_allclose(np.linalg.det(R), 1.0, atol=1e-8)

    def test_view_transform_shape(self):
        """View transform should be 4x4."""
        vp1 = np.array([-5.0, 0.0])
        vp2 = np.array([3.0, 0.0])
        pp = np.array([0.0, 0.0])
        f = compute_focal_length(vp1, vp2, pp)

        view = compute_view_transform(vp1, vp2, f, pp)
        assert view.shape == (4, 4)

    def test_no_translation(self):
        """View transform (rotation only) should have zero translation."""
        vp1 = np.array([-5.0, 0.0])
        vp2 = np.array([3.0, 0.0])
        pp = np.array([0.0, 0.0])
        f = compute_focal_length(vp1, vp2, pp)

        view = compute_view_transform(vp1, vp2, f, pp)
        np.testing.assert_allclose(view[:3, 3], [0.0, 0.0, 0.0], atol=1e-10)
        np.testing.assert_allclose(view[3, :], [0, 0, 0, 1], atol=1e-10)


# ---------------------------------------------------------------------------
# FOV tests
# ---------------------------------------------------------------------------

class TestFOV:
    """Test field of view calculations."""

    def test_fov_from_focal_length_1(self):
        """f = 1 → hFOV = 2*atan(1) = 90°."""
        fov = compute_horizontal_fov(1.0)
        np.testing.assert_allclose(fov, np.pi / 2.0, atol=1e-10)

    def test_fov_from_focal_length_large(self):
        """Larger focal length → narrower FOV."""
        fov_short = compute_horizontal_fov(1.0)
        fov_long = compute_horizontal_fov(2.0)
        assert fov_long < fov_short

    def test_vertical_fov_square(self):
        """For a square image, vertical FOV equals horizontal FOV."""
        h_fov = np.pi / 3.0  # 60 degrees
        v_fov = compute_vertical_fov(h_fov, 1.0)
        np.testing.assert_allclose(v_fov, h_fov, atol=1e-10)

    def test_vertical_fov_wide(self):
        """For a wide image, vertical FOV < horizontal FOV."""
        h_fov = np.pi / 3.0
        v_fov = compute_vertical_fov(h_fov, 16.0 / 9.0)
        assert v_fov < h_fov


# ---------------------------------------------------------------------------
# Full 2VP solve pipeline tests
# ---------------------------------------------------------------------------

class TestSolve2VP:
    """Integration tests for the full 2VP solve pipeline."""

    def test_basic_solve(self):
        """Basic 2VP solve with synthetic VP lines on a 1920x1080 image.

        Construct lines that converge to known VPs, then verify the solver
        produces a valid camera.
        """
        W, H = 1920, 1080

        # VP1 far left (perspective depth lines going left)
        # Two lines converging to pixel (-500, 540) — VP is off-screen left
        vp1_px = np.array([-500.0, 540.0])
        l1_p1 = np.array([200.0, 300.0])
        l1_p2 = vp1_px + (l1_p1 - vp1_px) * 2.0
        l1_p3 = np.array([200.0, 800.0])
        l1_p4 = vp1_px + (l1_p3 - vp1_px) * 2.0

        # VP2 far right
        vp2_px = np.array([2500.0, 540.0])
        l2_p1 = np.array([1700.0, 300.0])
        l2_p2 = vp2_px + (l2_p1 - vp2_px) * 2.0
        l2_p3 = np.array([1700.0, 800.0])
        l2_p4 = vp2_px + (l2_p3 - vp2_px) * 2.0

        result = solve_2vp(
            vp1_lines=(l1_p1, l1_p2, l1_p3, l1_p4),
            vp2_lines=(l2_p1, l2_p2, l2_p3, l2_p4),
            w=W, h=H,
        )

        assert result is not None
        assert result["focal_length"] > 0
        assert 0 < result["horizontal_fov"] < np.pi
        assert result["camera_transform"].shape == (4, 4)

        # Rotation should be orthonormal
        R = result["view_transform"][:3, :3]
        np.testing.assert_allclose(R.T @ R, np.eye(3), atol=1e-8)

    def test_solve_returns_none_for_parallel_lines(self):
        """Parallel lines (no VP) should fail gracefully."""
        W, H = 1920, 1080

        # Both "VP" line pairs are actually parallel
        result = solve_2vp(
            vp1_lines=(
                np.array([100.0, 100.0]), np.array([500.0, 100.0]),
                np.array([100.0, 200.0]), np.array([500.0, 200.0]),
            ),
            vp2_lines=(
                np.array([100.0, 100.0]), np.array([100.0, 500.0]),
                np.array([200.0, 100.0]), np.array([200.0, 500.0]),
            ),
            w=W, h=H,
        )

        assert result is None

    def test_solve_with_origin(self):
        """2VP solve with an origin control point produces a camera with translation."""
        W, H = 1920, 1080

        vp1_px = np.array([-800.0, 540.0])
        l1_p1 = np.array([300.0, 200.0])
        l1_p2 = vp1_px + (l1_p1 - vp1_px) * 3.0
        l1_p3 = np.array([300.0, 900.0])
        l1_p4 = vp1_px + (l1_p3 - vp1_px) * 3.0

        vp2_px = np.array([2800.0, 540.0])
        l2_p1 = np.array([1600.0, 200.0])
        l2_p2 = vp2_px + (l2_p1 - vp2_px) * 3.0
        l2_p3 = np.array([1600.0, 900.0])
        l2_p4 = vp2_px + (l2_p3 - vp2_px) * 3.0

        result = solve_2vp(
            vp1_lines=(l1_p1, l1_p2, l1_p3, l1_p4),
            vp2_lines=(l2_p1, l2_p2, l2_p3, l2_p4),
            w=W, h=H,
            origin_px=np.array([960.0, 540.0]),  # centre of image
        )

        assert result is not None
        # Translation should be non-zero
        t = result["camera_transform"][:3, 3]
        assert np.linalg.norm(t) > 0


# ---------------------------------------------------------------------------
# 1VP solve tests
# ---------------------------------------------------------------------------

class TestSolve1VP:
    """Tests for single vanishing point mode."""

    def test_basic_1vp(self):
        """1VP solve with known focal length and horizon."""
        W, H = 1920, 1080

        # VP1 off-centre to the left (one-point perspective, slightly angled)
        # Two lines converging to pixel (600, 500)
        vp_target = np.array([600.0, 500.0])
        l1_start = np.array([200.0, 300.0])
        l2_start = np.array([200.0, 700.0])
        vp1_lines = (
            l1_start, vp_target,
            l2_start, vp_target,
        )

        # Horizontal horizon line through centre
        horizon_p1 = np.array([0.0, 540.0])
        horizon_p2 = np.array([1920.0, 540.0])

        result = solve_1vp(
            vp1_lines=vp1_lines,
            horizon_p1=horizon_p1,
            horizon_p2=horizon_p2,
            focal_length_mm=50.0,
            sensor_width_mm=36.0,  # full frame
            w=W, h=H,
        )

        assert result is not None
        assert result["focal_length"] > 0
        assert result["camera_transform"].shape == (4, 4)

    def test_1vp_returns_none_for_parallel_vp_lines(self):
        """1VP with parallel lines should fail."""
        W, H = 1920, 1080

        result = solve_1vp(
            vp1_lines=(
                np.array([100.0, 100.0]), np.array([500.0, 100.0]),
                np.array([100.0, 200.0]), np.array([500.0, 200.0]),
            ),
            horizon_p1=np.array([0.0, 540.0]),
            horizon_p2=np.array([1920.0, 540.0]),
            focal_length_mm=50.0,
            sensor_width_mm=36.0,
            w=W, h=H,
        )

        assert result is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
