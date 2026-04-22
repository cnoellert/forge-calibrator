"""
Unit tests for forge_flame.camera_io.

Split into two sections:

1. Pure-math FOV <-> focal converters — no Flame dependency, fully testable.
2. export_flame_camera_to_json — uses duck-typed fakes for Flame PyAttribute
   objects (no live Flame session required). Tests cover the new
   ``custom_properties=`` and ``frame_rate=`` kwargs added in Plan 04.1-02
   (Phase 4.1 items 2 and 5).

What we test here:
  1. vfov_deg_from_focal agrees with the textbook formula at known pairs.
  2. focal_from_vfov_deg is the exact inverse of vfov_deg_from_focal.
  3. film_back_from_fov_focal recovers the film back from fov + focal.
  4. Input validation rejects invalid values cleanly.
  5. export_flame_camera_to_json — frame_rate kwarg emits / suppresses correctly.
  6. export_flame_camera_to_json — custom_properties kwarg emits / suppresses correctly.
  7. export_flame_camera_to_json — existing position/rotation/fov/focal behavior unchanged.

Reference values are drawn from the PASSOFF.md v5 sketch test setup:
  - 5184x3456 plate, 36mm film back, 42mm focal => ~46.4° vfov
    (actually that's the HORIZONTAL value; for VERTICAL with a 24mm vertical
     film back the vfov would be smaller — the converter doesn't care which
     dimension the caller passes, it's just h_sensor / (2·f) geometry.)
"""

import json
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from forge_flame.camera_io import (  # noqa: E402
    export_flame_camera_to_json,
    film_back_from_fov_focal,
    focal_from_vfov_deg,
    vfov_deg_from_focal,
)


# =============================================================================
# Duck-typed fakes for Flame PyAttribute — no live Flame required
# =============================================================================


class _Attr:
    """Minimal PyAttribute fake: just get_value()."""

    def __init__(self, value):
        self._value = value

    def get_value(self):
        return self._value


class _FakeCam:
    """Minimal fake for a Flame Action camera node.

    Mimics the four attributes that export_flame_camera_to_json reads:
    position, rotation, fov, focal. Uses _Attr fakes so get_value() works.
    """

    def __init__(
        self,
        position=(0.0, 0.0, 4747.64),
        rotation=(0.0, 0.0, 0.0),
        fov=40.0,
        focal=21.74,
    ):
        self.position = _Attr(position)
        self.rotation = _Attr(rotation)
        self.fov = _Attr(fov)
        self.focal = _Attr(focal)


# =============================================================================
# Group 1: textbook values
# =============================================================================


class TestVfovFromFocal:
    """Spot-check vfov_deg_from_focal against hand-computed textbook values."""

    def test_36mm_sensor_50mm_lens(self):
        # Classic "normal" lens on full-frame: 36mm sensor, 50mm focal.
        # vfov = 2 * atan(36 / 100) ≈ 39.598°
        got = vfov_deg_from_focal(50.0, 36.0)
        assert math.isclose(got, 39.59775, abs_tol=1e-4)

    def test_36mm_sensor_42mm_lens(self):
        # PASSOFF sketch test setup: 36mm film back, 42mm focal.
        # vfov = 2 * atan(36 / 84) ≈ 46.3972°
        got = vfov_deg_from_focal(42.0, 36.0)
        assert math.isclose(got, 46.39718, abs_tol=1e-4)

    def test_wide_lens(self):
        # 24mm film back, 14mm focal — ultrawide.
        # vfov = 2 * atan(24 / 28) ≈ 81.2026°
        got = vfov_deg_from_focal(14.0, 24.0)
        assert math.isclose(got, 81.20259, abs_tol=1e-4)

    def test_telephoto(self):
        # 36mm film back, 200mm focal.
        # vfov = 2 * atan(36 / 400) ≈ 10.2855°
        got = vfov_deg_from_focal(200.0, 36.0)
        assert math.isclose(got, 10.28553, abs_tol=1e-4)


# =============================================================================
# Group 2: inverse property — focal_from_vfov is the exact inverse
# =============================================================================


class TestInverse:
    """focal_from_vfov_deg(vfov_deg_from_focal(f, b), b) == f for any sane (f, b)."""

    @pytest.mark.parametrize("focal,film_back", [
        (14.0, 24.0),
        (24.0, 36.0),
        (35.0, 36.0),
        (42.0, 36.0),
        (50.0, 36.0),
        (85.0, 24.0),
        (200.0, 36.0),
        (600.0, 36.0),
    ])
    def test_roundtrip_focal(self, focal, film_back):
        vfov = vfov_deg_from_focal(focal, film_back)
        recovered = focal_from_vfov_deg(vfov, film_back)
        assert math.isclose(recovered, focal, rel_tol=1e-12)

    @pytest.mark.parametrize("vfov,film_back", [
        (10.0, 36.0),
        (25.0, 24.0),
        (46.4, 36.0),
        (60.0, 36.0),
        (90.0, 36.0),
        (120.0, 36.0),
    ])
    def test_roundtrip_vfov(self, vfov, film_back):
        focal = focal_from_vfov_deg(vfov, film_back)
        recovered = vfov_deg_from_focal(focal, film_back)
        assert math.isclose(recovered, vfov, rel_tol=1e-12)


# =============================================================================
# Group 3: film-back recovery from fov + focal (export-side helper)
# =============================================================================


class TestFilmBackRecovery:
    """film_back_from_fov_focal should recover the film back if you give it
    a self-consistent (fov, focal) pair."""

    @pytest.mark.parametrize("focal,film_back", [
        (14.0, 24.0),
        (24.0, 36.0),
        (35.0, 36.0),
        (42.0, 36.0),
        (200.0, 36.0),
    ])
    def test_recovery(self, focal, film_back):
        vfov = vfov_deg_from_focal(focal, film_back)
        recovered = film_back_from_fov_focal(vfov, focal)
        assert math.isclose(recovered, film_back, rel_tol=1e-12)


# =============================================================================
# Group 4: input validation
# =============================================================================


class TestInputValidation:
    """Invalid inputs should raise ValueError with a clear message, not
    silently return nonsense (e.g., from dividing by zero)."""

    def test_focal_zero_rejected(self):
        with pytest.raises(ValueError, match="focal_mm"):
            vfov_deg_from_focal(0.0, 36.0)

    def test_focal_negative_rejected(self):
        with pytest.raises(ValueError, match="focal_mm"):
            vfov_deg_from_focal(-42.0, 36.0)

    def test_film_back_zero_rejected(self):
        with pytest.raises(ValueError, match="film_back_mm"):
            vfov_deg_from_focal(50.0, 0.0)

    def test_vfov_zero_rejected(self):
        with pytest.raises(ValueError, match="vfov_deg"):
            focal_from_vfov_deg(0.0, 36.0)

    def test_vfov_180_rejected(self):
        with pytest.raises(ValueError, match="vfov_deg"):
            focal_from_vfov_deg(180.0, 36.0)

    def test_vfov_over_180_rejected(self):
        with pytest.raises(ValueError, match="vfov_deg"):
            focal_from_vfov_deg(200.0, 36.0)


# =============================================================================
# Group 5: export_flame_camera_to_json — frame_rate + custom_properties kwargs
# (Plan 04.1-02 — Phase 4.1 items 2 and 5)
# =============================================================================


class TestExportFlameCameraToJson:
    """Tests for export_flame_camera_to_json using duck-typed _FakeCam fakes.

    Tests cover:
    - A1: frame_rate="24 fps" -> top-level "frame_rate" key in JSON.
    - A2: frame_rate=None (default) -> no "frame_rate" key emitted.
    - A3: custom_properties dict -> top-level "custom_properties" key in JSON.
    - A4: custom_properties=None (default) -> no "custom_properties" key.
    - A5: custom_properties={} (empty) -> no "custom_properties" key.
    - A6: existing position/rotation/fov/focal behavior unchanged (regression).
    """

    def _call(self, tmp_path, **kwargs):
        """Helper: call export_flame_camera_to_json with a _FakeCam and return
        the on-disk JSON dict."""
        cam = _FakeCam(
            position=(10.0, 20.0, 4747.64),
            rotation=(1.0, 2.0, 3.0),
            fov=40.0,
            focal=21.74,
        )
        out = str(tmp_path / "out.json")
        export_flame_camera_to_json(
            cam, out,
            frame=1001,
            width=1920,
            height=1080,
            film_back_mm=36.0,
            **kwargs,
        )
        with open(out) as f:
            return json.load(f)

    def test_a1_frame_rate_emitted(self, tmp_path):
        """A1: frame_rate='24 fps' produces top-level 'frame_rate' key in JSON."""
        data = self._call(tmp_path, frame_rate="24 fps")
        assert "frame_rate" in data
        assert data["frame_rate"] == "24 fps"

    def test_a2_frame_rate_none_omitted(self, tmp_path):
        """A2: frame_rate=None (default) -> no 'frame_rate' key in JSON."""
        data = self._call(tmp_path)
        assert "frame_rate" not in data

    def test_a3_custom_properties_emitted(self, tmp_path):
        """A3: custom_properties dict -> top-level 'custom_properties' key."""
        props = {
            "forge_bake_action_name": "Ax",
            "forge_bake_camera_name": "Cx",
        }
        data = self._call(tmp_path, custom_properties=props)
        assert "custom_properties" in data
        assert data["custom_properties"] == {
            "forge_bake_action_name": "Ax",
            "forge_bake_camera_name": "Cx",
        }

    def test_a4_custom_properties_none_omitted(self, tmp_path):
        """A4: custom_properties=None (default) -> no 'custom_properties' key."""
        data = self._call(tmp_path)
        assert "custom_properties" not in data

    def test_a5_custom_properties_empty_dict_omitted(self, tmp_path):
        """A5: custom_properties={} (empty) -> no 'custom_properties' key.

        Mirrors fbx_ascii.py:874 truthy-check behavior — empty dict is
        treated the same as None for backward compatibility."""
        data = self._call(tmp_path, custom_properties={})
        assert "custom_properties" not in data

    def test_a6_core_fields_unchanged(self, tmp_path):
        """A6: existing position/rotation/fov/focal fields are still correct
        when new kwargs are added (regression sentinel)."""
        data = self._call(tmp_path, frame_rate="25 fps",
                          custom_properties={"k": "v"})
        assert data["width"] == 1920
        assert data["height"] == 1080
        assert math.isclose(data["film_back_mm"], 36.0, rel_tol=1e-9)
        assert len(data["frames"]) == 1
        frame = data["frames"][0]
        assert frame["frame"] == 1001
        assert math.isclose(frame["position"][0], 10.0)
        assert math.isclose(frame["position"][1], 20.0)
        assert math.isclose(frame["rotation_flame_euler"][0], 1.0)
        # focal_mm recomputed from fov=40 + film_back=36 (caller pinned)
        assert math.isclose(frame["focal_mm"], 36.0 / (2.0 * math.tan(math.radians(40.0) / 2.0)), rel_tol=1e-6)
