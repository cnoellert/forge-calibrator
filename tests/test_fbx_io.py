"""
Unit tests for forge_flame.fbx_io.

The real flame API isn't importable outside Flame, so these tests
exercise fbx_io against duck-typed fakes. The module's own camera
detection is duck-typed (``hasattr`` on position/rotation/fov/focal), so
the fakes only need to match that shape.

What we test:
  1. ``iter_keyframable_cameras`` filters out non-cameras AND the
     built-in ``Perspective`` camera. The Perspective exclusion is the
     module's primary reason for existing — if this breaks, users hit
     the crash the module was written to prevent.
  2. ``export_action_cameras_to_fbx`` propagates correct kwargs to
     Flame's ``export_fbx``, manages selection (and restores it), and
     raises cleanly on empty-cameras or ``False`` returns.
  3. ``import_fbx_to_action`` guards on missing files, narrows the kwarg
     defaults (cameras=True, lights/models=False, create_media=False),
     and raises cleanly on ``None`` returns.

The live-Flame side — actually calling export_fbx/import_fbx, inspecting
the resulting FBX, verifying keyframe counts — is covered manually via
the forge-bridge probes that live alongside the hook's Apply workflow.
Those probes ran clean on 2026-04-19 during the v6.2 design work
(see PASSOFF.md).
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from forge_flame.fbx_io import (  # noqa: E402
    DEFAULT_PIXEL_TO_UNITS,
    DEFAULT_UNIT_TO_PIXELS,
    export_action_cameras_to_fbx,
    import_fbx_to_action,
    iter_keyframable_cameras,
)


# =============================================================================
# Fakes — minimal PyAttribute / PyCoNode / PyActionNode look-alikes
# =============================================================================


class _Attr:
    """Minimal PyAttribute fake: get_value / set_value."""

    def __init__(self, value):
        self._value = value

    def get_value(self):
        return self._value

    def set_value(self, v):
        self._value = v
        return True


class _Camera:
    """Minimal PyCoNode fake — has the four duck-typing attrs."""

    def __init__(self, name, position=(0.0, 0.0, 0.0), rotation=(0.0, 0.0, 0.0),
                 fov=40.0, focal=22.0):
        self.name = _Attr(name)
        self.position = _Attr(position)
        self.rotation = _Attr(rotation)
        self.fov = _Attr(fov)
        self.focal = _Attr(focal)


class _NonCamera:
    """Non-camera node (e.g. an Axis or Light) — lacks fov/focal attrs."""

    def __init__(self, name):
        self.name = _Attr(name)
        # No position/rotation/fov/focal -> duck-typing filter excludes it.


class _Action:
    """Minimal PyActionNode fake — nodes list, selected_nodes attr, and
    stubs for export_fbx / import_fbx that record the call shape."""

    def __init__(self, nodes):
        self.nodes = list(nodes)
        self.selected_nodes = _Attr([])  # starts empty
        self.export_fbx_calls = []
        self.import_fbx_calls = []
        self.export_fbx_return = True
        self.import_fbx_return = None  # set by test

    def export_fbx(self, path, **kwargs):
        self.export_fbx_calls.append({"path": path,
                                      "selected_at_call": list(self.selected_nodes.get_value()),
                                      **kwargs})
        return self.export_fbx_return

    def import_fbx(self, path, **kwargs):
        self.import_fbx_calls.append({"path": path, **kwargs})
        return self.import_fbx_return


# =============================================================================
# Group 1: iter_keyframable_cameras — the core filter
# =============================================================================


class TestIterKeyframableCameras:
    """Verify the filter excludes non-cameras AND the Perspective camera."""

    def test_filters_non_cameras(self):
        action = _Action([
            _Camera("Default"),
            _NonCamera("Axis1"),
            _NonCamera("Light1"),
        ])
        cams = iter_keyframable_cameras(action)
        names = [c.name.get_value() for c in cams]
        assert names == ["Default"]

    def test_filters_perspective(self):
        action = _Action([
            _Camera("Default"),
            _Camera("Perspective"),  # built-in — must be filtered
            _Camera("MyCam"),
        ])
        cams = iter_keyframable_cameras(action)
        names = [c.name.get_value() for c in cams]
        assert "Perspective" not in names
        assert set(names) == {"Default", "MyCam"}

    def test_empty_action(self):
        action = _Action([])
        assert iter_keyframable_cameras(action) == []

    def test_only_perspective(self):
        """A freshly-created Action has only Default + Perspective. If
        the caller somehow has a pathological Action with ONLY Perspective,
        we return [] — caller is expected to raise on that."""
        action = _Action([_Camera("Perspective")])
        assert iter_keyframable_cameras(action) == []


# =============================================================================
# Group 2: export_action_cameras_to_fbx — selection dance + kwarg shape
# =============================================================================


class TestExport:
    """Verify selection management and the kwargs propagated to Flame."""

    def test_auto_selects_non_perspective_cameras(self, tmp_path):
        action = _Action([_Camera("Default"), _Camera("Perspective"), _Camera("MyCam")])
        out = tmp_path / "cam.fbx"
        result = export_action_cameras_to_fbx(action, str(out))
        assert result == str(out.resolve())
        assert len(action.export_fbx_calls) == 1
        call = action.export_fbx_calls[0]
        # Selection at the moment of the call should be exactly the
        # non-Perspective cameras.
        names = [c.name.get_value() for c in call["selected_at_call"]]
        assert set(names) == {"Default", "MyCam"}

    def test_explicit_camera_list_still_filters_perspective(self, tmp_path):
        """Caller passes an explicit list — Perspective exclusion is
        non-negotiable, filter runs anyway."""
        default = _Camera("Default")
        persp = _Camera("Perspective")
        action = _Action([default, persp])
        out = tmp_path / "cam.fbx"
        export_action_cameras_to_fbx(action, str(out),
                                     cameras=[default, persp])
        names = [c.name.get_value()
                 for c in action.export_fbx_calls[0]["selected_at_call"]]
        assert names == ["Default"]

    def test_kwargs_propagate_to_flame(self, tmp_path):
        action = _Action([_Camera("Default")])
        out = tmp_path / "cam.fbx"
        export_action_cameras_to_fbx(
            action, str(out),
            bake_animation=True,
            pixel_to_units=0.25,
            frame_rate="24 fps",
            export_axes=False,
        )
        call = action.export_fbx_calls[0]
        assert call["only_selected_nodes"] is True
        assert call["bake_animation"] is True
        assert call["pixel_to_units"] == 0.25
        assert call["frame_rate"] == "24 fps"
        assert call["export_axes"] is False

    def test_defaults_match_flame_defaults(self, tmp_path):
        """Our defaults should pass through cleanly as Flame's defaults."""
        action = _Action([_Camera("Default")])
        out = tmp_path / "cam.fbx"
        export_action_cameras_to_fbx(action, str(out))
        call = action.export_fbx_calls[0]
        assert call["pixel_to_units"] == DEFAULT_PIXEL_TO_UNITS
        assert call["frame_rate"] == "23.976 fps"
        assert call["bake_animation"] is True  # our default differs — bake by default
        assert call["export_axes"] is True
        assert call["only_selected_nodes"] is True

    def test_selection_restored_after_export(self, tmp_path):
        """Caller's prior selection must survive the export — we
        mutate selection to drive only_selected_nodes=True, but must
        put it back on exit."""
        cam_a = _Camera("Default")
        cam_b = _Camera("MyCam")
        action = _Action([cam_a, cam_b])
        action.selected_nodes.set_value([cam_b])  # caller had MyCam selected
        out = tmp_path / "cam.fbx"
        export_action_cameras_to_fbx(action, str(out))
        # After the call, selection should be back to [cam_b].
        after = action.selected_nodes.get_value()
        assert after == [cam_b]

    def test_selection_restored_even_when_export_raises(self, tmp_path):
        """If export_fbx returns False we raise, but the finally must
        still restore the selection."""
        cam_a = _Camera("Default")
        action = _Action([cam_a])
        action.selected_nodes.set_value([cam_a])
        action.export_fbx_return = False
        out = tmp_path / "cam.fbx"
        with pytest.raises(RuntimeError, match="returned False"):
            export_action_cameras_to_fbx(action, str(out))
        assert action.selected_nodes.get_value() == [cam_a]

    def test_raises_when_no_keyframable_cameras(self, tmp_path):
        action = _Action([_Camera("Perspective")])  # Only the untouchable one.
        out = tmp_path / "cam.fbx"
        with pytest.raises(ValueError, match="no keyframable cameras"):
            export_action_cameras_to_fbx(action, str(out))
        assert action.export_fbx_calls == []  # didn't attempt the call

    def test_raises_on_flame_false_return(self, tmp_path):
        action = _Action([_Camera("Default")])
        action.export_fbx_return = False
        out = tmp_path / "cam.fbx"
        with pytest.raises(RuntimeError, match="returned False"):
            export_action_cameras_to_fbx(action, str(out))

    def test_creates_parent_directory(self, tmp_path):
        action = _Action([_Camera("Default")])
        out = tmp_path / "nested" / "dirs" / "cam.fbx"
        assert not out.parent.exists()
        export_action_cameras_to_fbx(action, str(out))
        assert out.parent.exists()


# =============================================================================
# Group 3: import_fbx_to_action — guards + kwarg defaults
# =============================================================================


class TestImport:
    """Verify file-existence guards and the narrowed default kwargs."""

    def test_returns_imported_node_list(self, tmp_path):
        in_fbx = tmp_path / "cam.fbx"
        in_fbx.write_text("fake fbx content")
        fake_nodes = [object(), object()]  # the imports (opaque)
        action = _Action([])
        action.import_fbx_return = fake_nodes
        result = import_fbx_to_action(action, str(in_fbx))
        assert result == fake_nodes
        assert len(action.import_fbx_calls) == 1

    def test_missing_file_raises_early(self, tmp_path):
        action = _Action([])
        with pytest.raises(FileNotFoundError):
            import_fbx_to_action(action, str(tmp_path / "nope.fbx"))
        assert action.import_fbx_calls == []

    def test_none_return_raises(self, tmp_path):
        in_fbx = tmp_path / "cam.fbx"
        in_fbx.write_text("fake fbx content")
        action = _Action([])
        action.import_fbx_return = None
        with pytest.raises(RuntimeError, match="returned None"):
            import_fbx_to_action(action, str(in_fbx))

    def test_narrowed_defaults(self, tmp_path):
        """The default kwargs should be narrowed for camera round-trip
        use — cameras yes, everything else no, auto_fit off."""
        in_fbx = tmp_path / "cam.fbx"
        in_fbx.write_text("fake fbx content")
        action = _Action([])
        action.import_fbx_return = []
        import_fbx_to_action(action, str(in_fbx))
        call = action.import_fbx_calls[0]
        assert call["cameras"] is True
        assert call["lights"] is False
        assert call["models"] is False
        assert call["object_properties"] is False
        assert call["create_media"] is False
        assert call["auto_fit"] is False
        assert call["bake_animation"] is False
        assert call["unit_to_pixels"] == DEFAULT_UNIT_TO_PIXELS

    def test_kwargs_overridable(self, tmp_path):
        in_fbx = tmp_path / "cam.fbx"
        in_fbx.write_text("fake fbx content")
        action = _Action([])
        action.import_fbx_return = []
        import_fbx_to_action(action, str(in_fbx),
                             cameras=False, lights=True,
                             unit_to_pixels=5.0)
        call = action.import_fbx_calls[0]
        assert call["cameras"] is False
        assert call["lights"] is True
        assert call["unit_to_pixels"] == 5.0


# =============================================================================
# Group 4: constants sanity — the 1:10 ratio must cancel on round-trip
# =============================================================================


class TestScaleConstants:
    """The export/import default scales are inverses by construction. If
    someone changes one and not the other, round-trip positions will
    drift silently."""

    def test_round_trip_ratio_is_unity(self):
        assert DEFAULT_PIXEL_TO_UNITS * DEFAULT_UNIT_TO_PIXELS == pytest.approx(1.0)
