"""
forge_sender/flame_math.py — shared Blender-side Flame camera math.

Why this module exists: the "Send to Flame" addon and the legacy
extract_camera.py CLI script both need the same Euler decomposition,
axis-swap matrix, keyframe walker, and v5-JSON payload builder.
Putting them here gives us one copy to touch when the math needs a
fix (memory/flame_rotation_convention.md is the spec).

Scope boundaries:
  - Math only. No bpy Panel / Operator / UI surface.
  - No HTTP / JSON I/O. Callers serialize via json.dumps / json.dump.
  - Pure bpy + mathutils imports; safe to import from either the
    addon or from a Blender subprocess driving extract_camera.py.

Round-trip parity: the Euler decomposition here MUST stay
numerically identical to
forge_core.math.rotations.compute_flame_euler_zyx. If you change one,
change both and run tests/test_blender_roundtrip.py plus
tests/test_forge_sender_flame_math.py.

Scale handling:

  bake_camera.py stamps ``forge_bake_scale`` as a custom property on
  the camera's data-block. ``_resolve_scale`` reads that value and
  ``build_v5_payload`` multiplies POSITION back up by it, undoing the
  bake-time division. Lens and sensor_height are not scaled — bake
  left them in their native mm for the reasons documented there.
"""
from __future__ import annotations

import math
import sys
from typing import Optional

import bpy
from mathutils import Matrix


# =============================================================================
# Math — parallel implementation of
# forge_core.math.rotations.compute_flame_euler_zyx
# =============================================================================


def _rot3_to_flame_euler_deg(R) -> tuple:
    """Decompose a 3x3 cam-to-world rotation into Flame's Euler triple.

    Flame composes rotations as R = Rz(rz) · Ry(-ry) · Rx(-rx). This is
    the matching inverse decomposition. Must stay numerically identical
    to forge_core.math.rotations.compute_flame_euler_zyx — if you change
    one, change both and run tests/test_blender_roundtrip.py.

    Handles gimbal lock (ry ≈ ±90°) by pinning rx=0 and recovering rz
    from the remaining 2x2 block."""
    # mathutils 3x3 Matrix indexes as [row][col]. Keep aligned with numpy.
    cb = math.sqrt(R[0][0] ** 2 + R[1][0] ** 2)
    gimbal = cb <= 1e-6
    if not gimbal:
        rx = -math.atan2(R[2][1], R[2][2])
        ry = -math.asin(-R[2][0])
        rz =  math.atan2(R[1][0], R[0][0])
    else:
        rx = 0.0
        ry = -math.asin(-R[2][0])
        rz =  math.atan2(-R[0][1], R[1][1])
    return (math.degrees(rx), math.degrees(ry), math.degrees(rz))


# Blender world (Z-up) -> Flame world (Y-up). Inverse of the bake step.
# Transpose of Rx(+90°) is Rx(-90°).
_R_Z2Y = Matrix.Rotation(math.radians(90), 4, 'X').transposed()


# =============================================================================
# Keyframe discovery
# =============================================================================


def _camera_keyframe_set(cam: bpy.types.Object) -> list:
    """Return a sorted list of unique integer frame numbers on which the
    camera (object or its data) has any keyframe.

    Walks both the object-level action (location/rotation/scale) and the
    camera-data-level action (lens, sensor, etc.) because we keyframe
    both in bake_camera.py. Falls back to the scene's current frame if
    no animation data is present (single static bake)."""
    frames = set()

    def _drain(anim):
        if anim is None or anim.action is None:
            return
        for fcurve in anim.action.fcurves:
            for kp in fcurve.keyframe_points:
                frames.add(int(round(kp.co[0])))

    _drain(cam.animation_data)
    _drain(cam.data.animation_data)

    if not frames:
        frames.add(int(bpy.context.scene.frame_current))
    return sorted(frames)


# =============================================================================
# Scale resolution
# =============================================================================


def _resolve_scale(cam: bpy.types.Object, cli_override) -> float:
    """CLI override wins; otherwise read the stamped metadata; otherwise 1.0.

    extract_camera.py's ``--scale`` flag passes ``args.scale`` as the
    override. The addon operator passes ``None`` — it trusts the
    ``forge_bake_scale`` stamped by bake_camera.py. If the .blend has
    no stamped scale (e.g. it wasn't produced by our bake), this
    prints a stderr warning and defaults to 1.0; callers who care
    should surface a popup before reaching here (addon preflight)."""
    if cli_override is not None:
        return float(cli_override)
    stamped = cam.data.get("forge_bake_scale")
    if stamped is None:
        print("forge_sender/flame_math: warning — no forge_bake_scale "
              f"metadata on {cam.name!r}, defaulting to 1.0. Pass "
              "scale_override if this .blend came from a non-default bake.",
              file=sys.stderr)
        return 1.0
    return float(stamped)


# =============================================================================
# Public: build the v5 JSON dict for a camera
# =============================================================================


def build_v5_payload(cam, scale_override: Optional[float] = None) -> dict:
    """Return the v5 JSON dict for ``cam`` (a bpy camera Object).

    No JSON I/O — callers serialize with json.dumps / json.dump. Both
    the "Send to Flame" addon and ``extract_camera.py`` call this;
    the addon POSTs json.dumps(result) to forge-bridge, the CLI writes
    json.dump(result, file).

    Args:
        cam: bpy.types.Object (camera). Must have .animation_data,
            .data, and .matrix_world attributes. .data is a
            bpy.types.Camera with .lens, .sensor_height, and dict-like
            custom-property access.
        scale_override: if not None, bypasses the stamped
            forge_bake_scale lookup. extract_camera.py passes
            ``args.scale`` here (CLI --scale flag); the addon passes
            ``None`` (reads stamped metadata via _resolve_scale).

    Returns a dict with keys: ``width``, ``height``, ``film_back_mm``,
    ``frames``. Each frame in ``frames`` is a dict with
    ``frame``, ``position``, ``rotation_flame_euler``, ``focal_mm``.
    """
    scene = bpy.context.scene
    scale = _resolve_scale(cam, scale_override)
    frames_to_read = _camera_keyframe_set(cam)

    frames_out = []
    for frame in frames_to_read:
        scene.frame_set(frame)

        # cam.matrix_world is the Blender-frame world matrix for this frame.
        # Apply the inverse axis swap to get back to Flame's Y-up frame.
        m_flame = _R_Z2Y @ cam.matrix_world

        # Position: translation column, scaled back up.
        tx, ty, tz = m_flame.translation
        position = [tx * scale, ty * scale, tz * scale]

        # Rotation: upper-left 3x3, decomposed via Flame convention.
        R = m_flame.to_3x3()
        rx_deg, ry_deg, rz_deg = _rot3_to_flame_euler_deg(R)

        # Lens is stored in mm verbatim by bake — no scale inversion needed.
        focal_mm = float(cam.data.lens)

        frames_out.append({
            "frame": frame,
            "position": position,
            "rotation_flame_euler": [rx_deg, ry_deg, rz_deg],
            "focal_mm": focal_mm,
        })

    return {
        "width":        int(scene.render.resolution_x),
        "height":       int(scene.render.resolution_y),
        # film_back_mm is the VERTICAL sensor dimension in our contract;
        # bake writes it to sensor_height with sensor_fit='VERTICAL'. Read
        # sensor_height here to stay consistent (sensor_width would be
        # Blender's auto-derived horizontal value, a different number).
        "film_back_mm": float(cam.data.sensor_height),
        "frames":       frames_out,
    }
