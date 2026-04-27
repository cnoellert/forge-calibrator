"""
forge_sender/transport.py — HTTP transport to forge-bridge.

Why this module exists: the operator builds a v5 JSON payload via
flame_math.build_v5_payload, then needs to (a) wrap the payload in a
Flame-side Python template that runs v5_json_str_to_fbx +
import_fbx_to_action inside Flame, (b) POST it to forge-bridge at
http://127.0.0.1:9999/exec, and (c) parse the response envelope into
a "success or error message" shape the operator can surface to the
artist. Those three concerns live here, split for testability.

Contract (memory/flame_bridge_probing.md, 2026-04-19 update):
  POST http://127.0.0.1:9999/exec
    Content-Type: application/json
    Body: {"code": "<python>"}
  Response: {"result", "stdout", "stderr", "error", "traceback"}

Pure-builder + thin-runner split: ``build_payload`` composes the body
without touching the network so tests can assert the embedded-code
shape. ``send`` is the thin requests.post wrapper.
``parse_envelope`` splits the response into (error_message, result).

Security note (planner threat T-02-03-01): the v5 JSON string and the
frame_rate string are serialized into the Python code body via
``repr()`` — which Python guarantees produces a valid, unambiguous
string literal. We MUST NOT f-string user-controlled camera names,
metadata, or frame-rate values into the code body directly; every
dynamic value travels through ``json.dumps`` (JSON) or ``repr``
(Python literal) escape before landing in ``code``.

D-19 note (Plan 02-01 probe outcome):
  CONTEXT D-17 assumed that ``flame.batch.frame_rate.get_value()``
  returns the session frame rate as a string. Plan 02-01's live
  probe disproved this: ``flame.batch.frame_rate`` is a plain
  ``NoneType`` slot on Flame 2026.2.1 with no ``.get_value()``
  method, and the attribute stays ``None`` even with a loaded
  Batch + clip + Action. Recovery (D-19) is caller-owned frame
  rate: the Blender addon derives the value via a 3-level ladder
  (``cam["forge_bake_frame_rate"]`` custom prop → scene
  fps / fps_base → user popup) and passes it into
  :func:`build_payload` as ``frame_rate``. The Flame-side template
  receives the value from the payload, not by probing Flame.
  See memory/flame_batch_frame_rate.md for the probe findings.
"""
from __future__ import annotations

import ast
import json
from typing import Optional, Tuple

import requests  # D-13: bundled with Blender 4.5's Python


BRIDGE_URL = "http://127.0.0.1:9999/exec"  # UI-SPEC §Transport Tier literal
DEFAULT_TIMEOUT_S = 5.0                     # D-16; may bump to 10 s per
                                            # live-validation signal (CONTEXT
                                            # §Claude's Discretion)


# Flame-side template. Two substitution slots, both filled via
# ``repr()`` so the resulting Python literals are safe regardless of
# embedded quotes, newlines, or non-ASCII characters.
#
# Behavior inside Flame (executed by forge-bridge /exec):
#   1. tempfile.mkdtemp(prefix="forge_send_")            [D-03]
#   2. frame_rate is received from the addon via the payload
#      (D-19 recovery — Plan 02-01 disproved the D-17 assumption
#      that flame.batch.frame_rate.get_value() works; the batch
#      attribute is a NoneType slot in Flame 2026.2.1).
#   3. v5_json_str_to_fbx(v5_json_str, fbx_path,
#                         frame_rate=frame_rate)          [D-01]
#   4. Iterate flame.batch.nodes; duck-typed filter by
#      hasattr(n, "import_fbx"); exact-name match against
#      payload["custom_properties"]["forge_bake_action_name"];
#      0 / 2+ matches → RuntimeError (D-06, D-07, D-08).
#   5. import_fbx_to_action(action, fbx_path)             [from
#      forge_flame.fbx_io; defaults already narrowed for the
#      round-trip use case].
#   6. Assign {"action_name": ..., "created": [...]} to _result.
#   7. finally: shutil.rmtree(tmpdir) on success; preserve + print
#      the path on failure (D-03 mirror of Phase 1 D-14).
_FLAME_SIDE_TEMPLATE = '''\
import json
import os
import shutil
import tempfile

import flame
from forge_flame import fbx_ascii, fbx_io


def _forge_send():
    v5_json_str = {json_str_repr}
    # D-19: frame_rate is caller-provided (derived by the Blender
    # addon's 3-level ladder). Not probed from flame.batch.frame_rate
    # — that attribute is a NoneType slot on Flame 2026.2.1 and
    # .get_value() raises AttributeError. See Plan 02-01 probe.
    frame_rate = {frame_rate_repr}

    tmpdir = tempfile.mkdtemp(prefix="forge_send_")
    fbx_path = os.path.join(tmpdir, "incoming.fbx")
    # Phase 4.1 D-08: defensive instrumentation. Phase-tagged logs land
    # in <tmpdir>/forge_send_debug.log alongside incoming.fbx. The file
    # survives P-4's preserve-on-failure invariant naturally — no new
    # cleanup path. Log CONTENT: phase tags + counts + action names
    # ONLY. Never v5_json_str contents, never file contents, never
    # credentials (none involved). Keep lines lean.
    debuglog = os.path.join(tmpdir, "forge_send_debug.log")

    def _log(msg):
        # Phase 4.1 item 3: instrumentation. Logs land inside tmpdir so
        # P-4 preserve-on-failure covers them. Security: phase tags plus
        # counts plus action names ONLY — no file contents, no JSON body.
        try:
            with open(debuglog, "a") as f:
                print("[forge-send] %s" % msg, file=f)
        except Exception:
            pass  # instrumentation failures must never crash the send
        print("[forge-send] %s" % msg)

    success = False
    _log("step=start")
    try:
        # WR-02 defense-in-depth (02-REVIEW.md): fail loud if the
        # resolved frame_rate is not in _FPS_FROM_FRAME_RATE rather
        # than letting v5_json_str_to_fbx silently fall back to 24 fps
        # (which violates the Core Value of fps fidelity end-to-end).
        # The addon-side _resolve_frame_rate ladder already guards
        # this, but the two label sets (_FLAME_FPS_LABELS and
        # _FPS_FROM_FRAME_RATE) are currently duplicated (IN-02) — if
        # they ever drift, this check catches the mismatch before any
        # FBX gets written with the wrong KTime basis.
        if frame_rate not in fbx_ascii._FPS_FROM_FRAME_RATE:
            raise RuntimeError(
                "Unknown Flame frame rate: %r -- expected one of %s"
                % (frame_rate, sorted(fbx_ascii._FPS_FROM_FRAME_RATE))
            )
        _log("step=pre_fbx_parse fbx_path=%r" % fbx_path)
        # pixel_to_units=1.0 — the v5 JSON built by forge_sender.flame_math.
        # build_v5_payload already expresses position in FBX units (it
        # multiplied the Blender world-space coords by forge_bake_scale to
        # restore the FBX-unit values we originally read via fbx_to_v5_json).
        # v5_json_str_to_fbx's default pixel_to_units=0.1 assumes the caller
        # is passing Flame-PIXELS and divides by 10 to reach FBX units.
        # Applying that default here would double-scale: input FBX units
        # get another 0.1, Flame's import_fbx applies 10x on the way in,
        # net = 1/10. Positions came back 10x smaller than the original
        # before this fix. Pass 1.0 so the Lcl Translation written is
        # exactly the JSON value, and Flame's unit_to_pixels=10 on import
        # correctly undoes the 10x scale applied on the Flame export side.
        fbx_ascii.v5_json_str_to_fbx(
            v5_json_str, fbx_path, frame_rate=frame_rate,
            pixel_to_units=1.0,
        )
        _log("step=post_fbx_parse")

        payload = json.loads(v5_json_str)
        action_name = payload["custom_properties"]["forge_bake_action_name"]

        _log("step=pre_flame_batch_nodes_scan action_name=%r" % action_name)
        matches = [
            n for n in flame.batch.nodes
            if hasattr(n, "import_fbx") and n.name.get_value() == action_name
        ]
        _log("step=matched count=%d action_name=%r" % (len(matches), action_name))
        if not matches:
            raise RuntimeError(
                "No Action named '%s' in current batch — was it renamed or deleted?"
                % action_name
            )
        if len(matches) > 1:
            raise RuntimeError(
                "Ambiguous: %d Actions named '%s' — rename to disambiguate and resend"
                % (len(matches), action_name)
            )
        action = matches[0]

        _log("step=pre_import_fbx")
        created = fbx_io.import_fbx_to_action(action, fbx_path)
        _log("step=post_import_fbx created_count=%d" % len(created))

        # GAP-04.4-UAT-02: rename the imported camera to the Blender-side
        # name (`forge_bake_camera_name`) when the addon stamped one in
        # custom_properties. The Blender forge_sender stamping site at
        # tools/blender/forge_sender/__init__.py:551 always stamps the
        # active camera's `cam.name`; this rename closes the loop so the
        # Flame-side camera carries the Blender-side name end-to-end.
        #
        # Stereo-rig siblings (*_left/*_right) and FBX-internal nodes
        # (RootNode_*) are filtered by the duck-type predicate below the
        # return — we MUST NOT rename them here. Same predicate is
        # applied here so the rename targets only the primary camera.
        forge_bake_camera_name = payload.get("custom_properties", {{}}).get(
            "forge_bake_camera_name"
        )
        if forge_bake_camera_name:
            for c in created:
                try:
                    is_real_camera = (
                        all(hasattr(c, a) for a in ("position", "rotation", "fov", "focal"))
                        and c.name.get_value() != "Perspective"
                    )
                except Exception:
                    is_real_camera = False
                if is_real_camera:
                    try:
                        c.name.set_value(forge_bake_camera_name)
                    except Exception as exc:
                        _log("step=rename_failed err=%r" % (exc,))
                    else:
                        _log("step=renamed name=%r" % forge_bake_camera_name)
                    break  # rename only the FIRST duck-typed camera

        success = True
        # Filter per Phase 4.1 D-06: duck-type camera check mirrors
        # forge_flame.fbx_io.iter_keyframable_cameras:63-70. Drops FBX-internal
        # nodes (RootNode_*) and stereo-rig siblings (*_left/*_right) that
        # action.import_fbx() auto-spawns — they lack one or more of the four
        # camera attrs. Perspective-by-name exclusion matches fbx_io precedent.
        return {{
            "action_name": action_name,
            "created": [
                c.name.get_value() for c in created
                if all(hasattr(c, a) for a in ("position", "rotation", "fov", "focal"))
                and c.name.get_value() != "Perspective"
            ],
        }}
    finally:
        if success:
            shutil.rmtree(tmpdir, ignore_errors=True)
        else:
            print("[forge-send] tempdir preserved: %s" % tmpdir)


_forge_send()
'''


def build_payload(v5_json_str: str, *, frame_rate: str) -> dict:
    """Compose the bridge POST body: ``{"code": "<python>"}``.

    Pure builder — no network. ``v5_json_str`` and ``frame_rate`` are
    embedded via ``repr()`` (Python-literal escape) so the executor
    recovers them inside Flame without any ambiguity.

    Args:
        v5_json_str: v5 JSON payload as a string. The Flame-side
            template reconstructs the dict with ``json.loads``.
        frame_rate: Flame frame-rate string (one of the keys in
            ``forge_flame.fbx_ascii._FPS_FROM_FRAME_RATE``). Derived
            by the Blender addon via the D-19 3-level ladder and
            passed here — not probed from ``flame.batch.frame_rate``
            (which is broken in Flame 2026.2.1; see module docstring).

    Raises:
        TypeError: if ``v5_json_str`` or ``frame_rate`` is not a str.
    """
    if not isinstance(v5_json_str, str):
        raise TypeError(
            f"build_payload: expected v5_json_str to be str, got "
            f"{type(v5_json_str).__name__}. Serialize your dict with "
            f"json.dumps before passing it here.")
    if not isinstance(frame_rate, str):
        raise TypeError(
            f"build_payload: expected frame_rate to be str, got "
            f"{type(frame_rate).__name__}. The Blender addon's D-19 "
            f"ladder resolves to one of the keys in "
            f"_FPS_FROM_FRAME_RATE (e.g. '23.976 fps', '24 fps').")
    code = _FLAME_SIDE_TEMPLATE.format(
        json_str_repr=repr(v5_json_str),
        frame_rate_repr=repr(frame_rate),
    )
    return {"code": code}


def send(v5_json_str: str, *, frame_rate: str,
         timeout: float = DEFAULT_TIMEOUT_S) -> dict:
    """POST the v5 payload to forge-bridge and return the envelope.

    Raises:
        requests.exceptions.ConnectionError, requests.exceptions.Timeout,
        requests.exceptions.HTTPError — surfaced as UI-SPEC §Transport
        Tier by the caller.
    """
    payload = build_payload(v5_json_str, frame_rate=frame_rate)
    response = requests.post(BRIDGE_URL, json=payload, timeout=timeout)
    response.raise_for_status()
    return response.json()


def parse_envelope(envelope: dict) -> Tuple[Optional[str], Optional[dict]]:
    """Split a bridge response envelope into ``(error_message, result)``.

    Envelope shape: ``{"result", "stdout", "stderr", "error", "traceback"}``.

    The bridge wraps eval'd expression values in ``repr()``, so when
    the Flame-side template ends with ``_forge_send()`` (an expression
    returning a dict), the bridge's ``result`` field is a string like
    ``"{'action_name': 'foo', 'created': ['cam1']}"``. We parse that
    back into the dict with :func:`ast.literal_eval` so the operator
    sees a real dict.

    Returns:
        ``(None, result_dict)`` on success (``error`` field absent or
        empty). ``result_dict`` is either a parsed dict or ``None`` if
        the bridge returned no value.
        ``(formatted_error_string, None)`` on remote failure — the
        string follows UI-SPEC §Remote Tier copy template:
        ``Send to Flame failed: {error}\\n\\n{traceback}``.
    """
    error = envelope.get("error")
    if error:
        traceback = envelope.get("traceback") or ""
        return (f"Send to Flame failed: {error}\n\n{traceback}", None)
    raw = envelope.get("result")
    if isinstance(raw, str):
        try:
            return (None, ast.literal_eval(raw))
        except (ValueError, SyntaxError):
            # Non-literal string — pass through unchanged so callers
            # can still inspect it (preserves compatibility with
            # earlier bridge responses that sent back bare strings).
            return (None, raw)
    return (None, raw)


# =============================================================================
# Phase 04.4 additions: list Actions in current Batch + create new Action
# =============================================================================

# RESEARCH §Pattern 3 + §Code Example 3 — verified live 2026-04-25 via
# forge-bridge probe. The hasattr() guard on item.type is defensive: in
# the bridge context (NOT the action-hook context), item.type IS a
# PyAttribute and .get_value() is the correct call. The action-hook
# Pitfall 1 (item.type is a plain str) does NOT apply here — this code
# runs inside flame.batch.nodes iteration, not inside
# get_action_custom_ui_actions.
_CODE_LIST_ACTIONS = (
    "import flame\n"
    "[n.name.get_value() for n in flame.batch.nodes "
    "if hasattr(n.type, 'get_value') and n.type.get_value() == 'Action']"
)


def list_batch_actions(timeout: float = DEFAULT_TIMEOUT_S) -> list:
    """Return the names of all Action nodes in the current Flame Batch.

    Scope is the currently-loaded Batch only (D-08) — Actions in other
    Desktops or Reels are not visible here. Empty Batch returns [].

    Raises:
        requests.exceptions.* on transport failure (caller surfaces via
            UI-SPEC §Transport Tier popup).
        RuntimeError on bridge-side error envelope or malformed result.
    """
    response = requests.post(
        BRIDGE_URL,
        json={"code": _CODE_LIST_ACTIONS},
        timeout=timeout,
    )
    response.raise_for_status()
    envelope = response.json()
    if envelope.get("error"):
        raise RuntimeError(
            f"forge-bridge failed listing Actions: {envelope['error']}")
    raw = envelope.get("result") or "[]"
    try:
        result = ast.literal_eval(raw)
    except (ValueError, SyntaxError) as exc:
        raise RuntimeError(
            f"forge-bridge returned malformed Action list: {raw!r}") from exc
    # Defensive: ensure we got a list of strings.
    if not isinstance(result, list):
        raise RuntimeError(
            f"forge-bridge returned non-list Action result: {raw!r}")
    return result


# RESEARCH §P-03: Flame raises RuntimeError on Action name collision —
# `name.set_value()` does NOT auto-suffix. The bridge envelope's
# "error" field will contain the substring "Could not set Batch node
# name" when the user-provided name conflicts with an existing Action.
# The addon-side handler (FORGE_OT_send_to_flame_choose_action.execute)
# detects this substring and surfaces a clear collision error message.
# DO NOT remove the substring from this docstring — Wave 0 test
# test_create_action_name_collision_error_string_match grep-asserts it
# stays in this file as a canary against rename drift.
#
# SECURITY (T-04.4-04 / V5 ASVS L1 / transport.py:23-29 contract):
# the user-provided `name` is embedded via repr() — NEVER f-string
# interpolation. repr() guarantees a valid, unambiguous Python str
# literal regardless of whatever quotes / backslashes / unicode the
# user types. If a developer ever changes this to f"...'{name}'..."
# the Wave 0 test test_make_create_code_embeds_name_via_repr fails
# (the test asserts that the rendered code contains the
# single-quoted form 'MyAction' — i.e. the repr() form — and not the
# double-quoted form "MyAction").
def make_create_code(name: str) -> str:
    """Build the Flame-side Python that creates a new Action and renames it.

    The user-provided name is embedded via repr() (security T-04.4-04 /
    transport.py:23-29) — never f-stringed. On Flame side,
    `name.set_value()` raises RuntimeError on collision (RESEARCH §P-03,
    §Pitfall 2). The bridge envelope's "error" field will contain the
    substring 'Could not set Batch node name' on collision; caller
    detects this and surfaces a user-friendly message.

    Returns the Python code string ready to POST as {"code": <here>}.
    The bridge response's "result" field will be repr() of the new
    Action's name (e.g. "'MyAction'") — parse with ast.literal_eval.
    """
    if not isinstance(name, str):
        raise TypeError(
            f"make_create_code: expected name to be str, got "
            f"{type(name).__name__}")
    return (
        "import flame\n"
        "_n = flame.batch.create_node('Action')\n"
        f"_n.name.set_value({name!r})\n"
        "_n.name.get_value()\n"
    )
