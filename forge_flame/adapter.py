"""
Flame adapter — turns forge_core.solver.solve_2vp() output into the dict
shape Flame's Action camera expects.

Bridges two conventions:

  forge_core.solver.solve_2vp
      Pure geometry. Returns focal length (relative units), VPs in image-
      plane coords, principal point, and view/camera transforms (world↔cam
      rotation matrices). No Euler decomposition, no scale assumptions.

  Flame Action camera
      Takes Euler angles in a very specific order — R = Rz(rz) · Ry(-ry) ·
      Rx(-rx), i.e. ZYX composition with X and Y signs negated. Verified
      empirically via FBX export (see memory/flame_rotation_convention.md).
      Takes world position in pixel-native units: 1 world unit ≈ 1 image
      pixel, with camera distance to origin defaulting to h/(2·tan(vfov/2))
      so a default-sized geometry renders at expected scale.

This module also:
  - Accepts N≥2 lines per VP. When N>2 it fits the VP via least squares
    (forge_core.solver.fitting.fit_vp_from_lines) then hands solve_2vp()
    a 2-line pair that intersects exactly at the fitted VP. solve_2vp()'s
    internal 2-line intersection then agrees with the LSQ fit.
  - Supports quad mode (fSpy's quadModeEnabled): given 4 points on VP1
    treat them as a planar quad and synthesize VP2 from perpendicular
    edges.
  - Writes a full math trace to /tmp/forge_camera_match_trace.json on every
    solve — used by the parity test and by post-mortem debugging.

Public surface:
    solve_for_flame(vp1_lines, vp2_lines, w, h, ax1, ax2, origin_px=None,
                    cam_back=None, vp3_lines=None, quad_mode=False) -> dict | None

    compute_flame_euler_zyx(cam_rot) -> (rx_deg, ry_deg, rz_deg)
    default_cam_back(height, vfov) -> float
    write_trace(trace: dict, path: str = TRACE_PATH) -> None
"""

from __future__ import annotations

import json
import os
import time
from typing import List, Optional, Sequence, Tuple

import numpy as np

from forge_core.solver.fitting import fit_vp_from_lines
from forge_core.solver.solver import solve_2vp

# Axis int → string mapping. Hook stores axes as 0..5 integers; solve_2vp
# takes "+X"/"-X"/etc strings. Same order as the hook's _AX_LABELS.
AX_INT_TO_STR = ["+X", "-X", "+Y", "-Y", "+Z", "-Z"]
_AX_VEC = {
    0: np.array([1.0,  0.0,  0.0]),
    1: np.array([-1.0, 0.0,  0.0]),
    2: np.array([0.0,  1.0,  0.0]),
    3: np.array([0.0, -1.0,  0.0]),
    4: np.array([0.0,  0.0,  1.0]),
    5: np.array([0.0,  0.0, -1.0]),
}

SENSOR_MM = 36.0  # Flame's implicit 35mm film back
TRACE_PATH = "/tmp/forge_camera_match_trace.json"


# =============================================================================
# Flame rotation convention: R = Rz(rz) · Ry(-ry) · Rx(-rx)
#
# Implementations moved to forge_core.math.rotations so non-Flame consumers
# (e.g. the Blender bake script) can use them without pulling in the full
# adapter module. Re-exported here so existing imports keep working.
# =============================================================================

from forge_core.math.rotations import (  # noqa: E402, F401
    compute_flame_euler_zyx,
    flame_euler_to_cam_rot,
)


def default_cam_back(height: int, vfov_rad: float) -> float:
    """Flame's native pixel-unit camera distance.

    A fresh Flame Action camera sits at distance ``h / (2 · tan(vfov/2))``
    where h is the image height. At that distance, default-sized geometry
    renders at the expected scale. Use this when the user hasn't supplied
    an explicit camera-to-origin distance."""
    return float(height / (2.0 * np.tan(vfov_rad / 2.0)))


# =============================================================================
# Trace dump
# =============================================================================


def _coerce(obj):
    """JSON-friendly coercion: numpy arrays → lists, scalars → python floats."""
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.floating, np.integer)):
        return float(obj)
    if isinstance(obj, (tuple, list)):
        return [_coerce(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _coerce(v) for k, v in obj.items()}
    return obj


def write_trace(trace: dict, path: str = TRACE_PATH) -> None:
    """Write a solver trace dict as indented JSON. Silent on write errors —
    the trace is debug-only, a stale dump is better than crashing the UI."""
    try:
        with open(path, "w") as fp:
            json.dump(_coerce(trace), fp, indent=2)
    except Exception:
        pass


# =============================================================================
# Pixel ↔ image-plane conversion (matches solve_2vp's ImagePlane convention)
# =============================================================================


def _px_to_ip(px: float, py: float, w: int, h: int) -> np.ndarray:
    """Pixel coords → solve_2vp's image-plane coords. Top-left origin in,
    centered ±1 out (x-major for landscape, y-major for portrait)."""
    rx, ry = px / w, py / h
    a = w / h
    if a >= 1.0:
        return np.array([-1.0 + 2.0 * rx, (1.0 - 2.0 * ry) / a])
    else:
        return np.array([(-1.0 + 2.0 * rx) * a, 1.0 - 2.0 * ry])


def _ip_to_px(ip: np.ndarray, w: int, h: int) -> List[float]:
    """Inverse of _px_to_ip. Needed only for the principal-point readout
    when FromThirdVanishingPoint mode gives a non-centre PP."""
    a = w / h
    if a >= 1.0:
        rx = (float(ip[0]) + 1.0) / 2.0
        ry = (1.0 - float(ip[1]) * a) / 2.0
    else:
        rx = (float(ip[0]) / a + 1.0) / 2.0
        ry = (1.0 - float(ip[1])) / 2.0
    return [rx * w, ry * h]


# =============================================================================
# N-line → 2-line packing (feed LSQ-fitted VP through solve_2vp)
# =============================================================================


def _pack_lines_for_solve_2vp(
    lines_px: Sequence[Tuple[Tuple[float, float], Tuple[float, float]]]
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Turn N≥2 user lines into a 4-point tuple whose 2-line intersection
    equals the LSQ-fitted VP.

    Why: solve_2vp recomputes each VP from ``line_intersection(L0, L1)``
    internally. With N=2 that's correct. With N≥3 the LSQ VP is generally
    not on L0, so we can't just pass ``(L0, L1)`` — the solver would use
    a VP biased toward L0 instead of the fit. Trick: build two synthetic
    "lines" that both terminate at the fitted VP. Their intersection is
    the VP by construction, so the solver sees exactly the LSQ fit.

    For N=2 the fitted VP sits on both lines, so this collapses to the
    exact 2-line intersection — no accuracy loss vs. passing the raw
    endpoints.
    """
    if len(lines_px) < 2:
        raise ValueError("need at least 2 lines per VP")
    vp = fit_vp_from_lines(lines_px)
    if vp is None:
        # Lines truly parallel — let the solver handle failure path.
        # Pass endpoints through anyway; solve_2vp returns None.
        p1, p2 = lines_px[0]
        p3, p4 = lines_px[1]
        return (np.array(p1), np.array(p2), np.array(p3), np.array(p4))

    # Anchor points: use distinct endpoints from user lines for stability.
    anchor1 = lines_px[0][0]
    anchor2 = lines_px[1][0] if len(lines_px) > 1 else lines_px[0][1]
    vp_pt = np.array([vp[0], vp[1]])
    return (
        np.array(anchor1, dtype=float), vp_pt,
        np.array(anchor2, dtype=float), vp_pt,
    )


# =============================================================================
# Main entry point
# =============================================================================


def solve_for_flame(
    vp1_lines: Sequence[Tuple[Tuple[float, float], Tuple[float, float]]],
    vp2_lines: Sequence[Tuple[Tuple[float, float], Tuple[float, float]]],
    w: int,
    h: int,
    ax1: int = 1,
    ax2: int = 5,
    origin_px: Optional[Sequence[float]] = None,
    cam_back: Optional[float] = None,
    vp3_lines: Optional[Sequence[Tuple[Tuple[float, float], Tuple[float, float]]]] = None,
    quad_mode: bool = False,
) -> Optional[dict]:
    """Full solve → Flame-shaped dict, with trace.

    Accepts the hook's existing call shape: integer axis codes, N≥2 lines
    per VP, optional origin pixel, optional explicit cam_back distance,
    optional 3rd VP (FromThirdVanishingPoint), optional quad mode.

    Returns ``None`` when the solver can't converge (parallel lines,
    degenerate VPs, focal² ≤ 0). Otherwise returns a dict with every key
    the UI consumes:

        position            (x, y, z)  — world coords in Flame pixel-units
        rotation            (rx, ry, rz)  — degrees, Flame Euler convention
        focal_mm            float
        film_back_mm        float (= SENSOR_MM)
        hfov_deg, vfov_deg  floats
        cam_rot             3x3 list (cam-to-world rotation)
        f_relative          float (solve_2vp's focal in image-plane units)
        ax1, ax2            ints (the inputs, echoed for UI convenience)
        origin_px           [x, y] pixel coords (resolved default or input)
        cam_back_dist       float (resolved default or input)
        principal_point_px  [x, y] | None (only populated when vp3 was used)
    """
    trace = {
        "timestamp": time.time(),
        "inputs": {
            "image_size": [w, h],
            "aspect": w / h,
            "ax1": ax1, "ax1_name": AX_INT_TO_STR[ax1],
            "ax2": ax2, "ax2_name": AX_INT_TO_STR[ax2],
            "sensor_mm": SENSOR_MM,
            "origin_px": None if origin_px is None else [float(origin_px[0]), float(origin_px[1])],
            "cam_back_requested": None if cam_back is None else float(cam_back),
            "n_vp1_lines": len(vp1_lines),
            "n_vp2_lines": len(vp2_lines),
            "n_vp3_lines": len(vp3_lines) if vp3_lines else 0,
            "quad_mode": bool(quad_mode),
        },
        "stages": {},
        "result": None,
        "error": None,
    }

    # LSQ-fit and pack 2-line tuples for solve_2vp. quad_mode is handled by
    # solve_2vp directly so we don't synthesize VP2 here; just pass VP1's
    # lines through (solve_2vp uses the first 4 points as the quad corners).
    try:
        vp1_tuple = _pack_lines_for_solve_2vp(vp1_lines)
    except ValueError as e:
        trace["error"] = f"VP1 pack failed: {e}"
        write_trace(trace)
        return None

    if quad_mode:
        # In quad_mode, solve_2vp expects vp1_lines as 4 points treated as a
        # quad. If the user drew ≥2 lines, take their first two lines' endpoints
        # as the 4 quad corners. solve_2vp internally overrides vp2_lines.
        if len(vp1_lines) < 2:
            trace["error"] = "quad_mode requires ≥ 2 VP1 lines"
            write_trace(trace)
            return None
        a, b = vp1_lines[0]
        c, d = vp1_lines[1]
        vp1_tuple = (np.array(a, dtype=float), np.array(b, dtype=float),
                     np.array(c, dtype=float), np.array(d, dtype=float))
        vp2_tuple = vp1_tuple  # solve_2vp ignores this when quad_mode=True
    else:
        try:
            vp2_tuple = _pack_lines_for_solve_2vp(vp2_lines)
        except ValueError as e:
            trace["error"] = f"VP2 pack failed: {e}"
            write_trace(trace)
            return None

    vp3_tuple = None
    if vp3_lines and len(vp3_lines) >= 2:
        # Only forward a third VP if the LSQ fit actually converges — when
        # the two/three user lines are parallel (VP at infinity) the fit
        # returns None, and we fall back to "no vp3, principal point at
        # image centre" just like the old hook did.
        vp3_fit = fit_vp_from_lines(vp3_lines)
        if vp3_fit is not None:
            vp3_tuple = _pack_lines_for_solve_2vp(vp3_lines)

    origin_px_arr = None if origin_px is None else np.array(
        [float(origin_px[0]), float(origin_px[1])], dtype=float)

    raw = solve_2vp(
        vp1_tuple, vp2_tuple, w, h,
        axis1=AX_INT_TO_STR[ax1], axis2=AX_INT_TO_STR[ax2],
        origin_px=origin_px_arr,
        vp3_lines=vp3_tuple,
        quad_mode=quad_mode,
    )
    if raw is None:
        trace["error"] = "solve_2vp returned None (geometry degenerate)"
        write_trace(trace)
        return None

    f = float(raw["focal_length"])
    hfov = float(raw["horizontal_fov"])
    vfov = float(raw["vertical_fov"])
    pp = np.asarray(raw["principal_point"], dtype=float)
    vp1_ip = np.asarray(raw["vp1"], dtype=float)
    vp2_ip = np.asarray(raw["vp2"], dtype=float)
    cam_transform = np.asarray(raw["camera_transform"], dtype=float)
    view_transform = np.asarray(raw["view_transform"], dtype=float)

    # Rotation blocks. solve_2vp returns 4x4 camera_transform when origin_px
    # was supplied (it calls compute_translation), else the 3x3 inverse of
    # view. The top-left 3x3 is the cam-to-world rotation either way.
    cam_rot = cam_transform[:3, :3] if cam_transform.shape[0] == 4 else cam_transform
    view_rot = view_transform[:3, :3] if view_transform.shape[0] == 4 else view_transform

    trace["stages"]["vp1_imageplane"] = vp1_ip.tolist()
    trace["stages"]["vp2_imageplane"] = vp2_ip.tolist()
    trace["stages"]["principal_point_imageplane"] = pp.tolist()
    trace["stages"]["f_relative"] = f
    trace["stages"]["hfov_rad"] = hfov
    trace["stages"]["vfov_rad"] = vfov
    trace["stages"]["view_rot_world_to_cam"] = view_rot.tolist()
    trace["stages"]["cam_rot_cam_to_world"] = cam_rot.tolist()

    # Flame Euler.
    flame_euler = compute_flame_euler_zyx(cam_rot)
    trace["stages"]["flame_euler_deg"] = list(flame_euler)

    # cam_back default (Flame's 1unit=1px scale).
    if cam_back is None:
        cam_back = default_cam_back(h, vfov)
    trace["inputs"]["cam_back_resolved"] = float(cam_back)

    # Origin → world position. solve_2vp already computed this via
    # compute_translation when origin_px was passed; it lives in the last
    # column of camera_transform. Recompute here explicitly because the
    # hook's UI wants a separate "pixel world-origin" intermediary, and
    # because solve_2vp's origin handling uses reference_distance semantics
    # that don't match Flame's cam_back scale.
    if origin_px is None:
        # Default matches the hook's old behaviour: intersection of VP1 line 0
        # and VP2 line 0 in image-plane coords, converted back to pixels.
        # Falls back to image centre if the two lines are parallel.
        from forge_core.solver.math_util import line_intersection
        l1 = vp1_lines[0] if not quad_mode else (vp1_lines[0][0], vp1_lines[0][1])
        l2 = vp2_lines[0] if not quad_mode else (vp1_lines[1][0], vp1_lines[1][1])
        a_ip = _px_to_ip(l1[0][0], l1[0][1], w, h)
        b_ip = _px_to_ip(l1[1][0], l1[1][1], w, h)
        c_ip = _px_to_ip(l2[0][0], l2[0][1], w, h)
        d_ip = _px_to_ip(l2[1][0], l2[1][1], w, h)
        isect_ip = line_intersection(a_ip, b_ip, c_ip, d_ip)
        origin_ip = isect_ip if isect_ip is not None else np.array([0.0, 0.0])
        origin_px_resolved = _ip_to_px(origin_ip, w, h)
    else:
        origin_px_resolved = [float(origin_px[0]), float(origin_px[1])]
        origin_ip = _px_to_ip(origin_px_resolved[0], origin_px_resolved[1], w, h)
    # Origin in camera space: fSpy-style back-projection at perpendicular
    # depth cam_back (z_cam = -cam_back). Matches the old hook exactly.
    ray_cam = np.array([origin_ip[0] - pp[0], origin_ip[1] - pp[1], -f], dtype=float)
    origin_in_cam = (cam_back / f) * ray_cam
    cam_pos = -cam_rot @ origin_in_cam

    trace["stages"]["origin_px_resolved"] = list(origin_px_resolved)
    trace["stages"]["origin_imageplane"] = origin_ip.tolist()
    trace["stages"]["origin_in_cam"] = origin_in_cam.tolist()
    trace["stages"]["cam_position_world"] = cam_pos.tolist()

    # Project world axes through the solved camera — acid-test diagnostic
    # for the trace (not used by the UI).
    proj = {}
    for name, vec in [("+X", _AX_VEC[0]), ("-X", _AX_VEC[1]), ("+Y", _AX_VEC[2]),
                      ("-Y", _AX_VEC[3]), ("+Z", _AX_VEC[4]), ("-Z", _AX_VEC[5])]:
        v_cam = cam_rot.T @ vec
        if v_cam[2] >= 0:
            proj[name] = {"cam_dir": v_cam.tolist(), "projects": "BEHIND camera"}
        else:
            ipx = pp[0] + v_cam[0] / -v_cam[2] * f
            ipy = pp[1] + v_cam[1] / -v_cam[2] * f
            px_pos = _ip_to_px(np.array([ipx, ipy]), w, h)
            proj[name] = {"cam_dir": v_cam.tolist(),
                          "image_plane": [ipx, ipy], "pixel": px_pos}
    trace["stages"]["world_axis_projections"] = proj

    focal_mm = f * SENSOR_MM / 2.0

    result = {
        "position": (float(cam_pos[0]), float(cam_pos[1]), float(cam_pos[2])),
        "rotation": flame_euler,
        "focal_mm": float(focal_mm),
        "film_back_mm": float(SENSOR_MM),
        "hfov_deg": float(np.degrees(hfov)),
        "vfov_deg": float(np.degrees(vfov)),
        "cam_rot": cam_rot.tolist(),
        "f_relative": f,
        "ax1": ax1, "ax2": ax2,
        "origin_px": list(origin_px_resolved),
        "cam_back_dist": float(cam_back),
        # Only populated in FromThirdVanishingPoint mode (pp not at centre).
        "principal_point_px":
            _ip_to_px(pp, w, h) if vp3_tuple is not None else None,
    }
    trace["result"] = result
    write_trace(trace)
    return result
