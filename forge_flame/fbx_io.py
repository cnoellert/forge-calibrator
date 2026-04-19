"""
Flame Action-cameras <-> FBX I/O.

Sibling of ``camera_io.py`` (JSON). FBX is the route for animated cameras
because Flame's ``PyAttribute`` exposes no keyframe API — only
``get_value``/``set_value``/``values``-as-bounds. See
``memory/flame_keyframe_api.md``. ``PyActionNode`` does expose symmetric
``export_fbx`` / ``import_fbx``, and the former has a ``bake_animation``
flag that lets Flame's own baker handle the keyframe math.

Critical gotcha: the built-in ``Perspective`` camera on every Action is
the viewport/tumble camera — it is NOT keyframable, and including it in
a ``bake_animation=True`` export is the suspected cause of Flame crashes
during the v6.2 probing work (see ``memory/flame_perspective_camera.md``).
This module filters it out of every export transparently; callers cannot
opt in.

Scope: no numpy, no cv2, no OCIO — just ``flame`` and stdlib. Safe to
import from a stripped-down deployment that doesn't have the forge env,
and safe to unit-test from outside Flame by duck-typing the camera
objects.

Units convention:
  Flame's ``export_fbx`` defaults to ``pixel_to_units=0.1`` — meaning one
  Flame pixel becomes 0.1 FBX units (centimeters). Example: a Flame
  camera at ``(0, 0, 4747.64)`` pixels exports as ``(0, 0, 474.76)`` in
  FBX. ``import_fbx`` takes the inverse scale as ``unit_to_pixels=10.0``
  so a straight round-trip cancels. We expose both as defaults matching
  Flame's own defaults — no reason to diverge unless a future user has
  calibrated against a different convention.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Optional


# Match Flame's ``export_fbx`` / ``import_fbx`` defaults. The 1:10 pair
# cancels on round-trip, so Flame pixel coordinates survive intact.
DEFAULT_PIXEL_TO_UNITS = 0.1
DEFAULT_UNIT_TO_PIXELS = 10.0


# =============================================================================
# Camera discovery (Perspective exclusion is the whole point of this module)
# =============================================================================


def iter_keyframable_cameras(action) -> list:
    """Return the Action's cameras that are safe to include in FBX exports.

    Excludes:
      - Non-camera nodes (lights, axes, models, surfaces, etc.).
      - The built-in ``Perspective`` camera (viewport/tumble camera, not
        keyframable; see ``memory/flame_perspective_camera.md``).

    Detection is by duck-typing (``position`` + ``rotation`` + ``fov`` +
    ``focal`` PyAttributes) rather than ``isinstance(flame.PyCoNode)``,
    so this function is unit-testable from outside Flame.
    """
    out = []
    for n in action.nodes:
        if not all(hasattr(n, attr) for attr in ("position", "rotation", "fov", "focal")):
            continue
        if n.name.get_value() == "Perspective":
            continue
        out.append(n)
    return out


@contextmanager
def _selection_restored(action):
    """Save and restore ``action.selected_nodes`` around a block.

    ``export_fbx(only_selected_nodes=True)`` requires us to mutate the
    Action's selection. This context manager snapshots it on entry and
    best-effort restores on exit (silently swallows restore errors —
    they'd be from nodes disappearing mid-call, not worth bubbling up)."""
    prior = list(action.selected_nodes.get_value())
    try:
        yield
    finally:
        try:
            action.selected_nodes.set_value(prior)
        except Exception:
            pass


# =============================================================================
# Export: Flame Action -> FBX
# =============================================================================


def export_action_cameras_to_fbx(
    action,
    out_path: str,
    *,
    cameras: Optional[list] = None,
    bake_animation: bool = True,
    pixel_to_units: float = DEFAULT_PIXEL_TO_UNITS,
    export_axes: bool = True,
    frame_rate: str = "23.976 fps",
) -> str:
    """Export one or more Action cameras to an FBX file.

    Args:
        action: PyActionNode whose cameras to export.
        out_path: destination FBX path. Parent directory is created.
        cameras: optional explicit list of camera nodes to export. If
            ``None``, all keyframable cameras are exported (Perspective
            is always excluded — see module docstring). If passed
            explicitly, Perspective is still filtered out unconditionally.
        bake_animation: resample animated attributes onto per-frame
            keyframes before writing. ``True`` is the usual choice for
            handing off to Blender. ``False`` preserves native curves
            but Blender may interpret control-point tangents differently.
        pixel_to_units: divisor applied to position values on export.
            Default 0.1 matches Flame's own default; ``import_fbx``'s
            ``unit_to_pixels=10.0`` inverse cancels it on round-trip.
        export_axes: include Action's Axis nodes in the FBX (defaults
            match Flame's own).
        frame_rate: FBX frame-rate label. Flame's own default is
            ``'23.976 fps'``; callers authoring for a specific project
            rate should pass the matching string.

    Returns:
        Absolute path of the written FBX file.

    Raises:
        ValueError: if no keyframable cameras remain after filtering.
        RuntimeError: if Flame's ``export_fbx`` returns ``False``.
    """
    if cameras is None:
        cameras = iter_keyframable_cameras(action)
    else:
        # Explicit list still has Perspective stripped — exclusion is
        # non-optional (see memory/flame_perspective_camera.md).
        cameras = [c for c in cameras if c.name.get_value() != "Perspective"]

    if not cameras:
        raise ValueError(
            "no keyframable cameras to export — Action has only the "
            "built-in Perspective camera (always excluded)")

    out_abs = os.path.abspath(out_path)
    os.makedirs(os.path.dirname(out_abs) or ".", exist_ok=True)

    with _selection_restored(action):
        action.selected_nodes.set_value(cameras)
        ok = action.export_fbx(
            out_abs,
            only_selected_nodes=True,
            pixel_to_units=pixel_to_units,
            frame_rate=frame_rate,
            bake_animation=bake_animation,
            export_axes=export_axes,
        )

    if not ok:
        raise RuntimeError(
            f"action.export_fbx({out_abs!r}) returned False — Flame "
            f"rejected the export (check Flame console for details)")
    return out_abs


# =============================================================================
# Import: FBX -> Flame Action
# =============================================================================


def import_fbx_to_action(
    action,
    in_path: str,
    *,
    bake_animation: bool = False,
    unit_to_pixels: float = DEFAULT_UNIT_TO_PIXELS,
    cameras: bool = True,
    lights: bool = False,
    models: bool = False,
    mesh_animations: bool = True,
    object_properties: bool = False,
    create_media: bool = False,
    auto_fit: bool = False,
) -> list:
    """Import an FBX into an Action and return the created nodes.

    Defaults are narrowed for the camera-round-trip use case: only
    cameras are ingested, ``create_media=False`` so no texture imports,
    ``auto_fit=False`` so the viewport doesn't re-navigate on import.

    ``bake_animation`` here defaults to ``False`` because an FBX arriving
    back from Blender already has the animation baked into AnimCurves —
    re-baking would be a no-op at best and a resampling artifact at
    worst.

    Args:
        action: PyActionNode to receive the imported nodes.
        in_path: path to an FBX file.
        unit_to_pixels: multiplier applied to position values on import.
            Default 10.0 inverses the export default of 0.1.
        (remaining flags map 1:1 to Flame's ``import_fbx`` signature.)

    Returns:
        List of newly created nodes (PyCoNode for cameras, etc.).

    Raises:
        FileNotFoundError: if ``in_path`` doesn't exist.
        RuntimeError: if Flame's ``import_fbx`` returns ``None``.
    """
    if not os.path.exists(in_path):
        raise FileNotFoundError(in_path)

    in_abs = os.path.abspath(in_path)
    result = action.import_fbx(
        in_abs,
        lights=lights,
        cameras=cameras,
        models=models,
        mesh_animations=mesh_animations,
        bake_animation=bake_animation,
        object_properties=object_properties,
        auto_fit=auto_fit,
        unit_to_pixels=unit_to_pixels,
        create_media=create_media,
    )
    if result is None:
        raise RuntimeError(
            f"action.import_fbx({in_abs!r}) returned None — Flame "
            f"rejected the import (check Flame console for details)")
    return list(result)
