"""
Unit tests for tools/blender/forge_sender/flame_math.py.

What we test:
  - Euler decomposition matches forge_core.math.rotations numerically
    (the numpy reference this module's mathutils parallel implementation
    must track byte-for-byte, per memory/flame_rotation_convention.md).
  - Axis-swap matrix is the transposed Rx(+90°).
  - build_v5_payload returns the v5 schema shape (keys + frame dict
    keys) and responds to scale_override.

What we don't test:
  - Live Blender scene traversal (requires Blender runtime).
  - bpy operator / panel behavior (Plan 02-03 scope).

If the conda forge env lacks ``mathutils`` / ``bpy`` (both provided by
the ``bpy`` wheel), the whole module skips cleanly — the Blender
subprocess guards the math live via tests/test_blender_roundtrip.py
plus extract_camera's roundtrip_selftest.sh.
"""

from __future__ import annotations

import math
import os
import sys

import numpy as np
import pytest

# Math imports (always available).
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from forge_flame.adapter import (  # noqa: E402
    compute_flame_euler_zyx,
    flame_euler_to_cam_rot,
)

# Gate on Blender's Python APIs — if missing, skip the whole module.
pytest.importorskip("mathutils")
pytest.importorskip("bpy")

# Add the forge_sender directory to sys.path so ``flame_math`` resolves
# as a top-level module (matches the shim extract_camera.py uses).
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..",
                                "tools", "blender", "forge_sender"))

from flame_math import (  # noqa: E402
    _rot3_to_flame_euler_deg,
    _R_Z2Y,
    build_v5_payload,
)
from mathutils import Matrix  # noqa: E402


# =============================================================================
# Helpers — numpy-parallel reference for the Flame Euler composition
# =============================================================================


def _compose_flame_rotation_np(rx_deg, ry_deg, rz_deg) -> np.ndarray:
    """Flame convention: R = Rz(rz) · Ry(-ry) · Rx(-rx). Matches
    forge_core.math.rotations.flame_euler_to_cam_rot exactly; we use
    it here as the ground-truth matrix feeder for the decomposition
    test."""
    return flame_euler_to_cam_rot((rx_deg, ry_deg, rz_deg))


def _np_to_mathutils_matrix(R_np: np.ndarray) -> "Matrix":
    """Wrap a 3x3 numpy rotation as a mathutils.Matrix so flame_math's
    helper can consume it. flame_math indexes R[row][col]; mathutils
    Matrix does too, so this is a direct wrap."""
    return Matrix(tuple(tuple(float(x) for x in row) for row in R_np))


# =============================================================================
# Group 1: _rot3_to_flame_euler_deg
# =============================================================================


class TestRot3ToFlameEulerDeg:
    def test_rot3_to_flame_euler_deg_zero_rotation(self):
        """Identity in → zero triple out (within tight tolerance)."""
        R = Matrix.Identity(3)
        rx, ry, rz = _rot3_to_flame_euler_deg(R)
        assert math.isclose(rx, 0.0, abs_tol=1e-10)
        assert math.isclose(ry, 0.0, abs_tol=1e-10)
        assert math.isclose(rz, 0.0, abs_tol=1e-10)

    @pytest.mark.parametrize("triple", [
        (10.0, 20.0, 30.0),
        (-15.5, 45.0, -70.25),
        (5.0, 0.0, 0.0),
        (0.0, 30.0, 0.0),
        (0.0, 0.0, -60.0),
        (-80.0, 20.0, 45.0),  # non-gimbal pitch close to but not at ±90°
    ])
    def test_rot3_to_flame_euler_deg_roundtrip(self, triple):
        """Compose a known Euler via the numpy reference, decompose with
        the mathutils helper, assert recovered values match to 1e-6."""
        rx_in, ry_in, rz_in = triple
        R_np = _compose_flame_rotation_np(rx_in, ry_in, rz_in)
        R_m = _np_to_mathutils_matrix(R_np)

        rx_out, ry_out, rz_out = _rot3_to_flame_euler_deg(R_m)

        assert math.isclose(rx_out, rx_in, abs_tol=1e-6)
        assert math.isclose(ry_out, ry_in, abs_tol=1e-6)
        assert math.isclose(rz_out, rz_in, abs_tol=1e-6)

    def test_rot3_to_flame_euler_deg_gimbal_case(self):
        """ry ≈ +90° triggers the gimbal branch (cb ≤ 1e-6) and pins
        rx=0. The recovered rz absorbs the combined rx+rz rotation."""
        R_np = _compose_flame_rotation_np(0.0, 90.0, 0.0)
        R_m = _np_to_mathutils_matrix(R_np)

        rx, ry, rz = _rot3_to_flame_euler_deg(R_m)
        assert rx == 0.0
        # ry should be very close to 90°
        assert math.isclose(ry, 90.0, abs_tol=1e-4)


# =============================================================================
# Group 2: _R_Z2Y axis-swap matrix
# =============================================================================


class TestRZ2Y:
    def test_R_Z2Y_matches_transposed_rx90(self):
        """_R_Z2Y must be the transpose of Rx(+90°). Flame (Y-up) →
        Blender (Z-up) is Rx(+90°); the inverse (used at extract time)
        is the transpose. Identity smoke test: shape + equality."""
        expected = Matrix.Rotation(math.radians(90), 4, 'X').transposed()
        # Element-wise compare — mathutils Matrix equality via tuple form.
        for i in range(4):
            for j in range(4):
                assert math.isclose(_R_Z2Y[i][j], expected[i][j],
                                    abs_tol=1e-12), (
                    f"cell [{i}][{j}] mismatch: "
                    f"{_R_Z2Y[i][j]} vs {expected[i][j]}"
                )


# =============================================================================
# Group 3: build_v5_payload
# =============================================================================


class _FakeAttr:
    """Minimal placeholder for bpy attribute-like objects referenced by
    build_v5_payload. The function only touches them through specific
    attribute / dict access patterns; these fakes expose exactly that."""
    def __init__(self, value):
        self._v = value


class _FakeAnimationData:
    """Mirror bpy.types.AnimationData just enough for
    _camera_keyframe_set's duck-typed check (``anim is None or
    anim.action is None``)."""
    def __init__(self):
        self.action = None  # no curves → keyframe_set falls back to scene.frame_current


class _FakeCamData(dict):
    """dict-like (for custom props `forge_bake_scale` lookup) with
    lens/sensor_height attributes + animation_data slot."""
    def __init__(self, *, lens=35.0, sensor_height=16.0):
        super().__init__()
        self.lens = lens
        self.sensor_height = sensor_height
        self.animation_data = None


class _FakeCamera:
    """Blender Object-shaped fake — type='CAMERA', .data, .animation_data,
    .matrix_world. Only the attrs build_v5_payload actually reads are
    populated."""
    def __init__(self, *, matrix_world=None, data=None, name="Camera"):
        self.type = 'CAMERA'
        self.name = name
        self.matrix_world = matrix_world if matrix_world is not None \
            else Matrix.Identity(4)
        self.data = data if data is not None else _FakeCamData()
        self.animation_data = None


class _FakeRender:
    def __init__(self, *, resolution_x=1920, resolution_y=1080):
        self.resolution_x = resolution_x
        self.resolution_y = resolution_y


class _FakeScene:
    def __init__(self, *, frame_current=0, resolution=(1920, 1080)):
        self.frame_current = frame_current
        self.render = _FakeRender(resolution_x=resolution[0],
                                  resolution_y=resolution[1])

    def frame_set(self, frame):
        self.frame_current = int(frame)


class _FakeContext:
    def __init__(self, scene=None):
        self.scene = scene if scene is not None else _FakeScene()


@pytest.fixture
def patched_bpy_context(monkeypatch):
    """Patch flame_math.bpy.context so build_v5_payload has a scene
    without needing a real Blender runtime."""
    import flame_math  # module already imported at top of file
    fake_scene = _FakeScene()
    fake_context = _FakeContext(scene=fake_scene)
    monkeypatch.setattr(flame_math.bpy, "context", fake_context)
    return fake_scene


class TestBuildV5Payload:
    def test_build_v5_payload_shape(self, patched_bpy_context):
        """Output dict has exactly {width, height, film_back_mm, frames}
        and each frame has {frame, position, rotation_flame_euler,
        focal_mm}."""
        cam = _FakeCamera()
        cam.data["forge_bake_scale"] = 1000.0

        out = build_v5_payload(cam)

        assert set(out.keys()) == {"width", "height", "film_back_mm", "frames"}
        assert out["width"] == 1920
        assert out["height"] == 1080
        assert out["film_back_mm"] == pytest.approx(16.0)
        assert isinstance(out["frames"], list)
        assert len(out["frames"]) >= 1
        for frame_dict in out["frames"]:
            assert set(frame_dict.keys()) == {
                "frame", "position", "rotation_flame_euler", "focal_mm"
            }

    def test_build_v5_payload_scale_override(self, patched_bpy_context):
        """scale_override=2.0 multiplies the translation components by
        2.0 (bypasses the stamped forge_bake_scale)."""
        # Camera at translation (10, 20, 30) in Blender frame.
        m = Matrix.Translation((10.0, 20.0, 30.0))
        cam = _FakeCamera(matrix_world=m)
        cam.data["forge_bake_scale"] = 999.0  # must be ignored by override

        out = build_v5_payload(cam, scale_override=2.0)

        # _R_Z2Y @ translation flips Y/Z; validate the scale factor by
        # checking that the magnitude of the translation vector equals
        # 2.0 * sqrt(10² + 20² + 30²).
        [px, py, pz] = out["frames"][0]["position"]
        magnitude = math.sqrt(px * px + py * py + pz * pz)
        expected = 2.0 * math.sqrt(10 * 10 + 20 * 20 + 30 * 30)
        assert math.isclose(magnitude, expected, rel_tol=1e-9)
