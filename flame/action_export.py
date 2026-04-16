"""
Export solved camera parameters to a Flame Action node.

Flame's Action node camera uses:
  - Position: translate X/Y/Z
  - Rotation: rotate X/Y/Z (Euler angles, degrees)
  - Field of view OR focal length + film back

This module converts the solver's 4x4 camera transform into Flame-compatible
values and generates Python code to apply them via Flame's Python API.

Matrix convention notes:
  - Solver outputs a camera→world 4x4 matrix (right-handed, Y-up)
  - Flame uses right-handed Y-up coordinates
  - Flame Action camera rotation order needs verification in-app
    (assumed XYZ Euler here — adjust ROTATION_ORDER if needed)
"""

import numpy as np
from typing import Optional

# Flame rotation order — verify in Flame and change if needed
ROTATION_ORDER = "xyz"


def matrix_to_euler_xyz(R: np.ndarray) -> np.ndarray:
    """Extract XYZ Euler angles (in degrees) from a 3x3 rotation matrix.

    Convention: R = Rx(ax) @ Ry(ay) @ Rz(az)

    Args:
        R: 3x3 rotation matrix

    Returns:
        np.ndarray [rx, ry, rz] in degrees
    """
    # From the rotation matrix R = Rx @ Ry @ Rz:
    # R[0,2] = sin(ry)
    # R[2,2] = cos(ry)*cos(rx)
    # R[1,2] = -cos(ry)*sin(rx)  ... wait, let me use the standard decomposition

    # For R = Rx @ Ry @ Rz (intrinsic XYZ):
    sy = R[0, 2]
    cy = np.sqrt(R[0, 0] ** 2 + R[0, 1] ** 2)

    if cy > 1e-6:  # not at gimbal lock
        rx = np.arctan2(-R[1, 2], R[2, 2])
        ry = np.arctan2(R[0, 2], cy)
        rz = np.arctan2(-R[0, 1], R[0, 0])
    else:
        # Gimbal lock: ry = +/- 90 degrees
        rx = np.arctan2(R[2, 1], R[1, 1])
        ry = np.arctan2(R[0, 2], cy)
        rz = 0.0

    return np.degrees(np.array([rx, ry, rz]))


def matrix_to_euler_zxy(R: np.ndarray) -> np.ndarray:
    """Extract ZXY Euler angles (in degrees) from a 3x3 rotation matrix.

    Some Flame versions use ZXY order for Action camera.

    Args:
        R: 3x3 rotation matrix

    Returns:
        np.ndarray [rx, ry, rz] in degrees (applied in Z, X, Y order)
    """
    # R = Rz @ Rx @ Ry
    sx = R[2, 1]
    cx = np.sqrt(R[0, 1] ** 2 + R[1, 1] ** 2)

    if cx > 1e-6:
        rx = np.arctan2(R[2, 1], cx)
        ry = np.arctan2(-R[2, 0], R[2, 2])
        rz = np.arctan2(-R[0, 1], R[1, 1])
    else:
        rx = np.arctan2(R[2, 1], cx)
        ry = 0.0
        rz = np.arctan2(R[0, 0], R[1, 0])

    return np.degrees(np.array([rx, ry, rz]))


def camera_solve_to_flame_params(solve_result: dict, sensor_width_mm: float = 36.0) -> dict:
    """Convert solver output to Flame Action camera parameters.

    Args:
        solve_result: Dict from solve_2vp or solve_1vp containing:
            - camera_transform: 4x4 camera→world matrix
            - horizontal_fov: horizontal FOV in radians
            - focal_length: relative focal length
            - principal_point: principal point in ImagePlane coords
        sensor_width_mm: Camera sensor width in mm (default: 36mm full frame)

    Returns:
        Dict with Flame-ready camera parameters:
            - translate_x, translate_y, translate_z: position
            - rotate_x, rotate_y, rotate_z: Euler angles in degrees
            - focal_length_mm: focal length in mm
            - horizontal_fov_deg: horizontal FOV in degrees
            - film_back_width_mm: sensor width
            - principal_point_offset: (x, y) shift from centre, normalized
    """
    ct = solve_result["camera_transform"]
    R = ct[:3, :3]
    t = ct[:3, 3]

    # Euler angles
    euler = matrix_to_euler_xyz(R)

    # Focal length in mm: f_mm = f_rel * sensor_width / 2
    f_rel = solve_result["focal_length"]
    focal_length_mm = f_rel * sensor_width_mm / 2.0

    # FOV in degrees
    h_fov_deg = np.degrees(solve_result["horizontal_fov"])

    # Principal point offset (0, 0 = centred)
    pp = solve_result["principal_point"]

    return {
        "translate_x": float(t[0]),
        "translate_y": float(t[1]),
        "translate_z": float(t[2]),
        "rotate_x": float(euler[0]),
        "rotate_y": float(euler[1]),
        "rotate_z": float(euler[2]),
        "focal_length_mm": float(focal_length_mm),
        "horizontal_fov_deg": float(h_fov_deg),
        "film_back_width_mm": float(sensor_width_mm),
        "principal_point_offset": (float(pp[0]), float(pp[1])),
        "camera_transform_4x4": ct.tolist(),
    }


def generate_flame_python(
    params: dict,
    action_node_name: str = "Action",
    camera_name: str = "camera",
) -> str:
    """Generate Python code to apply camera parameters to a Flame Action node.

    The generated code is meant to run inside Flame's Python environment,
    either via the forge-bridge HTTP bridge or directly in a hook.

    Args:
        params: Dict from camera_solve_to_flame_params
        action_node_name: Name of the Action node in the Batch schematic
        camera_name: Name of the camera within the Action node

    Returns:
        Python source code string ready to exec in Flame.
    """
    tx = params["translate_x"]
    ty = params["translate_y"]
    tz = params["translate_z"]
    rx = params["rotate_x"]
    ry = params["rotate_y"]
    rz = params["rotate_z"]
    fl = params["focal_length_mm"]
    fbw = params["film_back_width_mm"]

    code = f'''import flame

def _apply_camera():
    """Apply solved camera parameters to Action node."""
    b = flame.batch

    # Find the Action node
    action_node = None
    for node in b.nodes:
        if node.name.get_value() == "{action_node_name}":
            action_node = node
            break

    if action_node is None:
        raise RuntimeError("Action node '{action_node_name}' not found in Batch")

    # Access the camera within the Action node
    # NOTE: The exact attribute path depends on your Flame version.
    # This assumes Action node exposes camera via node attributes.
    # If the camera is a sub-object, adjust the attribute path accordingly.
    #
    # Common patterns in Flame:
    #   action_node.camera.position.x.set_value(tx)
    #   action_node.camera.rotation.x.set_value(rx)
    #
    # Alternative: set the full 4x4 matrix directly if supported:
    #   action_node.camera.matrix.set_value(matrix_values)

    # --- Position ---
    try:
        cam = action_node.camera
        cam.position.x.set_value({tx})
        cam.position.y.set_value({ty})
        cam.position.z.set_value({tz})

        # --- Rotation (Euler XYZ, degrees) ---
        cam.rotation.x.set_value({rx})
        cam.rotation.y.set_value({ry})
        cam.rotation.z.set_value({rz})

        # --- Lens ---
        cam.focal_length.set_value({fl})
        cam.film_back_width.set_value({fbw})

        print("Camera solve applied successfully")
        print(f"  Position: ({tx:.4f}, {ty:.4f}, {tz:.4f})")
        print(f"  Rotation: ({rx:.4f}, {ry:.4f}, {rz:.4f})")
        print(f"  Focal length: {fl:.2f}mm")

    except AttributeError as e:
        # If the attribute path is wrong, print what's available
        print(f"Camera attribute error: {{e}}")
        print("Available Action node attributes:")
        for attr in dir(action_node):
            if not attr.startswith("_"):
                print(f"  {{attr}}")
        raise

flame.schedule_idle_event(_apply_camera)
'''
    return code


def generate_flame_python_matrix(
    params: dict,
    action_node_name: str = "Action",
) -> str:
    """Generate Python code that applies the full 4x4 matrix to Flame.

    Alternative approach: sets the camera world transform as a matrix
    rather than decomposed position/rotation. Use this if the Action node
    supports direct matrix input.

    Args:
        params: Dict from camera_solve_to_flame_params
        action_node_name: Name of the Action node

    Returns:
        Python source code string.
    """
    matrix = params["camera_transform_4x4"]
    fl = params["focal_length_mm"]
    fbw = params["film_back_width_mm"]

    # Format matrix as a flat list (row-major)
    flat = [matrix[r][c] for r in range(4) for c in range(4)]
    matrix_str = ", ".join(f"{v:.10f}" for v in flat)

    code = f'''import flame

def _apply_camera_matrix():
    """Apply solved camera matrix to Action node."""
    b = flame.batch

    action_node = None
    for node in b.nodes:
        if node.name.get_value() == "{action_node_name}":
            action_node = node
            break

    if action_node is None:
        raise RuntimeError("Action node '{action_node_name}' not found in Batch")

    # 4x4 camera-to-world transform (row-major)
    matrix = [{matrix_str}]

    # Apply matrix — the exact API depends on Flame version.
    # Try the matrix attribute first, fall back to decomposed.
    try:
        cam = action_node.camera
        cam.world_matrix.set_value(matrix)
        cam.focal_length.set_value({fl})
        cam.film_back_width.set_value({fbw})
        print("Camera matrix applied successfully")
    except AttributeError:
        print("Direct matrix API not available — use decomposed mode instead")
        raise

flame.schedule_idle_event(_apply_camera_matrix)
'''
    return code
