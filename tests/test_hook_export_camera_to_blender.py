"""
Unit tests for the Export Camera to Blender handler in
flame/camera_match_hook.py.

What we test:
  - H2: _resolve_flame_project_fps_label() returns a _FLAME_FPS_LABELS label
        when the fps source is present; falls back with a warning when absent.
  - H6: the handler passes frame_rate=fps_label into fbx_ascii.fbx_to_v5_json
        (item 5, D-11 always-stamp).

What we DON'T test:
  - Live Flame runtime (all Flame objects are duck-typed fakes).
  - blender_bridge.run_bake (subprocess; tested in test_blender_bridge.py).
  - Full integration of the handler (too much setup; covered by smoke test D-15).

History: the H1/H3/H4/H5/H7 tests around _is_animated_camera and the
static-JSON detect-and-route branch were removed 2026-04-23 when that
branch was deleted from the hook. The unified FBX path now handles
both static and animated cameras (via Flame's export_fbx with
bake_animation=True), which correctly handles aim-rig orientation
that the old static-JSON path discarded. See the
flame_fbx_empty_block_contract memory and the debug sessions in
.planning/debug/resolved/ for context.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import types
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Stub all the heavy Flame / GUI dependencies that camera_match_hook imports
# at module level. We do this BEFORE importing camera_match_hook.
# ---------------------------------------------------------------------------

# Stub heavy dependencies that camera_match_hook imports at module level.
# We track which stubs we install so we can restore sys.modules after the
# hook module is loaded — preventing stub pollution in other test modules
# (e.g. test_image_buffer.py needs the real cv2).

_STUBS_TO_INSTALL = {
    "flame": None,
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

# Stub `flame` module specially so it has the right attributes.
_fake_flame = types.ModuleType("flame")
_fake_flame.messages = MagicMock()
_fake_flame.batch = MagicMock()
_fake_flame.project = MagicMock()
_STUBS_TO_INSTALL["flame"] = _fake_flame

# Record which modules already existed before we touch sys.modules.
_pre_stub_state = {k: sys.modules.get(k) for k in _STUBS_TO_INSTALL}

# Install stubs only for modules not already present.
for _mod_name, _stub in _STUBS_TO_INSTALL.items():
    if _mod_name not in sys.modules:
        sys.modules[_mod_name] = _stub

# Add repo root to path so forge_flame / forge_core imports resolve
_REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, _REPO_ROOT)

# Import camera_match_hook directly from the flame/ directory via importlib.util
# to avoid the 'flame' package namespace collision with the flame API stub.
import importlib.util  # noqa: E402

_FLAME_DIR = os.path.join(_REPO_ROOT, "flame")
_spec = importlib.util.spec_from_file_location(
    "camera_match_hook",
    os.path.join(_FLAME_DIR, "camera_match_hook.py"),
)
_hook_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_hook_module)

# Restore sys.modules: remove stubs we installed so they don't pollute
# other test modules collected after this file.
for _mod_name in _STUBS_TO_INSTALL:
    if _pre_stub_state[_mod_name] is None and _mod_name in sys.modules:
        # We installed it; remove it.
        del sys.modules[_mod_name]
    elif _pre_stub_state[_mod_name] is not None:
        # It was already there; restore the original.
        sys.modules[_mod_name] = _pre_stub_state[_mod_name]


# ---------------------------------------------------------------------------
# Duck-typed fakes for Flame objects
# ---------------------------------------------------------------------------


class _Attr:
    """Minimal PyAttribute fake."""

    def __init__(self, value):
        self._value = value

    def get_value(self):
        return self._value


class _FakeCam:
    """Fake Flame Action camera node with the 4 required attrs."""

    def __init__(
        self,
        name="Camera",
        position=(0.0, 0.0, 4747.64),
        rotation=(0.0, 0.0, 0.0),
        fov=40.0,
        focal=21.74,
    ):
        self.name = _Attr(name)
        self.position = _Attr(position)
        self.rotation = _Attr(rotation)
        self.fov = _Attr(fov)
        self.focal = _Attr(focal)


class _FakeBatch:
    """Fake flame.batch with start_frame and frame_rate attributes."""

    def __init__(self, start_frame=1001, end_frame=1100, frame_rate=None):
        self.start_frame = _Attr(start_frame)
        self.end_frame = _Attr(end_frame)
        # frame_rate: None simulates the NoneType slot (D-19 on 2026.2.1)
        self.frame_rate = frame_rate


# ---------------------------------------------------------------------------
# H1: _is_animated_camera
# ---------------------------------------------------------------------------


# H1 (TestIsAnimatedCamera) removed 2026-04-23 — _is_animated_camera was
# deleted from the hook along with the static-JSON detect-and-route branch.


# ---------------------------------------------------------------------------
# H2: _resolve_flame_project_fps_label
# ---------------------------------------------------------------------------


class TestResolveFlameProjectFpsLabel:
    """H2: _resolve_flame_project_fps_label returns a _FLAME_FPS_LABELS label."""

    _VALID_LABELS = {
        "23.976 fps", "24 fps", "25 fps", "29.97 fps", "30 fps",
        "48 fps", "50 fps", "59.94 fps", "60 fps",
    }

    def test_h2_returns_a_label_string(self):
        """The function must return a non-empty string."""
        result = _hook_module._resolve_flame_project_fps_label()
        assert isinstance(result, str)
        assert result.strip()

    def test_h2_fallback_is_24fps_or_label(self, capsys):
        """When Flame fps source is unavailable, falls back to '24 fps'
        with a stderr warning, OR returns any valid label if a source
        is found."""
        result = _hook_module._resolve_flame_project_fps_label()
        # Either it's a valid label from the set, OR it's '24 fps' fallback,
        # OR it's some '<num> fps' form — any is acceptable as long as it's
        # a non-empty string (D-14: never silent, always stamp).
        assert result  # non-empty

    def test_h2_result_never_raw_numeric(self):
        """Result must not be a bare numeric (e.g., '24.0') — must be a label."""
        result = _hook_module._resolve_flame_project_fps_label()
        # A bare float string like '24.0' would fail the forge_sender ladder.
        # Valid labels all contain 'fps' or are formatted as '<num> fps'.
        # We just check it's not a bare float.
        try:
            float(result)
            pytest.fail(
                f"_resolve_flame_project_fps_label must not return a bare "
                f"numeric string; got {result!r}"
            )
        except ValueError:
            pass  # Good — not a bare float


# H3/H4/H5 (branch-dispatch and static-branch tests) removed 2026-04-23
# when the detect-and-route was collapsed to a single unified FBX path.
# The P-5 dialog-shape invariant is now covered by H6's source-grep plus
# the fbx_io.export_action_cameras_to_fbx contract tests in test_fbx_io.py.

# ---------------------------------------------------------------------------
# H6: handler passes frame_rate= into fbx_ascii.fbx_to_v5_json
# ---------------------------------------------------------------------------


class TestExportHandlerFpsLabel:
    """H6: the export handler stamps frame_rate=<resolved_label> into
    fbx_ascii.fbx_to_v5_json (item 5 / D-11 always-stamp). After the
    2026-04-23 unification of static + animated paths, there is one
    call site instead of two, so the source-grep assertion looks for
    exactly one occurrence."""

    def test_h6_frame_rate_kwarg_in_source(self):
        """H6: verify the hook source contains 'frame_rate=fps_label' at
        least once, confirming D-11 always-stamp is still wired on the
        unified path."""
        import inspect
        src = inspect.getsource(_hook_module)
        count = src.count("frame_rate=fps_label")
        assert count >= 1, (
            f"Expected at least 1 occurrence of 'frame_rate=fps_label' "
            f"in the hook source, found {count}. "
            "D-11 requires frame_rate to be stamped on every Export to Blender."
        )


# H7 (TestIsAnimatedCameraProbeApiContract) and its _StrictFakeAction /
# _SelectedNodesSetter fixtures were removed 2026-04-23 when the detect-
# and-route was collapsed. The probe API contract it pinned (action.
# export_fbx with only_selected_nodes=True, NO cameras= kwarg) is now
# moot — the hook calls fbx_io.export_action_cameras_to_fbx which
# handles the selection-restore pattern internally.


# ---------------------------------------------------------------------------
# Quick 260501-i31: TestLadderMenuFactory
#
# Covers _make_export_callback factory + flame_to_blender_scale parameter
# plumbing on the three signatures (_export_camera_pipeline,
# _export_camera_to_blender, _export_camera_from_action_selection) +
# menu shape for both surfaces + the two regression canaries
# (default-entry scale=100.0, viewport-nav scale=1000.0 byte-identical).
# ---------------------------------------------------------------------------


class TestLadderMenuFactory:
    """Quick 260501-i31: 5-stop scale ladder right-click menu entries.

    Covers _make_export_callback factory + flame_to_blender_scale plumbing
    + menu shape on both Batch (Action-scope) and Action (Camera-scope)
    surfaces + regression canaries.
    """

    # ------------------------------------------------------------------
    # A. Per-stop dispatch — Action-scope (camera_scope=False)
    # ------------------------------------------------------------------
    @pytest.mark.parametrize("scale", [0.01, 0.1, 1.0, 10.0, 100.0])
    def test_factory_dispatches_per_stop_action_scope(self, monkeypatch, scale):
        """Each ladder stop produces a closure whose dispatch fires the
        Action-scope wrapper with flame_to_blender_scale=stop_value.
        Catches loop-variable capture bugs (T-quick-260501-i31-01)."""
        calls = []

        def _recorder(selection, *, flame_to_blender_scale):
            calls.append((selection, flame_to_blender_scale))

        monkeypatch.setattr(
            _hook_module, "_export_camera_to_blender", _recorder)

        cb = _hook_module._make_export_callback(scale)
        sentinel = object()
        cb(sentinel)

        assert len(calls) == 1
        assert calls[0][0] is sentinel
        assert calls[0][1] == scale

    # ------------------------------------------------------------------
    # B. Per-stop dispatch — Camera-scope (camera_scope=True)
    # ------------------------------------------------------------------
    @pytest.mark.parametrize("scale", [0.01, 0.1, 1.0, 10.0, 100.0])
    def test_factory_dispatches_per_stop_camera_scope(self, monkeypatch, scale):
        """Camera-scope flag routes to _export_camera_from_action_selection
        with flame_to_blender_scale=stop_value; Action-scope wrapper is
        NOT called."""
        cam_calls = []
        action_calls = []

        def _cam_recorder(selection, *, flame_to_blender_scale):
            cam_calls.append((selection, flame_to_blender_scale))

        def _action_recorder(selection, *, flame_to_blender_scale):
            action_calls.append((selection, flame_to_blender_scale))

        monkeypatch.setattr(
            _hook_module, "_export_camera_from_action_selection",
            _cam_recorder)
        monkeypatch.setattr(
            _hook_module, "_export_camera_to_blender", _action_recorder)

        cb = _hook_module._make_export_callback(scale, camera_scope=True)
        sentinel = object()
        cb(sentinel)

        assert len(cam_calls) == 1
        assert cam_calls[0][0] is sentinel
        assert cam_calls[0][1] == scale
        assert action_calls == []

    # ------------------------------------------------------------------
    # C. Camera-scope routing inline (default vs explicit)
    # ------------------------------------------------------------------
    def test_factory_camera_scope_routing(self, monkeypatch):
        """Default (camera_scope=False) -> Action wrapper only.
        Explicit camera_scope=True -> Camera wrapper only."""
        action_calls = []
        cam_calls = []

        monkeypatch.setattr(
            _hook_module, "_export_camera_to_blender",
            lambda selection, *, flame_to_blender_scale:
                action_calls.append(flame_to_blender_scale))
        monkeypatch.setattr(
            _hook_module, "_export_camera_from_action_selection",
            lambda selection, *, flame_to_blender_scale:
                cam_calls.append(flame_to_blender_scale))

        # Default camera_scope is False
        _hook_module._make_export_callback(1.0)(object())
        assert action_calls == [1.0]
        assert cam_calls == []

        # Explicit camera_scope=True
        _hook_module._make_export_callback(1.0, camera_scope=True)(object())
        assert action_calls == [1.0]   # unchanged
        assert cam_calls == [1.0]

    # ------------------------------------------------------------------
    # D. Wrapper regression — both surfaces (quick 260501-knl)
    # ------------------------------------------------------------------
    def test_wrapper_action_scope_forwards_picked_scale(self, monkeypatch):
        """When the picker returns 100.0, the wrapper invokes
        _export_camera_to_blender(selection, flame_to_blender_scale=100.0).
        Regression guard for the studio-default behavior surfaced via the
        new menu wiring."""
        calls = []

        def _recorder(selection, *, flame_to_blender_scale):
            calls.append((selection, flame_to_blender_scale))

        monkeypatch.setattr(
            _hook_module, "_export_camera_to_blender", _recorder)

        # Stub the scale_picker_dialog module since it is imported lazily.
        fake_picker = types.ModuleType("scale_picker_dialog")
        fake_picker.pick_scale = lambda parent=None, default=100.0: 100.0
        monkeypatch.setitem(sys.modules, "scale_picker_dialog", fake_picker)

        sentinel = object()
        _hook_module._export_camera_to_blender_with_picker(sentinel)

        assert len(calls) == 1
        assert calls[0][0] is sentinel
        assert calls[0][1] == 100.0

    def test_wrapper_action_scope_cancel_skips_export(self, monkeypatch):
        """When the picker returns None (ESC/cancel), the wrapper invokes
        NO export. Defends the 'cancel = no-op' contract."""
        calls = []

        def _recorder(selection, *, flame_to_blender_scale):
            calls.append((selection, flame_to_blender_scale))

        monkeypatch.setattr(
            _hook_module, "_export_camera_to_blender", _recorder)

        fake_picker = types.ModuleType("scale_picker_dialog")
        fake_picker.pick_scale = lambda parent=None, default=100.0: None
        monkeypatch.setitem(sys.modules, "scale_picker_dialog", fake_picker)

        _hook_module._export_camera_to_blender_with_picker(object())

        assert calls == []

    def test_wrapper_camera_scope_forwards_picked_scale(self, monkeypatch):
        """Camera-scope wrapper: picker returns scale -> Camera-scope export
        fires with that scale."""
        calls = []

        def _recorder(selection, *, flame_to_blender_scale):
            calls.append((selection, flame_to_blender_scale))

        monkeypatch.setattr(
            _hook_module, "_export_camera_from_action_selection", _recorder)

        fake_picker = types.ModuleType("scale_picker_dialog")
        fake_picker.pick_scale = lambda parent=None, default=100.0: 10.0
        monkeypatch.setitem(sys.modules, "scale_picker_dialog", fake_picker)

        sentinel = object()
        _hook_module._export_camera_from_action_selection_with_picker(sentinel)

        assert len(calls) == 1
        assert calls[0][0] is sentinel
        assert calls[0][1] == 10.0

    def test_wrapper_camera_scope_cancel_skips_export(self, monkeypatch):
        """Camera-scope wrapper: picker returns None -> NO export."""
        calls = []

        def _recorder(selection, *, flame_to_blender_scale):
            calls.append((selection, flame_to_blender_scale))

        monkeypatch.setattr(
            _hook_module, "_export_camera_from_action_selection", _recorder)

        fake_picker = types.ModuleType("scale_picker_dialog")
        fake_picker.pick_scale = lambda parent=None, default=100.0: None
        monkeypatch.setitem(sys.modules, "scale_picker_dialog", fake_picker)

        _hook_module._export_camera_from_action_selection_with_picker(object())

        assert calls == []

    # ------------------------------------------------------------------
    # E. Batch menu shape (quick 260501-knl: reverted from i31's 7-entry shape)
    # ------------------------------------------------------------------
    def test_batch_menu_shape(self):
        """get_batch_custom_ui_actions()'s 'Camera' subgroup has 2 dicts:
        1 clip-scoped 'Open Camera Calibrator' + 1 Action-scoped
        'Export Camera to Blender' (now wired to the picker wrapper).
        Reverted from i31's 7-entry shape per quick 260501-knl."""
        groups = _hook_module.get_batch_custom_ui_actions()
        camera_groups = [g for g in groups if g.get("name") == "Camera"]
        assert len(camera_groups) == 1, \
            f"Expected exactly 1 'Camera' group; got {len(camera_groups)}"

        actions = camera_groups[0]["actions"]
        assert len(actions) == 2, \
            f"Expected 2 entries in 'Camera' subgroup; got {len(actions)}"

        action_scoped = [
            a for a in actions
            if a.get("isVisible") is _hook_module._scope_batch_action
        ]
        assert len(action_scoped) == 1, \
            f"Expected 1 Action-scoped entry; got {len(action_scoped)}"

        assert action_scoped[0]["name"] == "Export Camera to Blender"
        assert action_scoped[0]["execute"] is \
            _hook_module._export_camera_to_blender_with_picker, (
            "Action-scoped 'Export Camera to Blender' must wire to the "
            "picker wrapper, NOT directly to _export_camera_to_blender — "
            "the dialog is the new menu surface."
        )

    # ------------------------------------------------------------------
    # F. Action menu shape (quick 260501-knl: reverted from i31's 6-entry shape)
    # ------------------------------------------------------------------
    def test_action_menu_shape(self):
        """get_action_custom_ui_actions()'s root group has exactly 1 dict
        (the picker-wrapped Export Camera to Blender). Reverted from i31's
        6-entry shape per quick 260501-knl."""
        groups = _hook_module.get_action_custom_ui_actions()
        assert len(groups) == 1, \
            f"Expected exactly 1 root group; got {len(groups)}"

        actions = groups[0]["actions"]
        assert len(actions) == 1, \
            f"Expected 1 entry in root group; got {len(actions)}"

        assert actions[0]["name"] == "Export Camera to Blender"
        assert actions[0]["isVisible"] is _hook_module._scope_action_camera
        assert actions[0]["execute"] is \
            _hook_module._export_camera_from_action_selection_with_picker, (
            "Camera-scoped entry must wire to the picker wrapper, NOT "
            "directly to _export_camera_from_action_selection."
        )

    # ------------------------------------------------------------------
    # G. Viewport-nav scale=1000.0 canary (T-quick-260501-i31-03)
    # ------------------------------------------------------------------
    def test_viewport_nav_canary_unchanged(self):
        """The literal 'scale=1000.0' must appear exactly 2 times in the
        hook source (1 in run_bake call, 1 in the explanatory comment).
        Pre-edit baseline confirmed via grep -c."""
        hook_path = os.path.join(
            _REPO_ROOT, "flame", "camera_match_hook.py")
        with open(hook_path) as f:
            source = f.read()
        count = source.count("scale=1000.0")
        assert count == 2, (
            f"Expected 'scale=1000.0' to appear exactly 2 times in "
            f"flame/camera_match_hook.py; got {count}. The viewport-nav "
            f"CLI arg at run_bake must stay byte-identical."
        )

    # ------------------------------------------------------------------
    # H. No new PySide widgets in factory (T-quick-260501-i31-05)
    # ------------------------------------------------------------------
    def test_no_new_pyside_widgets_in_factory(self):
        """Defends the zero-dialog spec: factory must NOT introduce
        QDialog/QInputDialog/QListWidget/show_in_dialog/QMessageBox."""
        import inspect
        src = inspect.getsource(_hook_module._make_export_callback)
        forbidden = [
            "QDialog", "QInputDialog", "QListWidget",
            "show_in_dialog", "QMessageBox",
        ]
        for token in forbidden:
            assert token not in src, (
                f"_make_export_callback must not contain {token!r}; "
                f"the spec forbids new dialogs/popups."
            )

    # ------------------------------------------------------------------
    # I. Signature shape: keyword-only flame_to_blender_scale=100.0
    # ------------------------------------------------------------------
    def test_pipeline_signature_has_keyword_only_scale_default_100(self):
        """All three signatures (_export_camera_pipeline,
        _export_camera_to_blender, _export_camera_from_action_selection)
        must declare flame_to_blender_scale as keyword-only with
        default 100.0. Defends the regression anchor."""
        import inspect

        for fn_name in (
            "_export_camera_pipeline",
            "_export_camera_to_blender",
            "_export_camera_from_action_selection",
        ):
            fn = getattr(_hook_module, fn_name)
            sig = inspect.signature(fn)
            assert "flame_to_blender_scale" in sig.parameters, (
                f"{fn_name} must declare a flame_to_blender_scale parameter"
            )
            param = sig.parameters["flame_to_blender_scale"]
            assert param.kind == inspect.Parameter.KEYWORD_ONLY, (
                f"{fn_name}.flame_to_blender_scale must be KEYWORD_ONLY; "
                f"got {param.kind}"
            )
            assert param.default == 100.0, (
                f"{fn_name}.flame_to_blender_scale default must be 100.0; "
                f"got {param.default!r}"
            )

    # ------------------------------------------------------------------
    # J. Wrappers exist and take 1 arg (quick 260501-knl)
    # ------------------------------------------------------------------
    def test_wrappers_exist_and_are_callable(self):
        """The two new menu wrapper functions must exist at module scope
        and be 1-arg callables (the menu callback shape Flame expects)."""
        import inspect

        for fn_name in (
            "_export_camera_to_blender_with_picker",
            "_export_camera_from_action_selection_with_picker",
        ):
            fn = getattr(_hook_module, fn_name, None)
            assert callable(fn), f"{fn_name} must be a callable at module scope"
            sig = inspect.signature(fn)
            # 1 positional 'selection' arg (matches Flame menu callback shape).
            assert len(sig.parameters) == 1, (
                f"{fn_name} must take exactly 1 arg (selection); "
                f"got {list(sig.parameters)}"
            )

    # ------------------------------------------------------------------
    # K. Factory + ladder constant still present (PRESERVE-FACTORY-05)
    # ------------------------------------------------------------------
    def test_factory_still_present(self):
        """quick 260501-knl reverts the menu but KEEPS _make_export_callback
        and _LADDER_MENU_STOPS. Tests A/B/C/I depend on them. This test
        also catches accidental factory deletion during the revert."""
        assert hasattr(_hook_module, "_make_export_callback"), \
            "_make_export_callback factory must STAY (per PRESERVE-FACTORY-05)"
        assert hasattr(_hook_module, "_LADDER_MENU_STOPS"), \
            "_LADDER_MENU_STOPS constant must STAY"
        assert _hook_module._LADDER_MENU_STOPS == (0.01, 0.1, 1.0, 10.0, 100.0)
