"""
Parser for fSpy project files (.fspy).

Binary format:
  - 4 bytes: magic "fspy"
  - 4 bytes: uint32 LE version
  - 4 bytes: uint32 LE state JSON size
  - 4 bytes: uint32 LE image data size
  - N bytes: JSON state (camera parameters + control points)
  - M bytes: image data (PNG/JPEG)

The JSON state contains the solved camera result and control point positions,
which can be used to cross-validate our Python solver against the original app.
"""

import struct
import json
from pathlib import Path
from typing import Optional, Tuple


FSPY_MAGIC = b"fspy"


def read_fspy(path: str) -> Tuple[dict, bytes]:
    """Read an fSpy project file.

    Args:
        path: Path to the .fspy file

    Returns:
        Tuple of (state_dict, image_bytes)

    Raises:
        ValueError: If the file is not a valid fSpy project
    """
    path = Path(path)

    with open(path, "rb") as f:
        magic = f.read(4)
        if magic != FSPY_MAGIC:
            raise ValueError(
                f"Not an fSpy file: expected magic {FSPY_MAGIC!r}, got {magic!r}"
            )

        version = struct.unpack("<I", f.read(4))[0]
        state_size = struct.unpack("<I", f.read(4))[0]
        image_size = struct.unpack("<I", f.read(4))[0]

        state_json = f.read(state_size)
        image_data = f.read(image_size)

    state = json.loads(state_json)
    state["_fspy_version"] = version

    return state, image_data


def extract_control_points(state: dict) -> Optional[dict]:
    """Extract control point positions from fSpy state.

    Returns a dict with vanishing point line endpoints in relative coords
    (as stored by fSpy), plus the solved camera parameters for comparison.

    Args:
        state: Parsed fSpy state dict

    Returns:
        Dict with control points and camera parameters, or None if not present.
    """
    cp = state.get("controlPointsStateBase")
    if cp is None:
        return None

    camera = state.get("cameraParameters")

    return {
        "vanishing_points": cp.get("vanishingPoints", []),
        "principal_point": cp.get("principalPoint"),
        "origin": cp.get("origin"),
        "reference_distance_anchor": cp.get("referenceDistanceAnchor"),
        "camera_parameters": camera,
    }


def extract_image(state: dict, image_data: bytes, output_path: str) -> None:
    """Save the embedded image from an fSpy project to disk.

    Args:
        state: Parsed fSpy state dict (unused, reserved for format info)
        image_data: Raw image bytes from the fSpy file
        output_path: Where to write the image file
    """
    with open(output_path, "wb") as f:
        f.write(image_data)
