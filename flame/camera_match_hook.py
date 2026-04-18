"""
Flame Camera Match — PySide2 VP line tool with live camera solve.

Install: copy this directory to /opt/Autodesk/shared/python/camera_match/

Right-click a Clip in Batch > Camera Match > Open Camera Match
  - Exports one frame from the clip
  - Opens a PySide2 window with draggable VP line endpoints
  - Solver runs live on every drag
  - Apply button writes solved camera to Action node

Requires: forge conda env (numpy, cv2)
"""

from __future__ import print_function
import sys
import os


def _ensure_forge_env():
    """Add the forge conda env site-packages to sys.path if not already present."""
    # Common conda env locations
    candidates = [
        os.path.expanduser("~/miniconda3/envs/forge/lib/python3.11/site-packages"),
        os.path.expanduser("~/miniforge3/envs/forge/lib/python3.11/site-packages"),
        os.path.expanduser("~/anaconda3/envs/forge/lib/python3.11/site-packages"),
        "/opt/miniconda3/envs/forge/lib/python3.11/site-packages",
    ]
    for path in candidates:
        if os.path.isdir(path) and path not in sys.path:
            sys.path.append(path)  # append, not insert — Flame's own packages take priority
            return True
    # Check if numpy is already importable (forge hooks may have set up the path)
    try:
        import numpy
        return True
    except ImportError:
        return False


# =========================================================================
# Inline solver — all numpy usage contained in _solve()
# =========================================================================

_AX_LABELS = ["+X", "-X", "+Y", "-Y", "+Z", "-Z"]

_TRACE_PATH = "/tmp/forge_camera_match_trace.json"


def _write_trace(trace):
    """Dump a solver trace dict to a JSON file for post-mortem inspection."""
    import json
    def _co(o):
        try:
            import numpy as np
            if isinstance(o, np.ndarray):
                return o.tolist()
            if isinstance(o, (np.floating, np.integer)):
                return float(o)
        except Exception:
            pass
        if isinstance(o, (tuple, list)):
            return [_co(x) for x in o]
        if isinstance(o, dict):
            return {k: _co(v) for k, v in o.items()}
        return o
    try:
        with open(_TRACE_PATH, "w") as fp:
            json.dump(_co(trace), fp, indent=2)
    except Exception:
        pass  # non-fatal


def _fit_vp(lines_px):
    """Least-squares vanishing point from N≥2 lines in pixel coords.

    Each line is ((x0,y0),(x1,y1)). Represents line as homogeneous form L=(a,b,c)
    with ax+by+c=0 passing through both endpoints. VP is the homogeneous point
    v minimizing sum((L_i·v)^2); solved via eigenvector of smallest eigenvalue
    of sum(L_i L_i^T). Reduces exactly to 2-line intersection when N=2.
    Returns (vp_x, vp_y) in pixel coords, or None if degenerate.
    """
    import numpy as np
    M = []
    for (p0, p1) in lines_px:
        x0, y0 = float(p0[0]), float(p0[1])
        x1, y1 = float(p1[0]), float(p1[1])
        # Homogeneous line through (x0,y0,1) and (x1,y1,1): cross product.
        a = y0 - y1
        b = x1 - x0
        c = x0 * y1 - x1 * y0
        n = np.hypot(a, b) or 1.0
        M.append([a/n, b/n, c/n])  # normalize so each line contributes equal weight
    M = np.asarray(M, dtype=float)
    # SVD: smallest singular vector of M is the VP in homogeneous coords.
    _, _, Vt = np.linalg.svd(M)
    v = Vt[-1]
    if abs(v[2]) < 1e-12:
        return None  # VP at infinity (lines parallel in image)
    return (float(v[0] / v[2]), float(v[1] / v[2]))


def _line_residual_px(p0, p1, vp):
    """Perpendicular pixel distance from VP to the infinite line through p0,p1.
    Zero = line extension hits VP exactly. Used to score each user-drawn line
    against the least-squares VP fit in 3-line mode."""
    import numpy as np
    x0, y0 = float(p0[0]), float(p0[1])
    x1, y1 = float(p1[0]), float(p1[1])
    a = y0 - y1
    b = x1 - x0
    c = x0 * y1 - x1 * y0
    n = np.hypot(a, b) or 1.0
    return abs(a * vp[0] + b * vp[1] + c) / n


def _solve_lines(vp1_lines, vp2_lines, w, h, ax1=1, ax2=5, origin_px=None, cam_back=None,
                 vp3_lines=None, quad_mode=False):
    """Solve from explicit line lists (N lines per VP, N ≥ 2). Adapts the 8-point
    `_solve` by fitting each VP via least squares and forwarding 4 representative
    points (the endpoints of lines 0 and 1 of each VP) so downstream math is
    unchanged; VPs used by the math come from the full least-squares fit.

    vp3_lines: optional 3rd VP lines used for FromThirdVanishingPoint principal
        point. Forwarded as a fitted VP3 pixel through `_solve`'s pp_px arg.
    quad_mode: if True, override vp2_lines using VP1 endpoints as quad corners.
    """
    import numpy as np
    if quad_mode and len(vp1_lines) >= 2:
        (a, b), (c, d) = vp1_lines[0], vp1_lines[1]
        vp2_lines = [(a, c), (b, d)]
    vp1 = _fit_vp(vp1_lines)
    vp2 = _fit_vp(vp2_lines)
    if vp1 is None or vp2 is None:
        return None
    vp3_px = None
    if vp3_lines is not None and len(vp3_lines) >= 2:
        vp3_px = _fit_vp(vp3_lines)
    # Pack 8 points for downstream: _solve recomputes each VP via 2-line
    # intersection (line_isect(ip[0..1], ip[2..3])). To force solver VP =
    # least-squares VP, we pass two synthetic "lines" that BOTH terminate
    # at the fitted vp — their intersection is then vp by construction.
    # Anchors are distinct user-line endpoints for numerical stability.
    #
    # Why not pass user line 0 as-is: in 3-line mode the LSQ vp is generally
    # *not* on user line 0 (it has a non-zero residual), so line_isect(line0,
    # synthetic_through_vp) returns a point biased toward line 0, not vp.
    # For N=2 this collapses to the exact intersection (vp is on both lines).
    def _pack(lines, vp):
        p0 = lines[0][0]
        q0 = lines[1][0] if len(lines) > 1 else lines[0][1]
        return [list(p0), [vp[0], vp[1]], list(q0), [vp[0], vp[1]]]
    pts8 = _pack(vp1_lines, vp1) + _pack(vp2_lines, vp2)
    return _solve(pts8, w, h, ax1=ax1, ax2=ax2, origin_px=origin_px,
                  cam_back=cam_back, vp3_px=vp3_px)


def _solve(pts_px, w, h, ax1=1, ax2=5, origin_px=None, cam_back=None, vp3_px=None):
    """Run the full 2VP solve from pixel coordinates.

    pts_px: list of 8 points [(x,y), ...] — VP1 line1 start/end, line2 start/end,
            then VP2 line1 start/end, line2 start/end. All in pixel coords (top-left origin).
    origin_px: optional (x, y) pixel of the world-origin control point. If None,
               defaults to the intersection of VP1 line 0 and VP2 line 0.
    cam_back: optional distance (world units) from camera to world origin along
              the view ray. If None, matches Flame's native 1-unit=1-pixel scale
              by setting cam_back = h / (2·tan(vfov/2)), which places world origin
              at the distance where image-height pixels exactly fill the frame.
    Returns dict with position, rotation, focal_mm, hfov_deg or None on failure.

    Writes a complete math trace to /tmp/forge_camera_match_trace.json each call.
    """
    _ensure_forge_env()
    import numpy as np
    import time

    SENSOR_MM = 36.0
    _AX = {0:[1,0,0],1:[-1,0,0],2:[0,1,0],3:[0,-1,0],4:[0,0,1],5:[0,0,-1]}
    _AX_NAMES = ["+X","-X","+Y","-Y","+Z","-Z"]
    # cam_back default is computed below once we know vfov — defer resolution.

    trace = {
        "timestamp": time.time(),
        "inputs": {
            "image_size": [w, h],
            "aspect": w / h,
            "ax1": ax1, "ax1_name": _AX_NAMES[ax1],
            "ax2": ax2, "ax2_name": _AX_NAMES[ax2],
            "sensor_mm": SENSOR_MM,
            "points_px": [list(map(float, p)) for p in pts_px],
            "origin_px": None if origin_px is None else [float(origin_px[0]), float(origin_px[1])],
            "cam_back_requested": None if cam_back is None else float(cam_back),
        },
        "stages": {},
        "result": None,
        "error": None,
    }

    def px_to_ip(px, py):
        rx, ry = px / w, py / h
        a = w / h
        if a >= 1.0:
            return np.array([-1.0 + 2.0*rx, (1.0 - 2.0*ry) / a])
        else:
            return np.array([(-1.0 + 2.0*rx) * a, 1.0 - 2.0*ry])

    def line_isect(p1, p2, p3, p4):
        x1,y1 = p1; x2,y2 = p2; x3,y3 = p3; x4,y4 = p4
        d = (x1-x2)*(y3-y4) - (y1-y2)*(x3-x4)
        if abs(d) < 1e-12: return None
        t = ((x1-x3)*(y3-y4) - (y1-y3)*(x3-x4)) / d
        return np.array([x1+t*(x2-x1), y1+t*(y2-y1)])

    def ortho_proj(pt, a, b):
        d = b - a; s = np.dot(d, d)
        if s < 1e-24: return a.copy()
        return a + (np.dot(pt-a, d)/s) * d

    ip = [px_to_ip(p[0], p[1]) for p in pts_px]
    trace["stages"]["image_plane_points"] = [p.tolist() for p in ip]

    vp1 = line_isect(ip[0], ip[1], ip[2], ip[3])
    vp2 = line_isect(ip[4], ip[5], ip[6], ip[7])
    trace["stages"]["vp1_imageplane"] = None if vp1 is None else vp1.tolist()
    trace["stages"]["vp2_imageplane"] = None if vp2 is None else vp2.tolist()
    # VP positions in pixel coords too (more intuitive)
    def ip_to_px(ip_pt):
        a = w / h
        if a >= 1.0:
            rx = (ip_pt[0] + 1.0) / 2.0
            ry = (1.0 - ip_pt[1] * a) / 2.0
        else:
            rx = (ip_pt[0] / a + 1.0) / 2.0
            ry = (1.0 - ip_pt[1]) / 2.0
        return [rx * w, ry * h]
    trace["stages"]["vp1_px"] = None if vp1 is None else ip_to_px(vp1)
    trace["stages"]["vp2_px"] = None if vp2 is None else ip_to_px(vp2)

    if vp1 is None or vp2 is None:
        trace["error"] = "lines parallel — VP intersection failed"
        _write_trace(trace)
        return None

    # Principal point: orthocentre of VP1/VP2/VP3 triangle if a 3rd VP was
    # provided (fSpy's FromThirdVanishingPoint), else image centre.
    pp = np.array([0.0, 0.0])
    if vp3_px is not None:
        vp3 = px_to_ip(vp3_px[0], vp3_px[1])
        a, b = vp1[0], vp1[1]
        c, d = vp2[0], vp2[1]
        e, f = vp3[0], vp3[1]
        N = b*c + d*e + f*a - c*f - b*e - a*d
        if abs(N) > 1e-12:
            pp = np.array([
                ((d-f)*b*b + (f-b)*d*d + (b-d)*f*f + a*b*(c-e) + c*d*(e-a) + e*f*(a-c)) / N,
                ((e-c)*a*a + (a-e)*c*c + (c-a)*e*e + a*b*(f-d) + c*d*(b-f) + e*f*(d-b)) / N,
            ])
        trace["stages"]["vp3_imageplane"] = vp3.tolist()
        trace["stages"]["principal_point_imageplane"] = pp.tolist()
        trace["stages"]["principal_point_px"] = ip_to_px(pp)

    # Focal length
    puv = ortho_proj(pp, vp1, vp2)
    fsq = np.linalg.norm(vp2-puv)*np.linalg.norm(vp1-puv) - np.linalg.norm(pp-puv)**2
    trace["stages"]["pp_orthoproj"] = puv.tolist()
    trace["stages"]["f_squared"] = float(fsq)
    if fsq <= 0:
        trace["error"] = f"focal_sq <= 0 ({fsq}); camera setup geometrically impossible"
        _write_trace(trace)
        return None
    f = float(np.sqrt(fsq))
    trace["stages"]["f_relative"] = f

    # Rotation
    u = np.array([vp1[0]-pp[0], vp1[1]-pp[1], -f])
    v = np.array([vp2[0]-pp[0], vp2[1]-pp[1], -f])
    u /= np.linalg.norm(u); v /= np.linalg.norm(v)
    ww = np.cross(u, v); ww /= np.linalg.norm(ww)
    R = np.column_stack([u, v, ww])
    trace["stages"]["u_ax1_in_cam"] = u.tolist()
    trace["stages"]["v_ax2_in_cam"] = v.tolist()
    trace["stages"]["ww_cross"] = ww.tolist()
    trace["stages"]["R_columns_uvw"] = R.tolist()

    # Axis assignment
    r1 = np.array(_AX[ax1], dtype=float)
    r2 = np.array(_AX[ax2], dtype=float)
    A = np.vstack([r1, r2, np.cross(r1, r2)])
    trace["stages"]["r1_world"] = r1.tolist()
    trace["stages"]["r2_world"] = r2.tolist()
    trace["stages"]["A_matrix"] = A.tolist()

    view_rot = R @ A
    cam_rot = np.linalg.inv(view_rot)
    trace["stages"]["view_rot_world_to_cam"] = view_rot.tolist()
    trace["stages"]["cam_rot_cam_to_world"] = cam_rot.tolist()

    # Flame's identity camera looks -Z_local (verified empirically via top view:
    # a fresh camera at (0,0,+Z) with rotation (0,0,0) points toward origin at
    # Z=0, which is the -Z_world direction). Matches OpenGL/solver convention,
    # so no local-frame flip is needed here — push cam_rot directly. The Euler
    # decomposition below still uses Flame's inverted-XYZ composition.
    cam_rot_flame = cam_rot
    trace["stages"]["cam_rot_flame_convention"] = cam_rot_flame.tolist()

    # Euler angles — Flame's Action camera uses R = Rz(rz) · Ry(-ry) · Rx(-rx)
    # internally: ZYX order with X and Y signs inverted. Verified empirically
    # 2026-04-16 against the test.fspy fixture: pushing the ZYX-decomposed
    # angles aligns the rendered surface to the wall to single-degree precision,
    # while the previous XYZ-decomposed angles left a ~13° Z residual that
    # required an external axis-rotation fix to compensate.
    #
    # Substituting α=-rx, β=-ry, γ=rz reduces to the standard ZYX-positive
    # decomposition R = Rz(γ)·Ry(β)·Rx(α):
    #   α = atan2(R[2,1], R[2,2])
    #   β = arcsin(-R[2,0])
    #   γ = atan2(R[1,0], R[0,0])
    # Then rx = -α, ry = -β, rz = γ.
    cb = np.sqrt(cam_rot_flame[0,0]**2 + cam_rot_flame[1,0]**2)
    gimbal = cb <= 1e-6
    if not gimbal:
        rx = -np.arctan2( cam_rot_flame[2,1], cam_rot_flame[2,2])
        ry = -np.arcsin(-cam_rot_flame[2,0])
        rz =  np.arctan2( cam_rot_flame[1,0], cam_rot_flame[0,0])
    else:
        # ry = ±90° → α and γ are coupled. Set rx = 0, derive rz from upper-left.
        rx = 0.0
        ry = -np.arcsin(-cam_rot_flame[2,0])
        rz =  np.arctan2(-cam_rot_flame[0,1], cam_rot_flame[1,1])
    eul = np.degrees(np.array([rx, ry, rz]))
    trace["stages"]["gimbal_lock"] = bool(gimbal)
    trace["stages"]["flame_euler_deg"] = eul.tolist()

    # Sanity: reconstruct R from Euler using Flame's ZYX-with-X,Y-negated
    # convention and verify it round-trips to cam_rot_flame.
    def _rx(a): c,s=np.cos(a),np.sin(a); return np.array([[1,0,0],[0,c,-s],[0,s,c]])
    def _ry(a): c,s=np.cos(a),np.sin(a); return np.array([[c,0,s],[0,1,0],[-s,0,c]])
    def _rz(a): c,s=np.cos(a),np.sin(a); return np.array([[c,-s,0],[s,c,0],[0,0,1]])
    R_recon = _rz(rz) @ _ry(-ry) @ _rx(-rx)
    trace["stages"]["R_recon_from_euler"] = R_recon.tolist()
    trace["stages"]["R_recon_matches_cam_rot_flame"] = bool(np.allclose(R_recon, cam_rot_flame, atol=1e-6))

    # Project world axes through the solved camera back to pixel coords — this
    # is the acid test: does +ax1_world land near the user's VP1 pixel?
    def project_world_dir(d_world):
        v_cam = cam_rot.T @ np.asarray(d_world, dtype=float)
        if v_cam[2] >= 0:
            return {"cam_dir": v_cam.tolist(), "projects": "BEHIND camera"}
        # Pinhole: ip = pp + f * (X,Y) / (-Z). The pp offset matters whenever
        # the principal point isn't at image centre (FromThirdVanishingPoint).
        ipx = pp[0] + v_cam[0] / -v_cam[2] * f
        ipy = pp[1] + v_cam[1] / -v_cam[2] * f
        # Convert back to pixel
        a = w / h
        if a >= 1.0:
            px = (ipx + 1.0) / 2.0 * w
            py = (1.0 - ipy * a) / 2.0 * h
        else:
            px = (ipx / a + 1.0) / 2.0 * w
            py = (1.0 - ipy) / 2.0 * h
        return {"cam_dir": v_cam.tolist(), "image_plane": [ipx, ipy], "pixel": [px, py]}

    proj = {
        "+X": project_world_dir((1, 0, 0)),
        "-X": project_world_dir((-1, 0, 0)),
        "+Y": project_world_dir((0, 1, 0)),
        "-Y": project_world_dir((0, -1, 0)),
        "+Z": project_world_dir((0, 0, 1)),
        "-Z": project_world_dir((0, 0, -1)),
    }
    trace["stages"]["world_axis_projections"] = proj

    hfov = 2.0 * np.arctan(1.0 / f)
    aspect = w / h
    vfov = 2.0 * np.arctan(np.tan(hfov/2.0) / aspect)
    focal_mm = f * SENSOR_MM / 2.0

    # Default cam_back matches Flame's native scale: 1 unit ≈ 1 image pixel.
    # A fresh Flame camera sits at distance where image_height pixels exactly
    # fill the vertical FOV. At that distance, default-sized geometry renders
    # at the expected scale instead of appearing microscopic (10-unit scene)
    # or enormous (pixel-unit scene viewed up close).
    if cam_back is None:
        cam_back = h / (2.0 * np.tan(vfov / 2.0))
    trace["inputs"]["cam_back_resolved"] = float(cam_back)

    # Origin control point: default to intersection of first line of each VP pair
    # (image-plane coords). Fallback to principal point if parallel/missing.
    if origin_px is None:
        isect_ip = line_isect(ip[0], ip[1], ip[4], ip[5])
        if isect_ip is None:
            origin_ip = np.array([0.0, 0.0])
        else:
            origin_ip = isect_ip
        origin_px_resolved = ip_to_px(origin_ip)
    else:
        origin_px_resolved = [float(origin_px[0]), float(origin_px[1])]
        origin_ip = px_to_ip(origin_px_resolved[0], origin_px_resolved[1])

    # Back-project origin pixel to a camera-space point. Match fSpy's convention:
    # origin sits at *perpendicular* depth cam_back (z_cam = -cam_back), not
    # Euclidean distance — fSpy uses origin3D = k·(ox-pp.x, oy-pp.y, -1)·scale
    # with k = tan(hfov/2) = 1/f, which simplifies to:
    #     origin_in_cam = (cam_back / f) · (ox-pp.x, oy-pp.y, -f)
    # → x = (cam_back/f)·(ox-pp.x), y = (cam_back/f)·(oy-pp.y), z = -cam_back.
    ray_cam = np.array([origin_ip[0] - pp[0], origin_ip[1] - pp[1], -f], dtype=float)
    origin_in_cam = (cam_back / f) * ray_cam
    # If cam is at world position P and world origin is at offset O in cam space,
    # then (0,0,0) = P + cam_rot @ O  →  P = -cam_rot @ O.
    cam_pos = -cam_rot @ origin_in_cam
    trace["stages"]["origin_px_resolved"] = list(origin_px_resolved)
    trace["stages"]["origin_imageplane"] = origin_ip.tolist()
    trace["stages"]["origin_in_cam"] = origin_in_cam.tolist()
    trace["stages"]["cam_position_world"] = cam_pos.tolist()

    result = {
        "position": (float(cam_pos[0]), float(cam_pos[1]), float(cam_pos[2])),
        "rotation": (float(eul[0]), float(eul[1]), float(eul[2])),
        "focal_mm": float(focal_mm),
        "film_back_mm": float(SENSOR_MM),
        "hfov_deg": float(np.degrees(hfov)),
        "vfov_deg": float(np.degrees(vfov)),
        # For viewport projection helpers (plane overlay etc.)
        "cam_rot": cam_rot.tolist(),
        "f_relative": f,
        "ax1": ax1, "ax2": ax2,
        "origin_px": list(origin_px_resolved),
        "cam_back_dist": float(cam_back),
        # Principal point in pixels — only populated when VP3 was supplied
        # (FromThirdVanishingPoint mode). Otherwise None (PP at image centre).
        "principal_point_px": ip_to_px(pp) if vp3_px is not None else None,
    }
    trace["result"] = result
    _write_trace(trace)
    return result


# =========================================================================
# Export helper
# =========================================================================

_JPEG_PRESET = "/opt/Autodesk/shared/export/presets/file_sequence/JPEG_CameraMatch.xml"

class _NoHooks(object):
    def preExport(self, *a, **k): pass
    def postExport(self, *a, **k): pass
    def preExportSequence(self, *a, **k): pass
    def postExportSequence(self, *a, **k): pass
    def preExportAsset(self, *a, **k): pass
    def postExportAsset(self, *a, **k): pass
    def exportOverwriteFile(self, *a, **k): return "overwrite"

_WIRETAP_RW_FRAME = "/opt/Autodesk/wiretap/tools/current/wiretap_rw_frame"

# Preview colour pipeline. Uses Flame's shipped ACES 2.0 config so the
# preview goes through a real RRT+ODT — highlights roll off softly instead
# of clipping to pure white, which matters for marking VP lines against
# bright skies / blown windows. The sRGB display + ACES 2.0 SDR 100 nits
# view matches a standard desktop monitor.
_OCIO_CONFIG_PATH = (
    "/opt/Autodesk/colour_mgmt/configs/flame_configs/2026.0/"
    "aces2.0_config/config.ocio"
)
_OCIO_DISPLAY = "sRGB - Display"
_OCIO_VIEW = "ACES 2.0 - SDR 100 nits (Rec.709)"
_OCIO_PASSTHROUGH = "Display passthrough (sRGB / already encoded)"
_OCIO_SOURCE_OPTIONS = [
    _OCIO_PASSTHROUGH,        # data is already display-encoded — no transform
    "ARRI LogC4",
    "ARRI LogC3 (EI800)",
    "Linear ARRI Wide Gamut 4",
    "Linear ARRI Wide Gamut 3",
    "ACEScg",
    "ACES2065-1",
    "Linear Rec.709 (sRGB)",
    "sRGB Encoded Rec.709 (sRGB)",
]
_OCIO_DEFAULT_SOURCE = _OCIO_PASSTHROUGH


def _clip_wiretap_colour_space(clip):
    """Read the wiretap-reported colour space string for a PyClipNode (or its
    inner PyClip). Returns None on failure. Cheap — opens its own short-lived
    Wiretap session."""
    try:
        py_clip = clip.clip if hasattr(clip, "clip") else clip
        node_id = py_clip.get_wiretap_node_id()
    except Exception:
        return None
    if not node_id:
        return None
    try:
        sdk = "/opt/Autodesk/wiretap/tools/current/python"
        if sdk not in sys.path:
            sys.path.insert(0, sdk)
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


def _map_wiretap_cs_to_dropdown(wt_cs):
    """Best-effort map from Wiretap's colour space string to one of the
    _OCIO_SOURCE_OPTIONS entries. Returns the passthrough option for any
    obviously display-encoded source (sRGB / Rec.709 video / unknown)."""
    if not wt_cs:
        return _OCIO_PASSTHROUGH
    s = wt_cs.lower()
    if "logc4" in s:
        return "ARRI LogC4"
    if "logc3" in s or "logc " in s or s.startswith("logc"):
        return "ARRI LogC3 (EI800)"
    if "arri wide gamut 4" in s and "log" not in s:
        return "Linear ARRI Wide Gamut 4"
    if "arri wide gamut 3" in s and "log" not in s:
        return "Linear ARRI Wide Gamut 3"
    if "acescg" in s:
        return "ACEScg"
    if "aces2065" in s or "ap0" in s:
        return "ACES2065-1"
    if ("linear" in s and ("rec.709" in s or "rec709" in s or "srgb" in s)):
        return "Linear Rec.709 (sRGB)"
    # Display-encoded / video — no scene-referred transform needed.
    return _OCIO_PASSTHROUGH
_OCIO_CFG_CACHE = {"cfg": None, "loaded": False}
_OCIO_PROC_CACHE = {}


def _get_ocio_cfg():
    if _OCIO_CFG_CACHE["loaded"]:
        return _OCIO_CFG_CACHE["cfg"]
    _OCIO_CFG_CACHE["loaded"] = True
    try:
        import PyOpenColorIO as OCIO
        _OCIO_CFG_CACHE["cfg"] = OCIO.Config.CreateFromFile(_OCIO_CONFIG_PATH)
    except Exception as e:
        print("OCIO config load failed:", e)
        _OCIO_CFG_CACHE["cfg"] = None
    return _OCIO_CFG_CACHE["cfg"]


def _get_ocio_processor(src_cs):
    """CPU processor: src colorspace → display/view with tonemapped rolloff.
    Cached per source. Uses DisplayViewTransform so the ACES RRT+ODT is
    actually applied — a plain getProcessor(src, dst) would just colour-space
    convert and hard-clip."""
    if src_cs in _OCIO_PROC_CACHE:
        return _OCIO_PROC_CACHE[src_cs]
    cfg = _get_ocio_cfg()
    proc = None
    if cfg is not None:
        try:
            import PyOpenColorIO as OCIO
            dvt = OCIO.DisplayViewTransform()
            dvt.setSrc(src_cs)
            dvt.setDisplay(_OCIO_DISPLAY)
            dvt.setView(_OCIO_VIEW)
            proc = cfg.getProcessor(dvt).getDefaultCPUProcessor()
        except Exception as e:
            print(f"OCIO DVT {src_cs} -> {_OCIO_DISPLAY}/{_OCIO_VIEW} failed: {e}")
            proc = None
    _OCIO_PROC_CACHE[src_cs] = proc
    return proc


def _read_source_frame(clip, target_frame=None, source_colourspace=None):
    """Read one frame of a clip using Flame's Wiretap CLI.

    The source codec may be Sony/ARRI-proprietary MXF that cv2/ffmpeg can't
    decode, so we go through Flame's decoder via the wiretap_rw_frame tool:
    it pulls a single frame by wiretap node id, writes raw pixels (or a
    standard image container if the source is a soft-imported still) to
    disk, and we decode that.

    When source_colourspace is set (e.g. "ARRI LogC4"), the float pixel
    buffer is run through an OCIO transform to sRGB for a faithful preview.
    When None or "Gamma 2.2 (no OCIO)", falls back to a naive pow(x, 1/2.2)
    display encode.

    Returns (img_rgb_np_uint8, width, height) or (None, None, None).
    Frame indexing: target_frame is in clip-source frame numbering
    (e.g. 1001..4667 for start_frame=1001); we convert to the 0-based wiretap
    frame_index by subtracting start_frame.
    """
    import os
    import subprocess
    import tempfile
    import numpy as np
    import cv2

    if not os.path.isfile(_WIRETAP_RW_FRAME):
        print("wiretap_rw_frame not found:", _WIRETAP_RW_FRAME)
        return None, None, None

    try:
        py_clip = clip.clip
        node_id = py_clip.get_wiretap_node_id()
    except Exception as e:
        print("get_wiretap_node_id failed:", e)
        return None, None, None
    if not node_id:
        print("Clip has empty wiretap node id — is it in the Media Panel?")
        return None, None, None

    try:
        duration = int(clip.duration.get_value())
        start_frame = int(py_clip.start_frame)
    except Exception:
        duration, start_frame = 1, 1

    if target_frame is None:
        target_frame = start_frame
    target_frame = max(start_frame, min(start_frame + duration - 1, int(target_frame)))
    frame_index = target_frame - start_frame  # 0-based

    try:
        res = clip.resolution.get_value()
        w, h, bit_depth = int(res.width), int(res.height), int(res.bit_depth)
    except Exception as e:
        print("resolution read failed:", e)
        return None, None, None

    with tempfile.TemporaryDirectory(prefix="camera_match_wt_") as tmp:
        out_base = os.path.join(tmp, "frame")
        cmd = [_WIRETAP_RW_FRAME, "-n", node_id, "-i", str(frame_index), "-f", out_base]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        except subprocess.TimeoutExpired:
            print("wiretap_rw_frame timed out")
            return None, None, None
        except Exception as e:
            print("wiretap_rw_frame exec error:", e)
            return None, None, None

        files = [f for f in os.listdir(tmp) if f.startswith("frame")]
        if not files:
            print("wiretap_rw_frame wrote no output. stdout:", r.stdout.strip(),
                  "stderr:", r.stderr.strip())
            return None, None, None
        raw = open(os.path.join(tmp, files[0]), "rb").read()

    # Magic-byte sniff: wiretap may hand back a standard image container for
    # soft-imported stills (tiff/png/jpg/exr/dpx), or a raw pixel buffer for
    # transcoded / proxy-rendered sources.
    head = raw[:8]
    fmt = None
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        fmt = "png"
    elif head[:2] == b"\xff\xd8":
        fmt = "jpg"
    elif head[:4] in (b"II*\x00", b"MM\x00*"):
        fmt = "tiff"
    elif head[:4] == b"\x76\x2f\x31\x01":
        fmt = "exr"
    elif head[:4] in (b"SDPX", b"XPDS"):
        fmt = "dpx"

    if fmt is not None:
        arr = np.frombuffer(raw, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_UNCHANGED)
        if img is None:
            print(f"cv2.imdecode failed for container fmt={fmt}")
            return None, None, None
        if img.ndim == 2:
            img = np.stack([img, img, img], axis=-1)
        if img.shape[-1] == 4:
            img = img[..., :3]
        if img.dtype == np.uint16:
            img = (img // 257).astype(np.uint8)
        elif img.dtype in (np.float32, np.float64):
            img = (np.clip(img, 0.0, 1.0) * 255).astype(np.uint8)
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        return rgb, int(rgb.shape[1]), int(rgb.shape[0])

    # Raw pixel buffer. The file observed to be `header + W*H*C*bytes_per_sample`;
    # slicing the tail gives the pixel payload regardless of header size.
    channels = 3  # Flame wiretap delivers RGB for ClipFormat(RGB)
    if bit_depth == 32:
        dtype = np.float32
    elif bit_depth == 16:
        # Could be half-float or uint16; default to half since Flame's internal
        # scene bit-depth is usually float. If that's wrong for a given clip
        # we'll see it flipped saturated vs dim and can revisit.
        dtype = np.float16
    elif bit_depth == 8:
        dtype = np.uint8
    else:
        print(f"Unhandled wiretap raw bit_depth: {bit_depth}")
        return None, None, None
    sample_size = np.dtype(dtype).itemsize
    expected = w * h * channels * sample_size
    if len(raw) < expected:
        print(f"Raw buffer too small: got {len(raw)} bytes, expected ≥ {expected}")
        return None, None, None
    payload = raw[-expected:]
    arr = np.frombuffer(payload, dtype=dtype).reshape(h, w, channels)

    # Wiretap's raw buffer is bottom-up (OpenGL convention) AND delivered in
    # GBR channel order despite the "rgb_float_le" format tag (empirically
    # verified: full reverse left G/B swapped, while picking [2,0,1] gives
    # correct R/G/B for Qt's Format_RGB888). Flip vertically and re-order
    # channels to RGB in one shot.
    arr = np.ascontiguousarray(arr[::-1][..., [2, 0, 1]])

    # uint8 path — source was already 8-bit, almost always display-encoded
    # (Rec.709 video / sRGB JPEG). Pass through directly.
    if arr.dtype == np.uint8:
        return arr, w, h

    # Float path. Three flavors:
    #   - Display passthrough → clip to 0..1 and quantise; data is already
    #     in display-referred form, no transform should touch it.
    #   - Known OCIO source → DisplayViewTransform via ACES 2.0 SDR view
    #     (gives soft highlight rolloff, gamut compression).
    #   - OCIO unavailable / processor missing → same passthrough behavior.
    a = np.ascontiguousarray(arr.astype(np.float32))
    is_passthrough = (
        source_colourspace is None or source_colourspace == _OCIO_PASSTHROUGH
    )
    if not is_passthrough:
        proc = _get_ocio_processor(source_colourspace)
        if proc is not None:
            try:
                proc.applyRGB(a)
                rgb = (np.clip(a, 0.0, 1.0) * 255.0).astype(np.uint8)
                return rgb, w, h
            except Exception as e:
                print(f"OCIO applyRGB failed for {source_colourspace}: {e}; "
                      "falling back to passthrough")
    a = np.clip(a, 0.0, 1.0)
    rgb = (a * 255.0).astype(np.uint8)
    return rgb, w, h


# =========================================================================
# PySide2 Camera Match Window
# =========================================================================

def _open_camera_match(clip):
    _ensure_forge_env()
    import flame
    import os
    import shutil
    import cv2
    from PySide6 import QtWidgets, QtGui, QtCore

    # Probe Wiretap for the clip's tagged colour space and pick the matching
    # source-space option for the OCIO transform. Falls back to display
    # passthrough when the tag is missing or already display-encoded.
    wt_cs = _clip_wiretap_colour_space(clip)
    initial_source_cs = _map_wiretap_cs_to_dropdown(wt_cs)

    # Read one frame directly from the clip's source media. Defaults to the
    # clip's first source frame; user flips frames via the side-panel spinner.
    img_rgb, img_w, img_h = _read_source_frame(
        clip, source_colourspace=initial_source_cs)
    if img_rgb is None:
        flame.messages.show_in_dialog(
            title="Camera Match",
            message="Could not read frame from clip source. "
                    "Check the clip's media path is accessible.",
            type="error", buttons=["OK"])
        return
    tmp_dir = None  # no longer needed — we read media directly off disk

    HANDLE_RADIUS = 7

    # Axis colors — RGB = XYZ (positive = bright, negative = dim).
    # Order matches _AX_LABELS: +X -X +Y -Y +Z -Z
    _AXIS_RGB = [
        (235,  80,  80),   # +X bright red
        (160,  60,  60),   # -X dim red
        ( 90, 215, 110),   # +Y bright green
        ( 60, 150,  75),   # -Y dim green
        ( 90, 150, 255),   # +Z bright blue
        ( 55, 105, 190),   # -Z dim blue
    ]
    def _axis_color(idx, alpha=255):
        r, g, b = _AXIS_RGB[idx]
        return QtGui.QColor(r, g, b, alpha)

    def _axis_swatch(idx, size=14):
        pix = QtGui.QPixmap(size, size)
        pix.fill(QtCore.Qt.transparent)
        pa = QtGui.QPainter(pix)
        pa.setRenderHint(QtGui.QPainter.Antialiasing)
        pa.setBrush(_axis_color(idx))
        pa.setPen(QtGui.QPen(QtGui.QColor(0, 0, 0, 180), 1))
        pa.drawRoundedRect(1, 1, size - 2, size - 2, 2, 2)
        pa.end()
        return QtGui.QIcon(pix)

    # FORGE palette — matches forge_cv_align.
    _FORGE_SS = (
        "QDialog { background: #282c34; }"
        "QWidget#sidePanel { background: #282c34; }"
        "QGroupBox { color: #888; font-size: 11px; font-weight: bold; "
        "  border: 1px solid #3a3f4f; border-radius: 3px; "
        "  margin-top: 12px; padding: 12px 10px 10px 10px; }"
        "QGroupBox::title { subcontrol-origin: margin; left: 10px; "
        "  padding: 0 4px; color: #888; }"
        "QLabel { color: #ccc; font-size: 12px; }"
        "QLabel#fieldLabel { color: #888; font-size: 11px; }"
        "QLabel#value { color: #ccc; font-size: 12px; font-family: 'JetBrains Mono', 'SF Mono', monospace; }"
        "QLabel#valueDim { color: #666; font-size: 12px; font-family: 'JetBrains Mono', 'SF Mono', monospace; }"
        "QLabel#statusOK { color: #7bd37b; font-size: 11px; font-weight: bold; }"
        "QLabel#statusBad { color: #d37b7b; font-size: 11px; font-weight: bold; }"
        "QComboBox { background: #1e2028; color: #ccc; "
        "  border: 1px solid #555; border-radius: 3px; "
        "  padding: 4px 8px; font-size: 12px; }"
        "QComboBox:focus { border: 1px solid #E87E24; }"
        "QComboBox QAbstractItemView { background: #1e2028; color: #ccc; "
        "  selection-background-color: #E87E24; }"
        "QCheckBox { color: #ccc; font-size: 12px; }"
        "QCheckBox::indicator { width: 14px; height: 14px; }"
        "QSlider::groove:horizontal { border: 1px solid #3a3f4f; "
        "  height: 4px; background: #1e2028; border-radius: 2px; }"
        "QSlider::handle:horizontal { background: #E87E24; "
        "  border: none; width: 14px; margin: -5px 0; border-radius: 7px; }"
        "QPushButton { background: #333; color: #ccc; border: 1px solid #555; "
        "  border-radius: 3px; padding: 6px 12px; font-size: 12px; }"
        "QPushButton:hover:enabled { background: #444; }"
        "QPushButton:disabled { background: #2a2d36; color: #666; border: 1px solid #333; }"
        "QPushButton#primary { background: #E87E24; color: #fff; border: none; "
        "  font-weight: bold; padding: 8px 12px; }"
        "QPushButton#primary:hover:enabled { background: #f59035; }"
        "QPushButton#primary:disabled { background: #2a2d36; color: #555; border: 1px solid #333; }"
        "QFrame#sep { color: #3a3f4f; }"
    )

    class ImageWidget(QtWidgets.QWidget):
        """Image display with draggable VP line endpoints."""

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setMinimumSize(640, 480)
            self.setMouseTracking(True)

            # VP line endpoints in normalized coords (0-1, top-left origin).
            # Layout (16 points):
            #   indices  0..5  → VP1 lines 0,1,2
            #   indices  6..11 → VP2 lines 0,1,2
            #   indices 12..15 → VP3 lines 0,1   (only used when self.use_vp3)
            # Lines 3 (VP1) and 6 (VP2) are only used when self.three_lines.
            self.points = [
                # VP1: line 0, 1, 2
                [0.15, 0.35], [0.85, 0.40],
                [0.15, 0.65], [0.85, 0.60],
                [0.15, 0.50], [0.85, 0.50],
                # VP2: line 0, 1, 2
                [0.35, 0.15], [0.40, 0.85],
                [0.65, 0.15], [0.60, 0.85],
                [0.50, 0.15], [0.50, 0.85],
                # VP3: line 0, 1 (no third line — PP fit needs only one VP3)
                [0.30, 0.55], [0.10, 0.85],
                [0.70, 0.55], [0.90, 0.85],
            ]

            self.dragging = -1
            # Origin control point: normalized widget coords or None (= auto-place
            # at intersection of VP1 line-0 and VP2 line-0 on each solve).
            self.origin_norm = None
            self.dragging_origin = False
            self.image_opacity = 0.5
            self.show_extended = True
            self.show_plane = True
            self.three_lines = False  # when True, 3 lines per VP with least-squares VP fit
            self.use_vp3 = False      # when True, VP3 lines drive the principal point (orthocentre)
            self.quad_mode = False    # when True, VP2 lines synthesized from VP1 endpoints (planar quad)
            self.solve_result = None

            # Axis assignments (index into _AX_LABELS); updated from the window.
            # Default to Flame-friendly: VP1 = -X, VP2 = -Y.
            self.ax1 = 1  # VP1 -> -X
            self.ax2 = 3  # VP2 -> -Y

            self._qimage = QtGui.QImage(
                img_rgb.data, img_w, img_h, img_w * 3,
                QtGui.QImage.Format_RGB888
            ).copy()  # copy so numpy can be freed

        def reload_image(self, img_rgb_np):
            """Swap the backing image (e.g. when the user switches frames).
            Assumes the new image has the same dimensions as the original —
            resolutions don't change frame-to-frame within a clip."""
            self._qimage = QtGui.QImage(
                img_rgb_np.data, img_w, img_h, img_w * 3,
                QtGui.QImage.Format_RGB888
            ).copy()
            self.update()

        def _norm_to_widget(self, nx, ny):
            """Convert normalized image coords to widget coords."""
            r = self._image_rect()
            return r.x() + nx * r.width(), r.y() + ny * r.height()

        def _widget_to_norm(self, wx, wy):
            """Convert widget coords to normalized image coords."""
            r = self._image_rect()
            return (wx - r.x()) / r.width(), (wy - r.y()) / r.height()

        def _image_rect(self):
            """Compute the image rect fitted to widget with correct aspect."""
            w_asp = self.width() / self.height()
            i_asp = img_w / img_h
            if w_asp > i_asp:
                h = self.height()
                w = h * i_asp
                x = (self.width() - w) / 2
                y = 0
            else:
                w = self.width()
                h = w / i_asp
                x = 0
                y = (self.height() - h) / 2
            return QtCore.QRectF(x, y, w, h)

        def _norm_to_px(self, nx, ny):
            """Convert normalized to actual image pixel coords."""
            return nx * img_w, ny * img_h

        def set_axes(self, ax1, ax2):
            self.ax1 = ax1
            self.ax2 = ax2
            self.update()

        def _active_lines(self):
            """Return (vp1_lines, vp2_lines, vp3_lines) as lists of (p0_px, p1_px)
            pairs based on three_lines / use_vp3 modes. Layout:
                points[0:6]   = VP1 (lines 0,1,2)
                points[6:12]  = VP2 (lines 0,1,2)
                points[12:16] = VP3 (lines 0,1)   — used iff self.use_vp3
            vp3_lines is None when use_vp3 is False.
            Quad mode is *not* applied here — _solve_lines synthesizes VP2 itself
            so the VP2 endpoints in self.points stay untouched while quad is on."""
            n = 3 if self.three_lines else 2
            def lines_for(base, count):
                out = []
                for k in range(count):
                    p0 = self.points[base + 2*k]
                    p1 = self.points[base + 2*k + 1]
                    out.append((self._norm_to_px(*p0), self._norm_to_px(*p1)))
                return out
            vp1 = lines_for(0, n)
            vp2 = lines_for(6, n)
            vp3 = lines_for(12, 2) if self.use_vp3 else None
            return vp1, vp2, vp3

        def run_solve(self, ax1, ax2):
            """Run solver with current point positions."""
            self.ax1 = ax1
            self.ax2 = ax2
            vp1_lines, vp2_lines, vp3_lines = self._active_lines()
            origin_px = None
            if self.origin_norm is not None:
                origin_px = self._norm_to_px(self.origin_norm[0], self.origin_norm[1])
            self.solve_result = _solve_lines(
                vp1_lines, vp2_lines, img_w, img_h, ax1, ax2,
                origin_px=origin_px, vp3_lines=vp3_lines, quad_mode=self.quad_mode)
            self.update()
            return self.solve_result

        def _origin_widget_pos(self):
            """Return origin handle position in widget coords, or None if unresolved."""
            if self.origin_norm is not None:
                return self._norm_to_widget(self.origin_norm[0], self.origin_norm[1])
            if self.solve_result is None:
                return None
            ox, oy = self.solve_result.get("origin_px", (img_w / 2, img_h / 2))
            return self._norm_to_widget(ox / img_w, oy / img_h)

        def reset_origin_to_auto(self):
            self.origin_norm = None
            if hasattr(self, "_auto_solve_cb"):
                self._auto_solve_cb()
            self.update()

        def _draw_direction_chevron(self, painter, sx, sy, ex, ey, color, t=0.62):
            """Inline chevron at fraction t along the line pointing start→end.

            Rendered mid-line so it's always visible (never occluded by endpoint
            handles or labels) and clearly communicates the positive-axis direction.
            """
            import math
            dx, dy = ex - sx, ey - sy
            length = math.hypot(dx, dy)
            if length < 20:
                return
            ux, uy = dx / length, dy / length
            px_, py_ = -uy, ux  # perpendicular

            # Chevron tip position
            tx = sx + ux * length * t
            ty = sy + uy * length * t
            size = 9  # length of each barb
            half = size * 0.75  # perpendicular half-width at the base

            # Base points behind tip
            ax_ = tx - ux * size + px_ * half
            ay_ = ty - uy * size + py_ * half
            bx_ = tx - ux * size - px_ * half
            by_ = ty - uy * size - py_ * half

            painter.setBrush(color)
            painter.setPen(QtCore.Qt.NoPen)
            tri = QtGui.QPolygonF([
                QtCore.QPointF(tx, ty),
                QtCore.QPointF(ax_, ay_),
                QtCore.QPointF(bx_, by_),
            ])
            painter.drawPolygon(tri)

        def _line_intersect(self, a0, a1, b0, b1):
            """Infinite-line intersection of two segments. Returns (x, y) or None."""
            x1, y1 = a0; x2, y2 = a1
            x3, y3 = b0; x4, y4 = b1
            d = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
            if abs(d) < 1e-6:
                return None
            t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / d
            return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))

        def _draw_label_pill(self, painter, cx, cy, text, color, primary=True):
            """Rounded-rect label centered at (cx, cy). primary=False = dim 'minus' side."""
            f = painter.font()
            f.setBold(primary)
            f.setPointSize(10 if primary else 9)
            painter.setFont(f)
            fm = QtGui.QFontMetrics(f)
            tw = fm.horizontalAdvance(text) + 10
            th = fm.height() + 2
            rect = QtCore.QRectF(cx - tw/2, cy - th/2, tw, th)
            bg = QtGui.QColor(20, 22, 28, 220 if primary else 160)
            border_col = color if primary else QtGui.QColor(color.red(), color.green(), color.blue(), 140)
            painter.setBrush(bg)
            painter.setPen(QtGui.QPen(border_col, 1))
            painter.drawRoundedRect(rect, 3, 3)
            painter.setPen(color if primary else QtGui.QColor(color.red(), color.green(), color.blue(), 180))
            painter.drawText(rect, QtCore.Qt.AlignCenter, text)

        def _draw_vp_pair(self, painter, base_idx, ax_idx):
            """Draw the VP lines for one VP (base_idx = 0 for VP1, 6 for VP2).

            Draws 2 or 3 lines based on self.three_lines mode. VP is the
            least-squares fit across all drawn lines (reduces to intersection
            for N=2).
            """
            import math
            color = _axis_color(ax_idx)
            color_dim = _axis_color(ax_idx, alpha=90)
            pen = QtGui.QPen()

            n_lines = 3 if self.three_lines else 2
            # Collect segment endpoints in widget coords
            segs = []
            for i in range(n_lines):
                s = self.points[base_idx + i*2]
                e = self.points[base_idx + i*2 + 1]
                sx, sy = self._norm_to_widget(s[0], s[1])
                ex, ey = self._norm_to_widget(e[0], e[1])
                segs.append(((sx, sy), (ex, ey)))

            # VP from least-squares fit over active lines (exact intersection for N=2)
            vp_px = _fit_vp([(self._norm_to_px(self.points[base_idx + i*2][0],
                                              self.points[base_idx + i*2][1]),
                             self._norm_to_px(self.points[base_idx + i*2 + 1][0],
                                              self.points[base_idx + i*2 + 1][1]))
                            for i in range(n_lines)])
            vp = None
            if vp_px is not None:
                vp = self._norm_to_widget(vp_px[0] / img_w, vp_px[1] / img_h)

            for i, (A, B) in enumerate(segs):
                sx, sy = A; ex, ey = B

                # Extended dashed line through both endpoints
                if self.show_extended:
                    pen.setColor(color_dim)
                    pen.setStyle(QtCore.Qt.DashLine)
                    pen.setWidth(1)
                    painter.setPen(pen)
                    painter.setBrush(QtCore.Qt.NoBrush)
                    dx, dy = ex - sx, ey - sy
                    length = math.hypot(dx, dy)
                    if length > 0:
                        scale = 5000 / length
                        painter.drawLine(
                            QtCore.QPointF(sx - dx*scale, sy - dy*scale),
                            QtCore.QPointF(ex + dx*scale, ey + dy*scale))

                # Solid segment
                pen.setColor(color)
                pen.setStyle(QtCore.Qt.SolidLine)
                pen.setWidth(2)
                painter.setPen(pen)
                painter.setBrush(QtCore.Qt.NoBrush)
                painter.drawLine(QtCore.QPointF(sx, sy), QtCore.QPointF(ex, ey))

                # Decide which end of the segment is toward the VP. If VP is
                # unknown (lines parallel), fall back to drag order (A→B).
                if vp is not None:
                    vx, vy = vp
                    # Project VP onto the line's direction axis
                    dx, dy = ex - sx, ey - sy
                    proj_end = (vx - sx) * dx + (vy - sy) * dy   # >0 → B side, <0 → A side
                    vp_is_B = proj_end > 0
                else:
                    vp_is_B = True

                if vp_is_B:
                    pos_x, pos_y = ex, ey   # toward VP
                    neg_x, neg_y = sx, sy   # away
                else:
                    pos_x, pos_y = sx, sy
                    neg_x, neg_y = ex, ey

                # Chevron mid-line pointing start→end, where start is the NEG end
                self._draw_direction_chevron(painter, neg_x, neg_y, pos_x, pos_y, color)

                # Labels on line 0 only (second line inherits the convention via chevron)
                if i == 0:
                    # Offset labels perpendicular so they don't sit on the handle
                    dx, dy = pos_x - neg_x, pos_y - neg_y
                    L = math.hypot(dx, dy) or 1.0
                    ux, uy = dx / L, dy / L
                    px_, py_ = -uy, ux
                    pos_label = _AX_LABELS[ax_idx]                     # e.g. "+X"
                    neg_label = _AX_LABELS[ax_idx ^ 1]                 # e.g. "-X"
                    # + pill: just outside the VP end
                    lx = pos_x + ux * 16 + px_ * 12
                    ly = pos_y + uy * 16 + py_ * 12
                    self._draw_label_pill(painter, lx, ly, pos_label, color, primary=True)
                    # − pill: just outside the opposite end (dimmer)
                    nlx = neg_x - ux * 16 + px_ * 12
                    nly = neg_y - uy * 16 + py_ * 12
                    self._draw_label_pill(painter, nlx, nly, neg_label, color, primary=False)

                # Per-line residual (3-line mode only — 2-line mode is exact).
                # Pixel-space perpendicular distance from the fitted VP to the
                # line through this segment's endpoints. Zero = line passes
                # exactly through VP; large = that line is "lying" to the fit.
                if self.three_lines and vp_px is not None:
                    p0_img = self._norm_to_px(*self.points[base_idx + i*2])
                    p1_img = self._norm_to_px(*self.points[base_idx + i*2 + 1])
                    resid = _line_residual_px(p0_img, p1_img, vp_px)
                    if resid < 1.0:
                        rtext = f"Δ{resid:.2f}px"
                    elif resid < 10.0:
                        rtext = f"Δ{resid:.1f}px"
                    else:
                        rtext = f"Δ{int(round(resid))}px"
                    # Place at t=0.35 along the segment with a perpendicular
                    # offset so it never collides with handles (t=0,1) or the
                    # chevron (t=0.62). Side chosen so we don't fight the +/−
                    # pills on line 0.
                    dx, dy = ex - sx, ey - sy
                    L = math.hypot(dx, dy) or 1.0
                    ux, uy = dx / L, dy / L
                    px_, py_ = -uy, ux
                    lx = sx + ux * L * 0.35 - px_ * 14
                    ly = sy + uy * L * 0.35 - py_ * 14
                    self._draw_label_pill(painter, lx, ly, rtext, color, primary=False)

        def _draw_quad_synth_pair(self, painter, ax_idx):
            """Draw VP2 as the two synthesized quad edges (A→C, B→D) where
            (A,B) is VP1.line0 and (C,D) is VP1.line1. No handles — the four
            points are owned by VP1; this just visualizes that they form a quad."""
            import math
            color = _axis_color(ax_idx)
            color_dim = _axis_color(ax_idx, alpha=90)
            pen = QtGui.QPen()

            A = self.points[0]; B = self.points[1]   # VP1 line0
            C = self.points[2]; D = self.points[3]   # VP1 line1
            edges = [(A, C), (B, D)]

            # Fitted VP from the synthesized lines (= solver's actual VP2)
            edges_px = [(self._norm_to_px(*p0), self._norm_to_px(*p1)) for p0, p1 in edges]
            vp_px = _fit_vp(edges_px)
            vp_w = self._norm_to_widget(vp_px[0] / img_w, vp_px[1] / img_h) if vp_px else None

            for i, (p0, p1) in enumerate(edges):
                sx, sy = self._norm_to_widget(p0[0], p0[1])
                ex, ey = self._norm_to_widget(p1[0], p1[1])

                if self.show_extended:
                    pen.setColor(color_dim)
                    pen.setStyle(QtCore.Qt.DashLine)
                    pen.setWidth(1)
                    painter.setPen(pen)
                    painter.setBrush(QtCore.Qt.NoBrush)
                    dx, dy = ex - sx, ey - sy
                    length = math.hypot(dx, dy)
                    if length > 0:
                        scale = 5000 / length
                        painter.drawLine(
                            QtCore.QPointF(sx - dx*scale, sy - dy*scale),
                            QtCore.QPointF(ex + dx*scale, ey + dy*scale))

                pen.setColor(color)
                pen.setStyle(QtCore.Qt.SolidLine)
                pen.setWidth(2)
                painter.setPen(pen)
                painter.drawLine(QtCore.QPointF(sx, sy), QtCore.QPointF(ex, ey))

                # Direction chevron pointing toward the VP
                if vp_w is not None:
                    vx, vy = vp_w
                    dx, dy = ex - sx, ey - sy
                    proj_end = (vx - sx) * dx + (vy - sy) * dy
                    vp_is_B = proj_end > 0
                else:
                    vp_is_B = True
                if vp_is_B:
                    pos_x, pos_y = ex, ey
                    neg_x, neg_y = sx, sy
                else:
                    pos_x, pos_y = sx, sy
                    neg_x, neg_y = ex, ey
                self._draw_direction_chevron(painter, neg_x, neg_y, pos_x, pos_y, color)

                # ax2 label pills on the first synthesized edge only
                if i == 0:
                    dx, dy = pos_x - neg_x, pos_y - neg_y
                    L = math.hypot(dx, dy) or 1.0
                    ux, uy = dx / L, dy / L
                    px_, py_ = -uy, ux
                    self._draw_label_pill(painter,
                                          pos_x + ux * 16 + px_ * 12,
                                          pos_y + uy * 16 + py_ * 12,
                                          _AX_LABELS[ax_idx], color, primary=True)
                    self._draw_label_pill(painter,
                                          neg_x - ux * 16 + px_ * 12,
                                          neg_y - uy * 16 + py_ * 12,
                                          _AX_LABELS[ax_idx ^ 1], color, primary=False)

        def _draw_vp3_pair(self, painter):
            """Draw the two VP3 lines used for the FromThirdVanishingPoint
            principal point. Neutral grey — VP3 has no axis assignment, it just
            constrains the orthocentre that becomes the optical centre."""
            import math
            color = QtGui.QColor(220, 220, 220)
            color_dim = QtGui.QColor(220, 220, 220, 90)
            pen = QtGui.QPen()
            for k in range(2):
                s = self.points[12 + 2*k]
                e = self.points[12 + 2*k + 1]
                sx, sy = self._norm_to_widget(s[0], s[1])
                ex, ey = self._norm_to_widget(e[0], e[1])
                if self.show_extended:
                    pen.setColor(color_dim)
                    pen.setStyle(QtCore.Qt.DashLine)
                    pen.setWidth(1)
                    painter.setPen(pen)
                    painter.setBrush(QtCore.Qt.NoBrush)
                    dx, dy = ex - sx, ey - sy
                    length = math.hypot(dx, dy)
                    if length > 0:
                        scale = 5000 / length
                        painter.drawLine(
                            QtCore.QPointF(sx - dx*scale, sy - dy*scale),
                            QtCore.QPointF(ex + dx*scale, ey + dy*scale))
                pen.setColor(color)
                pen.setStyle(QtCore.Qt.SolidLine)
                pen.setWidth(2)
                painter.setPen(pen)
                painter.drawLine(QtCore.QPointF(sx, sy), QtCore.QPointF(ex, ey))
            # PP marker if a solve has run with VP3 enabled
            if self.solve_result is not None:
                pp_px = self.solve_result.get("principal_point_px")
                if pp_px is not None:
                    wx, wy = self._norm_to_widget(pp_px[0] / img_w, pp_px[1] / img_h)
                    painter.setPen(QtGui.QPen(color, 1.5))
                    painter.setBrush(QtCore.Qt.NoBrush)
                    painter.drawEllipse(QtCore.QPointF(wx, wy), 6, 6)
                    painter.drawLine(QtCore.QPointF(wx - 9, wy), QtCore.QPointF(wx + 9, wy))
                    painter.drawLine(QtCore.QPointF(wx, wy - 9), QtCore.QPointF(wx, wy + 9))

        def _project_world(self, world_pt):
            """Project a 3D world point through the solved camera to widget coords.

            Returns (wx, wy) or None if the point is behind the camera.
            """
            if self.solve_result is None:
                return None
            import numpy as np
            cam_rot = np.asarray(self.solve_result["cam_rot"])
            cam_pos = np.asarray(self.solve_result.get("position", (0.0, 0.0, 0.0)))
            f_rel = self.solve_result["f_relative"]
            v = cam_rot.T @ (np.asarray(world_pt, dtype=float) - cam_pos)
            if v[2] >= -1e-6:
                return None
            # image-plane coords (solver convention: normalized where image spans
            # [-1, +1] horizontally for wide images)
            ipx = v[0] / -v[2] * f_rel
            ipy = v[1] / -v[2] * f_rel
            # Invert px_to_ip: convert from normalized image plane → pixel → widget
            a = img_w / img_h
            if a >= 1.0:
                nx = (ipx + 1.0) / 2.0
                ny = (1.0 - ipy * a) / 2.0
            else:
                nx = (ipx / a + 1.0) / 2.0
                ny = (1.0 - ipy) / 2.0
            return self._norm_to_widget(nx, ny)

        def _back_project_to_plane(self, px, py):
            """Back-project an image pixel through the solved camera onto the
            VP-defined plane through world origin. Returns (x,y,z) or None if
            the ray is parallel to the plane or hits behind the camera.
            """
            if self.solve_result is None:
                return None
            import numpy as np
            a = img_w / img_h
            rx, ry = px / img_w, py / img_h
            if a >= 1.0:
                ipx = -1.0 + 2.0 * rx
                ipy = (1.0 - 2.0 * ry) / a
            else:
                ipx = (-1.0 + 2.0 * rx) * a
                ipy = 1.0 - 2.0 * ry
            # Principal point in image plane (0,0 unless VP3/FromThirdVP active).
            pp_ipx, pp_ipy = 0.0, 0.0
            pp_px = self.solve_result.get("principal_point_px")
            if pp_px is not None:
                pp_rx, pp_ry = pp_px[0] / img_w, pp_px[1] / img_h
                if a >= 1.0:
                    pp_ipx = -1.0 + 2.0 * pp_rx
                    pp_ipy = (1.0 - 2.0 * pp_ry) / a
                else:
                    pp_ipx = (-1.0 + 2.0 * pp_rx) * a
                    pp_ipy = 1.0 - 2.0 * pp_ry
            f = self.solve_result["f_relative"]
            ray_cam = np.array([ipx - pp_ipx, ipy - pp_ipy, -f], dtype=float)
            cam_rot = np.asarray(self.solve_result["cam_rot"])
            cam_pos = np.asarray(self.solve_result["position"], dtype=float)
            ray_world = cam_rot @ ray_cam
            _AX = {0:[1,0,0],1:[-1,0,0],2:[0,1,0],3:[0,-1,0],4:[0,0,1],5:[0,0,-1]}
            n = np.cross(np.asarray(_AX[self.solve_result["ax1"]], dtype=float),
                         np.asarray(_AX[self.solve_result["ax2"]], dtype=float))
            nd = float(np.dot(n, ray_world))
            if abs(nd) < 1e-9:
                return None  # ray parallel to plane
            t = -float(np.dot(n, cam_pos)) / nd
            if t <= 0:
                return None  # behind camera
            hit = cam_pos + t * ray_world
            return (float(hit[0]), float(hit[1]), float(hit[2]))

        def endpoint_axes(self):
            """Enumerate all currently-active line endpoints back-projected onto
            the VP plane. Returns a list of (label, (x,y,z)) tuples, skipping
            any endpoint whose ray doesn't hit the plane in front of the camera.
            """
            if self.solve_result is None:
                return []
            n = 3 if self.three_lines else 2
            groups = [("vp1", 0, n)]
            if not self.quad_mode:
                groups.append(("vp2", 6, n))
            if self.use_vp3:
                groups.append(("vp3", 12, 2))
            out = []
            for tag, base, count in groups:
                for li in range(count):
                    for ei, suffix in ((0, "a"), (1, "b")):
                        idx = base + 2 * li + ei
                        px, py = self._norm_to_px(*self.points[idx])
                        hit = self._back_project_to_plane(px, py)
                        if hit is None:
                            continue
                        out.append((f"knot_{tag}_L{li}{suffix}", hit))
            return out

        def _plane_basis(self):
            """Return two unit world-axis vectors that span the VP-defined plane."""
            import numpy as np
            # Axis index // 2: 0 → X family, 1 → Y, 2 → Z
            ax_vecs = [
                np.array([1.0, 0.0, 0.0]),  # X
                np.array([0.0, 1.0, 0.0]),  # Y
                np.array([0.0, 0.0, 1.0]),  # Z
            ]
            a = ax_vecs[self.ax1 // 2]
            b = ax_vecs[self.ax2 // 2]
            # Third axis is the out-of-plane direction (useful to indicate)
            c = np.cross(a, b)
            return a, b, c

        def _plane_label(self):
            """String like 'X/Y' for the VP-defined plane."""
            names = ["X", "Y", "Z"]
            return f"{names[self.ax1 // 2]}/{names[self.ax2 // 2]}"

        def _draw_plane_overlay(self, painter):
            """Draw a grid of the VP-defined plane projected through the solved
            camera — fSpy-style reference. Grid is centered at world origin
            (which the solver places along the view ray via the origin control
            point). Also draws a short arrow along the out-of-plane axis.
            """
            if self.solve_result is None:
                return
            import numpy as np
            axis_a, axis_b, axis_c = self._plane_basis()
            c_offset = np.zeros(3)

            # Grid step scales with the camera distance so the grid spans a
            # visible portion of the frame regardless of scene scale. A fresh
            # Flame camera at cam_back ≈ image_height/(2·tan(vfov/2)) puts the
            # frame about cam_back/f_rel × 2 tall at origin — step = cam_back/20
            # gives ~20 grid cells across the frame, matching fSpy-style density.
            cam_back = float(self.solve_result.get("cam_back_dist", 10.0))
            N = 10
            step = cam_back / 20.0
            rows = 2 * N + 1
            cols = 2 * N + 1
            pts = [[None] * cols for _ in range(rows)]
            for i, a in enumerate(np.linspace(-N * step, N * step, rows)):
                for j, b in enumerate(np.linspace(-N * step, N * step, cols)):
                    p3d = c_offset + a * axis_a + b * axis_b
                    pts[i][j] = self._project_world(p3d)

            pen = QtGui.QPen()
            pen.setCosmetic(True)
            # Color: subtle mix of ax1 & ax2 colors at low opacity
            c1 = _axis_color(self.ax1)
            c2 = _axis_color(self.ax2)
            axis_line_col = QtGui.QColor((c1.red()+c2.red())//2,
                                         (c1.green()+c2.green())//2,
                                         (c1.blue()+c2.blue())//2, 160)
            grid_col = QtGui.QColor(axis_line_col.red(), axis_line_col.green(),
                                    axis_line_col.blue(), 55)

            # Gridlines: horizontal lines (along axis_b at each axis_a value)
            pen.setWidth(1)
            pen.setColor(grid_col)
            painter.setPen(pen)
            painter.setBrush(QtCore.Qt.NoBrush)
            for i in range(rows):
                for j in range(cols - 1):
                    p0 = pts[i][j]
                    p1 = pts[i][j + 1]
                    if p0 and p1:
                        painter.drawLine(QtCore.QPointF(*p0), QtCore.QPointF(*p1))
            # Lines along axis_a
            for j in range(cols):
                for i in range(rows - 1):
                    p0 = pts[i][j]
                    p1 = pts[i + 1][j]
                    if p0 and p1:
                        painter.drawLine(QtCore.QPointF(*p0), QtCore.QPointF(*p1))

            # Center axis lines (through origin) drawn brighter, with axis colors
            # axis_a line (through origin, b=0)
            zero_row = pts[N]  # b=0 row? Actually our indexing: rows iterate axis_a
            # axis_a runs along rows; the b=0 line is column index = N (middle)
            pen.setWidth(2)
            pen.setColor(QtGui.QColor(c1.red(), c1.green(), c1.blue(), 190))
            painter.setPen(pen)
            for i in range(rows - 1):
                p0 = pts[i][N]
                p1 = pts[i + 1][N]
                if p0 and p1:
                    painter.drawLine(QtCore.QPointF(*p0), QtCore.QPointF(*p1))
            pen.setColor(QtGui.QColor(c2.red(), c2.green(), c2.blue(), 190))
            painter.setPen(pen)
            for j in range(cols - 1):
                p0 = pts[N][j]
                p1 = pts[N][j + 1]
                if p0 and p1:
                    painter.drawLine(QtCore.QPointF(*p0), QtCore.QPointF(*p1))

            # Grid-center marker (represents the nominal origin projected onto
            # the offset plane — since true origin is at the camera and can't
            # be drawn, this is the "center" of the visible plane section).
            origin_w = self._project_world(c_offset)
            if origin_w:
                painter.setBrush(QtGui.QColor(255, 255, 255, 220))
                painter.setPen(QtGui.QPen(QtGui.QColor(30, 30, 30), 1.5))
                painter.drawEllipse(QtCore.QPointF(*origin_w), 5, 5)

            # Third-axis arrow (out-of-plane) from grid-center — extends a few
            # grid cells out so it's clearly visible against the grid.
            tip_w = self._project_world(c_offset + 3.0 * step * axis_c)
            if origin_w and tip_w:
                third_idx = ({0,1,2} - {self.ax1 // 2, self.ax2 // 2}).pop()
                third_pos_idx = third_idx * 2  # +X, +Y, or +Z
                third_col = _axis_color(third_pos_idx)
                pen.setColor(third_col)
                pen.setWidth(2)
                painter.setPen(pen)
                painter.drawLine(QtCore.QPointF(*origin_w), QtCore.QPointF(*tip_w))
                # Arrowhead
                import math
                dx = tip_w[0] - origin_w[0]
                dy = tip_w[1] - origin_w[1]
                L = math.hypot(dx, dy) or 1.0
                ux, uy = dx/L, dy/L
                px_, py_ = -uy, ux
                size = 8
                ax_ = tip_w[0] - ux*size + px_*size*0.6
                ay_ = tip_w[1] - uy*size + py_*size*0.6
                bx_ = tip_w[0] - ux*size - px_*size*0.6
                by_ = tip_w[1] - uy*size - py_*size*0.6
                painter.setBrush(third_col)
                painter.setPen(QtCore.Qt.NoPen)
                tri = QtGui.QPolygonF([
                    QtCore.QPointF(*tip_w),
                    QtCore.QPointF(ax_, ay_),
                    QtCore.QPointF(bx_, by_),
                ])
                painter.drawPolygon(tri)
                # Label the out-of-plane axis
                names = ["X","Y","Z"]
                self._draw_label_pill(
                    painter, tip_w[0] + ux*14, tip_w[1] + uy*14,
                    "+" + names[third_idx], third_col, primary=True)

        def paintEvent(self, event):
            p = QtGui.QPainter(self)
            p.setRenderHint(QtGui.QPainter.Antialiasing)
            p.setRenderHint(QtGui.QPainter.TextAntialiasing)

            r = self._image_rect()

            # Dimmed image
            p.setOpacity(self.image_opacity)
            p.drawImage(r, self._qimage)
            p.setOpacity(1.0)

            # Plane overlay (drawn before VP lines so they sit on top)
            if self.show_plane and self.solve_result is not None:
                self._draw_plane_overlay(p)

            # VP1 always drawn. In quad mode, VP2 is rendered as the two
            # synthesized edges (A→C, B→D) closing the quad — no separate
            # handles since they share VP1's endpoints. VP3 drawn when on.
            self._draw_vp_pair(p, 0, self.ax1)
            if self.quad_mode:
                self._draw_quad_synth_pair(p, self.ax2)
            else:
                self._draw_vp_pair(p, 6, self.ax2)
            if self.use_vp3:
                self._draw_vp3_pair(p)

            # Handles — only render endpoints for currently active lines.
            #   VP1 indices 0..(2*n_lines)
            #   VP2 indices 6..(6+2*n_lines)   skipped when quad_mode
            #   VP3 indices 12..15             shown when use_vp3
            n_lines = 3 if self.three_lines else 2
            active_indices = list(range(0, 2*n_lines))
            if not self.quad_mode:
                active_indices += list(range(6, 6 + 2*n_lines))
            if self.use_vp3:
                active_indices += [12, 13, 14, 15]
            vp3_color = QtGui.QColor(220, 220, 220)
            for i in active_indices:
                pt = self.points[i]
                wx, wy = self._norm_to_widget(pt[0], pt[1])
                if i >= 12:
                    color = vp3_color
                else:
                    color = _axis_color(self.ax1 if i < 6 else self.ax2)
                p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255), 1.5))
                p.setBrush(color)
                p.drawEllipse(QtCore.QPointF(wx, wy), HANDLE_RADIUS, HANDLE_RADIUS)

            # Origin control handle (crosshair + ring). Bright if user-placed,
            # dimmer if auto-defaulted to VP1-line0 ∩ VP2-line0 intersection.
            o_wpos = self._origin_widget_pos()
            if o_wpos is not None:
                ox, oy = o_wpos
                is_auto = self.origin_norm is None
                ring_col = QtGui.QColor(255, 255, 255, 180 if is_auto else 240)
                cross_col = QtGui.QColor(255, 255, 255, 220 if not is_auto else 160)
                p.setPen(QtGui.QPen(ring_col, 1.5))
                p.setBrush(QtCore.Qt.NoBrush)
                p.drawEllipse(QtCore.QPointF(ox, oy), HANDLE_RADIUS + 2, HANDLE_RADIUS + 2)
                p.drawEllipse(QtCore.QPointF(ox, oy), 2, 2)
                p.setPen(QtGui.QPen(cross_col, 1))
                p.drawLine(QtCore.QPointF(ox - (HANDLE_RADIUS + 6), oy),
                           QtCore.QPointF(ox - 3, oy))
                p.drawLine(QtCore.QPointF(ox + 3, oy),
                           QtCore.QPointF(ox + (HANDLE_RADIUS + 6), oy))
                p.drawLine(QtCore.QPointF(ox, oy - (HANDLE_RADIUS + 6)),
                           QtCore.QPointF(ox, oy - 3))
                p.drawLine(QtCore.QPointF(ox, oy + 3),
                           QtCore.QPointF(ox, oy + (HANDLE_RADIUS + 6)))

            # Solve status dot
            if self.solve_result:
                p.setPen(QtGui.QPen(QtGui.QColor(123, 211, 123), 2))
                p.setBrush(QtGui.QColor(123, 211, 123, 50))
                p.drawEllipse(QtCore.QPointF(r.x() + 20, r.y() + 20), 6, 6)

            p.end()

        def mousePressEvent(self, event):
            if event.button() == QtCore.Qt.LeftButton:
                mx, my = event.x(), event.y()
                # Test origin handle first so it wins ties with nearby VP handles.
                o_wpos = self._origin_widget_pos()
                if o_wpos is not None:
                    ox, oy = o_wpos
                    if (mx - ox)**2 + (my - oy)**2 < (HANDLE_RADIUS + 6)**2:
                        self.dragging_origin = True
                        return
                n_lines = 3 if self.three_lines else 2
                active_indices = list(range(0, 2*n_lines))
                if not self.quad_mode:
                    active_indices += list(range(6, 6 + 2*n_lines))
                if self.use_vp3:
                    active_indices += [12, 13, 14, 15]
                for i in active_indices:
                    pt = self.points[i]
                    wx, wy = self._norm_to_widget(pt[0], pt[1])
                    if (mx - wx)**2 + (my - wy)**2 < (HANDLE_RADIUS + 4)**2:
                        self.dragging = i
                        return

        def mouseMoveEvent(self, event):
            if self.dragging_origin:
                nx, ny = self._widget_to_norm(event.x(), event.y())
                nx = max(0.0, min(1.0, nx))
                ny = max(0.0, min(1.0, ny))
                self.origin_norm = [nx, ny]
                if hasattr(self, '_auto_solve_cb'):
                    self._auto_solve_cb()
                self.update()
            elif self.dragging >= 0:
                nx, ny = self._widget_to_norm(event.x(), event.y())
                nx = max(0.0, min(1.0, nx))
                ny = max(0.0, min(1.0, ny))
                self.points[self.dragging] = [nx, ny]
                # Auto-solve on drag
                if hasattr(self, '_auto_solve_cb'):
                    self._auto_solve_cb()
                self.update()

        def mouseReleaseEvent(self, event):
            self.dragging = -1
            self.dragging_origin = False

        def mouseDoubleClickEvent(self, event):
            # Double-click origin handle to reset to auto-placement.
            mx, my = event.x(), event.y()
            o_wpos = self._origin_widget_pos()
            if o_wpos is not None:
                ox, oy = o_wpos
                if (mx - ox)**2 + (my - oy)**2 < (HANDLE_RADIUS + 6)**2:
                    self.reset_origin_to_auto()

    class CameraMatchWindow(QtWidgets.QDialog):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setWindowTitle("FORGE — Camera Match")
            self.resize(1280, 820)
            self.setStyleSheet(_FORGE_SS)

            clip_name = ""
            try:
                clip_name = clip.name.get_value() if hasattr(clip.name, "get_value") else str(clip.name)
            except Exception:
                pass

            # Root layout
            root = QtWidgets.QHBoxLayout(self)
            root.setContentsMargins(12, 12, 12, 12)
            root.setSpacing(12)

            # Image viewport (left)
            self.image_widget = ImageWidget()
            self.image_widget._auto_solve_cb = self._on_solve
            root.addWidget(self.image_widget, stretch=4)

            # Side panel container (fixed-ish width)
            side = QtWidgets.QWidget()
            side.setObjectName("sidePanel")
            side.setFixedWidth(300)
            panel = QtWidgets.QVBoxLayout(side)
            panel.setContentsMargins(0, 0, 0, 0)
            panel.setSpacing(10)
            root.addWidget(side, stretch=0)

            # Header
            header = QtWidgets.QLabel("Camera Match")
            header.setStyleSheet("color: #E87E24; font-weight: bold; font-size: 14px;")
            panel.addWidget(header)
            subtitle = QtWidgets.QLabel(
                f"{clip_name}  ·  {img_w}×{img_h}" if clip_name else f"{img_w}×{img_h}"
            )
            subtitle.setStyleSheet("color: #888; font-size: 11px;")
            subtitle.setWordWrap(True)
            panel.addWidget(subtitle)

            # Frame spinner — only useful when the clip has more than one frame.
            # Range spans the clip's source frame numbering (e.g. 1001..4667 for
            # a 3667-frame shot starting at 1001). Default to the current mark
            # if set, else the first frame.
            try:
                _dur = int(clip.duration.get_value())
            except Exception:
                _dur = 1
            try:
                _start = int(clip.clip.start_frame)
            except Exception:
                _start = 1
            if _dur > 1:
                frame_row = QtWidgets.QHBoxLayout()
                frame_row.setSpacing(8)
                fl = QtWidgets.QLabel("Frame")
                fl.setObjectName("fieldLabel")
                fl.setFixedWidth(40)
                self.frame_spin = QtWidgets.QSpinBox()
                self.frame_spin.setRange(_start, _start + _dur - 1)
                self.frame_spin.setValue(_start)
                self.frame_spin.setKeyboardTracking(False)  # fire only on commit
                self.frame_spin.valueChanged.connect(self._on_frame_changed)
                frame_row.addWidget(fl)
                frame_row.addWidget(self.frame_spin, stretch=1)
                panel.addLayout(frame_row)

            # Source colourspace selector — feeds the OCIO preview transform
            # to sRGB so log/linear footage looks correct instead of washed-out.
            cs_row = QtWidgets.QHBoxLayout()
            cs_row.setSpacing(8)
            cs_lbl = QtWidgets.QLabel("Source")
            cs_lbl.setObjectName("fieldLabel")
            cs_lbl.setFixedWidth(40)
            self.cs_combo = QtWidgets.QComboBox()
            for opt in _OCIO_SOURCE_OPTIONS:
                self.cs_combo.addItem(opt)
            try:
                self.cs_combo.setCurrentText(initial_source_cs)
            except Exception:
                self.cs_combo.setCurrentText(_OCIO_DEFAULT_SOURCE)
            # Show the raw Wiretap tag in the tooltip so the user can sanity-
            # check the auto-detect against the clip's actual metadata.
            if wt_cs:
                self.cs_combo.setToolTip(f"Wiretap colour space: {wt_cs}")
            self.cs_combo.currentTextChanged.connect(self._on_source_cs_changed)
            cs_row.addWidget(cs_lbl)
            cs_row.addWidget(self.cs_combo, stretch=1)
            panel.addLayout(cs_row)

            sep1 = QtWidgets.QFrame()
            sep1.setObjectName("sep")
            sep1.setFrameShape(QtWidgets.QFrame.HLine)
            panel.addWidget(sep1)

            # ── Vanishing Points group ──
            vp_group = QtWidgets.QGroupBox("VANISHING POINTS")
            vp_layout = QtWidgets.QVBoxLayout(vp_group)
            vp_layout.setSpacing(8)

            def _build_axis_combo(default_idx):
                cb = QtWidgets.QComboBox()
                for i, lbl in enumerate(_AX_LABELS):
                    cb.addItem(_axis_swatch(i), lbl)
                cb.setCurrentIndex(default_idx)
                return cb

            def _vp_row(label_text, combo):
                row = QtWidgets.QHBoxLayout()
                row.setSpacing(8)
                lbl = QtWidgets.QLabel(label_text)
                lbl.setObjectName("fieldLabel")
                lbl.setFixedWidth(40)
                row.addWidget(lbl)
                row.addWidget(combo, stretch=1)
                return row

            self.vp1_axis = _build_axis_combo(1)   # -X (Flame default)
            self.vp2_axis = _build_axis_combo(3)   # -Y (Flame default)
            vp_layout.addLayout(_vp_row("VP 1", self.vp1_axis))
            vp_layout.addLayout(_vp_row("VP 2", self.vp2_axis))
            self.vp1_axis.currentIndexChanged.connect(self._on_solve)
            self.vp2_axis.currentIndexChanged.connect(self._on_solve)

            self.three_lines_check = QtWidgets.QCheckBox("3 lines per VP (least-squares)")
            self.three_lines_check.setChecked(False)
            self.three_lines_check.toggled.connect(self._on_three_lines)
            vp_layout.addWidget(self.three_lines_check)

            self.quad_mode_check = QtWidgets.QCheckBox("Quad mode (VP2 from VP1 corners)")
            self.quad_mode_check.setChecked(False)
            self.quad_mode_check.toggled.connect(self._on_quad_mode)
            vp_layout.addWidget(self.quad_mode_check)

            self.vp3_check = QtWidgets.QCheckBox("VP3 → principal point (orthocentre)")
            self.vp3_check.setChecked(False)
            self.vp3_check.toggled.connect(self._on_vp3)
            vp_layout.addWidget(self.vp3_check)
            panel.addWidget(vp_group)

            # ── Display group ──
            disp_group = QtWidgets.QGroupBox("DISPLAY")
            disp_layout = QtWidgets.QVBoxLayout(disp_group)
            disp_layout.setSpacing(8)

            dim_row = QtWidgets.QHBoxLayout()
            dim_row.setSpacing(8)
            dim_lbl = QtWidgets.QLabel("Image dim")
            dim_lbl.setObjectName("fieldLabel")
            dim_lbl.setFixedWidth(70)
            self.opacity_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
            self.opacity_slider.setRange(10, 100)
            self.opacity_slider.setValue(50)
            self.opacity_slider.valueChanged.connect(self._on_opacity)
            dim_row.addWidget(dim_lbl)
            dim_row.addWidget(self.opacity_slider, stretch=1)
            disp_layout.addLayout(dim_row)

            self.ext_check = QtWidgets.QCheckBox("Show extended lines")
            self.ext_check.setChecked(True)
            self.ext_check.toggled.connect(self._on_extended)
            disp_layout.addWidget(self.ext_check)

            self.plane_check = QtWidgets.QCheckBox("Show plane overlay")
            self.plane_check.setChecked(True)
            self.plane_check.toggled.connect(self._on_plane)
            disp_layout.addWidget(self.plane_check)
            panel.addWidget(disp_group)

            # ── Results group ──
            result_group = QtWidgets.QGroupBox("SOLVED CAMERA")
            result_layout = QtWidgets.QGridLayout(result_group)
            result_layout.setHorizontalSpacing(10)
            result_layout.setVerticalSpacing(6)

            def _result_row(row, label_text):
                lbl = QtWidgets.QLabel(label_text)
                lbl.setObjectName("fieldLabel")
                val = QtWidgets.QLabel("—")
                val.setObjectName("valueDim")
                result_layout.addWidget(lbl, row, 0)
                result_layout.addWidget(val, row, 1)
                return val

            self.lbl_focal = _result_row(0, "Focal")
            self.lbl_fov   = _result_row(1, "FOV")
            self.lbl_rot   = _result_row(2, "Rotation")
            self.lbl_pos   = _result_row(3, "Position")
            result_layout.setColumnStretch(1, 1)
            panel.addWidget(result_group)

            # Status
            self.lbl_status = QtWidgets.QLabel("Drag VP lines to solve")
            self.lbl_status.setObjectName("fieldLabel")
            panel.addWidget(self.lbl_status)

            # ── Apply options ──
            apply_group = QtWidgets.QGroupBox("APPLY OPTIONS")
            apply_layout = QtWidgets.QVBoxLayout(apply_group)
            apply_layout.setSpacing(6)
            self.drop_axes_check = QtWidgets.QCheckBox("Drop axes at line endpoints")
            self.drop_axes_check.setChecked(False)
            self.drop_axes_check.setToolTip(
                "Back-project every VP line endpoint onto the solved plane and "
                "drop an Axis at each world position. Useful for anchoring "
                "geometry to real scene features.")
            apply_layout.addWidget(self.drop_axes_check)
            panel.addWidget(apply_group)

            # Spacer + buttons
            panel.addStretch(1)

            self.apply_btn = QtWidgets.QPushButton("Apply to Camera")
            self.apply_btn.setObjectName("primary")
            self.apply_btn.setEnabled(False)
            self.apply_btn.clicked.connect(self._on_apply)
            self.apply_btn.setMinimumHeight(36)
            panel.addWidget(self.apply_btn)

            close_btn = QtWidgets.QPushButton("Close")
            close_btn.clicked.connect(self.close)
            panel.addWidget(close_btn)

            # Sync image widget's axes to the current dropdowns and do initial solve
            self.image_widget.set_axes(
                self.vp1_axis.currentIndex(), self.vp2_axis.currentIndex())
            self._on_solve()

        def _on_opacity(self, val):
            self.image_widget.image_opacity = val / 100.0
            self.image_widget.update()

        def _on_extended(self, checked):
            self.image_widget.show_extended = checked
            self.image_widget.update()

        def _on_plane(self, checked):
            self.image_widget.show_plane = checked
            self.image_widget.update()

        def _on_three_lines(self, checked):
            self.image_widget.three_lines = checked
            self._on_solve()  # re-solve with new line count

        def _on_quad_mode(self, checked):
            self.image_widget.quad_mode = checked
            self._on_solve()

        def _on_vp3(self, checked):
            self.image_widget.use_vp3 = checked
            self._on_solve()

        def _on_solve(self, *args):
            ax1 = self.vp1_axis.currentIndex()
            ax2 = self.vp2_axis.currentIndex()
            # Keep viewport colors in sync with dropdowns even when solve fails
            self.image_widget.set_axes(ax1, ax2)
            result = self.image_widget.run_solve(ax1, ax2)

            if result:
                r = result["rotation"]
                self.lbl_focal.setText("%.1f mm" % result["focal_mm"])
                self.lbl_fov.setText("%.1f° H / %.1f° V" % (result["hfov_deg"], result["vfov_deg"]))
                self.lbl_rot.setText("%.2f, %.2f, %.2f°" % (r[0], r[1], r[2]))
                self.lbl_pos.setText("%.2f, %.2f, %.2f" % result["position"])
                for lbl in (self.lbl_focal, self.lbl_fov, self.lbl_rot, self.lbl_pos):
                    lbl.setObjectName("value")
                    lbl.setStyleSheet("")  # force re-evaluation of object-name sheet
                self.lbl_status.setText("● Solve valid")
                self.lbl_status.setObjectName("statusOK")
                self.apply_btn.setEnabled(True)
            else:
                for lbl in (self.lbl_focal, self.lbl_fov, self.lbl_rot, self.lbl_pos):
                    lbl.setText("—")
                    lbl.setObjectName("valueDim")
                    lbl.setStyleSheet("")
                self.lbl_status.setText("● Invalid — adjust lines")
                self.lbl_status.setObjectName("statusBad")
                self.apply_btn.setEnabled(False)
            # Re-polish the labels whose objectName changed (so QSS updates)
            for lbl in (self.lbl_focal, self.lbl_fov, self.lbl_rot, self.lbl_pos, self.lbl_status):
                lbl.style().unpolish(lbl)
                lbl.style().polish(lbl)

        def _on_apply(self):
            import flame

            result = self.image_widget.solve_result
            if result is None:
                return

            def _val(x):
                return x.get_value() if hasattr(x, "get_value") else str(x)

            # Find Action nodes with cameras. Skip the built-in "Perspective"
            # viewport camera — it drives the Action 3D-view tumble camera, not
            # the rendered scene; overwriting it is almost never the intent.
            cameras = []
            try:
                for node in flame.batch.nodes:
                    if _val(node.type) != "Action":
                        continue
                    action_name = _val(node.name)
                    for inode in node.nodes:
                        if "Camera" not in _val(inode.type):
                            continue
                        cam_name = _val(inode.name)
                        if cam_name == "Perspective":
                            continue
                        cameras.append((node, inode, f"{action_name} > {cam_name}"))
            except Exception as e:
                self.lbl_status.setText(f"● Apply failed: {e}")
                self.lbl_status.setObjectName("statusBad")
                self.lbl_status.style().unpolish(self.lbl_status)
                self.lbl_status.style().polish(self.lbl_status)
                return

            cam = None
            action = None
            created_new_action = False
            try:
                if cameras:
                    choices = [c[2] for c in cameras] + ["Create new Action"]
                    choice, ok = QtWidgets.QInputDialog.getItem(
                        self, "Apply Camera", "Target camera:", choices, 0, False)
                    if not ok:
                        return
                    if choice == "Create new Action":
                        action = flame.batch.create_node("Action")
                        cam = action.nodes[0]
                        created_new_action = True
                    else:
                        action = cameras[choices.index(choice)][0]
                        cam = cameras[choices.index(choice)][1]
                else:
                    action = flame.batch.create_node("Action")
                    cam = action.nodes[0]
                    created_new_action = True

                # Camera transform — solver now returns the full world position,
                # computed so that world origin projects to the origin control
                # pixel at a fixed distance along the view ray.
                cam.target_mode.set_value(False)
                pos = result["position"]
                cam.position.set_value((float(pos[0]), float(pos[1]), float(pos[2])))
                cam.rotation.set_value(result["rotation"])
                # Flame's `fov` is VERTICAL FOV. Setting it directly controls the
                # 3D projection regardless of `focal`/`film_type` assumptions.
                # (Setting `focal_mm` alone gives the wrong FOV because Flame's
                # default film back is 16mm Super 16.)
                cam.fov.set_value(float(result["vfov_deg"]))

                # When creating a new Action: wire the calibrated clip into the
                # Back input, park the node near the clip in the schematic, and
                # drop a small origin Axis so the user can see where the solved
                # world origin landed.
                if created_new_action:
                    # Back input wiring. "Default" on an Action input socket
                    # maps to Background (= Back) per flame.batch.connect_nodes
                    # docs, so this works without needing the clip's specific
                    # output socket name (which defaults to the clip's name).
                    try:
                        flame.batch.connect_nodes(clip, "Default", action, "Default")
                    except Exception:
                        pass  # non-fatal: user can wire manually
                    # Schematic placement: Flame's pos_x/pos_y are int-typed
                    # PyAttributes; must go through set_value() with int. Direct
                    # assignment or float values raise a C++ converter error.
                    try:
                        action.pos_x.set_value(int(clip.pos_x.get_value()) + 370)
                        action.pos_y.set_value(int(clip.pos_y.get_value()))
                    except Exception:
                        pass
                    # Origin marker
                    try:
                        origin_axis = action.create_node("Axis")
                        origin_axis.name = "cam_match_origin"
                        origin_axis.position.set_value((0.0, 0.0, 0.0))
                        origin_axis.rotation.set_value((0.0, 0.0, 0.0))
                        # Leave scale at Flame default — scene is now in native
                        # 1-unit-per-image-pixel space, so the default axis size
                        # is visible without modification.
                    except Exception:
                        pass  # non-fatal

                # Optional: drop an Axis at every back-projected line endpoint.
                # Checked by default off — user opts in when they want scene
                # anchors at the grout intersections / VP line endpoints.
                dropped_axes = 0
                if self.drop_axes_check.isChecked():
                    for label, pos_w in self.image_widget.endpoint_axes():
                        try:
                            ax = action.create_node("Axis")
                            ax.name = label
                            ax.position.set_value((float(pos_w[0]),
                                                   float(pos_w[1]),
                                                   float(pos_w[2])))
                            ax.rotation.set_value((0.0, 0.0, 0.0))
                            dropped_axes += 1
                        except Exception:
                            pass  # non-fatal, skip this endpoint

                # Readback for trace
                applied = {
                    "position": list(cam.position.get_value()),
                    "rotation": list(cam.rotation.get_value()),
                    "fov": cam.fov.get_value(),
                    "focal": cam.focal.get_value(),
                    "film_type": cam.film_type.get_value(),
                    "target_mode": cam.target_mode.get_value(),
                    "action_name": _val(action.name) if action else None,
                    "created_new_action": created_new_action,
                    "intended": {
                        "position": result["position"],
                        "rotation": result["rotation"],
                        "vfov_deg": result.get("vfov_deg"),
                        "hfov_deg": result.get("hfov_deg"),
                        "focal_mm": result.get("focal_mm"),
                    },
                }
                # Append to solve trace file if it exists
                try:
                    import json
                    with open(_TRACE_PATH, "r") as fp:
                        tr = json.load(fp)
                    tr["applied_to_flame"] = applied
                    with open(_TRACE_PATH, "w") as fp:
                        json.dump(tr, fp, indent=2)
                except Exception:
                    pass

                if dropped_axes:
                    self.lbl_status.setText(f"● Applied — {dropped_axes} axes dropped")
                else:
                    self.lbl_status.setText("● Applied to camera")
                self.lbl_status.setObjectName("statusOK")
            except Exception as e:
                self.lbl_status.setText(f"● Apply failed: {e}")
                self.lbl_status.setObjectName("statusBad")
            self.lbl_status.style().unpolish(self.lbl_status)
            self.lbl_status.style().polish(self.lbl_status)

        def _current_frame(self):
            return int(self.frame_spin.value()) if hasattr(self, "frame_spin") else None

        def _on_frame_changed(self, new_frame):
            """Re-read the requested source frame via the current source
            colourspace and swap the viewport image. VP lines and solve state
            are preserved; on failure the old image stays and status shows."""
            src_cs = self.cs_combo.currentText() if hasattr(self, "cs_combo") else None
            rgb, _w, _h = _read_source_frame(
                clip, target_frame=int(new_frame), source_colourspace=src_cs)
            if rgb is None:
                self.lbl_status.setText(f"● Frame {new_frame} read failed")
                self.lbl_status.setObjectName("statusBad")
                self.lbl_status.style().unpolish(self.lbl_status)
                self.lbl_status.style().polish(self.lbl_status)
                return
            self.image_widget.reload_image(rgb)

        def _on_source_cs_changed(self, _text):
            """Re-decode the currently-visible frame with the new source
            colourspace. Cheaper than a full reopen, no state lost."""
            fr = self._current_frame()
            if fr is not None:
                self._on_frame_changed(fr)
            else:
                # Single-frame/stills clip — re-read with no target frame.
                src_cs = self.cs_combo.currentText()
                rgb, _w, _h = _read_source_frame(clip, source_colourspace=src_cs)
                if rgb is not None:
                    self.image_widget.reload_image(rgb)

        def closeEvent(self, event):
            event.accept()

    # Show the window
    win = CameraMatchWindow()
    win.exec_()


# =========================================================================
# Flame hook registration
# =========================================================================

def _scope_batch_clip(selection):
    """Show menu only when a Clip node is selected in Batch."""
    import flame
    for item in selection:
        if isinstance(item, flame.PyClipNode):
            return True
    return False

def _launch_camera_match(selection):
    """Launch the Camera Match window for the selected clip.

    Passes the PyClipNode (not its inner PyClip) through to _open_camera_match
    — downstream code needs both the batch node (for pos_x, connect_nodes on
    Apply) and the inner PyClip (for wiretap node id, start_frame on read).
    """
    import flame

    clip_node = None
    for item in selection:
        if isinstance(item, flame.PyClipNode):
            clip_node = item
            break

    if clip_node is None:
        flame.messages.show_in_dialog(
            title="Camera Match",
            message="Select a Clip node in Batch.",
            type="error", buttons=["OK"])
        return

    _open_camera_match(clip_node)

def get_batch_custom_ui_actions():
    return [
        {
            "name": "Camera Match",
            "actions": [
                {
                    "name": "Open Camera Match",
                    "isVisible": _scope_batch_clip,
                    "execute": _launch_camera_match,
                },
            ],
        }
    ]
