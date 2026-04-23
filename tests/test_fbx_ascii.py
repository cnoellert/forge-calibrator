"""
Unit tests for forge_flame.fbx_ascii.

Organized in three tiers:

1. Tokenizer — small string snippets exercising each token class.
2. Parser — small FBX-shaped documents covering block structure,
   Properties70 lines, and the ``*N { a: ... }`` array form.
3. Extraction — against real Flame-emitted FBX files in
   ``tests/fixtures/``, checking that known camera values (position,
   rotation, FOV, animation curves) land in the v5 JSON correctly.

Fixtures were captured from a live Flame 2026.2.1 session during the
v6.2 probing work (2026-04-19):
  - ``forge_fbx_probe.fbx`` — static export, ``bake_animation=False``.
  - ``forge_fbx_baked.fbx`` — static export, ``bake_animation=True``
    (two-keyframe endpoints on each curve).

Source camera state in both: position (0, 0, 4747.64), rotation (0, 0, 0),
vfov 40°, default Flame Super-16 film back (16mm vertical).
"""

import json
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from forge_flame.fbx_ascii import (  # noqa: E402
    FBX_KTIME_PER_SECOND,
    FBXNode,
    emit_fbx_ascii,
    fbx_to_v5_json,
    frame_from_ktime,
    ktime_from_frame,
    ktime_per_frame,
    parse_fbx_ascii,
    v5_json_str_to_fbx,
    v5_json_to_fbx,
    _tokenize,
    _T_COLON,
    _T_COMMA,
    _T_IDENT,
    _T_LBRACE,
    _T_NUMBER,
    _T_RBRACE,
    _T_STAR,
    _T_STRING,
)

FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


# =============================================================================
# Group 1: Tokenizer
# =============================================================================


class TestTokenizer:
    """Basic lexical sanity — each token kind, edge cases on numbers,
    comment/whitespace handling."""

    def _kinds(self, text):
        return [t[0] for t in _tokenize(text)]

    def _values(self, text):
        return [t[1] for t in _tokenize(text)]

    def test_empty(self):
        assert _tokenize("") == []

    def test_whitespace_only(self):
        assert _tokenize("   \n\t  \r\n") == []

    def test_comments_stripped(self):
        text = "; this is a comment\nHello: 1"
        kinds = self._kinds(text)
        assert kinds == [_T_IDENT, _T_COLON, _T_NUMBER]

    def test_identifier(self):
        toks = _tokenize("FBXHeaderVersion")
        assert toks == [(_T_IDENT, "FBXHeaderVersion")]

    def test_identifier_with_digits(self):
        toks = _tokenize("Properties70")
        assert toks == [(_T_IDENT, "Properties70")]

    def test_string_simple(self):
        toks = _tokenize('"hello"')
        assert toks == [(_T_STRING, "hello")]

    def test_string_with_spaces(self):
        # FBX uses strings with spaces for property keys like "Lcl Translation".
        toks = _tokenize('"Lcl Translation"')
        assert toks == [(_T_STRING, "Lcl Translation")]

    def test_string_empty(self):
        toks = _tokenize('""')
        assert toks == [(_T_STRING, "")]

    def test_number_integer(self):
        toks = _tokenize("1004")
        assert toks == [(_T_NUMBER, 1004)]

    def test_number_large_integer(self):
        # FBX KTime values routinely exceed 1e10.
        toks = _tokenize("46186158000")
        assert toks == [(_T_NUMBER, 46186158000)]

    def test_number_float(self):
        toks = _tokenize("1.33333333333333")
        assert toks == [(_T_NUMBER, pytest.approx(1.33333333333333))]

    def test_number_negative_zero(self):
        # Seen in the FBX for rotation values like -0.
        toks = _tokenize("-0")
        assert toks == [(_T_NUMBER, 0)]  # int(-0) == 0 is fine

    def test_number_negative_float(self):
        toks = _tokenize("-90")
        assert toks == [(_T_NUMBER, -90)]

    def test_number_scientific(self):
        toks = _tokenize("1.5e-3")
        assert toks == [(_T_NUMBER, pytest.approx(1.5e-3))]

    def test_punctuation(self):
        kinds = self._kinds(": , { } *")
        assert kinds == [_T_COLON, _T_COMMA, _T_LBRACE, _T_RBRACE, _T_STAR]

    def test_mixed_line(self):
        text = 'P: "UpAxis", "int", "Integer", "",1'
        kinds = self._kinds(text)
        assert kinds == [
            _T_IDENT, _T_COLON,
            _T_STRING, _T_COMMA,
            _T_STRING, _T_COMMA,
            _T_STRING, _T_COMMA,
            _T_STRING, _T_COMMA,
            _T_NUMBER,
        ]

    def test_bare_identifier_value(self):
        # FBX lines like ``Shading: Y`` use a bare identifier as the value.
        text = "Shading: Y"
        vals = self._values(text)
        assert vals == ["Shading", ":", "Y"]

    def test_array_prefix(self):
        text = "KeyTime: *2 {\n a: 0,1926347345\n}"
        kinds = self._kinds(text)
        # KeyTime : * 2 { a : 0 , 1926347345 }
        assert kinds[:6] == [_T_IDENT, _T_COLON, _T_STAR, _T_NUMBER, _T_LBRACE, _T_IDENT]


# =============================================================================
# Group 2: Parser
# =============================================================================


class TestParser:
    """Recursive-descent parser — blocks, nested blocks, Properties70
    lines, and the ``*N { a: ... }`` array flattening behavior."""

    def test_empty_document(self):
        assert parse_fbx_ascii("") == []

    def test_simple_scalar(self):
        nodes = parse_fbx_ascii("Version: 7700")
        assert len(nodes) == 1
        n = nodes[0]
        assert n.name == "Version"
        assert n.values == [7700]
        assert n.children == []

    def test_simple_block(self):
        text = """
        FBXHeaderExtension: {
            FBXHeaderVersion: 1004
            FBXVersion: 7700
        }
        """
        nodes = parse_fbx_ascii(text)
        assert len(nodes) == 1
        root = nodes[0]
        assert root.name == "FBXHeaderExtension"
        assert root.values == []
        assert len(root.children) == 2
        assert root.children[0].name == "FBXHeaderVersion"
        assert root.children[0].values == [1004]

    def test_block_with_header_values(self):
        # Shape: Model: ID, "Model::Name", "Camera" { ... }
        text = 'Model: 1234, "Model::Default", "Camera" { Version: 232 }'
        nodes = parse_fbx_ascii(text)
        m = nodes[0]
        assert m.name == "Model"
        assert m.values == [1234, "Model::Default", "Camera"]
        assert len(m.children) == 1

    def test_tuple_values(self):
        text = "Position: 0,0,0"
        nodes = parse_fbx_ascii(text)
        assert nodes[0].name == "Position"
        assert nodes[0].values == [0, 0, 0]

    def test_properties70_line(self):
        text = """
        Properties70: {
            P: "UpAxis", "int", "Integer", "",1
            P: "Lcl Translation", "Lcl Translation", "", "A",0,0,474.764068603516
        }
        """
        nodes = parse_fbx_ascii(text)
        props = nodes[0]
        assert props.name == "Properties70"
        assert len(props.children) == 2
        p1 = props.children[0]
        assert p1.name == "P"
        assert p1.values[0] == "UpAxis"
        assert p1.values[-1] == 1
        p2 = props.children[1]
        assert p2.values[0] == "Lcl Translation"
        assert p2.values[-3:] == [0, 0, pytest.approx(474.764068603516)]

    def test_array_flattens_into_values(self):
        """The ``*N { a: v1, v2, ... }`` form should flatten the array
        values up into the enclosing node's ``values`` list so callers
        don't need to descend through an ``a:`` child."""
        text = """
        KeyTime: *3 {
            a: 10, 20, 30
        }
        """
        nodes = parse_fbx_ascii(text)
        kt = nodes[0]
        assert kt.name == "KeyTime"
        assert kt.array_len == 3
        assert kt.values == [10, 20, 30]
        # And the `a:` child is consumed, not surfaced.
        assert kt.find("a") is None

    def test_nested_blocks(self):
        text = """
        A: {
            B: {
                C: 7
            }
        }
        """
        nodes = parse_fbx_ascii(text)
        assert nodes[0].find("B").find("C").values == [7]

    def test_sibling_blocks_at_top_level(self):
        text = """
        GlobalSettings: { Version: 1000 }
        Documents: { Count: 1 }
        """
        nodes = parse_fbx_ascii(text)
        assert len(nodes) == 2
        assert nodes[0].name == "GlobalSettings"
        assert nodes[1].name == "Documents"

    def test_connection_lines(self):
        text = """
        Connections: {
            ;Model::Default, Model::RootNode
            C: "OO",5496786432,0
            ;AnimCurveNode::FieldOfView, NodeAttribute::Default
            C: "OP",105553137408000,5496790016, "FieldOfView"
        }
        """
        nodes = parse_fbx_ascii(text)
        conns = nodes[0]
        assert conns.name == "Connections"
        assert len(conns.children) == 2
        assert conns.children[0].values == ["OO", 5496786432, 0]
        assert conns.children[1].values == [
            "OP", 105553137408000, 5496790016, "FieldOfView",
        ]


# =============================================================================
# Group 3: KTime conversion
# =============================================================================


class TestKTime:
    """Frame-rate <-> FBX KTime conversion. FBX uses 46186158000 ticks
    per second across all project rates; the frame rate only changes
    what frame number a given KTime maps to."""

    def test_ktime_per_frame_24fps(self):
        per_frame = ktime_per_frame("24 fps")
        assert per_frame == pytest.approx(FBX_KTIME_PER_SECOND / 24.0)

    def test_ktime_per_frame_23_976(self):
        per_frame = ktime_per_frame("23.976 fps")
        # Should use the EXACT NTSC 24000/1001 ratio, not the truncated 23.976.
        expected = FBX_KTIME_PER_SECOND * 1001.0 / 24000.0
        assert per_frame == pytest.approx(expected, rel=1e-9)

    def test_ktime_round_trip(self):
        for rate in ("23.976 fps", "24 fps", "25 fps", "30 fps"):
            for frame in (0, 1, 24, 100, 1001, 5000):
                kt = ktime_from_frame(frame, rate)
                back = frame_from_ktime(kt, rate)
                assert back == frame, f"round-trip failed: {frame}@{rate}"


# =============================================================================
# Group 4: Extraction from real Flame FBX fixtures
# =============================================================================


class TestStaticFixture:
    """Static export (``bake_animation=False``). Camera position / rotation
    / FoV live only as static Lcl Translation values + NodeAttribute
    Properties70, with single-keyframe AnimCurves."""

    @pytest.fixture
    def fbx_path(self):
        p = os.path.join(FIXTURE_DIR, "forge_fbx_probe.fbx")
        if not os.path.exists(p):
            pytest.skip(f"missing fixture: {p}")
        return p

    def test_parses_without_error(self, fbx_path):
        with open(fbx_path) as f:
            text = f.read()
        tree = parse_fbx_ascii(text)
        assert len(tree) > 0

    def test_finds_camera_models(self, fbx_path):
        with open(fbx_path) as f:
            text = f.read()
        tree = parse_fbx_ascii(text)
        # Flame always emits Default + Perspective on a static Action.
        objects_block = next(n for n in tree if n.name == "Objects")
        camera_models = [
            m for m in objects_block.find_all("Model")
            if len(m.values) >= 3 and m.values[2] == "Camera"
        ]
        names = []
        for m in camera_models:
            raw = m.values[1]
            if "::" in raw:
                names.append(raw.split("::", 1)[1])
        assert "Default" in names
        assert "Perspective" in names

    def test_to_json_produces_single_frame(self, fbx_path, tmp_path):
        out = tmp_path / "cam.json"
        # Need to select Default since both Default and Perspective exist
        # in this fixture (was a plain Flame Action, pre-Perspective-filter).
        data = fbx_to_v5_json(str(fbx_path), str(out),
                              width=1920, height=1080,
                              camera_name="Default")
        assert os.path.exists(out)
        assert data["width"] == 1920
        assert data["height"] == 1080
        assert len(data["frames"]) == 1
        f0 = data["frames"][0]
        # Original Flame cam: position (0, 0, 4747.64).
        # FBX stores with pixel_to_units=0.1 scale: (0, 0, 474.76).
        assert f0["position"][0] == pytest.approx(0.0, abs=1e-6)
        assert f0["position"][1] == pytest.approx(0.0, abs=1e-6)
        assert f0["position"][2] == pytest.approx(474.764, abs=1e-2)
        # Rotation identity.
        assert f0["rotation_flame_euler"] == pytest.approx([0, 0, 0], abs=1e-6)
        # FOV 40 -> focal with 16mm Super-16 film back should be ~22mm.
        assert f0["focal_mm"] == pytest.approx(22.0, abs=1.0)


class TestBakedFixture:
    """Baked export (``bake_animation=True``). For a static source
    camera, Flame's baker still emits a two-keyframe endpoint curve —
    so we expect two frames in the JSON, both at the same values."""

    @pytest.fixture
    def fbx_path(self):
        p = os.path.join(FIXTURE_DIR, "forge_fbx_baked.fbx")
        if not os.path.exists(p):
            pytest.skip(f"missing fixture: {p}")
        return p

    def test_to_json_produces_two_frames(self, fbx_path, tmp_path):
        out = tmp_path / "cam.json"
        # This baked FBX came from a selection-filtered export, so it
        # contains only Default, not Perspective. No name filter needed.
        data = fbx_to_v5_json(str(fbx_path), str(out),
                              width=1920, height=1080)
        frames = data["frames"]
        # Two endpoint keyframes.
        assert len(frames) == 2
        # Both should carry identical static values.
        f0, f1 = frames
        assert f0["position"] == pytest.approx(f1["position"], abs=1e-6)
        assert f0["rotation_flame_euler"] == pytest.approx(
            f1["rotation_flame_euler"], abs=1e-6)
        assert f0["focal_mm"] == pytest.approx(f1["focal_mm"], abs=1e-6)

    def test_frame_back_to_zero_is_zero(self, fbx_path, tmp_path):
        """One of Flame's endpoint KTimes is 0 (start of range); confirm
        that lands on frame 0 after our KTime -> frame conversion."""
        out = tmp_path / "cam.json"
        data = fbx_to_v5_json(str(fbx_path), str(out),
                              width=1920, height=1080)
        frames = data["frames"]
        # Earliest KTime in the FBX is 0 -> frame 0.
        assert frames[0]["frame"] == 0


# =============================================================================
# Group 5: Public-API error cases
# =============================================================================


class TestPublicAPI:
    """Guard rails on the top-level entry point."""

    def test_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            fbx_to_v5_json(str(tmp_path / "nope.fbx"),
                           str(tmp_path / "out.json"))

    def test_no_camera_filter_ambiguous(self, tmp_path):
        """With both Default and Perspective present and no
        ``camera_name`` filter, extraction should refuse to pick."""
        probe = os.path.join(FIXTURE_DIR, "forge_fbx_probe.fbx")
        if not os.path.exists(probe):
            pytest.skip("missing fixture")
        with pytest.raises(ValueError, match="multiple cameras"):
            fbx_to_v5_json(probe, str(tmp_path / "out.json"))

    def test_no_camera_filter_misses(self, tmp_path):
        probe = os.path.join(FIXTURE_DIR, "forge_fbx_probe.fbx")
        if not os.path.exists(probe):
            pytest.skip("missing fixture")
        with pytest.raises(ValueError, match="no cameras"):
            fbx_to_v5_json(probe, str(tmp_path / "out.json"),
                           camera_name="DoesNotExist")

    def test_writes_json_readable(self, tmp_path):
        probe = os.path.join(FIXTURE_DIR, "forge_fbx_probe.fbx")
        if not os.path.exists(probe):
            pytest.skip("missing fixture")
        out = tmp_path / "cam.json"
        fbx_to_v5_json(str(probe), str(out),
                       width=1920, height=1080,
                       camera_name="Default")
        with open(out) as f:
            data = json.load(f)
        # v5 contract schema keys present.
        assert set(data.keys()) >= {"width", "height", "film_back_mm", "frames"}
        assert all(set(f.keys()) >= {"frame", "position",
                                     "rotation_flame_euler", "focal_mm"}
                   for f in data["frames"])


# =============================================================================
# Group 6: Serializer (FBXNode tree -> ASCII text)
# =============================================================================


class TestEmitter:
    """emit_fbx_ascii should produce text that round-trips cleanly
    through parse_fbx_ascii. Byte-identity with Flame's emission isn't
    required, but structural equivalence is."""

    def test_round_trip_preserves_tree(self):
        text = """
        GlobalSettings: {
            Version: 1000
            Properties70: {
                P: "UpAxis", "int", "Integer", "",1
                P: "UnitScaleFactor", "double", "Number", "",1
            }
        }
        """
        tree = parse_fbx_ascii(text)
        emitted = emit_fbx_ascii(tree)
        retree = parse_fbx_ascii(emitted)
        # Structural equivalence: same names, same values, recursively.
        _assert_tree_equiv(tree, retree)

    def test_round_trip_array_node(self):
        text = "KeyTime: *3 {\n  a: 10, 20, 30\n}"
        tree = parse_fbx_ascii(text)
        retree = parse_fbx_ascii(emit_fbx_ascii(tree))
        _assert_tree_equiv(tree, retree)

    def test_round_trip_fixture(self):
        p = os.path.join(FIXTURE_DIR, "forge_fbx_baked.fbx")
        if not os.path.exists(p):
            pytest.skip("missing fixture")
        with open(p) as f:
            tree = parse_fbx_ascii(f.read())
        emitted = emit_fbx_ascii(tree)
        retree = parse_fbx_ascii(emitted)
        _assert_tree_equiv(tree, retree)


def _assert_tree_equiv(a, b):
    """Compare two FBXNode trees ignoring ordering of Properties70 P
    lines (Flame's output order is arbitrary for those)."""
    if isinstance(a, list) and isinstance(b, list):
        assert len(a) == len(b), f"list length mismatch: {len(a)} vs {len(b)}"
        for x, y in zip(a, b):
            _assert_tree_equiv(x, y)
        return
    assert a.name == b.name, f"{a.name!r} != {b.name!r}"
    assert a.values == b.values, f"{a.name}: values differ {a.values} vs {b.values}"
    assert a.array_len == b.array_len, f"{a.name}: array_len differ"
    _assert_tree_equiv(a.children, b.children)


# =============================================================================
# Group 7: Writer — v5 JSON -> FBX
# =============================================================================


class TestWriter:
    """Write a synthetic v5 JSON to FBX, then read it back and check
    that the numbers we emitted survive the round-trip. This exercises
    every piece of the writer: tree mutation, AnimCurve rebuild,
    Connections preservation, emission, and re-parsing."""

    def _simple_payload(self, frames_count=3):
        """Build a v5 payload with N linearly-increasing keyframes."""
        frames = []
        for i in range(frames_count):
            frames.append({
                "frame": i,
                "position": [100.0 * i, 50.0 * i, 4000.0 + 10.0 * i],
                "rotation_flame_euler": [float(i), float(i * 2), float(i * 3)],
                "focal_mm": 35.0 + i,
            })
        return {
            "width": 1920,
            "height": 1080,
            "film_back_mm": 36.0,
            "frames": frames,
        }

    def test_round_trip_preserves_position(self, tmp_path):
        """Write → read → compare. Position should round-trip exactly
        (pos_scale=0.1 on write cancels with the reader's FBX-stored
        value, which we then read back through fbx_to_v5_json with
        pixel_to_units=0.1 already baked in from the writer).

        Note: the reader emits position in FBX units (not Flame pixels),
        so the read-back position is 0.1 * our input. The caller on the
        real pipeline undoes this via Flame's ``unit_to_pixels=10`` on
        ``import_fbx``."""
        payload = self._simple_payload(frames_count=3)

        json_in = tmp_path / "in.json"
        with open(json_in, "w") as f:
            json.dump(payload, f)

        fbx_out = tmp_path / "cam.fbx"
        v5_json_to_fbx(str(json_in), str(fbx_out), camera_name="Cam")

        # Read back.
        json_back = tmp_path / "back.json"
        data = fbx_to_v5_json(str(fbx_out), str(json_back),
                              width=1920, height=1080,
                              camera_name="Cam", film_back_mm=36.0)

        assert len(data["frames"]) == 3
        # Position comes back in FBX units (scaled by 0.1).
        for i, out_frame in enumerate(data["frames"]):
            expected_in = payload["frames"][i]
            for axis in range(3):
                assert out_frame["position"][axis] == pytest.approx(
                    expected_in["position"][axis] * 0.1, abs=1e-3)

    def test_round_trip_preserves_rotation(self, tmp_path):
        payload = self._simple_payload(frames_count=3)
        json_in = tmp_path / "in.json"
        with open(json_in, "w") as f:
            json.dump(payload, f)
        fbx_out = tmp_path / "cam.fbx"
        v5_json_to_fbx(str(json_in), str(fbx_out), camera_name="Cam")
        data = fbx_to_v5_json(str(fbx_out), str(tmp_path / "back.json"),
                              width=1920, height=1080,
                              camera_name="Cam", film_back_mm=36.0)
        for i, out_frame in enumerate(data["frames"]):
            assert out_frame["rotation_flame_euler"] == pytest.approx(
                payload["frames"][i]["rotation_flame_euler"], abs=1e-5)

    def test_round_trip_preserves_focal(self, tmp_path):
        payload = self._simple_payload(frames_count=3)
        json_in = tmp_path / "in.json"
        with open(json_in, "w") as f:
            json.dump(payload, f)
        fbx_out = tmp_path / "cam.fbx"
        v5_json_to_fbx(str(json_in), str(fbx_out), camera_name="Cam")
        data = fbx_to_v5_json(str(fbx_out), str(tmp_path / "back.json"),
                              width=1920, height=1080,
                              camera_name="Cam", film_back_mm=36.0)
        for i, out_frame in enumerate(data["frames"]):
            assert out_frame["focal_mm"] == pytest.approx(
                payload["frames"][i]["focal_mm"], abs=1e-3)

    def test_round_trip_preserves_frame_numbers(self, tmp_path):
        """Write frames [5, 17, 33], read back, verify the frame
        numbers survive the KTime conversion round-trip."""
        payload = {
            "width": 1920,
            "height": 1080,
            "film_back_mm": 36.0,
            "frames": [
                {"frame": 5,  "position": [0, 0, 4000],
                 "rotation_flame_euler": [0, 0, 0], "focal_mm": 35.0},
                {"frame": 17, "position": [10, 20, 4100],
                 "rotation_flame_euler": [1, 2, 3], "focal_mm": 36.0},
                {"frame": 33, "position": [30, 40, 4200],
                 "rotation_flame_euler": [4, 5, 6], "focal_mm": 37.0},
            ],
        }
        json_in = tmp_path / "in.json"
        with open(json_in, "w") as f:
            json.dump(payload, f)
        fbx_out = tmp_path / "cam.fbx"
        v5_json_to_fbx(str(json_in), str(fbx_out), camera_name="Cam")
        data = fbx_to_v5_json(str(fbx_out), str(tmp_path / "back.json"),
                              width=1920, height=1080,
                              camera_name="Cam", film_back_mm=36.0)
        got = [f["frame"] for f in data["frames"]]
        assert got == [5, 17, 33]

    def test_writer_renames_camera(self, tmp_path):
        """The camera_name arg should land on Model:: and NodeAttribute::
        so downstream reads with a camera_name filter find it."""
        payload = self._simple_payload(frames_count=1)
        json_in = tmp_path / "in.json"
        with open(json_in, "w") as f:
            json.dump(payload, f)
        fbx_out = tmp_path / "cam.fbx"
        v5_json_to_fbx(str(json_in), str(fbx_out), camera_name="TurboCam")

        # Read should succeed with the explicit name and fail with
        # a wrong one.
        data = fbx_to_v5_json(str(fbx_out), str(tmp_path / "back.json"),
                              width=1920, height=1080,
                              camera_name="TurboCam", film_back_mm=36.0)
        assert len(data["frames"]) >= 1

        with pytest.raises(ValueError, match="no cameras"):
            fbx_to_v5_json(str(fbx_out), str(tmp_path / "x.json"),
                           width=1920, height=1080,
                           camera_name="DoesNotExist", film_back_mm=36.0)

    def test_writer_rejects_empty_frames(self, tmp_path):
        payload = {"width": 1920, "height": 1080, "film_back_mm": 36.0,
                   "frames": []}
        json_in = tmp_path / "in.json"
        with open(json_in, "w") as f:
            json.dump(payload, f)
        with pytest.raises(ValueError, match="no frames"):
            v5_json_to_fbx(str(json_in), str(tmp_path / "out.fbx"))

    def test_writer_creates_parent_dirs(self, tmp_path):
        payload = self._simple_payload(frames_count=1)
        json_in = tmp_path / "in.json"
        with open(json_in, "w") as f:
            json.dump(payload, f)
        out = tmp_path / "nested" / "dirs" / "cam.fbx"
        assert not out.parent.exists()
        v5_json_to_fbx(str(json_in), str(out), camera_name="Cam")
        assert out.exists()

    def test_writer_emits_valid_fbx_with_header(self, tmp_path):
        """Our output should start with the FBX project-file comment
        Flame recognizes, so Flame's import_fbx treats it as a valid
        FBX file."""
        payload = self._simple_payload(frames_count=1)
        json_in = tmp_path / "in.json"
        with open(json_in, "w") as f:
            json.dump(payload, f)
        out = tmp_path / "cam.fbx"
        v5_json_to_fbx(str(json_in), str(out), camera_name="Cam")
        with open(out) as f:
            text = f.read()
        assert text.startswith("; FBX 7.7.0")
        # Has the required top-level blocks.
        for required in ("FBXHeaderExtension", "GlobalSettings", "Objects",
                         "Connections", "Takes"):
            assert required + ":" in text, f"missing {required} block"


# =============================================================================
# Group 7b: v5_json_str_to_fbx — in-memory string sibling (Plan 02-02, D-01)
# =============================================================================


class TestV5JsonStrToFbx:
    """D-01: in-memory JSON string variant must produce byte-identical
    FBX output to the file-path variant for the same payload, so the
    Blender "Send to Flame" addon can feed the forge-bridge template a
    string directly without an intermediate file on the Flame side.
    """

    def _simple_payload(self, frames_count=2):
        """Mirror TestWriter._simple_payload — same shape, fewer frames
        so the string-variant tests run cheap."""
        frames = []
        for i in range(frames_count):
            frames.append({
                "frame": i,
                "position": [100.0 * i, 50.0 * i, 4000.0 + 10.0 * i],
                "rotation_flame_euler": [float(i), float(i * 2), float(i * 3)],
                "focal_mm": 35.0 + i,
            })
        return {
            "width": 1920,
            "height": 1080,
            "film_back_mm": 36.0,
            "frames": frames,
        }

    def test_v5_json_str_to_fbx_equivalent_to_file_variant(self, tmp_path):
        """Given the same payload: writing it to a tempfile and calling
        v5_json_to_fbx must produce byte-identical output to serializing
        it and calling v5_json_str_to_fbx. This is the contract the
        shared _payload_to_fbx helper guarantees."""
        payload = self._simple_payload(frames_count=3)
        json_str = json.dumps(payload)

        # File variant.
        json_path = tmp_path / "in.json"
        json_path.write_text(json_str)
        fbx_from_file = tmp_path / "from_file.fbx"
        v5_json_to_fbx(str(json_path), str(fbx_from_file),
                       camera_name="Cam")

        # String variant.
        fbx_from_str = tmp_path / "from_str.fbx"
        v5_json_str_to_fbx(json_str, str(fbx_from_str),
                           camera_name="Cam")

        assert fbx_from_file.read_text() == fbx_from_str.read_text()

    def test_v5_json_str_to_fbx_signature_keyword_only(self, tmp_path):
        """camera_name / frame_rate / pixel_to_units must be keyword-only
        — guards against drift from the D-01 locked signature."""
        payload = self._simple_payload(frames_count=1)
        json_str = json.dumps(payload)
        out = tmp_path / "cam.fbx"

        # Positional call of the keyword-only args must raise.
        with pytest.raises(TypeError):
            v5_json_str_to_fbx(json_str, str(out), "Cam")  # type: ignore

    def test_v5_json_str_to_fbx_parses_json_str_input(self, tmp_path):
        """Invalid JSON as the first arg must raise json.JSONDecodeError
        — confirms the sibling uses json.loads, not json.load."""
        out = tmp_path / "cam.fbx"
        with pytest.raises(json.JSONDecodeError):
            v5_json_str_to_fbx("{ this is not json }", str(out),
                               camera_name="Cam")

    def test_v5_json_to_fbx_file_variant_unchanged(self, tmp_path):
        """Regression guard: the existing file-path variant must still
        accept a path string as its first positional arg and return the
        absolute output path. PATTERNS §1.3 "Do NOT touch v5_json_to_fbx's
        signature or docstring"."""
        payload = self._simple_payload(frames_count=1)
        json_in = tmp_path / "in.json"
        json_in.write_text(json.dumps(payload))
        out = tmp_path / "out.fbx"

        returned = v5_json_to_fbx(str(json_in), str(out), camera_name="Cam")
        assert returned == os.path.abspath(str(out))
        assert out.exists()


# =============================================================================
# Group 5: fbx_to_v5_json — custom_properties passthrough (Plan 01-02)
# =============================================================================


class TestFbxToV5JsonCustomProperties:
    """Tests for the optional ``custom_properties`` kwarg added to
    ``fbx_to_v5_json`` in Plan 01-02 (EXP-04 schema extension).

    Uses ``forge_fbx_baked.fbx`` — a live Flame 2026.2.1 export with
    ``bake_animation=True`` (two-keyframe endpoints on each curve).

    Tests cover:
    - Test A: custom_properties dict lands in both the returned dict and
      the on-disk JSON.
    - Test B: omitting the kwarg produces no ``custom_properties`` key
      (backward-compatible with pre-v6.3 callers).
    - Test C: passing ``custom_properties={}`` also omits the key (empty
      dicts are indistinguishable from "nothing to stamp").
    - Test D: caller mutating the input dict after the call does NOT
      affect the on-disk JSON (shallow-copy defense).
    """

    _FIXTURE = os.path.join(FIXTURE_DIR, "forge_fbx_baked.fbx")
    _COMMON_KWARGS = dict(
        width=1920,
        height=1080,
        film_back_mm=36.0,
        camera_name="Default",
    )

    def test_a_custom_properties_in_return_and_disk(self, tmp_path):
        """Test A: custom_properties appear in both returned dict and JSON."""
        props = {
            "forge_bake_action_name": "Action_01",
            "forge_bake_camera_name": "Cam_01",
        }
        json_path = tmp_path / "out.json"
        result = fbx_to_v5_json(
            self._FIXTURE,
            str(json_path),
            **self._COMMON_KWARGS,
            custom_properties=props,
        )
        # Check returned dict.
        assert "custom_properties" in result
        assert result["custom_properties"] == {
            "forge_bake_action_name": "Action_01",
            "forge_bake_camera_name": "Cam_01",
        }
        # Check on-disk JSON (full serialization path).
        with open(json_path) as f:
            on_disk = json.load(f)
        assert "custom_properties" in on_disk
        assert on_disk["custom_properties"] == {
            "forge_bake_action_name": "Action_01",
            "forge_bake_camera_name": "Cam_01",
        }

    def test_b_no_kwarg_no_key(self, tmp_path):
        """Test B: omitting custom_properties produces no key in JSON."""
        json_path = tmp_path / "out.json"
        result = fbx_to_v5_json(
            self._FIXTURE,
            str(json_path),
            **self._COMMON_KWARGS,
        )
        assert "custom_properties" not in result
        with open(json_path) as f:
            on_disk = json.load(f)
        assert "custom_properties" not in on_disk

    def test_c_empty_dict_no_key(self, tmp_path):
        """Test C: custom_properties={} also omits the key (empty == absent)."""
        json_path = tmp_path / "out.json"
        result = fbx_to_v5_json(
            self._FIXTURE,
            str(json_path),
            **self._COMMON_KWARGS,
            custom_properties={},
        )
        assert "custom_properties" not in result
        with open(json_path) as f:
            on_disk = json.load(f)
        assert "custom_properties" not in on_disk

    def test_d_shallow_copy_defense(self, tmp_path):
        """Test D: mutating the input dict after call does not affect on-disk JSON."""
        props = {"forge_bake_action_name": "Action_01"}
        json_path = tmp_path / "out.json"
        fbx_to_v5_json(
            self._FIXTURE,
            str(json_path),
            **self._COMMON_KWARGS,
            custom_properties=props,
        )
        # Mutate after the call.
        props["forge_bake_action_name"] = "MUTATED"
        props["extra_key"] = "should_not_appear"
        # On-disk JSON must still have the original values.
        with open(json_path) as f:
            on_disk = json.load(f)
        assert on_disk["custom_properties"]["forge_bake_action_name"] == "Action_01"
        assert "extra_key" not in on_disk["custom_properties"]


# =============================================================================
# Group 6: fbx_to_v5_json — frame_offset preserves Flame batch start_frame
# =============================================================================


class TestFbxToV5JsonFrameOffset:
    """Tests for the optional ``frame_offset`` kwarg added to
    ``fbx_to_v5_json`` (and inner ``_merge_curves``) in quick task
    260420-uzv.

    Background: ``action.export_fbx(bake_animation=True)`` zero-bases the
    FBX KTime stream regardless of the Flame batch's ``start_frame``, so
    a Flame batch whose frame range is 1001..1100 emits FBX KTimes that
    decode to frames 0..99. The Flame-side hook reads ``flame.batch.start_frame``
    and threads it through as ``frame_offset`` so the v5 JSON — and the
    eventual Blender scene — keep the source plate's frame numbers.

    Uses ``forge_fbx_baked.fbx`` — a live Flame 2026.2.1 export with
    ``bake_animation=True`` (two-keyframe endpoints on each curve), so
    the keyed branch of ``_merge_curves`` is exercised.

    Tests cover:
    - Test A: a non-zero offset shifts every emitted ``frame`` value.
    - Test B: the kwarg defaults to 0 (regression guard — existing
      behavior is unchanged when callers don't pass it).
    - Test C: the offset survives the on-disk serialization path.
    - Test D: negative offsets are honored (proves "plain integer add",
      no clamping that could regress in future "helpful" patches).
    """

    _FIXTURE = os.path.join(FIXTURE_DIR, "forge_fbx_baked.fbx")
    _COMMON_KWARGS = dict(
        width=1920,
        height=1080,
        film_back_mm=36.0,
        camera_name="Default",
    )

    def test_a_offset_shifts_frames(self, tmp_path):
        """Test A: frame_offset=1001 shifts every frame to >= 1001 and
        the first frame lands exactly on 1001."""
        json_path = tmp_path / "out.json"
        result = fbx_to_v5_json(
            self._FIXTURE,
            str(json_path),
            **self._COMMON_KWARGS,
            frame_offset=1001,
        )
        frames = result["frames"]
        assert len(frames) > 0, "fixture should produce at least one frame"
        assert frames[0]["frame"] == 1001
        # Defends against the +offset being applied to only some keys.
        for entry in frames:
            assert entry["frame"] >= 1001, (
                f"all frames must be shifted; got {entry['frame']}"
            )

    def test_b_default_offset_is_zero(self, tmp_path):
        """Test B: omitting frame_offset behaves identically to
        frame_offset=0 — proves the kwarg defaults to 0 and that 0 is a
        no-op (regression guard for pre-fix behavior)."""
        json_no_kwarg = tmp_path / "no_kwarg.json"
        result_no_kwarg = fbx_to_v5_json(
            self._FIXTURE,
            str(json_no_kwarg),
            **self._COMMON_KWARGS,
        )
        json_zero = tmp_path / "zero.json"
        result_zero = fbx_to_v5_json(
            self._FIXTURE,
            str(json_zero),
            **self._COMMON_KWARGS,
            frame_offset=0,
        )
        frames_no_kwarg = [e["frame"] for e in result_no_kwarg["frames"]]
        frames_zero = [e["frame"] for e in result_zero["frames"]]
        assert frames_no_kwarg == frames_zero

    def test_c_on_disk_parity(self, tmp_path):
        """Test C: the offset survives the full serialization path —
        the on-disk JSON shows the shifted frame numbers, not just the
        in-memory return."""
        json_path = tmp_path / "out.json"
        fbx_to_v5_json(
            self._FIXTURE,
            str(json_path),
            **self._COMMON_KWARGS,
            frame_offset=1001,
        )
        with open(json_path) as f:
            on_disk = json.load(f)
        assert on_disk["frames"][0]["frame"] == 1001
        for entry in on_disk["frames"]:
            assert entry["frame"] >= 1001

    def test_d_large_negative_offset(self, tmp_path):
        """Test D: negative offsets are honored — frame_offset=-50
        shifts the first frame by -50 from the no-offset baseline.
        Negative offsets aren't a real production case but proving
        "plain integer add, no clamping" prevents future regressions
        where someone "helpfully" adds ``max(0, ...)``."""
        json_baseline = tmp_path / "baseline.json"
        result_baseline = fbx_to_v5_json(
            self._FIXTURE,
            str(json_baseline),
            **self._COMMON_KWARGS,
        )
        baseline_first = result_baseline["frames"][0]["frame"]

        json_neg = tmp_path / "neg.json"
        result_neg = fbx_to_v5_json(
            self._FIXTURE,
            str(json_neg),
            **self._COMMON_KWARGS,
            frame_offset=-50,
        )
        assert result_neg["frames"][0]["frame"] == baseline_first - 50


# =============================================================================
# Group 7: fbx_to_v5_json — frame_end clips trailing bake_animation key
# =============================================================================


class TestFbxToV5JsonFrameEnd:
    """Tests for the optional ``frame_end`` kwarg added to
    ``fbx_to_v5_json`` (and inner ``_merge_curves``) in quick task
    260421-bhg.

    Background: UAT on the 260420-uzv deploy (which restored real plate
    frame numbers in the FBX -> v5 JSON path via ``frame_offset``)
    surfaced a second issue at the TAIL of the range. Flame's
    ``action.export_fbx(bake_animation=True)`` bakes ``end - start + 1``
    KTimes (0..100 for a 1001..1100 inclusive batch), and after the
    +1001 offset that becomes 1001..1101 — one frame beyond the user's
    batch end. User's verbatim report: *"I seem to still have an errant
    keyframe at 1101"*.

    The fix is a TAIL clip: thread ``frame_end`` (INCLUSIVE upper bound,
    applied AFTER ``frame_offset``) through the same wiring 260420-uzv
    added for ``frame_offset``. Default is ``None`` (no clipping,
    preserves pre-fix behavior).

    Uses ``forge_fbx_baked.fbx`` — the live Flame 2026.2.1 export with
    ``bake_animation=True`` (exercises the keyed branch of
    ``_merge_curves``).

    Tests cover:
    - Test A: exact UAT scenario — offset + end clip drops one trailing
      frame and preserves the inclusive boundary frame.
    - Test B: ``frame_end=None`` (default) is a no-op vs omitting the
      kwarg entirely (regression guard — preserves the 260420-uzv
      post-state).
    - Test C: ``frame_end`` below the minimum offset-adjusted frame
      yields an empty list (edge case — no crash, no None).
    - Test D: ``frame_end`` exactly equal to the minimum offset-adjusted
      frame yields exactly one frame (locks in the INCLUSIVE semantic —
      boundary frame is KEPT, not dropped).
    """

    _FIXTURE = os.path.join(FIXTURE_DIR, "forge_fbx_baked.fbx")
    _COMMON_KWARGS = dict(
        width=1920,
        height=1080,
        film_back_mm=36.0,
        camera_name="Default",
    )

    def test_a_offset_plus_end_clip_drops_trailing_frame(self, tmp_path):
        """Test A — the exact UAT scenario:

        1. Read the no-offset, no-clip baseline to discover the
           fixture's natural last frame at runtime (so this test stays
           correct if the fixture is regenerated with a different key
           density).
        2. Call again with ``frame_offset=1001`` and
           ``frame_end=1001 + baseline_last - 1`` — i.e., clip one
           frame shy of the offset-shifted natural end.
        3. Assert the max emitted frame equals the boundary (proves
           the INCLUSIVE upper bound — the boundary frame is KEPT).
        4. Assert the result is exactly one shorter than the no-clip
           baseline (proves exactly one trailing frame was dropped —
           the UAT symptom of the errant 1101 keyframe).
        5. Assert every emitted frame satisfies ``<= boundary``.
        """
        # Step 1: no-offset, no-clip baseline to discover fixture's range.
        json_baseline = tmp_path / "baseline.json"
        result_baseline = fbx_to_v5_json(
            self._FIXTURE,
            str(json_baseline),
            **self._COMMON_KWARGS,
        )
        baseline_frames = result_baseline["frames"]
        assert len(baseline_frames) >= 2, (
            "fixture must have at least two keyed frames for this test "
            "to meaningfully drop a trailing one"
        )
        baseline_last = baseline_frames[-1]["frame"]
        baseline_count = len(baseline_frames)

        # Step 2: offset + clip one-shy of the shifted end.
        boundary = 1001 + baseline_last - 1
        json_clipped = tmp_path / "clipped.json"
        result_clipped = fbx_to_v5_json(
            self._FIXTURE,
            str(json_clipped),
            **self._COMMON_KWARGS,
            frame_offset=1001,
            frame_end=boundary,
        )
        clipped_frames = result_clipped["frames"]
        clipped_frame_nums = [e["frame"] for e in clipped_frames]

        # Step 3: inclusive upper bound — boundary frame is kept.
        assert max(clipped_frame_nums) == boundary, (
            f"max emitted frame should be the INCLUSIVE boundary "
            f"{boundary}; got {max(clipped_frame_nums)}"
        )

        # Step 4: exactly one trailing frame dropped.
        assert len(clipped_frames) == baseline_count - 1, (
            f"expected exactly one trailing frame dropped "
            f"(baseline={baseline_count} -> clipped={baseline_count - 1}); "
            f"got {len(clipped_frames)}"
        )

        # Step 5: no frame exceeds the boundary.
        for entry in clipped_frames:
            assert entry["frame"] <= boundary, (
                f"frame {entry['frame']} exceeds boundary {boundary}"
            )

    def test_b_none_default_is_no_op(self, tmp_path):
        """Test B — ``frame_end=None`` (default) is identical to omitting
        the kwarg, and both preserve pre-260421-bhg behavior (regression
        guard on the 260420-uzv post-state)."""
        json_no_kwarg = tmp_path / "no_kwarg.json"
        result_no_kwarg = fbx_to_v5_json(
            self._FIXTURE,
            str(json_no_kwarg),
            **self._COMMON_KWARGS,
        )
        json_explicit_none = tmp_path / "explicit_none.json"
        result_explicit_none = fbx_to_v5_json(
            self._FIXTURE,
            str(json_explicit_none),
            **self._COMMON_KWARGS,
            frame_end=None,
        )
        frames_no_kwarg = [e["frame"] for e in result_no_kwarg["frames"]]
        frames_explicit_none = [
            e["frame"] for e in result_explicit_none["frames"]
        ]
        assert frames_no_kwarg == frames_explicit_none, (
            "frame_end=None must be a pure no-op; got "
            f"no_kwarg={frames_no_kwarg} vs explicit_none={frames_explicit_none}"
        )

    def test_c_frame_end_below_min_yields_empty(self, tmp_path):
        """Test C — ``frame_offset=1001, frame_end=0``: every offset-
        adjusted frame is >= 1001 and 1001 > 0, so ALL frames are
        dropped. Result must be an empty list — NOT a crash, NOT None.
        Locks in "empty result is legitimate" so a future "helpful"
        guard doesn't raise on it."""
        json_path = tmp_path / "empty.json"
        result = fbx_to_v5_json(
            self._FIXTURE,
            str(json_path),
            **self._COMMON_KWARGS,
            frame_offset=1001,
            frame_end=0,
        )
        assert result["frames"] == [], (
            f"expected empty frames list when frame_end below min; "
            f"got {result['frames']!r}"
        )

    def test_d_inclusive_boundary_keeps_first_frame(self, tmp_path):
        """Test D — inclusive boundary: compute the baseline's first
        frame, call with ``frame_offset=1001`` and
        ``frame_end=1001 + baseline_first``, and assert exactly the
        first frame survives. Locks in the INCLUSIVE semantic — if
        someone "helpfully" changes ``>`` to ``>=`` in the drop
        condition, this test goes red."""
        json_baseline = tmp_path / "baseline.json"
        result_baseline = fbx_to_v5_json(
            self._FIXTURE,
            str(json_baseline),
            **self._COMMON_KWARGS,
        )
        baseline_first = result_baseline["frames"][0]["frame"]
        boundary = 1001 + baseline_first

        json_clipped = tmp_path / "clipped.json"
        result = fbx_to_v5_json(
            self._FIXTURE,
            str(json_clipped),
            **self._COMMON_KWARGS,
            frame_offset=1001,
            frame_end=boundary,
        )
        frames = result["frames"]
        assert len(frames) == 1, (
            f"expected exactly one frame at the inclusive boundary; "
            f"got {len(frames)} frames: {[e['frame'] for e in frames]}"
        )
        assert frames[0]["frame"] == boundary, (
            f"surviving frame should be the boundary {boundary}; "
            f"got {frames[0]['frame']}"
        )


class TestFbxToV5JsonFrameStart:
    """Tests for the optional ``frame_start`` kwarg added to
    ``fbx_to_v5_json`` (and inner ``_merge_curves``) in quick task
    260421-c1w.

    Background: this is the THIRD fix in the chain:
      - 260420-uzv: added ``frame_offset`` so the FBX round-trip surfaces
        real plate frame numbers in Blender (not zero-based KTime).
      - 260421-bhg: added ``frame_end`` (INCLUSIVE upper bound) to drop
        the single trailing keyframe that
        ``action.export_fbx(bake_animation=True)`` bakes past the user's
        batch range.
      - 260421-c1w (this test class): adds ``frame_start`` (INCLUSIVE
        lower bound) to drop the implicit PRE-ROLL keyframe that Flame
        emits at FBX KTime 0, AND corrects the ``frame_offset`` to be
        ``start_frame - 1`` so the real per-frame samples (KTimes 1..N)
        land on their correct user-facing plate frames.

    UAT on the 260421-bhg deploy (which correctly dropped the errant
    1101 trailing key) surfaced a deeper bake-shape issue that was
    previously hidden BEHIND the trailing-frame bug. The actual Flame
    bake shape is:
      - KTime 0 = implicit PRE-ROLL (initial state — held before the
        first "real" key)
      - KTime k (k>=1) = source frame ``start_frame + k - 1``
    So for a 1001..1100 batch, the fix is TWO coordinated changes:
      - ``frame_offset = 1000`` (so KTime 1 -> 1001, not 1002)
      - ``frame_start = 1001`` (so KTime 0 -> 1000 -> DROPPED)

    ``frame_start`` is INCLUSIVE (STRICT ``<`` drop — boundary frame is
    KEPT), symmetric with ``frame_end``'s INCLUSIVE upper bound.

    Uses ``forge_fbx_baked.fbx`` — the live Flame 2026.2.1 export with
    ``bake_animation=True`` (exercises the keyed branch of
    ``_merge_curves``). Fixture has KTime 0 pre-roll plus at least one
    real-sample KTime.

    Tests cover:
    - Test A: UAT-shaped call (offset=1000 + start=1001 + end=<derived>)
      drops the pre-roll AND the Xpos at the first surviving frame
      matches the SECOND baseline frame's Xpos (regression guard for
      the +1 shift — if ``frame_offset = start_frame`` returns instead
      of ``start_frame - 1``, this goes red).
    - Test B: ``frame_start=None`` (default) is a no-op vs omitting the
      kwarg entirely (regression guard — preserves the 260421-bhg
      post-state).
    - Test C: ``frame_start`` equal to the minimum offset-adjusted
      frame keeps ALL frames (locks in the INCLUSIVE semantic — STRICT
      ``<`` drop, boundary frame kept).
    - Test D: ``frame_start`` above all offset-adjusted frames yields
      an empty list (edge case — no crash, no None).
    """

    _FIXTURE = os.path.join(FIXTURE_DIR, "forge_fbx_baked.fbx")
    _COMMON_KWARGS = dict(
        width=1920,
        height=1080,
        film_back_mm=36.0,
        camera_name="Default",
    )

    def test_a_uat_preroll_drop_and_shift_correction(self, tmp_path):
        """Test A — the exact UAT scenario:

        1. Read the no-offset, no-clip baseline to discover the
           fixture's natural range at runtime (so this test stays
           correct if the fixture is regenerated).
        2. Capture the SECOND baseline frame's ``position[0]`` — this
           is the first REAL sample's Xpos (KTime 1), which under the
           fix must land on user-facing frame 1001.
        3. Call with the full UAT-shaped kwargs:
           ``frame_offset=1000, frame_start=1001,
             frame_end=1001 + baseline_last - 1``.
        4. Assert:
           - first surviving frame is 1001 (pre-roll was dropped);
           - Xpos at frame 1001 equals the KTime 1 baseline Xpos
             (regression guard for the +1 shift);
           - exactly one frame (the pre-roll) was dropped;
           - every emitted frame is in the closed range
             ``[frame_start, frame_end]``.
        """
        # Step 1: no-offset, no-clip baseline.
        json_baseline = tmp_path / "baseline.json"
        result_baseline = fbx_to_v5_json(
            self._FIXTURE,
            str(json_baseline),
            **self._COMMON_KWARGS,
        )
        baseline_frames = result_baseline["frames"]
        assert len(baseline_frames) >= 2, (
            "fixture must have a pre-roll AND at least one real sample "
            "for this test to meaningfully exercise the pre-roll drop"
        )
        baseline_count = len(baseline_frames)
        baseline_last = baseline_frames[-1]["frame"]
        # Step 2: capture the KTime 1 Xpos (first REAL sample).
        ktime_1_xpos = baseline_frames[1]["position"][0]

        # Step 3: UAT-shaped call.
        boundary_end = 1001 + baseline_last - 1
        json_clipped = tmp_path / "clipped.json"
        result = fbx_to_v5_json(
            self._FIXTURE,
            str(json_clipped),
            **self._COMMON_KWARGS,
            frame_offset=1000,
            frame_start=1001,
            frame_end=boundary_end,
        )
        frames = result["frames"]

        # Step 4a: first surviving frame is the inclusive boundary.
        assert frames[0]["frame"] == 1001, (
            f"first surviving frame should be 1001 (the pre-roll at "
            f"offset-adjusted 1000 should be dropped); got "
            f"{frames[0]['frame']}"
        )
        # Step 4b: Xpos regression guard for the +1 shift correction.
        # Under the fix, user-facing frame 1001 shows the KTime 1 pose
        # (the first real sample). If someone reverts
        # ``frame_offset = int(float(sf)) - 1`` back to
        # ``int(float(sf))``, frame 1001 would show the KTime 0
        # pre-roll pose instead and this assertion goes red.
        assert frames[0]["position"][0] == ktime_1_xpos, (
            f"Xpos at frame 1001 should be the KTime 1 pose "
            f"({ktime_1_xpos}); got {frames[0]['position'][0]}. "
            f"Regression: +1 shift correction "
            f"(frame_offset = start_frame - 1) is broken."
        )
        # Step 4c: exactly one frame (the pre-roll) was dropped.
        assert len(frames) == baseline_count - 1, (
            f"expected exactly one frame (pre-roll) dropped "
            f"(baseline={baseline_count} -> clipped="
            f"{baseline_count - 1}); got {len(frames)}"
        )
        # Step 4d: every emitted frame in the closed range.
        for entry in frames:
            assert 1001 <= entry["frame"] <= boundary_end, (
                f"frame {entry['frame']} outside closed range "
                f"[1001, {boundary_end}]"
            )

    def test_b_none_default_is_no_op(self, tmp_path):
        """Test B — ``frame_start=None`` (default) is identical to
        omitting the kwarg, and both preserve pre-260421-c1w behavior
        (regression guard on the 260421-bhg post-state)."""
        json_no_kwarg = tmp_path / "no_kwarg.json"
        result_no_kwarg = fbx_to_v5_json(
            self._FIXTURE,
            str(json_no_kwarg),
            **self._COMMON_KWARGS,
        )
        json_explicit_none = tmp_path / "explicit_none.json"
        result_explicit_none = fbx_to_v5_json(
            self._FIXTURE,
            str(json_explicit_none),
            **self._COMMON_KWARGS,
            frame_start=None,
        )
        frames_no_kwarg = result_no_kwarg["frames"]
        frames_explicit_none = result_explicit_none["frames"]
        # Same frame numbers AND same positions — the default is a
        # pure no-op, not just "same count".
        assert [e["frame"] for e in frames_no_kwarg] == [
            e["frame"] for e in frames_explicit_none
        ], "frame_start=None must preserve frame numbers exactly"
        assert [e["position"] for e in frames_no_kwarg] == [
            e["position"] for e in frames_explicit_none
        ], "frame_start=None must preserve positions exactly"

    def test_c_inclusive_boundary_keeps_boundary_frame(self, tmp_path):
        """Test C — inclusive boundary: call with
        ``frame_offset=1001, frame_start=1001 + baseline_first``. The
        boundary equals the minimum offset-adjusted frame, so under
        STRICT ``<`` drop semantics ALL frames are kept. If someone
        changes ``<`` to ``<=``, the boundary frame gets dropped and
        this test goes red."""
        json_baseline = tmp_path / "baseline.json"
        result_baseline = fbx_to_v5_json(
            self._FIXTURE,
            str(json_baseline),
            **self._COMMON_KWARGS,
        )
        baseline_frames = result_baseline["frames"]
        baseline_first = baseline_frames[0]["frame"]
        baseline_count = len(baseline_frames)
        boundary = 1001 + baseline_first

        json_clipped = tmp_path / "clipped.json"
        result = fbx_to_v5_json(
            self._FIXTURE,
            str(json_clipped),
            **self._COMMON_KWARGS,
            frame_offset=1001,
            frame_start=boundary,
        )
        frames = result["frames"]
        # Nothing dropped — boundary is INCLUSIVE.
        assert len(frames) == baseline_count, (
            f"expected all {baseline_count} frames to survive when "
            f"frame_start equals the minimum offset-adjusted frame "
            f"(INCLUSIVE boundary); got {len(frames)}. If you see "
            f"{baseline_count - 1}, the drop condition was changed "
            f"from `<` to `<=`."
        )
        assert frames[0]["frame"] == boundary, (
            f"first surviving frame should be the boundary {boundary}; "
            f"got {frames[0]['frame']}"
        )

    def test_d_frame_start_above_all_yields_empty(self, tmp_path):
        """Test D — ``frame_offset=0, frame_start=baseline_last + 1``:
        every offset-adjusted frame is ``<= baseline_last <
        frame_start``, so ALL frames are dropped. Result must be an
        empty list — NOT a crash, NOT None. Mirrors
        ``TestFbxToV5JsonFrameEnd.test_c_frame_end_below_min_yields_empty``
        from the other direction."""
        json_baseline = tmp_path / "baseline.json"
        result_baseline = fbx_to_v5_json(
            self._FIXTURE,
            str(json_baseline),
            **self._COMMON_KWARGS,
        )
        baseline_last = result_baseline["frames"][-1]["frame"]

        json_path = tmp_path / "empty.json"
        result = fbx_to_v5_json(
            self._FIXTURE,
            str(json_path),
            **self._COMMON_KWARGS,
            frame_offset=0,
            frame_start=baseline_last + 1,
        )
        assert result["frames"] == [], (
            f"expected empty frames list when frame_start above all "
            f"offset-adjusted frames; got {result['frames']!r}"
        )


# =============================================================================
# Group 9: fbx_to_v5_json — frame_rate top-level key emit (Plan 04.1-02)
# =============================================================================


class TestFbxToV5JsonFrameRateTopLevel:
    """Tests for the top-level ``frame_rate`` key emitted by ``fbx_to_v5_json``.

    Plan 04.1-02 item 5 (D-13): the Flame hook propagates the Flame project fps
    label (e.g. "25 fps") via the v5 JSON schema as a TOP-LEVEL key — not nested
    under ``custom_properties`` — so downstream consumers (bake_camera.py) can
    read it without knowing the custom-properties dict shape.

    The ``frame_rate`` parameter already exists on ``fbx_to_v5_json`` for FBX
    KTime conversion purposes. This group tests that it is ALSO emitted as a
    top-level payload key (separate from its internal KTime conversion role).

    Tests:
    - B1: frame_rate="25 fps" lands as a TOP-LEVEL key in both the returned dict
      and the on-disk JSON (not nested under custom_properties).
    - B2: the existing default ("23.976 fps") is emitted as a top-level key when
      the caller uses the default (backward-compatible — v5 JSON has always been
      self-describing about frame rate).
    """

    _FIXTURE = os.path.join(FIXTURE_DIR, "forge_fbx_baked.fbx")
    _COMMON_KWARGS = dict(
        width=1920,
        height=1080,
        film_back_mm=36.0,
        camera_name="Default",
    )

    def test_b1_explicit_frame_rate_is_top_level_key(self, tmp_path):
        """B1: frame_rate='25 fps' lands as a top-level 'frame_rate' key,
        not nested under custom_properties."""
        json_path = tmp_path / "out.json"
        result = fbx_to_v5_json(
            self._FIXTURE,
            str(json_path),
            **self._COMMON_KWARGS,
            frame_rate="25 fps",
        )
        # Top-level key present with correct value.
        assert "frame_rate" in result, "frame_rate must be a top-level key"
        assert result["frame_rate"] == "25 fps"
        # Must NOT be nested under custom_properties.
        assert "custom_properties" not in result or \
               "frame_rate" not in result.get("custom_properties", {}), \
               "frame_rate must NOT be nested under custom_properties"
        # On-disk JSON must also have the top-level key.
        with open(json_path) as f:
            on_disk = json.load(f)
        assert "frame_rate" in on_disk
        assert on_disk["frame_rate"] == "25 fps"

    def test_b2_default_frame_rate_is_top_level_key(self, tmp_path):
        """B2: omitting frame_rate (default '23.976 fps') still emits a
        top-level key — the default is truthy so the existing emit path fires.
        This is intentional: v5 JSON is self-describing about frame rate."""
        json_path = tmp_path / "out.json"
        result = fbx_to_v5_json(
            self._FIXTURE,
            str(json_path),
            **self._COMMON_KWARGS,
            # frame_rate intentionally omitted — uses default "23.976 fps"
        )
        assert "frame_rate" in result, (
            "default frame_rate='23.976 fps' is truthy and must be emitted "
            "as a top-level key for v5 JSON self-description"
        )
        assert result["frame_rate"] == "23.976 fps"
        with open(json_path) as f:
            on_disk = json.load(f)
        assert on_disk["frame_rate"] == "23.976 fps"


# =============================================================================
# Group 11: Flame import_fbx rotation negation contract (Phase 04.1 hotfix)
# =============================================================================


class TestFlameRotationNegationContract:
    """Flame 2026.2.1's ``import_fbx`` negates all three LclRotation Euler
    components when storing ``cam.rotation`` — i.e. writing
    ``LclRotation=(lx, ly, lz)`` produces ``cam.rotation=(-lx, -ly, -lz)``
    after import. Live-verified 2026-04-22: original cam.rotation
    (27.3, -24.3, 0.7) round-tripped as (-27.3, 24.3, -0.7) in a pre-fix
    Send-to-Flame export; user confirmed rotation is correct after the
    double-negation fix landed on both the write and read paths.

    These tests pin the external FBX contract so a future refactor that
    removes both negations does not silently re-break the live Flame
    round-trip. The round-trip tests in ``TestWriter`` only catch a
    regression if *one* side is removed — if both sides are removed,
    write→read still cancels to identity even though the live Flame
    import would be wrong.
    """

    def _payload_rot(self, rotation):
        """Single-frame payload with the given rotation_flame_euler."""
        return {
            "width": 1920,
            "height": 1080,
            "film_back_mm": 16.0,
            "frames": [{
                "frame": 0,
                "position": [0.0, 0.0, 4000.0],
                "rotation_flame_euler": list(rotation),
                "focal_mm": 35.0,
            }],
        }

    def test_write_emits_negated_lcl_rotation_for_flame_import(self, tmp_path):
        """Given rotation_flame_euler=(27.3, -24.3, 0.7) (the user's
        observed failing case from Phase 04.1 verification), the emitted
        FBX's static LclRotation property must carry (-27.3, 24.3, -0.7).
        Flame's import_fbx negates during import, so the final cam.rotation
        matches the input rotation_flame_euler."""
        payload = self._payload_rot([27.3, -24.3, 0.7])
        json_in = tmp_path / "in.json"
        json_in.write_text(json.dumps(payload))
        fbx_out = tmp_path / "out.fbx"
        v5_json_to_fbx(str(json_in), str(fbx_out), camera_name="Cam")

        fbx_text = fbx_out.read_text()
        # Locate the static Lcl Rotation property line. Format is:
        #   P: "Lcl Rotation","Lcl Rotation","","A+",<x>,<y>,<z>
        import re
        m = re.search(
            r'P:\s*"Lcl Rotation","Lcl Rotation","","A\+",\s*([\d\.\-eE]+),'
            r'\s*([\d\.\-eE]+),\s*([\d\.\-eE]+)',
            fbx_text,
        )
        assert m is not None, (
            "FBX output does not contain a static Lcl Rotation property. "
            "Excerpt:\n" + fbx_text[:2000]
        )
        emitted = [float(m.group(1)), float(m.group(2)), float(m.group(3))]
        assert emitted == pytest.approx([-27.3, 24.3, -0.7], abs=1e-5), (
            f"Lcl Rotation must be negated in the FBX so Flame's import_fbx "
            f"re-negates back to the input. Got {emitted}, expected "
            f"[-27.3, 24.3, -0.7]."
        )

    def test_write_emits_negated_anim_curve_rotation_defaults(self, tmp_path):
        """Same contract on the AnimCurveNode::R d|X,Y,Z Default values —
        they carry the same static rotation and must also be negated so
        Flame's AnimationCurve import produces the correct cam.rotation."""
        payload = self._payload_rot([27.3, -24.3, 0.7])
        json_in = tmp_path / "in.json"
        json_in.write_text(json.dumps(payload))
        fbx_out = tmp_path / "out.fbx"
        v5_json_to_fbx(str(json_in), str(fbx_out), camera_name="Cam")

        fbx_text = fbx_out.read_text()
        # AnimationCurve KeyValueFloat lines carry the per-frame samples.
        # For a single-frame payload, there is exactly one value per axis.
        # The curves are connected to AnimCurveNode::R properties d|X,Y,Z.
        # We inspect the concrete numeric arrays written for each axis.
        import re
        # Each rotation curve appears as:
        #   AnimationCurve: <id>, "AnimCurve::", "" {
        #       ...
        #       KeyValueFloat: *1 { a: <val> }
        #       ...
        #   }
        # and is connected via a Connections: OP "Channel" to the
        # AnimCurveNode::R with sub-channel "d|X"/"d|Y"/"d|Z".
        #
        # Rather than untangle the ID graph, we check the weaker but
        # sufficient invariant: the FBX text contains the three negated
        # values on a single-frame payload. The positive values must NOT
        # appear as KeyValueFloat samples.
        #
        # (The stronger invariant — value X lands on curve X — is covered
        # by the round-trip tests in TestWriter.)
        def _keyvalue_samples(text):
            return set(re.findall(r'KeyValueFloat:\s*\*\d+\s*\{\s*a:\s*([\-\d\.eE,\s]+)\s*\}', text))

        samples = _keyvalue_samples(fbx_text)
        flat_values = []
        for s in samples:
            for tok in s.split(','):
                tok = tok.strip()
                if tok:
                    try:
                        flat_values.append(float(tok))
                    except ValueError:
                        pass
        # Negated values must be present.
        for expected in (-27.3, 24.3, -0.7):
            assert any(abs(v - expected) < 1e-4 for v in flat_values), (
                f"Expected KeyValueFloat sample with value {expected} not "
                f"found in FBX. Samples: {sorted(flat_values)[:20]}..."
            )
        # Unnegated values must NOT appear as rotation samples. (27.3 and
        # 0.7 and -24.3 would indicate the double-negation was removed and
        # the live Flame round-trip would break.)
        for forbidden in (27.3, -24.3, 0.7):
            close_matches = [v for v in flat_values if abs(v - forbidden) < 1e-4]
            assert not close_matches, (
                f"Unnegated rotation sample {forbidden} found in FBX — this "
                f"means the negation on write was removed. The live Flame "
                f"import_fbx round-trip will break. Samples matching: "
                f"{close_matches}"
            )

    def test_read_negates_when_reading_back_flame_export(self, tmp_path):
        """The read path must also negate — a Flame-emitted FBX has
        already-negated LclRotation (because Flame's export_fbx applies
        its own convention), so when our reader extracts cam.rotation we
        re-negate to recover the user-visible rotation.

        Concretely: build a payload whose emitted FBX has LclRotation=
        (-27.3, 24.3, -0.7); parse that FBX back with fbx_to_v5_json;
        assert the returned rotation_flame_euler equals (27.3, -24.3, 0.7).
        """
        # Start from the user-visible rotation, write (the writer negates
        # on our behalf), then read back (the reader negates again).
        payload = self._payload_rot([27.3, -24.3, 0.7])
        json_in = tmp_path / "in.json"
        json_in.write_text(json.dumps(payload))
        fbx_out = tmp_path / "out.fbx"
        v5_json_to_fbx(str(json_in), str(fbx_out), camera_name="Cam")

        data = fbx_to_v5_json(
            str(fbx_out), str(tmp_path / "back.json"),
            width=1920, height=1080,
            camera_name="Cam", film_back_mm=16.0,
        )
        assert len(data["frames"]) == 1
        got = data["frames"][0]["rotation_flame_euler"]
        assert got == pytest.approx([27.3, -24.3, 0.7], abs=1e-5), (
            f"Expected round-trip to return (27.3, -24.3, 0.7) (user-visible "
            f"rotation); got {got}. If this fails, either the write-side "
            f"negation or the read-side negation has drifted."
        )
