"""
Solve camera from Matchbox VP control points and write results back
to the Matchbox output parameters.

Self-contained — runs inside Flame via forge-bridge HTTP bridge.
Includes the solver math inline (no external imports needed beyond numpy).

Usage via forge-bridge:
    curl -X POST http://localhost:9999/exec -H "Content-Type: application/json" \
         -d '{"code": "<this file contents>", "main_thread": true}'
"""

import numpy as np

# =========================================================================
# Inline solver (subset of solver/ package)
# =========================================================================

def px_to_image_plane(px, py, w, h):
    rx, ry = px / w, py / h
    aspect = w / h
    if aspect >= 1.0:
        x = -1.0 + 2.0 * rx
        y = (1.0 - 2.0 * ry) / aspect
    else:
        x = (-1.0 + 2.0 * rx) * aspect
        y = 1.0 - 2.0 * ry
    return np.array([x, y])

def line_intersection(p1, p2, p3, p4):
    x1, y1 = p1; x2, y2 = p2; x3, y3 = p3; x4, y4 = p4
    denom = (x1-x2)*(y3-y4) - (y1-y2)*(x3-x4)
    if abs(denom) < 1e-12:
        return None
    t = ((x1-x3)*(y3-y4) - (y1-y3)*(x3-x4)) / denom
    return np.array([x1 + t*(x2-x1), y1 + t*(y2-y1)])

def ortho_proj(point, p1, p2):
    d = p2 - p1
    d_sq = np.dot(d, d)
    if d_sq < 1e-24:
        return p1.copy()
    return p1 + (np.dot(point - p1, d) / d_sq) * d

def compute_focal_length(vp1, vp2, pp):
    puv = ortho_proj(pp, vp1, vp2)
    f_sq = np.linalg.norm(vp2 - puv) * np.linalg.norm(vp1 - puv) - np.linalg.norm(pp - puv)**2
    return float(np.sqrt(f_sq)) if f_sq > 0 else None

def compute_rotation(vp1, vp2, f, pp):
    of_u = np.array([vp1[0]-pp[0], vp1[1]-pp[1], -f])
    of_v = np.array([vp2[0]-pp[0], vp2[1]-pp[1], -f])
    u = of_u / np.linalg.norm(of_u)
    v = of_v / np.linalg.norm(of_v)
    w = np.cross(u, v)
    w = w / np.linalg.norm(w)
    return np.column_stack([u, v, w])

AXIS_VECTORS = {
    0: np.array([1,0,0]),   # +X
    1: np.array([-1,0,0]),  # -X
    2: np.array([0,1,0]),   # +Y
    3: np.array([0,-1,0]),  # -Y
    4: np.array([0,0,1]),   # +Z
    5: np.array([0,0,-1]),  # -Z
}

def axis_assignment(ax1, ax2):
    r1 = AXIS_VECTORS[ax1].astype(float)
    r2 = AXIS_VECTORS[ax2].astype(float)
    r3 = np.cross(r1, r2)
    return np.vstack([r1, r2, r3])

def euler_from_matrix(R):
    # Flame's identity camera looks +Z_local (not -Z); rotate local frame
    # 180° around Y to convert OpenGL-style cam→world to Flame's convention.
    RY_180 = np.array([[-1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, -1.0]])
    R = R @ RY_180
    # Flame uses R = Rx(-rx) · Ry(-ry) · Rz(rz) (X, Y inverted from RH rule)
    cy = np.sqrt(R[0,0]**2 + R[0,1]**2)
    if cy > 1e-6:
        rx = np.arctan2( R[1,2], R[2,2])
        ry = np.arctan2(-R[0,2], cy)
        rz = np.arctan2(-R[0,1], R[0,0])
    else:
        rx = np.arctan2(-R[2,1], R[1,1])
        ry = np.arctan2(-R[0,2], cy)
        rz = 0.0
    return np.degrees(np.array([rx, ry, rz]))

# =========================================================================
# Flame interaction
# =========================================================================

import flame

MATCHBOX_NAME = "CameraMatch"  # partial match
SENSOR_WIDTH_MM = 36.0  # full frame default

def find_matchbox():
    b = flame.batch
    for node in b.nodes:
        name = node.name.get_value() if hasattr(node.name, "get_value") else str(node.name)
        if MATCHBOX_NAME in name:
            return node
    return None

def read_vec2(node, attr_name):
    """Read a vec2 param — may come back as tuple or have get_value."""
    try:
        attr = getattr(node, attr_name)
        val = attr.get_value() if hasattr(attr, "get_value") else attr
        if hasattr(val, "__iter__"):
            return (float(val[0]), float(val[1]))
        return (0.5, 0.5)
    except Exception as e:
        print("  WARN: could not read " + attr_name + ": " + str(e))
        return (0.5, 0.5)

def read_int(node, attr_name, default=0):
    try:
        attr = getattr(node, attr_name)
        val = attr.get_value() if hasattr(attr, "get_value") else attr
        return int(val)
    except:
        return default

def read_bool(node, attr_name, default=False):
    try:
        attr = getattr(node, attr_name)
        val = attr.get_value() if hasattr(attr, "get_value") else attr
        return bool(val)
    except:
        return default

def set_float(node, attr_name, value):
    try:
        attr = getattr(node, attr_name)
        attr.set_value(float(value))
    except Exception as e:
        print("  WARN: could not set " + attr_name + ": " + str(e))

def solve():
    mb = find_matchbox()
    if mb is None:
        print("ERROR: No CameraMatch Matchbox found in batch")
        return

    mb_name = mb.name.get_value() if hasattr(mb.name, "get_value") else str(mb.name)
    print("Found Matchbox: " + mb_name)

    # Read VP control points (normalized 0..1, origin bottom-left)
    vp1_l1_s = read_vec2(mb, "vp1_l1_start")
    vp1_l1_e = read_vec2(mb, "vp1_l1_end")
    vp1_l2_s = read_vec2(mb, "vp1_l2_start")
    vp1_l2_e = read_vec2(mb, "vp1_l2_end")
    vp2_l1_s = read_vec2(mb, "vp2_l1_start")
    vp2_l1_e = read_vec2(mb, "vp2_l1_end")
    vp2_l2_s = read_vec2(mb, "vp2_l2_start")
    vp2_l2_e = read_vec2(mb, "vp2_l2_end")

    ax1 = read_int(mb, "vp1_axis", 1)
    ax2 = read_int(mb, "vp2_axis", 5)
    has_origin = read_bool(mb, "use_origin", False)
    origin = read_vec2(mb, "origin_pt") if has_origin else None

    # Get image resolution from batch
    b = flame.batch
    try:
        W = int(b.width.get_value())
        H = int(b.height.get_value())
    except:
        W, H = 1920, 1080
        print("  WARN: could not read batch resolution, using 1920x1080")

    print("Image: " + str(W) + "x" + str(H))
    print("VP1 axis: " + str(ax1) + "  VP2 axis: " + str(ax2))

    # Convert normalized coords to pixels (flip Y: param 0,0 = bottom-left, pixel 0,0 = top-left)
    def param_to_px(p):
        return np.array([p[0] * W, (1.0 - p[1]) * H])

    # Convert to ImagePlane and find VPs
    pts1 = [px_to_image_plane(param_to_px(p)[0], param_to_px(p)[1], W, H)
            for p in [vp1_l1_s, vp1_l1_e, vp1_l2_s, vp1_l2_e]]
    pts2 = [px_to_image_plane(param_to_px(p)[0], param_to_px(p)[1], W, H)
            for p in [vp2_l1_s, vp2_l1_e, vp2_l2_s, vp2_l2_e]]

    vp1 = line_intersection(pts1[0], pts1[1], pts1[2], pts1[3])
    vp2 = line_intersection(pts2[0], pts2[1], pts2[2], pts2[3])

    if vp1 is None or vp2 is None:
        print("ERROR: Lines are parallel — no vanishing point found")
        return

    pp = np.array([0.0, 0.0])
    f = compute_focal_length(vp1, vp2, pp)
    if f is None:
        print("ERROR: Degenerate VP configuration (focal length undefined)")
        return

    # Rotation
    R = compute_rotation(vp1, vp2, f, pp)
    A = axis_assignment(ax1, ax2)
    view_rot = R @ A
    cam_rot_mat = np.linalg.inv(view_rot)  # = transpose for orthonormal
    euler = euler_from_matrix(cam_rot_mat)

    # FOV
    hfov = 2.0 * np.arctan(1.0 / f)
    aspect = W / H
    vfov = 2.0 * np.arctan(np.tan(hfov / 2.0) / aspect)
    hfov_deg = float(np.degrees(hfov))
    vfov_deg = float(np.degrees(vfov))

    # Focal length in mm
    focal_mm = f * SENSOR_WIDTH_MM / 2.0

    # Translation
    cam_pos = np.array([0.0, 0.0, 0.0])
    if has_origin and origin is not None:
        org_px = param_to_px(origin)
        org_ip = px_to_image_plane(org_px[0], org_px[1], W, H)
        hw = np.tan(hfov / 2.0)
        if aspect >= 1.0:
            ray = np.array([org_ip[0] * hw, org_ip[1] * hw, -1.0])
        else:
            hh = hw / aspect
            ray = np.array([org_ip[0] * hh * aspect, org_ip[1] * hh, -1.0])
        ray = ray / np.linalg.norm(ray)
        ray_world = cam_rot_mat @ ray
        cam_pos = -10.0 * ray_world

    # Print results
    print("--- Solved Camera ---")
    print("Position: " + str(cam_pos))
    print("Rotation: " + str(euler) + " deg")
    print("Focal:    " + str(round(focal_mm, 2)) + " mm")
    print("H FOV:    " + str(round(hfov_deg, 2)) + " deg")
    print("V FOV:    " + str(round(vfov_deg, 2)) + " deg")

    # Write results back to Matchbox output params
    set_float(mb, "out_pos_x", cam_pos[0])
    set_float(mb, "out_pos_y", cam_pos[1])
    set_float(mb, "out_pos_z", cam_pos[2])
    set_float(mb, "out_rot_x", euler[0])
    set_float(mb, "out_rot_y", euler[1])
    set_float(mb, "out_rot_z", euler[2])
    set_float(mb, "out_focal_mm", focal_mm)
    set_float(mb, "out_hfov", hfov_deg)
    set_float(mb, "out_vfov", vfov_deg)

    print("--- Values written to Matchbox 'Solved' page ---")

solve()
