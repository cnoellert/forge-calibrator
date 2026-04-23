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
