"""Regression guards for extract_camera.py after the D-05 refactor.

What we test:
  - The file imports flame_math successfully (the sys.path shim works).
  - _rot3_to_flame_euler_deg and friends are reachable from
    extract_camera's namespace — i.e. the lift-and-shift didn't leave
    a stale local definition or lose a symbol.
  - argparse surface is unchanged (--out / --camera-name / --scale).
    ``forge_flame.blender_bridge.build_extract_cmd`` composes these
    flags and its unit tests assert the exact set; this guards from
    the other side.

What we don't test:
  - Running extract_camera.py inside Blender (requires bpy runtime
    with a real scene; tests/test_blender_roundtrip.py covers the
    round-trip math against numpy baselines).
"""

from __future__ import annotations

import os
import sys

import pytest

# Gate on Blender's Python APIs — extract_camera.py has a top-level
# ``import bpy``; without it, the whole module skips cleanly.
pytest.importorskip("mathutils")
pytest.importorskip("bpy")

# Shim: pytest discovers this test from the repo root; extract_camera
# and flame_math both need to be importable as top-level modules.
_TOOLS_BLENDER = os.path.join(os.path.dirname(__file__), "..",
                              "tools", "blender")
sys.path.insert(0, _TOOLS_BLENDER)
sys.path.insert(0, os.path.join(_TOOLS_BLENDER, "forge_sender"))

import extract_camera  # noqa: E402


class TestImports:
    """Verify the D-05 shim successfully imports the math helpers from
    forge_sender/flame_math.py and exposes them in extract_camera's
    namespace under the same names."""

    def test_shim_resolves_flame_math(self):
        assert hasattr(extract_camera, "_rot3_to_flame_euler_deg")
        assert hasattr(extract_camera, "_R_Z2Y")
        assert hasattr(extract_camera, "_camera_keyframe_set")
        assert hasattr(extract_camera, "_resolve_scale")
        assert hasattr(extract_camera, "build_v5_payload")

    def test_helpers_are_from_flame_math(self):
        """Verify the helpers are literally the same objects as
        flame_math exports — not shadowed by a local definition.
        Catches a regression where someone re-defines the math
        locally instead of trusting the import."""
        from flame_math import (_rot3_to_flame_euler_deg,  # noqa: E402
                                build_v5_payload)
        assert extract_camera._rot3_to_flame_euler_deg is _rot3_to_flame_euler_deg
        assert extract_camera.build_v5_payload is build_v5_payload


class TestArgparseSurface:
    """Ensure forge_flame.blender_bridge.build_extract_cmd's argv shape
    still parses cleanly after the refactor. build_extract_cmd emits
    ``--out``, ``--camera-name``, ``--scale`` flags (see
    tests/test_blender_bridge.py::TestBuildExtractCmd)."""

    def test_cli_flags_frozen(self):
        argv = ["blender", "--background", "/tmp/in.blend",
                "--python", "/tmp/extract_camera.py",
                "--",
                "--out", "/tmp/x.json",
                "--camera-name", "Camera",
                "--scale", "1.0"]
        args = extract_camera._parse_args(argv)
        assert args.out_path == "/tmp/x.json"
        assert args.camera_name == "Camera"
        assert args.scale == 1.0

    def test_scale_optional(self):
        """--scale is optional; omitting it leaves args.scale as None
        so build_v5_payload reads the stamped forge_bake_scale."""
        argv = ["blender", "--", "--out", "/tmp/x.json"]
        args = extract_camera._parse_args(argv)
        assert args.out_path == "/tmp/x.json"
        assert args.camera_name == "Camera"  # default
        assert args.scale is None

    def test_out_required(self):
        """--out has no default; missing it must fail argparse."""
        argv = ["blender", "--"]
        with pytest.raises(SystemExit):
            extract_camera._parse_args(argv)
