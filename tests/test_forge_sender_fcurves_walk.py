"""
Unit tests for tools/blender/forge_sender/flame_math._iter_action_fcurves
and the _camera_keyframe_set regression that consumes it.

What we test:
  - The three-tier iterator: bound-slot via bpy_extras.anim_utils helper,
    unbound-slot manual layers/strips/channelbags walk, and the legacy
    action.fcurves fallback for 4.5 legacy-mode actions.
  - _camera_keyframe_set still merges object-level + camera-data-level
    fcurve frames into one sorted unique set (regression for the
    rewritten _drain).

What we DON'T test:
  - Live Blender API (bpy / bpy_extras / mathutils). These tests are
    duck-typed against fakes so they run in the forge conda env (macOS
    dev) without bpy installed. Live API gates are FCV-08 / FCV-09
    (manual UAT on flame-01 with Blender 5.1).

Why this file lives outside test_forge_sender_flame_math.py:
  the existing file pytest.importorskip("bpy") at module top, which
  skips the whole module in the forge env. These tests are bpy-free
  and must run unconditionally — keeping them in a sibling file is
  cleaner than refactoring the importorskip gate.

See memory/blender_slotted_actions_fcurves_api.md for the migration
context (Blender 4.4 introduced slotted actions; 5.0 removed the
legacy proxy; flame-01 hit AttributeError on action.fcurves under 5.1).
"""

from __future__ import annotations

import os
import sys
import types

import pytest

# Add the forge_sender directory to sys.path so ``flame_math`` resolves
# as a top-level module (matches the shim extract_camera.py uses).
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..",
                                "tools", "blender", "forge_sender"))


# Forge env on macOS has neither bpy nor mathutils. flame_math imports
# both at module scope (`import bpy` + `from mathutils import Matrix`),
# so we stub both BEFORE importing flame_math, then REMOVE the stubs
# from sys.modules afterwards so they don't leak into other test
# modules' collection (test_forge_sender_flame_math.py uses
# pytest.importorskip("bpy") and would mistakenly proceed against our
# stub). flame_math itself keeps a reference to the stubs via its
# module-level `import bpy` / `from mathutils import Matrix` lines, so
# `flame_math.bpy.context` still works inside _camera_keyframe_set's
# fallback. The iterator tests are duck-typed and don't exercise that
# fallback path. Live API verification is the manual UAT gate
# (FCV-08, FCV-09).
def _import_flame_math_with_stubs():
    fake_bpy = types.ModuleType("bpy")
    fake_bpy.context = types.SimpleNamespace(
        scene=types.SimpleNamespace(frame_current=0)
    )
    # bpy.types.Object is referenced only as a type annotation
    # (`cam: bpy.types.Object`); under `from __future__ import
    # annotations` the annotation is never evaluated, so an empty
    # types module is enough.
    fake_bpy.types = types.SimpleNamespace(Object=object, Camera=object)

    fake_mathutils = types.ModuleType("mathutils")

    # flame_math computes _R_Z2Y at module-import time via
    # Matrix.Rotation(...).transposed(). We give Matrix.Rotation a stub
    # that returns a placeholder object with .transposed() — the value
    # is never inspected by the iterator tests.
    class _StubMatrix:
        @staticmethod
        def Rotation(_angle, _size, _axis):
            class _Rot:
                def transposed(self):
                    return self
            return _Rot()
    fake_mathutils.Matrix = _StubMatrix

    # Track which keys we add so we can clean up exactly what we added,
    # without disturbing pre-existing entries.
    added_keys = []
    if "bpy" not in sys.modules:
        sys.modules["bpy"] = fake_bpy
        added_keys.append("bpy")
    if "mathutils" not in sys.modules:
        sys.modules["mathutils"] = fake_mathutils
        added_keys.append("mathutils")

    try:
        import flame_math  # noqa: F401  (imported for its side effects + cache)
    finally:
        # Drop the stubs so other test modules' importorskip("bpy") etc.
        # see the env's real (absent) state. flame_math itself keeps
        # references to the stubs via its closure on `import bpy`.
        for key in added_keys:
            sys.modules.pop(key, None)


_import_flame_math_with_stubs()


# =============================================================================
# Test fakes — duck-typed Action / Layer / Strip / Channelbag / FCurve / etc.
# =============================================================================


class _KP:
    def __init__(self, frame: float):
        self.co = (float(frame), 0.0)


class _FCurve:
    def __init__(self, data_path: str = "location", array_index: int = 0,
                 frames=()):
        self.data_path = data_path
        self.array_index = array_index
        self.keyframe_points = [_KP(f) for f in frames]


class _Channelbag:
    def __init__(self, slot_handle: int, fcurves):
        self.slot_handle = slot_handle
        self.fcurves = list(fcurves)


class _Strip:
    def __init__(self, channelbags):
        self.channelbags = list(channelbags)


class _Layer:
    def __init__(self, strips):
        self.strips = list(strips)


class _SlottedAction:
    """Mimics a Blender 5.x slotted-only Action — no .fcurves attribute."""
    def __init__(self, layers):
        self.layers = list(layers)


class _LegacyAction:
    """Mimics a Blender 4.5 legacy-mode Action — has .fcurves shim and
    empty .layers (forces Tier 2 to skip, Tier 3 to fire)."""
    def __init__(self, fcurves):
        self.fcurves = list(fcurves)
        self.layers = []


class _Slot:
    def __init__(self, handle: int):
        self.handle = handle


class _AnimData:
    def __init__(self, action, slot=None):
        self.action = action
        self.action_slot = slot


class _CamData:
    def __init__(self, animation_data=None):
        self.animation_data = animation_data


class _CamObject:
    """Mimics a bpy.types.Object (camera). _camera_keyframe_set walks
    .animation_data and .data.animation_data."""
    def __init__(self, animation_data=None, data_animation_data=None):
        self.animation_data = animation_data
        self.data = _CamData(animation_data=data_animation_data)


# =============================================================================
# Helpers — install / remove a fake bpy_extras.anim_utils into sys.modules
# =============================================================================


def _install_fake_anim_utils(monkeypatch, lookup_fn):
    """Install a fake `bpy_extras.anim_utils` module whose
    `action_get_channelbag_for_slot(action, slot)` calls ``lookup_fn``.

    The helper does a lazy `from bpy_extras import anim_utils` inside
    Tier 1 — so we just need the entry to be importable from
    sys.modules at call time.
    """
    fake_anim_utils = types.ModuleType("bpy_extras.anim_utils")
    fake_anim_utils.action_get_channelbag_for_slot = lookup_fn

    fake_bpy_extras = types.ModuleType("bpy_extras")
    fake_bpy_extras.anim_utils = fake_anim_utils

    monkeypatch.setitem(sys.modules, "bpy_extras", fake_bpy_extras)
    monkeypatch.setitem(sys.modules, "bpy_extras.anim_utils", fake_anim_utils)


def _install_raising_anim_utils(monkeypatch, exc):
    """Install a fake bpy_extras.anim_utils whose
    action_get_channelbag_for_slot raises ``exc``. Used to verify FCV-06
    fall-through to Tier 2."""
    def _raise(_action, _slot):
        raise exc
    _install_fake_anim_utils(monkeypatch, _raise)


# =============================================================================
# Group: TestIterActionFcurves — FCV-01..FCV-06
# =============================================================================


class TestIterActionFcurves:
    def test_tier1_bound_slot_uses_helper(self, monkeypatch):
        """FCV-01: bound slot resolves via bpy_extras.anim_utils helper to
        a single channelbag; helper yields ONLY that slot's fcurves
        (not the cross-slot ones)."""
        # Slot handle 42 has 3 fcurves; slot handle 99 has 2.
        cbag42 = _Channelbag(42, [
            _FCurve("location", 0, [1, 2]),
            _FCurve("location", 1, [1, 2]),
            _FCurve("location", 2, [1, 2]),
        ])
        cbag99 = _Channelbag(99, [
            _FCurve("rotation_euler", 0, [3, 4]),
            _FCurve("rotation_euler", 1, [3, 4]),
        ])
        action = _SlottedAction([_Layer([_Strip([cbag42, cbag99])])])
        anim_data = _AnimData(action=action, slot=_Slot(handle=42))

        # Fake helper resolves slot.handle -> matching channelbag.
        def _fake_lookup(act, slot):
            for layer in act.layers:
                for strip in layer.strips:
                    for cb in strip.channelbags:
                        if cb.slot_handle == slot.handle:
                            return cb
            return None

        _install_fake_anim_utils(monkeypatch, _fake_lookup)

        from flame_math import _iter_action_fcurves
        result = list(_iter_action_fcurves(action, anim_data=anim_data))

        # Should be exactly the 3 fcurves of the slot-42 channelbag.
        assert len(result) == 3
        # Confirm none of the slot-99 fcurves leaked in.
        assert all(fc.data_path == "location" for fc in result)

    def test_tier2_no_slot_walks_all_channelbags(self, monkeypatch):
        """FCV-02: anim_data.action_slot is None → Tier 1 skipped → Tier 2
        emits every fcurve in every channelbag of every strip of every
        layer (all 5 fcurves)."""
        cbag42 = _Channelbag(42, [
            _FCurve("location", 0, [1]),
            _FCurve("location", 1, [1]),
            _FCurve("location", 2, [1]),
        ])
        cbag99 = _Channelbag(99, [
            _FCurve("rotation_euler", 0, [1]),
            _FCurve("rotation_euler", 1, [1]),
        ])
        action = _SlottedAction([_Layer([_Strip([cbag42, cbag99])])])
        anim_data = _AnimData(action=action, slot=None)

        from flame_math import _iter_action_fcurves
        result = list(_iter_action_fcurves(action, anim_data=anim_data))

        assert len(result) == 5

    def test_tier3_legacy_action_fcurves(self):
        """FCV-03: _LegacyAction (empty .layers, populated .fcurves) →
        Tier 2 skips, Tier 3 yields fc1, fc2."""
        fc1 = _FCurve("location", 0, [1, 2])
        fc2 = _FCurve("location", 1, [1, 2])
        action = _LegacyAction([fc1, fc2])
        anim_data = _AnimData(action=action, slot=None)

        from flame_math import _iter_action_fcurves
        result = list(_iter_action_fcurves(action, anim_data=anim_data))

        assert result == [fc1, fc2]

    def test_empty_slotted_action_yields_nothing(self):
        """FCV-04: slotted action with empty layers and no .fcurves →
        helper yields nothing, raises nothing."""
        action = _SlottedAction(layers=[])
        anim_data = _AnimData(action=action, slot=None)

        from flame_math import _iter_action_fcurves
        result = list(_iter_action_fcurves(action, anim_data=anim_data))

        assert result == []

    def test_none_action_yields_nothing(self):
        """FCV-05: _iter_action_fcurves(None, None) → empty iterator,
        no exception."""
        from flame_math import _iter_action_fcurves
        result = list(_iter_action_fcurves(None, anim_data=None))
        assert result == []

    def test_helper_attribute_error_falls_through(self, monkeypatch):
        """FCV-06: bound slot present, but the bpy_extras helper raises
        AttributeError → Tier 1 catches and falls through to Tier 2.
        All 5 fcurves yield (Tier 2 fired), NOT just the bound-slot 3."""
        cbag42 = _Channelbag(42, [
            _FCurve("location", 0, [1]),
            _FCurve("location", 1, [1]),
            _FCurve("location", 2, [1]),
        ])
        cbag99 = _Channelbag(99, [
            _FCurve("rotation_euler", 0, [1]),
            _FCurve("rotation_euler", 1, [1]),
        ])
        action = _SlottedAction([_Layer([_Strip([cbag42, cbag99])])])
        anim_data = _AnimData(action=action, slot=_Slot(handle=42))

        # Helper raises AttributeError — Tier 1 catches, Tier 2 fires.
        _install_raising_anim_utils(monkeypatch, AttributeError("not in 4.3"))

        from flame_math import _iter_action_fcurves
        result = list(_iter_action_fcurves(action, anim_data=anim_data))

        assert len(result) == 5


# =============================================================================
# Group: TestCameraKeyframeSet — FCV-07 (regression for the rewritten _drain)
# =============================================================================


class TestCameraKeyframeSet:
    def test_camera_keyframe_set_combines_object_and_data(self, monkeypatch):
        """FCV-07: _camera_keyframe_set walks BOTH cam.animation_data AND
        cam.data.animation_data, merging unique frames into a sorted list.

        Object-level slotted action has keyframes at {1, 5}.
        Camera-data-level slotted action has keyframes at {1, 10}.
        Merged result must be sorted unique [1, 5, 10]."""
        # Object-level: bound slot 42, fcurves at frames 1 and 5.
        obj_cbag = _Channelbag(42, [
            _FCurve("location", 0, [1, 5]),
        ])
        obj_action = _SlottedAction([_Layer([_Strip([obj_cbag])])])
        obj_anim = _AnimData(action=obj_action, slot=_Slot(handle=42))

        # Data-level: bound slot 7, fcurves at frames 1 and 10.
        data_cbag = _Channelbag(7, [
            _FCurve("lens", 0, [1, 10]),
        ])
        data_action = _SlottedAction([_Layer([_Strip([data_cbag])])])
        data_anim = _AnimData(action=data_action, slot=_Slot(handle=7))

        cam = _CamObject(animation_data=obj_anim,
                         data_animation_data=data_anim)

        # Fake bpy_extras helper resolves slot.handle to the matching cbag.
        def _fake_lookup(act, slot):
            for layer in act.layers:
                for strip in layer.strips:
                    for cb in strip.channelbags:
                        if cb.slot_handle == slot.handle:
                            return cb
            return None

        _install_fake_anim_utils(monkeypatch, _fake_lookup)

        from flame_math import _camera_keyframe_set
        result = _camera_keyframe_set(cam)

        # Sorted unique merge of {1, 5} ∪ {1, 10}.
        assert result == [1, 5, 10]
