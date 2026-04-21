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
