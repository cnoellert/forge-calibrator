"""
forge_sender/__init__.py — "Send to Flame" Blender addon entry.

Why this addon exists: completes the Flame ↔ Blender round-trip
without requiring the artist to visit Flame's batch menu. Phase 1
stamps ``forge_bake_action_name`` / ``forge_bake_camera_name`` /
``forge_bake_source`` on the baked camera; this addon reads those
back, extracts the current per-frame T/R/focal via
``forge_sender.flame_math.build_v5_payload``, and POSTs to forge-bridge
at http://127.0.0.1:9999/exec with a payload that runs
``v5_json_str_to_fbx`` + target-Action resolution +
``import_fbx_to_action`` inside Flame. Success / failure surfaces
in a Blender popup.

Scope boundaries:
  - Single Panel in the 3D viewport N-panel 'Forge' tab.
  - Single Operator: FORGE_OT_send_to_flame (bl_idname forge.send_to_flame).
  - Synchronous POST with a 5 s timeout (D-16) — no threading.
  - No config UI, no override inputs (D-14/D-15 minimal panel).

UI contract: see .planning/phases/02-blender-addon/02-UI-SPEC.md
for exact layout calls, icon names, and copy strings.
Bridge contract: see memory/flame_bridge.md and
memory/flame_bridge_probing.md.

D-19 frame-rate ladder (Plan 02-01 recovery):
  ``flame.batch.frame_rate`` is a NoneType slot on Flame 2026.2.1 —
  the D-17 assumption was disproved by the live probe. The addon
  therefore owns the frame-rate lookup via a 3-level ladder:

    1. ``cam.data["forge_bake_frame_rate"]`` — authoritative when
       stamped (optional Phase 1 supplement; not relied upon).
    2. ``bpy.context.scene.render.fps / fps_base`` — mapped to one
       of the keys in ``forge_flame.fbx_ascii._FPS_FROM_FRAME_RATE``.
    3. If neither resolves, surface an error popup with the scene
       fps and instructions (the "popup asking the user" step —
       rendered as a Tier-1-style error rather than a live prompt
       because a sync operator can't block for input without
       reinventing modal state).

  The resolved string is passed through ``transport.send(..., frame_rate=...)``
  which forwards it into the bridge payload. The Flame-side template
  receives the value from the payload, never by probing Flame.
  See ``memory/flame_batch_frame_rate.md``.
"""
from __future__ import annotations

import ast
import json
from typing import Optional

import bpy
import requests  # D-13: bundled with Blender 4.5's Python

# Relative imports from siblings. Blender addon loader exposes the
# package namespace correctly when the directory is installed via
# Preferences → Add-ons → Install from file.
from . import flame_math, preflight, transport


bl_info = {
    "name": "Forge: Send Camera to Flame",
    "author": "forge-calibrator",
    "version": (1, 3, 2),
    "blender": (4, 5, 0),
    "location": "View3D > Sidebar > Forge",
    "description": "Send the active Flame-baked camera back to its source Action in Flame.",
    "category": "Import-Export",
}
# v1.3.2 (2026-04-27): Phase 04.4 UAT fix #2 — empty dropdown again because
#                      _get_action_items rebuilt fresh tuples each call,
#                      letting Blender garbage-collect them. Cache the items
#                      tuple list itself at module scope (_choose_action_items)
#                      and return the same list object every callback call.
# v1.3.1 (2026-04-27): Phase 04.4 UAT fix #1 — Target Action dropdown was
#                      empty because invoke()'s self._cached_actions did not
#                      survive invoke_props_dialog instance churn. First
#                      attempt: moved cache to module level. Insufficient.
# v1.3.0 (2026-04-26): Phase 04.4 — added FORGE_OT_send_to_flame_choose_action
#                      operator for cameras without forge bake metadata
#                      (D-07/D-08/D-09). Panel shows a second button row in
#                      the no-metadata state. R-08 menu-path string updates
#                      land in preflight.py error copy.
# v1.2.0 (2026-04-25): aim-rig fix — adopt Phase 04.3 R = Rz(-rz)·Ry(-ry)·Rx(-rx)
#                      decomposer convention to match Flame-side bake's new
#                      composer. Resolves rz sign flip on aim-rig round-trip.
#                      flame_math.py was updated in source on 2026-04-25 but
#                      the redistributable zip was not rebuilt; users must
#                      reinstall this version. See .planning/debug/
#                      resolved/aim-rig-roundtrip-offset.md.
# v1.1.1 (2026-04-23): unit-scale fix.
# v1.1.0 (earlier):    debug build.
# v1.0.0 (initial):    first release.


# =============================================================================
# D-19 frame-rate ladder
# =============================================================================


# Map Blender's scene.render.fps / fps_base numeric ratio to the string
# keys accepted by ``forge_flame.fbx_ascii._FPS_FROM_FRAME_RATE``.
# Tolerance is 1e-3 so 23.976 ≈ 24000/1001 = 23.9760239… matches the
# "23.976 fps" key. Blender encodes 23.976 as fps=24, fps_base=1.001
# (ratio 23.976023…), 24 as fps=24, fps_base=1.0, etc.
_FLAME_FPS_LABELS = (
    ("23.976 fps", 24000.0 / 1001.0),
    ("24 fps", 24.0),
    ("25 fps", 25.0),
    ("29.97 fps", 30000.0 / 1001.0),
    ("30 fps", 30.0),
    ("48 fps", 48.0),
    ("50 fps", 50.0),
    ("59.94 fps", 60000.0 / 1001.0),
    ("60 fps", 60.0),
)


def _map_scene_fps_to_flame_label(fps: float,
                                  tolerance: float = 1e-3) -> Optional[str]:
    """Return the Flame frame-rate string for a Blender numeric fps,
    or None if no label matches within ``tolerance``."""
    for label, target in _FLAME_FPS_LABELS:
        if abs(fps - target) < tolerance:
            return label
    return None


def _resolve_frame_rate(cam, context) -> (Optional[str], Optional[str]):
    """D-19 ladder. Returns ``(label, None)`` on success or
    ``(None, error_message)`` if the ladder exhausts without
    resolving a supported Flame frame-rate label."""
    # Ladder step 1: stamped custom prop on camera data (authoritative).
    # WR-01 fix (02-REVIEW.md): when the stamp is present we FAIL LOUD on
    # any unsupported label rather than silently falling through to the
    # scene fps. The D-19 ladder documents step 1 as authoritative when
    # stamped; silently substituting a different frame rate violates the
    # Core Value of fidelity end-to-end (a stamp of "12 fps" or a stray
    # IDPropertyArray coerced to "[24]" must surface as an error, not a
    # quiet swap to whatever the scene happens to be set to).
    stamped = cam.data.get("forge_bake_frame_rate")
    if stamped:
        label = str(stamped)
        supported = {x[0] for x in _FLAME_FPS_LABELS}
        if label in supported:
            return (label, None)
        err = (f"Send to Flame: cam.data['forge_bake_frame_rate'] "
               f"= {label!r} is not a supported Flame label. "
               f"Expected one of: {', '.join(sorted(supported))}.")
        return (None, err)
    # Ladder step 2: Blender scene fps / fps_base.
    render = context.scene.render
    try:
        numeric_fps = float(render.fps) / float(render.fps_base)
    except (TypeError, ZeroDivisionError):
        numeric_fps = None
    if numeric_fps is not None:
        mapped = _map_scene_fps_to_flame_label(numeric_fps)
        if mapped is not None:
            return (mapped, None)
    # Ladder step 3: exhausted — surface a descriptive error.
    supported = ", ".join(x[0] for x in _FLAME_FPS_LABELS)
    err = (f"Send to Flame: cannot resolve Flame frame rate — "
           f"Blender scene fps={numeric_fps!r} is not one of the "
           f"supported Flame labels ({supported}). Either set the "
           f"scene frame rate to a supported value or stamp "
           f"cam.data['forge_bake_frame_rate'] with one of the "
           f"supported labels verbatim.")
    return (None, err)


# =============================================================================
# Popup helpers
# =============================================================================


def _popup(context, message: str, *, title: str = "Send to Flame",
           level: str = 'ERROR') -> None:
    """Single-line popup via ``wm.popup_menu``.

    Used for preflight Tier 1, transport Tier, and success (level='INFO').
    """
    def draw(self, _ctx):
        self.layout.label(text=message)
    icon = 'INFO' if level == 'INFO' else 'ERROR'
    context.window_manager.popup_menu(draw, title=title, icon=icon)


def _popup_multiline(context, message: str,
                     *, title: str = "Send to Flame") -> None:
    """Multi-line popup: one ``layout.label`` per line so pipeline-TDs
    can screenshot / copy the Flame-side traceback verbatim
    (UI-SPEC §Remote Tier "copy-paste-friendly"). Preserves
    whitespace; does NOT reflow."""
    lines = message.split("\n")

    def draw(self, _ctx):
        for line in lines:
            # Empty ``layout.label()`` renders a zero-height spacer;
            # preserve blank lines for the summary/traceback gap.
            self.layout.label(text=line if line else " ")
    context.window_manager.popup_menu(draw, title=title, icon='ERROR')


# =============================================================================
# Operator
# =============================================================================


class FORGE_OT_send_to_flame(bpy.types.Operator):
    """Send the active Flame-baked camera to its source Action in Flame."""
    bl_idname = "forge.send_to_flame"
    bl_label = "Send to Flame"
    bl_description = "Send the active Flame-baked camera to its source Action"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        # Permissive — poll() always accepts; execute() runs the full
        # preflight check and reports errors via popup. This lets F3 /
        # operator-search / direct bpy.ops call exercise the Tier 1
        # failure popups (see Plan 02-04 Task 3). The Panel draws its
        # enabled-state directly from preflight.check() and wraps the
        # button in an explicit `col.enabled = False` block when the
        # camera isn't Flame-baked — it does NOT rely on poll().
        return True

    def execute(self, context):
        # Belt-and-braces: re-check preflight inside execute() so
        # F3-search / keymap invocation can't bypass the panel gate.
        err = preflight.check(context)
        if err is not None:
            self.report({'ERROR'}, err)
            _popup(context, err)
            return {'CANCELLED'}

        cam = context.active_object

        # D-19 frame-rate ladder — resolve before building the payload
        # so an unsupported fps fails loud without ever touching the
        # bridge (Core Value: geometric fidelity over frictionless UX).
        frame_rate, fps_err = _resolve_frame_rate(cam, context)
        if fps_err is not None:
            self.report({'ERROR'}, fps_err)
            _popup(context, fps_err)
            return {'CANCELLED'}

        # Build the v5 payload from the current Blender scene state.
        # scale_override=None so _resolve_scale reads the stamped
        # forge_bake_scale off cam.data.
        payload_dict = flame_math.build_v5_payload(cam, scale_override=None)

        # Inject the stamped metadata the Flame side needs to resolve
        # the target Action (D-06/D-07). Phase 1 writes these keys on
        # bake; we echo them back inside custom_properties so the
        # bridge-side template can extract action_name without another
        # round-trip.
        payload_dict["custom_properties"] = {
            "forge_bake_action_name": cam.data["forge_bake_action_name"],
            "forge_bake_camera_name": cam.data["forge_bake_camera_name"],
        }

        v5_json_str = json.dumps(payload_dict)

        # POST to forge-bridge. Transport Tier covers ConnectionError
        # and Timeout; any other requests-layer error surfaces with
        # the same Transport Tier framing plus exception class.
        try:
            envelope = transport.send(v5_json_str, frame_rate=frame_rate)
        except (requests.exceptions.ConnectionError,
                requests.exceptions.Timeout):
            msg = (
                "Send to Flame: forge-bridge not reachable at http://127.0.0.1:9999"
                " — is Flame running with the Camera Calibrator hook loaded?"
            )
            self.report({'ERROR'}, msg)
            _popup(context, msg)
            return {'CANCELLED'}
        except requests.exceptions.RequestException as exc:
            # Any other requests-layer error: surface with Transport
            # Tier framing plus exception class so pipeline-TDs can
            # debug without having to curl the bridge themselves.
            msg = (f"Send to Flame: forge-bridge request failed — "
                   f"{type(exc).__name__}: {exc}")
            self.report({'ERROR'}, msg)
            _popup(context, msg)
            return {'CANCELLED'}

        # Parse the envelope. Remote Tier on error, success on result.
        err_msg, result = transport.parse_envelope(envelope)
        if err_msg is not None:
            self.report({'ERROR'}, err_msg)
            _popup_multiline(context, err_msg)
            return {'CANCELLED'}

        # Success — format the D-10 popup.
        action_name = (result or {}).get("action_name", "<unknown>")
        created = (result or {}).get("created") or []
        if len(created) == 1:
            msg = (f"Sent to Flame: camera '{created[0]}' "
                   f"in Action '{action_name}'")
        elif len(created) > 1:
            joined = ", ".join(f"'{n}'" for n in created)
            msg = f"Sent to Flame: cameras {joined} in Action '{action_name}'"
        else:
            # Edge case: bridge returned a result with no created list.
            msg = (f"Sent to Flame (no new camera reported) — "
                   f"Action '{action_name}'")

        self.report({'INFO'}, msg)
        _popup(context, msg, level='INFO')
        return {'FINISHED'}


# =============================================================================
# Phase 04.4 D-07: choose-Action operator (cameras without forge metadata)
# =============================================================================
#
# RESEARCH §Pitfall 2 (D-09 corrected): Flame raises RuntimeError on
# Action name collision — `name.set_value()` does NOT auto-suffix. The
# create-new path detects 'Could not set Batch node name' in the
# envelope error field and surfaces a clear collision message. DO NOT
# implement an auto-retry-with-suffix path; the user-correct flow is to
# choose a different name (or pick the existing Action from the dropdown).
# RESEARCH §Pattern 2: invoke() probes Flame for the Action list ONCE
# and caches the EnumProperty items tuples at MODULE level. Two
# Blender-specific reasons this MUST be module-level (not self.):
#
# 1. invoke_props_dialog uses fresh operator instances for draw
#    redraws, so attrs set on `self` in invoke() are gone before the
#    items callback runs (live UAT 2026-04-27 confirmed empty dropdown
#    when caching on self).
#
# 2. Blender's EnumProperty items callback contract requires Python to
#    hold strong references to the EXACT tuple objects returned —
#    rebuilding fresh tuple lists each call lets Blender garbage-
#    collect the strings, silently dropping all items including
#    "-- Create New --" (live UAT 2026-04-27 confirmed empty dropdown
#    even after fixing #1 above by caching just the action names).
#
# So: cache the items-tuple list itself, return the same list object
# every callback call. invoke() rebuilds the list once per dialog open.
_CREATE_NEW_ITEM = (
    "__create_new__",
    "-- Create New --",
    "Create a new Action in Flame",
)
_choose_action_items: list = [_CREATE_NEW_ITEM]
# UI-SPEC §B-1: both buttons remain visible simultaneously in the
# no-metadata state (disabled top button kept for muscle memory; new
# enabled bottom button is the active path). DO NOT hide either.
# Security T-04.4-04 / V5 ASVS L1: the user-typed `new_action_name`
# is embedded into the bridge code body via transport.make_create_code,
# which uses repr() (not f-string) — see transport.py docstring lines
# 23-29 and the security comment above make_create_code itself.


class FORGE_OT_send_to_flame_choose_action(bpy.types.Operator):
    """Send camera to Flame — pick or create the target Action.

    Phase 04.4 D-07/D-08/D-09. Use this when the active camera lacks
    forge bake metadata (e.g. it was created in Blender, not exported
    from Flame). The operator probes Flame for the live Action list,
    presents a dropdown with a '-- Create New --' option, and pushes
    the camera to the chosen / created Action.
    """
    bl_idname = "forge.send_to_flame_choose_action"
    bl_label = "Send to Flame (choose Action)"
    bl_description = (
        "Send the active camera to a chosen Flame Action — for cameras "
        "that were not exported from Flame (no forge bake metadata)"
    )
    bl_options = {'REGISTER'}

    target_action: bpy.props.EnumProperty(
        name="Target Action",
        description="Existing Flame Action or -- Create New --",
        items=lambda self, ctx: self._get_action_items(ctx),
    )
    new_action_name: bpy.props.StringProperty(
        name="New Action Name",
        description="Name for the new Action to create in Flame",
        default="",
    )

    @classmethod
    def poll(cls, context):
        # Active object must be a camera (any camera — no metadata gate).
        # Bridge reachability is checked in invoke() so F3-search can
        # exercise the failure popup.
        obj = context.active_object
        return obj is not None and getattr(obj, "type", None) == "CAMERA"

    def _get_action_items(self, ctx):
        """Return the EnumProperty items tuple list.

        Returns the SAME module-level list object on every call so
        Blender keeps a strong ref to the tuples (and their strings).
        Returning a freshly-built list each call lets Blender garbage-
        collect the strings, which silently empties the dropdown.
        """
        return _choose_action_items

    def invoke(self, context, event):
        # Probe Flame for live Actions before showing the dialog.
        global _choose_action_items
        try:
            action_names = transport.list_batch_actions()
        except (requests.exceptions.ConnectionError,
                requests.exceptions.Timeout):
            msg = (
                "forge-bridge not reachable at http://127.0.0.1:9999 — "
                "is Flame running with the Camera Calibrator hook loaded?"
            )
            self.report({'ERROR'}, msg)
            _popup(context, msg)
            return {'CANCELLED'}
        except requests.exceptions.RequestException as exc:
            msg = (f"forge-bridge request failed — "
                   f"{type(exc).__name__}: {exc}")
            self.report({'ERROR'}, msg)
            _popup(context, msg)
            return {'CANCELLED'}
        except RuntimeError as exc:
            msg = f"forge-bridge error: {exc}"
            self.report({'ERROR'}, msg)
            _popup(context, msg)
            return {'CANCELLED'}
        # Rebuild the module-level items list and KEEP IT — Blender's
        # EnumProperty items callback requires Python to hold strong refs
        # to the exact tuple objects that get returned.
        _choose_action_items = (
            [(n, n, "") for n in action_names] + [_CREATE_NEW_ITEM]
        )
        return context.window_manager.invoke_props_dialog(self, width=360)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "target_action")
        if self.target_action == "__create_new__":
            layout.prop(self, "new_action_name")

    def execute(self, context):
        cam = context.active_object

        # Resolve the target Action name — either pick existing or create new.
        if self.target_action == "__create_new__":
            new_name = self.new_action_name.strip()
            if not new_name:
                msg = (
                    "New Action name cannot be empty — enter a name and "
                    "try again"
                )
                self.report({'ERROR'}, msg)
                _popup(context, msg)
                return {'CANCELLED'}

            # POST the create-Action payload. Name is embedded via repr()
            # inside make_create_code (security T-04.4-04 / V5 ASVS L1).
            try:
                response = requests.post(
                    transport.BRIDGE_URL,
                    json={"code": transport.make_create_code(new_name)},
                    timeout=transport.DEFAULT_TIMEOUT_S,
                )
                response.raise_for_status()
                envelope = response.json()
            except (requests.exceptions.ConnectionError,
                    requests.exceptions.Timeout):
                msg = (
                    "forge-bridge not reachable at http://127.0.0.1:9999 — "
                    "is Flame running with the Camera Calibrator hook loaded?"
                )
                self.report({'ERROR'}, msg)
                _popup(context, msg)
                return {'CANCELLED'}
            except requests.exceptions.RequestException as exc:
                msg = (f"forge-bridge request failed — "
                       f"{type(exc).__name__}: {exc}")
                self.report({'ERROR'}, msg)
                _popup(context, msg)
                return {'CANCELLED'}

            err = envelope.get("error", "") or ""
            if "Could not set Batch node name" in err:
                # RESEARCH §P-03: Flame raises RuntimeError on Action name
                # collision — name.set_value() does NOT auto-suffix.
                msg = (
                    f"An Action named '{new_name}' already exists in this "
                    f"Batch — choose a different name and try again"
                )
                self.report({'ERROR'}, msg)
                _popup(context, msg)
                return {'CANCELLED'}
            if err:
                err_msg, _ = transport.parse_envelope(envelope)
                self.report({'ERROR'}, err_msg)
                _popup_multiline(context, err_msg)
                return {'CANCELLED'}

            # Bridge returned the created Action's name (repr of a str).
            try:
                target_name = ast.literal_eval(envelope["result"])
            except (ValueError, SyntaxError, KeyError):
                msg = (
                    f"forge-bridge returned malformed create-Action result: "
                    f"{envelope.get('result')!r}"
                )
                self.report({'ERROR'}, msg)
                _popup(context, msg)
                return {'CANCELLED'}
            created_new_action = True
        else:
            target_name = self.target_action
            created_new_action = False

        # D-19 frame-rate ladder — same as the stamped-camera path.
        frame_rate, fps_err = _resolve_frame_rate(cam, context)
        if fps_err is not None:
            self.report({'ERROR'}, fps_err)
            _popup(context, fps_err)
            return {'CANCELLED'}

        # Build the v5 payload. Inject custom_properties with the resolved
        # target Action name so the Flame-side template knows where to
        # land the camera. The Blender-camera name becomes the cam name
        # inside the target Action.
        payload_dict = flame_math.build_v5_payload(cam, scale_override=None)
        payload_dict["custom_properties"] = {
            "forge_bake_action_name": target_name,
            "forge_bake_camera_name": cam.name,
        }
        v5_json_str = json.dumps(payload_dict)

        try:
            envelope = transport.send(v5_json_str, frame_rate=frame_rate)
        except (requests.exceptions.ConnectionError,
                requests.exceptions.Timeout):
            msg = (
                "forge-bridge not reachable at http://127.0.0.1:9999 — "
                "is Flame running with the Camera Calibrator hook loaded?"
            )
            self.report({'ERROR'}, msg)
            _popup(context, msg)
            return {'CANCELLED'}
        except requests.exceptions.RequestException as exc:
            msg = (f"forge-bridge request failed — "
                   f"{type(exc).__name__}: {exc}")
            self.report({'ERROR'}, msg)
            _popup(context, msg)
            return {'CANCELLED'}

        err_msg, result = transport.parse_envelope(envelope)
        if err_msg is not None:
            self.report({'ERROR'}, err_msg)
            _popup_multiline(context, err_msg)
            return {'CANCELLED'}

        action_name = (result or {}).get("action_name", target_name)
        created = (result or {}).get("created") or []
        if len(created) == 1:
            cam_label = created[0]
        elif len(created) > 1:
            cam_label = ", ".join(f"'{n}'" for n in created)
        else:
            cam_label = "<unknown>"

        if created_new_action:
            msg = (f"Sent to Flame: camera '{cam_label}' "
                   f"in new Action '{action_name}'")
        else:
            msg = (f"Sent to Flame: camera '{cam_label}' "
                   f"in Action '{action_name}'")
        self.report({'INFO'}, msg)
        _popup(context, msg, level='INFO')
        return {'FINISHED'}


# =============================================================================
# Panel
# =============================================================================


class VIEW3D_PT_forge_sender(bpy.types.Panel):
    """N-panel under the 'Forge' tab — shows target Action/Camera
    labels and the Send to Flame button, or a disabled-state warning
    row when preflight fails (UI-SPEC §Panel Layout Contract)."""
    bl_label = "Send to Flame"
    bl_idname = "VIEW3D_PT_forge_sender"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Forge"
    bl_order = 0

    def draw(self, context):
        layout = self.layout
        preflight_error = preflight.check(context)

        if preflight_error is None:
            # Happy path — UI-SPEC §Row order (valid camera).
            cam_data = context.active_object.data
            layout.label(
                text=f"Target Action: {cam_data['forge_bake_action_name']}",
                icon='OUTLINER_OB_CAMERA')
            layout.label(
                text=f"Target Camera: {cam_data['forge_bake_camera_name']}",
                icon='CAMERA_DATA')
            layout.separator()
            layout.operator("forge.send_to_flame", icon='EXPORT')
        else:
            # Disabled state — UI-SPEC §B-1 (Phase 04.4):
            # show the warning row, the disabled existing button (kept for
            # muscle memory), AND the new enabled "choose Action" button
            # below it. Both buttons are visible simultaneously per D-04.
            row = layout.row()
            row.alert = True
            row.label(
                text="No Flame metadata — choose a target Action",
                icon='ERROR')
            layout.separator()

            # Existing disabled button — preserved for users switching
            # between stamped and unstamped cameras.
            col = layout.column()
            col.enabled = False
            col.operator("forge.send_to_flame", icon='EXPORT')

            # NEW (Phase 04.4 D-07): enabled fallback button — opens
            # the choose-Action dialog. Operator's poll() returns True
            # when active object is a CAMERA, so this row enables/
            # disables automatically based on selection.
            layout.operator(
                "forge.send_to_flame_choose_action",
                icon='EXPORT')


# =============================================================================
# Register / unregister
# =============================================================================


_CLASSES = (
    FORGE_OT_send_to_flame,
    FORGE_OT_send_to_flame_choose_action,
    VIEW3D_PT_forge_sender,
)


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
