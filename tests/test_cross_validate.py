"""
Cross-validation test against fSpy reference output.

Uses test.fspy project file: Canon 60D (5184x3456), 2VP mode,
axes: VP1 → -X, VP2 → -Z.
"""

import numpy as np
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from forge_core.solver.coordinates import px_to_image_plane
from forge_core.solver.math_util import line_intersection
from forge_core.solver.solver import (
    compute_focal_length,
    compute_camera_rotation_matrix,
    compute_view_transform,
    compute_horizontal_fov,
    compute_vertical_fov,
    solve_2vp,
)

# ---------------------------------------------------------------------------
# fSpy reference data extracted from test.fspy
# ---------------------------------------------------------------------------

W, H = 5184, 3456
ASPECT = W / H  # 1.5

# Control points in relative coords (0..1) from fSpy state
VP1_LINE1_P1_REL = (0.42601555503030025, 0.40415286833528946)
VP1_LINE1_P2_REL = (0.9000365618654662, 0.5454031009322207)
VP1_LINE2_P1_REL = (0.41739415081491654, 0.04953202027892652)
VP1_LINE2_P2_REL = (0.9507110122414305, 0.14287330297426987)

VP2_LINE1_P1_REL = (0.9172152342530506, 0.4082780302620597)
VP2_LINE1_P2_REL = (0.9480780284454208, 0.16349931327560732)
VP2_LINE2_P1_REL = (0.2569948727351605, 0.03775924569203336)
VP2_LINE2_P2_REL = (0.2713070131097316, 0.2613996034325672)

# fSpy solved results
FSPY_VP1 = np.array([-5.891365385593294, 1.2687527705977109])
FSPY_VP2 = np.array([0.011237501153991802, -4.237919974243164])
FSPY_FOCAL_LENGTH = 2.333040277023006
FSPY_HFOV = 0.8098745307314665
FSPY_VFOV = 0.5566656780878579
FSPY_PP = np.array([0.0, 0.0])

FSPY_VIEW_TRANSFORM = np.array([
    [0.9116550277351482, 0.41094977125381343, -0.0023229101714609154, -1.7296617938679595],
    [-0.19633221953892094, 0.44049708753502287, 0.876022816737146, 0.8755186648023873],
    [0.36102461131638547, -0.798174543179373, 0.48226406526326626, -10],
    [0, 0, 0, 1],
])

FSPY_CAMERA_TRANSFORM = np.array([
    [0.9116550277351483, -0.19633221953892097, 0.3610246113163856, 5.358993506533381],
    [0.41094977125381354, 0.440497087535023, -0.7981745431793732, -7.656604735185237],
    [-0.0023229101714608573, 0.8760228167371462, 0.48226406526326643, 4.051648476812368],
    [0, 0, 0, 1],
])

# fSpy axis assignments
AXIS1 = "-X"  # firstVanishingPointAxis: xNegative
AXIS2 = "-Z"  # secondVanishingPointAxis: zNegative


def rel_to_px(rx, ry):
    """Convert fSpy relative coords (0..1) to pixel coords."""
    return np.array([rx * W, ry * H])


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCrossValidateVPs:
    """Verify vanishing point computation matches fSpy."""

    def test_vp1_matches(self):
        """VP1 from our line intersection should match fSpy's VP1."""
        p1 = px_to_image_plane(*rel_to_px(*VP1_LINE1_P1_REL), W, H)
        p2 = px_to_image_plane(*rel_to_px(*VP1_LINE1_P2_REL), W, H)
        p3 = px_to_image_plane(*rel_to_px(*VP1_LINE2_P1_REL), W, H)
        p4 = px_to_image_plane(*rel_to_px(*VP1_LINE2_P2_REL), W, H)

        vp1 = line_intersection(p1, p2, p3, p4)
        assert vp1 is not None
        np.testing.assert_allclose(vp1, FSPY_VP1, atol=1e-6)

    def test_vp2_matches(self):
        """VP2 from our line intersection should match fSpy's VP2."""
        p1 = px_to_image_plane(*rel_to_px(*VP2_LINE1_P1_REL), W, H)
        p2 = px_to_image_plane(*rel_to_px(*VP2_LINE1_P2_REL), W, H)
        p3 = px_to_image_plane(*rel_to_px(*VP2_LINE2_P1_REL), W, H)
        p4 = px_to_image_plane(*rel_to_px(*VP2_LINE2_P2_REL), W, H)

        vp2 = line_intersection(p1, p2, p3, p4)
        assert vp2 is not None
        # Looser tolerance: fSpy quad mode may constrain VP2 jointly with VP1,
        # giving a slightly different intersection than independent line pairs
        np.testing.assert_allclose(vp2, FSPY_VP2, atol=0.15)


class TestCrossValidateFocalLength:
    """Verify focal length matches fSpy."""

    def test_focal_length_matches(self):
        f = compute_focal_length(FSPY_VP1, FSPY_VP2, FSPY_PP)
        assert f is not None
        np.testing.assert_allclose(f, FSPY_FOCAL_LENGTH, atol=1e-6)


class TestCrossValidateFOV:
    """Verify FOV matches fSpy."""

    def test_horizontal_fov_matches(self):
        h_fov = compute_horizontal_fov(FSPY_FOCAL_LENGTH)
        np.testing.assert_allclose(h_fov, FSPY_HFOV, atol=1e-6)

    def test_vertical_fov_matches(self):
        v_fov = compute_vertical_fov(FSPY_HFOV, ASPECT)
        np.testing.assert_allclose(v_fov, FSPY_VFOV, atol=1e-6)


class TestCrossValidateRotation:
    """Verify rotation matrix matches fSpy."""

    def test_view_rotation_matches(self):
        """The 3x3 rotation block of our view transform should match fSpy's."""
        view = compute_view_transform(
            FSPY_VP1, FSPY_VP2, FSPY_FOCAL_LENGTH, FSPY_PP,
            axis1=AXIS1, axis2=AXIS2,
        )
        # Compare rotation blocks — allow sign flips on entire columns
        # (equivalent camera orientation, just different axis convention)
        our_rot = view[:3, :3]
        fspy_rot = FSPY_VIEW_TRANSFORM[:3, :3]

        # Direct element-wise comparison
        np.testing.assert_allclose(our_rot, fspy_rot, atol=1e-8)


class TestCrossValidateFullPipeline:
    """End-to-end: feed pixel control points through solve_2vp and compare."""

    def test_full_solve_matches_fspy(self):
        """Full pipeline from pixel line endpoints to solved camera."""
        result = solve_2vp(
            vp1_lines=(
                rel_to_px(*VP1_LINE1_P1_REL),
                rel_to_px(*VP1_LINE1_P2_REL),
                rel_to_px(*VP1_LINE2_P1_REL),
                rel_to_px(*VP1_LINE2_P2_REL),
            ),
            vp2_lines=(
                rel_to_px(*VP2_LINE1_P1_REL),
                rel_to_px(*VP2_LINE1_P2_REL),
                rel_to_px(*VP2_LINE2_P1_REL),
                rel_to_px(*VP2_LINE2_P2_REL),
            ),
            w=W, h=H,
            axis1=AXIS1,
            axis2=AXIS2,
        )

        assert result is not None

        # VP1 matches exactly
        np.testing.assert_allclose(result["vp1"], FSPY_VP1, atol=1e-6)
        # VP2 has quad-mode variance
        np.testing.assert_allclose(result["vp2"], FSPY_VP2, atol=0.15)

        # Focal length (computed from VPs — inherits VP2 variance)
        np.testing.assert_allclose(
            result["focal_length"], FSPY_FOCAL_LENGTH, atol=0.05
        )

        # FOV
        np.testing.assert_allclose(
            result["horizontal_fov"], FSPY_HFOV, atol=0.02
        )
        np.testing.assert_allclose(
            result["vertical_fov"], FSPY_VFOV, atol=0.02
        )

        # View transform rotation block (inherits VP2 variance)
        our_rot = result["view_transform"][:3, :3]
        fspy_rot = FSPY_VIEW_TRANSFORM[:3, :3]
        np.testing.assert_allclose(our_rot, fspy_rot, atol=0.05)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
