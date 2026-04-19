"""
bake_camera.py — Flame camera JSON -> Blender .blend

Runs *inside* Blender via the CLI:

    blender --background --python tools/blender/bake_camera.py -- \\
        --in  path/to/cam.json \\
        --out path/to/output.blend \\
        [--camera-name NAME]        # default "Camera"
        [--scale S]                 # divisor, default 1.0 (no rescale)
        [--create-if-missing]       # make a new camera if NAME not found

JSON contract (see PASSOFF.md v5 "Data contract"):

    {
      "width":         <int>,
      "height":        <int>,
      "film_back_mm":  <float>,
      "frames": [
        {"frame": <int>,
         "position":              [x, y, z],
         "rotation_flame_euler":  [rx_deg, ry_deg, rz_deg],
         "focal_mm":              <float>},
        ...
      ]
    }

Conventions:

  - Flame world is Y-up, 1 unit ≈ 1 image pixel. Blender world is Z-up.
    Bridge is a single left-multiplication by Rx(+90°) per frame. Both
    cameras look down local -Z (OpenGL), so no camera-local correction
    is needed.

  - Flame's rotation composes as R = Rz(rz) · Ry(-ry) · Rx(-rx). This is
    the ZYX-with-X,Y-negated order verified in memory/flame_rotation_convention.md
    and tested by tests/test_hook_parity.py + tests/test_blender_roundtrip.py.

  - --scale is a divisor applied to POSITION ONLY. `--scale 1000` means
    "1 Blender unit represents 1000 Flame pixels" for placement purposes.
    Lens and sensor_width stay in their native mm — FOV depends only on
    their ratio, and Blender clamps both to min=1.0mm, so scaling them
    in lockstep breaks small values silently. extract_camera.py reads
    the stamped metadata and multiplies position back up for lossless
    round-trip.

  - We keyframe rotation_quaternion (not rotation_euler) so animated bakes
    are gimbal-safe. User can switch rotation_mode to 'XYZ' in Blender if
    they prefer Euler controls for editing.

The math here intentionally duplicates forge_core.math.rotations.
flame_euler_to_cam_rot using mathutils instead of numpy so this file
can ship standalone to anyone with Blender — no forge_core install
required. The round-trip test in tests/test_blender_roundtrip.py is
what guards against the two implementations drifting.
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
        prog="bake_camera.py",
        description="Bake a Flame-exported camera JSON into a Blender .blend.")
    ap.add_argument("--in", dest="in_path", required=True,
                    help="input JSON path (Flame camera export)")
    ap.add_argument("--out", dest="out_path", required=True,
                    help="output .blend path")
    ap.add_argument("--camera-name", default="Camera",
                    help="target camera object name (default: Camera)")
    ap.add_argument("--scale", type=float, default=1.0,
                    help="divide POSITION by this value (default 1.0). "
                         "Use >1 to shrink the scene for usable Blender "
                         "viewport navigation. Lens and sensor_width are "
                         "not scaled — Blender clamps them to min=1.0mm "
                         "and FOV depends only on their ratio.")
    ap.add_argument("--create-if-missing", action="store_true",
                    help="create the camera if --camera-name doesn't exist")
    return ap.parse_args(our_argv)


# =============================================================================
# Math — parallel implementation of forge_core.math.rotations.flame_euler_to_cam_rot
# =============================================================================


def _flame_euler_to_rot_matrix(rx_deg: float, ry_deg: float, rz_deg: float) -> Matrix:
    """Compose Flame's R = Rz(rz) · Ry(-ry) · Rx(-rx) as a 4x4 mathutils.Matrix.

    Must stay numerically identical to forge_core.math.rotations
    .flame_euler_to_cam_rot. If you touch one, touch both, and run
    tests/test_blender_roundtrip.py."""
    rx, ry, rz = (math.radians(a) for a in (rx_deg, ry_deg, rz_deg))
    return (Matrix.Rotation(rz,  4, 'Z')
            @ Matrix.Rotation(-ry, 4, 'Y')
            @ Matrix.Rotation(-rx, 4, 'X'))


# Flame world (Y-up) -> Blender world (Z-up). +90° about X, applied once
# per frame as a pure left-multiplication. See PASSOFF.md §"Axis map".
_R_Y2Z = Matrix.Rotation(math.radians(90), 4, 'X')


# =============================================================================
# Scene / camera setup
# =============================================================================


def _get_or_create_camera(name: str, create_if_missing: bool) -> bpy.types.Object:
    """Look up the named camera object, or create a fresh one."""
    obj = bpy.data.objects.get(name)
    if obj is not None:
        if obj.type != 'CAMERA':
            raise SystemExit(
                f"object {name!r} exists but is a {obj.type}, not a CAMERA")
        return obj
    if not create_if_missing:
        raise SystemExit(
            f"no camera named {name!r} in .blend; "
            f"pass --create-if-missing to spawn one")
    cam_data = bpy.data.cameras.new(name)
    obj = bpy.data.objects.new(name, cam_data)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def _stamp_metadata(cam_data: bpy.types.Camera, scale: float, source_path: str) -> None:
    """Write round-trip metadata onto the camera's data-block so extract
    can undo the scale and provenance-check the source."""
    cam_data["forge_bake_version"] = 1
    cam_data["forge_bake_source"] = "flame"
    cam_data["forge_bake_scale"] = scale
    cam_data["forge_bake_input_path"] = os.path.abspath(source_path)


# =============================================================================
# Bake
# =============================================================================


def _bake(args: argparse.Namespace) -> None:
    with open(args.in_path) as f:
        data = json.load(f)

    frames = data.get("frames") or []
    if not frames:
        raise SystemExit(f"{args.in_path}: no frames in JSON")

    scale = args.scale
    if scale <= 0:
        raise SystemExit(f"--scale must be positive, got {scale}")

    cam = _get_or_create_camera(args.camera_name, args.create_if_missing)
    cam.rotation_mode = 'QUATERNION'
    cam.data.lens_unit = 'MILLIMETERS'
    # Our JSON contract treats film_back_mm as the VERTICAL sensor dimension
    # (Flame's cam.fov is vertical FOV). Blender's default sensor_fit='AUTO'
    # treats sensor_width as horizontal for wide-aspect plates, which would
    # silently misrender the FOV. Pin sensor_fit='VERTICAL' so Blender's
    # FOV calc uses sensor_height directly, matching our math.
    cam.data.sensor_fit = 'VERTICAL'
    cam.data.sensor_height = float(data["film_back_mm"])

    for kf in frames:
        frame = int(kf["frame"])
        rot_mat = _flame_euler_to_rot_matrix(*kf["rotation_flame_euler"])
        pos_scaled = [p / scale for p in kf["position"]]
        m_flame = Matrix.Translation(pos_scaled) @ rot_mat
        cam.matrix_world = _R_Y2Z @ m_flame
        cam.data.lens = float(kf["focal_mm"])

        cam.keyframe_insert("location", frame=frame)
        cam.keyframe_insert("rotation_quaternion", frame=frame)
        cam.data.keyframe_insert("lens", frame=frame)

    # Scene setup so the .blend opens render-ready.
    scene = bpy.context.scene
    scene.frame_start = min(int(kf["frame"]) for kf in frames)
    scene.frame_end = max(int(kf["frame"]) for kf in frames)
    scene.frame_current = scene.frame_start
    scene.camera = cam
    scene.render.resolution_x = int(data["width"])
    scene.render.resolution_y = int(data["height"])

    _stamp_metadata(cam.data, scale, args.in_path)

    # Ensure the output directory exists before bpy chokes on it.
    out_abs = os.path.abspath(args.out_path)
    os.makedirs(os.path.dirname(out_abs) or ".", exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=out_abs)

    print(
        f"bake_camera: {len(frames)} frame(s) baked "
        f"[{scene.frame_start}..{scene.frame_end}] "
        f"camera={cam.name!r} scale={scale} "
        f"resolution={scene.render.resolution_x}x{scene.render.resolution_y} "
        f"-> {out_abs}"
    )


def main() -> None:
    args = _parse_args()
    _bake(args)


if __name__ == "__main__":
    main()
