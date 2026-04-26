"""
Unit tests for scope-helper / selection-resolver functions in
flame/camera_match_hook.py.

What we test:
  - _scope_action_camera (Wave 1, Plan 04.4-02): True for a non-Perspective
    Camera PyCoNode, False for Perspective, False for non-Camera node types.
    Plus the Pitfall-1 guard (item.type is plain str in action context — the
    helper MUST NOT call .get_value() on it) and the per-item exception
    swallow (defensive try/except continues iterating).

What we DON'T test:
  - get_action_custom_ui_actions (NEW function, Wave 1) registration —
    verified manually after Flame restart per RESEARCH §Pitfall 3.
  - Live PyCoNode object behavior — fakes here use plain str for .type
    per the verified action-context shape (RESEARCH §P-02 Pitfall 1).

# Pitfall 1 (RESEARCH §): in get_action_custom_ui_actions, item.type is a PLAIN
# Python str — NOT a PyAttribute. Tests below intentionally pass plain str
# values for .type; if _scope_action_camera ever uses .get_value() on .type,
# Test 4 will fail (caught by the try/except → returns False instead of True).
# Pitfall 3 (RESEARCH §): get_action_custom_ui_actions is a NEW function — these
# tests cover only the scope helper; the hook function itself is verified via
# manual UAT after Wave 2 menu install + Flame restart.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import types
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Stub heavy Flame / GUI dependencies that camera_match_hook imports at
# module load. We track which stubs we install so we can restore sys.modules
# afterwards — preventing stub pollution in other test modules.
# Mirrors the pattern in tests/test_hook_export_camera_to_blender.py.
# ---------------------------------------------------------------------------

_STUBS_TO_INSTALL = {
    "flame": None,  # filled below — we need a real ModuleType with PyCoNode
    "cv2": MagicMock(),
    "PySide6": MagicMock(),
    "PySide6.QtWidgets": MagicMock(),
    "PySide6.QtCore": MagicMock(),
    "PySide6.QtGui": MagicMock(),
    "PySide6.QtOpenGLWidgets": MagicMock(),
    "forge_flame": MagicMock(),
    "forge_flame.fbx_ascii": MagicMock(),
    "forge_flame.fbx_io": MagicMock(),
    "forge_flame.camera_io": MagicMock(),
    "forge_flame.blender_bridge": MagicMock(),
    "forge_flame.adapter": MagicMock(),
    "forge_flame.wiretap_reader": MagicMock(),
    "forge_core": MagicMock(),
    "forge_core.ocio_pipeline": MagicMock(),
}

# Build a minimal fake `flame` module with PyCoNode as a class so
# isinstance(item, flame.PyCoNode) works inside the scope helper.
_fake_flame = types.ModuleType("flame")


class _PyCoNode:
    """Stand-in for flame.PyCoNode — only used for isinstance() in the helper."""
    pass


_fake_flame.PyCoNode = _PyCoNode
_fake_flame.messages = MagicMock()
_fake_flame.batch = MagicMock()
_fake_flame.project = MagicMock()
_STUBS_TO_INSTALL["flame"] = _fake_flame

_pre_stub_state = {k: sys.modules.get(k) for k in _STUBS_TO_INSTALL}
for _mod_name, _stub in _STUBS_TO_INSTALL.items():
    if _mod_name not in sys.modules:
        sys.modules[_mod_name] = _stub

# Add repo root to path so forge_flame / forge_core imports resolve.
_REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, _REPO_ROOT)

# Import camera_match_hook directly from flame/ via importlib.util to avoid
# the 'flame' package namespace collision with our flame API stub above.
_FLAME_DIR = os.path.join(_REPO_ROOT, "flame")
_spec = importlib.util.spec_from_file_location(
    "camera_match_hook",
    os.path.join(_FLAME_DIR, "camera_match_hook.py"),
)
_hook_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_hook_module)

# Restore sys.modules: remove stubs we installed so they don't pollute
# other test modules collected after this file.
#
# EXCEPTION: keep `_fake_flame` installed in sys.modules. _scope_action_camera
# (and other module-level helpers added in Plan 04.4-02 / Wave 1) use a lazy
# `import flame` inside the function body — required because camera_match_hook
# is imported at Flame startup and a top-level `import flame` would create a
# circular dependency. At test runtime that lazy import has to find the fake
# `flame` module with `_PyCoNode` attached so `isinstance(item, flame.PyCoNode)`
# succeeds. `flame` is not a real importable package on dev machines, so
# leaving the fake in sys.modules cannot pollute any other test module.
_KEEP_INSTALLED = {"flame"}
for _mod_name in _STUBS_TO_INSTALL:
    if _mod_name in _KEEP_INSTALLED:
        continue
    if _pre_stub_state[_mod_name] is None and _mod_name in sys.modules:
        del sys.modules[_mod_name]
    elif _pre_stub_state[_mod_name] is not None:
        sys.modules[_mod_name] = _pre_stub_state[_mod_name]


# ---------------------------------------------------------------------------
# Wave-0 scope-helper skip gate. Flips from SKIP to PASS once Plan 04.4-02
# (Wave 1) lands _scope_action_camera in flame/camera_match_hook.py.
# Skip message MUST read exactly:
#   "_scope_action_camera not yet implemented (Wave 1)"
# so future executors can grep for the wave pointer.
# ---------------------------------------------------------------------------


def _scope_helper_implemented():
    return hasattr(_hook_module, "_scope_action_camera")


_WAVE1_SKIP_REASON = "_scope_action_camera not yet implemented (Wave 1)"


# ---------------------------------------------------------------------------
# Fakes for PyCoNode / PyAttribute selection items.
# ---------------------------------------------------------------------------


class _FakeAttr:
    """Minimal Flame PyAttribute fake — exposes get_value()."""

    def __init__(self, value):
        self._value = value

    def get_value(self):
        return self._value


class _FakeCameraNode(_PyCoNode):
    """Camera-typed PyCoNode fake.

    .type is a PLAIN Python str (not a PyAttribute) per RESEARCH §Pitfall 1
    — action-context selection items expose item.type as str. Calling
    .get_value() on it raises AttributeError; that is the trap the
    scope helper must avoid.
    """

    def __init__(self, name="Default"):
        self.type = "Camera"
        self.name = _FakeAttr(name)


class _FakeAxisNode(_PyCoNode):
    """Axis-typed PyCoNode fake — same shape as camera but different type."""

    def __init__(self, name="Axis1"):
        self.type = "Axis"
        self.name = _FakeAttr(name)


class _ExplodingItem:
    """Selection item whose .type access raises — exercises per-item try/except."""

    @property
    def type(self):
        raise RuntimeError("simulated Flame API error")


# ---------------------------------------------------------------------------
# Tests — _scope_action_camera (Wave 1, Plan 04.4-02).
# ---------------------------------------------------------------------------


def test_scope_action_camera_true_for_non_perspective_camera():
    """A Camera PyCoNode whose name != 'Perspective' → True."""
    if not _scope_helper_implemented():
        pytest.skip(_WAVE1_SKIP_REASON)
    item = _FakeCameraNode(name="Default")
    assert _hook_module._scope_action_camera([item]) is True


def test_scope_action_camera_false_for_perspective():
    """A Camera PyCoNode named 'Perspective' must be excluded.

    Mirrors the Perspective filter in iter_keyframable_cameras (fbx_io.py)
    per memory/flame_perspective_camera.md.
    """
    if not _scope_helper_implemented():
        pytest.skip(_WAVE1_SKIP_REASON)
    item = _FakeCameraNode(name="Perspective")
    assert _hook_module._scope_action_camera([item]) is False


def test_scope_action_camera_false_for_axis_node():
    """A non-Camera node type (e.g. Axis) must return False."""
    if not _scope_helper_implemented():
        pytest.skip(_WAVE1_SKIP_REASON)
    item = _FakeAxisNode(name="Axis1")
    assert _hook_module._scope_action_camera([item]) is False


def test_scope_action_camera_does_not_call_get_value_on_type():
    """RESEARCH §Pitfall 1 canary — item.type is a plain str in action
    context (no .get_value method). If the helper calls .get_value() on
    .type, AttributeError raises, the try/except swallows it, and the
    function returns False instead of True. This test catches that
    regression by asserting True for a fake whose .type is bare str.
    """
    if not _scope_helper_implemented():
        pytest.skip(_WAVE1_SKIP_REASON)
    item = _FakeCameraNode(name="Default")
    # Sanity-check the test's premise: .type really is a plain str with no get_value.
    assert isinstance(item.type, str)
    assert not hasattr(item.type, "get_value")
    assert _hook_module._scope_action_camera([item]) is True


def test_scope_action_camera_handles_per_item_exception():
    """Per-item try/except must continue past an exploding item.

    Selection list = [bad_item, good_item]. Even though bad_item's
    .type access raises, the helper must keep iterating and return True
    because good_item satisfies the predicate.
    """
    if not _scope_helper_implemented():
        pytest.skip(_WAVE1_SKIP_REASON)
    bad = _ExplodingItem()
    good = _FakeCameraNode(name="Default")
    assert _hook_module._scope_action_camera([bad, good]) is True
