"""
Unit tests for forge_flame.blender_bridge.

What we test:
  1. resolve_blender_bin — env override, platform defaults, PATH fallback,
     error message includes attempted locations.
  2. resolve_bake_script / resolve_extract_script — env override beats dev
     checkout beats install path; error when none exist.
  3. build_bake_cmd / build_extract_cmd — CLI shape matches what the scripts
     expect, positional vs flag ordering, --create-if-missing gating.

What we don't test:
  - Subprocess execution itself (requires a real Blender binary).
  - reveal_in_file_manager (launches external processes; best-effort by design).
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from forge_flame import blender_bridge  # noqa: E402
from forge_flame.blender_bridge import (  # noqa: E402
    _script_candidates,
    build_bake_cmd,
    build_extract_cmd,
    resolve_bake_script,
    resolve_blender_bin,
    resolve_extract_script,
)


# =============================================================================
# Binary resolution
# =============================================================================


class TestResolveBlenderBin:
    """resolve_blender_bin picks $FORGE_BLENDER_BIN first, falls through to
    platform defaults, then PATH, then raises with a useful message."""

    def test_env_override_wins(self, tmp_path, monkeypatch):
        # Fake executable
        fake_bin = tmp_path / "blender"
        fake_bin.write_text("#!/bin/sh\necho fake\n")
        fake_bin.chmod(0o755)
        monkeypatch.setenv("FORGE_BLENDER_BIN", str(fake_bin))

        assert resolve_blender_bin() == str(fake_bin)

    def test_env_override_missing_file_raises(self, tmp_path, monkeypatch):
        monkeypatch.setenv("FORGE_BLENDER_BIN", str(tmp_path / "does-not-exist"))
        # Clear PATH so `which blender` can't sneak in and succeed
        monkeypatch.setenv("PATH", "")
        # Also stub out the platform default list
        monkeypatch.setattr(blender_bridge, "_DEFAULT_BLENDER_BINS", {})
        with pytest.raises(FileNotFoundError, match="Blender binary not found"):
            resolve_blender_bin()

    def test_env_override_not_executable_skips_to_next(self, tmp_path, monkeypatch):
        # Non-executable file at the override path — should NOT be returned;
        # resolution should continue past it to PATH fallback.
        nonexec = tmp_path / "blender"
        nonexec.write_text("not executable")
        # Deliberately no chmod +x
        monkeypatch.setenv("FORGE_BLENDER_BIN", str(nonexec))
        monkeypatch.setattr(blender_bridge, "_DEFAULT_BLENDER_BINS", {})

        # Put a real executable on PATH
        real_dir = tmp_path / "bin"
        real_dir.mkdir()
        real_blender = real_dir / "blender"
        real_blender.write_text("#!/bin/sh\necho ok\n")
        real_blender.chmod(0o755)
        monkeypatch.setenv("PATH", str(real_dir))

        assert resolve_blender_bin() == str(real_blender)

    def test_platform_defaults_tried_when_no_override(self, tmp_path, monkeypatch):
        monkeypatch.delenv("FORGE_BLENDER_BIN", raising=False)
        fake_bin = tmp_path / "Blender"
        fake_bin.write_text("#!/bin/sh\n")
        fake_bin.chmod(0o755)
        monkeypatch.setattr(
            blender_bridge, "_DEFAULT_BLENDER_BINS", {sys.platform: [str(fake_bin)]})

        assert resolve_blender_bin() == str(fake_bin)

    def test_path_fallback_used_when_defaults_miss(self, tmp_path, monkeypatch):
        monkeypatch.delenv("FORGE_BLENDER_BIN", raising=False)
        monkeypatch.setattr(blender_bridge, "_DEFAULT_BLENDER_BINS", {})

        bindir = tmp_path / "bin"
        bindir.mkdir()
        blender = bindir / "blender"
        blender.write_text("#!/bin/sh\n")
        blender.chmod(0o755)
        monkeypatch.setenv("PATH", str(bindir))

        assert resolve_blender_bin() == str(blender)

    def test_error_message_lists_attempted_locations(self, monkeypatch):
        monkeypatch.delenv("FORGE_BLENDER_BIN", raising=False)
        monkeypatch.setattr(blender_bridge, "_DEFAULT_BLENDER_BINS", {})
        monkeypatch.setenv("PATH", "")

        with pytest.raises(FileNotFoundError) as exc_info:
            resolve_blender_bin()
        msg = str(exc_info.value)
        assert "FORGE_BLENDER_BIN" in msg
        assert "Tried:" in msg

    # ---------------------------------------------------------------------
    # Glob / expanduser resolution (260429-fk5)
    # ---------------------------------------------------------------------

    def test_glob_expansion_finds_versioned_linux_binary(self, tmp_path, monkeypatch):
        """A `*` in a default candidate path must glob-match a real install."""
        monkeypatch.delenv("FORGE_BLENDER_BIN", raising=False)
        monkeypatch.setenv("PATH", "")

        target_dir = tmp_path / "blender-4.5"
        target_dir.mkdir()
        target = target_dir / "blender"
        target.write_text("#!/bin/sh\n")
        target.chmod(0o755)

        pattern = str(tmp_path / "blender-*" / "blender")
        monkeypatch.setattr(
            blender_bridge, "_DEFAULT_BLENDER_BINS", {sys.platform: [pattern]})

        assert resolve_blender_bin() == str(target)

    def test_glob_multi_match_prefers_highest_sorted(self, tmp_path, monkeypatch):
        """When multiple versioned dirs match the glob, the highest-sorted wins."""
        monkeypatch.delenv("FORGE_BLENDER_BIN", raising=False)
        monkeypatch.setenv("PATH", "")

        for ver in ("4.4", "4.5"):
            d = tmp_path / f"blender-{ver}"
            d.mkdir()
            b = d / "blender"
            b.write_text("#!/bin/sh\n")
            b.chmod(0o755)

        pattern = str(tmp_path / "blender-*" / "blender")
        monkeypatch.setattr(
            blender_bridge, "_DEFAULT_BLENDER_BINS", {sys.platform: [pattern]})

        result = resolve_blender_bin()
        assert result.endswith(os.path.join("blender-4.5", "blender")), \
            f"expected blender-4.5 to win sort; got {result}"

    def test_env_override_still_beats_glob_match(self, tmp_path, monkeypatch):
        """FORGE_BLENDER_BIN must take priority over any glob-matched default."""
        # Glob match candidate
        glob_dir = tmp_path / "blender-4.5"
        glob_dir.mkdir()
        glob_bin = glob_dir / "blender"
        glob_bin.write_text("#!/bin/sh\n")
        glob_bin.chmod(0o755)

        # Env override candidate (different binary)
        override_bin = tmp_path / "override-blender"
        override_bin.write_text("#!/bin/sh\n")
        override_bin.chmod(0o755)

        monkeypatch.setenv("FORGE_BLENDER_BIN", str(override_bin))
        pattern = str(tmp_path / "blender-*" / "blender")
        monkeypatch.setattr(
            blender_bridge, "_DEFAULT_BLENDER_BINS", {sys.platform: [pattern]})

        assert resolve_blender_bin() == str(override_bin)

    def test_path_fallback_when_all_globs_miss(self, tmp_path, monkeypatch):
        """If every glob misses on disk, PATH fallback still fires."""
        monkeypatch.delenv("FORGE_BLENDER_BIN", raising=False)

        # A glob with no matches
        pattern = str(tmp_path / "no-such-*" / "blender")
        monkeypatch.setattr(
            blender_bridge, "_DEFAULT_BLENDER_BINS", {sys.platform: [pattern]})

        # Real blender on PATH
        bindir = tmp_path / "bin"
        bindir.mkdir()
        path_blender = bindir / "blender"
        path_blender.write_text("#!/bin/sh\n")
        path_blender.chmod(0o755)
        monkeypatch.setenv("PATH", str(bindir))

        assert resolve_blender_bin() == str(path_blender)

    def test_darwin_glob_resolves_versioned_app_bundle(self, tmp_path, monkeypatch):
        """Darwin-style versioned `Blender X.Y.app` bundle is discovered via glob."""
        monkeypatch.delenv("FORGE_BLENDER_BIN", raising=False)
        monkeypatch.setenv("PATH", "")

        macos_dir = tmp_path / "Blender 4.5.app" / "Contents" / "MacOS"
        macos_dir.mkdir(parents=True)
        target = macos_dir / "Blender"
        target.write_text("#!/bin/sh\n")
        target.chmod(0o755)

        pattern = str(tmp_path / "Blender*.app" / "Contents" / "MacOS" / "Blender")
        monkeypatch.setattr(
            blender_bridge, "_DEFAULT_BLENDER_BINS", {sys.platform: [pattern]})

        result = resolve_blender_bin()
        assert result.endswith(os.path.join(
            "Blender 4.5.app", "Contents", "MacOS", "Blender")), \
            f"expected versioned .app bundle path; got {result}"

    def test_expanduser_handles_tilde_paths(self, tmp_path, monkeypatch):
        """A `~/...` candidate must expand against $HOME at resolve time."""
        monkeypatch.delenv("FORGE_BLENDER_BIN", raising=False)
        monkeypatch.setenv("PATH", "")
        monkeypatch.setenv("HOME", str(tmp_path))

        apps_dir = tmp_path / "Apps" / "blender-4.5"
        apps_dir.mkdir(parents=True)
        target = apps_dir / "blender"
        target.write_text("#!/bin/sh\n")
        target.chmod(0o755)

        monkeypatch.setattr(
            blender_bridge, "_DEFAULT_BLENDER_BINS",
            {sys.platform: ["~/Apps/blender-*/blender"]})

        result = resolve_blender_bin()
        assert os.path.realpath(result) == os.path.realpath(str(target)), \
            f"expected expanduser-resolved path under tmp HOME; got {result}"


# =============================================================================
# Script resolution
# =============================================================================


class TestScriptCandidates:
    """_script_candidates orders paths: override > dev > install."""

    def test_override_first(self, tmp_path, monkeypatch):
        monkeypatch.setenv("FORGE_BLENDER_SCRIPTS", str(tmp_path))
        candidates = _script_candidates("bake_camera.py")
        assert candidates[0] == str(tmp_path / "bake_camera.py")

    def test_no_override_starts_with_dev_checkout(self, monkeypatch):
        monkeypatch.delenv("FORGE_BLENDER_SCRIPTS", raising=False)
        candidates = _script_candidates("bake_camera.py")
        # First candidate should be the dev checkout: <repo>/tools/blender/
        assert candidates[0].endswith(os.path.join("tools", "blender", "bake_camera.py"))

    def test_install_location_always_last(self, tmp_path, monkeypatch):
        monkeypatch.setenv("FORGE_BLENDER_SCRIPTS", str(tmp_path))
        candidates = _script_candidates("extract_camera.py")
        assert candidates[-1].startswith("/opt/Autodesk/shared/forge_blender_scripts/")


class TestResolveScripts:
    """resolve_bake_script / resolve_extract_script return the first existing
    candidate; raise FileNotFoundError with the list when none exist."""

    def test_finds_in_dev_checkout_by_default(self, monkeypatch):
        monkeypatch.delenv("FORGE_BLENDER_SCRIPTS", raising=False)
        # In this repo checkout, tools/blender/bake_camera.py exists — this
        # should resolve without env override.
        path = resolve_bake_script()
        assert path.endswith(os.path.join("tools", "blender", "bake_camera.py"))
        assert os.path.isfile(path)

    def test_override_beats_dev_checkout(self, tmp_path, monkeypatch):
        # Create a fake bake_camera.py in the override dir.
        fake = tmp_path / "bake_camera.py"
        fake.write_text("# fake\n")
        monkeypatch.setenv("FORGE_BLENDER_SCRIPTS", str(tmp_path))

        assert resolve_bake_script() == str(fake)

    def test_extract_also_resolves(self, monkeypatch):
        monkeypatch.delenv("FORGE_BLENDER_SCRIPTS", raising=False)
        path = resolve_extract_script()
        assert path.endswith(os.path.join("tools", "blender", "extract_camera.py"))

    def test_error_when_none_exist(self, tmp_path, monkeypatch):
        # Point override at an empty dir; stub dev + install paths so they
        # don't accidentally hit files.
        monkeypatch.setenv("FORGE_BLENDER_SCRIPTS", str(tmp_path))
        monkeypatch.setattr(
            blender_bridge, "_INSTALL_SCRIPT_DIR", str(tmp_path / "also-empty"))
        # And mask the dev checkout by monkeypatching _script_candidates to
        # only return what's under the override
        monkeypatch.setattr(
            blender_bridge, "_script_candidates",
            lambda name: [str(tmp_path / name)])

        with pytest.raises(FileNotFoundError, match="bake_camera.py not found"):
            resolve_bake_script()


# =============================================================================
# CLI composition
# =============================================================================


class TestBuildBakeCmd:
    """The argv list we pass to subprocess.run must match what bake_camera.py
    actually parses via argparse."""

    def test_basic_shape(self):
        cmd = build_bake_cmd(
            "/tmp/in.json", "/tmp/out.blend",
            blender_bin="/fake/blender",
            bake_script="/fake/bake_camera.py",
        )
        assert cmd[0] == "/fake/blender"
        assert cmd[1] == "--background"
        assert "--python" in cmd
        assert "/fake/bake_camera.py" in cmd
        assert "--" in cmd

    def test_args_come_after_separator(self):
        cmd = build_bake_cmd(
            "/tmp/in.json", "/tmp/out.blend",
            blender_bin="/fake/b", bake_script="/fake/bake.py",
        )
        sep = cmd.index("--")
        # Script-level args must come AFTER the "--" separator, else Blender
        # consumes them as its own args.
        assert "--in" in cmd[sep:]
        assert "--out" in cmd[sep:]
        assert "--camera-name" in cmd[sep:]
        assert "--scale" in cmd[sep:]

    def test_in_out_values_match(self):
        cmd = build_bake_cmd(
            "/path/to/camera.json", "/path/to/output.blend",
            blender_bin="/b", bake_script="/s",
        )
        in_idx = cmd.index("--in")
        out_idx = cmd.index("--out")
        assert cmd[in_idx + 1] == "/path/to/camera.json"
        assert cmd[out_idx + 1] == "/path/to/output.blend"

    def test_camera_name_flag(self):
        cmd = build_bake_cmd(
            "a", "b", camera_name="ForgeCam",
            blender_bin="/b", bake_script="/s",
        )
        idx = cmd.index("--camera-name")
        assert cmd[idx + 1] == "ForgeCam"

    def test_scale_flag(self):
        cmd = build_bake_cmd(
            "a", "b", scale=500.0,
            blender_bin="/b", bake_script="/s",
        )
        idx = cmd.index("--scale")
        assert cmd[idx + 1] == "500.0"

    def test_create_if_missing_present_by_default(self):
        cmd = build_bake_cmd("a", "b", blender_bin="/b", bake_script="/s")
        assert "--create-if-missing" in cmd

    def test_create_if_missing_omitted_when_false(self):
        cmd = build_bake_cmd(
            "a", "b", create_if_missing=False,
            blender_bin="/b", bake_script="/s",
        )
        assert "--create-if-missing" not in cmd


class TestBuildExtractCmd:
    """extract_camera.py wants the .blend as a POSITIONAL arg before --python,
    not a flag after -- (Blender opens the .blend, then runs the script
    against it)."""

    def test_blend_is_positional_before_python(self):
        cmd = build_extract_cmd(
            "/tmp/in.blend", "/tmp/out.json",
            blender_bin="/fake/blender",
            extract_script="/fake/extract_camera.py",
        )
        python_idx = cmd.index("--python")
        background_idx = cmd.index("--background")
        # .blend must come after --background but before --python
        blend_idx = cmd.index("/tmp/in.blend")
        assert background_idx < blend_idx < python_idx

    def test_out_after_separator(self):
        cmd = build_extract_cmd(
            "/tmp/in.blend", "/tmp/out.json",
            blender_bin="/b", extract_script="/s",
        )
        sep = cmd.index("--")
        out_idx = cmd.index("--out")
        assert sep < out_idx
        assert cmd[out_idx + 1] == "/tmp/out.json"

    def test_camera_name_defaults_to_Camera(self):
        cmd = build_extract_cmd(
            "in.blend", "out.json",
            blender_bin="/b", extract_script="/s",
        )
        idx = cmd.index("--camera-name")
        assert cmd[idx + 1] == "Camera"
