"""
Python companion for the Camera Match Matchbox shader.

Reads VP control point positions from the Matchbox node parameters,
runs the Python solver (more numerically robust than GLSL float),
and applies the result to the Action camera.

Can run via:
  1. forge-bridge HTTP bridge (POST /exec)
  2. Direct Flame Python console
  3. Flame hook callback
"""

import sys
import os
import numpy as np

# Add solver to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from solver.coordinates import px_to_image_plane
from solver.math_util import line_intersection
from solver.solver import (
    compute_focal_length,
    compute_camera_rotation_matrix,
    compute_view_transform,
    compute_horizontal_fov,
    compute_translation,
)
from flame.action_export import camera_solve_to_flame_params, matrix_to_euler_xyz

# Axis index to string mapping (matches Matchbox XML popup order)
AXIS_INDEX_MAP = {0: "+X", 1: "-X", 2: "+Y", 3: "-Y", 4: "+Z", 5: "-Z"}


def read_matchbox_params(action_node_name="Action", matchbox_name="Camera Match"):
    """Read VP control point values from the Matchbox node in Flame.

    This function runs inside Flame's Python environment.

    Args:
        action_node_name: Name of the Action node containing the Matchbox
        matchbox_name: Name of the Matchbox shader node

    Returns:
        Dict with control point positions and settings, or None on error.
    """
    import flame

    b = flame.batch

    # Find the Matchbox node
    matchbox_node = None
    for node in b.nodes:
        name = node.name.get_value() if hasattr(node.name, "get_value") else str(node.name)
        if name == matchbox_name:
            matchbox_node = node
            break

    if matchbox_node is None:
        print(f"Matchbox node '{matchbox_name}' not found")
        return None

    # Read vec2 parameters
    # The exact attribute access pattern depends on Flame version.
    # Matchbox params are typically accessible via node attributes.
    def read_vec2(param_name):
        attr = getattr(matchbox_node, param_name, None)
        if attr is None:
            print(f"  Warning: parameter '{param_name}' not found")
            return (0.5, 0.5)
        val = attr.get_value() if hasattr(attr, "get_value") else attr
        # vec2 may come back as tuple, list, or custom type
        if hasattr(val, "x"):
            return (float(val.x), float(val.y))
        return (float(val[0]), float(val[1]))

    def read_int(param_name, default=0):
        attr = getattr(matchbox_node, param_name, None)
        if attr is None:
            return default
        val = attr.get_value() if hasattr(attr, "get_value") else attr
        return int(val)

    def read_bool(param_name, default=False):
        attr = getattr(matchbox_node, param_name, None)
        if attr is None:
            return default
        val = attr.get_value() if hasattr(attr, "get_value") else attr
        return bool(val)

    params = {
        "vp1_line1_start": read_vec2("vp1_line1_start"),
        "vp1_line1_end": read_vec2("vp1_line1_end"),
        "vp1_line2_start": read_vec2("vp1_line2_start"),
        "vp1_line2_end": read_vec2("vp1_line2_end"),
        "vp2_line1_start": read_vec2("vp2_line1_start"),
        "vp2_line1_end": read_vec2("vp2_line1_end"),
        "vp2_line2_start": read_vec2("vp2_line2_start"),
        "vp2_line2_end": read_vec2("vp2_line2_end"),
        "vp1_axis": read_int("vp1_axis", 1),  # default -X
        "vp2_axis": read_int("vp2_axis", 5),  # default -Z
        "use_origin": read_bool("use_origin", False),
        "origin_point": read_vec2("origin_point"),
    }

    return params


def solve_from_params(params, width, height, sensor_width_mm=36.0):
    """Run the camera solve using Matchbox parameter values.

    Args:
        params: Dict from read_matchbox_params
        width: Image width in pixels
        height: Image height in pixels
        sensor_width_mm: Sensor width in mm

    Returns:
        Dict with Flame camera parameters, or None on failure.
    """
    W, H = width, height

    # Convert normalized (0..1) param coords to pixel coords
    # Matchbox params: (0,0) = bottom-left, (1,1) = top-right
    # Our solver expects: (0,0) = top-left pixel
    def param_to_px(p):
        return np.array([p[0] * W, (1.0 - p[1]) * H])

    vp1_lines = (
        param_to_px(params["vp1_line1_start"]),
        param_to_px(params["vp1_line1_end"]),
        param_to_px(params["vp1_line2_start"]),
        param_to_px(params["vp1_line2_end"]),
    )
    vp2_lines = (
        param_to_px(params["vp2_line1_start"]),
        param_to_px(params["vp2_line1_end"]),
        param_to_px(params["vp2_line2_start"]),
        param_to_px(params["vp2_line2_end"]),
    )

    axis1 = AXIS_INDEX_MAP.get(params["vp1_axis"], "-X")
    axis2 = AXIS_INDEX_MAP.get(params["vp2_axis"], "-Z")

    origin_px = None
    if params.get("use_origin"):
        origin_px = param_to_px(params["origin_point"])

    # Import solve_2vp here to avoid circular import at module level
    from solver.solver import solve_2vp

    result = solve_2vp(
        vp1_lines=vp1_lines,
        vp2_lines=vp2_lines,
        w=W, h=H,
        axis1=axis1,
        axis2=axis2,
        origin_px=origin_px,
    )

    if result is None:
        return None

    return camera_solve_to_flame_params(result, sensor_width_mm)


def apply_to_action_camera(
    flame_params,
    action_node_name="Action",
):
    """Apply solved camera parameters to a Flame Action camera.

    Must be called from within Flame's Python environment.
    Wraps the write operation in schedule_idle_event.

    Args:
        flame_params: Dict from camera_solve_to_flame_params
        action_node_name: Name of the Action node
    """
    import flame
    import threading

    result = {"error": None}
    event = threading.Event()

    def _apply():
        try:
            b = flame.batch

            action_node = None
            for node in b.nodes:
                name = node.name.get_value() if hasattr(node.name, "get_value") else str(node.name)
                if name == action_node_name:
                    action_node = node
                    break

            if action_node is None:
                result["error"] = f"Action node '{action_node_name}' not found"
                return

            cam = action_node.camera

            # Position
            cam.position.x.set_value(flame_params["translate_x"])
            cam.position.y.set_value(flame_params["translate_y"])
            cam.position.z.set_value(flame_params["translate_z"])

            # Rotation
            cam.rotation.x.set_value(flame_params["rotate_x"])
            cam.rotation.y.set_value(flame_params["rotate_y"])
            cam.rotation.z.set_value(flame_params["rotate_z"])

            # Lens
            cam.focal_length.set_value(flame_params["focal_length_mm"])
            cam.film_back_width.set_value(flame_params["film_back_width_mm"])

            print("Camera solve applied:")
            print(f"  Pos: ({flame_params['translate_x']:.3f}, "
                  f"{flame_params['translate_y']:.3f}, "
                  f"{flame_params['translate_z']:.3f})")
            print(f"  Rot: ({flame_params['rotate_x']:.2f}, "
                  f"{flame_params['rotate_y']:.2f}, "
                  f"{flame_params['rotate_z']:.2f}) deg")
            print(f"  FL:  {flame_params['focal_length_mm']:.1f}mm")
            print(f"  FOV: {flame_params['horizontal_fov_deg']:.1f} deg")

        except AttributeError as e:
            result["error"] = f"Camera attribute error: {e}"
            # Dump available attributes for debugging
            try:
                print("Available camera attributes:")
                for attr in dir(cam):
                    if not attr.startswith("_"):
                        print(f"  {attr}")
            except Exception:
                pass
        except Exception as e:
            result["error"] = str(e)
        finally:
            event.set()

    flame.schedule_idle_event(_apply)
    event.wait(timeout=10)

    if result["error"]:
        print(f"Error: {result['error']}")
    return result["error"] is None


def solve_and_apply(
    action_node_name="Action",
    matchbox_name="Camera Match",
    sensor_width_mm=36.0,
):
    """One-shot: read Matchbox params, solve, apply to Action camera.

    Call this from Flame's Python console or via forge-bridge.

    Args:
        action_node_name: Name of the Action node
        matchbox_name: Name of the Matchbox shader node
        sensor_width_mm: Camera sensor width in mm
    """
    import flame

    # Get image dimensions from current clip or batch setup
    # Try batch resolution first
    try:
        b = flame.batch
        width = int(b.width.get_value())
        height = int(b.height.get_value())
    except Exception:
        # Fallback to a common resolution
        print("Could not read batch resolution, defaulting to 1920x1080")
        width, height = 1920, 1080

    print(f"Image: {width}x{height}")

    # Read control points from Matchbox
    params = read_matchbox_params(action_node_name, matchbox_name)
    if params is None:
        return False

    print(f"VP1 axis: {AXIS_INDEX_MAP.get(params['vp1_axis'])}")
    print(f"VP2 axis: {AXIS_INDEX_MAP.get(params['vp2_axis'])}")

    # Solve
    flame_params = solve_from_params(params, width, height, sensor_width_mm)
    if flame_params is None:
        print("Solve failed — check VP line placement (lines may be parallel or degenerate)")
        return False

    # Apply
    return apply_to_action_camera(flame_params, action_node_name)
