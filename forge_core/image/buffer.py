"""
Image-buffer utilities — host-agnostic.

Three concerns, one module:

1. ``decode_image_container(raw_bytes)`` — magic-byte sniff for PNG/JPEG/TIFF/
   EXR/DPX, then cv2.imdecode. Returns uint8 RGB or None if the bytes don't
   start with any known container signature. Used when Wiretap (or any other
   source) hands back a standard image file for soft-imported stills.

2. ``decode_raw_rgb_buffer(raw_bytes, w, h, bit_depth, gbr_order=True,
   bottom_up=True)`` — strip trailing header, reshape to (h, w, 3), optionally
   flip vertically and swap channels. Defaults match Flame's Wiretap raw
   buffer quirks (bottom-up OpenGL orientation, GBR despite the rgb_float_le
   format tag). Any caller feeding a differently-quirked buffer can pass
   ``gbr_order=False`` or ``bottom_up=False``.

3. ``apply_ocio_or_passthrough(float_rgb, processor)`` — apply an OCIO CPU
   processor in place and quantise to uint8, or clip+quantise with no
   transform when ``processor is None``. Handles the float16/float32 cast
   that ``processor.applyRGB`` needs.

trafFIK and any non-Flame tool can import these directly. The only Flame-
facing binding lives in ``flame/wiretap.py`` which calls into these
functions after extracting bytes via the Wiretap CLI.
"""

from __future__ import annotations

from typing import Optional
import numpy as np


# =============================================================================
# Container decode (PNG/JPEG/TIFF/EXR/DPX → uint8 RGB)
# =============================================================================

_CONTAINER_MAGIC = [
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8",          "jpg"),
    (b"II*\x00",           "tiff-le"),
    (b"MM\x00*",           "tiff-be"),
    (b"\x76\x2f\x31\x01",  "exr"),
    (b"SDPX",              "dpx-be"),
    (b"XPDS",              "dpx-le"),
]


def sniff_container(raw_bytes: bytes) -> Optional[str]:
    """Return a short format tag if raw_bytes starts with a known image
    container signature, else None. Cheap magic-byte check only."""
    head = raw_bytes[:8]
    for magic, tag in _CONTAINER_MAGIC:
        if head.startswith(magic):
            return tag
    return None


def decode_image_container(raw_bytes: bytes) -> Optional[np.ndarray]:
    """Decode a standard image container to uint8 RGB.

    Returns None if:
      - the bytes don't start with a known magic signature, or
      - cv2.imdecode can't parse them.

    Handles grayscale (broadcast to 3 channels), RGBA (alpha dropped),
    uint16 (bit-shifted to uint8), and float formats (clipped+quantised).
    Always returns RGB, never BGR — callers don't have to care about cv2's
    channel convention."""
    if sniff_container(raw_bytes) is None:
        return None
    import cv2  # lazy: forge env only
    arr = np.frombuffer(raw_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_UNCHANGED)
    if img is None:
        return None
    if img.ndim == 2:
        img = np.stack([img, img, img], axis=-1)
    if img.shape[-1] == 4:
        img = img[..., :3]
    if img.dtype == np.uint16:
        img = (img // 257).astype(np.uint8)
    elif img.dtype in (np.float32, np.float64):
        img = (np.clip(img, 0.0, 1.0) * 255).astype(np.uint8)
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)


# =============================================================================
# Raw buffer decode (strip header, reshape, repair orientation / channel order)
# =============================================================================

_BIT_DEPTH_TO_DTYPE = {
    8:  np.uint8,
    # 16-bit Wiretap RGB is usually half-float in Flame's scene-referred
    # pipeline. If a specific clip turns out to be uint16, we'll see saturated-
    # or-inverted preview and revisit — Flame exposes bit_depth but not
    # "is this integer or float" directly on ClipFormat.
    16: np.float16,
    32: np.float32,
}


def decode_raw_rgb_buffer(
    raw_bytes: bytes,
    width: int,
    height: int,
    bit_depth: int,
    channels: int = 3,
    gbr_order: Optional[bool] = None,
    bottom_up: bool = True,
) -> Optional[np.ndarray]:
    """Decode a raw pixel buffer of known geometry into an ndarray.

    Strips any leading header by slicing the *tail* of raw_bytes so we don't
    have to parse it — Wiretap's header is small (~16 bytes) and variable,
    and the pixel payload is always at the end.

    Args:
        raw_bytes: Full buffer (header + payload).
        width, height: Expected pixel dimensions.
        bit_depth: 8/16/32 (maps to uint8/float16/float32).
        channels: Number of channels in the payload (default 3 = RGB).
        gbr_order: If True, swap channels from GBR to RGB. If None
            (default), auto-detect from bit_depth: 8-bit Wiretap dumps
            (transcoded MXF / proxy) are tagged ``rgb_float_le`` but
            empirically arrive in GBR order, so they need the swap.
            Float dumps (16-bit half / 32-bit float, typically EXR-
            sourced ACEScg plates) are correctly tagged AND laid out
            as RGB, so they must NOT be swapped — applying the swap on
            float buffers introduces the well-known magenta-on-greens
            cast that motivated this gating. Verified 2026-04-28 against
            an A005C008 ACEScg plate (4448×3096 float16) on portofino.
            Pass an explicit True/False to override (used by tests).
        bottom_up: If True, flip vertically. Default True matches Wiretap's
            OpenGL-convention (origin bottom-left) buffers.

    Returns:
        ndarray of shape (height, width, channels) in the native dtype. For
        uint8 this is display-ready; for float dtypes the caller typically
        applies an OCIO transform next (see apply_ocio_or_passthrough).
        Returns None if the buffer is too small or the bit_depth is unknown.
    """
    dtype = _BIT_DEPTH_TO_DTYPE.get(bit_depth)
    if dtype is None:
        return None
    if gbr_order is None:
        gbr_order = (bit_depth == 8)
    sample_size = np.dtype(dtype).itemsize
    expected = width * height * channels * sample_size
    if len(raw_bytes) < expected:
        return None

    payload = raw_bytes[-expected:]  # tail slice; header lengths vary
    arr = np.frombuffer(payload, dtype=dtype).reshape(height, width, channels)

    # Order of operations matters when both flags are set: flip first, then
    # channel swap. The flip is just a view stride reversal so it's free;
    # the fancy-indexing swap forces a copy that we then contiguous-ify so
    # Qt / OCIO get a tight buffer.
    if bottom_up:
        arr = arr[::-1]
    if gbr_order:
        # Swap GBR → RGB (equivalent to [2, 0, 1] in the last axis).
        arr = arr[..., [2, 0, 1]]
    if bottom_up or gbr_order:
        arr = np.ascontiguousarray(arr)
    return arr


# =============================================================================
# Tonemap: float RGB + optional OCIO processor → display-ready uint8 RGB
# =============================================================================


def apply_ocio_or_passthrough(
    float_rgb: np.ndarray, processor=None,
) -> np.ndarray:
    """Convert a float RGB buffer to display-ready uint8.

    If ``processor`` is supplied, calls ``processor.applyRGB(buffer)`` in
    place — the processor is an OCIO CPU processor (from
    ``OcioPipeline.get_processor(src_cs)``) that applies a
    DisplayViewTransform with RRT+ODT, giving soft highlight rolloff.

    If ``processor`` is None or the transform raises, falls back to
    clip-to-[0,1] passthrough. Either path returns uint8 RGB ready for
    Qt's Format_RGB888.

    The input is cast to float32 if needed (OCIO's ``applyRGB`` doesn't
    accept float16) and made contiguous.
    """
    a = np.ascontiguousarray(float_rgb.astype(np.float32, copy=False))
    if processor is not None:
        try:
            processor.applyRGB(a)
        except Exception as e:
            # Callers expect a working array back; log and fall through to
            # passthrough rather than re-raise mid-preview.
            print(f"OCIO applyRGB failed ({e}); falling back to passthrough")
    a = np.clip(a, 0.0, 1.0)
    return (a * 255.0).astype(np.uint8)
