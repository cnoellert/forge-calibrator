"""Unit tests for tools/blender/forge_sender/transport.py.

What we test:
  - build_payload returns a {"code": str} dict with the Flame-side
    template filled in safely via repr()
  - The embedded code references all the pinned Flame-side operations
    (frame_rate context, v5_json_str_to_fbx, import_fbx_to_action,
    tempfile.mkdtemp, duck-typed Action resolution)
  - send() calls requests.post with the JSON contract (``json=``
    kwarg, not ``data=``)
  - parse_envelope routes success vs error envelopes correctly

What we don't test:
  - Live HTTP to forge-bridge (Plan 04 E2E).
  - Flame-side execution of the template (also Plan 04).

D-19 note: Plan 02-01 proved that ``flame.batch.frame_rate`` is a
plain NoneType slot on Flame 2026.2.1 — ``.get_value()`` raises
AttributeError, and the attribute stays None even with a live
Batch+clip+Action loaded. Recovery adopted: the Blender addon
owns the frame-rate ladder and passes the resolved value into
``build_payload(json_str, frame_rate_str)`` as a keyword argument.
The bridge-side template therefore receives frame_rate from the
addon, not by probing Flame. See ``memory/flame_batch_frame_rate.md``.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..",
                                "tools", "blender", "forge_sender"))

# requests must be importable for transport.py to load.
pytest.importorskip("requests")

import transport  # noqa: E402


class TestBuildPayload:
    def test_returns_dict_with_code_key(self):
        body = transport.build_payload('{"frames": []}', frame_rate="23.976 fps")
        assert isinstance(body, dict)
        assert "code" in body
        assert isinstance(body["code"], str)

    def test_embeds_json_string_via_repr(self):
        # repr() of a string produces a Python literal. If we probe
        # for the input JSON's content, it must appear somewhere in
        # the code body (inside the repr form).
        body = transport.build_payload('{"width": 1920}',
                                       frame_rate="23.976 fps")
        assert "1920" in body["code"]
        assert "width" in body["code"]

    def test_references_flame_api(self):
        body = transport.build_payload("{}", frame_rate="23.976 fps")
        code = body["code"]
        # D-19 note: flame.batch.frame_rate appears in a comment
        # documenting why the caller passes frame_rate (see module
        # docstring). The literal is grep-present for Plan 02-03
        # acceptance checks and to make the D-17→D-19 pivot easy
        # to find from source.
        assert "flame.batch.frame_rate" in code
        assert "v5_json_str_to_fbx" in code
        assert "import_fbx_to_action" in code

    def test_uses_tempfile_mkdtemp_with_prefix(self):
        body = transport.build_payload("{}", frame_rate="23.976 fps")
        assert 'tempfile.mkdtemp(prefix="forge_send_")' in body["code"]

    def test_zero_match_error_message(self):
        body = transport.build_payload("{}", frame_rate="23.976 fps")
        code = body["code"]
        assert "No Action named" in code
        assert "in current batch" in code
        assert "was it renamed or deleted" in code

    def test_ambiguous_match_error_message(self):
        body = transport.build_payload("{}", frame_rate="23.976 fps")
        code = body["code"]
        assert "Ambiguous:" in code
        assert "rename to disambiguate and resend" in code

    def test_resolves_action_duck_typed_exact_name(self):
        body = transport.build_payload("{}", frame_rate="23.976 fps")
        code = body["code"]
        assert 'hasattr(n, "import_fbx")' in code
        assert "n.name.get_value() == action_name" in code

    def test_rejects_non_string_input(self):
        with pytest.raises(TypeError):
            transport.build_payload({"width": 1920},  # dict, not str
                                    frame_rate="23.976 fps")

    def test_frame_rate_embedded_via_repr(self):
        # D-19: frame_rate flows from the Blender addon's ladder into
        # the Flame-side template as a Python literal. repr() escape
        # guarantees safety regardless of embedded quotes.
        body = transport.build_payload("{}", frame_rate="23.976 fps")
        assert "'23.976 fps'" in body["code"] or '"23.976 fps"' in body["code"]

    def test_rejects_non_string_frame_rate(self):
        # Guardrail: the ladder resolves to a string (e.g. "23.976 fps",
        # "24 fps") — if a caller accidentally passes a float or None,
        # fail fast with TypeError rather than silently producing a
        # malformed template.
        with pytest.raises(TypeError):
            transport.build_payload("{}", frame_rate=24.0)


class TestSend:
    def test_calls_requests_post_with_json_kwarg(self, monkeypatch):
        captured = {}

        def fake_post(url, *, json=None, timeout=None):
            captured["url"] = url
            captured["json"] = json
            captured["timeout"] = timeout
            resp = MagicMock()
            resp.json.return_value = {"result": None}
            resp.raise_for_status.return_value = None
            return resp

        monkeypatch.setattr(transport.requests, "post", fake_post)
        transport.send("{}", frame_rate="23.976 fps")
        assert captured["url"] == transport.BRIDGE_URL
        assert captured["url"] == "http://127.0.0.1:9999/exec"
        assert "code" in captured["json"]
        assert captured["timeout"] == 5.0

    def test_default_timeout_is_5_seconds(self, monkeypatch):
        captured = {}

        def fake_post(url, *, json=None, timeout=None):
            captured["timeout"] = timeout
            resp = MagicMock()
            resp.json.return_value = {}
            resp.raise_for_status.return_value = None
            return resp

        monkeypatch.setattr(transport.requests, "post", fake_post)
        transport.send("{}", frame_rate="23.976 fps")
        assert captured["timeout"] == transport.DEFAULT_TIMEOUT_S
        assert captured["timeout"] == 5.0

    def test_respects_timeout_override(self, monkeypatch):
        captured = {}

        def fake_post(url, *, json=None, timeout=None):
            captured["timeout"] = timeout
            resp = MagicMock()
            resp.json.return_value = {}
            resp.raise_for_status.return_value = None
            return resp

        monkeypatch.setattr(transport.requests, "post", fake_post)
        transport.send("{}", frame_rate="23.976 fps", timeout=10.0)
        assert captured["timeout"] == 10.0


class TestParseEnvelope:
    def test_success_returns_none_and_result(self):
        env = {"result": {"action_name": "X", "created": ["a"]},
               "stdout": "", "stderr": "", "error": None, "traceback": None}
        err, result = transport.parse_envelope(env)
        assert err is None
        assert result == {"action_name": "X", "created": ["a"]}

    def test_error_with_traceback(self):
        env = {"error": "boom", "traceback": "File \"fake.py\", line 1\n"}
        err, result = transport.parse_envelope(env)
        assert result is None
        assert err.startswith("Send to Flame failed: boom\n\n")
        assert "File \"fake.py\"" in err

    def test_error_without_traceback(self):
        env = {"error": "boom"}
        err, result = transport.parse_envelope(env)
        assert result is None
        assert err.startswith("Send to Flame failed: boom\n\n")

    def test_empty_error_string_treated_as_success(self):
        env = {"result": "R", "error": ""}
        err, result = transport.parse_envelope(env)
        assert err is None
        assert result == "R"
