"""Unit tests for tools/blender/forge_sender/preflight.py.

What we test:
  - All four D-09 Tier 1 failure paths return the exact UI-SPEC copy
  - Happy path returns None
  - First-missing-key rule (both missing → name only the first)

What we don't test:
  - Live bpy context (checker verifies in Blender during Plan 04 E2E)
  - Operator poll()/execute() wiring (tested indirectly via __init__.py)
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..",
                                "tools", "blender", "forge_sender"))

from preflight import check, _REQUIRED_STAMPED_KEYS  # noqa: E402


class _FakeData(dict):
    """Dict subclass to mimic bpy camera data-block custom-property access:
    ``data["key"]`` works, ``data.get("key")`` works, ``"key" in data``
    works. bpy ID data-blocks expose exactly this interface for custom
    props, which is why preflight.check can be unit-tested with a plain
    dict subclass."""
    pass


class _FakeObject:
    def __init__(self, type_: str = "CAMERA", data: dict = None):
        self.type = type_
        self.data = _FakeData(data or {})


class _FakeContext:
    def __init__(self, active_object=None):
        self.active_object = active_object


class TestNoActiveObject:
    def test_returns_tier_1a_copy(self):
        ctx = _FakeContext(active_object=None)
        msg = check(ctx)
        assert msg is not None
        assert "no active object" in msg
        assert msg.startswith("Send to Flame: no active object")
        # UI-SPEC fix-hint suffix after em-dash.
        assert "select a forge-baked camera in the 3D viewport" in msg


class TestNotACamera:
    def test_mesh_returns_tier_1b_copy(self):
        ctx = _FakeContext(_FakeObject(type_="MESH"))
        msg = check(ctx)
        assert msg is not None
        assert "active object is not a camera" in msg
        assert msg.startswith("Send to Flame: active object is not a camera")

    def test_empty_string_type_also_fails(self):
        # Duck-typing guard: if .type is missing or falsy, still fail at
        # Tier 1(b). getattr(obj, "type", None) returns None, which != 'CAMERA'.
        ctx = _FakeContext(_FakeObject(type_=""))
        msg = check(ctx)
        assert msg is not None
        assert "active object is not a camera" in msg


class TestMissingStampedKey:
    def test_missing_action_name(self):
        data = {"forge_bake_camera_name": "cam1",
                "forge_bake_source": "flame"}
        ctx = _FakeContext(_FakeObject(data=data))
        msg = check(ctx)
        assert msg is not None
        assert "'forge_bake_action_name'" in msg
        assert "active camera is missing" in msg

    def test_missing_camera_name_only(self):
        data = {"forge_bake_action_name": "Action",
                "forge_bake_source": "flame"}
        ctx = _FakeContext(_FakeObject(data=data))
        msg = check(ctx)
        assert msg is not None
        assert "'forge_bake_camera_name'" in msg
        assert "'forge_bake_action_name'" not in msg

    def test_both_missing_reports_first(self):
        # UI-SPEC: "If both are missing, name only the first."
        data = {"forge_bake_source": "flame"}
        ctx = _FakeContext(_FakeObject(data=data))
        msg = check(ctx)
        assert msg is not None
        # First in _REQUIRED_STAMPED_KEYS is forge_bake_action_name.
        assert "'forge_bake_action_name'" in msg
        assert "'forge_bake_camera_name'" not in msg


class TestBadProvenance:
    def test_wrong_source_value(self):
        data = {"forge_bake_action_name": "Action",
                "forge_bake_camera_name": "cam1",
                "forge_bake_source": "blender"}
        ctx = _FakeContext(_FakeObject(data=data))
        msg = check(ctx)
        assert msg is not None
        assert "forge_bake_source != 'flame'" in msg

    def test_missing_source_key_treated_as_wrong(self):
        data = {"forge_bake_action_name": "Action",
                "forge_bake_camera_name": "cam1"}
        ctx = _FakeContext(_FakeObject(data=data))
        msg = check(ctx)
        assert msg is not None
        assert "forge_bake_source != 'flame'" in msg


class TestHappyPath:
    def test_valid_camera_returns_none(self):
        data = {"forge_bake_action_name": "Action",
                "forge_bake_camera_name": "cam1",
                "forge_bake_source": "flame"}
        ctx = _FakeContext(_FakeObject(data=data))
        assert check(ctx) is None


class TestRequiredKeysOrder:
    def test_order_matches_ui_spec_priority(self):
        # UI-SPEC §Preflight Tier 1 pins the priority order: action_name
        # first, camera_name second. Lock the tuple order via a direct
        # assertion so a refactor can't silently flip it.
        assert _REQUIRED_STAMPED_KEYS == (
            "forge_bake_action_name", "forge_bake_camera_name")
