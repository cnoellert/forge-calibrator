"""
Unit tests for forge_flame.camera_io's pure-math FOV <-> focal converters.

The flame-API side (export_flame_camera_to_json, import_json_to_flame_camera)
is untested here — it requires a live PyAction camera node. Those paths
will get exercised the first time the user runs them against Flame.

What we test here:
  1. vfov_deg_from_focal agrees with the textbook formula at known pairs.
  2. focal_from_vfov_deg is the exact inverse of vfov_deg_from_focal.
  3. film_back_from_fov_focal recovers the film back from fov + focal.
  4. Input validation rejects invalid values cleanly.

Reference values are drawn from the PASSOFF.md v5 sketch test setup:
  - 5184x3456 plate, 36mm film back, 42mm focal => ~46.4° vfov
    (actually that's the HORIZONTAL value; for VERTICAL with a 24mm vertical
     film back the vfov would be smaller — the converter doesn't care which
     dimension the caller passes, it's just h_sensor / (2·f) geometry.)
"""

import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from forge_flame.camera_io import (  # noqa: E402
    film_back_from_fov_focal,
    focal_from_vfov_deg,
    vfov_deg_from_focal,
)


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
