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
import os
import re
import sys


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


def _ensure_forge_core_on_path():
    """Put the parent directory of forge_core/ on sys.path.

    forge_core/ ships as a sibling of this file:
        dev:     <repo>/forge_core            (sibling of <repo>/flame/)
        install: /opt/Autodesk/shared/python/forge_core
                                              (sibling of /opt/…/camera_match/)
    In both layouts, the parent of this file's directory is also the parent
    of forge_core/, so adding it to sys.path makes `import forge_core` work.
    """
    this_dir = os.path.dirname(os.path.abspath(__file__))
    parent = os.path.dirname(this_dir)
    if parent not in sys.path:
        sys.path.insert(0, parent)


# =========================================================================
# Module-level constants used by the UI
# =========================================================================

_AX_LABELS = ["+X", "-X", "+Y", "-Y", "+Z", "-Z"]

# Trace file — written by forge_flame.adapter.solve_for_flame on every solve,
# read by the UI's "Open trace" affordance for post-mortem inspection.
# Keep in sync with forge_flame.adapter.TRACE_PATH.
_TRACE_PATH = "/tmp/forge_camera_match_trace.json"


# =========================================================================
# Thin re-exports so UI code can keep its existing _fit_vp / _line_residual_px
# call sites. Real implementations live in forge_core.solver.fitting.
# =========================================================================


def _fit_vp(lines_px):
    """See forge_core.solver.fitting.fit_vp_from_lines."""
    _ensure_forge_core_on_path()
    from forge_core.solver.fitting import fit_vp_from_lines
    return fit_vp_from_lines(lines_px)


def _line_residual_px(p0, p1, vp):
    """See forge_core.solver.fitting.line_to_vp_residual_px."""
    _ensure_forge_core_on_path()
    from forge_core.solver.fitting import line_to_vp_residual_px
    return line_to_vp_residual_px(p0, p1, vp)


# The inlined _solve / _solve_lines / _write_trace functions that used to
# live here moved to forge_flame.adapter.solve_for_flame (which wraps
# forge_core.solver.solve_2vp). See:
#   - forge_core/solver/solver.py     — pure-math solve_2vp
#   - forge_flame/adapter.py          — Flame ZYX Euler + cam_back + trace
#   - tests/test_hook_parity.py       — verifies adapter ≡ solve_2vp math


# Preview colour pipeline. Uses Flame's shipped ACES 2.0 config so the
# preview goes through a real RRT+ODT — highlights roll off softly instead
# of clipping to pure white, which matters for marking VP lines against
# bright skies / blown windows. The sRGB display + ACES 2.0 SDR 100 nits
# view matches a standard desktop monitor. Config-path resolution lives in
# forge_core.colour.ocio.resolve_flame_aces2_config().
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
    """Thin wrapper over forge_flame.wiretap.get_clip_colour_space.
    Kept as a hook-level name so existing call sites don't need to change."""
    _ensure_forge_core_on_path()
    from forge_flame.wiretap import get_clip_colour_space
    return get_clip_colour_space(clip)


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
# OCIO pipeline is lazy-constructed on first use. The reusable OcioPipeline
# class lives in forge_core.colour.ocio; the hook just keeps the Flame-specific
# config-path resolver + the display/view names its preview is pinned to.
_OCIO_PIPELINE = None


def _get_ocio_pipeline():
    """Lazy-build the OcioPipeline for the hook's fixed display/view target.

    Kept as a module-level singleton so repeated _read_source_frame calls
    reuse the cached OCIO config and per-source processors across UI events."""
    global _OCIO_PIPELINE
    if _OCIO_PIPELINE is not None:
        return _OCIO_PIPELINE

    # Resolve the hook's sys.path so forge_core (sibling of flame/) is importable.
    # Production install lands camera_match.py at /opt/Autodesk/shared/python/
    # camera_match/ — forge_core/ must ship alongside.
    _ensure_forge_core_on_path()

    from forge_core.colour.ocio import OcioPipeline, resolve_flame_aces2_config
    path = resolve_flame_aces2_config()
    _OCIO_PIPELINE = OcioPipeline(
        config_path=path, display=_OCIO_DISPLAY, view=_OCIO_VIEW,
    )
    return _OCIO_PIPELINE


def _get_ocio_processor(src_cs):
    """Thin wrapper so _read_source_frame can keep its existing call site."""
    return _get_ocio_pipeline().get_processor(src_cs)


def _read_source_frame(clip, target_frame=None, source_colourspace=None):
    """Read one frame of a Flame clip and return it as a display-ready uint8 RGB.

    Orchestrates three extracted helpers:

      - ``forge_flame.wiretap.extract_frame_bytes`` pulls the frame via the
        wiretap_rw_frame CLI. Necessary because cv2/ffmpeg can't decode Sony/
        ARRI-proprietary MXF wrappers; Flame's decoder handles them natively.
      - ``forge_core.image.buffer`` decodes the bytes. Wiretap may hand back
        either a standard image container (soft-imported stills) or a raw
        pixel buffer — buffer.decode_image_container handles the former,
        decode_raw_rgb_buffer handles the latter (stripping the leading
        header, flipping vertically, reordering GBR → RGB).
      - ``apply_ocio_or_passthrough`` runs float buffers through OCIO's
        DisplayViewTransform (ACES 2.0 SDR) so highlights roll off softly.
        When source_colourspace is None / Passthrough, it clips+quantises.

    Frame indexing: target_frame is in clip-source frame numbering (e.g.
    1001..4667 for start_frame=1001).

    Returns (img_rgb_uint8, width, height) or (None, None, None) on failure."""
    _ensure_forge_core_on_path()
    from forge_flame.wiretap import extract_frame_bytes
    from forge_core.image.buffer import (
        decode_image_container, decode_raw_rgb_buffer, apply_ocio_or_passthrough,
    )

    extracted = extract_frame_bytes(clip, target_frame)
    if extracted is None:
        return None, None, None
    raw, w, h, bit_depth = extracted

    # Container path: PNG/JPEG/TIFF/EXR/DPX for soft-imported stills.
    img = decode_image_container(raw)
    if img is not None:
        return img, int(img.shape[1]), int(img.shape[0])

    # Raw buffer path: Wiretap's bottom-up, GBR-ordered float (or uint8) dump.
    arr = decode_raw_rgb_buffer(raw, w, h, bit_depth)
    if arr is None:
        print(f"decode_raw_rgb_buffer rejected buffer "
              f"({len(raw)} bytes, {w}x{h}, bit_depth={bit_depth})")
        return None, None, None

    # uint8 → already display-encoded (Rec.709 video / sRGB JPG). Pass through.
    import numpy as np
    if arr.dtype == np.uint8:
        return arr, w, h

    # Float → OCIO view transform when a known source is tagged, else passthrough.
    is_passthrough = (
        source_colourspace is None or source_colourspace == _OCIO_PASSTHROUGH
    )
    proc = None if is_passthrough else _get_ocio_processor(source_colourspace)
    return apply_ocio_or_passthrough(arr, proc), w, h


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
            """Run solver with current point positions. Delegates to
            forge_flame.adapter.solve_for_flame, which wraps
            forge_core.solver.solve_2vp with Flame's ZYX-negated Euler
            decomposition and pixel-unit cam_back default."""
            self.ax1 = ax1
            self.ax2 = ax2
            vp1_lines, vp2_lines, vp3_lines = self._active_lines()
            origin_px = None
            if self.origin_norm is not None:
                origin_px = self._norm_to_px(self.origin_norm[0], self.origin_norm[1])
            _ensure_forge_core_on_path()
            from forge_flame.adapter import solve_for_flame
            self.solve_result = solve_for_flame(
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

def _val(x):
    """Unwrap a Flame PyAttribute to its Python value, or str() anything else.

    Shared helper for the handlers below. _apply_camera has an inline copy
    of the same logic — next time that path is touched, fold it into this
    module-level helper."""
    return x.get_value() if hasattr(x, "get_value") else str(x)


def _find_action_cameras(only_action=None):
    """Return [(action_node, camera_node, label), ...] for solvable cameras.

    If `only_action` is given, restrict to cameras inside that Action node.
    Otherwise scan every Action in the current batch.

    Skips Flame's built-in Perspective viewport cameras — overwriting those
    changes the 3D tumble view, not the rendered scene.

    Duplicates the discovery loop inlined in _apply_camera (line ~1465);
    scheduled for consolidation next time that path is touched."""
    import flame

    if only_action is not None:
        actions = [only_action]
    else:
        actions = [n for n in flame.batch.nodes if _val(n.type) == "Action"]

    cameras = []
    for action in actions:
        action_name = _val(action.name)
        for inode in action.nodes:
            if "Camera" not in _val(inode.type):
                continue
            cam_name = _val(inode.name)
            if cam_name == "Perspective":
                continue
            cameras.append((action, inode, f"{action_name} > {cam_name}"))
    return cameras


def _scope_batch_action(selection):
    """True when any selected item is an Action node in Batch.

    Uses type-string match rather than isinstance because flame.PyActionNode
    isn't consistently exposed as a Python class across Flame versions. The
    type attribute is a PyAttribute wrapping the string 'Action' — same
    pattern the _apply_camera path uses."""
    for item in selection:
        try:
            t = item.type
            type_val = t.get_value() if hasattr(t, "get_value") else str(t)
            if type_val == "Action":
                return True
        except Exception:
            continue
    return False


def _first_action_in_selection(selection):
    """Return the first Action node in `selection`, or None."""
    for item in selection:
        try:
            t = item.type
            type_val = t.get_value() if hasattr(t, "get_value") else str(t)
            if type_val == "Action":
                return item
        except Exception:
            continue
    return None


def _scan_first_clip_metadata():
    """Best-effort plate metadata from the first clip in the current batch.

    Returns a 3-tuple `(width, height, start_frame)` of ints if any clip
    is readable, or `None` if no clip exists in the batch or every clip
    failed to read.

    Returning `None` (rather than a hard-coded 1920x1080 sentinel) is
    deliberate: per Phase 1 D-08, callers must fall through to an error
    dialog when plate resolution cannot be determined — silent defaults
    are forbidden because geometric fidelity is the tool's core value.
    Never raises."""
    try:
        import flame
        for node in flame.batch.nodes:
            if isinstance(node, flame.PyClipNode):
                try:
                    pc = node.clip
                    return (int(pc.width), int(pc.height), int(pc.start_frame))
                except Exception:
                    continue
    except Exception:
        pass
    return None


def _pick_camera(cameras, dialog_title):
    """Prompt user to pick one camera from the list; returns (action, cam,
    label) or None if cancelled. No dialog shown if only one camera exists."""
    if len(cameras) == 1:
        return cameras[0]
    from PySide6 import QtWidgets
    choices = [c[2] for c in cameras]
    choice, ok = QtWidgets.QInputDialog.getItem(
        None, dialog_title, "Target camera:", choices, 0, False)
    if not ok:
        return None
    return cameras[choices.index(choice)]


def _read_launch_focus_steal() -> bool:
    """Read blender_launch_focus_steal from .planning/config.json.

    Returns False if the file is missing, unreadable, or the key is absent.
    Defaults to False per EXP-05 (Blender launches in background by default).
    Tolerant of any I/O or JSON failure — launch preference is non-critical.

    Read per-invocation (not cached) — the check is cheap and avoids
    module-state staleness across Flame's menu-handler lifecycle.

    On installed deployments (/opt/Autodesk/shared/python/camera_match/)
    there is no .planning/ sibling; the try/except returns False, which
    is the documented default per D-02.
    """
    import json
    this_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(this_dir)
    config_path = os.path.join(repo_root, ".planning", "config.json")
    try:
        with open(config_path) as f:
            return bool(json.load(f).get("blender_launch_focus_steal", False))
    except Exception:
        return False


_SANITIZE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]")


def _sanitize_name_component(name: str) -> str:
    """Make a Flame node name safe to embed in a filesystem path.

    The export handler builds `~/forge-bakes/{action}_{cam}.blend` from
    Flame Action and camera names. Flame permits characters in node names
    that are hostile to paths: `/`, `\\`, spaces, shell metacharacters
    (`$`, `` ` ``, `;`, `&`, `|`, `>`, `<`, `*`, `?`, quotes), and
    control bytes. Embedding those raw into a path risks path traversal
    (`..`-chains), shell confusion if the path is ever logged into a
    shell-expanded context, and plain OS-level write failures.

    This helper is ONLY for the filesystem path component. The original,
    unsanitized name is still stamped into the v5 JSON's
    `custom_properties` (per D-11) so the Blender-side "Send to Flame"
    return trip can look up the correct Flame Action.

    Rules:
      - Whitelist `[A-Za-z0-9._-]`; replace all other runes with `_`.
      - Truncate to 64 chars (keeps combined filename < 255-char FS limit).
      - If the result is empty, return `"unnamed"` so the caller never
        builds a degenerate `_{cam}.blend` or `{action}_.blend` path.

    Never raises; `None` and non-str inputs coerce via `str()`.
    """
    safe = _SANITIZE_NAME_RE.sub("_", str(name))[:64]
    return safe if safe.strip("_") else "unnamed"


class PlateResolutionUnavailable(RuntimeError):
    """Raised when plate resolution cannot be inferred from any of the
    three tiers (action.resolution, batch width/height, first clip in
    batch). Per D-08, callers must surface this as an error dialog —
    silent defaults to 1920x1080 are forbidden because geometric
    fidelity is the core value.
    """


def _infer_plate_resolution(action_node) -> tuple:
    """Infer plate (width, height) via the three-tier fallback chain.

    Tier order (per D-07; D-08 forbids any silent default):
      1. action_node.resolution   -- primary; shape confirmed by Plan 01's
         live-Flame probe (see .planning/phases/01-export-polish/01-PROBE.md
         TIER1_DISPOSITION line for the exact access pattern).
      2. flame.batch.width/height -- batch-level fallback; same pattern
         used at flame/apply_solve.py:269.
      3. _scan_first_clip_metadata() -- scan any clip in the current batch;
         returns None (after Plan 04 Task 1) when no readable clip exists.

    On total failure, raises PlateResolutionUnavailable. The caller
    (_export_camera_to_blender) catches this and surfaces an error dialog.

    Args:
        action_node: the Flame PyActionNode selected by the user.

    Returns:
        A `(width, height)` tuple of ints. Always valid (>0) on success.
    """
    import flame

    # Tier 1 — action.resolution (shape per 01-PROBE.md TIER1_DISPOSITION:
    # use-attr-width-height). action.resolution.get_value() returns a
    # PyResolution object with .width and .height attributes.
    try:
        if hasattr(action_node, "resolution") and hasattr(action_node.resolution, "get_value"):
            r = action_node.resolution.get_value()
            width, height = int(r.width), int(r.height)
            if width > 0 and height > 0:
                return (width, height)
    except Exception:
        pass  # fall through to Tier 2

    # Tier 2 — flame.batch.width/height (analog: flame/apply_solve.py:269).
    try:
        b = flame.batch
        width = int(b.width.get_value())
        height = int(b.height.get_value())
        if width > 0 and height > 0:
            return (width, height)
    except Exception:
        pass  # fall through to Tier 3

    # Tier 3 — first clip in batch. _scan_first_clip_metadata returns
    # None on miss (Task 1 of this plan refactored the sentinel away).
    scan = _scan_first_clip_metadata()
    if scan is not None:
        width, height, _start = scan
        if width > 0 and height > 0:
            return (int(width), int(height))

    # Every tier failed. Per D-08: no silent default; raise for the caller
    # to surface as an error dialog.
    raise PlateResolutionUnavailable(
        "Could not infer plate resolution from the Action, the batch, "
        "or any clip in the current batch. Open a clip in this batch "
        "or set a resolution on the Action before exporting."
    )


def _launch_blender_on_blend(blend_path: str, *, focus_steal: bool):
    """Spawn Blender as a detached subprocess opening `blend_path`.

    Per D-02, the platform branches are:
      - macOS: `open -a Blender <path>` when focus_steal is True;
        `open -a -g Blender <path>` when False (default). The `-g` flag
        (see `man open`) means "do not bring the application to the
        foreground", satisfying EXP-05's no-focus-steal default.
      - Linux: `subprocess.Popen([blender_bin, path], start_new_session=True)`
        regardless of focus_steal (Linux focus behavior is WM-dependent
        and documented as best-effort). `start_new_session=True` calls
        `setsid` in the child so closing Flame does not signal Blender.

    All subprocess calls use argv lists only (no shell expansion) — passing
    the path via shell would enable metacharacter injection via blend_path
    (which, although Task 2's sanitization prevents hostile names in the
    filename, could still contain user HOME path components we don't control).

    Returns the `subprocess.Popen` handle so the caller can inspect
    `.pid` or surface it in diagnostic logging. Never consumes the
    child's stdout/stderr — Blender runs detached.

    Raises NotImplementedError on unsupported platforms (forge-calibrator
    is macOS + Linux only per PROJECT.md). The caller is expected to
    catch exceptions from this helper and surface via show_in_dialog
    per D-03 (fall back to reveal_in_file_manager on failure).

    Args:
        blend_path: absolute path to the .blend to open.
        focus_steal: honored only on macOS. On Linux it is accepted
            for signature symmetry but has no effect.

    Returns:
        subprocess.Popen handle.
    """
    import subprocess
    import sys

    from forge_flame import blender_bridge

    if sys.platform == "darwin":
        args = ["open", "-a", "Blender"]
        if not focus_steal:
            args.append("-g")  # -g == background, no focus steal
        args.append(blend_path)
        return subprocess.Popen(args)
    elif sys.platform == "linux":
        # focus_steal is best-effort-ignored on Linux (WM-dependent).
        blender_bin = blender_bridge.resolve_blender_bin()
        return subprocess.Popen(
            [blender_bin, blend_path],
            start_new_session=True,
        )
    else:
        raise NotImplementedError(
            f"Blender launch not supported on platform {sys.platform!r}. "
            "forge-calibrator targets macOS and Linux only (see PROJECT.md)."
        )


def _export_camera_to_blender(selection):
    """Export a Flame Action camera to a Blender .blend via the forge bridge.

    Flow: right-click the Action holding your solved camera
    -> pick the target camera (dialog if Action has multiple non-Perspective)
    -> confirm/edit plate resolution (WxH; pre-filled from first clip in batch)
    -> pick output .blend path
    -> bake the camera to ASCII FBX via fbx_io.export_action_cameras_to_fbx
       (Flame's own baker walks the batch range flame.batch.start_frame +
       duration for animated cameras; static cameras get a 2-key endpoint
       FBX as an optimization)
    -> convert FBX to v5 JSON via fbx_ascii.fbx_to_v5_json (pins
       film_back_mm=36.0 for full-frame Blender parity)
    -> shell out to Blender via blender_bridge.run_bake
    -> reveal the .blend in the OS file manager.

    Frame range is auto-detected from the current batch — no dialog field.
    The FBX intermediate is kept alongside the .blend + .json for
    debuggability.

    Scope is `_scope_batch_action`, so this menu item appears on Action
    right-clicks. Open Camera Match remains on clip context since its
    workflow starts from a plate."""
    _ensure_forge_env()
    _ensure_forge_core_on_path()

    import flame
    import json as _json
    import os
    import subprocess
    from PySide6 import QtWidgets

    from forge_flame import blender_bridge, fbx_ascii, fbx_io

    action_node = _first_action_in_selection(selection)
    if action_node is None:
        flame.messages.show_in_dialog(
            title="Export Camera to Blender",
            message="Right-click an Action node in Batch (the Action that "
                    "holds your solved camera).",
            type="error", buttons=["OK"])
        return

    cameras = _find_action_cameras(only_action=action_node)
    if not cameras:
        flame.messages.show_in_dialog(
            title="Export Camera to Blender",
            message=f"No non-Perspective camera in "
                    f"'{_val(action_node.name)}'.",
            type="error", buttons=["OK"])
        return
    picked = _pick_camera(cameras, "Export Camera to Blender")
    if picked is None:
        return
    action, cam, label = picked

    # Plate resolution — pre-fill from the first clip in batch. The FBX
    # carries sensor/FOV/animation natively, but plate pixel dims aren't
    # a stock FBX property, so we still stamp them into the v5 JSON that
    # bake_camera.py consumes. Frame number was removed from this dialog:
    # the FBX baker walks flame.batch.start_frame + duration automatically.
    default_w, default_h, _default_frame = _scan_first_clip_metadata()
    res_text, ok = QtWidgets.QInputDialog.getText(
        None, "Export Camera to Blender",
        "Plate resolution (WxH):",
        QtWidgets.QLineEdit.Normal,
        f"{default_w}x{default_h}")
    if not ok:
        return
    try:
        w_str, h_str = res_text.lower().strip().split("x")
        width = int(w_str.strip())
        height = int(h_str.strip())
    except (ValueError, AttributeError):
        flame.messages.show_in_dialog(
            title="Export Camera to Blender",
            message=f"Couldn't parse {res_text!r}. "
                    f"Expected 'WxH' (e.g. 5184x3456).",
            type="error", buttons=["OK"])
        return

    # Output path — default name combines Action + camera.
    default_name = f"{_val(action_node.name)}_{_val(cam.name)}.blend"
    default_path = os.path.join("/tmp", default_name)
    blend_path, _filter = QtWidgets.QFileDialog.getSaveFileName(
        None, "Save Blender File", default_path, "Blender File (*.blend)")
    if not blend_path:
        return
    if not blend_path.endswith(".blend"):
        blend_path += ".blend"

    # Intermediate artifacts alongside the .blend for debuggability.
    fbx_path = blend_path[:-len(".blend")] + ".fbx"
    json_path = blend_path[:-len(".blend")] + ".json"

    # Bake Flame cam -> ASCII FBX. fbx_io handles the Perspective
    # exclusion and the selection dance (saves + restores user's prior
    # selection so we don't leak selection state back to Flame's UI).
    try:
        fbx_io.export_action_cameras_to_fbx(
            action, fbx_path,
            cameras=[cam],
            bake_animation=True,
        )
    except Exception as e:
        flame.messages.show_in_dialog(
            title="Export Camera to Blender",
            message=f"Failed to write FBX:\n{e}",
            type="error", buttons=["OK"])
        return

    # FBX -> v5 JSON for bake_camera.py. Pin film_back_mm=36.0 for
    # full-frame Blender parity (matches the prior single-frame path).
    try:
        fbx_ascii.fbx_to_v5_json(
            fbx_path, json_path,
            width=width, height=height,
            film_back_mm=36.0,
            camera_name=_val(cam.name),
        )
    except Exception as e:
        flame.messages.show_in_dialog(
            title="Export Camera to Blender",
            message=f"Failed to convert FBX to JSON:\n{e}",
            type="error", buttons=["OK"])
        return

    # Blender bake — bake_camera.py is already multi-frame capable.
    try:
        blender_bridge.run_bake(
            json_path, blend_path,
            camera_name="Camera", scale=1000.0, create_if_missing=True,
        )
    except FileNotFoundError as e:
        flame.messages.show_in_dialog(
            title="Export Camera to Blender",
            message=str(e), type="error", buttons=["OK"])
        return
    except subprocess.CalledProcessError as e:
        err = (e.stderr or e.stdout or "unknown error").strip()
        flame.messages.show_in_dialog(
            title="Export Camera to Blender",
            message=f"Blender bake failed (exit {e.returncode}):\n\n{err}",
            type="error", buttons=["OK"])
        return

    # Read frame count from JSON for the outcome dialog.
    try:
        with open(json_path) as f:
            n_frames = len(_json.load(f).get("frames") or [])
    except Exception:
        n_frames = 0
    frame_label = f"{n_frames}-frame" + ("" if n_frames == 1 else "s")

    blender_bridge.reveal_in_file_manager(blend_path)
    flame.messages.show_in_dialog(
        title="Export Camera to Blender",
        message=f"Exported '{label}' ({frame_label})\n"
                f"  plate:  {width}x{height}\n"
                f"  blend:  {blend_path}\n"
                f"  fbx:    {fbx_path}\n"
                f"  json:   {json_path}",
        type="info", buttons=["OK"])


def _import_camera_from_blender(selection):
    """Import a camera FROM a Blender .blend back into a Flame Action.

    Flow: right-click the target Action in Batch
    -> pick input .blend
    -> pick target camera name (informs the name on the imported cam;
       dialog only shown if multiple non-Perspective cameras present)
    -> shell out to Blender via blender_bridge.run_extract for JSON
    -> convert the v5 JSON to ASCII FBX via fbx_ascii.v5_json_to_fbx
    -> Flame-side FBX ingest via fbx_io.import_fbx_to_action

    The FBX route is mandatory for animated cameras — Flame's PyAttribute
    API has no keyframe write path (see memory/flame_keyframe_api.md).
    Static .blend files round-trip identically through the same flow;
    Flame's import_fbx just sees a single-keyframe curve. The Perspective
    exclusion lives in fbx_io, so the built-in viewport camera is safely
    filtered out regardless of what the .blend contains.

    Unlike the pre-v6.2 JSON-overwrite path, this creates a NEW camera
    rather than mutating the picked target. Flame auto-appends a numeric
    suffix on name collision (e.g. a .blend imported against an existing
    'Default' produces 'Default1'). The original camera is preserved so
    the user can compare and remove it manually."""
    _ensure_forge_env()
    _ensure_forge_core_on_path()

    import flame
    import json as _json
    import subprocess
    from PySide6 import QtWidgets

    from forge_flame import blender_bridge, fbx_ascii, fbx_io

    action_node = _first_action_in_selection(selection)
    if action_node is None:
        flame.messages.show_in_dialog(
            title="Import Camera from Blender",
            message="Right-click an Action node in Batch (the target for the "
                    "imported camera values).",
            type="error", buttons=["OK"])
        return

    cameras = _find_action_cameras(only_action=action_node)
    if not cameras:
        flame.messages.show_in_dialog(
            title="Import Camera from Blender",
            message=f"No non-Perspective camera in "
                    f"'{_val(action_node.name)}'.",
            type="error", buttons=["OK"])
        return

    blend_path, _filter = QtWidgets.QFileDialog.getOpenFileName(
        None, "Open Blender File", "/tmp", "Blender File (*.blend)")
    if not blend_path:
        return

    picked = _pick_camera(cameras, "Import Camera from Blender")
    if picked is None:
        return
    action, cam, _label = picked
    target_name = _val(cam.name)

    json_path = blend_path[:-len(".blend")] + "_extract.json" \
        if blend_path.endswith(".blend") else blend_path + "_extract.json"
    try:
        blender_bridge.run_extract(
            blend_path, json_path, camera_name="Camera")
    except FileNotFoundError as e:
        flame.messages.show_in_dialog(
            title="Import Camera from Blender",
            message=str(e), type="error", buttons=["OK"])
        return
    except subprocess.CalledProcessError as e:
        err = (e.stderr or e.stdout or "unknown error").strip()
        flame.messages.show_in_dialog(
            title="Import Camera from Blender",
            message=f"Blender extract failed (exit {e.returncode}):\n\n{err}",
            type="error", buttons=["OK"])
        return

    # Convert v5 JSON -> ASCII FBX. Name the emitted camera after the
    # picked target; Flame will auto-append a suffix on collision.
    fbx_path = json_path[:-len(".json")] + ".fbx"
    try:
        fbx_ascii.v5_json_to_fbx(
            json_path, fbx_path,
            camera_name=target_name,
        )
    except Exception as e:
        flame.messages.show_in_dialog(
            title="Import Camera from Blender",
            message=f"Failed to convert Blender JSON to FBX:\n{e}",
            type="error", buttons=["OK"])
        return

    try:
        new_nodes = fbx_io.import_fbx_to_action(action, fbx_path)
    except Exception as e:
        flame.messages.show_in_dialog(
            title="Import Camera from Blender",
            message=f"Failed to import FBX into Action:\n{e}",
            type="error", buttons=["OK"])
        return

    # Count frames for the outcome report.
    try:
        with open(json_path) as f:
            n_frames = len(_json.load(f).get("frames") or [])
    except Exception:
        n_frames = 0

    # PyCoNode instances have position / rotation / fov PyAttributes;
    # helper nodes (null targets) don't.
    imported_cam_names = [
        _val(n.name) for n in new_nodes
        if hasattr(n, "position") and hasattr(n, "fov")
    ]
    imported_list = ", ".join(imported_cam_names) or "(none)"
    plural = "s" if len(imported_cam_names) != 1 else ""

    flame.messages.show_in_dialog(
        title="Import Camera from Blender",
        message=(
            f"Imported {n_frames}-frame camera{plural} into "
            f"'{_val(action_node.name)}':\n"
            f"  {imported_list}\n"
            f"\n"
            f"Target '{target_name}' preserved; remove manually if desired."
        ),
        type="info", buttons=["OK"])


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
                {
                    "name": "Export Camera to Blender",
                    "isVisible": _scope_batch_action,
                    "execute": _export_camera_to_blender,
                },
                {
                    "name": "Import Camera from Blender",
                    "isVisible": _scope_batch_action,
                    "execute": _import_camera_from_blender,
                },
            ],
        }
    ]
