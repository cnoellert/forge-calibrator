"""
Flame Action-camera <-> JSON I/O.

Bridges the Flame PyAction camera API to the v5 JSON contract used by
tools/blender/bake_camera.py and extract_camera.py (see PASSOFF.md v5
"Data contract"). Writing and reading the JSON here closes the loop
for a full Flame -> Blender -> Flame round-trip:

    Flame solved camera
      -> export_flame_camera_to_json          (this file)
      -> tools/blender/bake_camera.py         (.blend, editable in Blender)
      -> [user adjusts camera in Blender]
      -> tools/blender/extract_camera.py      (JSON out)
      -> import_json_to_flame_camera          (this file)

Scope (v1): single-frame only. The hook currently produces a static
solve; this module mirrors that and doesn't attempt Flame keyframing.
When multi-frame animation is needed, add a frame-loop variant that
calls Flame's PyAttribute keyframe API (unverified shape at time of
writing — will want a live Flame session to confirm).

Conventions matched to the hook's apply pipeline:

  - cam.position: (x, y, z) tuple in Flame pixel-units
  - cam.rotation: (rx, ry, rz) tuple in degrees, Flame ZYX-with-X,Y-negated
  - cam.fov:      vertical FOV in degrees (set directly rather than
                  trying to drive `focal` — `focal` alone gives wrong FOV
                  because Flame's default film back is 16mm Super 16)
  - cam.focal:    read-only for our purposes; derive film_back from fov+focal

Dependencies: flame (Flame-provided), json, math — no numpy, no cv2, no
OCIO. So this module is safe to import from a stripped-down deployment
that doesn't have the forge conda env.
"""

from __future__ import annotations

import json
import math
import os
from typing import Optional, Tuple


# =============================================================================
# Pure-math FOV <-> focal converters (no flame dependency — testable)
# =============================================================================


def vfov_deg_from_focal(focal_mm: float, film_back_mm: float) -> float:
    """Vertical FOV in degrees for a camera with the given focal + film back.

    Uses the thin-lens pinhole model: ``vfov = 2 · atan(h_sensor / (2·f))``.
    film_back_mm here is the SENSOR HEIGHT used for vertical FOV. Flame's
    film back convention is a single scalar — caller must know whether
    it refers to the horizontal or vertical dimension; this function
    just takes whatever's in ``film_back_mm`` as the relevant dimension."""
    if focal_mm <= 0:
        raise ValueError(f"focal_mm must be positive, got {focal_mm}")
    if film_back_mm <= 0:
        raise ValueError(f"film_back_mm must be positive, got {film_back_mm}")
    return math.degrees(2.0 * math.atan(film_back_mm / (2.0 * focal_mm)))


def focal_from_vfov_deg(vfov_deg: float, film_back_mm: float) -> float:
    """Focal length in mm for a camera with the given vertical FOV and film back.

    Inverse of ``vfov_deg_from_focal``. Returns focal in the same mm units
    as film_back_mm."""
    if not (0.0 < vfov_deg < 180.0):
        raise ValueError(f"vfov_deg must be in (0, 180), got {vfov_deg}")
    if film_back_mm <= 0:
        raise ValueError(f"film_back_mm must be positive, got {film_back_mm}")
    return film_back_mm / (2.0 * math.tan(math.radians(vfov_deg) / 2.0))


def film_back_from_fov_focal(vfov_deg: float, focal_mm: float) -> float:
    """Recover film-back mm from a camera's reported FOV + focal.

    Used on export when Flame reports both fov (which it drives the 3D
    projection with) and focal (display-only mm value) — these two
    together imply the film back Flame is effectively using."""
    if focal_mm <= 0:
        raise ValueError(f"focal_mm must be positive, got {focal_mm}")
    if not (0.0 < vfov_deg < 180.0):
        raise ValueError(f"vfov_deg must be in (0, 180), got {vfov_deg}")
    return 2.0 * focal_mm * math.tan(math.radians(vfov_deg) / 2.0)


# =============================================================================
# Export: Flame cam_node -> JSON
# =============================================================================


def export_flame_camera_to_json(
    cam_node,
    out_path: str,
    *,
    frame: int,
    width: int,
    height: int,
    film_back_mm: Optional[float] = None,
    frame_rate: Optional[str] = None,
    flame_to_blender_scale: Optional[float] = None,
    custom_properties: Optional[dict] = None,
) -> str:
    """Serialize a Flame Action camera node to the v5 JSON contract.

    Args:
        cam_node: PyAction camera node (the object with .position, .rotation,
            .fov, .focal PyAttributes — i.e. ``action.nodes[0]`` or any
            named camera under an Action).
        out_path: destination JSON path. Parent directory is created if missing.
        frame: frame number to stamp on the single frame entry. The hook
            knows the frame the solve was performed on; pass that through.
        width, height: plate resolution in pixels. Not stored on the cam_node
            directly — the caller (hook) has these from the clip context.
        film_back_mm: optional override. If None, we derive it from the
            camera's fov + focal. Pass explicitly if you want to pin a
            specific value (e.g. 36.0 for full-frame parity with Blender).
        frame_rate: optional Flame-project fps label (e.g. "24 fps",
            "23.976 fps"). When provided, written as a top-level
            ``frame_rate`` key on the JSON payload. Consumed by
            ``tools/blender/bake_camera.py::_bake`` which feeds
            ``forge_sender/__init__.py::_resolve_frame_rate`` via the
            ``forge_bake_frame_rate`` Blender custom property.
            When ``None``, no ``frame_rate`` key is emitted (backward-
            compatible with pre-v6.3 consumers).
        flame_to_blender_scale: optional per-camera Flame↔Blender world
            scale factor for the bake/extract round-trip. Allowed
            values are restricted to the discrete log10 ladder
            ``{0.01, 0.1, 1.0, 10.0, 100.0}`` (validated by
            ``tools/blender/bake_camera.py::_validate_flame_to_blender_scale``
            — this serializer does NOT validate; it's a thin emit).
            When provided, written as a top-level ``flame_to_blender_scale``
            key on the JSON payload; ``bake_camera.py`` then uses it as
            the position divisor with precedence over its CLI ``--scale``
            flag. When ``None``, no key is emitted (backward-compatible
            with pre-v6.4 consumers and with the existing hook call site
            in ``flame/camera_match_hook.py`` that still drives the CLI
            ``scale=1000.0`` viewport-navigation hack). Uses
            ``is not None`` semantics — ``1.0`` and ``0.01`` are valid
            values that must round-trip explicitly when the caller asked
            for them; truthy semantics would silently drop a meaningful
            ``1.0``.
        custom_properties: optional dict of caller-supplied metadata to
            stamp into the v5 JSON payload under a top-level
            ``custom_properties`` key. Values must be JSON-serialisable.
            See ``tools/blender/bake_camera.py::_stamp_metadata``, which
            consumes this field on bake. When ``None`` or empty, no
            ``custom_properties`` key is emitted (backward-compatible
            with pre-v6.3 consumers).

    Returns:
        Absolute path of the written JSON file.
    """
    position = tuple(cam_node.position.get_value())
    rotation = tuple(cam_node.rotation.get_value())
    vfov_deg = float(cam_node.fov.get_value())

    if film_back_mm is None:
        # Derive film_back from Flame's own (fov, focal). Flame defaults to
        # 16mm Super 16, so expect ~16.0 unless the camera's film_type was
        # changed elsewhere. The (fov, focal, film_back) trio is tautologically
        # self-consistent in this branch.
        focal_mm = float(cam_node.focal.get_value())
        film_back_mm = film_back_from_fov_focal(vfov_deg, focal_mm)
    else:
        # Caller pinned a specific film_back (commonly 36.0 for full-frame
        # compositing parity with Blender). Recompute focal from (fov, new
        # film_back) so the JSON trio is self-consistent — using Flame's
        # reported cam.focal here would describe a different FOV.
        focal_mm = focal_from_vfov_deg(vfov_deg, film_back_mm)

    payload = {
        "width": int(width),
        "height": int(height),
        "film_back_mm": float(film_back_mm),
        "frames": [
            {
                "frame": int(frame),
                "position": [float(position[0]),
                             float(position[1]),
                             float(position[2])],
                "rotation_flame_euler": [float(rotation[0]),
                                         float(rotation[1]),
                                         float(rotation[2])],
                "focal_mm": float(focal_mm),
            }
        ],
    }

    if custom_properties:
        payload["custom_properties"] = dict(custom_properties)
    if frame_rate:
        payload["frame_rate"] = str(frame_rate)
    # NOTE: ``is not None`` semantics, NOT truthy — see kwarg docstring.
    # ``1.0`` is a valid ladder stop the artist may have explicitly chosen,
    # and dropping it would silently fall back to bake's CLI default. The
    # bake-side validator catches ``0.0`` (not on the ladder) loudly.
    if flame_to_blender_scale is not None:
        payload["flame_to_blender_scale"] = float(flame_to_blender_scale)

    out_abs = os.path.abspath(out_path)
    os.makedirs(os.path.dirname(out_abs) or ".", exist_ok=True)
    with open(out_abs, "w") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")
    return out_abs


# =============================================================================
# Import: JSON -> Flame cam_node
# =============================================================================


def import_json_to_flame_camera(
    in_path: str,
    cam_node,
    *,
    frame_index: int = 0,
) -> dict:
    """Load a v5 camera JSON and apply one frame's values to a Flame cam_node.

    Mirrors the hook's apply pattern: sets position + rotation + fov
    directly on the cam_node (fov, not focal — see the hook's note about
    Flame's default film back being 16mm Super 16).

    Args:
        in_path: JSON path produced by export_flame_camera_to_json, by
            extract_camera.py, or by any source matching the v5 contract.
        cam_node: target PyAction camera node.
        frame_index: which entry in ``frames[]`` to apply. Defaults to 0
            (first frame). If the JSON has multiple frames and you want a
            specific frame NUMBER, resolve it to an index yourself before
            calling.

    Returns:
        Dict of the values actually applied, for tracing / confirmation.
    """
    with open(in_path) as f:
        data = json.load(f)

    frames = data.get("frames") or []
    if not frames:
        raise ValueError(f"{in_path}: no frames in JSON")
    if not (0 <= frame_index < len(frames)):
        raise IndexError(
            f"frame_index {frame_index} out of range for {len(frames)} frames")

    kf = frames[frame_index]
    film_back_mm = float(data["film_back_mm"])
    focal_mm = float(kf["focal_mm"])
    vfov_deg = vfov_deg_from_focal(focal_mm, film_back_mm)

    pos = kf["position"]
    rot = kf["rotation_flame_euler"]

    cam_node.position.set_value((float(pos[0]), float(pos[1]), float(pos[2])))
    cam_node.rotation.set_value((float(rot[0]), float(rot[1]), float(rot[2])))
    cam_node.fov.set_value(float(vfov_deg))

    return {
        "source": in_path,
        "frame": int(kf["frame"]),
        "frame_index": frame_index,
        "position": list(pos),
        "rotation": list(rot),
        "fov_deg": vfov_deg,
        "focal_mm": focal_mm,
        "film_back_mm": film_back_mm,
    }
