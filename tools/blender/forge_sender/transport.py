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
