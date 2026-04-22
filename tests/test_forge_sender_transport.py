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


# ---------------------------------------------------------------------------
# Helpers for filter tests (Phase 4.1 item 1 — GA-3 stereo-rig popup filter)
# ---------------------------------------------------------------------------

class _Attr:
    """Minimal Flame PyAttribute stub — supports get_value() only."""

    def __init__(self, value):
        self._value = value

    def get_value(self):
        return self._value


def _make_node(name, *, has_position=True, has_rotation=True,
               has_fov=True, has_focal=True):
    """Build a fake Flame Action child node with selectable camera attrs."""

    class _Node:
        pass

    n = _Node()
    n.name = _Attr(name)
    if has_position:
        n.position = _Attr(0.0)
    if has_rotation:
        n.rotation = _Attr(0.0)
    if has_fov:
        n.fov = _Attr(50.0)
    if has_focal:
        n.focal = _Attr(35.0)
    return n


def _apply_filter(nodes):
    """Apply the _FLAME_SIDE_TEMPLATE filter predicate to a list of nodes.

    Mirrors the predicate that will appear in _FLAME_SIDE_TEMPLATE after
    Plan 04.1-01 ships.  Written here as a pure-Python expression so the
    tests stay RED until the actual template is updated.

    The predicate is:
        all(hasattr(c, a) for a in ("position", "rotation", "fov", "focal"))
        and c.name.get_value() != "Perspective"

    This helper executes the template as-built to exercise the REAL filter —
    tests verify both the template text (grep checks) and the runtime
    behaviour (this helper).
    """
    # Exec the formatted template in a fake Flame namespace so we can
    # inspect the return value of _forge_send() with controlled nodes.
    import json as _json
    import ast as _ast

    # We need a minimal v5 JSON with the required custom_properties keys
    # so the template doesn't error before reaching the filter.
    dummy_json = _json.dumps({
        "custom_properties": {
            "forge_bake_action_name": "TestAction",
        }
    })

    # Build a fake namespace matching what the template imports.
    class _FakeAction:
        pass

    fake_action = _FakeAction()
    fake_action.name = _Attr("TestAction")
    fake_action.import_fbx = lambda path: nodes  # returns the node list

    class _FakeBatch:
        nodes = [fake_action]

    class _FakeFlame:
        batch = _FakeBatch()

    class _FakeFbxIo:
        @staticmethod
        def import_fbx_to_action(action, fbx_path):
            return nodes

    class _FakeFbxAscii:
        @staticmethod
        def v5_json_str_to_fbx(v5_json_str, fbx_path, *, frame_rate):
            pass  # no-op

    import tempfile as _tempfile
    import os as _os
    import shutil as _shutil

    fake_globals = {
        "json": _json,
        "os": _os,
        "shutil": _shutil,
        "tempfile": _tempfile,
        "flame": _FakeFlame(),
        "fbx_io": _FakeFbxIo(),
        "fbx_ascii": _FakeFbxAscii(),
    }

    # Format the template with safe dummy values.
    code = transport._FLAME_SIDE_TEMPLATE.format(
        json_str_repr=repr(dummy_json),
        frame_rate_repr=repr("24 fps"),
    )

    local_ns = {}
    exec(code, fake_globals, local_ns)  # defines _forge_send
    result = eval("_forge_send()", fake_globals, local_ns)
    return result.get("created", [])


class TestFilterStereoRigAndFbxInternalNodes:
    """Phase 4.1 item 1 (GA-3) — filter inside _FLAME_SIDE_TEMPLATE.

    These tests are RED until _FLAME_SIDE_TEMPLATE replaces the bare list-comp
    with the duck-type + Perspective-name predicate per D-06.
    """

    def test_filter_accepts_real_camera(self):
        """A node with all four camera attrs and name != 'Perspective' must appear."""
        cam = _make_node("Camera1")
        result = _apply_filter([cam])
        assert "Camera1" in result

    def test_filter_drops_node_missing_fov(self):
        """A RootNode_*-style node lacking fov must be dropped."""
        non_cam = _make_node("RootNode_Scene5", has_fov=False)
        result = _apply_filter([non_cam])
        assert "RootNode_Scene5" not in result

    def test_filter_drops_perspective_by_name(self):
        """Perspective has all four camera attrs but must be excluded by name
        (matches iter_keyframable_cameras:67 precedent from fbx_io.py)."""
        perspective = _make_node("Perspective")
        result = _apply_filter([perspective])
        assert "Perspective" not in result

    def test_filter_drops_stereo_rig_sibling_lacking_focal(self):
        """Stereo-rig siblings (*_left, *_right) that lack fov/focal must be dropped."""
        left_cam = _make_node("Camera1_left", has_fov=False, has_focal=False)
        result = _apply_filter([left_cam])
        assert "Camera1_left" not in result

    def test_filter_preserves_list_order(self):
        """Filter must preserve order of real cameras (no set-based reordering)."""
        cam_a = _make_node("CameraA")
        cam_b = _make_node("CameraB")
        cam_c = _make_node("CameraC")
        result = _apply_filter([cam_a, cam_b, cam_c])
        assert result == ["CameraA", "CameraB", "CameraC"]

    def test_template_contains_duck_type_predicate(self):
        """The template string must contain the duck-type hasattr predicate verbatim."""
        assert 'all(hasattr(c, a) for a in ("position", "rotation", "fov", "focal"))' \
            in transport._FLAME_SIDE_TEMPLATE

    def test_template_contains_perspective_exclusion(self):
        """The template string must contain the Perspective-by-name exclusion."""
        assert 'c.name.get_value() != "Perspective"' in transport._FLAME_SIDE_TEMPLATE


# ---------------------------------------------------------------------------
# Helpers for instrumentation tests (Phase 4.1 item 3 — GA-4 crash logging)
# ---------------------------------------------------------------------------

def _exec_template_with_fakes(
    action_name="TestAction",
    *,
    action_exists=True,
    patch_rmtree=True,
):
    """Execute _FLAME_SIDE_TEMPLATE in a fake Flame namespace.

    Returns ``(result, log_content, tmpdir_path)`` on success path,
    ``(None, log_content, tmpdir_path)`` on failure path (RuntimeError raised
    by the template — the log file survives because P-4 preserves the tempdir
    on failure).

    ``patch_rmtree``: when True (default), monkey-patches shutil.rmtree inside
    the template namespace to a no-op so the log file survives for assertion
    even on the success path.  Tests that verify P-4 cleanup behaviour set
    this to False and inspect tmpdir absence instead.

    Security contract: log_content must NEVER contain v5_json_str body or
    credentials.  Test I5 asserts this.
    """
    import json as _json
    import os as _os
    import shutil as _shutil
    import tempfile as _tempfile

    dummy_json = _json.dumps({
        "custom_properties": {
            "forge_bake_action_name": action_name,
        }
    })

    cam = _make_node("BakedCamera")
    fake_action = type("_FakeAction", (), {
        "name": _Attr(action_name),
        "import_fbx": lambda self, path: [cam],  # noqa: ARG005
    })()

    class _FakeBatch:
        nodes = [fake_action] if action_exists else []

    class _FakeFlame:
        batch = _FakeBatch()

    class _FakeFbxIo:
        @staticmethod
        def import_fbx_to_action(action, fbx_path):  # noqa: ARG004
            return [cam]

    class _FakeFbxAscii:
        @staticmethod
        def v5_json_str_to_fbx(v5_json_str, fbx_path, *, frame_rate):  # noqa: ARG004
            # no-op; just create the file so the template doesn't error
            open(fbx_path, "w").write("")  # noqa: WPS515

    # Capture tmpdir paths so we can read the log after the template runs.
    created_tmpdirs = []
    original_mkdtemp = _tempfile.mkdtemp

    def _tracking_mkdtemp(*args, **kwargs):
        path = original_mkdtemp(*args, **kwargs)
        created_tmpdirs.append(path)
        return path

    rmtree_calls = []

    def _fake_rmtree(path, **kwargs):  # noqa: ARG001
        rmtree_calls.append(path)
        # Do NOT actually remove — let log survive for assertion.

    # Use types.SimpleNamespace so method lookup doesn't bind 'self',
    # which would cause tempfile.mkdtemp(prefix=...) to pass the namespace
    # object as the first positional argument to the real mkdtemp.
    import types as _types
    fake_shutil = _types.SimpleNamespace(
        rmtree=_fake_rmtree if patch_rmtree else _shutil.rmtree,
    )
    fake_tempfile = _types.SimpleNamespace(mkdtemp=_tracking_mkdtemp)

    fake_globals = {
        "json": _json,
        "os": _os,
        "shutil": fake_shutil,
        "tempfile": fake_tempfile,
        "flame": _FakeFlame(),
        "fbx_io": _FakeFbxIo(),
        "fbx_ascii": _FakeFbxAscii(),
    }

    code = transport._FLAME_SIDE_TEMPLATE.format(
        json_str_repr=repr(dummy_json),
        frame_rate_repr=repr("24 fps"),
    )

    # The template ends with a bare `_forge_send()` call.  Strip it so exec
    # only defines the function; we then call it once via eval so we can
    # cleanly catch RuntimeError from the failure path.
    # (This mirrors the _apply_filter helper approach from Plan 04.1-01.)
    code_without_call = code.rstrip()
    if code_without_call.endswith("_forge_send()"):
        code_without_call = code_without_call[: -len("_forge_send()")]

    local_ns = {}
    exec(code_without_call, fake_globals, local_ns)  # defines _forge_send only

    result = None
    raised = None
    try:
        result = eval("_forge_send()", fake_globals, local_ns)
    except RuntimeError as exc:
        raised = exc

    # Read the log file from the first tmpdir created.
    log_content = ""
    tmpdir_path = created_tmpdirs[0] if created_tmpdirs else None
    if tmpdir_path:
        log_path = _os.path.join(tmpdir_path, "forge_send_debug.log")
        if _os.path.exists(log_path):
            with open(log_path) as f:
                log_content = f.read()

    # Cleanup: if we patched rmtree, the tmpdir is still on disk; remove now.
    if patch_rmtree and tmpdir_path and _os.path.isdir(tmpdir_path):
        _shutil.rmtree(tmpdir_path, ignore_errors=True)

    if raised is not None:
        return (None, log_content, tmpdir_path)
    return (result, log_content, tmpdir_path)


class TestInstrumentationLogging:
    """Phase 4.1 item 3 (GA-4) — forge_send_debug.log written by _FLAME_SIDE_TEMPLATE.

    Tests I1-I6 match the <behavior> block in 04.1-03-PLAN.md.
    These tests are RED until _FLAME_SIDE_TEMPLATE adds the _log helper and
    phase-tagged log calls at start / pre_fbx_parse / post_fbx_parse /
    pre_flame_batch_nodes_scan / matched / pre_import_fbx / post_import_fbx.
    """

    def test_i1_success_path_log_file_exists_with_all_phases(self):
        """I1: on SUCCESS path, log file exists and contains all six phase tags."""
        result, log_content, _ = _exec_template_with_fakes()
        assert result is not None, "template should succeed when action exists"
        # All six phase tags must be present.
        for phase in (
            "step=start",
            "step=pre_fbx_parse",
            "step=post_fbx_parse",
            "step=pre_flame_batch_nodes_scan",
            "step=matched",
            "step=pre_import_fbx",
            "step=post_import_fbx",
        ):
            assert phase in log_content, (
                f"Expected log phase tag {phase!r} not found in log:\n{log_content}"
            )

    def test_i2_success_path_rmtree_called_on_tmpdir(self):
        """I2: on SUCCESS path, shutil.rmtree is called (P-4 cleanup invariant).

        We verify the rmtree call happens by NOT patching rmtree and confirming
        the tmpdir is gone after the template runs.
        """
        import os as _os
        import tempfile as _tempfile

        # Use a real tmpdir to check it disappears.
        # We won't patch rmtree, so the SUCCESS path should clean up.
        # To inspect the log before cleanup, we must read it DURING exec — but
        # that's not easy without a side-channel.  Instead we verify the
        # contract: result is not None (success) AND tmpdir is removed.
        # Patch only to track which tmpdir was created.
        original_mkdtemp = _tempfile.mkdtemp
        created_tmpdirs = []

        import json as _json
        import shutil as _shutil

        dummy_json = _json.dumps({
            "custom_properties": {"forge_bake_action_name": "TestAction"}
        })
        cam = _make_node("BakedCamera")
        fake_action = type("_FA", (), {
            "name": _Attr("TestAction"),
            "import_fbx": lambda self, path: [cam],
        })()

        class _FakeBatch2:
            nodes = [fake_action]

        class _FakeFlame2:
            batch = _FakeBatch2()

        class _FakeFbxIo2:
            @staticmethod
            def import_fbx_to_action(action, fbx_path):  # noqa: ARG004
                return [cam]

        class _FakeFbxAscii2:
            @staticmethod
            def v5_json_str_to_fbx(v5_json_str, fbx_path, *, frame_rate):  # noqa: ARG004
                open(fbx_path, "w").write("")  # noqa: WPS515

        def _tracking_mkdtemp(*args, **kwargs):
            path = original_mkdtemp(*args, **kwargs)
            created_tmpdirs.append(path)
            return path

        import tempfile as _tempfile2  # noqa: F401
        import types as _types2
        fake_globals = {
            "json": _json,
            "os": _os,
            "shutil": _shutil,
            "tempfile": _types2.SimpleNamespace(mkdtemp=_tracking_mkdtemp),
            "flame": _FakeFlame2(),
            "fbx_io": _FakeFbxIo2(),
            "fbx_ascii": _FakeFbxAscii2(),
        }

        code = transport._FLAME_SIDE_TEMPLATE.format(
            json_str_repr=repr(dummy_json),
            frame_rate_repr=repr("24 fps"),
        )
        local_ns = {}
        exec(code, fake_globals, local_ns)
        result = eval("_forge_send()", fake_globals, local_ns)

        assert result is not None, "template should succeed"
        assert created_tmpdirs, "mkdtemp should have been called"
        # P-4: on success path, rmtree must have been called — tmpdir gone.
        tmpdir = created_tmpdirs[0]
        assert not _os.path.isdir(tmpdir), (
            "Success path must remove tmpdir via shutil.rmtree"
        )

    def test_i3_failure_path_log_preserved_with_scan_and_matched(self):
        """I3: on FAILURE path (no action found), log file preserved with scan phase."""
        result, log_content, tmpdir_path = _exec_template_with_fakes(
            action_name="NonExistentAction",
            action_exists=False,
        )
        assert result is None, "template should raise RuntimeError on missing action"
        # Log must be preserved on failure path (P-4 invariant).
        assert log_content, "log file must survive on failure path"
        assert "step=pre_flame_batch_nodes_scan" in log_content
        assert "step=matched" in log_content

    def test_i4_log_format_every_line_starts_with_forge_send_tag_and_step(self):
        """I4: every log line starts with [forge-send] and contains a step= key."""
        _, log_content, _ = _exec_template_with_fakes()
        assert log_content, "log must not be empty on success path"
        lines = [l for l in log_content.splitlines() if l.strip()]
        for line in lines:
            assert line.startswith("[forge-send]"), (
                f"Log line does not start with [forge-send]: {line!r}"
            )
            assert "step=" in line, (
                f"Log line missing step= key: {line!r}"
            )

    def test_i5_security_no_json_body_in_log(self):
        """I5: log must NOT contain v5_json_str contents (security gate)."""
        _, log_content, _ = _exec_template_with_fakes()
        # The dummy JSON body contains "forge_bake_action_name" — this must NOT
        # appear in the log (it's a key inside the JSON body, not a phase tag).
        assert "forge_bake_action_name" not in log_content, (
            "Security gate: JSON body key must not appear in log"
        )
        # The string "v5_json_str" must not appear in log content.
        assert "v5_json_str" not in log_content, (
            "Security gate: variable name v5_json_str must not appear in log"
        )

    def test_i6_failure_path_preserves_existing_tempdir_print(self):
        """I6: failure path still prints the [forge-send] tempdir preserved line."""
        import io
        import sys as _sys

        captured = io.StringIO()
        old_stdout = _sys.stdout
        _sys.stdout = captured
        try:
            _exec_template_with_fakes(
                action_name="GoneAction",
                action_exists=False,
            )
        finally:
            _sys.stdout = old_stdout

        stdout_output = captured.getvalue()
        assert "tempdir preserved" in stdout_output, (
            "Failure path must still print 'tempdir preserved' for bridge envelope visibility"
        )

    def test_template_contains_forge_send_debug_log_filename(self):
        """Template string must reference forge_send_debug.log (grep anchor)."""
        assert "forge_send_debug.log" in transport._FLAME_SIDE_TEMPLATE

    def test_template_contains_all_six_step_tags(self):
        """Template string must contain all six phase step= tags."""
        template = transport._FLAME_SIDE_TEMPLATE
        for tag in (
            "step=start",
            "step=pre_fbx_parse",
            "step=post_fbx_parse",
            "step=pre_flame_batch_nodes_scan",
            "step=matched",
            "step=pre_import_fbx",
            "step=post_import_fbx",
        ):
            assert tag in template, (
                f"Template missing phase tag {tag!r}"
            )
