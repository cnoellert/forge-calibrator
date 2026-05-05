"""
Flame Camera Calibrator — PySide2 VP line tool with live camera solve.

Install: copy this directory to /opt/Autodesk/shared/python/camera_match/

Right-click a Clip in Batch > FORGE > Open Camera Calibrator
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

    Returns (img_rgb_uint8, width, height) on success.

    On failure returns ``(None, reason, None)`` where ``reason`` is:
        - ``None`` — Wiretap / extract_frame_bytes failure (media path
          inaccessible, missing node_id, CLI exec failed, etc.)
        - ``"unsupported_bit_depth:{bd}"`` — Wiretap delivered bytes BUT
          ``decode_raw_rgb_buffer`` rejected the buffer because the
          bit_depth is not in {8, 10, 12, 16, 32} (or the buffer was
          truncated). Callers must check ``isinstance(width, str)``
          before treating the second tuple slot as an int.

    The overload of the second slot (int width OR str reason code) is
    deliberate: every other caller in the file already early-returns on
    ``img_rgb is None``, so the change is backward-compatible. Only
    ``_open_camera_match`` reads the second slot on the failure path
    (to branch the dialog message — see flame/camera_match_hook.py near
    line 305)."""
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

    # Raw buffer path: Wiretap's bottom-up, channel-order-quirked float (or
    # uint8) dump. None here means either the bit_depth isn't in our supported
    # set {8, 10, 12, 16, 32} or the buffer is truncated. Surface a reason
    # code in the second tuple slot so the caller can show an actionable
    # dialog ("unsupported bit-depth" vs "media path inaccessible").
    arr = decode_raw_rgb_buffer(raw, w, h, bit_depth)
    if arr is None:
        print(f"decode_raw_rgb_buffer rejected buffer "
              f"({len(raw)} bytes, {w}x{h}, bit_depth={bit_depth})")
        return None, f"unsupported_bit_depth:{bit_depth}", None

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

# FORGE palette — matches forge_cv_align. Hoisted to module level (Plan
# 04.4-02 / RESEARCH Pitfall 5) so module-level dialogs like _pick_camera
# can reference it without NameError. The original definition lived inside
# _open_camera_match's body; the inner-scope copy was removed when this
# constant was hoisted.
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
        # img_w carries either None (media-path / Wiretap failure) or a
        # reason code string ("unsupported_bit_depth:{bd}" — decoder
        # rejected the buffer). Branch the dialog message accordingly so
        # the user gets an actionable error, not the generic "media path"
        # text on a clip whose media is fine but whose bit-depth isn't
        # supported. See _read_source_frame's docstring for the contract.
        if isinstance(img_w, str) and img_w.startswith("unsupported_bit_depth:"):
            bd = img_w.split(":", 1)[1]
            message = (f"Camera Calibrator does not yet support "
                       f"{bd}-bit clips. Supported bit-depths: 8, 10, 12, 16, 32. "
                       f"If this clip really is one of those, please file a bug.")
        else:
            message = ("Could not read frame from clip source. "
                       "Check the clip's media path is accessible.")
        flame.messages.show_in_dialog(
            title="Camera Calibrator",
            message=message,
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

    # _FORGE_SS hoisted to module scope (Plan 04.4-02 / RESEARCH Pitfall 5).
    # The CameraMatchWindow.setStyleSheet call below this comment still
    # resolves — it now reads the module global _FORGE_SS instead of an
    # inner-scope local.

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
            """Return two unit world-axis vectors that span the VP-defined plane,
            plus the +world-direction of the missing third axis.

            The third axis is always the +direction of the missing world-axis
            letter, NOT cross(a, b). cross(a, b) is sign-flipped on anti-cyclic
            letter pairs (X-Z, Y-X, Z-Y) — using it here would draw the
            third-axis arrow in the OPPOSITE direction from what its
            "+missing-letter" label downstream (line ~1040) implies. The
            solver's own world-axis math (forge_core/solver/solver.py:
            axis_assignment_matrix) is on a different code path and is
            unaffected by this overlay choice.
            """
            import numpy as np
            # Axis index // 2: 0 → X family, 1 → Y, 2 → Z
            ax_vecs = [
                np.array([1.0, 0.0, 0.0]),  # X
                np.array([0.0, 1.0, 0.0]),  # Y
                np.array([0.0, 0.0, 1.0]),  # Z
            ]
            a_idx = self.ax1 // 2
            b_idx = self.ax2 // 2
            a = ax_vecs[a_idx]
            b = ax_vecs[b_idx]
            third_idx = ({0, 1, 2} - {a_idx, b_idx}).pop()
            c = ax_vecs[third_idx]
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
            self.setWindowTitle("FORGE — Camera Calibrator")
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
            header = QtWidgets.QLabel("Camera Calibrator")
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
                    # Append a synthetic sentinel for the "Create new Action"
                    # option. _pick_camera takes (action, cam, label) tuples
                    # and returns the picked tuple unchanged, so we detect
                    # the sentinel by None action/cam after the dialog returns.
                    # Plan 04.4-03: replaces the prior bare-style picker
                    # dialog with the FORGE-styled _pick_camera so the
                    # Apply Camera picker matches the Export picker
                    # visually.
                    _CREATE_NEW_LABEL = "Create new Action"
                    choices = list(cameras) + [(None, None, _CREATE_NEW_LABEL)]
                    picked = _pick_camera(choices, "Apply Camera")
                    if picked is None:
                        return
                    sel_action, sel_cam, sel_label = picked
                    if sel_label == _CREATE_NEW_LABEL:
                        action = flame.batch.create_node("Action")
                        cam = action.nodes[0]
                        created_new_action = True
                    else:
                        action = sel_action
                        cam = sel_cam
                else:
                    action = flame.batch.create_node("Action")
                    cam = action.nodes[0]
                    created_new_action = True

                # Force Free rig mode. Without this, Flame's default creation
                # path produces a Target-rig camera whose `position` /
                # `rotation` / `fov` are interpreted relative to an aim
                # target rather than as absolute world transforms — the
                # calibrator's solver outputs world-frame Free-rig values,
                # so Target-rig defaults silently corrupt the result.
                # Reverts the 04.2-02 deletion (commit 19e6d17): that
                # commit's probe missed `target_mode` in `cam.attributes`,
                # but live re-probe 2026-04-28 confirmed the attribute is
                # a real PyAttribute on Flame 2026.2.1 (cam.attributes
                # listing includes "target_mode" at position 13). Defensive
                # try/except in case the attribute is genuinely missing on
                # other Flame versions — Free-rig is the long-running
                # default contract, not a hard requirement.
                try:
                    cam.target_mode.set_value(False)
                except Exception:
                    pass

                # Camera transform — solver now returns the full world position,
                # computed so that world origin projects to the origin control
                # pixel at a fixed distance along the view ray.
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
    """Launch the Camera Calibrator window for the selected clip.

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
            title="Camera Calibrator",
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


# Flame project fps labels — mirrored from forge_sender/__init__.py _FLAME_FPS_LABELS
# and tools/blender/bake_camera.py _FLAME_FPS_LABELS. The stamp written here feeds
# the forge_sender ladder step 1 (cam.data.get("forge_bake_frame_rate")); it MUST
# be one of these label strings for step 1 to accept it.
_FLAME_FPS_LABELS = (
    ("23.976 fps", 23.976),
    ("24 fps", 24.0),
    ("25 fps", 25.0),
    ("29.97 fps", 29.97),
    ("30 fps", 30.0),
    ("48 fps", 48.0),
    ("50 fps", 50.0),
    ("59.94 fps", 59.94),
    ("60 fps", 60.0),
)


# _is_animated_camera was removed 2026-04-23 along with the detect-and-route
# static-JSON branch. Both static and animated cameras now route through
# Flame's native export_fbx(bake_animation=True) which correctly handles
# aim-rig orientation (aim+up+roll → Euler) that the old static-JSON path
# discarded. See memory/flame_fbx_empty_block_contract.md + the debug
# sessions in .planning/debug/resolved/ for the hotfix chain that made
# the unified path reliable.


def _resolve_flame_project_fps_label() -> str:
    """Return the Flame project frame rate as a _FLAME_FPS_LABELS string.

    Mechanism: D-12 conservative default (bridge-offline probe deferred).
    Attempts flame.batch.frame_rate.get_value() first (may be a NoneType
    slot on Flame 2026.2.1 per Phase 2 D-19); falls back to '24 fps' with
    a loud stderr warning — never silent.

    D-14 fallback chain:
        1. flame.batch.frame_rate.get_value() — may be NoneType on 2026.2.1
        2. '24 fps' + stderr warning (ABSOLUTE LAST RESORT; never silent)

    Returns a label from _FLAME_FPS_LABELS or a raw '<num> fps' string
    if the source is a numeric with no label match within 0.1 tolerance.
    """
    import sys as _sys

    def _numeric_to_label(raw) -> str:
        """Coerce a raw fps value (label string or numeric) to a label."""
        raw_str = str(raw).strip()
        # If it's already a label string, return as-is.
        for label, _ in _FLAME_FPS_LABELS:
            if raw_str == label:
                return label
        # Try numeric coercion.
        try:
            fps_float = float(raw_str)
        except (ValueError, TypeError):
            return raw_str  # unknown format; pass through
        for label, numeric in _FLAME_FPS_LABELS:
            if abs(fps_float - numeric) < 0.1:
                return label
        # No match — stamp a raw label string; forge_sender ladder falls to step 2.
        return f"{fps_float} fps"

    try:
        import flame as _flame
        raw = _flame.batch.frame_rate
        if raw is not None and hasattr(raw, "get_value"):
            val = raw.get_value()
            if val is not None:
                return _numeric_to_label(val)
        elif raw is not None and not hasattr(raw, "get_value"):
            return _numeric_to_label(raw)
    except Exception:
        pass

    # D-14: loud fallback, never silent.
    print(
        "_resolve_flame_project_fps_label: falling back to '24 fps' — "
        "no Flame project fps source available",
        file=_sys.stderr,
    )
    return "24 fps"


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


def _scope_action_camera(selection):
    """True when any selected item is a non-Perspective Camera PyCoNode
    inside an Action schematic. Used as `isVisible` for
    get_action_custom_ui_actions (added in Plan 04.4-03).

    CRITICAL (RESEARCH §Pitfall 1): in get_action_custom_ui_actions
    callbacks, item.type is a plain Python str — NOT a PyAttribute.
    Compare with `item.type == "Camera"` directly. Calling .get_value()
    raises AttributeError, the try/except below swallows it, and the
    menu silently never appears. The Wave 0 test
    test_scope_action_camera_does_not_call_get_value_on_type guards
    against re-introducing the .get_value() call.

    Camera variants (GAP-04.4-UAT-05, 2026-04-27): Flame distinguishes
    `"Camera"` (free) from `"Camera 3D"` (3D rig). Both expose the same
    position/rotation/fov/focal API and both round-trip cleanly through
    `action.export_fbx(only_selected_nodes=True)` (verified via bridge
    probe). Allowlist both type strings here so the menu surfaces on
    either variant.
    """
    import flame
    for item in selection:
        try:
            if (isinstance(item, flame.PyCoNode)
                    and item.type in ("Camera", "Camera 3D")
                    and item.name.get_value() != "Perspective"):
                return True
        except Exception:
            continue
    return False


def _find_cam_in_action_nodes(action, cam_name):
    """Return the first non-Perspective Camera in ``action.nodes`` whose
    name matches ``cam_name``, or None if no match.

    Used by ``_first_camera_in_action_selection`` Steps 2 and 3 to obtain
    the camera wrapper from ``action.nodes`` after resolving the Action
    by name. Downstream ``action.selected_nodes.set_value([cam])`` needs
    the wrapper that lives in ``action.nodes`` — set_value silently
    no-ops when handed a wrapper from a different context (e.g. the cam
    object Flame surfaces in a hook-selection list), which produces an
    empty FBX and cascades to "no cameras found named '<X>'" downstream.

    `cam_name` may be None (caller couldn't read it) — in that case we
    still return the first non-Perspective Camera in action.nodes as a
    last-ditch fallback. This is best-effort; the caller still has the
    diagnostic-write path on total failure.
    """
    if action is None or not hasattr(action, "nodes"):
        return None
    try:
        for inode in action.nodes:
            try:
                t = inode.type
                t_val = t.get_value() if hasattr(t, "get_value") else str(t)
                if t_val not in ("Camera", "Camera 3D"):
                    continue
                n_name = (inode.name.get_value()
                          if hasattr(inode.name, "get_value")
                          else str(inode.name))
                if n_name == "Perspective":
                    continue
                if cam_name is None or n_name == cam_name:
                    return inode
            except Exception:
                continue
    except Exception:
        return None
    return None


def _first_camera_in_action_selection(selection):
    """Return (action_node, cam_node) for the first non-Perspective Camera
    in selection, or (None, None) if no such item.

    Three-step resolution (extended 2026-04-28 after live diag on portofino
    + flame-01 reproduced the GAP-04.4-UAT-04 'NoneType' regression on
    cam.parent + on the identity-comparison fallback):

    1. Fast path: try ``cam.parent`` directly. Filter requires the parent
       to be non-None, expose ``.nodes``, AND have ``callable(.export_fbx)``.
       In hook callback context the cam.parent wrapper is sometimes
       degraded to the ``PyActionFamilyNode`` base class (without
       ``.export_fbx``) even though the bridge thread sees the
       specialized ``PyActionNode``. This filter rejects the degraded
       wrapper.

    2. Promote-by-name path (NEW 2026-04-28): if the fast path's parent is
       degraded but its ``.name`` is still readable, use
       ``flame.batch.get_node(parent_name)`` to look up the specialized
       wrapper. Bridge probe 2026-04-28 confirmed ``flame.batch.get_node``
       returns the healthy ``PyActionNode`` (``export_fbx_callable: true``)
       even when the iteration in step 3 surfaces wrappers that don't
       match by Python identity.

    3. Scan fallback: walk ``flame.batch.nodes`` for an Action that
       contains the cam. Try Python identity first (``inode is item``)
       to preserve disambiguation when two Actions share a camera name.
       If identity match fails (wrapper instances differ between hook
       selection and ``action.nodes`` — observed across hook-callback
       boundary on flame-01 RHEL 9 + portofino macOS arm64 2026-04-28),
       fall through to a name match. Disambiguation prefers an Action
       whose name matches ``cam.parent.name`` if any.

    On total failure (all three steps return no Action), write a
    diagnostic JSON to ``/tmp/forge_camera_match_diag.json`` capturing the
    hook-context wrapper-class shapes so the next failure carries its own
    forensic evidence — bridge thread can't see hook context, so the
    instrumentation has to live here.

    Pitfall 1 (RESEARCH §P-02): on the action-schematic side, ``item.type``
    is a plain Python str — NEVER call ``.get_value()`` on it. The
    duck-typed PyAttribute handling applies only to ``flame.batch.nodes``
    items inside step 3 (where the batch-context shape exposes ``.type``
    as a PyAttribute).
    """
    import flame
    for item in selection:
        try:
            if not (isinstance(item, flame.PyCoNode)
                    and item.type in ("Camera", "Camera 3D")
                    and item.name.get_value() != "Perspective"):
                continue
        except Exception:
            continue

        # Step 1: cam.parent direct (fast path).
        parent = None
        try:
            parent = item.parent
        except Exception:
            parent = None
        if (parent is not None
                and hasattr(parent, "nodes")
                and callable(getattr(parent, "export_fbx", None))):
            return parent, item

        # Step 2: promote-by-name. cam.parent may be a degraded base-class
        # proxy in hook context — its .name still reads cleanly even when
        # .export_fbx is None. flame.batch.get_node(parent_name) returns
        # the specialized PyActionNode wrapper.
        parent_name = None
        if parent is not None:
            try:
                parent_name = (parent.name.get_value()
                               if hasattr(parent.name, "get_value")
                               else str(parent.name))
            except Exception:
                parent_name = None
        # Try to read cam_name early — needed for both Step 2 (find the
        # cam inside promoted.nodes by name) and Step 3 (name match in
        # batch.nodes scan). Selection wrappers and action.nodes wrappers
        # may be different Python objects, so the downstream
        # `action.selected_nodes.set_value([cam])` call requires the
        # action.nodes wrapper — set_value silently no-ops when handed
        # a wrapper that isn't in action.nodes (verified 2026-04-28: the
        # FBX exported under those conditions has zero Model:: blocks
        # and only the FBX SDK's stock 'Producer Perspective').
        try:
            cam_name = item.name.get_value()
        except Exception:
            cam_name = None

        if parent_name and hasattr(flame.batch, "get_node"):
            try:
                promoted = flame.batch.get_node(parent_name)
            except Exception:
                promoted = None
            if (promoted is not None
                    and callable(getattr(promoted, "export_fbx", None))
                    and hasattr(promoted, "nodes")):
                target_cam = _find_cam_in_action_nodes(promoted, cam_name)
                if target_cam is not None:
                    return promoted, target_cam
                # Couldn't find the cam by name in promoted.nodes — that's
                # surprising (the broken parent at least had a usable name
                # so the action match is likely correct). Skip rather than
                # return a wrapper that downstream can't select; Step 3
                # (name match in batch.nodes scan) is the next attempt.

        # Step 3: flame.batch.nodes scan with identity-then-name match.
        # Identity match preserves disambiguation when two Actions share
        # a camera name. Name match handles the wrapper-instance mismatch
        # observed in hook callback context. parent_name (if known) is
        # used to disambiguate name matches across multiple Actions.
        identity_hit = None
        # name_hits entries: (action_node, action_side_cam, disambiguated)
        # action_side_cam is the wrapper from action.nodes — required by
        # action.selected_nodes.set_value downstream.
        name_hits = []
        try:
            for n in flame.batch.nodes:
                try:
                    t = n.type
                    type_val = (t.get_value()
                                if hasattr(t, "get_value")
                                else str(t))
                    if type_val != "Action":
                        continue
                    if not hasattr(n, "nodes"):
                        continue
                    if not callable(getattr(n, "export_fbx", None)):
                        continue
                    n_name = None
                    try:
                        n_name = (n.name.get_value()
                                  if hasattr(n.name, "get_value")
                                  else str(n.name))
                    except Exception:
                        n_name = None
                    for inode in n.nodes:
                        # Identity first — exact match wins immediately.
                        if inode is item:
                            identity_hit = (n, inode)
                            break
                        # Name match candidate — only Cameras matching
                        # by name. Disambiguate via parent_name when set.
                        try:
                            inode_t = inode.type
                            inode_t_val = (inode_t.get_value()
                                           if hasattr(inode_t, "get_value")
                                           else str(inode_t))
                            inode_name = (inode.name.get_value()
                                          if hasattr(inode.name, "get_value")
                                          else str(inode.name))
                        except Exception:
                            continue
                        if (cam_name is not None
                                and inode_t_val in ("Camera", "Camera 3D")
                                and inode_name == cam_name):
                            disambiguated = (parent_name is not None
                                             and n_name == parent_name)
                            name_hits.append((n, inode, disambiguated))
                    if identity_hit is not None:
                        break
                except Exception:
                    continue
        except Exception:
            pass

        if identity_hit is not None:
            return identity_hit  # already (action, action_side_cam)
        if name_hits:
            # Prefer disambiguated hit (Action whose name matches
            # cam.parent.name) over a generic name match. If multiple
            # disambiguated hits, take the first; if none, take the first
            # generic. Both cases beat the cryptic NoneType.
            for cand_action, cand_cam, disambiguated in name_hits:
                if disambiguated:
                    return cand_action, cand_cam
            return name_hits[0][0], name_hits[0][1]

        # Total resolution failure — capture diagnostic context for the
        # forensic record before falling through to the caller's error
        # dialog. Bridge thread can't see hook context, so we write the
        # JSON here. Best-effort; never raise.
        try:
            _dump_camera_resolution_diag(
                selection=selection,
                item=item,
                parent=parent,
                parent_name=parent_name,
                cam_name=cam_name,
                flame_module=flame,
            )
        except Exception:
            pass

        # Selection cam exists but no containing Action found — return
        # the cam alone with action=None so the caller can surface a
        # diagnostic dialog (better than silent failure). The existing
        # caller `_export_camera_from_action_selection` checks
        # `action_node is None` and shows a Tier-1 popup, so (None, item)
        # is treated identically to (None, None).
        return None, item

    return None, None


def _dump_camera_resolution_diag(*, selection, item, parent, parent_name,
                                 cam_name, flame_module):
    """Write a one-shot JSON diagnostic to /tmp/forge_camera_match_diag.json
    capturing the hook-callback-context wrapper-class shape at the moment
    `_first_camera_in_action_selection` failed to find a usable Action.

    Bridge-thread probes can't observe hook callback context — wrapper
    classes and identity invariants observed there don't generalise to
    the main-thread hook callback. This dump runs INSIDE the hook so
    its readings reflect the actual failing state. Overwrite-on-write;
    one file per failed resolution. Never raises.
    """
    import json
    import os
    import time

    def _safe(call, default="<err>"):
        try:
            return call()
        except Exception as e:
            return f"<err: {e!r}>"

    def _node_summary(n):
        return {
            "class": type(n).__name__,
            "mro": [c.__name__ for c in type(n).__mro__],
            "type": _safe(lambda: (n.type.get_value()
                                   if hasattr(n.type, "get_value")
                                   else str(n.type))),
            "name": _safe(lambda: (n.name.get_value()
                                   if hasattr(n.name, "get_value")
                                   else str(n.name))),
            "has_nodes": hasattr(n, "nodes"),
            "has_export_fbx_attr": hasattr(n, "export_fbx"),
            "export_fbx_is_None": getattr(n, "export_fbx", "__missing__") is None,
            "export_fbx_callable": callable(getattr(n, "export_fbx", None)),
            "export_fbx_repr": repr(getattr(n, "export_fbx", "__missing__"))[:160],
            "id": id(n),
        }

    diag = {
        "schema": "forge_camera_match_diag.v1",
        "timestamp": time.time(),
        "context": "hook_callback (_first_camera_in_action_selection)",
        "flame_attrs": [a for a in dir(flame_module)
                        if "Action" in a or "Camera" in a],
        "selection": [],
        "parent": None,
        "parent_name": parent_name,
        "cam_name": cam_name,
        "batch_nodes": [],
        "promote_by_name_attempt": None,
    }

    for sel in selection:
        info = {"class": type(sel).__name__,
                "mro": [c.__name__ for c in type(sel).__mro__],
                "id": id(sel)}
        info["type"] = _safe(lambda: (sel.type.get_value()
                                       if hasattr(sel.type, "get_value")
                                       else str(sel.type)))
        info["name"] = _safe(lambda: (sel.name.get_value()
                                       if hasattr(sel.name, "get_value")
                                       else str(sel.name)))
        diag["selection"].append(info)

    if parent is not None:
        p_info = _node_summary(parent)
        p_info["is_item_parent_attr"] = True
        diag["parent"] = p_info

    # If we have a parent_name, retry the get_node call here so the diag
    # records what the API returned at the moment of failure (may differ
    # from what step 2 saw if state mutates between calls).
    if parent_name and hasattr(flame_module.batch, "get_node"):
        try:
            promoted = flame_module.batch.get_node(parent_name)
            if promoted is None:
                diag["promote_by_name_attempt"] = {"result": "None"}
            else:
                p_summary = _node_summary(promoted)
                p_summary["promoted_for_name"] = parent_name
                diag["promote_by_name_attempt"] = p_summary
        except Exception as e:
            diag["promote_by_name_attempt"] = {"error": repr(e)}

    try:
        for n in flame_module.batch.nodes:
            info = _node_summary(n)
            try:
                if info.get("type") == "Action" and info["has_nodes"]:
                    info["children"] = []
                    for child in n.nodes:
                        info["children"].append({
                            "class": type(child).__name__,
                            "type": _safe(lambda: (child.type.get_value()
                                                    if hasattr(child.type, "get_value")
                                                    else str(child.type))),
                            "name": _safe(lambda: (child.name.get_value()
                                                    if hasattr(child.name, "get_value")
                                                    else str(child.name))),
                            "id": id(child),
                            "is_selection_item": child is item,
                        })
            except Exception as e:
                info["children_err"] = repr(e)
            diag["batch_nodes"].append(info)
    except Exception as e:
        diag["batch_nodes_err"] = repr(e)

    out_path = os.environ.get(
        "FORGE_CAMERA_MATCH_DIAG_PATH",
        "/tmp/forge_camera_match_diag.json",
    )
    with open(out_path, "w") as f:
        json.dump(diag, f, indent=2, default=str)


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


# RESEARCH Pitfall 5: _FORGE_SS MUST be at module level by the time this
# function is called. The Plan 04.4-02 hoist moved it from inside
# _open_camera_match's body to module scope so this reference resolves
# without NameError.
# UI-SPEC §A-1: keyboard semantics — Enter accepts (default button),
# Escape rejects (QDialog default), double-click on item also accepts
# via the itemDoubleClicked → dialog.accept signal wiring below.
def _pick_camera(cameras, dialog_title):
    """FORGE-styled camera picker. Returns (action, cam, label) or None.

    No dialog shown if 0 or 1 cameras (D-01 early exit). Dialog uses
    module-level _FORGE_SS (hoisted in this same plan). Window title is
    em-dash framed: 'FORGE — <title>'.
    """
    if not cameras:
        return None
    if len(cameras) == 1:
        return cameras[0]

    from PySide6.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout,
        QLabel, QListWidget, QPushButton, QFrame,
    )
    from PySide6.QtCore import Qt  # noqa: F401  (kept for future use; harmless)

    dialog = QDialog()
    dialog.setWindowTitle(f"FORGE — {dialog_title}")
    dialog.setMinimumWidth(360)
    dialog.setStyleSheet(_FORGE_SS)

    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(16, 14, 16, 14)
    layout.setSpacing(12)

    header = QLabel(dialog_title)
    header.setStyleSheet("color: #E87E24; font-weight: bold; font-size: 14px;")
    layout.addWidget(header)

    sep1 = QFrame()
    sep1.setFrameShape(QFrame.HLine)
    sep1.setObjectName("sep")
    layout.addWidget(sep1)

    lst = QListWidget()
    lst.setStyleSheet(
        "QListWidget { background: #1e2028; color: #ccc; border: 1px solid #555; "
        "  border-radius: 3px; font-size: 12px; }"
        "QListWidget::item:selected { background: #E87E24; color: #fff; }"
    )
    choices = [c[2] for c in cameras]
    lst.addItems(choices)
    lst.setCurrentRow(0)
    layout.addWidget(lst)

    sep2 = QFrame()
    sep2.setFrameShape(QFrame.HLine)
    sep2.setObjectName("sep")
    layout.addWidget(sep2)

    btn_row = QHBoxLayout()
    btn_row.setSpacing(8)
    btn_row.addStretch()

    cancel_btn = QPushButton("Don't Export")
    cancel_btn.clicked.connect(dialog.reject)
    btn_row.addWidget(cancel_btn)

    ok_btn = QPushButton("Select Camera")
    ok_btn.setObjectName("primary")
    ok_btn.setDefault(True)
    ok_btn.clicked.connect(dialog.accept)
    btn_row.addWidget(ok_btn)

    layout.addLayout(btn_row)

    lst.itemDoubleClicked.connect(lambda _: dialog.accept())

    if dialog.exec() != QDialog.Accepted:
        return None
    return cameras[lst.currentRow()]


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
      - Strip leading dots so names like ``".hidden"`` do not produce
        Unix dotfiles the user's file browser silently hides, and names
        like ``"."`` / ``".."`` / ``"..."`` cannot slip in as
        traversal-looking path components inside the final
        ``{action}_{cam}.blend``.
      - Require at least one alphanumeric character in the result. All-
        punctuation inputs (e.g. ``"---"``, ``"___"``, ``"."``) fall
        back to ``"unnamed"`` so the caller never builds a degenerate
        ``_{cam}.blend`` / ``{action}_.blend`` or a file whose name is
        only separators.

    Never raises; `None` and non-str inputs coerce via `str()`.
    """
    safe = _SANITIZE_NAME_RE.sub("_", str(name))[:64]
    # Strip leading dots first so ``.hidden`` / ``.`` / ``..`` never
    # produce Unix dotfiles or traversal-looking components. The
    # alnum-required predicate below then catches all-punctuation
    # inputs (``---``, ``___``, ``...``) the old ``strip("_")`` fallback
    # missed.
    safe = safe.lstrip(".")
    if not any(c.isalnum() for c in safe):
        return "unnamed"
    return safe


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
      2. flame.batch.width/height -- batch-level fallback; same one-liner
         (`int(flame.batch.width.get_value())`) was used by the legacy
         Matchbox-era apply_solve.py before its removal in
         quick-260505-mrv (Phase B forge family cleanup).
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

    # Tier 2 — flame.batch.width/height (legacy Matchbox-era apply_solve.py
    # used the same one-liner before its removal in quick-260505-mrv).
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


def _export_camera_to_blender(selection, *, flame_to_blender_scale=1000.0):
    """Right-click handler for an Action node in Batch — Action-scope path.

    Flow: right-click the Action holding your solved camera
    -> auto-pick the target camera (dialog ONLY if Action has 2+ cameras)
    -> delegate to _export_camera_pipeline for the shared
       plate-resolution / bake / Blender-launch sequence.

    Scope is `_scope_batch_action`, so this menu item appears on Action
    right-clicks. The Camera-scope sibling
    (_export_camera_from_action_selection, Plan 04.4-02) bypasses
    _pick_camera and feeds (action, cam, label) directly into the
    shared pipeline. D-05: single resolution helper, two thin wrappers.

    Default `flame_to_blender_scale=1000.0` is the new studio sweet spot
    (Interior — per quick 260501-rus; supersedes 260501-em8's 100.0
    Soundstage default); ladder entries override via
    `_make_export_callback(scale)` (per quick 260501-i31).
    """
    import flame

    # --- Selection / action / camera pick (Action-scope head) ---
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
        return  # user cancelled the 2+-camera picker; no dialog needed
    action, cam, label = picked

    _export_camera_pipeline(
        action, cam, label,
        flame_to_blender_scale=flame_to_blender_scale,
    )


# RESEARCH §P-02 + Open Question OQ-2: cam.parent returning the containing
# PyActionNode is verified via bridge probe but not in the actual hook
# callback context. If UAT shows action_node is None despite a camera
# being right-clicked, the fallback is to scan flame.batch.nodes for an
# Action whose .nodes contains cam_node. NOT implemented here — defer to
# a quick-fix patch if UAT trips it.
# RESEARCH §Pitfall 4: this handler is wired into the menu only AFTER
# Plan 04.4-03 ships and a Flame restart picks up the new
# get_action_custom_ui_actions function. After Plan 04.4-02 lands, this
# code is present but unreachable from the menu.
def _export_camera_from_action_selection(selection, *, flame_to_blender_scale=1000.0):
    """Right-click handler for a Camera PyCoNode inside an Action's
    schematic — Camera-scope path. Bypasses _pick_camera entirely:
    the user has already indicated which camera by right-clicking it.

    Resolution: cam.parent → containing PyActionNode (RESEARCH §P-02).
    The label format matches _find_action_cameras' f"{action} > {cam}"
    shape so the pipeline's downstream code (filename construction,
    info-dialog text) sees identical input regardless of entry point.

    Default `flame_to_blender_scale=1000.0` is the new studio sweet spot
    (Interior — per quick 260501-rus); ladder entries override via
    `_make_export_callback(scale, camera_scope=True)` (per quick 260501-i31).
    """
    import flame
    action_node, cam_node = _first_camera_in_action_selection(selection)
    if action_node is None or cam_node is None:
        flame.messages.show_in_dialog(
            title="Export Camera to Blender",
            message="Right-click a Camera node inside an Action's "
                    "schematic. Perspective cameras are not supported.",
            type="error", buttons=["OK"])
        return

    # Mirror _find_action_cameras' label format (':1812' — uses '>' not em-dash)
    # so downstream _safe_filename / info-dialog text is identical between
    # entry points.
    label = f"{_val(action_node.name)} > {_val(cam_node.name)}"

    _export_camera_pipeline(
        action_node, cam_node, label,
        flame_to_blender_scale=flame_to_blender_scale,
    )


# Discrete log10 7-stop ladder for the right-click menu entries —
# must match tools/blender/bake_camera.py::_FLAME_TO_BLENDER_SCALE_LADDER.
# Default-entry hardcode of 1000.0 is the studio-default convenience
# entry (Interior — per quick 260501-rus); these are the additional
# artist-pickable stops surfaced via _make_export_callback (per quick
# 260501-i31).
_LADDER_MENU_STOPS = (1.0, 10.0, 100.0, 1000.0, 10000.0, 100000.0, 1000000.0)


def _make_export_callback(scale, *, camera_scope=False):
    """Return a single-arg `(selection,)` callback that fires the
    appropriate export entry point with `flame_to_blender_scale=scale`
    injected at the `fbx_to_v5_json` call site.

    Closure-over-scale lets each ladder stop be one menu entry without
    per-stop helpers. NO dialog, NO popup — fires the export immediately
    (per quick 260501-i31 spec).

    `camera_scope=False` (default) -> wraps `_export_camera_to_blender`
      (Batch right-click on Action node).
    `camera_scope=True`            -> wraps
      `_export_camera_from_action_selection` (Action-schematic
      right-click on Camera node).

    Each call to `_make_export_callback(0.01)`, `_make_export_callback(0.1)`,
    etc. produces a distinct closure with its own captured `scale`.
    """

    def _cb(selection):
        if camera_scope:
            return _export_camera_from_action_selection(
                selection, flame_to_blender_scale=scale)
        return _export_camera_to_blender(
            selection, flame_to_blender_scale=scale)

    return _cb


# Quick 260501-knl: replace i31's 5-sibling ladder menu with a single
# entry per surface that opens a forge-themed scale picker dialog.
# The wrappers below are the new menu callables; the dialog lives in
# flame/scale_picker_dialog.py.
#
# Lazy import of pick_scale: same pattern as _pick_camera's lazy
# PySide6 import — keeps the test path that stubs PySide6 from having
# to also stub the dialog module at module-load time.
def _export_camera_to_blender_with_picker(selection):
    """Action-scope menu wrapper. Opens the scale picker; on a chosen
    scale, fires _export_camera_to_blender(selection, flame_to_blender_scale=scale).
    On ESC/cancel, returns silently with no export call.

    Studio default is 1000.0 — the dialog's 'Interior · ×10³' button is
    highlighted as primary so the artist can hit Enter for the common case.
    """
    from scale_picker_dialog import pick_scale
    scale = pick_scale(default=1000.0)
    if scale is None:
        return  # ESC / cancel / X — no export
    _export_camera_to_blender(selection, flame_to_blender_scale=scale)


def _export_camera_from_action_selection_with_picker(selection):
    """Camera-scope menu wrapper. Opens the scale picker; on a chosen
    scale, fires _export_camera_from_action_selection(selection,
    flame_to_blender_scale=scale). On ESC/cancel, returns silently."""
    from scale_picker_dialog import pick_scale
    scale = pick_scale(default=1000.0)
    if scale is None:
        return  # ESC / cancel / X — no export
    _export_camera_from_action_selection(
        selection, flame_to_blender_scale=scale)


def _export_camera_pipeline(action, cam, label, *, flame_to_blender_scale=1000.0):
    """Shared export pipeline used by both right-click entry points
    (Batch Action-scope and Action-schematic Camera-scope).

    Caller resolves (action, cam, label) by whatever means and hands it
    here; this function owns the plate-resolution / bake / Blender-launch
    sequence. Extracted from _export_camera_to_blender per D-05 (single
    resolution helper) so both entry points share one implementation.

    `flame_to_blender_scale` is the divisor baked into the v5 JSON
    `flame_to_blender_scale` field (per 260501-dpa); default 1000.0 is
    the studio-default convenience entry (Interior — per the 260501-rus
    flip; supersedes 260501-em8's 100.0 Soundstage default). The
    right-click ladder (260501-i31) passes other values from
    `_LADDER_MENU_STOPS` via `_make_export_callback(scale)`.

    Flow: infer plate resolution via the three-tier fallback
       (_infer_plate_resolution: action.resolution -> batch w/h -> first clip)
    -> bake to a tempfile.mkdtemp(prefix='forge_bake_') dir:
         * ASCII FBX via fbx_io.export_action_cameras_to_fbx
         * v5 JSON via fbx_ascii.fbx_to_v5_json, stamped with
           `forge_bake_action_name` + `forge_bake_camera_name` custom
           properties (D-11) so the Blender-side return trip can look
           up the correct Flame Action
    -> Blender headless bake via blender_bridge.run_bake, producing
       `~/forge-bakes/{action}_{cam}.blend` (filesystem-safe names via
       _sanitize_name_component; raw names stamped into the .blend
       custom properties)
    -> on success, remove the temp dir; on failure, preserve it and
       include its path in the error dialog (D-14)
    -> spawn Blender on the .blend via _launch_blender_on_blend,
       honoring _read_launch_focus_steal() on macOS (EXP-05, D-02)
    -> on launch failure, fall back to reveal_in_file_manager + warning
       dialog (D-03). On success, a single informational dialog
       summarizes the bake and confirms Blender has been launched.

    Zero-dialog rule applies to the HAPPY PATH (single non-Perspective
    camera, all three resolution tiers or one of them succeeds, bake
    + convert + launch all work). Error paths still surface dialogs
    per D-15 — "zero dialogs" is a happy-path goal, not a silencing
    rule.

    `action` is the PyActionNode that owns `cam`; `cam` is the
    PyCoNode for the target Camera; `label` is the human-readable
    identifier ('{action_name} > {cam_name}') for the info dialog.
    """
    _ensure_forge_env()
    _ensure_forge_core_on_path()

    import flame
    import json as _json
    import os
    import shutil
    import subprocess  # imported for CalledProcessError catch below
    import tempfile

    from forge_flame import blender_bridge, fbx_ascii, fbx_io

    # NOTE: The lazy QtWidgets import (previously used for input/file-open
    # dialogs in the prior handler body) has been removed — both dialogs
    # are gone from the new happy path. File-level PySide6 imports at the
    # top of camera_match_hook.py are UNCHANGED; other handlers still use
    # them.

    # `action_node` here is the same object as `action` — the original
    # head used both names. _infer_plate_resolution takes the Action node.
    action_node = action

    # --- Plate resolution — three-tier fallback (D-07, D-08) ---
    try:
        width, height = _infer_plate_resolution(action_node)
    except PlateResolutionUnavailable as e:
        flame.messages.show_in_dialog(
            title="Export Camera to Blender",
            message=f"Could not infer plate resolution.\n\n{e}",
            type="error", buttons=["OK"])
        return

    # --- Filesystem-safe name components (Task 2) ---
    # Raw names (unsanitized) are stamped into the .blend's custom
    # properties below per D-11; sanitized names are ONLY for the path.
    raw_action_name = _val(action_node.name)
    raw_cam_name = _val(cam.name)
    safe_action = _sanitize_name_component(raw_action_name)
    safe_cam = _sanitize_name_component(raw_cam_name)

    # --- Output dir (D-04, D-05 — overwrite on collision) ---
    out_dir = os.path.expanduser("~/forge-bakes")
    os.makedirs(out_dir, exist_ok=True)
    blend_path = os.path.join(out_dir, f"{safe_action}_{safe_cam}.blend")

    # --- Temp dir for intermediates (D-14 — preserve on failure) ---
    temp_dir = tempfile.mkdtemp(prefix="forge_bake_")
    fbx_path = os.path.join(temp_dir, "baked.fbx")
    json_path = os.path.join(temp_dir, "baked.json")

    n_frames = 0  # populated BEFORE success=True so the finally-block cleanup doesn't race the read
    success = False
    try:
        # --- Frame offset / frame start — read FIRST so both branches share it.
        # start_frame drives the static branch's `frame=` kwarg AND the
        # animated branch's frame_offset/frame_start for pre-roll clipping.
        # ONE read of start_frame drives all three values — do NOT duplicate.
        #
        # Fallback semantics: frame_offset=0, frame_start=None, start_frame_int=1
        # on error. Paired (0, None) is the safe no-op for the animated branch.
        # start_frame_int=1 is the conservative default for the static branch.
        # NEVER let an unknown PyAttribute shape crash a working export. ---
        frame_offset = 0
        frame_start = None
        start_frame_int = 1  # conservative default for static-branch frame stamp
        try:
            sf = flame.batch.start_frame.get_value()
            # PyAttribute may return int, float, or string depending on
            # attr type; coerce defensively. int(float(x)) handles
            # "1001", 1001, 1001.0 uniformly.
            start_frame_int = int(float(sf))
            frame_offset = start_frame_int - 1  # shift for KTime 0 pre-roll
            frame_start = start_frame_int       # INCLUSIVE drop of pre-roll
        except Exception:
            frame_offset = 0    # silent fallback; no shift
            frame_start = None  # silent fallback; no clip

        # --- Frame end — drop the single trailing keyframe that
        # bake_animation=True bakes past the user's batch range. Flame
        # emits (end - start + 1) KTimes; after the +start_frame offset
        # above, that's one frame past end (UAT from 260420-uzv: user
        # reported an errant 1101 keyframe on a 1001..1100 batch).
        # Same defensive shape as start_frame above. Fallback is None
        # (NOT 0) — None means "don't clip", preserving pre-fix
        # behavior on any error; 0 would incorrectly drop every frame
        # since the offset-adjusted frames are all >= start_frame. ---
        frame_end = None
        try:
            ef = flame.batch.end_frame.get_value()
            frame_end = int(float(ef))
        except Exception:
            frame_end = None  # silent fallback; None = no clip

        # --- Phase 4.1 item 5: resolve Flame project fps label (D-11 always-stamp) ---
        # Must happen before the detect-and-route branch so BOTH branches
        # can pass fps_label through to their respective JSON writers.
        fps_label = _resolve_flame_project_fps_label()

        # Unified FBX path — static and animated cameras both route
        # through Flame's native export_fbx(bake_animation=True). The
        # static-JSON fast path added in plan 04.1-02 has been removed
        # because: (a) the "no frames in JSON" bug it worked around is
        # now fixed at root (empty-block emit, Takes LocalTime,
        # GlobalSettings TimeSpanStop, expanded KeyAttr), (b) Flame's
        # export_fbx handles aim-rig cameras natively (baking aim+up+
        # roll into Euler rotation), which the static-JSON path did NOT
        # — it discarded aim/roll and produced an orientation-wrong
        # returned camera; (c) the detect-and-route was the source of
        # two debug sessions' worth of misclassification bugs.
        try:
            fbx_io.export_action_cameras_to_fbx(
                action, fbx_path,
                cameras=[cam],
                bake_animation=True,
            )
        except Exception as e:
            flame.messages.show_in_dialog(
                title="Export Camera to Blender",
                message=f"Failed to write FBX:\n{e}\n\n"
                        f"Intermediate files preserved at:\n{temp_dir}",
                type="error", buttons=["OK"])
            return

        # --- FBX -> v5 JSON with custom_properties stamp (Plan 02) ---
        # NOTE: raw_action_name / raw_cam_name are the UNSANITIZED Flame
        # names per D-11. Phase 2's "Send to Flame" looks these up against
        # Flame's Action list, so they MUST match the live Flame names
        # exactly (sanitization is only for filesystem paths above).
        try:
            # film_back_mm=None — let fbx_to_v5_json derive from the
            # FBX's FilmHeight property (Flame's own export writes
            # the camera's true filmback here; typically 16mm
            # Super-16). Pinning 36.0 was the old full-frame parity
            # shortcut; it breaks the Blender→Flame return trip
            # because the round-trip then stamps 36mm onto the
            # original camera.
            fbx_ascii.fbx_to_v5_json(
                fbx_path, json_path,
                width=width, height=height,
                film_back_mm=None,
                frame_rate=fps_label,
                camera_name=raw_cam_name,
                frame_offset=frame_offset,
                frame_start=frame_start,
                frame_end=frame_end,
                custom_properties={
                    "forge_bake_action_name": raw_action_name,
                    "forge_bake_camera_name": raw_cam_name,
                },
                # 1000.0 is the studio default per the 260501-rus flip
                # (Interior — supersedes 260501-em8's 100.0 Soundstage
                # default; a divisor; see bake_camera.py: pos / scale).
                # The dialog (260501-knl) and right-click ladder
                # (260501-i31) let the artist pick other values; the
                # default entry uses the parameter default on
                # _export_camera_pipeline. Per the ladder spec
                # (260501-dpa) this OVERRIDES the `scale=1000.0` CLI
                # arg below at the bake call site (a separate divisor —
                # legacy viewport-nav hack, byte-identical canary).
                flame_to_blender_scale=flame_to_blender_scale,
            )
        except Exception as e:
            flame.messages.show_in_dialog(
                title="Export Camera to Blender",
                message=f"Failed to convert FBX to JSON:\n{e}\n\n"
                        f"Intermediate files preserved at:\n{temp_dir}",
                type="error", buttons=["OK"])
            return

        # --- Blender headless bake (unchanged) ---
        try:
            blender_bridge.run_bake(
                json_path, blend_path,
                camera_name="Camera", scale=1000.0, create_if_missing=True,
            )
        except FileNotFoundError as e:
            flame.messages.show_in_dialog(
                title="Export Camera to Blender",
                message=f"{e}\n\nIntermediate files preserved at:\n{temp_dir}",
                type="error", buttons=["OK"])
            return
        except subprocess.CalledProcessError as e:
            err = (e.stderr or e.stdout or "unknown error").strip()
            flame.messages.show_in_dialog(
                title="Export Camera to Blender",
                message=f"Blender bake failed (exit {e.returncode}):\n\n{err}\n\n"
                        f"Intermediate files preserved at:\n{temp_dir}",
                type="error", buttons=["OK"])
            return

        # --- Frame count read (MUST happen BEFORE success = True) ---
        # temp_dir is still alive here; the finally-block below only
        # removes it when `success` is already True. Reading json_path
        # AFTER `success = True` would race the cleanup and always
        # produce n_frames == 0 on the happy path. Do NOT move this.
        try:
            with open(json_path) as f:
                n_frames = len(_json.load(f).get("frames") or [])
        except Exception:
            # Non-fatal — frame count is cosmetic for the info dialog.
            n_frames = 0

        success = True
    finally:
        # D-14: clean temp dir ONLY on success. On failure, leave it so
        # the user (or support) can inspect the intermediate .fbx/.json.
        if success:
            shutil.rmtree(temp_dir, ignore_errors=True)

    frame_label = f"{n_frames}-frame" + ("" if n_frames == 1 else "s")

    # --- Blender launch spawn (EXP-05, D-02, D-03) ---
    focus_steal = _read_launch_focus_steal()
    try:
        _launch_blender_on_blend(blend_path, focus_steal=focus_steal)
        launch_status = "Blender opened."
    except Exception as e:
        # D-03 fallback: reveal in file manager so the user at least
        # sees where the .blend landed, and surface a warning dialog.
        try:
            blender_bridge.reveal_in_file_manager(blend_path)
        except Exception:
            pass  # reveal is cosmetic; do not shadow the launch error
        flame.messages.show_in_dialog(
            title="Export Camera to Blender",
            message=f"Exported to {blend_path}\n\n"
                    f"Couldn't auto-launch Blender: {e}\n"
                    f"File manager opened to the output folder.",
            type="warning", buttons=["OK"])
        return

    # --- Informational success dialog (happy-path INFO, not a gate) ---
    # This fires AFTER Blender has been launched. Per <specifics> in
    # CONTEXT.md the user-visible surface is the .blend + Blender
    # window; this dialog exists only to summarize what happened.
    flame.messages.show_in_dialog(
        title="Export Camera to Blender",
        message=f"Exported '{label}' ({frame_label})\n"
                f"  plate:  {width}x{height}\n"
                f"  blend:  {blend_path}\n"
                f"  {launch_status}",
        type="info", buttons=["OK"])


# RESEARCH §Pitfall 4: menu structure changes require a full Flame
# restart. The gc/exec live-reload pattern refreshes module globals but
# NOT Flame's cached menu dispatch table. Test this menu surface only
# after `bash install.sh` + Flame restart.
def get_batch_custom_ui_actions():
    """Right-click menu registration for Batch schematic.

    Two-level FORGE/Camera hierarchy. The pattern is the same shape
    forge_cv_align uses in its timeline menu — declare the parent group
    with `hierarchy: []` and an empty `actions` list, then declare each
    child group with `hierarchy: ["FORGE"]`. RESEARCH §P-01's flat
    workaround was based on absence-of-evidence, not a live test;
    sibling tools confirm the dict shape and Flame 2026.2.1 renders it.

    The legacy 'Import' entry (Blender-to-Flame pull) was removed
    (D-06): the Blender-side forge_sender addon is now the sole
    inbound path. Hard cut on install per D-14 — no backwards-compat
    shim.
    """
    return [
        {
            "name": "FORGE",
            "hierarchy": [],
            "actions": [],
        },
        {
            "name": "Camera",
            "hierarchy": ["FORGE"],
            "actions": [
                {
                    "name": "Open Camera Calibrator",
                    "isVisible": _scope_batch_clip,
                    "execute": _launch_camera_match,
                },
                {
                    # Quick 260501-knl: reverted from i31's 6-sibling ladder
                    # to a single entry that opens the forge-themed scale
                    # picker dialog. The wrapper lazy-imports pick_scale
                    # from scale_picker_dialog.py and forwards the chosen
                    # scale to _export_camera_to_blender via the kw-only
                    # flame_to_blender_scale parameter (i31 plumbing
                    # preserved). _make_export_callback + _LADDER_MENU_STOPS
                    # remain at module scope (defended by tests A/B/C/K).
                    "name": "Export Camera to Blender",
                    "isVisible": _scope_batch_action,
                    "execute": _export_camera_to_blender_with_picker,
                },
            ],
        },
    ]


# RESEARCH §Pitfall 1: _scope_action_camera uses item.type == "Camera"
# (PLAIN STR, not PyAttribute) — see _scope_action_camera definition above.
# Do NOT switch to .get_value() here; the Wave 0 test
# test_scope_action_camera_does_not_call_get_value_on_type guards it.
# RESEARCH §Pitfall 3: this is a NEW Flame hook function that must
# coexist with get_batch_custom_ui_actions. Both fire on different
# selection surfaces. Do NOT consolidate them.
# RESEARCH §Pitfall 4: requires a full Flame restart after `bash
# install.sh` for Flame's menu dispatch table to pick up the new
# function. Live-reload (gc/exec) does NOT refresh the dispatch table.
# RESEARCH §P-02 OQ-2: cam.parent returning the containing PyActionNode
# is verified via bridge but not yet in hook callback context. If UAT
# shows the parent path failing, fallback to scanning flame.batch.nodes
# for the Action containing the right-clicked camera.
def get_action_custom_ui_actions():
    """Right-click menu on camera nodes inside an Action's schematic.

    Distinct from get_batch_custom_ui_actions — fires when the user
    right-clicks a PyCoNode inside an Action's node graph, not when
    they right-click the Action node itself in the Batch schematic
    (RESEARCH §P-02 — verified live 2026-04-25 via forge-bridge).

    Uses hierarchy: [] (root level) because two-level nesting in
    action context is unverified on Flame 2026.2.1 (RESEARCH §P-01).
    The leaf appears as a top-level item in the right-click menu.
    """
    return [
        {
            "hierarchy": [],
            "actions": [
                {
                    # Quick 260501-knl: reverted from i31's 6-sibling ladder
                    # to a single entry that opens the forge-themed scale
                    # picker dialog. The wrapper forwards the chosen scale
                    # to _export_camera_from_action_selection via the
                    # kw-only flame_to_blender_scale parameter.
                    "name": "Export Camera to Blender",
                    "isVisible": _scope_action_camera,
                    "execute": _export_camera_from_action_selection_with_picker,
                },
            ],
        }
    ]
