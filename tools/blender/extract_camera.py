"""
extract_camera.py — Blender .blend -> Flame camera JSON

Runs *inside* Blender via the CLI:

    blender --background path/to/input.blend \\
        --python tools/blender/extract_camera.py -- \\
        --out path/to/cam.json \\
        [--camera-name NAME]        # default "Camera"
        [--scale S]                 # override the bake-stamped scale

The inverse of bake_camera.py. Reads keyframed camera animation from a
.blend, applies the Z-up -> Y-up axis swap, decomposes each frame's
world matrix into Flame's Euler convention, and writes the v5 JSON
contract (see PASSOFF.md v5 "Data contract").

Scale handling:

  bake_camera.py stamps `forge_bake_scale` as a custom property on the
  camera's data-block. extract_camera.py reads that value and multiplies
  POSITION back up by it, undoing the bake-time division. Lens and
  sensor_width are not scaled — bake left them in their native mm for
  the reasons documented there.

  If the .blend has no stamped scale (e.g. it wasn't produced by our
  bake), extract defaults to 1.0 and prints a warning. --scale on the
  CLI overrides both stamped and default.

Math mirrors forge_core.math.rotations.compute_flame_euler_zyx using
mathutils instead of numpy, for the same ship-standalone reasons as
bake. tests/test_blender_roundtrip.py validates the numpy reference;
this file's parallel implementation is guarded by a round-trip sanity
test (run bake then extract against sample_camera.json; diff JSONs).

Round-trip self-test from the repo root:

    blender --background --python tools/blender/bake_camera.py -- \\
      --in tools/blender/sample_camera.json \\
      --out /tmp/forge_rt.blend \\
      --scale 1000 --create-if-missing

    blender --background /tmp/forge_rt.blend \\
      --python tools/blender/extract_camera.py -- \\
      --out /tmp/forge_rt.json

    diff tools/blender/sample_camera.json /tmp/forge_rt.json
"""

import argparse
import json
import math
import os
import sys

import bpy
from mathutils import Matrix


# =============================================================================
# CLI
# =============================================================================


def _parse_args() -> argparse.Namespace:
    """Blender prepends its own flags to sys.argv; ours are after '--'."""
    if "--" in sys.argv:
        our_argv = sys.argv[sys.argv.index("--") + 1:]
    else:
        our_argv = []
    ap = argparse.ArgumentParser(
        prog="extract_camera.py",
        description="Extract a keyframed Blender camera as Flame JSON.")
    ap.add_argument("--out", dest="out_path", required=True,
                    help="output JSON path")
    ap.add_argument("--camera-name", default="Camera",
                    help="source camera object name (default: Camera)")
    ap.add_argument("--scale", type=float, default=None,
                    help="override the bake-stamped scale divisor. Usually "
                         "omitted — extract reads forge_bake_scale from the "
                         ".blend automatically.")
    return ap.parse_args(our_argv)


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
# Extract
# =============================================================================


def _resolve_scale(cam: bpy.types.Object, cli_override) -> float:
    """CLI override wins; otherwise read the stamped metadata; otherwise 1.0."""
    if cli_override is not None:
        return float(cli_override)
    stamped = cam.data.get("forge_bake_scale")
    if stamped is None:
        print("extract_camera: warning — no forge_bake_scale metadata on "
              f"{cam.name!r}, defaulting to 1.0. Pass --scale if this .blend "
              "came from a non-default bake.", file=sys.stderr)
        return 1.0
    return float(stamped)


def _extract(args: argparse.Namespace) -> None:
    scene = bpy.context.scene
    cam = bpy.data.objects.get(args.camera_name)
    if cam is None:
        raise SystemExit(f"no camera named {args.camera_name!r} in .blend")
    if cam.type != 'CAMERA':
        raise SystemExit(
            f"object {args.camera_name!r} is a {cam.type}, not a CAMERA")

    scale = _resolve_scale(cam, args.scale)
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

    out = {
        "width":        int(scene.render.resolution_x),
        "height":       int(scene.render.resolution_y),
        # film_back_mm is the VERTICAL sensor dimension in our contract;
        # bake writes it to sensor_height with sensor_fit='VERTICAL'. Read
        # sensor_height here to stay consistent (sensor_width would be
        # Blender's auto-derived horizontal value, a different number).
        "film_back_mm": float(cam.data.sensor_height),
        "frames":       frames_out,
    }

    out_abs = os.path.abspath(args.out_path)
    os.makedirs(os.path.dirname(out_abs) or ".", exist_ok=True)
    with open(out_abs, "w") as f:
        json.dump(out, f, indent=2)
        f.write("\n")

    print(
        f"extract_camera: {len(frames_out)} frame(s) extracted "
        f"[{frames_to_read[0]}..{frames_to_read[-1]}] "
        f"camera={cam.name!r} scale={scale} "
        f"resolution={out['width']}x{out['height']} "
        f"-> {out_abs}"
    )


def main() -> None:
    args = _parse_args()
    _extract(args)


if __name__ == "__main__":
    main()
