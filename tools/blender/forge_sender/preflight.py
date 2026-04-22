"""
forge_sender/preflight.py — Tier 1 validation for the Send to Flame button.

Why this module exists: the operator's poll() gates the Send button
and the operator's execute() re-checks (belt-and-braces, so
F3-search / keymap invocation can't bypass the panel gate). Both
call check() below; poll() uses only "is this None?", execute()
surfaces the returned string to the artist.

Scope boundaries:
  - Validation only. No network. No JSON. No bpy ops.
  - Duck-typed: does NOT import bpy. Accepts any object with
    ``.active_object`` where ``.active_object`` has ``.type`` and
    ``.data`` (dict-like for the custom-properties read).
  - Unit-testable with plain Python fakes (see
    tests/test_forge_sender_preflight.py).

Copy strings: the four Tier-1 strings below are EXACT per UI-SPEC
§Copywriting Contract §Preflight Tier 1 — IMP-02 literal requirement
fixes the missing-key naming, and drift breaks downstream tests.
"""
from __future__ import annotations

from typing import Optional


# Required custom-property keys on cam.data, in priority order.
# UI-SPEC §Preflight Tier 1 ``{missing_key}`` substitution rule:
# "If both are missing, name only the first." Order here IS the
# priority order — check forge_bake_action_name before camera_name.
_REQUIRED_STAMPED_KEYS = ("forge_bake_action_name", "forge_bake_camera_name")


def check(context) -> Optional[str]:
    """Validate that ``context.active_object`` is a forge-baked camera
    ready to send. Returns None on pass, or one of the four D-09
    Tier 1 copy strings on fail (UI-SPEC §Copywriting Contract).

    Duck-typed; accepts any object exposing ``.active_object`` with
    ``.type`` + ``.data`` (dict-like for custom-property reads).
    """
    obj = getattr(context, "active_object", None)
    if obj is None:
        return ("Send to Flame: no active object — select a forge-baked "
                "camera in the 3D viewport and try again")

    if getattr(obj, "type", None) != "CAMERA":
        return ("Send to Flame: active object is not a camera — select a "
                "forge-baked camera in the 3D viewport and try again")

    data = obj.data
    for key in _REQUIRED_STAMPED_KEYS:
        if key not in data:
            return (f"Send to Flame: active camera is missing '{key}' — "
                    f"this camera was not baked by forge-calibrator. "
                    f"Re-export from Flame via right-click → Camera Match → "
                    f"Export Camera to Blender")

    if data.get("forge_bake_source") != "flame":
        return ("Send to Flame: active camera was not baked by forge-calibrator "
                "(forge_bake_source != 'flame') — re-export from Flame via "
                "right-click → Camera Match → Export Camera to Blender")

    return None
