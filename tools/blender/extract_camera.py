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
import os
import sys
from typing import Optional, Sequence

import bpy

# D-05: share math with the Blender "Send to Flame" addon.
# forge_sender/ is a sibling directory shipped alongside this script.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "forge_sender"))

from flame_math import (  # noqa: E402
    _rot3_to_flame_euler_deg,
    _R_Z2Y,
    _camera_keyframe_set,
    _resolve_scale,
    build_v5_payload,
)


# =============================================================================
# CLI
# =============================================================================


def _parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Parse Blender-subprocess argv.

    Blender prepends its own flags to sys.argv; ours are after ``--``.
    When ``argv`` is None, read from sys.argv (runtime path). When
    provided, use that sequence directly — lets tests exercise the
    argparse surface without mutating sys.argv (see
    tests/test_extract_camera.py::TestArgparseSurface).
    """
    if argv is None:
        argv = sys.argv
    if "--" in argv:
        our_argv = list(argv[argv.index("--") + 1:])
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
# Extract
# =============================================================================


def _extract(args: argparse.Namespace) -> None:
    cam = bpy.data.objects.get(args.camera_name)
    if cam is None:
        raise SystemExit(f"no camera named {args.camera_name!r} in .blend")
    if cam.type != 'CAMERA':
        raise SystemExit(
            f"object {args.camera_name!r} is a {cam.type}, not a CAMERA")

    # D-05: payload math lives in forge_sender/flame_math.py so the
    # "Send to Flame" addon and this CLI script share one source of truth.
    out = build_v5_payload(cam, scale_override=args.scale)

    out_abs = os.path.abspath(args.out_path)
    os.makedirs(os.path.dirname(out_abs) or ".", exist_ok=True)
    with open(out_abs, "w") as f:
        json.dump(out, f, indent=2)
        f.write("\n")

    frames = out["frames"]
    frame_span = (f"[{frames[0]['frame']}..{frames[-1]['frame']}]"
                  if frames else "[no frames]")
    print(
        f"extract_camera: {len(frames)} frame(s) extracted "
        f"{frame_span} "
        f"camera={cam.name!r} scale={args.scale} "
        f"resolution={out['width']}x{out['height']} "
        f"-> {out_abs}"
    )


def main() -> None:
    args = _parse_args()
    _extract(args)


if __name__ == "__main__":
    main()
