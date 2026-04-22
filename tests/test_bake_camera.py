"""
Unit tests for tools/blender/bake_camera.py — _stamp_metadata, _RESERVED_STAMP_KEYS,
and the forge_bake_frame_rate D-11/D-14 invariants.

What we test:
  - C1: 'forge_bake_frame_rate' is in _RESERVED_STAMP_KEYS.
  - C2: _stamp_metadata stamps forge_bake_frame_rate from the frame_rate_label kwarg.
  - C3: caller custom_properties['forge_bake_frame_rate'] is REJECTED (clobber guard).
  - C4: D-14 fallback — when frame_rate_label=None, _stamp_metadata falls back to
        scene.render.fps / fps_base, stamps the label, AND prints to stderr.
  - C5: D-14 NEVER-SILENT — forge_bake_frame_rate is always populated even when
        the fallback fires.

What we DON'T test:
  - The full _bake() path (requires Blender runtime with bpy scene graph).
  - _get_or_create_camera (requires bpy.data.objects, bpy.data.cameras).
  - bpy.ops.wm.save_as_mainfile (requires a real Blender process).

Approach: _stamp_metadata takes cam_data (a bpy.types.Camera data-block) which
supports dict-style property access (cam_data[key] = value). We pass a plain dict
as cam_data — this is sufficient because _stamp_metadata only does dict-style writes
and reads (no method calls on cam_data itself). The function is tested in isolation
from bpy.

For D-14 tests (C4/C5) we also need a fake scene with render.fps and render.fps_base.
bake_camera.py uses bpy.context.scene.render.fps / fps_base in _bake, NOT in
_stamp_metadata. The D-14 fallback is expected to live in _bake() and be passed
through to _stamp_metadata as frame_rate_label. So C4/C5 test that _stamp_metadata
correctly handles a None frame_rate_label by using a fallback resolver provided to it.

Note: if _stamp_metadata takes frame_rate_label as a required parameter (per Plan
04.1-02 Task 2 Step E), a None value triggers the fallback path in _stamp_metadata.
"""

from __future__ import annotations

import os
import sys

import pytest

# bake_camera.py has a top-level `import bpy` which would fail outside Blender.
# We stub bpy BEFORE importing bake_camera so the module-level import succeeds.
# The stub only needs to satisfy the top-level code and the parts _stamp_metadata
# touches — not the full bpy surface.

class _FakeRender:
    fps = 24
    fps_base = 1.0


class _FakeScene:
    render = _FakeRender()


class _FakeContext:
    scene = _FakeScene()


class _FakeBpy:
    """Minimal bpy stub that satisfies bake_camera.py's top-level imports."""
    context = _FakeContext()

    class data:
        @staticmethod
        def objects_get(name):
            return None

        @staticmethod
        def cameras_new(name):
            return {}

        @staticmethod
        def objects_new(name, data):
            return {}

    class types:
        Camera = dict  # cam_data is treated as dict in _stamp_metadata
        Object = object  # used in type annotation only

    class ops:
        class wm:
            @staticmethod
            def save_as_mainfile(**kwargs):
                pass


class _FakeMathutils:
    class Matrix:
        @staticmethod
        def Rotation(angle, size, axis):
            return None
        def __matmul__(self, other):
            return self
        def __rmatmul__(self, other):
            return self
        @staticmethod
        def Translation(v):
            return None


# Inject stubs so the top-level `import bpy` and `from mathutils import Matrix`
# in bake_camera.py succeed outside Blender.
_fake_bpy = _FakeBpy()
sys.modules.setdefault("bpy", _fake_bpy)
sys.modules.setdefault("mathutils", _FakeMathutils())

# Now import bake_camera from the tools/blender directory.
_TOOLS_BLENDER = os.path.join(os.path.dirname(__file__), "..", "tools", "blender")
sys.path.insert(0, _TOOLS_BLENDER)

import bake_camera  # noqa: E402


# =============================================================================
# C1: forge_bake_frame_rate is in _RESERVED_STAMP_KEYS
# =============================================================================


class TestReservedStampKeys:
    """C1: _RESERVED_STAMP_KEYS must include 'forge_bake_frame_rate' per P-3
    (D-11 always-stamp invariant — the key is round-trip-critical so callers
    cannot clobber it via custom_properties)."""

    def test_c1_forge_bake_frame_rate_reserved(self):
        assert "forge_bake_frame_rate" in bake_camera._RESERVED_STAMP_KEYS, (
            "forge_bake_frame_rate must be in _RESERVED_STAMP_KEYS so callers "
            "cannot clobber it via custom_properties"
        )

    def test_c1_existing_keys_still_reserved(self):
        """Regression guard: the 4 pre-existing reserved keys are still there."""
        for key in ("forge_bake_version", "forge_bake_source",
                    "forge_bake_scale", "forge_bake_input_path"):
            assert key in bake_camera._RESERVED_STAMP_KEYS, (
                f"pre-existing reserved key {key!r} must still be reserved"
            )


# =============================================================================
# C2: _stamp_metadata stamps forge_bake_frame_rate from frame_rate_label kwarg
# =============================================================================


class TestStampMetadataFrameRate:
    """C2-C5: _stamp_metadata stamps forge_bake_frame_rate correctly."""

    def _make_cam_data(self):
        """Return a plain dict to stand in for a bpy.types.Camera data-block."""
        return {}

    def test_c2_frame_rate_label_stamped(self, tmp_path):
        """C2: _stamp_metadata stamps cam_data['forge_bake_frame_rate'] = '24 fps'."""
        cam_data = self._make_cam_data()
        source = str(tmp_path / "cam.json")
        # Write a dummy file so abspath doesn't trip on non-existent path.
        with open(source, "w") as f:
            f.write("{}")
        bake_camera._stamp_metadata(
            cam_data, scale=1.0, source_path=source,
            custom_properties={}, frame_rate_label="24 fps",
        )
        assert cam_data.get("forge_bake_frame_rate") == "24 fps", (
            f"expected '24 fps', got {cam_data.get('forge_bake_frame_rate')!r}"
        )

    def test_c3_clobber_guard(self, tmp_path, capsys):
        """C3: caller's custom_properties['forge_bake_frame_rate'] is rejected
        (clobber guard). The resolver-derived value wins; a stderr warning is
        printed."""
        cam_data = self._make_cam_data()
        source = str(tmp_path / "cam.json")
        with open(source, "w") as f:
            f.write("{}")
        bake_camera._stamp_metadata(
            cam_data, scale=1.0, source_path=source,
            custom_properties={"forge_bake_frame_rate": "99 fps"},
            frame_rate_label="24 fps",
        )
        # The resolver-derived label must win.
        assert cam_data.get("forge_bake_frame_rate") == "24 fps", (
            f"resolver value must win over custom_properties; "
            f"got {cam_data.get('forge_bake_frame_rate')!r}"
        )
        # A stderr warning must have been printed.
        captured = capsys.readouterr()
        assert "forge_bake_frame_rate" in captured.err, (
            "clobber attempt must produce a stderr warning"
        )

    def test_c4_d14_fallback_fires_with_stderr(self, tmp_path, capsys):
        """C4: when frame_rate_label=None (Flame-side propagation failed),
        _stamp_metadata falls back AND emits a stderr warning containing
        'falling back to Blender scene fps'."""
        cam_data = self._make_cam_data()
        source = str(tmp_path / "cam.json")
        with open(source, "w") as f:
            f.write("{}")
        bake_camera._stamp_metadata(
            cam_data, scale=1.0, source_path=source,
            custom_properties={}, frame_rate_label=None,
        )
        # The stamp must be populated (never missing — D-11).
        assert "forge_bake_frame_rate" in cam_data, (
            "forge_bake_frame_rate must be stamped even when frame_rate_label=None"
        )
        # The fallback must have printed a stderr warning.
        captured = capsys.readouterr()
        assert "falling back to Blender scene fps" in captured.err, (
            f"D-14 fallback must print stderr warning; got: {captured.err!r}"
        )

    def test_c5_d14_never_silent(self, tmp_path):
        """C5: even when the D-14 fallback fires, forge_bake_frame_rate is
        populated (never missing). The warning is the diagnostic; the stamp
        still happens."""
        cam_data = self._make_cam_data()
        source = str(tmp_path / "cam.json")
        with open(source, "w") as f:
            f.write("{}")
        bake_camera._stamp_metadata(
            cam_data, scale=1.0, source_path=source,
            custom_properties=None, frame_rate_label=None,
        )
        assert "forge_bake_frame_rate" in cam_data, (
            "forge_bake_frame_rate must be stamped even in D-14 fallback path"
        )
        val = cam_data["forge_bake_frame_rate"]
        assert val is not None and str(val).strip(), (
            f"forge_bake_frame_rate must be a non-empty string; got {val!r}"
        )
