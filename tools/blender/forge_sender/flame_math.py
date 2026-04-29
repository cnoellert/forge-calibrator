"""
forge_sender/flame_math.py — shared Blender-side Flame camera math.

Why this module exists: the "Send to Flame" addon and the legacy
extract_camera.py CLI script both need the same Euler decomposition,
axis-swap matrix, keyframe walker, and v5-JSON payload builder.
Putting them here gives us one copy to touch when the math needs a
fix (memory/flame_rotation_convention.md is the spec).

Scope boundaries:
  - Math only. No bpy Panel / Operator / UI surface.
  - No HTTP / JSON I/O. Callers serialize via json.dumps / json.dump.
  - Pure bpy + mathutils imports; safe to import from either the
    addon or from a Blender subprocess driving extract_camera.py.

Round-trip parity: the Euler decomposition here MUST stay
numerically identical to
forge_core.math.rotations.compute_flame_euler_xyz. If you change one,
change both and run tests/test_blender_roundtrip.py plus
tests/test_forge_sender_flame_math.py. Phase 04.3 swapped this
module from the older Z·Y·X convention with only rx/ry negated
(the Free-rig _zyx pair) to R = Rz(-rz)·Ry(-ry)·Rx(-rx) — same
Z·Y·X product, but with rz also sign-negated — to match Flame's
actual aim-rig rendering, verified 2026-04-25 via forge-bridge
probe of Camera1. Coupled with the L167 sign flip in
forge_core.math.rotations.rotation_matrix_from_look_at; the two
changes must always land together.

Scale handling:

  bake_camera.py stamps ``forge_bake_scale`` as a custom property on
  the camera's data-block. ``_resolve_scale`` reads that value and
  ``build_v5_payload`` multiplies POSITION back up by it, undoing the
  bake-time division. Lens and sensor_height are not scaled — bake
  left them in their native mm for the reasons documented there.
"""
from __future__ import annotations

import math
import sys
from typing import Optional

import bpy
from mathutils import Matrix


# =============================================================================
# Math — parallel implementation of
# forge_core.math.rotations.compute_flame_euler_xyz
# =============================================================================


def _rot3_to_flame_euler_deg(R) -> tuple:
    """Decompose a 3x3 cam-to-world rotation into Flame's XYZ-signflip Euler.

    Flame's aim-rig camera composes rotations as
    R = Rz(-rz) · Ry(-ry) · Rx(-rx). This is the matching inverse
    decomposition. Must stay numerically identical to
    forge_core.math.rotations.compute_flame_euler_xyz — if you
    change one, change both and run tests/test_blender_roundtrip.py
    plus tests/test_forge_sender_flame_math.py.

    Phase 04.3: convention swapped from Rz(rz)·Ry(-ry)·Rx(-rx) (the
    Z·Y·X with only rx/ry negated form used by the Free-rig _zyx
    pair) to Rz(-rz)·Ry(-ry)·Rx(-rx) — same Z·Y·X product, with rz
    now ALSO sign-negated. Coupled with the L167 sign flip in
    forge_core.math.rotations.rotation_matrix_from_look_at; the two
    changes always land together. Verified 2026-04-25 against
    Camera1 viewport ground truth (1.8193°, 1.0639°, 1.2529°) within
    0.01° per axis.

    Handles gimbal lock (ry ≈ ±90°) by pinning rx=0 and recovering
    rz from the remaining 2x2 block."""
    # mathutils 3x3 Matrix indexes as [row][col]. Keep aligned with numpy.
    cb = math.sqrt(R[0][0] ** 2 + R[1][0] ** 2)
    gimbal = cb <= 1e-6
    if not gimbal:
        rx = -math.atan2(R[2][1], R[2][2])
        ry = -math.asin(-R[2][0])
        rz = -math.atan2(R[1][0], R[0][0])             # Phase 04.3: sign flipped
    else:
        rx = 0.0
        ry = -math.asin(-R[2][0])
        rz =  math.atan2(R[0][1], R[1][1])             # Phase 04.3: first arg sign flipped
    return (math.degrees(rx), math.degrees(ry), math.degrees(rz))


# Blender world (Z-up) -> Flame world (Y-up). Inverse of the bake step.
# Transpose of Rx(+90°) is Rx(-90°).
_R_Z2Y = Matrix.Rotation(math.radians(90), 4, 'X').transposed()


# =============================================================================
# Keyframe discovery
# =============================================================================


def _iter_action_fcurves(action, anim_data=None):
    """Version-tolerant fcurves walk for Blender 4.5..5.x slotted Actions.

    WHY this exists: Blender 4.4 (Mar 2025) introduced Slotted Actions —
    an Action is no longer a flat collection of fcurves but a layered
    tree of Action -> ActionLayer -> ActionStrip -> ActionChannelbag ->
    FCurve, and one Action can drive multiple data-blocks via slots.
    Blender 4.4 retained `action.fcurves` as a back-compat proxy, but
    Blender 5.0 (Oct 2025) REMOVED it entirely. flame-01 (Blender 5.1)
    crashes the addon's "Send to Flame" operator with
    ``AttributeError: 'Action' object has no attribute 'fcurves'``;
    this helper is the fix.

    Three-tier strategy:

      * Tier 1 — official helper: when ``anim_data.action_slot`` is
        bound, use ``bpy_extras.anim_utils.action_get_channelbag_for_slot``
        to find the right channelbag and yield its fcurves. This is the
        common case for forge-produced .blends (bake_camera.py creates
        single-slot Actions via keyframe_insert).

      * Tier 2 — manual slotted walk: when no slot is bound (rare —
        non-forge-produced .blend, or auto-assignment couldn't pick a
        unique slot), iterate every channelbag of every strip of every
        layer and emit all fcurves. May include cross-slot fcurves on a
        multi-slot Action; Tier 1 above is the always-fires path that
        prevents that for forge's own writes.

      * Tier 3 — legacy proxy: ``action.fcurves`` direct access. Covers
        Blender 4.5 actions still in legacy-proxy mode (created in 4.3
        and loaded into 4.4/4.5). Harmless dead code on Blender 5.0+
        because the attr no longer exists; intentional — removing it
        would break 4.5 legacy-mode actions.

    Args:
        action: the bpy.types.Action data-block, or None.
        anim_data: the bpy.types.AnimData hosting the action binding
            (cam.animation_data or cam.data.animation_data). The helper
            reads ``anim_data.action_slot`` to drive Tier 1; pass None
            to skip Tier 1 outright.

    Yields:
        bpy.types.FCurve instances. Empty iterator on a None action,
        an empty slotted action, or an action whose layers/fcurves are
        all empty.

    See memory/blender_slotted_actions_fcurves_api.md for the full
    migration spec, version cutoffs, and writer-side rationale (the
    bake_camera.py keyframe_insert path needs no change because Blender
    auto-creates slot/layer/strip/channelbag plumbing on first insert).

    Sources:
        developer.blender.org/docs/release_notes/4.4/upgrading/slotted_actions/
        developer.blender.org/docs/release_notes/5.0/python_api/
    """
    if action is None:
        return

    # Tier 1: official helper, when a slot is bound.
    slot = getattr(anim_data, "action_slot", None) if anim_data else None
    if slot is not None:
        try:
            from bpy_extras import anim_utils
            cbag = anim_utils.action_get_channelbag_for_slot(action, slot)
        except (ImportError, AttributeError):
            cbag = None
        if cbag is not None:
            for fc in cbag.fcurves:
                yield fc
            return

    # Tier 2: manual slotted walk (no slot bound, or helper missing).
    layers = getattr(action, "layers", None)
    if layers:
        emitted = False
        for layer in layers:
            for strip in getattr(layer, "strips", ()):
                for cbag in getattr(strip, "channelbags", ()):
                    for fc in cbag.fcurves:
                        emitted = True
                        yield fc
        if emitted:
            return

    # Tier 3: legacy-mode action.fcurves (4.4/4.5 back-compat proxy).
    # Harmless dead code on Blender 5.0+ where the attr was removed.
    legacy = getattr(action, "fcurves", None)
    if legacy:
        for fc in legacy:
            yield fc


def _camera_keyframe_set(cam: bpy.types.Object) -> list:
    """Return a sorted list of unique integer frame numbers on which the
    camera (object or its data) has any keyframe.

    Walks both the object-level action (location/rotation/scale) and the
    camera-data-level action (lens, sensor, etc.) because we keyframe
    both in bake_camera.py. Falls back to the scene's current frame if
    no animation data is present (single static bake).

    Uses ``_iter_action_fcurves`` to stay version-tolerant across the
    Blender 4.4 slotted-actions migration; see that helper's docstring
    and memory/blender_slotted_actions_fcurves_api.md for context."""
    frames = set()

    def _drain(anim):
        if anim is None or anim.action is None:
            return
        for fc in _iter_action_fcurves(anim.action, anim_data=anim):
            for kp in fc.keyframe_points:
                frames.add(int(round(kp.co[0])))

    _drain(cam.animation_data)
    _drain(cam.data.animation_data)

    if not frames:
        frames.add(int(bpy.context.scene.frame_current))
    return sorted(frames)


# =============================================================================
# Scale resolution
# =============================================================================


def _resolve_scale(cam: bpy.types.Object, cli_override) -> float:
    """CLI override wins; otherwise read the stamped metadata; otherwise 1.0.

    extract_camera.py's ``--scale`` flag passes ``args.scale`` as the
    override. The addon operator passes ``None`` — it trusts the
    ``forge_bake_scale`` stamped by bake_camera.py. If the .blend has
    no stamped scale (e.g. it wasn't produced by our bake), this
    prints a stderr warning and defaults to 1.0; callers who care
    should surface a popup before reaching here (addon preflight)."""
    if cli_override is not None:
        return float(cli_override)
    stamped = cam.data.get("forge_bake_scale")
    if stamped is None:
        print("forge_sender/flame_math: warning — no forge_bake_scale "
              f"metadata on {cam.name!r}, defaulting to 1.0. Pass "
              "scale_override if this .blend came from a non-default bake.",
              file=sys.stderr)
        return 1.0
    return float(stamped)


# =============================================================================
# Public: build the v5 JSON dict for a camera
# =============================================================================


def build_v5_payload(cam, scale_override: Optional[float] = None) -> dict:
    """Return the v5 JSON dict for ``cam`` (a bpy camera Object).

    No JSON I/O — callers serialize with json.dumps / json.dump. Both
    the "Send to Flame" addon and ``extract_camera.py`` call this;
    the addon POSTs json.dumps(result) to forge-bridge, the CLI writes
    json.dump(result, file).

    Args:
        cam: bpy.types.Object (camera). Must have .animation_data,
            .data, and .matrix_world attributes. .data is a
            bpy.types.Camera with .lens, .sensor_height, and dict-like
            custom-property access.
        scale_override: if not None, bypasses the stamped
            forge_bake_scale lookup. extract_camera.py passes
            ``args.scale`` here (CLI --scale flag); the addon passes
            ``None`` (reads stamped metadata via _resolve_scale).

    Returns a dict with keys: ``width``, ``height``, ``film_back_mm``,
    ``frames``. Each frame in ``frames`` is a dict with
    ``frame``, ``position``, ``rotation_flame_euler``, ``focal_mm``.
    """
    scene = bpy.context.scene
    scale = _resolve_scale(cam, scale_override)
    frames_to_read = _camera_keyframe_set(cam)

    frames_out = []
    for frame in frames_to_read:
        scene.frame_set(frame)

        # cam.matrix_world is the Blender-frame world matrix for this frame.
        # Apply the inverse axis swap to get back to Flame's Y-up frame.
        m_flame = _R_Z2Y @ cam.matrix_world

        # Position: translation column, scaled back up.
        tx, ty, tz = m_flame.translation
        position = [tx * scale, ty * scale, tz * scale]

        # Rotation: upper-left 3x3, decomposed via Flame convention.
        R = m_flame.to_3x3()
        rx_deg, ry_deg, rz_deg = _rot3_to_flame_euler_deg(R)

        # Lens is stored in mm verbatim by bake — no scale inversion needed.
        focal_mm = float(cam.data.lens)

        frames_out.append({
            "frame": frame,
            "position": position,
            "rotation_flame_euler": [rx_deg, ry_deg, rz_deg],
            "focal_mm": focal_mm,
        })

    return {
        "width":        int(scene.render.resolution_x),
        "height":       int(scene.render.resolution_y),
        # film_back_mm is the VERTICAL sensor dimension in our contract;
        # bake writes it to sensor_height with sensor_fit='VERTICAL'. Read
        # sensor_height here to stay consistent (sensor_width would be
        # Blender's auto-derived horizontal value, a different number).
        "film_back_mm": float(cam.data.sensor_height),
        "frames":       frames_out,
    }
