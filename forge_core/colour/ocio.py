"""
OCIO display-view pipeline — host-agnostic building block.

Wraps ``PyOpenColorIO.Config.CreateFromFile`` + ``DisplayViewTransform`` into
an object that hands back cached CPU processors per source colour space, so
callers don't have to think about the three-level cache (config → DVT →
processor) every time they want to tonemap a float buffer.

Why DisplayViewTransform and not ``getProcessor(src, dst)``:
    A bare ``src → dst`` processor just does colour-space conversion and
    hard-clips highlights. DisplayViewTransform runs the full view pipeline
    (RRT + ODT), so highlights roll off softly through an ACES tonemap.
    For a preview UI like Camera Match where users mark lines against bright
    skies, that difference is what makes the preview usable.

Host integration:
    This module has no path logic. Callers resolve a config path their own
    way and pass it in. For Flame, use ``resolve_flame_aces2_config()``
    below, which globs Flame's shipped configs. For trafFIK or any other
    host, resolve however you want (``$OCIO`` env, explicit path, etc.).

Typical usage:

    from forge_core.colour.ocio import OcioPipeline, resolve_flame_aces2_config

    pipeline = OcioPipeline(
        config_path=resolve_flame_aces2_config(),
        display="sRGB - Display",
        view="ACES 2.0 - SDR 100 nits (Rec.709)",
    )
    proc = pipeline.get_processor("ARRI LogC4")
    if proc:
        proc.applyRGB(float_rgb_array)  # in-place
"""

from __future__ import annotations

import glob
import os
import re
from typing import Optional


# =============================================================================
# Path resolution — Flame-specific helper. Not required by OcioPipeline itself.
# =============================================================================

_DEFAULT_FLAME_CONFIGS_ROOT = "/opt/Autodesk/colour_mgmt/configs/flame_configs"
_DEFAULT_ACES2_SUBPATH = "aces2.0_config/config.ocio"


def resolve_flame_aces2_config(
    configs_root: str = _DEFAULT_FLAME_CONFIGS_ROOT,
    config_subpath: str = _DEFAULT_ACES2_SUBPATH,
) -> Optional[str]:
    """Find the newest shipped aces2.0_config under Flame's colour_mgmt tree.

    We deliberately don't honour ``$OCIO``: Camera Match's preview pipeline is
    pinned to ACES-2.0-specific view names ("ACES 2.0 - SDR 100 nits (Rec.709)")
    that only exist in Autodesk's aces2.0_config. A studio-custom ``$OCIO``
    would load but fail silently at setView time. Glob the shipped configs
    instead so the tool auto-tracks Flame version bumps (2026.0 → 2027.0 → …).

    Override ``configs_root`` / ``config_subpath`` for tests or non-default
    Flame installs.

    Returns the resolved path as str, or None if no config is found.
    """
    pattern = os.path.join(configs_root, "*", config_subpath)
    hits = glob.glob(pattern)
    if not hits:
        return None

    def _ver_key(p: str):
        # /opt/Autodesk/colour_mgmt/configs/flame_configs/2026.0/aces2.0_config/config.ocio
        #                                                  ^^^^^^ pull this segment
        parts = p.split(os.sep)
        try:
            idx = parts.index(os.path.basename(configs_root.rstrip(os.sep)))
            ver = parts[idx + 1]
        except (ValueError, IndexError):
            return (0, 0, p)
        m = re.match(r"(\d+)\.(\d+)", ver)
        if not m:
            return (0, 0, p)
        return (int(m.group(1)), int(m.group(2)), p)

    hits.sort(key=_ver_key, reverse=True)
    return hits[0]


# =============================================================================
# Pipeline — the reusable piece
# =============================================================================


class OcioPipeline:
    """Build cached CPU processors for a fixed (config, display, view) triple.

    One pipeline per display/view target; call ``get_processor(src_cs)`` with
    whatever source colour space the incoming buffer is tagged as. Failures
    at any stage (missing config, bad view name, unknown source) print a
    diagnostic line and return None — the caller decides whether to fall
    back to a passthrough display or to stop.

    Thread-safety: not thread-safe. The caches are plain dicts. Camera Match's
    preview path is single-threaded (main Qt thread), so this is fine. If you
    ever call it from background workers, gate ``get_processor`` with a lock.
    """

    def __init__(self, config_path: Optional[str], display: str, view: str):
        self._config_path = config_path
        self._display = display
        self._view = view
        self._cfg = None
        self._cfg_loaded = False
        self._procs: dict = {}

    @property
    def config_path(self) -> Optional[str]:
        return self._config_path

    @property
    def display(self) -> str:
        return self._display

    @property
    def view(self) -> str:
        return self._view

    def get_config(self):
        """Load and cache the OCIO Config. Returns None if the path is missing
        or the file won't parse. Safe to call repeatedly."""
        if self._cfg_loaded:
            return self._cfg
        self._cfg_loaded = True
        if self._config_path is None:
            print(
                "OCIO config path is None — preview will use passthrough for float sources."
            )
            return None
        try:
            import PyOpenColorIO as OCIO
        except ImportError as e:
            print(f"PyOpenColorIO not importable: {e}")
            return None
        try:
            self._cfg = OCIO.Config.CreateFromFile(self._config_path)
            print(f"OCIO config: {self._config_path}")
        except Exception as e:
            print(f"OCIO config load failed ({self._config_path}): {e}")
            self._cfg = None
        return self._cfg

    def get_processor(self, src_cs: str):
        """Return a cached CPU processor that maps ``src_cs`` → display/view.

        Returns None if the config didn't load or the DisplayViewTransform
        couldn't be constructed (bad src name, bad view name, etc.). The
        None result is also cached — retrying the same bad source won't
        re-probe OCIO on every frame."""
        if src_cs in self._procs:
            return self._procs[src_cs]
        cfg = self.get_config()
        proc = None
        if cfg is not None:
            try:
                import PyOpenColorIO as OCIO
                dvt = OCIO.DisplayViewTransform()
                dvt.setSrc(src_cs)
                dvt.setDisplay(self._display)
                dvt.setView(self._view)
                proc = cfg.getProcessor(dvt).getDefaultCPUProcessor()
            except Exception as e:
                print(
                    f"OCIO DVT {src_cs} -> {self._display}/{self._view} failed: {e}"
                )
                proc = None
        self._procs[src_cs] = proc
        return proc
