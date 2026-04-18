"""
Coordinate conversions between pixel space and fSpy's ImagePlane frame.

ImagePlane frame:
  - Origin at image centre
  - Wide image: x in [-1, 1], y in [-1/aspect, 1/aspect]
  - Tall image: x in [-aspect, aspect], y in [-1, 1]
  - Y is up (pixel y is flipped)
"""

import numpy as np


def px_to_image_plane(px: float, py: float, w: int, h: int) -> np.ndarray:
    """Convert pixel coordinates to ImagePlane coordinates.

    Args:
        px: Pixel x (0 = left edge, w = right edge)
        py: Pixel y (0 = top edge, h = bottom edge)
        w: Image width in pixels
        h: Image height in pixels

    Returns:
        2D point in ImagePlane coordinates as np.ndarray [x, y]
    """
    rx = px / w
    ry = py / h
    aspect = w / h

    if aspect >= 1.0:  # wide or square
        x = -1.0 + 2.0 * rx
        y = (1.0 - 2.0 * ry) / aspect
    else:  # tall
        x = (-1.0 + 2.0 * rx) * aspect
        y = 1.0 - 2.0 * ry

    return np.array([x, y])


def image_plane_to_px(ip: np.ndarray, w: int, h: int) -> np.ndarray:
    """Convert ImagePlane coordinates back to pixel coordinates.

    Args:
        ip: 2D point in ImagePlane coordinates [x, y]
        w: Image width in pixels
        h: Image height in pixels

    Returns:
        Pixel coordinates as np.ndarray [px, py]
    """
    aspect = w / h
    x, y = ip[0], ip[1]

    if aspect >= 1.0:  # wide or square
        rx = (x + 1.0) / 2.0
        ry = (1.0 - y * aspect) / 2.0
    else:  # tall
        rx = (x / aspect + 1.0) / 2.0
        ry = (1.0 - y) / 2.0

    return np.array([rx * w, ry * h])
