# Phase 2: Blender Addon — Pattern Map

**Mapped:** 2026-04-21
**Files analyzed:** 8 (6 new, 2 modified)
**Analogs found:** 7 / 8 (one file — the Blender addon `__init__.py` / operator / panel surface — has **no in-repo analog**; see §"No Analog Found" below and §"Authoritative external references")

---

## File Classification

| New/Modified File | Change | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|--------|------|-----------|----------------|---------------|
| `tools/blender/forge_sender/__init__.py` | NEW | Blender addon entry (bl_info, register/unregister, Panel + Operator classes — or import from split modules per D-11) | bpy UI event → operator dispatch | **no in-repo analog** — first Blender addon in this repo. Closest adjacent: `tools/blender/bake_camera.py` (bpy script, shares module-docstring style + `bpy`/`mathutils` usage) | **partial** — adjacent bpy context only; addon scaffolding (`bl_info`, `register()`, `bpy.types.Panel`, `bpy.types.Operator`, `poll()`/`execute()`) is new surface. Planner MUST reference Blender docs via `mcp:context7` (`bpy.types.Panel`, `bpy.types.Operator`, `register_class`). |
| `tools/blender/forge_sender/flame_math.py` | NEW | Pure math helper (no bpy UI; only bpy / mathutils math types) | bpy camera data-block (matrix_world, data.lens, custom props) → v5 JSON dict (position / rotation_flame_euler / focal_mm + frames list) | `tools/blender/extract_camera.py:90-146, 154-164` — functions `_rot3_to_flame_euler_deg`, `_R_Z2Y`, `_camera_keyframe_set`, `_resolve_scale`, and the frame-walk body of `_extract` | **exact** — D-04 says the math MOVES from `extract_camera.py` into this module. Lift-and-shift with `from __future__ import annotations`. |
| `tools/blender/forge_sender/transport.py` | NEW | HTTP client; JSON payload builder + bridge-response envelope parser | v5 JSON dict (in-memory) → POST body → dict envelope (`result`, `error`, `traceback`) | **no direct in-repo analog** for HTTP-client role. Adjacent: `forge_flame/blender_bridge.py:156-210` (`build_bake_cmd` / `build_extract_cmd` — same "compose args, then call runner" split that makes transport unit-testable without the network). | **role-match** — subprocess → HTTP swap. Mirror the "pure payload builder + thin caller" split so tests can assert payload shape without mocking `requests`. |
| `tools/blender/forge_sender/preflight.py` | NEW | Pure validator returning `Optional[str]` error message | `bpy.context` → `None` (pass) or one of four D-09 Tier 1 strings | `forge_flame/fbx_io.py:51-70` (`iter_keyframable_cameras`) — duck-typed attribute checks that must stay testable outside Flame. Applied here as duck-typed checks on `context.active_object` + `obj.data.get("forge_bake_source")`. | **role-match** — same "validate by hasattr / dict.get, return early" shape. |
| `tools/blender/forge_sender/operator.py` (optional per D-11; may live in `__init__.py`) | NEW | `bpy.types.Operator` subclass (`FORGE_OT_send_to_flame`, `bl_idname="forge.send_to_flame"`) | button click → `poll()` → `execute()` → preflight → transport → popup | **no in-repo analog**. External: Blender docs for `bpy.types.Operator`, `self.report()`, `bpy.ops.wm.popup_menu`. | **no match** — new surface. |
| `tools/blender/forge_sender/panel.py` (optional per D-11; may live in `__init__.py`) | NEW | `bpy.types.Panel` subclass (`VIEW3D_PT_forge_sender`) | draw() → `layout.label` / `layout.operator` rows per UI-SPEC | **no in-repo analog**. External: Blender docs for `bpy.types.Panel`, `layout.label`, `layout.operator`, `row.alert`. | **no match** — new surface. |
| `forge_flame/fbx_ascii.py` (ADD `v5_json_str_to_fbx`) | MODIFY | Pure converter (no Flame, no Blender) | in-memory JSON string → ASCII FBX file | `forge_flame/fbx_ascii.py:1230-1271` — existing `v5_json_to_fbx(json_path, ...)` | **exact** — new sibling; everything below `json.loads(...)` is reused verbatim from the file variant. |
| `tools/blender/extract_camera.py` | MODIFY | Blender CLI script (subprocess entrypoint) | unchanged CLI surface; math imports from `forge_sender/flame_math.py` | self (pre-refactor) — the file that loses the math body | **exact** — D-05 lift-and-shift with a `sys.path.insert` shim at top-of-file. |
| `tests/test_forge_sender_flame_math.py` (NEW) | NEW | Test module | importable `forge_sender.flame_math` symbols → numpy-parallel round-trip assertions | `tests/test_blender_roundtrip.py` (numpy parallel implementation of the same math) + `tests/test_fbx_io.py` (duck-typed Flame fakes) | **exact** for round-trip; **role-match** for fakes if bpy shim is needed. |
| `tests/test_forge_sender_transport.py` (NEW) | NEW | Test module | build-payload / parse-envelope pure funcs → assertions (no live HTTP) | `tests/test_blender_bridge.py:187-288` — `TestBuildBakeCmd` / `TestBuildExtractCmd` (pure argv composition tests that never launch Blender) | **exact** — apply the same "pure builder + test the shape" pattern to HTTP payload. |
| `tests/test_forge_sender_preflight.py` (NEW) | NEW | Test module | fake bpy context → `None` or Tier 1 copy string | `tests/test_fbx_io.py:49-80` — `_Attr` / `_Camera` duck-typed fakes | **role-match** — apply the same fakes pattern to `context.active_object` / `obj.data`. |
| `tests/test_v5_json_str_to_fbx.py` or extend `tests/test_fbx_ascii.py` (NEW / EXTEND) | NEW or MODIFY | Test module | JSON string → FBX file → parse back → assertions | `tests/test_fbx_ascii.py::TestPublicAPI` (L420+) and the existing `v5_json_to_fbx` round-trip assertions | **exact** — extend `TestPublicAPI` with a `test_v5_json_str_to_fbx_equivalent_to_file_variant` case. |

**Note on scope:**
- `tools/blender/bake_camera.py` is **unchanged** — stamped metadata contract (CONTEXT §Integration Points) is already sufficient.
- `flame/camera_match_hook.py` is **unchanged** — D-17 frame-rate strategy avoids revisiting Phase 1.
- `forge_flame/fbx_io.py::import_fbx_to_action` is **called unchanged** on the Flame side of the bridge payload (D-06 / D-07 resolution happens BEFORE this call).

---

## Pattern Assignments

### 1. `forge_flame/fbx_ascii.v5_json_str_to_fbx` (NEW sibling, D-01)

**File:** `forge_flame/fbx_ascii.py` — add a new function **adjacent to** `v5_json_to_fbx` (currently at `forge_flame/fbx_ascii.py:1230`).
**Role:** pure converter.
**Analog:** the file-path variant itself — **share everything below `json.loads(...)`**.

#### 1.1 Analog: `v5_json_to_fbx` (verbatim, `forge_flame/fbx_ascii.py:1230-1271`)

```python
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

    tree = _load_template_tree()
    _mutate_template_with_payload(tree, payload, camera_name,
                                  frame_rate, pixel_to_units)

    text = emit_fbx_ascii(tree)

    out_abs = os.path.abspath(out_fbx_path)
    os.makedirs(os.path.dirname(out_abs) or ".", exist_ok=True)
    with open(out_abs, "w") as f:
        f.write(text)
    return out_abs
```

#### 1.2 Pattern to copy

The new sibling **replaces only** lines 1258–1259 (`with open(json_path) ... payload = json.load(f)`) with `payload = json.loads(json_str)`. Everything else is identical. Recommended surgery: extract the common tail into a `_payload_to_fbx(payload, out_fbx_path, *, camera_name, frame_rate, pixel_to_units)` private helper, and make both public functions a thin wrapper. This is additive (doesn't change `v5_json_to_fbx`'s signature or behavior) and honors the Phase 1 convention of "one converter, two input shapes".

**Signature (per D-01):**

```python
def v5_json_str_to_fbx(
    json_str: str,
    out_fbx_path: str,
    *,
    camera_name: str = "Camera",
    frame_rate: str = "23.976 fps",
    pixel_to_units: float = 0.1,
) -> str:
    """Convert an in-memory v5 JSON string to ASCII FBX (sibling of
    ``v5_json_to_fbx``). Shares the template-mutate emit path.
    """
    payload = json.loads(json_str)
    # ... same as v5_json_to_fbx from here ...
```

#### 1.3 Gotchas / reuse constraints

- **Do NOT touch `v5_json_to_fbx`'s signature or docstring.** CLI consumers (`roundtrip_selftest.sh`, `extract_camera.py`'s downstream tooling, hook's `_import_camera_from_blender`) expect the file-path form. Additive only.
- **Frame-rate string contract (`forge_flame/fbx_ascii.py:57-69`):** `frame_rate` must be one of the keys in `_FPS_FROM_FRAME_RATE` — unknown strings silently fall back to 24.0 fps (`ktime_per_frame`). The bridge-side probe (D-18) must confirm `flame.batch.frame_rate.get_value()` returns one of these keys **before** the implementation task runs; if it returns a float or an unsupported string, D-19's contingency (stamp `forge_bake_frame_rate` in Phase 1) triggers.
- **Imports at the top of `fbx_ascii.py` already cover `json` + `os`** (line 38, 40). No new imports required for the sibling.

---

### 2. `tools/blender/forge_sender/flame_math.py` (NEW, D-04)

**File:** `tools/blender/forge_sender/flame_math.py`
**Role:** shared Euler / axis-swap / keyframe-walk math — **no bpy UI, no HTTP, no JSON I/O**; only imports `bpy` + `mathutils` for types (same way `extract_camera.py` does today).
**Analog:** `tools/blender/extract_camera.py:90-146, 154-164` — lift-and-shift.

#### 2.1 Analog: `_rot3_to_flame_euler_deg` (`tools/blender/extract_camera.py:90-111`)

```python
def _rot3_to_flame_euler_deg(R) -> tuple:
    """Decompose a 3x3 cam-to-world rotation into Flame's Euler triple.

    Flame composes rotations as R = Rz(rz) · Ry(-ry) · Rx(-rx). This is
    the matching inverse decomposition. Must stay numerically identical
    to forge_core.math.rotations.compute_flame_euler_zyx — if you change
    one, change both and run tests/test_blender_roundtrip.py.

    Handles gimbal lock (ry ≈ ±90°) by pinning rx=0 and recovering rz
    from the remaining 2x2 block."""
    # mathutils 3x3 Matrix indexes as [row][col]. Keep aligned with numpy.
    cb = math.sqrt(R[0][0] ** 2 + R[1][0] ** 2)
    gimbal = cb <= 1e-6
    if not gimbal:
        rx = -math.atan2(R[2][1], R[2][2])
        ry = -math.asin(-R[2][0])
        rz =  math.atan2(R[1][0], R[0][0])
    else:
        rx = 0.0
        ry = -math.asin(-R[2][0])
        rz =  math.atan2(-R[0][1], R[1][1])
    return (math.degrees(rx), math.degrees(ry), math.degrees(rz))
```

#### 2.2 Analog: axis-swap matrix (`tools/blender/extract_camera.py:114-116`)

```python
# Blender world (Z-up) -> Flame world (Y-up). Inverse of the bake step.
# Transpose of Rx(+90°) is Rx(-90°).
_R_Z2Y = Matrix.Rotation(math.radians(90), 4, 'X').transposed()
```

#### 2.3 Analog: `_camera_keyframe_set` (`tools/blender/extract_camera.py:124-146`)

```python
def _camera_keyframe_set(cam: bpy.types.Object) -> list:
    """Return a sorted list of unique integer frame numbers on which the
    camera (object or its data) has any keyframe.

    Walks both the object-level action (location/rotation/scale) and the
    camera-data-level action (lens, sensor, etc.) because we keyframe
    both in bake_camera.py. Falls back to the scene's current frame if
    no animation data is present (single static bake)."""
    frames = set()

    def _drain(anim):
        if anim is None or anim.action is None:
            return
        for fcurve in anim.action.fcurves:
            for kp in fcurve.keyframe_points:
                frames.add(int(round(kp.co[0])))

    _drain(cam.animation_data)
    _drain(cam.data.animation_data)

    if not frames:
        frames.add(int(bpy.context.scene.frame_current))
    return sorted(frames)
```

#### 2.4 Analog: `_resolve_scale` (`tools/blender/extract_camera.py:154-164`)

```python
def _resolve_scale(cam: bpy.types.Object, cli_override) -> float:
    """CLI override wins; otherwise read the stamped metadata; otherwise 1.0."""
    if cli_override is not None:
        return float(cli_override)
    stamped = cam.data.get("forge_bake_scale")
    if stamped is None:
        print("extract_camera: warning — no forge_bake_scale metadata on "
              f"{cam.name!r}, defaulting to 1.0. Pass --scale if this .blend "
              "came from a non-default bake.", file=sys.stderr)
        return 1.0
    return float(stamped)
```

#### 2.5 Analog: frame-walk body (`tools/blender/extract_camera.py:177-214`)

The loop that produces the `frames_out` list + the final `out = {...}` dict. This is the payload-building core — the addon's operator calls this directly, then serializes with `json.dumps()` before POSTing (D-02).

```python
scale = _resolve_scale(cam, args.scale)
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

out = {
    "width":        int(scene.render.resolution_x),
    "height":       int(scene.render.resolution_y),
    # film_back_mm is the VERTICAL sensor dimension in our contract;
    # bake writes it to sensor_height with sensor_fit='VERTICAL'. Read
    # sensor_height here to stay consistent (sensor_width would be
    # Blender's auto-derived horizontal value, a different number).
    "film_back_mm": float(cam.data.sensor_height),
    "frames":       frames_out,
}
```

#### 2.6 Pattern to copy for `flame_math.py`

1. Module docstring in the repo's established style (see `forge_flame/fbx_ascii.py:1-34` or `tools/blender/extract_camera.py:1-47`): open with "Why this module exists" paragraph, scope boundaries, cross-references to `memory/flame_rotation_convention.md`.
2. `from __future__ import annotations` at top (CLAUDE.md §Code Style convention).
3. Imports: `import math`, `import sys`, `import bpy`, `from mathutils import Matrix`.
4. Copy the four private helpers verbatim. **Keep the underscore prefix** — these are module-private; the addon and `extract_camera.py` reach in by name.
5. Add a public `build_v5_payload(cam, scale_override=None) -> dict` function that wraps the frame-walk body and returns the `out` dict (**no JSON I/O**). Both the addon operator and `extract_camera.py` call this; `extract_camera.py` then does `json.dump(build_v5_payload(cam, args.scale), f, indent=2)`; the addon does `json.dumps(build_v5_payload(cam))` and POSTs.

#### 2.7 Gotchas (carry-overs the planner must preserve)

- **Round-trip parity:** per module docstring at `tools/blender/extract_camera.py:29-33` and `bake_camera.py:51-56`, the Flame Euler math MUST stay numerically identical to `forge_core.math.rotations.compute_flame_euler_zyx`. If the planner touches either, run `tests/test_blender_roundtrip.py`.
- **Gimbal-lock tolerance `1e-6`** (CLAUDE.md §Numeric Precision) — do not adjust.
- **`sensor_fit='VERTICAL'` is pinned by bake** (`tools/blender/bake_camera.py:230`); `extract_camera.py` reads `sensor_height` to match. Preserve the same read in `flame_math.py`.

---

### 3. `tools/blender/extract_camera.py` refactor (MODIFY, D-05)

**File:** `tools/blender/extract_camera.py`
**Role:** unchanged — Blender CLI script (subprocess entrypoint for the existing `forge_flame/blender_bridge.run_extract` path).
**Analog:** itself (pre-refactor). The change is a lift-and-shift of the math into `flame_math.py`, nothing else.

#### 3.1 Pattern to copy (D-05 verbatim)

Add at the top of `extract_camera.py`, after the `import` block:

```python
# D-05: share math with the Blender "Send to Flame" addon.
# forge_sender/ is a sibling directory shipped alongside this script.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "forge_sender"))

from flame_math import (  # noqa: E402
    _rot3_to_flame_euler_deg,
    _R_Z2Y,
    _camera_keyframe_set,
    _resolve_scale,
    build_v5_payload,   # if the planner extracts the frame-walk into a public helper
)
```

Then **delete** the corresponding definitions from `extract_camera.py` (lines 90-146, 154-164) and replace the `_extract` body's frame-walk section with a call to `build_v5_payload(cam, args.scale)`.

#### 3.2 Gotchas

- **`noqa: E402`** is the CLAUDE.md convention for imports after sys.path manipulation — see `tests/test_blender_bridge.py:24-32` for the established shape.
- **Argparse surface is frozen** (same CLI flags: `--out`, `--camera-name`, `--scale`). `forge_flame/blender_bridge.build_extract_cmd` (L188-210) constructs these flags and its unit tests (`tests/test_blender_bridge.py::TestBuildExtractCmd`) would catch any drift.
- **`scale_override` parameter** on `build_v5_payload` maps 1:1 to the current CLI `--scale` flag. `extract_camera.py` passes `args.scale`; the addon passes `None` (reads the stamped `forge_bake_scale` on `cam.data` via `_resolve_scale`).
- **All tests must still pass** after the move (CONTEXT.md D-05 literal requirement). `tests/test_blender_roundtrip.py` is the guardrail.

---

### 4. `tools/blender/forge_sender/preflight.py` (NEW, D-09 Tier 1)

**File:** `tools/blender/forge_sender/preflight.py`
**Role:** pure validator.
**Analog:** `forge_flame/fbx_io.py:51-70` — `iter_keyframable_cameras` duck-typed attribute filter.

#### 4.1 Analog: duck-typed validation (`forge_flame/fbx_io.py:63-70`)

```python
def iter_keyframable_cameras(action) -> list:
    """... excludes non-cameras and the built-in Perspective camera.

    Detection is by duck-typing (``position`` + ``rotation`` + ``fov`` +
    ``focal`` PyAttributes) rather than ``isinstance(flame.PyCoNode)``,
    so this function is unit-testable from outside Flame."""
    out = []
    for n in action.nodes:
        if not all(hasattr(n, attr) for attr in ("position", "rotation", "fov", "focal")):
            continue
        if n.name.get_value() == "Perspective":
            continue
        out.append(n)
    return out
```

#### 4.2 Pattern to copy

```python
# tools/blender/forge_sender/preflight.py
from __future__ import annotations

from typing import Optional


# Keys to check in priority order. The first missing key wins the error
# popup (UI-SPEC §Preflight Tier 1 — "missing_key" substitution rule).
_REQUIRED_STAMPED_KEYS = ("forge_bake_action_name", "forge_bake_camera_name")


def check(context) -> Optional[str]:
    """Validate that `context.active_object` is a forge-baked camera
    ready for send. Returns None on pass, or one of the four D-09
    Tier 1 copy strings on fail (see UI-SPEC §Copywriting Contract).

    Duck-typed: does not import bpy; accepts any object exposing
    `.active_object` with `.type` + `.data` (dict-like on the data-block).
    This keeps the function unit-testable with a plain fake.
    """
    obj = getattr(context, "active_object", None)
    if obj is None:
        return "Send to Flame: no active object — select a forge-baked camera in the 3D viewport and try again"

    if getattr(obj, "type", None) != "CAMERA":
        return "Send to Flame: active object is not a camera — select a forge-baked camera in the 3D viewport and try again"

    data = obj.data
    for key in _REQUIRED_STAMPED_KEYS:
        if key not in data:
            return (f"Send to Flame: active camera is missing '{key}' — "
                    f"this camera was not baked by forge-calibrator. "
                    f"Re-export from Flame via right-click → Camera Match → Export Camera to Blender")

    if data.get("forge_bake_source") != "flame":
        return ("Send to Flame: active camera was not baked by forge-calibrator "
                "(forge_bake_source != 'flame') — re-export from Flame via "
                "right-click → Camera Match → Export Camera to Blender")

    return None
```

#### 4.3 Gotchas

- **Copy strings are UI-SPEC literal** — the planner/executor MUST NOT reword. UI-SPEC §Copywriting Contract fixes them; any drift breaks downstream tests that assert on the strings.
- **Return the FIRST missing key** only — UI-SPEC §Preflight Tier 1 "`{missing_key}` substitution rule": "If both are missing, name only the first." The `_REQUIRED_STAMPED_KEYS` tuple order is the priority order.
- **Operator `poll()` and `execute()` both call this** per UI-SPEC §Panel Layout Contract — "belt-and-braces": `poll()` gates the button; `execute()` re-checks so F3-search / keymap invocation can't bypass. `poll()` ignores the return string and uses only `result is None`; `execute()` surfaces the string in the popup.
- **Provenance guard (D-09 Tier 1d)** is `forge_bake_source != "flame"`, **not** just "key missing". This catches tampered / hand-edited `.blend` files where a user set only the two names but not the source stamp. `tools/blender/bake_camera.py:199` is what writes `forge_bake_source = "flame"`.

---

### 5. `tools/blender/forge_sender/transport.py` (NEW, D-02, D-03, D-16)

**File:** `tools/blender/forge_sender/transport.py`
**Role:** HTTP client + payload builder + response-envelope parser.
**Analog:** `forge_flame/blender_bridge.py:156-210` — `build_bake_cmd` / `build_extract_cmd`. Same pure-builder + thin-runner split, but the transport here is HTTP (`requests.post`) not `subprocess.run`.

#### 5.1 Analog: pure builder + thin runner split (`forge_flame/blender_bridge.py:156-252`)

```python
def build_bake_cmd(
    json_path: str,
    blend_path: str,
    *,
    camera_name: str = "Camera",
    scale: float = 1000.0,
    create_if_missing: bool = True,
    blender_bin: Optional[str] = None,
    bake_script: Optional[str] = None,
) -> List[str]:
    """Compose the argv list for a Blender bake invocation.

    Split from run_bake so tests can assert the command shape without
    actually running Blender. The blender_bin and bake_script kwargs
    exist to let tests inject fake paths."""
    # ... pure list composition ...


def run_bake(
    json_path: str,
    blend_path: str,
    *,
    camera_name: str = "Camera",
    scale: float = 1000.0,
    create_if_missing: bool = True,
) -> subprocess.CompletedProcess:
    """Run bake_camera.py through Blender. ..."""
    cmd = build_bake_cmd(...)
    return subprocess.run(cmd, check=True, capture_output=True, text=True)
```

#### 5.2 Pattern to copy (apply the split to HTTP)

```python
# tools/blender/forge_sender/transport.py
from __future__ import annotations

import json
from typing import Optional, Tuple

import requests  # D-13: bundled with Blender 4.5's Python


BRIDGE_URL = "http://127.0.0.1:9999/exec"  # UI-SPEC §Transport Tier literal
DEFAULT_TIMEOUT_S = 5.0                     # D-16; bump to 10 s if live validation demands


def build_payload(v5_json_str: str) -> dict:
    """Compose the bridge `{"code": "<python>"}` body.

    Split from `send` so tests can assert the embedded-code shape without
    actually hitting the bridge. The Flame-side Python runs:
        1. tempfile.mkdtemp(prefix="forge_send_")       # D-03
        2. v5_json_str_to_fbx(json_str, fbx_path,
               frame_rate=flame.batch.frame_rate.get_value())  # D-17
        3. Resolve Action by name in flame.batch (D-06/D-07)
        4. import_fbx_to_action(action, fbx_path)       # unchanged from
                                                        # forge_flame.fbx_io
        5. On success: remove tempdir, return created camera name(s) + action_name
        6. On failure: leave tempdir, raise with path in message (D-03)
    """
    # Claude's Discretion (CONTEXT §Claude's Discretion bullet 2):
    # embed the JSON payload as a Python string literal inside `code`.
    # `repr(v5_json_str)` is the safe escape (handles newlines, quotes).
    code = _FLAME_SIDE_TEMPLATE.format(json_str_repr=repr(v5_json_str))
    return {"code": code}


def send(v5_json_str: str, *, timeout: float = DEFAULT_TIMEOUT_S) -> dict:
    """POST the v5 JSON payload to forge-bridge and return the response
    envelope dict.

    Raises:
        requests.exceptions.ConnectionError, requests.exceptions.Timeout
            on transport failures (surface as UI-SPEC §Transport Tier).
    """
    payload = build_payload(v5_json_str)
    response = requests.post(BRIDGE_URL, json=payload, timeout=timeout)
    response.raise_for_status()
    return response.json()


def parse_envelope(envelope: dict) -> Tuple[Optional[str], Optional[dict]]:
    """Split a bridge response envelope into (error_message, success_payload).

    Envelope shape per `memory/flame_bridge.md`:
        {"result": ..., "stdout": ..., "stderr": ..., "error": ..., "traceback": ...}

    Returns:
        (None, result_dict) on success (`error` field absent / empty);
        (formatted_error_string, None) on remote failure (D-09 Tier 3).
    """
    error = envelope.get("error")
    if error:
        traceback = envelope.get("traceback") or ""
        # UI-SPEC §Remote Tier copy template: "Send to Flame failed: {error}\n\n{traceback}"
        return (f"Send to Flame failed: {error}\n\n{traceback}", None)
    return (None, envelope.get("result"))
```

#### 5.3 Flame-side code template (embedded inside `code`)

The bridge receives one Python string. That string does the Flame-side work (D-17 frame-rate probe, D-06/D-07 Action resolution, D-03 tempdir). Sketch for the planner — **exact wording is Claude's Discretion per CONTEXT**, only the behavior is locked:

```python
_FLAME_SIDE_TEMPLATE = '''
import flame
import os
import shutil
import tempfile

from forge_flame import fbx_ascii, fbx_io

def _run():
    v5_json_str = {json_str_repr}

    # D-03 tempdir — preserve on failure, remove on success.
    tmpdir = tempfile.mkdtemp(prefix="forge_send_")
    fbx_path = os.path.join(tmpdir, "incoming.fbx")
    success = False
    try:
        # D-17: query frame rate at import time.
        frame_rate = flame.batch.frame_rate.get_value()

        # D-01 new sibling — in-memory JSON → ASCII FBX.
        fbx_ascii.v5_json_str_to_fbx(
            v5_json_str, fbx_path, frame_rate=frame_rate,
        )

        # Pull the stamped target-Action name out of the payload.
        import json
        payload = json.loads(v5_json_str)
        action_name = payload["custom_properties"]["forge_bake_action_name"]

        # D-06 / D-07: scoped to current batch, duck-typed, fail-loud.
        matches = [n for n in flame.batch.nodes
                   if hasattr(n, "import_fbx") and n.name.get_value() == action_name]
        if not matches:
            raise RuntimeError(
                f"No Action named '{{action_name}}' in current batch — "
                f"was it renamed or deleted?")
        if len(matches) > 1:
            raise RuntimeError(
                f"Ambiguous: {{len(matches)}} Actions named '{{action_name}}' — "
                f"rename to disambiguate and resend")
        action = matches[0]

        created = fbx_io.import_fbx_to_action(action, fbx_path)

        success = True
        return {{
            "action_name": action_name,
            "created": [c.name.get_value() for c in created],
        }}
    finally:
        if success:
            shutil.rmtree(tmpdir, ignore_errors=True)
        else:
            # D-03: leave tmpdir alive; include path in any exception
            # the caller's traceback will carry. We log stderr-ish here
            # so the bridge `stderr` captures it.
            print(f"[forge-send] tempdir preserved: {{tmpdir}}")

_result = _run()
'''.strip()
```

**Planner note on code-embedding strategy (CONTEXT §Claude's Discretion bullet 2):** the recommendation is to inline the JSON via `repr(json_str)` inside the `code` string as shown. Alternative (bridge-exposed payload context) only makes sense if the bridge is extended — out of scope for this phase. `repr()` covers escaping cleanly; Python string literals are the canonical Flame-side test pattern.

#### 5.4 Gotchas

- **Bridge payload contract (`memory/flame_bridge_probing.md`, 2026-04-19 update):** `POST /exec` with JSON body `{"code": "<py>"}`, returns `{"result", "stdout", "stderr", "error", "traceback"}`. Older raw-body form is superseded — do NOT emit `data=code`; use `json=payload`.
- **Timeout (D-16):** 5 s is the default. CONTEXT §Claude's Discretion bullet 4 allows bumping to 10 s if live validation shows p99 > 3 s.
- **`requests` is bundled with Blender 4.5** (D-13). No `pip install` inside Blender — artists install the addon via Preferences; they MUST NOT be asked to touch Blender's site-packages.
- **Urllib fallback (D-13):** only triggered if a future Blender bundle drops `requests`. Not a v1 concern.
- **One probe per request (`flame_bridge_probing.md`):** the D-18 frame-rate probe task MUST be one isolated `import flame; print(flame.batch.frame_rate.get_value())` call, not bundled with other introspection. **Ping first** (`print(2+2)`) before the real probe.

---

### 6. `tools/blender/forge_sender/__init__.py` (+ optional `operator.py`, `panel.py`) (NEW, D-11)

**File:** `tools/blender/forge_sender/__init__.py` — addon entry.
**Role:** Blender addon registration surface + UI.
**Analog:** **none in this repo**. Adjacent bpy context: `tools/blender/bake_camera.py` / `extract_camera.py` (share the `bpy` + `mathutils` import style, module-docstring convention, and sys.argv handling idiom — but those are CLI scripts, not addons).

#### 6.1 What the planner MUST reference (no in-repo analog)

For the addon-specific scaffolding — `bl_info`, `register()`/`unregister()`, `bpy.types.Panel`, `bpy.types.Operator`, `self.report()`, `bpy.ops.wm.popup_menu`, `layout.label` / `layout.operator` / `row.alert` — the planner must consult **Blender 4.5 Python API docs** (via `mcp:context7` for `bpy.types.Panel`, `bpy.types.Operator`, `bpy.utils.register_class`) or the official Blender docs.

The UI-SPEC §Panel Layout Contract and §Copywriting Contract already pin every exact string and layout call that lands in the panel/operator; the scaffold is what needs external reference.

#### 6.2 Pattern to copy from `bake_camera.py` (adjacent bpy conventions)

**Module docstring convention** (`tools/blender/bake_camera.py:1-56`):

```python
"""
bake_camera.py — Flame camera JSON -> Blender .blend

Runs *inside* Blender via the CLI:
    ...

JSON contract (see PASSOFF.md v5 "Data contract"):
    ...

Conventions:
  - Flame world is Y-up, 1 unit ≈ 1 image pixel. Blender world is Z-up.
    ...
"""
```

Apply the same "why this module exists" + "conventions" + "gotchas" shape to the addon's `__init__.py` docstring. Cross-reference `memory/flame_rotation_convention.md` (Flame Euler ZYX) if `flame_math.py` is imported, and the UI-SPEC for copywriting.

**Import style** (`tools/blender/bake_camera.py:58-66`):

```python
from __future__ import annotations   # NB: bake_camera.py does NOT currently use this;
                                     # CLAUDE.md §Code Style says "at top of every module file"
                                     # — the addon should FOLLOW the repo rule, not the legacy script.

import argparse
import json
import math
import os
import sys
from typing import Optional

import bpy
from mathutils import Matrix
```

Group stdlib first, then third-party (`bpy`, `mathutils`, `requests`), then local relative imports (`.flame_math`, `.transport`, `.preflight`). Matches CLAUDE.md §Import Organization.

**Class naming (UI-SPEC §Component Inventory + §Naming pattern):**
- Panel: `VIEW3D_PT_forge_sender(bpy.types.Panel)` — pattern `{SPACE}_PT_{unique}`.
- Operator: `FORGE_OT_send_to_flame(bpy.types.Operator)` with `bl_idname="forge.send_to_flame"`.

#### 6.3 `bl_info` block (D-11 exact values)

```python
bl_info = {
    "name": "Forge: Send Camera to Flame",
    "author": "forge-calibrator",
    "version": (1, 0, 0),
    "blender": (4, 5, 0),
    "location": "View3D > Sidebar > Forge",
    "description": "Send the active Flame-baked camera back to its source Action in Flame.",
    "category": "Import-Export",
}
```

#### 6.4 `register()` / `unregister()` pattern

```python
_CLASSES = (FORGE_OT_send_to_flame, VIEW3D_PT_forge_sender)


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
```

Standard Blender idiom — `context7` will corroborate.

#### 6.5 Operator `poll()` + `execute()` shape (UI-SPEC §Panel Layout Contract)

```python
class FORGE_OT_send_to_flame(bpy.types.Operator):
    bl_idname = "forge.send_to_flame"
    bl_label = "Send to Flame"
    bl_description = "Send the active Flame-baked camera to its source Action"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return preflight.check(context) is None

    def execute(self, context):
        # Belt-and-braces re-check (UI-SPEC §Panel Layout Contract)
        err = preflight.check(context)
        if err is not None:
            self.report({'ERROR'}, err)
            _popup(context, err)
            return {'CANCELLED'}

        cam = context.active_object
        payload_dict = flame_math.build_v5_payload(cam)
        # Stamp metadata carried forward from bake (custom_properties
        # round-trip — the Flame side reads forge_bake_action_name from here).
        payload_dict["custom_properties"] = {
            "forge_bake_action_name": cam.data["forge_bake_action_name"],
            "forge_bake_camera_name": cam.data["forge_bake_camera_name"],
        }
        v5_json_str = json.dumps(payload_dict)

        try:
            envelope = transport.send(v5_json_str)
        except (requests.exceptions.ConnectionError,
                requests.exceptions.Timeout) as e:
            msg = ("Send to Flame: forge-bridge not reachable at "
                   "http://127.0.0.1:9999 — is Flame running with the "
                   "Camera Match hook loaded?")
            self.report({'ERROR'}, msg)
            _popup(context, msg)
            return {'CANCELLED'}

        err, result = transport.parse_envelope(envelope)
        if err is not None:
            self.report({'ERROR'}, err)
            _popup_multiline(context, err)
            return {'CANCELLED'}

        # D-10 success popup
        action_name = result["action_name"]
        created = result["created"]
        if len(created) == 1:
            msg = f"Sent to Flame: camera '{created[0]}' in Action '{action_name}'"
        else:
            joined = ", ".join(f"'{n}'" for n in created)
            msg = f"Sent to Flame: cameras {joined} in Action '{action_name}'"
        self.report({'INFO'}, msg)
        _popup(context, msg, level='INFO')
        return {'FINISHED'}
```

#### 6.6 Panel `draw()` shape (UI-SPEC §Panel Layout Contract)

```python
class VIEW3D_PT_forge_sender(bpy.types.Panel):
    bl_label = "Send to Flame"
    bl_idname = "VIEW3D_PT_forge_sender"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Forge"
    bl_order = 0

    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        preflight_error = preflight.check(context)

        if preflight_error is None:
            # Happy path — UI-SPEC §Row order (valid camera)
            cam_data = obj.data
            layout.label(
                text=f"Target Action: {cam_data['forge_bake_action_name']}",
                icon='OUTLINER_OB_CAMERA')
            layout.label(
                text=f"Target Camera: {cam_data['forge_bake_camera_name']}",
                icon='CAMERA_DATA')
            layout.separator()
            layout.operator("forge.send_to_flame", icon='EXPORT')
        else:
            # Disabled state — UI-SPEC §Row order (preflight Tier 1 failure)
            row = layout.row()
            row.alert = True
            row.label(text="Not a Flame-baked camera", icon='ERROR')
            layout.separator()
            layout.operator("forge.send_to_flame", icon='EXPORT')  # poll() disables
```

#### 6.7 Popup helpers

Two helpers — single-line (preflight + transport) and multi-line (remote tier with traceback, UI-SPEC §Remote Tier "copy-paste-friendly"). Both use `bpy.context.window_manager.popup_menu`:

```python
def _popup(context, message: str, *, title: str = "Send to Flame", level: str = 'ERROR'):
    """Single-line popup via wm.popup_menu."""
    def draw(self, _ctx):
        self.layout.label(text=message)
    icon = 'INFO' if level == 'INFO' else 'ERROR'
    context.window_manager.popup_menu(draw, title=title, icon=icon)


def _popup_multiline(context, message: str, *, title: str = "Send to Flame"):
    """Multi-line popup — one layout.label per line so pipeline-TDs
    can screenshot/copy the traceback verbatim (UI-SPEC §Remote Tier).
    Preserves whitespace; does NOT reflow."""
    lines = message.split("\n")
    def draw(self, _ctx):
        for line in lines:
            self.layout.label(text=line)
    context.window_manager.popup_menu(draw, title=title, icon='ERROR')
```

#### 6.8 Gotchas

- **D-11: directory package**, not a single `.py` — `__init__.py` + siblings. `bl_info` lives in `__init__.py`.
- **D-12: zip by shell command**, NOT via `install.sh`. The planner must NOT add the addon to `install.sh` — CONTEXT explicitly forbids it (violates the Flame-side-only contract of `install.sh`).
- **Claude's Discretion (D-11):** operator and panel classes MAY live in `__init__.py` OR split into `operator.py` / `panel.py`. Recommendation: keep them in `__init__.py` for v1 — the whole addon is < 200 LOC and a split adds import ceremony without payoff.
- **Custom-properties round-trip:** the extract math builds `out` with only `width`/`height`/`film_back_mm`/`frames`; the operator MUST inject `custom_properties` into the dict before `json.dumps()` (Phase 1 D-10 contract — the Flame side reads `forge_bake_action_name` from there for D-06 target-Action resolution). This is the step that closes the round-trip.

---

### 7. Test patterns (NEW test files)

**Files:**
- `tests/test_forge_sender_flame_math.py`
- `tests/test_forge_sender_transport.py`
- `tests/test_forge_sender_preflight.py`
- Extension to `tests/test_fbx_ascii.py` for `v5_json_str_to_fbx`

**Role:** pytest unit tests, no live Blender, no live Flame, no live bridge.

#### 7.1 Analog: sys.path shim + noqa (`tests/test_fbx_io.py:28-41`, `tests/test_blender_bridge.py:17-32`)

```python
"""Unit tests for forge_flame.fbx_io.

What we test:
  1. ...
  2. ...

What we don't test:
  - Subprocess execution itself (requires a real Blender binary).
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from forge_flame.fbx_io import (  # noqa: E402
    DEFAULT_PIXEL_TO_UNITS,
    ...
)
```

For `flame_math.py` tests, add the tools dir to path:

```python
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools", "blender", "forge_sender"))
from flame_math import _rot3_to_flame_euler_deg, _R_Z2Y, build_v5_payload  # noqa: E402
```

#### 7.2 Analog: duck-typed fakes (`tests/test_fbx_io.py:46-90`)

```python
class _Attr:
    """Minimal PyAttribute fake: get_value / set_value."""
    def __init__(self, value):
        self._value = value
    def get_value(self):
        return self._value
    def set_value(self, v):
        self._value = v
        return True


class _Camera:
    """Minimal PyCoNode fake — has the four duck-typing attrs."""
    def __init__(self, name, position=(0.0, 0.0, 0.0), rotation=(0.0, 0.0, 0.0),
                 fov=40.0, focal=22.0):
        self.name = _Attr(name)
        self.position = _Attr(position)
        self.rotation = _Attr(rotation)
        self.fov = _Attr(fov)
        self.focal = _Attr(focal)
```

Apply the same pattern to `test_forge_sender_preflight.py` — a `_Context` fake with `.active_object`, and a `_BlenderCamera` fake with `.type`, `.data` (where `.data` is a plain dict). `preflight.check()` accepts ANY object with those attributes (per §4.2 "does not import bpy; accepts any object").

#### 7.3 Analog: pure-builder argv/payload tests (`tests/test_blender_bridge.py:187-252`)

```python
class TestBuildBakeCmd:
    """The argv list we pass to subprocess.run must match what bake_camera.py
    actually parses via argparse."""

    def test_basic_shape(self):
        cmd = build_bake_cmd(
            "/tmp/in.json", "/tmp/out.blend",
            blender_bin="/fake/blender",
            bake_script="/fake/bake_camera.py",
        )
        assert cmd[0] == "/fake/blender"
        assert cmd[1] == "--background"
        assert "--python" in cmd
        assert "/fake/bake_camera.py" in cmd
        assert "--" in cmd
```

Apply to `test_forge_sender_transport.py::TestBuildPayload`:

```python
class TestBuildPayload:
    def test_returns_code_key(self):
        body = transport.build_payload('{"frames":[]}')
        assert "code" in body
        assert isinstance(body["code"], str)

    def test_code_embeds_json_string(self):
        body = transport.build_payload('{"width":1920}')
        # repr() of the JSON string must appear verbatim inside the code
        assert "1920" in body["code"]

    def test_code_references_flame_api(self):
        body = transport.build_payload("{}")
        assert "flame.batch" in body["code"]
        assert "v5_json_str_to_fbx" in body["code"]
        assert "import_fbx_to_action" in body["code"]
```

#### 7.4 Analog: round-trip sanity (`tests/test_blender_roundtrip.py`)

The existing `tests/test_blender_roundtrip.py` uses numpy parallel implementations of the Blender-side math. For `flame_math.py` tests, the planner can either:
- **Option A (recommended):** import directly from `flame_math.py` and assert the functions are numerically identical to `forge_core.math.rotations.compute_flame_euler_zyx` by feeding both the same input (requires `mathutils` available in the test env — `conda forge` env may or may not have it; check).
- **Option B (fallback):** rewrite the math using numpy in the test file and assert against `flame_math.py`'s functions using a `mathutils` shim or skip with `pytest.importorskip("mathutils")`.

Pick based on whether `mathutils` is pip-installable in the conda forge env (it is, via `blender` wheel — but weight of the dep is non-trivial). Planner decides.

#### 7.5 Existing `tests/test_fbx_ascii.py::TestPublicAPI` extension

```python
class TestV5JsonStrToFbx:
    """D-01: in-memory JSON string variant must produce byte-identical output
    to the file-path variant for the same input."""

    def test_equivalent_to_file_variant(self, tmp_path):
        payload = {
            "width": 1920, "height": 1080, "film_back_mm": 16.0,
            "frames": [{
                "frame": 0,
                "position": [0.0, 0.0, 4747.64],
                "rotation_flame_euler": [0.0, 0.0, 0.0],
                "focal_mm": 22.0,
            }],
        }
        json_str = json.dumps(payload)

        # File variant
        json_path = tmp_path / "in.json"
        json_path.write_text(json_str)
        fbx_from_file = tmp_path / "from_file.fbx"
        v5_json_to_fbx(str(json_path), str(fbx_from_file))

        # String variant
        fbx_from_str = tmp_path / "from_str.fbx"
        v5_json_str_to_fbx(json_str, str(fbx_from_str))

        assert fbx_from_file.read_text() == fbx_from_str.read_text()
```

---

## Shared Patterns

### Duck-typing on Flame / Blender objects (CLAUDE.md §Duck Typing)

**Source:** `forge_flame/fbx_io.py:63-70` (Flame side) + `tools/blender/extract_camera.py:141-142` (Blender side).

**Apply to:**
- `preflight.check()` — accept any object exposing `.active_object.type` + `.active_object.data`.
- Bridge-side Action filter in `_FLAME_SIDE_TEMPLATE` — `hasattr(n, "import_fbx")` duck-types a PyActionNode without importing `flame.PyActionNode`.
- `flame_math.py` `_camera_keyframe_set` — already uses `anim.action is None` duck-check, preserve.

```python
# Pattern:
if not all(hasattr(n, attr) for attr in ("position", "rotation", "fov", "focal")):
    continue
if n.name.get_value() == "Perspective":
    continue
```

### Error taxonomy surfacing (D-09 three-tier)

**Source:** UI-SPEC §Copywriting Contract + `flame/camera_match_hook.py:2079-2083, 2113-2119, 2219-2224` (Phase 1 analog — Flame side uses `flame.messages.show_in_dialog`; Blender side uses `self.report` + `bpy.ops.wm.popup_menu`).

**Apply to:** every error path in `operator.py` / `__init__.py`.

Three tiers, **all use `report_level='ERROR'`** (UI-SPEC consolidated matrix — no `'WARNING'` anywhere):

1. **Preflight Tier 1** (addon-side, before POST) → `preflight.check()` returns a string → `self.report({'ERROR'}, msg)` + `_popup(context, msg)`.
2. **Transport Tier** (addon-side, POST failed) → `except (ConnectionError, Timeout)` → fixed copy `"Send to Flame: forge-bridge not reachable at http://127.0.0.1:9999 — is Flame running..."`.
3. **Remote Tier** (bridge returned `error` field) → `transport.parse_envelope` returns `err` → `self.report({'ERROR'}, err)` + `_popup_multiline(context, err)`.

### "Pure builder + thin runner" split

**Source:** `forge_flame/blender_bridge.py:156-252`.

**Apply to:** `transport.py` (`build_payload` pure + `send` thin), and to the operator (`flame_math.build_v5_payload` pure + `execute()` thin). Rationale: tests assert shape without network/Blender.

### Tempdir preserve-on-failure + clean-on-success (D-03, carried from Phase 1 D-14)

**Source:** `flame/camera_match_hook.py:2099-2243` (Phase 1 export handler).

**Apply to:** bridge-side Flame Python template in `transport.py` §5.3 — `success = False` flag, `finally: if success: shutil.rmtree(tmpdir)`. On failure, `print(f"[forge-send] tempdir preserved: {tmpdir}")` so the bridge `stderr` field captures the path and the Remote Tier popup surfaces it to the artist.

**Gotcha:** `tempfile.TemporaryDirectory` as a context manager cleans on BOTH success and failure — wrong for this pattern. Use `tempfile.mkdtemp()` + explicit `shutil.rmtree()`.

### Module-docstring convention (CLAUDE.md §Comments and Documentation)

**Source:** `forge_flame/fbx_ascii.py:1-34`, `tools/blender/bake_camera.py:1-56`, `tools/blender/extract_camera.py:1-47`.

**Apply to:** every new file — open with "Why this module exists" paragraph + scope boundaries + cross-references to `memory/*.md` gotchas.

Example skeleton for `flame_math.py`:

```python
"""
forge_sender/flame_math.py — shared Blender-side Flame camera math.

Why this module exists: the "Send to Flame" addon and the legacy
extract_camera.py CLI script both need the same Euler decomposition,
axis-swap matrix, keyframe walker, and v5-JSON payload builder. Putting
them here gives us one copy to touch when the math needs a fix
(memory/flame_rotation_convention.md is the spec).

Scope boundaries:
  - Math only. No bpy Panel / Operator / UI.
  - No HTTP / JSON I/O. Callers serialize via json.dumps.
  - Pure bpy + mathutils imports; safe to import from either the addon
    or from a Blender subprocess driving extract_camera.py.

Round-trip parity: the Euler decomposition here MUST stay numerically
identical to forge_core.math.rotations.compute_flame_euler_zyx. If you
change one, change both and run tests/test_blender_roundtrip.py.
"""
from __future__ import annotations
...
```

### Type-hint convention (CLAUDE.md §Type Hints)

**Source:** project-wide; `forge_flame/fbx_io.py:51` (`-> list`), `tools/blender/extract_camera.py:90` (`def _rot3_to_flame_euler_deg(R) -> tuple`).

**Apply to:** every function in `flame_math.py`, `transport.py`, `preflight.py`. Use `from typing import Optional, Tuple` + `from __future__ import annotations`. Return-type annotations mandatory.

---

## No Analog Found

| File | Role | Data Flow | Reason / Reference |
|------|------|-----------|--------------------|
| `tools/blender/forge_sender/__init__.py` (addon scaffold: `bl_info`, `register`, `bpy.types.Panel`, `bpy.types.Operator`) | Blender addon entry | bpy UI events | **First Blender addon in this repo.** Existing `bake_camera.py` and `extract_camera.py` are CLI subprocess scripts — they use `bpy` and `mathutils` but NOT addon registration surface. Planner MUST fall back to Blender 4.5 docs (via `mcp:context7` for `bpy.types.Panel`, `bpy.types.Operator`, `bpy.utils.register_class`, `layout.label`, `layout.operator`, `bpy.ops.wm.popup_menu`). UI-SPEC already pins every exact layout call and copy string; only the addon scaffolding is externally referenced. |

---

## Authoritative External References

Where the planner / executor must consult external docs because no in-repo analog exists:

| Surface | Reference | Why |
|---------|-----------|-----|
| `bpy.types.Panel` subclass, `bl_label`/`bl_idname`/`bl_space_type`/`bl_region_type`/`bl_category`/`bl_order`/`draw()` contract | Blender 4.5 Python API docs (via `mcp:context7` resolve `blender` → lookup `bpy.types.Panel`) | New surface in this repo; UI-SPEC pins the values but the scaffold needs docs. |
| `bpy.types.Operator` subclass, `bl_idname`/`bl_label`/`poll()`/`execute()`/`self.report()` contract | Blender 4.5 Python API docs | New surface. |
| `bpy.ops.wm.popup_menu` `draw` callback shape | Blender 4.5 Python API docs | UI-SPEC §Remote Tier requires multi-line `layout.label` per line. |
| `bpy.utils.register_class` / `unregister_class` | Blender 4.5 Python API docs | Standard addon entry point. |
| `requests.post` with `json=` kwarg and `timeout=` | `requests` library docs (D-13: bundled with Blender 4.5's Python) | Standard. `mcp:context7` `requests` if signature doubt arises. |
| forge-bridge JSON envelope | `~/.claude/projects/-Users-cnoellert-Documents-GitHub-forge-calibrator/memory/flame_bridge.md` + `flame_bridge_probing.md` | Response envelope keys (`result`, `stdout`, `stderr`, `error`, `traceback`); 2026-04-19 payload contract update. |
| Flame `flame.batch.frame_rate` shape | **D-18 probe REQUIRED** — not documented. Run a forge-bridge ping-only probe, then a single isolated `print(flame.batch.frame_rate.get_value())` call, per `memory/flame_bridge_probing.md`. Save findings to `memory/` before asking for a Flame restart. | Unverified API surface; probing discipline mandatory. |

---

## Metadata

**Analog search scope:**
- `tools/blender/` — CLI scripts (bake / extract); bundled JSON sample; roundtrip selftest shell.
- `forge_flame/` — Flame-side adapters (`fbx_ascii.py`, `fbx_io.py`, `blender_bridge.py`).
- `flame/camera_match_hook.py` — Phase 1 export handler (tempdir + error-dialog conventions).
- `tests/` — test patterns (duck-typed fakes, pure-builder assertions, sys.path shims).
- `~/.claude/projects/.../memory/*.md` — bridge contracts + probing discipline.
- `.planning/phases/01-export-polish/` — Phase 1 PATTERNS.md + CONTEXT.md for carry-forward conventions.

**Files scanned:** 14 code files + 3 memory docs + 2 planning docs.

**Pattern extraction date:** 2026-04-21.

**Key observation:** the Blender addon surface (`bl_info`, `register()`, `bpy.types.Panel`, `bpy.types.Operator`, `bpy.ops.wm.popup_menu`) is **brand new in this repo** — no prior addon exists. Planner must reference Blender docs for scaffolding. Everything ELSE (math, HTTP, validation, tests, docstring style, error taxonomy, tempdir pattern) has strong in-repo analogs cited above.
