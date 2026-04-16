"""
Camera calibration solver — 1VP and 2VP modes.

Ported from fSpy (solver.ts). Reference: Guillou et al.,
"Using Vanishing Points for Camera Calibration and Coarse 3D Reconstruction
from a Single Image"
"""

import numpy as np
from typing import Optional, Tuple
from .math_util import orthogonal_projection_on_line
from .coordinates import px_to_image_plane

# Default depth scale when no reference distance is provided
DEFAULT_CAMERA_DISTANCE_SCALE = 10.0

# World axis unit vectors
AXIS_VECTORS = {
    "+X": np.array([1.0, 0.0, 0.0]),
    "-X": np.array([-1.0, 0.0, 0.0]),
    "+Y": np.array([0.0, 1.0, 0.0]),
    "-Y": np.array([0.0, -1.0, 0.0]),
    "+Z": np.array([0.0, 0.0, 1.0]),
    "-Z": np.array([0.0, 0.0, -1.0]),
}


def compute_focal_length(
    vp1: np.ndarray, vp2: np.ndarray, principal_point: np.ndarray
) -> Optional[float]:
    """Compute relative focal length from two vanishing points and principal point.

    Uses the orthocentre relationship: if P is the principal point and VP1, VP2
    are vanishing points, the focal length f satisfies:
        f^2 = |VP2 - Puv| * |VP1 - Puv| - |P - Puv|^2
    where Puv is the orthogonal projection of P onto line VP1->VP2.

    Args:
        vp1: First vanishing point in ImagePlane coords [x, y]
        vp2: Second vanishing point in ImagePlane coords [x, y]
        principal_point: Principal point in ImagePlane coords [x, y]

    Returns:
        Relative focal length, or None if the VP configuration is degenerate
        (f^2 <= 0).
    """
    puv = orthogonal_projection_on_line(principal_point, vp1, vp2)

    dist_vp2_puv = np.linalg.norm(vp2 - puv)
    dist_vp1_puv = np.linalg.norm(vp1 - puv)
    dist_p_puv = np.linalg.norm(principal_point - puv)

    f_sq = dist_vp2_puv * dist_vp1_puv - dist_p_puv ** 2

    if f_sq <= 0:
        return None

    return float(np.sqrt(f_sq))


def compute_camera_rotation_matrix(
    vp1: np.ndarray,
    vp2: np.ndarray,
    focal_length: float,
    principal_point: np.ndarray,
) -> np.ndarray:
    """Compute the 3x3 camera rotation matrix from vanishing points.

    Following Guillou et al. section 3.3:
        OFu = (VP1 - P, -f)  (3D direction through VP1)
        OFv = (VP2 - P, -f)  (3D direction through VP2)
        u = normalize(OFu)
        v = normalize(OFv)
        w = u x v

    Args:
        vp1: First vanishing point in ImagePlane coords
        vp2: Second vanishing point in ImagePlane coords
        focal_length: Relative focal length
        principal_point: Principal point in ImagePlane coords

    Returns:
        3x3 rotation matrix (columns are u, v, w camera axes)
    """
    of_u = np.array([
        vp1[0] - principal_point[0],
        vp1[1] - principal_point[1],
        -focal_length,
    ])
    of_v = np.array([
        vp2[0] - principal_point[0],
        vp2[1] - principal_point[1],
        -focal_length,
    ])

    u = of_u / np.linalg.norm(of_u)
    v = of_v / np.linalg.norm(of_v)
    w = np.cross(u, v)
    w = w / np.linalg.norm(w)  # normalize for safety

    # Column matrix: M = [u | v | w]
    return np.column_stack([u, v, w])


def axis_assignment_matrix(axis1: str, axis2: str) -> np.ndarray:
    """Build the axis assignment matrix mapping VP directions to world axes.

    VP1's direction maps to axis1, VP2's direction maps to axis2, and the
    third axis is their cross product.

    Args:
        axis1: World axis for VP1, e.g. "+X", "-Z"
        axis2: World axis for VP2, e.g. "+Z", "+X"

    Returns:
        3x3 axis assignment matrix (rows are world axis unit vectors)
    """
    row1 = AXIS_VECTORS[axis1].copy()
    row2 = AXIS_VECTORS[axis2].copy()
    row3 = np.cross(row1, row2)

    return np.vstack([row1, row2, row3])


def compute_view_transform(
    vp1: np.ndarray,
    vp2: np.ndarray,
    focal_length: float,
    principal_point: np.ndarray,
    axis1: str = "+Z",
    axis2: str = "+X",
) -> np.ndarray:
    """Compute the full 4x4 view transform (world -> camera, rotation only).

    Combines the camera rotation matrix with the axis assignment to produce
    a view transform whose rotation block maps world axes correctly.
    Translation is identity (origin) — use compute_translation to set position.

    Args:
        vp1: First vanishing point in ImagePlane coords
        vp2: Second vanishing point in ImagePlane coords
        focal_length: Relative focal length
        principal_point: Principal point in ImagePlane coords
        axis1: World axis corresponding to VP1 direction
        axis2: World axis corresponding to VP2 direction

    Returns:
        4x4 view transform matrix (rotation only, translation = 0)
    """
    R = compute_camera_rotation_matrix(vp1, vp2, focal_length, principal_point)
    A = axis_assignment_matrix(axis1, axis2)

    view_rot = R @ A

    view = np.eye(4)
    view[:3, :3] = view_rot

    return view


def compute_translation(
    origin_px: np.ndarray,
    view_transform: np.ndarray,
    horizontal_fov: float,
    w: int,
    h: int,
    reference_distance: Optional[float] = None,
    ref_point1_px: Optional[np.ndarray] = None,
    ref_point2_px: Optional[np.ndarray] = None,
    ref_axis: Optional[str] = None,
) -> np.ndarray:
    """Compute camera translation from an origin control point.

    A ray is cast from the camera through the user-marked origin point.
    The camera is placed along that ray at either a default depth or
    a distance calibrated by reference points.

    Args:
        origin_px: Pixel coords of the point the user marks as world origin
        view_transform: 4x4 view transform (rotation-only, from compute_view_transform)
        horizontal_fov: Horizontal field of view in radians
        w: Image width in pixels
        h: Image height in pixels
        reference_distance: Real-world distance between ref_point1 and ref_point2
        ref_point1_px: First reference point in pixel coords
        ref_point2_px: Second reference point in pixel coords
        ref_axis: Which world axis the reference points lie along (e.g. "+X")

    Returns:
        4x4 camera transform (camera -> world), with translation set.
    """
    # Convert origin to image plane
    origin_ip = px_to_image_plane(origin_px[0], origin_px[1], w, h)

    # Compute half-width at unit depth from FOV
    half_w = np.tan(horizontal_fov / 2.0)
    aspect = w / h

    # Ray direction in camera space (image plane point at z = -1)
    # Image plane x in [-1, 1] maps to camera x in [-half_w, half_w]
    if aspect >= 1.0:
        cam_x = origin_ip[0] * half_w
        cam_y = origin_ip[1] * half_w  # y range is [-1/aspect, 1/aspect], already scaled
    else:
        half_h = half_w / aspect
        cam_x = origin_ip[0] * half_h * aspect  # x range is [-aspect, aspect]
        cam_y = origin_ip[1] * half_h

    ray_dir_cam = np.array([cam_x, cam_y, -1.0])
    ray_dir_cam = ray_dir_cam / np.linalg.norm(ray_dir_cam)

    # Transform ray direction to world space
    camera_transform = np.linalg.inv(view_transform)
    rot = camera_transform[:3, :3]
    ray_dir_world = rot @ ray_dir_cam

    # Determine depth
    depth = DEFAULT_CAMERA_DISTANCE_SCALE

    if (
        reference_distance is not None
        and ref_point1_px is not None
        and ref_point2_px is not None
        and ref_axis is not None
    ):
        # Project both reference points to get their 3D separation at unit depth,
        # then scale so the separation matches reference_distance
        rp1_ip = px_to_image_plane(ref_point1_px[0], ref_point1_px[1], w, h)
        rp2_ip = px_to_image_plane(ref_point2_px[0], ref_point2_px[1], w, h)

        if aspect >= 1.0:
            rp1_cam = np.array([rp1_ip[0] * half_w, rp1_ip[1] * half_w, -1.0])
            rp2_cam = np.array([rp2_ip[0] * half_w, rp2_ip[1] * half_w, -1.0])
        else:
            half_h = half_w / aspect
            rp1_cam = np.array([rp1_ip[0] * half_h * aspect, rp1_ip[1] * half_h, -1.0])
            rp2_cam = np.array([rp2_ip[0] * half_h * aspect, rp2_ip[1] * half_h, -1.0])

        # Project to world
        rp1_world = rot @ rp1_cam
        rp2_world = rot @ rp2_cam

        # Get the axis index to compare along
        axis_vec = AXIS_VECTORS[ref_axis]
        axis_idx = int(np.argmax(np.abs(axis_vec)))

        # Separation along that axis at unit depth
        sep_at_unit = abs(rp1_world[axis_idx] - rp2_world[axis_idx])

        if sep_at_unit > 1e-12:
            depth = reference_distance / sep_at_unit

    # Camera position = -depth * ray_dir_world (camera looks at origin along ray)
    camera_pos = -depth * ray_dir_world

    result = camera_transform.copy()
    result[:3, 3] = camera_pos

    return result


def compute_horizontal_fov(focal_length: float) -> float:
    """Compute horizontal field of view from relative focal length.

    For a wide image, the ImagePlane x range is [-1, 1], so half-width = 1.
    FOV = 2 * atan(half_width / f) = 2 * atan(1 / f)

    Args:
        focal_length: Relative focal length

    Returns:
        Horizontal field of view in radians
    """
    return 2.0 * np.arctan(1.0 / focal_length)


def compute_vertical_fov(horizontal_fov: float, aspect: float) -> float:
    """Compute vertical FOV from horizontal FOV and aspect ratio.

    Args:
        horizontal_fov: Horizontal FOV in radians
        aspect: Width / height

    Returns:
        Vertical field of view in radians
    """
    return 2.0 * np.arctan(np.tan(horizontal_fov / 2.0) / aspect)


def solve_2vp(
    vp1_lines: Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray],
    vp2_lines: Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray],
    w: int,
    h: int,
    principal_point: Optional[np.ndarray] = None,
    axis1: str = "+Z",
    axis2: str = "+X",
    origin_px: Optional[np.ndarray] = None,
    reference_distance: Optional[float] = None,
    ref_point1_px: Optional[np.ndarray] = None,
    ref_point2_px: Optional[np.ndarray] = None,
    ref_axis: Optional[str] = None,
) -> Optional[dict]:
    """Full 2-vanishing-point solve pipeline.

    Args:
        vp1_lines: (p1, p2, p3, p4) — two line segments converging to VP1, in pixels
        vp2_lines: (p1, p2, p3, p4) — two line segments converging to VP2, in pixels
        w: Image width in pixels
        h: Image height in pixels
        principal_point: Override principal point in ImagePlane coords (default: image centre)
        axis1: World axis for VP1
        axis2: World axis for VP2
        origin_px: Origin control point in pixel coords
        reference_distance: Real-world reference distance
        ref_point1_px, ref_point2_px: Reference measurement points in pixel coords
        ref_axis: Axis the reference measurement lies along

    Returns:
        Dict with solved camera parameters, or None on failure.
    """
    from .math_util import line_intersection

    # Convert line endpoints to image plane
    vp1_ip_pts = [px_to_image_plane(p[0], p[1], w, h) for p in vp1_lines]
    vp2_ip_pts = [px_to_image_plane(p[0], p[1], w, h) for p in vp2_lines]

    # Compute vanishing points
    vp1 = line_intersection(vp1_ip_pts[0], vp1_ip_pts[1], vp1_ip_pts[2], vp1_ip_pts[3])
    vp2 = line_intersection(vp2_ip_pts[0], vp2_ip_pts[1], vp2_ip_pts[2], vp2_ip_pts[3])

    if vp1 is None or vp2 is None:
        return None

    # Principal point defaults to image centre (0, 0 in ImagePlane)
    pp = principal_point if principal_point is not None else np.array([0.0, 0.0])

    # Focal length
    f = compute_focal_length(vp1, vp2, pp)
    if f is None:
        return None

    # View transform (rotation only)
    view = compute_view_transform(vp1, vp2, f, pp, axis1, axis2)

    # FOV
    h_fov = compute_horizontal_fov(f)
    v_fov = compute_vertical_fov(h_fov, w / h)

    # Camera transform
    if origin_px is not None:
        camera_transform = compute_translation(
            origin_px, view, h_fov, w, h,
            reference_distance, ref_point1_px, ref_point2_px, ref_axis,
        )
    else:
        camera_transform = np.linalg.inv(view)

    return {
        "vp1": vp1,
        "vp2": vp2,
        "principal_point": pp,
        "focal_length": f,
        "horizontal_fov": h_fov,
        "vertical_fov": v_fov,
        "view_transform": view,
        "camera_transform": camera_transform,
    }


def solve_1vp(
    vp1_lines: Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray],
    horizon_p1: np.ndarray,
    horizon_p2: np.ndarray,
    focal_length_mm: float,
    sensor_width_mm: float,
    w: int,
    h: int,
    principal_point: Optional[np.ndarray] = None,
    axis1: str = "+Z",
    axis2: str = "+X",
    origin_px: Optional[np.ndarray] = None,
) -> Optional[dict]:
    """Single vanishing point solve using known focal length and horizon line.

    When only one VP can be drawn, the second VP is synthesized from the
    known focal length and horizon direction:
        k = -(|OFu|^2 + f^2) / (OFu . horizonDir)
        VP2 = VP1 + k * horizonDir

    Args:
        vp1_lines: (p1, p2, p3, p4) — two line segments converging to VP1, in pixels
        horizon_p1, horizon_p2: Two points defining the horizon line, in pixels
        focal_length_mm: Known focal length in mm
        sensor_width_mm: Sensor width in mm
        w: Image width in pixels
        h: Image height in pixels
        principal_point: Override principal point in ImagePlane coords
        axis1: World axis for VP1
        axis2: World axis for VP2
        origin_px: Origin control point in pixel coords

    Returns:
        Dict with solved camera parameters, or None on failure.
    """
    from .math_util import line_intersection

    # Convert to image plane
    vp1_ip_pts = [px_to_image_plane(p[0], p[1], w, h) for p in vp1_lines]
    h1_ip = px_to_image_plane(horizon_p1[0], horizon_p1[1], w, h)
    h2_ip = px_to_image_plane(horizon_p2[0], horizon_p2[1], w, h)

    # Compute VP1
    vp1 = line_intersection(vp1_ip_pts[0], vp1_ip_pts[1], vp1_ip_pts[2], vp1_ip_pts[3])
    if vp1 is None:
        return None

    pp = principal_point if principal_point is not None else np.array([0.0, 0.0])

    # Relative focal length from mm: f_rel = f_mm / (sensor_width / 2)
    # Because ImagePlane x range for wide images is [-1, 1], so half-width = 1
    f = focal_length_mm / (sensor_width_mm / 2.0)

    # Horizon direction in image plane
    horizon_dir = h2_ip - h1_ip
    horizon_dir = horizon_dir / np.linalg.norm(horizon_dir)

    # OFu = 3D direction through VP1
    of_u = np.array([vp1[0] - pp[0], vp1[1] - pp[1]])
    of_u_3d = np.array([of_u[0], of_u[1], -f])

    # k = -(|OFu|^2 + f^2) / (OFu_2d . horizonDir)
    of_u_sq = np.dot(of_u_3d, of_u_3d)
    denom = np.dot(of_u, horizon_dir)

    if abs(denom) < 1e-12:
        return None

    k = -of_u_sq / denom

    # Synthesized VP2
    vp2 = vp1 + k * horizon_dir

    # Now solve as 2VP
    view = compute_view_transform(vp1, vp2, f, pp, axis1, axis2)
    h_fov = compute_horizontal_fov(f)
    v_fov = compute_vertical_fov(h_fov, w / h)

    if origin_px is not None:
        camera_transform = compute_translation(origin_px, view, h_fov, w, h)
    else:
        camera_transform = np.linalg.inv(view)

    return {
        "vp1": vp1,
        "vp2": vp2,
        "principal_point": pp,
        "focal_length": f,
        "horizontal_fov": h_fov,
        "vertical_fov": v_fov,
        "view_transform": view,
        "camera_transform": camera_transform,
    }
