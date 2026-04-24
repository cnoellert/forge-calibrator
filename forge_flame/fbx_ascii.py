"""
Flame ASCII FBX reader + writer — narrowly scoped to camera and
animation-curve data, not a general-purpose FBX library.

Why this module exists: Flame's ``PyActionNode.export_fbx`` only emits
ASCII FBX 7.7.0 (no binary option in the Python API), and Blender 4.5's
FBX importer explicitly rejects ASCII. The official FBX Python SDK wheel
Autodesk ships is cp310, which doesn't match Flame's 3.11 Python. So
for animated camera round-trip we need our own narrow ASCII FBX bridge:

    reader:  Flame ASCII FBX  -> v5 JSON contract (camera + keyframes)
    writer:  v5 JSON contract -> ASCII FBX acceptable to Flame's import_fbx

Tested against the exact shape Flame's ``export_fbx`` emits — not
attempting to handle arbitrary FBX files from other DCCs. If Blender is
asked to produce FBX that lands back in Flame, we go Blender->JSON
(via ``tools/blender/extract_camera.py``)->this writer->FBX so we
control the emitted shape end-to-end.

Scope boundaries, on purpose:
  - Cameras only. Meshes, lights, materials, skeletons: ignored on read,
    not emitted on write.
  - Animation curves for the three channels Flame populates during
    ``bake_animation=True``: ``Lcl Translation`` (T), ``Lcl Rotation``
    (R), and ``FieldOfView``.
  - Single camera per FBX on write. Callers who want multi-camera can
    export each separately.

The reader is a general-purpose FBX-ASCII tokenizer + recursive-descent
parser (~200 LOC). The writer is template-shaped emission: it doesn't
try to reproduce FBX's Definitions templates from first principles, it
emits the exact subset Flame's own export writes (verified via
``/tmp/forge_fbx_baked.fbx`` from the v6.2 probing session).

As of 2026-04-24 (Phase 4.2), this module also resolves Aim/Target-rig
camera orientation. Flame's ``action.export_fbx`` emits aim-rig cameras
with zero Lcl Rotation and encodes orientation as (a) a LookAtProperty
``C: "OP", <null_id>, <cam_id>, "LookAtProperty"`` connection to an
aim Null, (b) the camera's UpVector + Roll Properties70, and (c)
optional AnimCurveNodes on any of those three (per-frame aim, up,
roll). The parser resolves these into a per-frame cam-to-world matrix
via ``forge_core.math.rotations.rotation_matrix_from_look_at`` and
decomposes to Flame's ZYX Euler — the resulting ``rotation_flame_euler``
in the v5 JSON is identical in shape to what a free-rig camera
produces, so downstream consumers (Blender bake, 2VP parity tests)
stay unchanged. See memory/flame_bridge.md for the live-probe history
that motivated this parser-layer fix.
"""

from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional, Tuple


# =============================================================================
# FBX time constants
# =============================================================================

# FBX internal time resolution — ticks per second. This is fixed across
# FBX versions since at least 6.0 and is documented in Autodesk's FBX
# SDK reference. Every ``KeyTime`` integer in an FBX AnimCurve is in
# these units, regardless of the project frame rate.
FBX_KTIME_PER_SECOND = 46186158000

# Frame-rate string -> numeric fps. Matches the strings Flame accepts
# for the ``frame_rate`` kwarg of ``export_fbx``. Fall back to 24.0 for
# unknown strings; the writer will log but not raise.
_FPS_FROM_FRAME_RATE = {
    "23.976 fps": 24000.0 / 1001.0,  # exact NTSC 23.976
    "24 fps": 24.0,
    "25 fps": 25.0,
    "29.97 fps": 30000.0 / 1001.0,
    "30 fps": 30.0,
    "48 fps": 48.0,
    "50 fps": 50.0,
    "59.94 fps": 60000.0 / 1001.0,
    "60 fps": 60.0,
}


def ktime_per_frame(frame_rate: str) -> float:
    """Return FBX-ticks per frame at the given frame-rate label."""
    fps = _FPS_FROM_FRAME_RATE.get(frame_rate, 24.0)
    return FBX_KTIME_PER_SECOND / fps


def frame_from_ktime(ktime: int, frame_rate: str) -> int:
    """Convert an FBX ``KeyTime`` integer to a nearest-integer frame
    number. Invariant: ``frame_from_ktime(ktime_from_frame(f, fr), fr) == f``
    for all frame rates we ship."""
    return int(round(ktime / ktime_per_frame(frame_rate)))


def ktime_from_frame(frame: int, frame_rate: str) -> int:
    """Convert a frame number to an FBX ``KeyTime`` integer."""
    return int(round(frame * ktime_per_frame(frame_rate)))


# =============================================================================
# Tokenizer
# =============================================================================

# Lexical tokens emitted by the tokenizer.
_T_IDENT   = "IDENT"    # bare name: Model, Properties70, Y, Version, ...
_T_STRING  = "STRING"   # "..." double-quoted
_T_NUMBER  = "NUMBER"   # int or float, with optional sign / exponent
_T_COLON   = "COLON"    # :
_T_COMMA   = "COMMA"    # ,
_T_LBRACE  = "LBRACE"   # {
_T_RBRACE  = "RBRACE"   # }
_T_STAR    = "STAR"     # * (array-length prefix, followed by NUMBER)


# Regex for one token at a time. Order matters — we test most specific first.
# FBX identifiers can contain digits AND double-colons (e.g. "Lcl Translation"
# in some contexts, but those always appear quoted as strings; identifiers
# themselves are plain alphanumeric-plus-underscore).
_TOK_RE = re.compile(
    r"""
    \s+                     # whitespace — skipped
  | ;[^\n]*                 # comments from ; to end of line — skipped
  | " (?: [^"\\] | \\. )* " # string
  | -? \d+ \. \d* (?: [eE][+-]?\d+ )?  # float with digits before dot
  | -? \. \d+ (?: [eE][+-]?\d+ )?      # float starting with .
  | -? \d+ (?: [eE][+-]?\d+ )?         # int or float with exponent
  | [A-Za-z_][A-Za-z0-9_]*  # identifier
  | :
  | ,
  | \{
  | \}
  | \*
    """,
    re.VERBOSE,
)


def _tokenize(text: str) -> list[tuple[str, Any]]:
    """Split FBX ASCII text into a list of ``(kind, value)`` tokens.

    Whitespace and comments are discarded. String values are unescaped.
    Numbers are parsed as ``int`` when they have no decimal point and no
    exponent, else ``float``. Identifiers remain strings."""
    tokens: list[tuple[str, Any]] = []
    pos = 0
    length = len(text)

    while pos < length:
        m = _TOK_RE.match(text, pos)
        if m is None:
            raise ValueError(
                f"FBX tokenize: unexpected character {text[pos]!r} at "
                f"position {pos} (near: {text[max(0, pos-20):pos+20]!r})")
        s = m.group(0)
        pos = m.end()

        # Skip whitespace and comments.
        if s[0] in " \t\r\n" or s.startswith(";"):
            continue

        c0 = s[0]
        if c0 == '"':
            tokens.append((_T_STRING, _unescape_string(s)))
        elif c0 == ":":
            tokens.append((_T_COLON, s))
        elif c0 == ",":
            tokens.append((_T_COMMA, s))
        elif c0 == "{":
            tokens.append((_T_LBRACE, s))
        elif c0 == "}":
            tokens.append((_T_RBRACE, s))
        elif c0 == "*":
            tokens.append((_T_STAR, s))
        elif c0 == "-" or c0.isdigit() or c0 == ".":
            tokens.append((_T_NUMBER, _parse_number(s)))
        else:
            # Bare identifier (letter or underscore start).
            tokens.append((_T_IDENT, s))

    return tokens


def _unescape_string(s: str) -> str:
    """Strip surrounding quotes and expand backslash escapes."""
    inner = s[1:-1]
    # FBX ASCII strings rarely use escapes beyond \" and \\ but handle
    # those defensively. Python's codecs do the rest.
    return inner.encode("utf-8").decode("unicode_escape")


def _parse_number(s: str) -> Any:
    """Parse a numeric token into ``int`` (no `.` or exponent) else ``float``."""
    if "." in s or "e" in s or "E" in s:
        return float(s)
    return int(s)


# =============================================================================
# Parser — recursive descent into a tree of FBXNode
# =============================================================================


@dataclass
class FBXNode:
    """One node in an FBX ASCII tree.

    ``name``    — the identifier before the ``:``, e.g. ``Model``.
    ``values``  — the comma-separated values between ``:`` and the
                  block (or end of line), e.g. ``[5496786432,
                  "Model::Default", "Camera"]`` for ``Model:
                  5496786432, "Model::Default", "Camera" { ... }``.
    ``array_len`` — set if the values are of the form ``*N { a: v... }``.
                  The actual array values live in ``values`` (flattened
                  from the ``a:`` child).
    ``children`` — nested FBXNodes if a ``{ ... }`` block followed.
    ``is_block``  — True when the source text had explicit ``{ }``,
                  even if the block was empty. Flame's ``import_fbx``
                  requires ``{ }`` on certain object-instance nodes
                  (AnimationStack, AnimationLayer, References, etc.)
                  even when they carry no children. Dropping the braces
                  on round-trip silently breaks animation imports — the
                  stack doesn't register, so curves never activate.
    """

    name: str
    values: list[Any] = field(default_factory=list)
    array_len: Optional[int] = None
    children: list["FBXNode"] = field(default_factory=list)
    is_block: bool = False

    # -------------------------------------------------------------------------
    # Tree-query convenience — these keep extraction code compact.
    # -------------------------------------------------------------------------

    def find(self, name: str) -> Optional["FBXNode"]:
        """Return the first child with the given name, or ``None``."""
        for c in self.children:
            if c.name == name:
                return c
        return None

    def find_all(self, name: str) -> list["FBXNode"]:
        """Return all children with the given name."""
        return [c for c in self.children if c.name == name]


def _parse(tokens: list[tuple[str, Any]]) -> list[FBXNode]:
    """Parse a token list into a list of top-level FBXNodes."""
    idx = 0

    def peek(offset: int = 0) -> Optional[tuple[str, Any]]:
        i = idx + offset
        return tokens[i] if i < len(tokens) else None

    def consume(kind: str) -> Any:
        nonlocal idx
        tok = peek()
        if tok is None or tok[0] != kind:
            raise ValueError(
                f"FBX parse: expected {kind}, got {tok!r} at token {idx}")
        idx += 1
        return tok[1]

    def parse_values() -> tuple[list[Any], Optional[int]]:
        """Parse a comma-separated value list after a COLON. Handles the
        ``*N`` array-length form specially."""
        values: list[Any] = []
        array_len: Optional[int] = None
        tok = peek()
        if tok is None:
            return values, array_len

        # Array-length form: *N { a: v1, v2, ... }
        if tok[0] == _T_STAR:
            nonlocal idx
            idx += 1
            n_tok = peek()
            if n_tok is None or n_tok[0] != _T_NUMBER:
                raise ValueError(
                    f"FBX parse: expected array length after *, got {n_tok!r}")
            array_len = int(n_tok[1])
            idx += 1
            # The array values are the `a:` child of the following
            # block, but we flatten them up into this node's values.
            return values, array_len

        # Normal comma-separated value list. Stops at newline-equivalent
        # boundaries: a following IDENT that is the next entry's name,
        # a LBRACE, or a RBRACE. We detect "new entry" by looking for
        # IDENT-COLON ahead.
        while True:
            tok = peek()
            if tok is None:
                break
            if tok[0] == _T_LBRACE or tok[0] == _T_RBRACE:
                break
            if tok[0] == _T_IDENT:
                # Is this the start of a new entry? If followed by COLON
                # it is — yield control back to the block parser.
                next_tok = peek(1)
                if next_tok is not None and next_tok[0] == _T_COLON:
                    break
                # Bare identifier as a value (e.g. `Shading: Y`).
                values.append(tok[1])
                idx += 1
            elif tok[0] in (_T_NUMBER, _T_STRING):
                values.append(tok[1])
                idx += 1
            elif tok[0] == _T_COMMA:
                idx += 1
            else:
                break
        return values, array_len

    def parse_node() -> FBXNode:
        name = consume(_T_IDENT)
        consume(_T_COLON)
        values, array_len = parse_values()

        children: list[FBXNode] = []
        saw_lbrace = False
        if peek() is not None and peek()[0] == _T_LBRACE:
            saw_lbrace = True
            idx_save = idx  # noqa: F841 — kept for debugger
            consume(_T_LBRACE)
            while peek() is not None and peek()[0] != _T_RBRACE:
                children.append(parse_node())
            consume(_T_RBRACE)

        # If this was an array node (*N { a: ... }), flatten the `a:`
        # child into the node's own values for easier downstream use.
        if array_len is not None:
            a_child = None
            for c in children:
                if c.name == "a":
                    a_child = c
                    break
            if a_child is not None:
                values = list(a_child.values)
                children = [c for c in children if c.name != "a"]

        return FBXNode(name=name, values=values, array_len=array_len,
                       children=children, is_block=saw_lbrace)

    nodes: list[FBXNode] = []
    while idx < len(tokens):
        nodes.append(parse_node())
    return nodes


def parse_fbx_ascii(text: str) -> list[FBXNode]:
    """Tokenize and parse an FBX ASCII document into a top-level
    FBXNode list. Public entry point for test code."""
    return _parse(_tokenize(text))


# =============================================================================
# Extraction — FBX tree -> v5 JSON contract
# =============================================================================


def _as_int(v: Any) -> int:
    return int(v)


def _as_float(v: Any) -> float:
    return float(v)


def _get_property70(node: FBXNode, key: str) -> Optional[list[Any]]:
    """Pull a ``P: "key", type, subtype, flags, value...`` line out of a
    node's ``Properties70`` child, return the trailing value list or
    ``None`` if missing."""
    props = node.find("Properties70")
    if props is None:
        return None
    for child in props.children:
        if child.name != "P":
            continue
        if not child.values or child.values[0] != key:
            continue
        # values[0..3] are (key, type, subtype, flags). Rest is the value.
        return list(child.values[4:])
    return None


def _iter_objects(root: list[FBXNode], kind: str) -> Iterable[FBXNode]:
    """Walk the top-level ``Objects { ... }`` block and yield children
    whose name matches ``kind`` (e.g. ``Model``, ``NodeAttribute``,
    ``AnimationCurve``, ``AnimationCurveNode``)."""
    for top in root:
        if top.name != "Objects":
            continue
        for obj in top.children:
            if obj.name == kind:
                yield obj


def _parse_connections(root: list[FBXNode]) -> list[tuple[str, int, int, Optional[str]]]:
    """Extract the ``Connections { C: "OO"/"OP", src, dst [, channel] }``
    edges into a flat list. Source and destination are FBX object IDs
    (64-bit integers). ``channel`` is the property name for ``OP`` edges
    (e.g. ``"Lcl Translation"``, ``"d|X"``)."""
    edges: list[tuple[str, int, int, Optional[str]]] = []
    for top in root:
        if top.name != "Connections":
            continue
        for c in top.children:
            if c.name != "C":
                continue
            v = c.values
            if len(v) < 3:
                continue
            kind = v[0]
            src = _as_int(v[1])
            dst = _as_int(v[2])
            channel = v[3] if len(v) >= 4 else None
            edges.append((kind, src, dst, channel))
    return edges


def _object_id(obj: FBXNode) -> int:
    """Return the numeric ID of an FBX object node (the first value on
    ``Model: 5496786432, "Model::Default", "Camera" { ... }``)."""
    if not obj.values:
        raise ValueError(f"FBX extract: {obj.name!r} has no object ID")
    return _as_int(obj.values[0])


def _object_name(obj: FBXNode) -> str:
    """Return the object's name, parsed out of ``"ClassName::InstanceName"``
    (the 2nd value on the object header). Empty if missing."""
    if len(obj.values) < 2:
        return ""
    raw = obj.values[1]
    if isinstance(raw, str) and "::" in raw:
        return raw.split("::", 1)[1]
    return raw if isinstance(raw, str) else ""


@dataclass
class _CameraExtract:
    """Intermediate bag of parsed camera data before JSON emission."""

    name: str
    model_id: int
    node_attr_id: int
    field_of_view: float        # from NodeAttribute Properties70
    film_width_inches: float    # from NodeAttribute Properties70 (FilmHeight? see note)
    film_height_inches: float
    static_position: Tuple[float, float, float]   # from Model Lcl Translation
    static_rotation: Tuple[float, float, float]   # from Model Lcl Rotation
    # Animation, if any:
    t_curve_ids: dict[str, int] = field(default_factory=dict)  # {"X": curve_id, ...}
    r_curve_ids: dict[str, int] = field(default_factory=dict)
    fov_curve_id: Optional[int] = None
    # Aim-rig fields (Phase 4.2, D-08). All default to empty / None; only
    # populated when the camera is bound by a LookAtProperty connection
    # to an aim Null. When any of these is non-default, _merge_curves
    # takes the aim-rig branch instead of reading rx/ry/rz curves.
    aim_null_id: Optional[int] = None
    static_aim_position: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    aim_t_curve_ids: dict[str, int] = field(default_factory=dict)
    static_up_vector: Tuple[float, float, float] = (0.0, 1.0, 0.0)
    up_curve_ids: dict[str, int] = field(default_factory=dict)  # Properties70 "UpVector" AnimCurveNode d|X/d|Y/d|Z
    static_roll: float = 0.0
    roll_curve_id: Optional[int] = None


def _extract_cameras(root: list[FBXNode]) -> list[_CameraExtract]:
    """Find all camera Models in the tree and pair each with its
    NodeAttribute + animation curves via the Connections graph."""
    # Pass 1: Models with TypeFlags "Camera" (or `, "Camera"` in the header).
    # Pass 2: NodeAttributes of type Camera.
    # Pass 3: AnimationCurveNode objects and their Properties70/d|... links.
    # Pass 4: walk Connections to hook them all up.

    camera_models: dict[int, FBXNode] = {}
    for m in _iter_objects(root, "Model"):
        # Header shape: Model: ID, "Model::Name", "Camera"
        if len(m.values) >= 3 and m.values[2] == "Camera":
            camera_models[_object_id(m)] = m

    # Aim-rig detection (Phase 4.2, D-02): scan Null Models so we can
    # resolve LookAtProperty connection sources. Duck-typing on
    # ``values[2] == "Null"`` mirrors the camera scan shape above.
    null_models: dict[int, FBXNode] = {}
    for m in _iter_objects(root, "Model"):
        if len(m.values) >= 3 and m.values[2] == "Null":
            null_models[_object_id(m)] = m

    camera_node_attrs: dict[int, FBXNode] = {}
    for na in _iter_objects(root, "NodeAttribute"):
        if len(na.values) >= 3 and na.values[2] == "Camera":
            camera_node_attrs[_object_id(na)] = na

    anim_nodes: dict[int, FBXNode] = {
        _object_id(n): n for n in _iter_objects(root, "AnimationCurveNode")
    }
    anim_curves: dict[int, FBXNode] = {
        _object_id(c): c for c in _iter_objects(root, "AnimationCurve")
    }

    edges = _parse_connections(root)

    # Map NodeAttribute -> Model.
    model_to_node_attr: dict[int, int] = {}
    for kind, src, dst, _chan in edges:
        if kind != "OO":
            continue
        if src in camera_node_attrs and dst in camera_models:
            model_to_node_attr[dst] = src

    # Map AnimCurveNode -> (model_or_nodeattr, channel_name).
    anim_links: dict[int, tuple[int, str]] = {}
    for kind, src, dst, chan in edges:
        if kind != "OP" or chan is None:
            continue
        if src in anim_nodes:
            anim_links[src] = (dst, chan)

    # Map AnimCurve -> (anim_node, sub_channel_name).
    curve_links: dict[int, tuple[int, str]] = {}
    for kind, src, dst, chan in edges:
        if kind != "OP" or chan is None:
            continue
        if src in anim_curves and dst in anim_nodes:
            curve_links[src] = (dst, chan)

    # Map camera Model ID -> aim Null Model ID (LookAtProperty connections).
    # FBX shape: C: "OP", <null_id>, <cam_id>, "LookAtProperty"
    # (Phase 4.2, D-02/D-14.) A LookAtProperty edge whose source does not
    # resolve to a known Null is a structural bug — fail loud rather than
    # silently drop the aim-rig semantic.
    cam_to_aim_null: dict[int, int] = {}
    for kind, src, dst, chan in edges:
        if kind == "OP" and chan == "LookAtProperty":
            if src in null_models and dst in camera_models:
                cam_to_aim_null[dst] = src
            elif dst in camera_models and src not in null_models:
                raise ValueError(
                    f"aim-rig resolve: LookAtProperty connection references "
                    f"unknown Null id {src!r} for camera "
                    f"{_object_name(camera_models[dst])!r}"
                )

    results: list[_CameraExtract] = []
    for model_id, model in camera_models.items():
        name = _object_name(model)

        na_id = model_to_node_attr.get(model_id)
        na = camera_node_attrs.get(na_id) if na_id is not None else None

        # Field of view: NodeAttribute.Properties70 FieldOfView, default 40.
        fov = 40.0
        if na is not None:
            p = _get_property70(na, "FieldOfView")
            if p:
                fov = _as_float(p[0])

        # Film dimensions: FilmWidth/FilmHeight on NodeAttribute in inches.
        film_w = 0.944
        film_h = 0.629
        if na is not None:
            p = _get_property70(na, "FilmWidth")
            if p:
                film_w = _as_float(p[0])
            p = _get_property70(na, "FilmHeight")
            if p:
                film_h = _as_float(p[0])

        # Static Lcl Translation / Lcl Rotation, if present on the Model.
        pos = (0.0, 0.0, 0.0)
        p = _get_property70(model, "Lcl Translation")
        if p and len(p) >= 3:
            pos = (_as_float(p[0]), _as_float(p[1]), _as_float(p[2]))

        rot = (0.0, 0.0, 0.0)
        p = _get_property70(model, "Lcl Rotation")
        if p and len(p) >= 3:
            rot = (_as_float(p[0]), _as_float(p[1]), _as_float(p[2]))

        # Aim-rig detection and field population (Phase 4.2, D-02/D-08).
        # When the camera is bound by a LookAtProperty connection to an aim
        # Null, resolve the aim target's position, the camera's UpVector /
        # Roll Properties70, and any animation curves for those channels.
        # Flame emits UpVector / Roll on BOTH the NodeAttribute (primary —
        # this is where ``action.export_fbx`` writes live-probe values)
        # AND the Model (inherited from the FBX template). AnimCurveNodes
        # for UpVector / Roll are connected to the NodeAttribute in the
        # Camera1 live probe (lines 642-643 of the fixture); the code
        # tolerates either target.
        aim_null_id = cam_to_aim_null.get(model_id)
        static_aim_position: Tuple[float, float, float] = (0.0, 0.0, 0.0)
        aim_t_curve_ids: dict[str, int] = {}
        static_up_vector: Tuple[float, float, float] = (0.0, 1.0, 0.0)
        up_curve_ids: dict[str, int] = {}
        static_roll: float = 0.0
        roll_curve_id: Optional[int] = None

        if aim_null_id is not None:
            aim_null = null_models[aim_null_id]
            # Static aim position from the aim Null's Lcl Translation.
            # Same inline _get_property70 + _as_float pattern as the
            # camera's own Lcl Translation read above.
            p = _get_property70(aim_null, "Lcl Translation")
            if p and len(p) >= 3:
                static_aim_position = (
                    _as_float(p[0]), _as_float(p[1]), _as_float(p[2])
                )

            # Animated aim: find AnimCurveNodes linked to the aim Null's
            # Lcl Translation via the existing anim_links dispatch, then
            # walk curve_links to bucket d|X / d|Y / d|Z curves.
            for anim_node_id, (target_id, channel) in anim_links.items():
                if target_id == aim_null_id and channel == "Lcl Translation":
                    for curve_id, (owner_anim_id, sub_chan) in curve_links.items():
                        if owner_anim_id == anim_node_id and sub_chan in ("d|X", "d|Y", "d|Z"):
                            aim_t_curve_ids[sub_chan[-1]] = curve_id

            # Static up from Properties70 "UpVector" — NodeAttribute first
            # (authoritative for live-probe values), then Model (template
            # default). Later assignment wins; we check NA first then
            # overwrite with Model only if Model has a non-template value.
            if na is not None:
                p = _get_property70(na, "UpVector")
                if p and len(p) >= 3:
                    static_up_vector = (_as_float(p[0]), _as_float(p[1]), _as_float(p[2]))
            p = _get_property70(model, "UpVector")
            if p and len(p) >= 3:
                static_up_vector = (_as_float(p[0]), _as_float(p[1]), _as_float(p[2]))

            # Animated up: AnimCurveNodes linked with channel "UpVector"
            # — check BOTH the camera Model and the NodeAttribute as
            # possible targets (Flame's live export attaches to the NA).
            for anim_node_id, (target_id, channel) in anim_links.items():
                if channel == "UpVector" and target_id in (model_id, na_id):
                    for curve_id, (owner_anim_id, sub_chan) in curve_links.items():
                        if owner_anim_id == anim_node_id and sub_chan in ("d|X", "d|Y", "d|Z"):
                            up_curve_ids[sub_chan[-1]] = curve_id

            # Static roll from Properties70 "Roll" (default 0.0). Same
            # NA-first-then-Model precedence as UpVector.
            if na is not None:
                p = _get_property70(na, "Roll")
                if p:
                    static_roll = _as_float(p[0])
            p = _get_property70(model, "Roll")
            if p:
                static_roll = _as_float(p[0])

            # Animated roll: AnimCurveNode linked with channel "Roll".
            # Scalar channel — pick the first AnimCurve bound to the node.
            # Check BOTH model_id and na_id as possible targets.
            for anim_node_id, (target_id, channel) in anim_links.items():
                if channel == "Roll" and target_id in (model_id, na_id):
                    for curve_id, (owner_anim_id, sub_chan) in curve_links.items():
                        if owner_anim_id == anim_node_id:
                            roll_curve_id = curve_id
                            break
                    break

        cam = _CameraExtract(
            name=name,
            model_id=model_id,
            node_attr_id=na_id or 0,
            field_of_view=fov,
            film_width_inches=film_w,
            film_height_inches=film_h,
            static_position=pos,
            static_rotation=rot,
            aim_null_id=aim_null_id,
            static_aim_position=static_aim_position,
            aim_t_curve_ids=aim_t_curve_ids,
            static_up_vector=static_up_vector,
            up_curve_ids=up_curve_ids,
            static_roll=static_roll,
            roll_curve_id=roll_curve_id,
        )

        # Find the animation-curve-nodes attached to this Model (T, R) and
        # to its NodeAttribute (FieldOfView).
        for anim_id, (target, chan) in anim_links.items():
            if target == model_id and chan == "Lcl Translation":
                cam._anim_node_t = anim_id
            elif target == model_id and chan == "Lcl Rotation":
                cam._anim_node_r = anim_id
            elif target == na_id and chan == "FieldOfView":
                cam._anim_node_fov = anim_id

        # Walk curves attached to those anim-nodes and bucket by sub-channel.
        for curve_id, (parent_anim, sub_chan) in curve_links.items():
            if getattr(cam, "_anim_node_t", None) == parent_anim:
                cam.t_curve_ids[_axis_from_sub_channel(sub_chan)] = curve_id
            elif getattr(cam, "_anim_node_r", None) == parent_anim:
                cam.r_curve_ids[_axis_from_sub_channel(sub_chan)] = curve_id
            elif getattr(cam, "_anim_node_fov", None) == parent_anim:
                cam.fov_curve_id = curve_id

        results.append(cam)

    return results


def _axis_from_sub_channel(chan: str) -> str:
    """Map FBX sub-channel names (``d|X``, ``d|Y``, ``d|Z``,
    ``d|FieldOfView``) to our short axis labels."""
    if chan.startswith("d|"):
        return chan[2:]
    return chan


@dataclass
class _CurveSamples:
    times: list[int]         # FBX KTime integers
    values: list[float]

    @classmethod
    def empty(cls) -> "_CurveSamples":
        return cls(times=[], values=[])


def _read_curve(curve_id: Optional[int], root: list[FBXNode]) -> _CurveSamples:
    """Given an AnimationCurve object ID, pull the flattened KeyTime +
    KeyValueFloat arrays (both arrays share length). Default to empty
    if the curve isn't found."""
    if curve_id is None:
        return _CurveSamples.empty()
    for c in _iter_objects(root, "AnimationCurve"):
        if _object_id(c) != curve_id:
            continue
        kt = c.find("KeyTime")
        kv = c.find("KeyValueFloat")
        times = [int(x) for x in (kt.values if kt else [])]
        vals = [float(x) for x in (kv.values if kv else [])]
        return _CurveSamples(times=times, values=vals)
    return _CurveSamples.empty()


def _sample_or_static(samples: _CurveSamples, static: float) -> list[tuple[int, float]]:
    """Prefer curve samples; if empty, emit a single (ktime=0, static)
    pair so the caller still sees something consistent."""
    if not samples.times:
        return [(0, static)]
    return list(zip(samples.times, samples.values))


def _inches_to_mm(inches: float) -> float:
    """FBX's FilmHeight is in inches by convention — convert to mm for
    the v5 JSON contract (which uses mm)."""
    return inches * 25.4


def _merge_curves(
    cam: _CameraExtract,
    root: list[FBXNode],
    frame_rate: str,
    *,
    frame_offset: int = 0,
    frame_start: Optional[int] = None,
    frame_end: Optional[int] = None,
) -> list[dict[str, Any]]:
    """Resolve T, R, FoV curves for a camera and interleave them into a
    per-frame list. We take the union of unique KeyTime stamps across
    the seven curves (T/R have 3 axes each, FoV has 1) and look up or
    hold each channel's last value at every stamp.

    If the camera has no keyframes at all (static export) we emit a
    single entry at frame 0 using the static Lcl Translation/Rotation.

    If ``frame_offset`` is non-zero it is added to every emitted
    ``frame`` value (both the static-fallback and keyed paths). This
    is how the Flame batch's ``start_frame`` survives the FBX
    round-trip — ``action.export_fbx(bake_animation=True)`` zero-bases
    the KTime stream, so the offset must be reapplied on read.

    If ``frame_start`` is not None, any frame whose POST-OFFSET value
    is STRICTLY less than ``frame_start`` is dropped (INCLUSIVE lower
    bound — ``frame == frame_start`` is kept; only
    ``frame < frame_start`` is dropped). This is how the Flame batch's
    ``start_frame``, combined with a ``frame_offset = start_frame - 1``,
    drops the implicit PRE-ROLL keyframe that
    ``action.export_fbx(bake_animation=True)`` emits at FBX KTime 0.
    The symmetric counterpart of ``frame_end``: together they define a
    closed range ``[frame_start, frame_end]`` in post-offset plate-frame
    space.

    If ``frame_end`` is not None, any frame whose POST-OFFSET value
    exceeds it is dropped (INCLUSIVE upper bound — ``frame == frame_end``
    is kept; only ``frame > frame_end`` is dropped). This is how the
    Flame batch's ``end_frame`` trims the single trailing keyframe that
    ``action.export_fbx(bake_animation=True)`` bakes past the user's
    range — Flame emits ``(end - start + 1)`` KTimes which, after the
    +``start_frame`` offset, lands one frame past end. Clip applies
    after the offset so the comparison is against the user-facing plate
    frame number.
    """
    # Local import — aim-rig branch only. Keeps fbx_ascii module-scope
    # numpy-free so other consumers (e.g. the FBX writer) do not pay
    # the numpy import cost unless the reader is actually invoked.
    # Imported up-front (not conditionally) to keep the static_fallback
    # and per-frame branches below straightforward.
    from forge_core.math.rotations import (  # noqa: E402 — intentional local import
        rotation_matrix_from_look_at,
        compute_flame_euler_zyx,
    )

    tx = _read_curve(cam.t_curve_ids.get("X"), root)
    ty = _read_curve(cam.t_curve_ids.get("Y"), root)
    tz = _read_curve(cam.t_curve_ids.get("Z"), root)
    rx = _read_curve(cam.r_curve_ids.get("X"), root)
    ry = _read_curve(cam.r_curve_ids.get("Y"), root)
    rz = _read_curve(cam.r_curve_ids.get("Z"), root)
    fov = _read_curve(cam.fov_curve_id, root)

    # Aim-rig mode detection (Phase 4.2, D-02/D-08). The branch fires
    # when the camera was bound by a LookAtProperty connection AND its
    # Lcl Rotation curves are either absent or identically zero — Flame
    # emits zero rotation on aim-rig cameras; the orientation lives in
    # aim/up/roll. If for some reason an FBX carries BOTH a non-zero
    # Lcl Rotation curve AND an aim Null, prefer the explicit rotation
    # curve (matches the user's principle "transform is what matters").
    is_aim_rig = cam.aim_null_id is not None
    if is_aim_rig:
        for c in (rx, ry, rz):
            if any(abs(v) > 1e-9 for v in c.values):
                is_aim_rig = False
                break

    if is_aim_rig:
        # Aim-rig animation curves. Any of these may be empty (static
        # channel); _sample_at falls back to the Properties70 static.
        aim_tx = _read_curve(cam.aim_t_curve_ids.get("X"), root)
        aim_ty = _read_curve(cam.aim_t_curve_ids.get("Y"), root)
        aim_tz = _read_curve(cam.aim_t_curve_ids.get("Z"), root)
        up_cx  = _read_curve(cam.up_curve_ids.get("X"), root)
        up_cy  = _read_curve(cam.up_curve_ids.get("Y"), root)
        up_cz  = _read_curve(cam.up_curve_ids.get("Z"), root)
        roll_c = _read_curve(cam.roll_curve_id, root)
    else:
        aim_tx = aim_ty = aim_tz = _CurveSamples.empty()
        up_cx  = up_cy  = up_cz  = _CurveSamples.empty()
        roll_c = _CurveSamples.empty()

    # Static fallback: none of the curves had any keys.
    if is_aim_rig:
        any_keyed = any(c.times for c in (
            tx, ty, tz, rx, ry, rz, fov,
            aim_tx, aim_ty, aim_tz, up_cx, up_cy, up_cz, roll_c,
        ))
    else:
        any_keyed = any(c.times for c in (tx, ty, tz, rx, ry, rz, fov))

    if not any_keyed:
        frame = frame_offset
        # Clip AFTER the offset so the comparison is against the
        # user-facing plate frame number. Symmetric with the keyed
        # path below; in practice the static case rarely trips either
        # guard (a static camera in an offset-inverted batch is
        # degenerate), but apply for defensive correctness. STRICT
        # ``<`` preserves the INCLUSIVE lower bound — ``frame ==
        # frame_start`` is kept. Filter order matches the signature
        # order (``frame_start`` first, then ``frame_end``).
        if frame_start is not None and frame < frame_start:
            return []
        if frame_end is not None and frame > frame_end:
            return []
        sp = cam.static_position
        film_back_mm = _inches_to_mm(cam.film_height_inches)
        focal_mm = _focal_from_fov_filmback(cam.field_of_view, film_back_mm)

        if is_aim_rig:
            # Aim-rig static: resolve orientation from Properties70
            # values. Flame stores Roll with the same sign-flip
            # convention as Lcl Rotation (FBX positive → Flame-probe
            # negative), so negate before feeding the look-at helper —
            # matches the free-rig branch's `-_sample_at(rx, ...)`
            # negation below. Plan 01's ValueError with 'aim-rig
            # resolve:' prefix on degenerate input propagates (no
            # try/except).
            R = rotation_matrix_from_look_at(
                position=sp,
                aim=cam.static_aim_position,
                up=cam.static_up_vector,
                roll_deg=-cam.static_roll,
            )
            rx_deg, ry_deg, rz_deg = compute_flame_euler_zyx(R)
        else:
            sr = cam.static_rotation
            # Existing free-rig sign-flip.
            rx_deg, ry_deg, rz_deg = -sr[0], -sr[1], -sr[2]

        return [{
            "frame": frame,
            "position": [sp[0], sp[1], sp[2]],
            "rotation_flame_euler": [rx_deg, ry_deg, rz_deg],
            "focal_mm": focal_mm,
        }]

    # Collect unique KeyTimes across all curves (include aim-rig if active).
    all_times: set[int] = set()
    if is_aim_rig:
        for c in (tx, ty, tz, fov,
                  aim_tx, aim_ty, aim_tz,
                  up_cx, up_cy, up_cz, roll_c):
            all_times.update(c.times)
    else:
        for c in (tx, ty, tz, rx, ry, rz, fov):
            all_times.update(c.times)
    sorted_times = sorted(all_times)

    film_back_mm = _inches_to_mm(cam.film_height_inches)

    out: list[dict[str, Any]] = []
    for ktime in sorted_times:
        frame = frame_from_ktime(ktime, frame_rate) + frame_offset
        # Clip AFTER the offset is added, because frame_start and
        # frame_end are both user-facing plate frame numbers (from
        # flame.batch.start_frame / end_frame), not raw FBX KTime
        # indices. STRICT ``<`` / ``>`` preserve the INCLUSIVE bounds
        # — ``frame == frame_start`` and ``frame == frame_end`` are
        # both kept. Filter order matches the signature order
        # (``frame_start`` first, then ``frame_end``); either drops
        # the frame independently.
        if frame_start is not None and frame < frame_start:
            continue
        if frame_end is not None and frame > frame_end:
            continue
        px = _sample_at(tx, ktime, cam.static_position[0])
        py = _sample_at(ty, ktime, cam.static_position[1])
        pz = _sample_at(tz, ktime, cam.static_position[2])
        fov_deg = _sample_at(fov, ktime, cam.field_of_view)
        focal_mm = _focal_from_fov_filmback(fov_deg, film_back_mm)

        if is_aim_rig:
            # Per-frame aim-rig composition. Sampled values fall back
            # to the Properties70 static when the animation curve is
            # absent (mirror of _sample_at default-fallback for position).
            # Roll sign-flipped (FBX→Flame-probe convention) — same as
            # the static-fallback branch above.
            aim_x = _sample_at(aim_tx, ktime, cam.static_aim_position[0])
            aim_y = _sample_at(aim_ty, ktime, cam.static_aim_position[1])
            aim_z = _sample_at(aim_tz, ktime, cam.static_aim_position[2])
            up_x  = _sample_at(up_cx,  ktime, cam.static_up_vector[0])
            up_y  = _sample_at(up_cy,  ktime, cam.static_up_vector[1])
            up_z  = _sample_at(up_cz,  ktime, cam.static_up_vector[2])
            roll  = _sample_at(roll_c, ktime, cam.static_roll)
            # Propagates Plan 01's ValueError on degenerate input.
            R = rotation_matrix_from_look_at(
                position=(px, py, pz),
                aim=(aim_x, aim_y, aim_z),
                up=(up_x, up_y, up_z),
                roll_deg=-roll,
            )
            rx_deg, ry_deg, rz_deg = compute_flame_euler_zyx(R)
        else:
            rx_deg = -_sample_at(rx, ktime, cam.static_rotation[0])
            ry_deg = -_sample_at(ry, ktime, cam.static_rotation[1])
            rz_deg = -_sample_at(rz, ktime, cam.static_rotation[2])

        out.append({
            "frame": frame,
            "position": [px, py, pz],
            "rotation_flame_euler": [rx_deg, ry_deg, rz_deg],
            "focal_mm": focal_mm,
        })
    return out


def _sample_at(curve: _CurveSamples, ktime: int, default: float) -> float:
    """Look up a curve's value at an exact KTime. If the curve has no
    sample at that time, return the most-recent-prior value, or the
    default if there's nothing earlier."""
    if not curve.times:
        return float(default)
    # Exact match wins.
    if ktime in curve.times:
        idx = curve.times.index(ktime)
        return float(curve.values[idx])
    # Otherwise: last sample at or before ktime, else default.
    prior = default
    for t, v in zip(curve.times, curve.values):
        if t <= ktime:
            prior = v
        else:
            break
    return float(prior)


def _focal_from_fov_filmback(vfov_deg: float, film_back_mm: float) -> float:
    """Inverse of vfov = 2·atan(h_sensor / (2·f)). Shared with
    forge_flame.camera_io.focal_from_vfov_deg, duplicated here so this
    module has no cross-module imports."""
    if not (0.0 < vfov_deg < 180.0) or film_back_mm <= 0:
        return 0.0
    return film_back_mm / (2.0 * math.tan(math.radians(vfov_deg) / 2.0))


# =============================================================================
# Public entry points
# =============================================================================


def fbx_to_v5_json(
    fbx_path: str,
    out_json_path: str,
    *,
    width: int = 0,
    height: int = 0,
    film_back_mm: Optional[float] = None,
    frame_rate: str = "23.976 fps",
    camera_name: Optional[str] = None,
    custom_properties: Optional[dict] = None,
    frame_offset: int = 0,
    frame_start: Optional[int] = None,
    frame_end: Optional[int] = None,
) -> dict:
    """Read a Flame-emitted ASCII FBX and write a v5 JSON contract file.

    Args:
        fbx_path: source FBX path.
        out_json_path: destination JSON path. Parent dir is created.
        width, height: plate resolution. Not present in FBX cam metadata
            (FBX only has AspectWidth/Height hints), so the caller must
            supply them — typically derived from the same Flame clip the
            camera was solved for.
        film_back_mm: optional override for the v5 ``film_back_mm``
            field. If ``None``, we derive it from the FBX FilmHeight
            (inches -> mm). Callers who pinned film_back=36.0 in Camera
            Match should pass that same value here so JSON and the
            original solve stay consistent.
        frame_rate: FBX KTime conversion basis. Should match the frame
            rate Flame used when emitting the FBX; callers who use
            ``fbx_io.export_action_cameras_to_fbx`` with the default get
            ``"23.976 fps"``.
        camera_name: optional filter — if given, only emit the camera
            whose ``Model::<name>`` matches. If the FBX has a single
            camera the filter is a noop.
        custom_properties: optional dict of caller-supplied metadata to
            stamp into the v5 JSON payload under a top-level
            ``custom_properties`` key. Values must be JSON-serialisable
            (str / int / float per the v5 contract; see
            ``tools/blender/bake_camera.py::_stamp_metadata``, which
            consumes this field). When ``None`` or empty, no
            ``custom_properties`` key is emitted (backward-compatible
            with pre-v6.3 consumers).
        frame_offset: integer added to every ``frame`` value in the
            output. Default 0 (preserves Flame's zero-based KTime).
            Set to ``start_frame - 1`` (NOT ``start_frame`` — see
            260421-c1w) to keep round-trip frame numbers aligned with
            the source plate: ``action.export_fbx(bake_animation=True)``
            zero-bases the KTime stream AND emits an implicit pre-roll
            at KTime 0, so the first real sample lives at KTime 1 and
            must be shifted by ``start_frame - 1`` to land on
            ``start_frame``.
        frame_start: optional INCLUSIVE lower bound on emitted
            ``frame`` values. Applied AFTER ``frame_offset``. Any frame
            whose post-offset value is STRICTLY less than ``frame_start``
            is dropped. Default ``None`` (no clipping — preserves
            pre-260421-c1w behavior). Set to the Flame batch's
            ``start_frame`` (paired with
            ``frame_offset = start_frame - 1``) to drop the implicit
            PRE-ROLL keyframe that
            ``action.export_fbx(bake_animation=True)`` emits at FBX
            KTime 0. Symmetric counterpart of ``frame_end``: together
            they define a closed range ``[frame_start, frame_end]`` in
            post-offset plate-frame space.
        frame_end: optional INCLUSIVE upper bound on emitted ``frame``
            values. Applied AFTER ``frame_offset``. Any frame whose
            post-offset value exceeds ``frame_end`` is dropped. Default
            ``None`` (no clipping — preserves pre-260421-bhg behavior).
            Set to the Flame batch's ``end_frame`` to trim the single
            trailing keyframe that ``action.export_fbx(bake_animation=True)``
            bakes past the user's range: Flame emits ``(end - start + 1)``
            KTimes, which after the +``start_frame`` offset lands one
            frame past end.

    Returns the parsed v5 JSON dict (also written to disk).
    """
    with open(fbx_path, "r", encoding="utf-8") as f:
        text = f.read()
    tree = parse_fbx_ascii(text)

    cameras = _extract_cameras(tree)
    if camera_name:
        cameras = [c for c in cameras if c.name == camera_name]
    if not cameras:
        raise ValueError(f"{fbx_path}: no cameras found"
                         + (f" named {camera_name!r}" if camera_name else ""))
    if len(cameras) > 1:
        names = [c.name for c in cameras]
        raise ValueError(
            f"{fbx_path}: multiple cameras found ({names}); "
            f"pass camera_name= to select one")
    cam = cameras[0]

    frames = _merge_curves(
        cam, tree, frame_rate,
        frame_offset=frame_offset,
        frame_start=frame_start,
        frame_end=frame_end,
    )

    if film_back_mm is None:
        film_back_mm = _inches_to_mm(cam.film_height_inches)

    payload = {
        "width": int(width),
        "height": int(height),
        "film_back_mm": float(film_back_mm),
        "frames": frames,
    }
    if custom_properties:
        payload["custom_properties"] = dict(custom_properties)
    if frame_rate:
        payload["frame_rate"] = str(frame_rate)

    out_abs = os.path.abspath(out_json_path)
    os.makedirs(os.path.dirname(out_abs) or ".", exist_ok=True)
    with open(out_abs, "w") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")
    return payload


# =============================================================================
# Writer — FBXNode tree -> ASCII FBX text
# =============================================================================


def _format_value(v: Any) -> str:
    """Serialize a single FBX value literal matching Flame's output shape.

    - Strings get double-quoted (and escaped).
    - Bools become 1 / 0.
    - Ints stay as-is.
    - Floats use repr() so full double precision survives round-trip.
    - Identifiers passed in as strings starting with a letter AND having
      no spaces, quotes, or punctuation are treated as bare identifiers
      (e.g. ``Y`` for ``Shading: Y``). Callers signal this by passing
      a tuple ``("IDENT", "Y")``.
    """
    if isinstance(v, tuple) and len(v) == 2 and v[0] == "IDENT":
        return v[1]
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, str):
        return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        # repr() preserves double precision without trailing zeros.
        return repr(v)
    return str(v)


def _emit_node(node: FBXNode, lines: list[str], indent: int) -> None:
    """Recursive emitter for a single FBXNode."""
    ind = "\t" * indent

    # Special case: array form ``*N { a: v1,v2,... }``. Flame emits the
    # array header on the same line as the block open and the trailing
    # closing brace is on its own line with a trailing space (observed
    # in real files, though the trailing space isn't semantically
    # meaningful — we keep the structure but don't bother reproducing
    # that cosmetic detail).
    if node.array_len is not None:
        payload = ",".join(_format_value(v) for v in node.values)
        lines.append(f"{ind}{node.name}: *{node.array_len} {{")
        lines.append(f"{ind}\ta: {payload}")
        lines.append(f"{ind}}}")
        return

    # Value list (comma-separated, no brackets).
    values_str = ",".join(_format_value(v) for v in node.values)

    # Emit as block form when children exist OR when the source had an
    # explicit ``{ }`` (is_block=True). This preserves empty-block
    # object-instance nodes like ``AnimationStack: <id>,... { }`` that
    # Flame's ``import_fbx`` requires in their exact shape — omitting
    # the braces silently breaks animation imports because the stack
    # doesn't register and its curves never activate.
    if node.children or node.is_block:
        if values_str:
            lines.append(f"{ind}{node.name}: {values_str} {{")
        else:
            # Match Flame's two-space padding on empty-value blocks.
            lines.append(f"{ind}{node.name}:  {{")
        for child in node.children:
            _emit_node(child, lines, indent + 1)
        lines.append(f"{ind}}}")
    else:
        if values_str:
            lines.append(f"{ind}{node.name}: {values_str}")
        else:
            lines.append(f"{ind}{node.name}:")


def emit_fbx_ascii(nodes: list[FBXNode]) -> str:
    """Serialize an FBXNode tree (as returned by ``parse_fbx_ascii``)
    back to ASCII FBX text.

    The output is not byte-identical to Flame's own emit — whitespace
    and comment lines are dropped, and floats use Python's ``repr()``
    rather than Flame's specific formatting — but is structurally
    equivalent and round-trips cleanly through ``parse_fbx_ascii``.
    Flame's own ``import_fbx`` accepts it (verified on the 2026-04-19
    live round-trip).
    """
    lines: list[str] = ["; FBX 7.7.0 project file",
                        "; ----------------------------------------------------",
                        ""]
    for n in nodes:
        _emit_node(n, lines, indent=0)
    return "\n".join(lines) + "\n"


# =============================================================================
# Template-driven JSON -> FBX writer
# =============================================================================

# Template FBX shipped alongside this module. Captured from a live Flame
# 2026.2.1 session during the v6.2 probing work — represents Flame's
# exact output shape for a single-camera Action, which is the shape we
# need Flame's ``import_fbx`` to accept. We load and mutate it rather
# than building from first principles, so we inherit all of Flame's
# required metadata (Definitions templates, scene info, GlobalSettings
# axis convention, Takes section) without having to rediscover what's
# mandatory.
_TEMPLATE_FBX = os.path.join(os.path.dirname(__file__),
                              "templates", "camera_baked.fbx")


def _load_template_tree() -> list[FBXNode]:
    with open(_TEMPLATE_FBX, "r", encoding="utf-8") as f:
        return parse_fbx_ascii(f.read())


def _set_property70(node: FBXNode, key: str, type1: str, type2: str,
                    flags: str, values: list[Any]) -> None:
    """Update an existing ``P: "key", ...`` line in a node's
    ``Properties70`` child, or append one if not present. Callers pass
    the trailing value list (without the leading 4 metadata strings)."""
    props = node.find("Properties70")
    if props is None:
        props = FBXNode(name="Properties70")
        node.children.append(props)
    for child in props.children:
        if child.name == "P" and child.values and child.values[0] == key:
            child.values = [key, type1, type2, flags] + list(values)
            return
    props.children.append(FBXNode(
        name="P", values=[key, type1, type2, flags] + list(values)))


def _replace_or_append_child(node: FBXNode, name: str, new_child: FBXNode) -> None:
    """Replace the first child with this name, else append."""
    for i, c in enumerate(node.children):
        if c.name == name:
            node.children[i] = new_child
            return
    node.children.append(new_child)


def _anim_curve_node_with_data(curve_id: int, default_value: float,
                               times: list[int], values: list[float]) -> FBXNode:
    """Build an AnimationCurve FBXNode with the given keyframe arrays,
    matching the EXPANDED structure Flame 2026.2.1 emits and requires on
    import.

    Flame's ``action.import_fbx`` rejects the compact KeyAttr encoding
    (single shared flag with RefCount=N) that the FBX spec permits —
    only the expanded per-key form triggers keyframe creation on the
    imported camera. Live probe 2026-04-23 confirmed: a well-formed
    FBX using the compact form imports with cam.rotation/position
    correctly set to the FIRST key's value but zero keyframes, as if
    every key after the first were silently discarded. Re-exporting
    the imported camera produces an FBX with zero KeyValueFloat
    entries. See .planning/debug/resolved/fbx-compact-keyattr-rejected.md.

    Flame's own export uses:
      - KeyAttrFlags: *N  (N entries, value 8456 = Cubic|TangentAuto)
      - KeyAttrDataFloat: *(4*N)  (one 4-tuple per key)
      - KeyAttrRefCount: *N  (N ones)
    """
    n = len(times)
    if n != len(values):
        raise ValueError(f"curve times/values length mismatch: {n} vs {len(values)}")

    # Flame's per-key attribute flag. 8456 = 0x2108 =
    # Cubic|TangentAuto|GenericTimeIndependent. Mirrors the value emitted
    # by Flame 2026.2.1's action.export_fbx(bake_animation=True).
    FLAME_KEYATTR_FLAG = 8456
    # Flame's per-key tangent data (4 floats per key, all identical for
    # default auto-tangent keys). 218434821 encodes the standard Flame
    # tangent configuration; zeros are the other three slots.
    FLAME_TANGENT_QUAD = [0, 0, 218434821, 0]

    flags = [FLAME_KEYATTR_FLAG] * n
    tangent_data = FLAME_TANGENT_QUAD * n
    ref_counts = [1] * n

    return FBXNode(
        name="AnimationCurve",
        values=[curve_id, "AnimCurve::", ""],
        children=[
            FBXNode(name="Default", values=[float(default_value)]),
            FBXNode(name="KeyVer", values=[4009]),
            FBXNode(name="KeyTime", values=[int(t) for t in times],
                    array_len=n),
            FBXNode(name="KeyValueFloat", values=[float(v) for v in values],
                    array_len=n),
            # Per-key flag entries — one per keyframe. Flame's importer
            # requires this expanded form; the compact form (*1 with
            # RefCount=N) silently drops all keys.
            FBXNode(name="KeyAttrFlags", values=flags, array_len=n),
            # Per-key tangent data — 4 floats per key (expanded).
            FBXNode(name="KeyAttrDataFloat", values=tangent_data,
                    array_len=n * 4),
            # Per-key reference count. Each entry "1" means the
            # corresponding flag/data slot covers exactly one key —
            # the expanded form Flame's importer expects.
            FBXNode(name="KeyAttrRefCount", values=ref_counts, array_len=n),
        ],
    )


def _mutate_template_with_payload(
    tree: list[FBXNode],
    payload: dict,
    camera_name: str,
    frame_rate: str,
    pixel_to_units: float,
) -> None:
    """Rewrite the template tree's single camera + its animation curves
    to reflect the values in ``payload`` (our v5 JSON contract).

    - Renames ``Model::Default`` / ``NodeAttribute::Default`` to
      ``camera_name`` if different.
    - Updates Properties70 values for Lcl Translation/Rotation, FilmWidth,
      FilmHeight, FieldOfView.
    - Replaces the seven AnimationCurve nodes wholesale (preserving
      their object IDs and Connections) with keyframe arrays derived
      from ``payload['frames']``.
    - Updates Takes::Take::LocalTime/ReferenceTime and
      GlobalSettings::TimeSpanStop to span the full animation range.
    """
    # Find the Objects block.
    objects = next((n for n in tree if n.name == "Objects"), None)
    if objects is None:
        raise ValueError("template FBX missing Objects block")

    # Locate the single Model::Camera + NodeAttribute::Camera.
    model = None
    node_attr = None
    for m in objects.find_all("Model"):
        if len(m.values) >= 3 and m.values[2] == "Camera":
            model = m
            break
    for na in objects.find_all("NodeAttribute"):
        if len(na.values) >= 3 and na.values[2] == "Camera":
            node_attr = na
            break
    if model is None or node_attr is None:
        raise ValueError("template FBX missing a Camera Model + NodeAttribute")

    # Rename both to the caller's camera_name.
    model.values[1] = f"Model::{camera_name}"
    node_attr.values[1] = f"NodeAttribute::{camera_name}"

    # Map AnimCurveNode roles (T/R/FieldOfView) via Connections.
    model_id = _object_id(model)
    na_id = _object_id(node_attr)
    edges = _parse_connections(tree)
    anim_node_ids = {_object_id(n): n for n in objects.find_all("AnimationCurveNode")}

    role_to_anim_id: dict[str, int] = {}
    for kind, src, dst, chan in edges:
        if kind != "OP" or src not in anim_node_ids:
            continue
        if dst == model_id and chan == "Lcl Translation":
            role_to_anim_id["T"] = src
        elif dst == model_id and chan == "Lcl Rotation":
            role_to_anim_id["R"] = src
        elif dst == na_id and chan == "FieldOfView":
            role_to_anim_id["FoV"] = src

    # For each role, find the AnimCurve object IDs (one per sub-channel).
    # Order on axes (X, Y, Z) mirrors the template.
    anim_curve_ids_by_role: dict[str, dict[str, int]] = {"T": {}, "R": {}, "FoV": {}}
    for kind, src, dst, chan in edges:
        if kind != "OP" or chan is None:
            continue
        for role, aid in role_to_anim_id.items():
            if dst == aid:
                sub = chan[2:] if chan.startswith("d|") else chan
                anim_curve_ids_by_role[role][sub] = src

    # Frames -> arrays of time/values per curve.
    frames = payload.get("frames") or []
    if not frames:
        raise ValueError("payload has no frames")

    film_back_mm = float(payload.get("film_back_mm", 36.0))
    # Flame's ``import_fbx`` default unit_to_pixels=10 expects FBX
    # Lcl Translation in units of 0.1*pixels (same as Flame's own
    # ``export_fbx`` default). Our writer mirrors that so the round-trip
    # through ``fbx_io.import_fbx_to_action`` lands at Flame-pixel scale.
    pos_scale = pixel_to_units

    times = [ktime_from_frame(int(kf["frame"]), frame_rate) for kf in frames]

    tx_vals = [float(kf["position"][0]) * pos_scale for kf in frames]
    ty_vals = [float(kf["position"][1]) * pos_scale for kf in frames]
    tz_vals = [float(kf["position"][2]) * pos_scale for kf in frames]

    rx_vals = [-float(kf["rotation_flame_euler"][0]) for kf in frames]
    ry_vals = [-float(kf["rotation_flame_euler"][1]) for kf in frames]
    rz_vals = [-float(kf["rotation_flame_euler"][2]) for kf in frames]

    fov_vals: list[float] = []
    for kf in frames:
        focal = float(kf["focal_mm"])
        if focal <= 0 or film_back_mm <= 0:
            fov_vals.append(40.0)
        else:
            fov_vals.append(
                math.degrees(2.0 * math.atan(film_back_mm / (2.0 * focal))))

    # Update Model's Properties70 for Lcl Translation + Lcl Rotation.
    # First frame's values become the static defaults; the AnimCurves
    # carry the per-frame variation. Flag "A+" marks them as animated.
    _set_property70(model, "Lcl Translation",
                    "Lcl Translation", "", "A+",
                    [tx_vals[0], ty_vals[0], tz_vals[0]])
    _set_property70(model, "Lcl Rotation",
                    "Lcl Rotation", "", "A+",
                    [rx_vals[0], ry_vals[0], rz_vals[0]])

    # Update NodeAttribute Properties70 for FilmWidth, FilmHeight,
    # FieldOfView. FilmHeight in inches is film_back_mm / 25.4. We pick
    # a reasonable FilmWidth using the payload's pixel aspect ratio.
    film_h_inch = film_back_mm / 25.4
    width = int(payload.get("width") or 0)
    height = int(payload.get("height") or 0)
    if width > 0 and height > 0:
        film_w_inch = film_h_inch * (width / height)
        aspect = width / height
    else:
        film_w_inch = film_h_inch * 1.5  # matches Flame's default 3:2 Super 16
        aspect = 1.5
    _set_property70(node_attr, "FilmWidth", "double", "Number", "", [film_w_inch])
    _set_property70(node_attr, "FilmHeight", "double", "Number", "", [film_h_inch])
    _set_property70(node_attr, "FilmAspectRatio", "double", "Number", "", [aspect])
    _set_property70(node_attr, "FieldOfView", "FieldOfView", "", "A+", [fov_vals[0]])

    # Replace every AnimationCurve in the tree whose ID matches a role
    # channel with a fresh curve derived from the frames.
    replacements: dict[int, FBXNode] = {}
    for role, ids in anim_curve_ids_by_role.items():
        if role == "T":
            for axis, vals in (("X", tx_vals), ("Y", ty_vals), ("Z", tz_vals)):
                cid = ids.get(axis)
                if cid is None:
                    continue
                replacements[cid] = _anim_curve_node_with_data(
                    cid, vals[0], times, vals)
        elif role == "R":
            for axis, vals in (("X", rx_vals), ("Y", ry_vals), ("Z", rz_vals)):
                cid = ids.get(axis)
                if cid is None:
                    continue
                replacements[cid] = _anim_curve_node_with_data(
                    cid, vals[0], times, vals)
        elif role == "FoV":
            # FoV sub-channel is "FieldOfView" (from "d|FieldOfView").
            cid = ids.get("FieldOfView")
            if cid is not None:
                replacements[cid] = _anim_curve_node_with_data(
                    cid, fov_vals[0], times, fov_vals)

    for i, child in enumerate(objects.children):
        if child.name == "AnimationCurve" and child.values:
            cid = _as_int(child.values[0])
            if cid in replacements:
                objects.children[i] = replacements[cid]

    # Also update the AnimCurveNode's Properties70 default values
    # (``d|X``, ``d|Y``, ``d|Z`` for T and R; ``d|FieldOfView`` for FoV).
    # Flame uses these as the value when no curve is connected; keeping
    # them aligned with frame 0 avoids cosmetic surprises in the UI.
    t_node = anim_node_ids.get(role_to_anim_id.get("T", -1))
    if t_node is not None:
        _set_property70(t_node, "d|X", "Number", "", "A", [tx_vals[0]])
        _set_property70(t_node, "d|Y", "Number", "", "A", [ty_vals[0]])
        _set_property70(t_node, "d|Z", "Number", "", "A", [tz_vals[0]])
    r_node = anim_node_ids.get(role_to_anim_id.get("R", -1))
    if r_node is not None:
        _set_property70(r_node, "d|X", "Number", "", "A", [rx_vals[0]])
        _set_property70(r_node, "d|Y", "Number", "", "A", [ry_vals[0]])
        _set_property70(r_node, "d|Z", "Number", "", "A", [rz_vals[0]])
    fov_node = anim_node_ids.get(role_to_anim_id.get("FoV", -1))
    if fov_node is not None:
        _set_property70(fov_node, "d|FieldOfView", "FieldOfView", "", "A",
                        [fov_vals[0]])

    # Update Takes::Take::LocalTime / ReferenceTime AND
    # GlobalSettings::TimeSpanStop to span the full animation range.
    #
    # Takes::LocalTime/ReferenceTime: the template hard-codes a single-frame
    # value (KTime for frame 1 at 23.976 fps). Flame's import_fbx clips any
    # keyframe with KTime > LocalTime end, so this must equal the KTime of
    # the last keyframe.
    #
    # GlobalSettings::TimeSpanStop: the template hard-codes 46186158000
    # (= frame 24 at 24 fps). For VFX-style shot ranges (e.g. frames
    # 1001–1024) ALL keyframe KTimes exceed this value. Flame uses
    # TimeSpanStop as a secondary clip boundary in addition to LocalTime:
    # keyframes with KTime > TimeSpanStop are silently dropped. Leaving it
    # stale causes every keyframe to be lost for shots beyond frame 24 at
    # 24 fps (the Blender→Flame round-trip arrives in Flame with no keys).
    # Setting it to last_ktime ensures it always covers the full payload.
    last_ktime = times[-1]  # times list was built above from payload frames
    takes_node = next((n for n in tree if n.name == "Takes"), None)
    if takes_node is not None:
        for take in takes_node.find_all("Take"):
            for child in take.children:
                if child.name in ("LocalTime", "ReferenceTime"):
                    # Values are [start_ktime, end_ktime]. Preserve start.
                    child.values = [child.values[0], last_ktime]
    global_settings = next((n for n in tree if n.name == "GlobalSettings"), None)
    if global_settings is not None:
        _set_property70(global_settings, "TimeSpanStop", "KTime", "Time", "",
                        [last_ktime])


def _payload_to_fbx(
    payload,
    out_fbx_path: str,
    *,
    camera_name: str,
    frame_rate: str,
    pixel_to_units: float,
) -> str:
    """Shared tail for the v5-JSON → FBX converter pair.

    Takes a pre-parsed v5 payload dict and runs the template-mutate +
    emit + write steps. Both ``v5_json_to_fbx`` (file-path input) and
    ``v5_json_str_to_fbx`` (string input) call this helper so the two
    public functions produce byte-identical FBX output for the same
    payload (Plan 02-02 D-01 guarantee).
    """
    tree = _load_template_tree()
    _mutate_template_with_payload(tree, payload, camera_name,
                                  frame_rate, pixel_to_units)

    text = emit_fbx_ascii(tree)

    out_abs = os.path.abspath(out_fbx_path)
    os.makedirs(os.path.dirname(out_abs) or ".", exist_ok=True)
    with open(out_abs, "w") as f:
        f.write(text)
    return out_abs


def v5_json_to_fbx(
    json_path: str,
    out_fbx_path: str,
    *,
    camera_name: str = "Camera",
    frame_rate: str = "23.976 fps",
    pixel_to_units: float = 0.1,
) -> str:
    """Convert a v5 JSON contract file to ASCII FBX that Flame's
    ``import_fbx`` accepts.

    Args:
        json_path: source v5 JSON (from ``tools/blender/extract_camera.py``
            or from another producer matching the contract).
        out_fbx_path: destination FBX path. Parent dir is created.
        camera_name: name to give the emitted camera. Flame's import
            will collide on duplicates and auto-rename to ``<name>1``,
            ``<name>2``, etc.
        frame_rate: FBX KTime conversion basis. Match what the downstream
            ``fbx_io.import_fbx_to_action`` call expects Flame's batch
            to be using.
        pixel_to_units: position divisor to write into FBX Lcl Translation.
            Default 0.1 matches Flame's own ``export_fbx`` default —
            pairs cleanly with our ``fbx_io.import_fbx_to_action``'s
            default ``unit_to_pixels=10.0`` so Flame-pixel coords round-trip.

    Returns the absolute path of the written FBX.
    """
    with open(json_path, "r") as f:
        payload = json.load(f)
    return _payload_to_fbx(payload, out_fbx_path,
                           camera_name=camera_name,
                           frame_rate=frame_rate,
                           pixel_to_units=pixel_to_units)


def v5_json_str_to_fbx(
    json_str: str,
    out_fbx_path: str,
    *,
    camera_name: str = "Camera",
    frame_rate: str = "23.976 fps",
    pixel_to_units: float = 0.1,
) -> str:
    """Convert an in-memory v5 JSON string to ASCII FBX.

    Sibling of :func:`v5_json_to_fbx`; shares the template-mutate
    emit path via :func:`_payload_to_fbx`. Used by the Blender
    "Send to Flame" addon via the forge-bridge payload so no
    intermediate JSON file is needed on the Flame side.

    Args:
        json_str: v5 JSON payload as a string (output of ``json.dumps``
            on the dict produced by
            ``forge_sender.flame_math.build_v5_payload``).
        out_fbx_path: destination FBX path. Parent dir is created.
        camera_name: name to give the emitted camera. Flame's import
            will collide on duplicates and auto-rename.
        frame_rate: FBX KTime conversion basis. Must be one of the
            keys in ``_FPS_FROM_FRAME_RATE`` (unknown strings silently
            fall back to 24 fps — the caller is responsible for
            supplying a valid key; see Phase 2 Plan 01 D-19: the
            Blender addon owns the frame-rate ladder and passes the
            resolved value here as a caller-provided kwarg).
        pixel_to_units: position divisor written into Lcl Translation.
            Default 0.1 pairs with ``fbx_io.import_fbx_to_action``'s
            default ``unit_to_pixels=10.0``.

    Returns the absolute path of the written FBX.
    """
    payload = json.loads(json_str)
    return _payload_to_fbx(payload, out_fbx_path,
                           camera_name=camera_name,
                           frame_rate=frame_rate,
                           pixel_to_units=pixel_to_units)
