"""
Wiretap adapter — Flame-only. Reads one frame of a clip via the wiretap_rw_frame
CLI and probes its tagged colour space via the Wiretap Python SDK.

Why here and not in forge_core: trafFIK and other downstream tools won't run
inside Flame, so they can't talk to Wiretap anyway. They'll read media off
disk with cv2 / OpenImageIO / their renderer of choice and feed the resulting
bytes straight into ``forge_core.image.buffer``. This module is the only glue
that needs to know the Wiretap CLI exists.

Paths go through /current/ symlinks that Autodesk maintains per install, so
the same code keeps working across Flame version bumps.

Public functions:
    get_clip_colour_space(clip)     — str ("LogC4 / ARRI Wide Gamut 4" etc.) or None
    extract_frame_bytes(clip, frame_num) — (raw_bytes, width, height, bit_depth) or None
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from typing import Optional, Tuple

# CLI lives at /opt/Autodesk/wiretap/tools/current/wiretap_rw_frame. The
# /current/ symlink is maintained by Autodesk across upgrades, so this
# path is version-safe.
_WIRETAP_RW_FRAME = "/opt/Autodesk/wiretap/tools/current/wiretap_rw_frame"
_WIRETAP_SDK_PATH = "/opt/Autodesk/wiretap/tools/current/python"


# =============================================================================
# Colour-space probe
# =============================================================================


def get_clip_colour_space(clip) -> Optional[str]:
    """Return the Wiretap-tagged colour space string for a PyClipNode or PyClip.

    Examples of what comes back:
        "LogC4 / ARRI Wide Gamut 4"
        "LogC3 (EI800) / ARRI Wide Gamut 3"
        "Rec.709 video"
        "ACEScg"
        None  — clip has no wiretap node id or the SDK import failed

    Cheap to call (opens its own short-lived Wiretap session), but does
    cost a round-trip to the Wiretap server so don't call it in a hot loop.
    Used at clip-open time to auto-select the matching OCIO source in the
    UI dropdown."""
    try:
        py_clip = clip.clip if hasattr(clip, "clip") else clip
        node_id = py_clip.get_wiretap_node_id()
    except Exception:
        return None
    if not node_id:
        return None

    if _WIRETAP_SDK_PATH not in sys.path:
        sys.path.insert(0, _WIRETAP_SDK_PATH)
    try:
        from adsk.libwiretapPythonClientAPI import (
            WireTapClientInit, WireTapClientUninit,
            WireTapServerHandle, WireTapNodeHandle, WireTapClipFormat,
        )
    except Exception as e:
        print("Wiretap SDK import failed:", e)
        return None

    WireTapClientInit()
    try:
        server = WireTapServerHandle("127.0.0.1:IFFFS")
        nh = WireTapNodeHandle(server, node_id)
        fmt = WireTapClipFormat()
        if not nh.getClipFormat(fmt):
            return None
        return fmt.colourSpace() or None
    except Exception as e:
        print("Wiretap colour-space probe failed:", e)
        return None
    finally:
        WireTapClientUninit()


# =============================================================================
# Single-frame extract via CLI
# =============================================================================


def extract_frame_bytes(
    clip, target_frame: Optional[int] = None,
) -> Optional[Tuple[bytes, int, int, int]]:
    """Extract one frame of a clip and return (raw_bytes, w, h, bit_depth).

    Calls wiretap_rw_frame with a temp output path, reads the file Flame
    writes, and returns its full contents as bytes. Whether those bytes
    are a standard image container (PNG/JPEG/TIFF/EXR/DPX for soft-imported
    stills) or a raw pixel buffer (for transcoded / proxy-rendered sources)
    is up to the caller to sniff — see forge_core.image.buffer.

    target_frame is in clip-source frame numbering (e.g. 1001 for a clip
    whose start_frame is 1001). Clamped to the clip's [start, start+duration-1]
    range. When None, defaults to the clip's first frame.

    Returns None if:
      - wiretap_rw_frame CLI is missing
      - the clip has no wiretap node id
      - the CLI errors or times out
      - no output file was written

    Width, height, and bit_depth come from Flame's ClipResolution, so
    callers can pass them straight into decode_raw_rgb_buffer without
    parsing the output format."""
    if not os.path.isfile(_WIRETAP_RW_FRAME):
        print("wiretap_rw_frame not found:", _WIRETAP_RW_FRAME)
        return None

    try:
        py_clip = clip.clip
        node_id = py_clip.get_wiretap_node_id()
    except Exception as e:
        print("get_wiretap_node_id failed:", e)
        return None
    if not node_id:
        print("Clip has empty wiretap node id — is it in the Media Panel?")
        return None

    # Frame range + target resolve. Source-frame numbering (not 0-based).
    try:
        duration = int(clip.duration.get_value())
        start_frame = int(py_clip.start_frame)
    except Exception:
        duration, start_frame = 1, 1
    if target_frame is None:
        target_frame = start_frame
    target_frame = max(start_frame, min(start_frame + duration - 1, int(target_frame)))
    frame_index = target_frame - start_frame  # CLI wants 0-based

    try:
        res = clip.resolution.get_value()
        w, h, bit_depth = int(res.width), int(res.height), int(res.bit_depth)
    except Exception as e:
        print("resolution read failed:", e)
        return None

    with tempfile.TemporaryDirectory(prefix="camera_match_wt_") as tmp:
        out_base = os.path.join(tmp, "frame")
        cmd = [
            _WIRETAP_RW_FRAME,
            "-n", node_id,
            "-i", str(frame_index),
            "-f", out_base,
        ]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        except subprocess.TimeoutExpired:
            print("wiretap_rw_frame timed out")
            return None
        except Exception as e:
            print("wiretap_rw_frame exec error:", e)
            return None

        files = [f for f in os.listdir(tmp) if f.startswith("frame")]
        if not files:
            print(
                "wiretap_rw_frame wrote no output. stdout:", r.stdout.strip(),
                "stderr:", r.stderr.strip(),
            )
            return None
        with open(os.path.join(tmp, files[0]), "rb") as f:
            raw = f.read()

    return raw, w, h, bit_depth
