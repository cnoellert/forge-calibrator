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


def _solve(pts_px, w, h, ax1=1, ax2=5):
    """Run the full 2VP solve from pixel coordinates.

    pts_px: list of 8 points [(x,y), ...] — VP1 line1 start/end, line2 start/end,
            then VP2 line1 start/end, line2 start/end. All in pixel coords (top-left origin).
    Returns dict with position, rotation, focal_mm, hfov_deg or None on failure.

    Writes a complete math trace to /tmp/forge_camera_match_trace.json each call.
    """
    _ensure_forge_env()
    import numpy as np
    import time

    SENSOR_MM = 36.0
    _AX = {0:[1,0,0],1:[-1,0,0],2:[0,1,0],3:[0,-1,0],4:[0,0,1],5:[0,0,-1]}
    _AX_NAMES = ["+X","-X","+Y","-Y","+Z","-Z"]

    trace = {
        "timestamp": time.time(),
        "inputs": {
            "image_size": [w, h],
            "aspect": w / h,
            "ax1": ax1, "ax1_name": _AX_NAMES[ax1],
            "ax2": ax2, "ax2_name": _AX_NAMES[ax2],
            "sensor_mm": SENSOR_MM,
            "points_px": [list(map(float, p)) for p in pts_px],
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

    pp = np.array([0.0, 0.0])

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

    # Flame's identity camera looks down +Z_local (verified: with Lcl=0 and
    # PostRotation=(0,-90,0), FBX export yields world forward = +Z). The
    # solver's cam_rot uses the OpenGL convention where camera looks -Z_local.
    # Convert by rotating the camera's local frame 180° around Y before
    # decomposing to Flame Euler angles.
    RY_180 = np.array([[-1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, -1.0]])
    cam_rot_flame = cam_rot @ RY_180
    trace["stages"]["cam_rot_flame_convention"] = cam_rot_flame.tolist()

    # Euler angles — Flame uses R = Rx(-rx) · Ry(-ry) · Rz(rz) internally
    # (X and Y inverted from right-hand rule; verified empirically via FBX export)
    cy = np.sqrt(cam_rot_flame[0,0]**2 + cam_rot_flame[0,1]**2)
    gimbal = cy <= 1e-6
    if not gimbal:
        rx = np.arctan2( cam_rot_flame[1,2], cam_rot_flame[2,2])
        ry = np.arctan2(-cam_rot_flame[0,2], cy)
        rz = np.arctan2(-cam_rot_flame[0,1], cam_rot_flame[0,0])
    else:
        rx = np.arctan2(-cam_rot_flame[2,1], cam_rot_flame[1,1])
        ry = np.arctan2(-cam_rot_flame[0,2], cy)
        rz = 0.0
    eul = np.degrees(np.array([rx, ry, rz]))
    trace["stages"]["gimbal_lock"] = bool(gimbal)
    trace["stages"]["flame_euler_deg"] = eul.tolist()

    # Sanity: reconstruct R from Euler using Flame's convention and compare
    def _rx(a): c,s=np.cos(a),np.sin(a); return np.array([[1,0,0],[0,c,-s],[0,s,c]])
    def _ry(a): c,s=np.cos(a),np.sin(a); return np.array([[c,0,s],[0,1,0],[-s,0,c]])
    def _rz(a): c,s=np.cos(a),np.sin(a); return np.array([[c,-s,0],[s,c,0],[0,0,1]])
    R_recon = _rx(-rx) @ _ry(-ry) @ _rz(rz)
    trace["stages"]["R_recon_from_euler"] = R_recon.tolist()
    trace["stages"]["R_recon_matches_cam_rot_flame"] = bool(np.allclose(R_recon, cam_rot_flame, atol=1e-6))

    # Project world axes through the solved camera back to pixel coords — this
    # is the acid test: does +ax1_world land near the user's VP1 pixel?
    def project_world_dir(d_world):
        v_cam = cam_rot.T @ np.asarray(d_world, dtype=float)
        if v_cam[2] >= 0:
            return {"cam_dir": v_cam.tolist(), "projects": "BEHIND camera"}
        # In image plane: x' = v[0]/-v[2], y' = v[1]/-v[2]
        ipx = v_cam[0] / -v_cam[2]
        ipy = v_cam[1] / -v_cam[2]
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

    result = {
        "position": (0.0, 0.0, 0.0),
        "rotation": (float(eul[0]), float(eul[1]), float(eul[2])),
        "focal_mm": float(focal_mm),
        "film_back_mm": float(SENSOR_MM),
        "hfov_deg": float(np.degrees(hfov)),
        "vfov_deg": float(np.degrees(vfov)),
        # For viewport projection helpers (plane overlay etc.)
        "cam_rot": cam_rot.tolist(),
        "f_relative": f,
        "ax1": ax1, "ax2": ax2,
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

def _export_frame(clip):
    """Export one frame of a clip to a temp JPEG. Returns (image_path, tmp_dir) or (None, None)."""
    import flame
    import os
    import tempfile
    import shutil

    tmp_dir = tempfile.mkdtemp(prefix="camera_match_")
    exp = flame.PyExporter()
    exp.foreground = True
    try:
        exp.export(clip, _JPEG_PRESET, tmp_dir, hooks=_NoHooks())
    except Exception as e:
        print("Export error:", e)
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return None, None

    # Find the exported file
    for root, dirs, files in os.walk(tmp_dir):
        for f in files:
            if f.lower().endswith((".jpg", ".jpeg")):
                return os.path.join(root, f), tmp_dir

    shutil.rmtree(tmp_dir, ignore_errors=True)
    return None, None


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

    # Export frame
    img_path, tmp_dir = _export_frame(clip)
    if img_path is None:
        flame.messages.show_in_dialog(
            title="Camera Match",
            message="Could not export frame from clip.",
            type="error", buttons=["OK"])
        return

    # Load image
    img_bgr = cv2.imread(img_path)
    if img_bgr is None:
        flame.messages.show_in_dialog(
            title="Camera Match",
            message="Could not read exported image.",
            type="error", buttons=["OK"])
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return

    img_h, img_w = img_bgr.shape[:2]
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)

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

            # VP line endpoints in normalized coords (0-1, top-left origin)
            self.points = [
                # VP1 line 1
                [0.15, 0.35], [0.85, 0.40],
                # VP1 line 2
                [0.15, 0.65], [0.85, 0.60],
                # VP2 line 1
                [0.35, 0.15], [0.40, 0.85],
                # VP2 line 2
                [0.65, 0.15], [0.60, 0.85],
            ]

            self.dragging = -1
            self.image_opacity = 0.5
            self.show_extended = True
            self.show_plane = True
            self.solve_result = None

            # Axis assignments (index into _AX_LABELS); updated from the window
            self.ax1 = 1  # VP1 -> -X
            self.ax2 = 5  # VP2 -> -Z

            self._qimage = QtGui.QImage(
                img_rgb.data, img_w, img_h, img_w * 3,
                QtGui.QImage.Format_RGB888
            ).copy()  # copy so numpy can be freed

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

        def run_solve(self, ax1, ax2):
            """Run solver with current point positions."""
            self.ax1 = ax1
            self.ax2 = ax2
            pts = [self._norm_to_px(p[0], p[1]) for p in self.points]
            self.solve_result = _solve(pts, img_w, img_h, ax1, ax2)
            self.update()
            return self.solve_result

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
            """Draw the two lines for one VP (base_idx = 0 for VP1, 4 for VP2).

            Direction semantics:
            - The positive axis (whatever the dropdown says, e.g. '+X' or '-X')
              points toward the VP = intersection of the two lines.
            - Chevron on each line points toward the VP end.
            - Label pill on the VP-facing end of line 0 shows the chosen axis;
              a dim pill on the opposite end shows the inverse axis.
            """
            import math
            color = _axis_color(ax_idx)
            color_dim = _axis_color(ax_idx, alpha=90)
            pen = QtGui.QPen()

            # Collect segment endpoints in widget coords
            segs = []
            for i in range(2):
                s = self.points[base_idx + i*2]
                e = self.points[base_idx + i*2 + 1]
                sx, sy = self._norm_to_widget(s[0], s[1])
                ex, ey = self._norm_to_widget(e[0], e[1])
                segs.append(((sx, sy), (ex, ey)))

            # Compute VP (intersection of the two extended lines)
            vp = self._line_intersect(segs[0][0], segs[0][1], segs[1][0], segs[1][1])

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

        def _project_world(self, world_pt):
            """Project a 3D world point through the solved camera to widget coords.

            Returns (wx, wy) or None if the point is behind the camera.
            """
            if self.solve_result is None:
                return None
            import numpy as np
            cam_rot = np.asarray(self.solve_result["cam_rot"])
            f_rel = self.solve_result["f_relative"]
            v = cam_rot.T @ np.asarray(world_pt, dtype=float)
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
            camera — fSpy-style reference. Also draws a short arrow along the
            out-of-plane (third) axis from origin.

            NOTE: in a 2VP solve without an origin control point, the world
            origin is at the camera position. The plane containing origin
            therefore passes through the camera and projects as a single line.
            We offset the grid along the camera's forward direction by a
            distance that places the grid center on the principal axis — this
            makes the plane's orientation visible as a 2D region in the image.
            """
            if self.solve_result is None:
                return
            import numpy as np
            axis_a, axis_b, axis_c = self._plane_basis()

            # Camera forward in world coords = -(cam's +Z axis in world) since
            # cam looks down -Z_local. That's -(col 2 of cam_rot).
            cam_rot = np.asarray(self.solve_result["cam_rot"])
            forward_world = -cam_rot[:, 2]

            # Project forward onto the plane normal (axis_c): the offset applied
            # along axis_c that puts us at unit depth along view direction.
            # We want the grid's center at (forward_world * d) — but only the
            # component of that along axis_c matters for "moving off the plane"
            # since axis_a and axis_b offsets stay on the plane. Pure axis_c
            # offset is simplest and most predictable.
            d = 10.0  # world-unit distance to grid center along camera forward
            proj_on_c = float(np.dot(forward_world, axis_c))
            if abs(proj_on_c) < 1e-3:
                # Camera's forward is nearly parallel to the plane — no useful
                # offset possible. Fall back to flat axis_c offset (may project off-screen).
                c_offset = d * axis_c
            else:
                # Place grid center at P = k·axis_c such that forward·P = d.
                # This puts the grid on a plane parallel to the VP plane, d units
                # ahead of the camera along its forward direction — visible regardless
                # of whether axis_c points toward or away from the camera.
                c_offset = (d / proj_on_c) * axis_c

            N = 10
            step = 1.0
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

            # Third-axis arrow (out-of-plane) from grid-center
            tip_w = self._project_world(c_offset + 3.0 * axis_c)
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

            # VP1 + VP2 line pairs, colored by assigned axis
            self._draw_vp_pair(p, 0, self.ax1)
            self._draw_vp_pair(p, 4, self.ax2)

            # Handles
            for i, pt in enumerate(self.points):
                wx, wy = self._norm_to_widget(pt[0], pt[1])
                ax_idx = self.ax1 if i < 4 else self.ax2
                color = _axis_color(ax_idx)
                p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255), 1.5))
                p.setBrush(color)
                p.drawEllipse(QtCore.QPointF(wx, wy), HANDLE_RADIUS, HANDLE_RADIUS)

            # Solve status dot
            if self.solve_result:
                p.setPen(QtGui.QPen(QtGui.QColor(123, 211, 123), 2))
                p.setBrush(QtGui.QColor(123, 211, 123, 50))
                p.drawEllipse(QtCore.QPointF(r.x() + 20, r.y() + 20), 6, 6)

            p.end()

        def mousePressEvent(self, event):
            if event.button() == QtCore.Qt.LeftButton:
                mx, my = event.x(), event.y()
                for i, pt in enumerate(self.points):
                    wx, wy = self._norm_to_widget(pt[0], pt[1])
                    if (mx - wx)**2 + (my - wy)**2 < (HANDLE_RADIUS + 4)**2:
                        self.dragging = i
                        return

        def mouseMoveEvent(self, event):
            if self.dragging >= 0:
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

            self.vp1_axis = _build_axis_combo(1)   # -X
            self.vp2_axis = _build_axis_combo(5)   # -Z
            vp_layout.addLayout(_vp_row("VP 1", self.vp1_axis))
            vp_layout.addLayout(_vp_row("VP 2", self.vp2_axis))
            self.vp1_axis.currentIndexChanged.connect(self._on_solve)
            self.vp2_axis.currentIndexChanged.connect(self._on_solve)
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

            # Find Action nodes with cameras
            cameras = []
            try:
                for node in flame.batch.nodes:
                    if _val(node.type) != "Action":
                        continue
                    action_name = _val(node.name)
                    for inode in node.nodes:
                        if "Camera" in _val(inode.type):
                            cam_name = _val(inode.name)
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

                # Camera transform
                cam.target_mode.set_value(False)
                # Pull the camera back along its view direction so the origin
                # axis lands some distance in front (visible), not at the camera.
                # Translation doesn't affect VP projection.
                DEFAULT_CAM_BACK = 10.0
                import numpy as _np
                cam_rot_mat = _np.asarray(result.get("cam_rot", _np.eye(3).tolist()))
                cam_forward = -cam_rot_mat[:, 2]  # solver-convention forward
                pos = tuple(-DEFAULT_CAM_BACK * cam_forward)
                cam.position.set_value((float(pos[0]), float(pos[1]), float(pos[2])))
                cam.rotation.set_value(result["rotation"])
                # Flame's `fov` is VERTICAL FOV. Setting it directly controls the
                # 3D projection regardless of `focal`/`film_type` assumptions.
                # (Setting `focal_mm` alone gives the wrong FOV because Flame's
                # default film back is 16mm Super 16.)
                cam.fov.set_value(float(result["vfov_deg"]))

                # When creating a new Action, drop a small Axis at world origin so
                # the user can immediately see where the solved origin landed and
                # verify the axis directions against the plate.
                if created_new_action:
                    try:
                        origin_axis = action.create_node("Axis")
                        origin_axis.name = "cam_match_origin"
                        origin_axis.position.set_value((0.0, 0.0, 0.0))
                        origin_axis.rotation.set_value((0.0, 0.0, 0.0))
                        origin_axis.scale.set_value((100.0, 100.0, 100.0))
                    except Exception:
                        pass  # non-fatal

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

                self.lbl_status.setText("● Applied to camera")
                self.lbl_status.setObjectName("statusOK")
            except Exception as e:
                self.lbl_status.setText(f"● Apply failed: {e}")
                self.lbl_status.setObjectName("statusBad")
            self.lbl_status.style().unpolish(self.lbl_status)
            self.lbl_status.style().polish(self.lbl_status)

        def closeEvent(self, event):
            # Clean up temp files
            if tmp_dir and os.path.exists(tmp_dir):
                shutil.rmtree(tmp_dir, ignore_errors=True)
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
    """Launch the Camera Match window for the selected clip."""
    import flame

    # Get PyClip from the selected PyClipNode via .clip attribute
    clip = None
    for item in selection:
        if isinstance(item, flame.PyClipNode):
            clip = item.clip
            break

    if clip is None:
        flame.messages.show_in_dialog(
            title="Camera Match",
            message="Select a Clip node in Batch.",
            type="error", buttons=["OK"])
        return

    _open_camera_match(clip)

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
