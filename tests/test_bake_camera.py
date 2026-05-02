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


class _FakeMatrix:
    """Minimal Matrix fake that supports the operations bake_camera.py uses
    at module level (Rotation, Translation, matmul) without returning None."""

    @staticmethod
    def Rotation(angle, size, axis):
        return _FakeMatrix()

    @staticmethod
    def Translation(v):
        return _FakeMatrix()

    def __matmul__(self, other):
        return _FakeMatrix()

    def __rmatmul__(self, other):
        return _FakeMatrix()

    def transposed(self):
        return _FakeMatrix()

    def to_quaternion(self):
        # Returns a fake quaternion with w, x, y, z
        class _FakeQuat:
            w = x = y = z = 0.0
        return _FakeQuat()


class _FakeMathutils:
    Matrix = _FakeMatrix


# Inject stubs so the top-level `import bpy` and `from mathutils import Matrix`
# in bake_camera.py succeed outside Blender.
# We inject ONLY if the real module is absent — and we restore sys.modules
# after the import so the stubs don't pollute other test modules (particularly
# test_forge_sender_flame_math.py which uses pytest.importorskip("mathutils")
# and would get wrong results with a fake).
_fake_bpy = _FakeBpy()
_had_bpy = "bpy" in sys.modules
_had_mathutils = "mathutils" in sys.modules
_prev_bpy = sys.modules.get("bpy")
_prev_mathutils = sys.modules.get("mathutils")

if not _had_bpy:
    sys.modules["bpy"] = _fake_bpy
if not _had_mathutils:
    sys.modules["mathutils"] = _FakeMathutils()

# Now import bake_camera from the tools/blender directory.
_TOOLS_BLENDER = os.path.join(os.path.dirname(__file__), "..", "tools", "blender")
sys.path.insert(0, _TOOLS_BLENDER)

import bake_camera  # noqa: E402

# Restore sys.modules to pre-stub state so other tests are not affected.
# bake_camera is already imported and holds references to the stub objects it
# used — those references remain valid. Other modules that import mathutils/bpy
# after this point will either find the real module (if available) or skip.
if not _had_bpy:
    del sys.modules["bpy"]
if not _had_mathutils:
    del sys.modules["mathutils"]


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


# =============================================================================
# Quick task 260501-dpa: flame_to_blender_scale ladder
# =============================================================================


class TestFlameToBlenderScaleLadder:
    """Ladder validation for the new v5 JSON ``flame_to_blender_scale``
    field. The constant lives at module scope of bake_camera.py and is the
    authoritative source-of-truth on the bake side. ``_validate_flame_to_blender_scale``
    is the bake-side gate; off-ladder values raise SystemExit with the
    full ladder in the error so the artist can self-correct without
    needing to reach for documentation."""

    def test_ladder_constant_shape(self):
        """Canonical ladder must equal the 7-stop log10 set
        (1.0, 10.0, 100.0, 1000.0, 10000.0, 100000.0, 1000000.0) — chosen
        so multiplier (bake) and divisor (extract) are exact-inverse floats."""
        assert bake_camera._FLAME_TO_BLENDER_SCALE_LADDER == (
            1.0, 10.0, 100.0, 1000.0, 10000.0, 100000.0, 1000000.0
        ), (
            f"ladder must be (1.0, 10.0, 100.0, 1000.0, 10000.0, 100000.0, 1000000.0); "
            f"got {bake_camera._FLAME_TO_BLENDER_SCALE_LADDER!r}"
        )

    def test_deprecated_ladder_constant_shape(self):
        """Deprecated ladder must equal (0.01, 0.1) — kept valid bake-side
        for back-compat with .blend files baked under the original
        260501-dpa contract; never offered in the dialog."""
        assert bake_camera._DEPRECATED_FLAME_TO_BLENDER_SCALE_LADDER == (0.01, 0.1), (
            f"deprecated ladder must be (0.01, 0.1); got "
            f"{bake_camera._DEPRECATED_FLAME_TO_BLENDER_SCALE_LADDER!r}"
        )

    @pytest.mark.parametrize("value", [1.0, 10.0, 100.0, 1000.0, 10000.0, 100000.0, 1000000.0])
    def test_validator_accepts_each_ladder_value(self, value):
        """Every canonical ladder value passes validation and round-trips
        unchanged (returned as float)."""
        got = bake_camera._validate_flame_to_blender_scale(value)
        assert got == value
        assert isinstance(got, float)

    @pytest.mark.parametrize("value", [0.01, 0.1])
    def test_validator_accepts_each_deprecated_ladder_value(self, value):
        """Deprecated stops still validate cleanly — proves back-compat
        with .blend files baked under the original 260501-dpa contract."""
        got = bake_camera._validate_flame_to_blender_scale(value)
        assert got == value
        assert isinstance(got, float)

    @pytest.mark.parametrize(
        "value", [0.5, 2.0, 0.05, -1.0, 0.0, 5.0, 50.0, 500.0, 9999.99])
    def test_validator_rejects_off_ladder(self, value):
        """Off-ladder values raise SystemExit. Includes user-likely typos
        (0.5, 5.0) plus degenerate cases (0.0, -1.0). Note: 1000.0 is now
        a CANONICAL stop (Interior) and is not in this rejection set."""
        with pytest.raises(SystemExit):
            bake_camera._validate_flame_to_blender_scale(value)

    def test_validator_rejection_message_lists_ladder(self):
        """The SystemExit message must name the offending value AND
        list every canonical stop AND every deprecated stop, so the
        artist can self-correct without consulting docs."""
        with pytest.raises(SystemExit) as excinfo:
            bake_camera._validate_flame_to_blender_scale(0.5)
        msg = str(excinfo.value)
        assert "0.5" in msg, f"offending value missing from message: {msg!r}"
        # Canonical ladder ends.
        assert "1.0" in msg, f"canonical lower bound missing: {msg!r}"
        assert "1000000.0" in msg, f"canonical upper bound missing: {msg!r}"
        # Deprecated stops listed parenthetically.
        assert "0.01" in msg, f"deprecated lower bound missing: {msg!r}"
        assert "0.1" in msg, f"deprecated upper bound missing: {msg!r}"
