"""
forge_flame.blender_bridge — Flame ↔ Blender subprocess orchestration.

Thin wrapper around the three things the hook needs to drive the bake/extract
pipeline from a Flame batch action:

  1. Locate the Blender binary.
  2. Locate the bake_camera.py / extract_camera.py scripts in the installed
     or dev-checkout location.
  3. Run them with the correct CLI args and surface errors usefully.
  4. Reveal the resulting .blend in the OS file manager.

Kept deliberately Flame-free and Qt-free so the path + CLI composition logic
is unit-testable without either host. The hook imports this module and
supplies its own Qt dialogs for camera/path pickers.

Path resolution strategy
========================

Blender binary (in order of preference):
  1. $FORGE_BLENDER_BIN environment override
  2. Platform defaults (/Applications/Blender.app/... on macOS, /usr/bin/blender
     on Linux)
  3. `blender` on PATH

Scripts (in order of preference):
  1. $FORGE_BLENDER_SCRIPTS environment override (directory containing
     bake_camera.py + extract_camera.py)
  2. Dev checkout: ../tools/blender/ relative to this file (works when
     forge_flame/ lives at the repo root)
  3. Install location: /opt/Autodesk/shared/forge_blender_scripts/ — a path
     DELIBERATELY OUTSIDE /opt/Autodesk/shared/python/. These files top-import
     bpy/mathutils and are not importable from Flame's Python 3.11; placing
     them on Flame's hook scan path trips the loader with ModuleNotFoundError
     and disables the hook (surfaced live during phase 04.2 HUMAN-UAT).
"""

from __future__ import annotations

import glob
import os
import shutil
import subprocess
import sys
from typing import List, Optional


# =============================================================================
# Defaults
# =============================================================================

# Where Blender typically lives on supported platforms. Each entry is a path
# pattern that supports `~` (expanduser) and `*` (glob) — `resolve_blender_bin`
# expands and globs each candidate and returns the first executable match.
# Multi-match results are sorted in DESCENDING order so newer versioned
# installs (Blender 4.5 > Blender 4.4) win without manual configuration.
_DEFAULT_BLENDER_BINS = {
    "darwin": [
        "/Applications/Blender.app/Contents/MacOS/Blender",
        "/Applications/Blender*.app/Contents/MacOS/Blender",
        "~/Applications/Blender.app/Contents/MacOS/Blender",
        "~/Applications/Blender*.app/Contents/MacOS/Blender",
    ],
    "linux": [
        "/usr/bin/blender",
        "/usr/local/bin/blender",
        "/opt/blender/blender",
        "/opt/blender-*/blender",
        "~/Apps/blender-*/blender",
    ],
}

# Installed location for the bake/extract scripts — the installer populates
# this. DELIBERATELY outside /opt/Autodesk/shared/python/ because the scripts
# top-import bpy/mathutils; placing them on Flame's hook scan path would trip
# its loader with ModuleNotFoundError. Kept as a module constant so tests can
# mock it without monkey-patching os.path calls.
_INSTALL_SCRIPT_DIR = "/opt/Autodesk/shared/forge_blender_scripts"


# =============================================================================
# Binary resolution
# =============================================================================


def resolve_blender_bin() -> str:
    """Return the absolute path to the Blender binary.

    Raises:
        FileNotFoundError: with a message listing the locations we tried,
            suitable for surfacing directly in a Flame error dialog.
    """
    tried: List[str] = []

    override = os.environ.get("FORGE_BLENDER_BIN")
    if override:
        tried.append(f"$FORGE_BLENDER_BIN={override!r}")
        if os.path.isfile(override) and os.access(override, os.X_OK):
            return override

    for candidate in _DEFAULT_BLENDER_BINS.get(sys.platform, []):
        # Record the raw user-facing pattern (with `~`/`*` intact) so the
        # error message preserves what's configured, not its expansion.
        tried.append(candidate)
        expanded = os.path.expanduser(candidate)
        # glob.glob returns [path] for an existing literal path with no
        # wildcards and [] for non-existent paths — one code path covers
        # both literal and glob candidates.
        matches = sorted(glob.glob(expanded), reverse=True)
        for match in matches:
            if os.path.isfile(match) and os.access(match, os.X_OK):
                return match

    on_path = shutil.which("blender")
    tried.append("`which blender` (PATH)")
    if on_path:
        return on_path

    raise FileNotFoundError(
        "Blender binary not found. Tried: " + ", ".join(tried)
        + ". Set FORGE_BLENDER_BIN to point at your Blender executable.")


# =============================================================================
# Script resolution
# =============================================================================


def _script_candidates(script_name: str) -> List[str]:
    """Ordered list of paths to check for `script_name`.

    The order here IS the priority order: env override > dev checkout >
    installed. Exposed for tests; not meant for hook use."""
    candidates: List[str] = []

    override_dir = os.environ.get("FORGE_BLENDER_SCRIPTS")
    if override_dir:
        candidates.append(os.path.join(override_dir, script_name))

    # Dev checkout: this file is in <repo>/forge_flame/, scripts are in
    # <repo>/tools/blender/, so ../tools/blender/ does it.
    this_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(this_dir)
    candidates.append(os.path.join(repo_root, "tools", "blender", script_name))

    # Installed location.
    candidates.append(os.path.join(_INSTALL_SCRIPT_DIR, script_name))

    return candidates


def _resolve_script(script_name: str) -> str:
    """Return the first existing path in the candidate list, or raise."""
    candidates = _script_candidates(script_name)
    for candidate in candidates:
        if os.path.isfile(candidate):
            return os.path.abspath(candidate)
    raise FileNotFoundError(
        f"{script_name} not found. Tried: {', '.join(candidates)}. "
        f"Set FORGE_BLENDER_SCRIPTS to the directory containing the scripts, "
        f"or run the installer to populate {_INSTALL_SCRIPT_DIR}.")


def resolve_bake_script() -> str:
    """Absolute path to tools/blender/bake_camera.py, or raise."""
    return _resolve_script("bake_camera.py")


def resolve_extract_script() -> str:
    """Absolute path to tools/blender/extract_camera.py, or raise."""
    return _resolve_script("extract_camera.py")


# =============================================================================
# CLI composition (pure — subprocess.run is separate, so tests can verify
# the command shape without actually launching Blender)
# =============================================================================


def build_bake_cmd(
    json_path: str,
    blend_path: str,
    *,
    camera_name: str = "Camera",
    scale: float = 1000.0,
    create_if_missing: bool = True,
    blender_bin: Optional[str] = None,
    bake_script: Optional[str] = None,
) -> List[str]:
    """Compose the argv list for a Blender bake invocation.

    Split from run_bake so tests can assert the command shape without
    actually running Blender. The blender_bin and bake_script kwargs
    exist to let tests inject fake paths."""
    bin_path = blender_bin or resolve_blender_bin()
    script = bake_script or resolve_bake_script()
    cmd = [
        bin_path,
        "--background",
        "--python", script,
        "--",
        "--in", str(json_path),
        "--out", str(blend_path),
        "--camera-name", camera_name,
        "--scale", str(float(scale)),
    ]
    if create_if_missing:
        cmd.append("--create-if-missing")
    return cmd


def build_extract_cmd(
    blend_path: str,
    json_path: str,
    *,
    camera_name: str = "Camera",
    blender_bin: Optional[str] = None,
    extract_script: Optional[str] = None,
) -> List[str]:
    """Compose the argv list for a Blender extract invocation.

    Note: Blender requires the .blend path as a positional arg BEFORE --python
    (Blender opens the file then runs the script against it)."""
    bin_path = blender_bin or resolve_blender_bin()
    script = extract_script or resolve_extract_script()
    return [
        bin_path,
        "--background",
        str(blend_path),
        "--python", script,
        "--",
        "--out", str(json_path),
        "--camera-name", camera_name,
    ]


# =============================================================================
# Subprocess runners
# =============================================================================


def run_bake(
    json_path: str,
    blend_path: str,
    *,
    camera_name: str = "Camera",
    scale: float = 1000.0,
    create_if_missing: bool = True,
) -> subprocess.CompletedProcess:
    """Run bake_camera.py through Blender. Returns CompletedProcess on success.

    Raises:
        FileNotFoundError: if Blender or the script can't be located.
        subprocess.CalledProcessError: if bake exits non-zero. The stderr
            attribute on the exception carries Blender's error output for
            surfacing in the hook's dialog.
    """
    cmd = build_bake_cmd(
        json_path, blend_path,
        camera_name=camera_name, scale=scale,
        create_if_missing=create_if_missing,
    )
    return subprocess.run(cmd, check=True, capture_output=True, text=True)


def run_extract(
    blend_path: str,
    json_path: str,
    *,
    camera_name: str = "Camera",
) -> subprocess.CompletedProcess:
    """Run extract_camera.py through Blender. Returns CompletedProcess."""
    cmd = build_extract_cmd(
        blend_path, json_path, camera_name=camera_name,
    )
    return subprocess.run(cmd, check=True, capture_output=True, text=True)


# =============================================================================
# OS file manager reveal
# =============================================================================


def reveal_in_file_manager(path: str) -> None:
    """Open the OS file manager with `path` highlighted (best-effort).

    macOS: `open -R path` selects the file in Finder.
    Linux: `xdg-open <parent dir>` — can't highlight a specific file portably
           across distros, so opens the containing folder instead.
    Other: no-op.

    Never raises — reveal failing is cosmetic; the hook shouldn't abort over it.
    """
    try:
        abs_path = os.path.abspath(path)
        if sys.platform == "darwin":
            subprocess.run(["open", "-R", abs_path], check=False)
        elif sys.platform == "linux":
            parent = os.path.dirname(abs_path)
            subprocess.run(["xdg-open", parent], check=False)
    except Exception:
        pass
