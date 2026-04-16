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

def _solve(pts_px, w, h, ax1=1, ax2=5):
    """Run the full 2VP solve from pixel coordinates.

    pts_px: list of 8 points [(x,y), ...] — VP1 line1 start/end, line2 start/end,
            then VP2 line1 start/end, line2 start/end. All in pixel coords (top-left origin).
    Returns dict with position, rotation, focal_mm, hfov_deg or None on failure.
    """
    _ensure_forge_env()
    import numpy as np

    SENSOR_MM = 36.0
    _AX = {0:[1,0,0],1:[-1,0,0],2:[0,1,0],3:[0,-1,0],4:[0,0,1],5:[0,0,-1]}

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

    vp1 = line_isect(ip[0], ip[1], ip[2], ip[3])
    vp2 = line_isect(ip[4], ip[5], ip[6], ip[7])
    if vp1 is None or vp2 is None:
        return None

    pp = np.array([0.0, 0.0])

    # Focal length
    puv = ortho_proj(pp, vp1, vp2)
    fsq = np.linalg.norm(vp2-puv)*np.linalg.norm(vp1-puv) - np.linalg.norm(pp-puv)**2
    if fsq <= 0:
        return None
    f = float(np.sqrt(fsq))

    # Rotation
    u = np.array([vp1[0]-pp[0], vp1[1]-pp[1], -f])
    v = np.array([vp2[0]-pp[0], vp2[1]-pp[1], -f])
    u /= np.linalg.norm(u); v /= np.linalg.norm(v)
    ww = np.cross(u, v); ww /= np.linalg.norm(ww)
    R = np.column_stack([u, v, ww])

    # Axis assignment
    r1 = np.array(_AX[ax1], dtype=float)
    r2 = np.array(_AX[ax2], dtype=float)
    A = np.vstack([r1, r2, np.cross(r1, r2)])

    view_rot = R @ A
    cam_rot = np.linalg.inv(view_rot)

    # Euler angles
    cy = np.sqrt(cam_rot[0,0]**2 + cam_rot[0,1]**2)
    if cy > 1e-6:
        rx = np.arctan2(cam_rot[1,2], cam_rot[2,2])
        ry = np.arctan2(-cam_rot[0,2], cy)
        rz = np.arctan2(cam_rot[0,1], cam_rot[0,0])
    else:
        rx = np.arctan2(-cam_rot[2,1], cam_rot[1,1])
        ry = np.arctan2(-cam_rot[0,2], cy)
        rz = 0.0
    eul = np.degrees(np.array([rx, ry, rz]))

    hfov = 2.0 * np.arctan(1.0 / f)
    aspect = w / h
    vfov = 2.0 * np.arctan(np.tan(hfov/2.0) / aspect)
    focal_mm = f * SENSOR_MM / 2.0

    return {
        "position": (0.0, 0.0, 0.0),
        "rotation": (float(eul[0]), float(eul[1]), float(eul[2])),
        "focal_mm": float(focal_mm),
        "hfov_deg": float(np.degrees(hfov)),
        "vfov_deg": float(np.degrees(vfov)),
    }


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

    HANDLE_RADIUS = 8
    VP1_COLOR = QtGui.QColor(255, 80, 30)
    VP2_COLOR = QtGui.QColor(30, 130, 255)
    VP1_COLOR_DIM = QtGui.QColor(255, 80, 30, 100)
    VP2_COLOR_DIM = QtGui.QColor(30, 130, 255, 100)

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
            self.solve_result = None

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

        def run_solve(self, ax1, ax2):
            """Run solver with current point positions."""
            pts = [self._norm_to_px(p[0], p[1]) for p in self.points]
            self.solve_result = _solve(pts, img_w, img_h, ax1, ax2)
            self.update()
            return self.solve_result

        def paintEvent(self, event):
            p = QtGui.QPainter(self)
            p.setRenderHint(QtGui.QPainter.Antialiasing)

            r = self._image_rect()

            # Draw dimmed image
            p.setOpacity(self.image_opacity)
            p.drawImage(r, self._qimage)
            p.setOpacity(1.0)

            # Draw VP lines
            pen = QtGui.QPen()
            pen.setWidth(2)

            # VP1 lines (orange)
            for i in range(2):
                s = self.points[i*2]
                e = self.points[i*2+1]
                sx, sy = self._norm_to_widget(s[0], s[1])
                ex, ey = self._norm_to_widget(e[0], e[1])

                # Extended line (dashed, dim)
                if self.show_extended:
                    pen.setColor(VP1_COLOR_DIM)
                    pen.setStyle(QtCore.Qt.DashLine)
                    pen.setWidth(1)
                    p.setPen(pen)
                    dx, dy = ex - sx, ey - sy
                    length = (dx*dx + dy*dy) ** 0.5
                    if length > 0:
                        scale = 5000 / length
                        p.drawLine(
                            QtCore.QPointF(sx - dx*scale, sy - dy*scale),
                            QtCore.QPointF(ex + dx*scale, ey + dy*scale))

                # Solid segment
                pen.setColor(VP1_COLOR)
                pen.setStyle(QtCore.Qt.SolidLine)
                pen.setWidth(2)
                p.setPen(pen)
                p.drawLine(QtCore.QPointF(sx, sy), QtCore.QPointF(ex, ey))

            # VP2 lines (blue)
            for i in range(2):
                s = self.points[4 + i*2]
                e = self.points[4 + i*2+1]
                sx, sy = self._norm_to_widget(s[0], s[1])
                ex, ey = self._norm_to_widget(e[0], e[1])

                if self.show_extended:
                    pen.setColor(VP2_COLOR_DIM)
                    pen.setStyle(QtCore.Qt.DashLine)
                    pen.setWidth(1)
                    p.setPen(pen)
                    dx, dy = ex - sx, ey - sy
                    length = (dx*dx + dy*dy) ** 0.5
                    if length > 0:
                        scale = 5000 / length
                        p.drawLine(
                            QtCore.QPointF(sx - dx*scale, sy - dy*scale),
                            QtCore.QPointF(ex + dx*scale, ey + dy*scale))

                pen.setColor(VP2_COLOR)
                pen.setStyle(QtCore.Qt.SolidLine)
                pen.setWidth(2)
                p.setPen(pen)
                p.drawLine(QtCore.QPointF(sx, sy), QtCore.QPointF(ex, ey))

            # Draw handles
            for i, pt in enumerate(self.points):
                wx, wy = self._norm_to_widget(pt[0], pt[1])
                color = VP1_COLOR if i < 4 else VP2_COLOR
                p.setPen(QtCore.Qt.NoPen)
                p.setBrush(color)
                p.drawEllipse(QtCore.QPointF(wx, wy), HANDLE_RADIUS, HANDLE_RADIUS)
                # White center dot
                p.setBrush(QtGui.QColor(255, 255, 255))
                p.drawEllipse(QtCore.QPointF(wx, wy), 3, 3)

            # Solve status
            if self.solve_result:
                pen.setColor(QtGui.QColor(0, 255, 0))
                pen.setWidth(2)
                p.setPen(pen)
                p.setBrush(QtGui.QColor(0, 255, 0, 50))
                p.drawEllipse(QtCore.QPointF(r.x() + 20, r.y() + 20), 8, 8)

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
            self.setWindowTitle("Camera Match")
            self.resize(1200, 800)

            # Main layout
            layout = QtWidgets.QHBoxLayout(self)

            # Image widget (left, takes most space)
            self.image_widget = ImageWidget()
            self.image_widget._auto_solve_cb = self._on_solve
            layout.addWidget(self.image_widget, stretch=4)

            # Controls panel (right)
            panel = QtWidgets.QVBoxLayout()
            layout.addLayout(panel, stretch=1)

            # Axis selection
            ax_group = QtWidgets.QGroupBox("Axis Assignment")
            ax_layout = QtWidgets.QFormLayout()
            self.vp1_axis = QtWidgets.QComboBox()
            self.vp1_axis.addItems(_AX_LABELS)
            self.vp1_axis.setCurrentIndex(1)  # -X
            self.vp2_axis = QtWidgets.QComboBox()
            self.vp2_axis.addItems(_AX_LABELS)
            self.vp2_axis.setCurrentIndex(5)  # -Z
            ax_layout.addRow("VP1 Axis:", self.vp1_axis)
            ax_layout.addRow("VP2 Axis:", self.vp2_axis)
            ax_group.setLayout(ax_layout)
            panel.addWidget(ax_group)
            self.vp1_axis.currentIndexChanged.connect(self._on_solve)
            self.vp2_axis.currentIndexChanged.connect(self._on_solve)

            # Display controls
            disp_group = QtWidgets.QGroupBox("Display")
            disp_layout = QtWidgets.QFormLayout()
            self.opacity_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
            self.opacity_slider.setRange(10, 100)
            self.opacity_slider.setValue(50)
            self.opacity_slider.valueChanged.connect(self._on_opacity)
            disp_layout.addRow("Image Dim:", self.opacity_slider)
            self.ext_check = QtWidgets.QCheckBox("Show Extended Lines")
            self.ext_check.setChecked(True)
            self.ext_check.toggled.connect(self._on_extended)
            disp_layout.addRow(self.ext_check)
            disp_group.setLayout(disp_layout)
            panel.addWidget(disp_group)

            # Solve results
            result_group = QtWidgets.QGroupBox("Solved Camera")
            result_layout = QtWidgets.QFormLayout()
            self.lbl_pos = QtWidgets.QLabel("—")
            self.lbl_rot = QtWidgets.QLabel("—")
            self.lbl_focal = QtWidgets.QLabel("—")
            self.lbl_fov = QtWidgets.QLabel("—")
            self.lbl_status = QtWidgets.QLabel("Drag VP lines to solve")
            result_layout.addRow("Position:", self.lbl_pos)
            result_layout.addRow("Rotation:", self.lbl_rot)
            result_layout.addRow("Focal:", self.lbl_focal)
            result_layout.addRow("FOV:", self.lbl_fov)
            result_layout.addRow("Status:", self.lbl_status)
            result_group.setLayout(result_layout)
            panel.addWidget(result_group)

            # Action buttons
            panel.addStretch()
            self.apply_btn = QtWidgets.QPushButton("Apply to Camera")
            self.apply_btn.setEnabled(False)
            self.apply_btn.clicked.connect(self._on_apply)
            self.apply_btn.setMinimumHeight(40)
            panel.addWidget(self.apply_btn)

            close_btn = QtWidgets.QPushButton("Close")
            close_btn.clicked.connect(self.close)
            panel.addWidget(close_btn)

            # Initial solve
            self._on_solve()

        def _on_opacity(self, val):
            self.image_widget.image_opacity = val / 100.0
            self.image_widget.update()

        def _on_extended(self, checked):
            self.image_widget.show_extended = checked
            self.image_widget.update()

        def _on_solve(self, *args):
            ax1 = self.vp1_axis.currentIndex()
            ax2 = self.vp2_axis.currentIndex()
            result = self.image_widget.run_solve(ax1, ax2)

            if result:
                r = result["rotation"]
                self.lbl_pos.setText("%.2f, %.2f, %.2f" % result["position"])
                self.lbl_rot.setText("%.2f, %.2f, %.2f" % (r[0], r[1], r[2]))
                self.lbl_focal.setText("%.1f mm" % result["focal_mm"])
                self.lbl_fov.setText("%.1f deg" % result["hfov_deg"])
                self.lbl_status.setText("Valid")
                self.lbl_status.setStyleSheet("color: #00cc00;")
                self.apply_btn.setEnabled(True)
            else:
                self.lbl_pos.setText("—")
                self.lbl_rot.setText("—")
                self.lbl_focal.setText("—")
                self.lbl_fov.setText("—")
                self.lbl_status.setText("Invalid — adjust lines")
                self.lbl_status.setStyleSheet("color: #cc0000;")
                self.apply_btn.setEnabled(False)

        def _on_apply(self):
            import flame

            result = self.image_widget.solve_result
            if result is None:
                return

            # Find or create Action camera
            cameras = []
            for node in flame.batch.nodes:
                ntype = node.type.get_value() if hasattr(node.type, "get_value") else ""
                if str(ntype) == "Action":
                    action_name = node.name.get_value()
                    for inode in node.nodes:
                        itype = inode.type.get_value() if hasattr(inode.type, "get_value") else ""
                        if "Camera" in str(itype):
                            cam_name = inode.name.get_value()
                            cameras.append((node, inode, action_name + " > " + cam_name))

            if cameras:
                choices = [c[2] for c in cameras] + ["Create New Action"]
                choice, ok = QtWidgets.QInputDialog.getItem(
                    self, "Apply Camera", "Select target camera:", choices, 0, False)
                if not ok:
                    return
                if choice == "Create New Action":
                    action = flame.batch.create_node("Action")
                    cam = action.nodes[0]
                else:
                    idx = choices.index(choice)
                    cam = cameras[idx][1]
            else:
                action = flame.batch.create_node("Action")
                cam = action.nodes[0]

            cam.target_mode.set_value(False)
            cam.position.set_value(result["position"])
            cam.rotation.set_value(result["rotation"])
            cam.focal.set_value(result["focal_mm"])

            self.lbl_status.setText("Applied!")
            self.lbl_status.setStyleSheet("color: #00cc00;")

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
