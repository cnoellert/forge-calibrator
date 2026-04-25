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

  - Flame's aim-rig rotation composes as R = Rz(-rz) · Ry(-ry) · Rx(-rx).
    This is the Z·Y·X-with-all-three-negated order verified 2026-04-25
    against Camera1 (forge-bridge probe + viewport manual-match; see
    memory/flame_rotation_convention.md and Phase 04.3 CONTEXT.md /
    04.3-SPIKE.md). Note: the Free-rig solve path on the Flame side
    still uses the older Rz(rz)·Ry(-ry)·Rx(-rx) (Z·Y·X with only
    rx/ry negated) convention via forge_core.math.rotations
    .flame_euler_to_cam_rot — the two conventions coexist
    intentionally; aim-rig (this script's consumer) uses the
    XYZ-signflip pair from Phase 04.3.

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
flame_euler_xyz_to_cam_rot using mathutils instead of numpy so this
file can ship standalone to anyone with Blender — no forge_core
install required. tests/test_blender_roundtrip.py guards the
Free-rig pipeline (which still rides on the older Z·Y·X with only
rx/ry negated convention via flame_euler_to_cam_rot); the aim-rig
convention parity is guarded by tests/test_fbx_ascii.py
::TestAimRigFixture (parser side) and tests/test_rotations.py
::TestComputeFlameEulerXyz (forge_core side).
"""

import argparse
import json
import math
import os
import sys
from typing import Optional

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
# Math — parallel implementation of forge_core.math.rotations.flame_euler_xyz_to_cam_rot
# =============================================================================


def _flame_euler_to_rot_matrix(rx_deg: float, ry_deg: float, rz_deg: float) -> Matrix:
    """Compose Flame's R = Rz(-rz) · Ry(-ry) · Rx(-rx) as a 4x4 mathutils.Matrix.

    Must stay numerically identical to forge_core.math.rotations
    .flame_euler_xyz_to_cam_rot. If you touch one, touch both, and run
    tests/test_blender_roundtrip.py.

    Phase 04.3: convention swapped from Rz(rz)·Ry(-ry)·Rx(-rx) (used by
    `flame_euler_to_cam_rot` on the Free-rig solve path) to
    Rz(-rz)·Ry(-ry)·Rx(-rx) — the same Z·Y·X matrix-product order, with
    rz now ALSO negated (in addition to the existing rx, ry negations).
    Coupled with the L167 sign flip in forge_core.math.rotations
    .rotation_matrix_from_look_at; both must change together. Verified
    2026-04-25 via forge-bridge probe + viewport manual-match on
    Camera1 + empirical sign/order search; closes the Phase 04.2
    ~0.087° ry residual on the aim-rig fixture."""
    rx, ry, rz = (math.radians(a) for a in (rx_deg, ry_deg, rz_deg))
    return (Matrix.Rotation(-rz, 4, 'Z')
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


_RESERVED_STAMP_KEYS = frozenset({
    "forge_bake_version",
    "forge_bake_source",
    "forge_bake_scale",
    "forge_bake_input_path",
    "forge_bake_frame_rate",   # Phase 4.1 D-11 (always-stamp invariant)
})

# Flame project fps labels — mirrors forge_sender/__init__.py _FLAME_FPS_LABELS.
# Used by _closest_flame_fps_label and _stamp_metadata's D-14 fallback.
# Values are (label_string, numeric_fps) pairs. Kept in sync by inspection;
# if forge_sender adds a new rate, add it here too.
_FLAME_FPS_LABELS = (
    ("23.976 fps", 23.976),
    ("24 fps", 24.0),
    ("25 fps", 25.0),
    ("29.97 fps", 29.97),
    ("30 fps", 30.0),
    ("48 fps", 48.0),
    ("50 fps", 50.0),
    ("59.94 fps", 59.94),
    ("60 fps", 60.0),
)


def _closest_flame_fps_label(fps: float) -> str:
    """Map a numeric fps to the nearest _FLAME_FPS_LABELS label string.

    Tolerance: abs(fps - label_numeric) < 0.1. If no match within tolerance,
    returns '<fps> fps' and the caller should emit an extra stderr line noting
    the miss — this hits forge_sender/__init__.py::_resolve_frame_rate's
    ladder step 1 fall-through to step 2 cleanly (step 2 re-maps from numeric).

    Args:
        fps: numeric frames-per-second value (e.g. 24.0, 23.976).

    Returns:
        A label string from _FLAME_FPS_LABELS or '<fps> fps' on no-match.
    """
    for label, numeric in _FLAME_FPS_LABELS:
        if abs(fps - numeric) < 0.1:
            return label
    # No match within tolerance — stamp a raw label and warn at call site.
    return f"{fps} fps"


def _stamp_metadata(
    cam_data: bpy.types.Camera,
    scale: float,
    source_path: str,
    custom_properties: Optional[dict] = None,
    frame_rate_label: Optional[str] = None,
) -> None:
    """Write round-trip metadata onto the camera's data-block so extract
    can undo the scale and provenance-check the source.

    Args:
        cam_data: the bpy Camera data-block (cam.data, NOT the object).
            Custom properties are stored on the ID-block so they survive
            .blend save/load and are readable by extract_camera.py.
        scale: the position divisor used during bake; extract multiplies
            this back up for a lossless round-trip.
        source_path: the input JSON path; stamped as provenance.
        custom_properties: optional caller-supplied dict of extra
            metadata (e.g. Flame Action name + camera name for the
            Blender-side "Send to Flame" addon to read). Values must
            be bpy-property-compatible (str / int / float per the v5
            JSON contract). Applied as-is to cam_data[key] = value.

            Reserved keys in ``_RESERVED_STAMP_KEYS`` (the round-trip
            stamps this function writes) cannot be overridden here:
            any attempt to set them via ``custom_properties`` is
            skipped with a stderr warning so a buggy or tampered JSON
            cannot clobber ``forge_bake_scale`` (which would produce
            a silently-miscalibrated camera on extract) or
            ``forge_bake_source`` (used for provenance gating by the
            Blender-side "Send to Flame" addon).
        frame_rate_label: Flame-project fps label to stamp as
            ``forge_bake_frame_rate`` (e.g. "24 fps", "23.976 fps").
            This value is the authoritative source per D-12; the
            reserved-key guard ensures callers cannot override it via
            ``custom_properties``. When ``None``, the D-14 fallback
            path fires: derives a label from ``bpy.context.scene.render.fps
            / fps_base`` and prints a stderr warning — never silent.
            See ``forge_sender/__init__.py::_resolve_frame_rate`` step 1
            for the downstream consumer of this stamp.
    """
    # Apply caller properties first, then overwrite with reserved stamps so
    # the round-trip scale/provenance invariants cannot be clobbered even
    # if the caller forgets the reserved-key guard. The explicit reject
    # below is the loud layer; the write-last below it is the silent
    # belt-and-braces layer.
    if custom_properties:
        for key, value in custom_properties.items():
            if key in _RESERVED_STAMP_KEYS:
                print(
                    f"bake_camera: ignoring reserved custom_properties "
                    f"key {key!r} (would clobber round-trip stamp)",
                    file=sys.stderr,
                )
                continue
            cam_data[key] = value
    cam_data["forge_bake_version"] = 1
    cam_data["forge_bake_source"] = "flame"
    cam_data["forge_bake_scale"] = scale
    cam_data["forge_bake_input_path"] = os.path.abspath(source_path)

    # D-11: always stamp forge_bake_frame_rate — makes the .blend self-describing
    # for debugging and feeds forge_sender/__init__.py::_resolve_frame_rate step 1.
    # D-14 fallback: if frame_rate_label is None (Flame-side propagation failed),
    # derive from Blender scene fps with a loud stderr warning — never silent.
    if frame_rate_label is not None:
        cam_data["forge_bake_frame_rate"] = str(frame_rate_label)
    else:
        scene_fps = (bpy.context.scene.render.fps
                     / bpy.context.scene.render.fps_base)
        derived_label = _closest_flame_fps_label(scene_fps)
        print(
            "forge_bake_frame_rate: falling back to Blender scene fps "
            f"({scene_fps}) — Flame-side propagation failed; stamped "
            f"{derived_label!r}",
            file=sys.stderr,
        )
        cam_data["forge_bake_frame_rate"] = derived_label


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

    # D-13 preferred source: top-level `frame_rate` field on the v5 JSON
    # (self-describing, set by the Flame hook from the Flame project fps).
    # D-14 fallback: if absent, _stamp_metadata derives from Blender scene fps
    # and emits a loud stderr warning — never silently stamp 24.0.
    json_frame_rate = data.get("frame_rate")
    frame_rate_label = str(json_frame_rate) if json_frame_rate else None

    _stamp_metadata(cam.data, scale, args.in_path, data.get("custom_properties"),
                    frame_rate_label=frame_rate_label)

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
