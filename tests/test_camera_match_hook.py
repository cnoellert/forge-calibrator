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

    def __init__(self, name="Default", cam_type="Camera"):
        # `cam_type` defaults to "Camera" so existing fixtures match the
        # free-camera shape; pass cam_type="Camera 3D" to exercise the
        # GAP-04.4-UAT-05 (3D-camera variant) allowlist branch.
        self.type = cam_type
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


def test_scope_action_camera_true_for_camera_3d():
    """GAP-04.4-UAT-05: Flame distinguishes "Camera" (free) from
    "Camera 3D" (3D rig). Both round-trip cleanly through
    `action.export_fbx(only_selected_nodes=True)` (verified via bridge
    probe 2026-04-27 on ACTION_TEST/Camera1 — 29429-byte FBX). The pre-
    fix exact-string match `item.type == "Camera"` excluded Camera 3D
    silently, so the FORGE → Camera menu never surfaced on a 3D camera
    right-click. Post-fix uses an explicit allowlist
    ``("Camera", "Camera 3D")`` so both variants get the menu.
    """
    if not _scope_helper_implemented():
        pytest.skip(_WAVE1_SKIP_REASON)
    item = _FakeCameraNode(name="Camera1", cam_type="Camera 3D")
    assert _hook_module._scope_action_camera([item]) is True


def test_first_camera_in_action_selection_accepts_camera_3d(monkeypatch):
    """Companion to test_scope_action_camera_true_for_camera_3d:
    `_first_camera_in_action_selection`'s selection filter must also
    accept "Camera 3D" so the right-click handler can resolve the
    cam → action pair after the menu surfaces. Pre-fix the same
    exact-string match excluded 3D cameras at the resolution stage too,
    so even with a hypothetical scope override the helper would return
    (None, None).
    """
    if not _first_camera_helper_has_fallback():
        pytest.skip(_GAP1_SKIP_REASON)

    cam = _FakeCameraNode(name="Camera1", cam_type="Camera 3D")
    cam.parent = None  # force fallback so we exercise the type filter

    action_target = _FakeActionNode("OwningAction", child_nodes=[cam])

    class _Batch:
        nodes = [action_target]

    monkeypatch.setattr(_fake_flame, "batch", _Batch())

    action_node, cam_node = _hook_module._first_camera_in_action_selection([cam])
    assert action_node is action_target
    assert cam_node is cam


# ---------------------------------------------------------------------------
# Tests — _first_camera_in_action_selection rewrite (Plan 04.4-07 / GAP-1).
# Two paths under test: (1) cam.parent works → fast path returns (parent, cam).
# (2) cam.parent raises / returns None / returns object lacking .nodes →
#     fall back to scanning flame.batch.nodes for the Action whose .nodes
#     contains cam (identity comparison).
# ---------------------------------------------------------------------------


import inspect


def _first_camera_helper_has_fallback():
    """True iff the rewrite from Plan 04.4-07 has landed.

    Checks for the function AND for the substring 'for n in flame.batch.nodes'
    inside its body — distinguishes the Wave-1 deferred-fallback shape
    (`return item.parent, item`) from the Plan 04.4-07 rewrite that adds
    the scan loop.
    """
    fn = getattr(_hook_module, "_first_camera_in_action_selection", None)
    if fn is None:
        return False
    try:
        src = inspect.getsource(fn)
    except (OSError, TypeError):
        return False
    return "for n in flame.batch.nodes" in src


_GAP1_SKIP_REASON = (
    "_first_camera_in_action_selection scan fallback not yet implemented "
    "(Plan 04.4-07 / GAP-04.4-UAT-01)"
)


class _FakeActionNode:
    """Batch-context Action fake — .type is a PyAttribute (matches batch shape).

    Differs from action-schematic-context items (which use plain str .type)
    per RESEARCH §P-02 / Pitfall 1 — the batch context exposes PyAttributes,
    the action-schematic context exposes plain strs. The fallback scan
    iterates flame.batch.nodes, so it sees the PyAttribute shape; the
    helper's duck-typed `t = n.type; type_val = t.get_value() if hasattr(t, "get_value") else str(t)`
    handles both shapes.
    """

    _UNSET = object()

    def __init__(self, name, child_nodes, export_fbx=_UNSET):
        self.type = _FakeAttr("Action")  # batch-context PyAttribute
        self.name = _FakeAttr(name)
        self.nodes = list(child_nodes)
        # `export_fbx` is the discriminator the fast path uses to detect
        # the broken proxy described in GAP-04.4-UAT-04 (round 2). A
        # healthy PyActionNode exposes export_fbx as a callable; the
        # broken hook-context proxy exposes it as None. Default to a
        # no-op callable so existing fast-path fixtures match the
        # healthy shape. Tests can pass `export_fbx=None` to simulate
        # the broken proxy (sentinel _UNSET vs explicit None lets us
        # distinguish "default" from "explicitly broken").
        if export_fbx is _FakeActionNode._UNSET:
            self.export_fbx = lambda *args, **kwargs: True
        else:
            self.export_fbx = export_fbx


def test_first_camera_parent_works_returns_fast_path_tuple(monkeypatch):
    """Fast path: cam.parent returns a usable PyActionNode-like object →
    helper returns (parent, cam) without scanning flame.batch.nodes.

    Pre-condition: the rewritten helper preserves the cam.parent fast
    path inside try/except. This test verifies the fast path still
    returns the cached parent when it has a .nodes attribute.
    """
    if not _first_camera_helper_has_fallback():
        pytest.skip(_GAP1_SKIP_REASON)

    cam = _FakeCameraNode(name="MyCam")
    fake_parent = _FakeActionNode("ParentAction", child_nodes=[cam])
    cam.parent = fake_parent  # fast-path attribute injected

    # If the helper's fast path works, it MUST NOT scan flame.batch.nodes
    # — assert no scan side effect by setting batch.nodes to a sentinel
    # that would explode if iterated.
    class _ExplodingBatch:
        @property
        def nodes(self):
            raise AssertionError(
                "fast path returned (parent, cam); "
                "flame.batch.nodes scan must NOT run when cam.parent is usable"
            )

    monkeypatch.setattr(_fake_flame, "batch", _ExplodingBatch())

    action_node, cam_node = _hook_module._first_camera_in_action_selection([cam])
    assert action_node is fake_parent
    assert cam_node is cam


def test_first_camera_parent_with_broken_export_fbx_falls_back(monkeypatch):
    """Fallback path #3: cam.parent returns an object with .nodes but
    `.export_fbx is None` → helper falls through to batch.nodes scan.

    This is the GAP-04.4-UAT-04 (round 2) live-UAT case: in hook
    callback context on Flame 2026.2.1 arm64 macOS, cam.parent returns
    a proxy whose .nodes is populated but whose .export_fbx is None.
    The pre-fix fast-path filter (`hasattr(parent, "nodes")`) accepted
    that proxy, so `action.export_fbx(...)` later in the export pipeline
    raised `'NoneType' object is not callable`. The post-fix filter adds
    `callable(getattr(parent, "export_fbx", None))` so the broken proxy
    falls through to the scan, which returns the healthy PyActionNode
    that batch.nodes exposes.
    """
    if not _first_camera_helper_has_fallback():
        pytest.skip(_GAP1_SKIP_REASON)

    cam = _FakeCameraNode(name="MyCam")
    # Broken proxy: .nodes present, .export_fbx is None (matches the
    # live failure shape). Must be a different OBJECT than the healthy
    # action_target so the identity check on cam_node still works
    # downstream — the broken proxy's .nodes does NOT contain cam (we
    # only test identity in the scan path, and the scan looks at
    # batch.nodes not parent.nodes).
    broken_parent = _FakeActionNode(
        "BrokenProxy", child_nodes=[cam], export_fbx=None,
    )
    cam.parent = broken_parent

    action_target = _FakeActionNode("HealthyAction", child_nodes=[cam])

    class _Batch:
        nodes = [action_target]

    monkeypatch.setattr(_fake_flame, "batch", _Batch())

    action_node, cam_node = _hook_module._first_camera_in_action_selection([cam])
    assert action_node is action_target, (
        "broken-proxy fast-path must fall through to scan; got "
        f"{action_node!r} (broken_parent={broken_parent!r})"
    )
    assert cam_node is cam


def test_first_camera_parent_raises_falls_back_to_batch_scan(monkeypatch):
    """Fallback path: cam.parent raises Exception → helper scans
    flame.batch.nodes, finds the Action whose .nodes contains cam by
    identity, returns (action, cam).

    This is the GAP-04.4-UAT-01 fix path. UAT 2026-04-27 confirmed that
    cam.parent on Flame 2026.2.1 hook callback context produces a chained
    API resolution that lands on a None — represented here as a raising
    property since that's the visible behaviour from the helper's
    perspective.
    """
    if not _first_camera_helper_has_fallback():
        pytest.skip(_GAP1_SKIP_REASON)

    cam = _FakeCameraNode(name="MyCam")

    # cam.parent raises — simulate the Flame 2026.2.1 hook-context misbehavior.
    class _RaisingDescriptor:
        def __get__(self, obj, objtype=None):
            raise RuntimeError("simulated cam.parent failure (GAP-1 case)")

    type(cam).parent = _RaisingDescriptor()

    action_a = _FakeActionNode("OtherAction", child_nodes=[])
    action_target = _FakeActionNode("RealParent", child_nodes=[cam])
    action_c = _FakeActionNode("ThirdAction", child_nodes=[])

    class _Batch:
        nodes = [action_a, action_target, action_c]

    monkeypatch.setattr(_fake_flame, "batch", _Batch())

    try:
        action_node, cam_node = _hook_module._first_camera_in_action_selection([cam])
    finally:
        # Clean up the parent descriptor so other tests aren't polluted.
        del type(cam).parent

    assert action_node is action_target, (
        "scan fallback must return the Action whose .nodes contains cam "
        "(identity comparison, not name equality)"
    )
    assert cam_node is cam


def test_first_camera_parent_returns_none_falls_back_to_batch_scan(monkeypatch):
    """Fallback path #2: cam.parent returns None (no exception, just None) →
    helper scans flame.batch.nodes and resolves via identity.

    Distinct from the raise case because the helper's check is
    `parent is not None and hasattr(parent, "nodes")` — a parent that's
    None falls through to the scan without raising. UAT GAP-1 may
    manifest as either shape depending on Flame's chained-API state.
    """
    if not _first_camera_helper_has_fallback():
        pytest.skip(_GAP1_SKIP_REASON)

    cam = _FakeCameraNode(name="MyCam")
    cam.parent = None  # explicit None — fallback should engage

    action_target = _FakeActionNode("ParentAction", child_nodes=[cam])

    class _Batch:
        nodes = [action_target]

    monkeypatch.setattr(_fake_flame, "batch", _Batch())

    action_node, cam_node = _hook_module._first_camera_in_action_selection([cam])
    assert action_node is action_target
    assert cam_node is cam


def test_first_camera_returns_none_pair_when_no_camera_in_selection():
    """Empty selection / non-camera selection: helper returns (None, None)."""
    if not _first_camera_helper_has_fallback():
        pytest.skip(_GAP1_SKIP_REASON)

    axis = _FakeAxisNode(name="Axis1")
    action_node, cam_node = _hook_module._first_camera_in_action_selection([axis])
    assert action_node is None
    assert cam_node is None


def test_first_camera_skips_perspective_and_continues(monkeypatch):
    """Perspective is filtered: a Perspective cam in selection followed
    by a real cam → returns (parent, real_cam). This reuses the same
    scan-fallback path as `test_first_camera_parent_raises_...` since
    the fallback is the production code path post-Plan 04.4-07.
    """
    if not _first_camera_helper_has_fallback():
        pytest.skip(_GAP1_SKIP_REASON)

    perspective_cam = _FakeCameraNode(name="Perspective")
    real_cam = _FakeCameraNode(name="RealCam")
    real_cam.parent = None  # force fallback

    action_target = _FakeActionNode("OwningAction", child_nodes=[real_cam])

    class _Batch:
        nodes = [action_target]

    monkeypatch.setattr(_fake_flame, "batch", _Batch())

    action_node, cam_node = _hook_module._first_camera_in_action_selection(
        [perspective_cam, real_cam]
    )
    assert action_node is action_target
    assert cam_node is real_cam
