# Phase 1: Export Polish — Pattern Map

**Mapped:** 2026-04-19
**Files analyzed:** 4 (3 modified, 1 new config key)
**Analogs found:** 4 / 4

## File Classification

| File | Change type | Role | Data Flow | Closest Analog | Match Quality |
|------|-------------|------|-----------|----------------|---------------|
| `flame/camera_match_hook.py` (rework `_export_camera_to_blender` at L1793) | modify | Flame batch hook handler / subprocess orchestrator | Flame Action -> filesystem (temp) -> Blender subprocess (bake) -> filesystem (`~/forge-bakes/`) -> Blender launch subprocess | `flame/camera_match_hook.py::_import_camera_from_blender` (L1958, same file, sibling handler) | exact (same role, same module, opposite direction) |
| `tools/blender/bake_camera.py` (add `custom_properties` application) | modify | Blender-side bpy script (subprocess entrypoint) | v5 JSON -> bpy camera keyframes + custom properties -> `.blend` file | `tools/blender/bake_camera.py::_stamp_metadata` (L144, same file, same function class) | exact (existing custom-property stamping lives right here) |
| `forge_flame/fbx_ascii.py::fbx_to_v5_json` (L710, optional `custom_properties=` kwarg passthrough) | modify | Pure converter (no Flame, no Blender) | FBX tree + caller-supplied dict -> v5 JSON dict + file | `forge_flame/fbx_ascii.py::fbx_to_v5_json` itself — extending an existing keyword-only signature | exact (same function, additive kwarg) |
| `.planning/config.json` (new `blender_launch_focus_steal` key) | modify | Project config (human-edited JSON) | Disk -> hook reads at handler invocation | `.planning/config.json` existing keys (`parallelization`, `commit_docs`) | exact (same file, same schema style) |

**Note on scope:** `_scan_first_clip_metadata` (L1756) and `_pick_camera` (L1779) are **unchanged**; they are referenced only as fallback/reuse by the reworked handler. `forge_flame/blender_bridge.run_bake` (L218) is called unchanged; a new **launch** helper may live alongside it — planning decides whether that helper lives inside `blender_bridge.py` or inline in the hook.

---

## Pattern Assignments

### 1. `_export_camera_to_blender` rework (controller-layer handler)

**File:** `flame/camera_match_hook.py`, function at L1793
**Role:** batch-menu handler (scope `_scope_batch_action`)
**Analog:** the sibling handler `_import_camera_from_blender` (L1958) in the same file — mirror its shape for temp dir, error branches, and final success dialog.

#### 1.1 Module preamble / env bootstrap (copy verbatim)

First three lines of every hook handler are non-negotiable — they wire in the forge conda env and put `forge_core` / `forge_flame` on `sys.path`. From the current `_export_camera_to_blender` (L1816-1825):

```python
def _export_camera_to_blender(selection):
    """... docstring ..."""
    _ensure_forge_env()
    _ensure_forge_core_on_path()

    import flame
    import json as _json
    import os
    import subprocess
    from PySide6 import QtWidgets

    from forge_flame import blender_bridge, fbx_ascii, fbx_io
```

Keep identical. Add `import tempfile` at the same level (lazy, inside the function, not module-level — matches the file's convention of deferring heavy/platform-specific imports until the handler actually runs).

#### 1.2 Selection / action / camera pick pattern (keep as-is)

From L1827-1847 (current handler):

```python
action_node = _first_action_in_selection(selection)
if action_node is None:
    flame.messages.show_in_dialog(
        title="Export Camera to Blender",
        message="Right-click an Action node in Batch (the Action that "
                "holds your solved camera).",
        type="error", buttons=["OK"])
    return

cameras = _find_action_cameras(only_action=action_node)
if not cameras:
    flame.messages.show_in_dialog(
        title="Export Camera to Blender",
        message=f"No non-Perspective camera in "
                f"'{_val(action_node.name)}'.",
        type="error", buttons=["OK"])
    return
picked = _pick_camera(cameras, "Export Camera to Blender")
if picked is None:
    return
action, cam, label = picked
```

Keep verbatim — this is the contract. `_pick_camera` already honors D-13 (auto-select on 1, dialog on 2+). Zero changes here.

#### 1.3 Resolution readback — three-tier fallback (NEW, per D-07/D-08)

Replace the current `QInputDialog.getText` block (L1854-1872) with a silent three-tier probe. No RESEARCH.md exists, so treat `action.resolution` shape as **unverified** — the plan MUST include a forge-bridge probe task first (per D-09, and `memory/flame_bridge_probing.md`).

**Tier 1 — primary (unverified shape, duck-type it):** per EXP-02, read `action.resolution.get_value()`. Use the same duck-typing guard style as `iter_keyframable_cameras` (`forge_flame/fbx_io.py:65`):

```python
if not all(hasattr(n, attr) for attr in ("position", "rotation", "fov", "focal")):
    continue
```

Adapt to `hasattr(action, "resolution")` + `hasattr(action.resolution, "get_value")`. Whether the returned object exposes `.width`/`.height` (like `clip.resolution`, see `forge_flame/wiretap.py:142-143`) or a tuple is what the probe must confirm.

**Tier 2 — batch fallback:** copy the exact shape from `flame/apply_solve.py:269-276`:

```python
# Get image dimensions from current clip or batch setup
# Try batch resolution first
try:
    b = flame.batch
    width = int(b.width.get_value())
    height = int(b.height.get_value())
except Exception:
    # Fallback to a common resolution
    print("Could not read batch resolution, defaulting to 1920x1080")
    width, height = 1920, 1080
```

**Critical amendment** (per D-08): do NOT silently default to 1920x1080. If Tier 1 and Tier 2 both fail, fall through to Tier 3.

**Tier 3 — first-clip scan:** call existing `_scan_first_clip_metadata()` from same module (L1756), unwrap the `(w, h, _start)` tuple, and treat the baked-in `(1920, 1080, 1)` return as a sentinel meaning "nothing found". That sentinel is only reached when **no** clip exists in batch AND both prior tiers failed — at which point raise an error dialog. Error wording is Claude's discretion (per CONTEXT.md Claude's Discretion bullet 3).

**Gotcha:** `_scan_first_clip_metadata` returns `(1920, 1080, 1)` today as its "no clip" fallback. The plan should either (a) differentiate real vs. sentinel by refactoring the helper to return `None` on miss (lightweight change, low risk), or (b) only trust Tier 3 if `flame.batch.nodes` actually has at least one `PyClipNode` (read-only check). Planner picks.

#### 1.4 Output path (NEW, per D-04/D-05)

Replace the `QFileDialog.getSaveFileName` block (L1875-1882) with a computed path — no dialog:

```python
default_name = f"{_val(action_node.name)}_{_val(cam.name)}.blend"
output_dir = os.path.expanduser("~/forge-bakes")
os.makedirs(output_dir, exist_ok=True)
blend_path = os.path.join(output_dir, default_name)
# D-05: overwrite. No collision check. Freshest bake wins.
```

The `_val(action_node.name)` / `_val(cam.name)` pattern is already the convention (L1875 of current handler; `_val` defined at L1685 returns `x.get_value() if hasattr(x, "get_value") else str(x)`).

#### 1.5 Temp dir for intermediates (NEW, per D-14)

Analog: `forge_flame/wiretap.py:148` uses `tempfile.TemporaryDirectory` as a context manager. That pattern **auto-cleans on both success AND failure**, which violates D-14 ("preserve temp dir on failure, clean on success"). Use `tempfile.mkdtemp` + explicit `shutil.rmtree` instead:

```python
import shutil
import tempfile

tmp_dir = tempfile.mkdtemp(prefix="forge_bake_")
fbx_path = os.path.join(tmp_dir, f"{_val(cam.name)}.fbx")
json_path = os.path.join(tmp_dir, f"{_val(cam.name)}.json")

success = False
try:
    # ... bake / convert / launch blocks below ...
    success = True
finally:
    if success:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    # else: leave tmp_dir intact; its path goes into the error dialog
```

**Error dialog amendment:** every `flame.messages.show_in_dialog(..., type="error", ...)` branch below (L1897-1902, L1913-1918, L1926-1937 in the current handler) must include `tmp_dir` in the message so the user knows where to look (per D-14). Example:

```python
flame.messages.show_in_dialog(
    title="Export Camera to Blender",
    message=f"Failed to write FBX:\n{e}\n\n"
            f"Intermediate files preserved at:\n{tmp_dir}",
    type="error", buttons=["OK"])
return  # tmp_dir stays on disk; `success` is still False
```

#### 1.6 FBX bake (keep as-is)

L1891-1902 of current handler — `fbx_io.export_action_cameras_to_fbx(action, fbx_path, cameras=[cam], bake_animation=True)` is already correct. `fbx_io.py:135-145` filters Perspective unconditionally, and `fbx_io.py:150-159` handles the selection save/restore. No change beyond pointing `fbx_path` at the new `tmp_dir`.

**Gotcha documented in `memory/flame_perspective_camera.md`:** never pass Perspective as a camera. `_find_action_cameras` (L1694) already filters it at L1719, so the upstream list is safe — but the `export_action_cameras_to_fbx` filter at `fbx_io.py:140` is the unconditional belt-and-braces. Do not remove either guard.

#### 1.7 FBX -> v5 JSON conversion (modify per D-10/D-12)

Current call at L1906-1912:

```python
fbx_ascii.fbx_to_v5_json(
    fbx_path, json_path,
    width=width, height=height,
    film_back_mm=36.0,
    camera_name=_val(cam.name),
)
```

Two options, planner picks (per D-12):
- **Option A** (additive kwarg): add `custom_properties: Optional[dict] = None` to `fbx_to_v5_json` (see §3 below).
- **Option B** (post-hoc stamp): keep `fbx_to_v5_json` unchanged; after it returns, load the JSON, inject `"custom_properties": {...}` at the top level, rewrite.

**Recommendation (not a decision):** Option A is a 4-line change, keeps the JSON write atomic, and honors the CONTEXT.md line "v5 JSON contract is the bridge… extend it, do not bypass." But Option B is genuinely simpler if you treat the v5 contract as stable and the hook as the mutator. Plan should pick one and justify.

Values to stamp (per D-11) — **exactly these two, nothing else**:

```python
custom_properties = {
    "forge_bake_action_name": _val(action_node.name),
    "forge_bake_camera_name": _val(cam.name),
}
```

#### 1.8 Blender headless bake (keep as-is)

L1920-1937 of current handler calls `blender_bridge.run_bake(json_path, blend_path, ...)`. **Unchanged per D-01.** Error branches (FileNotFoundError, CalledProcessError) keep their current shape; just append `tmp_dir` to the message per §1.5.

#### 1.9 Blender launch spawn (NEW, per D-02)

Replace the `blender_bridge.reveal_in_file_manager(blend_path)` line (L1947) and the final info dialog (L1948-1955). The new launch spawn:

```python
# Read the focus-steal preference from .planning/config.json.
# Claude's discretion (bullet 4): read once at handler start or per-invocation.
# Pick per-invocation — simpler, no module state, cheap read.
focus_steal = _read_launch_focus_steal()  # see §4 below

try:
    if sys.platform == "darwin":
        args = ["open", "-a", "Blender"]
        if not focus_steal:
            args.insert(2, "-g")  # -g == background (no focus steal)
        args.append(blend_path)
        subprocess.Popen(args)
    elif sys.platform == "linux":
        # focus_steal flag is best-effort-ignored on Linux (WM-dependent).
        blender_bin = blender_bridge.resolve_blender_bin()
        subprocess.Popen(
            [blender_bin, blend_path],
            start_new_session=True,
        )
    else:
        raise OSError(f"Unsupported platform: {sys.platform}")
except Exception as e:
    # D-03: Blender launch failed. Fall back to file-manager reveal so
    # the user at least sees where the .blend landed.
    blender_bridge.reveal_in_file_manager(blend_path)
    flame.messages.show_in_dialog(
        title="Export Camera to Blender",
        message=f"Exported to {blend_path}\n\n"
                f"Couldn't auto-launch Blender ({e}).\n"
                f"File manager opened to the output folder.",
        type="warning", buttons=["OK"])
    return
```

**Analog for `subprocess.Popen` with platform branching:** `forge_flame/blender_bridge.py:270-278` (`reveal_in_file_manager`) — same `sys.platform == "darwin"` vs. `"linux"` shape. Mirror that branching style.

**Analog for `open -a [-g]` on macOS:** no existing use in the codebase. D-02 is the source of truth. `-g` flag semantics: `man open` — "do not bring the application to the foreground". When `focus_steal=true`, omit `-g` entirely (default foreground behavior).

**Analog for `start_new_session=True` on Linux:** no existing use in the codebase either. Rationale per D-02: detaches the Blender child from Flame's process group so closing Flame doesn't signal Blender.

**Zero-dialog happy path:** on success, NO `show_in_dialog` call. The .blend file and the Blender window ARE the user feedback (per CONTEXT.md `<specifics>`: "User-visible surface after a successful export: the `.blend` file + Blender window. That's it."). Drop the current L1948-1955 info dialog entirely.

#### 1.10 Error dialog policy (keep, per D-15)

All existing `flame.messages.show_in_dialog(..., type="error", ...)` branches stay. Do NOT convert any of them to console-only or toast. Only the **success-path info dialog** is removed.

---

### 2. `tools/blender/bake_camera.py` — custom_properties application

**File:** `tools/blender/bake_camera.py` (modify)
**Role:** Blender-side bpy script (subprocess entrypoint, no forge imports)
**Analog:** `_stamp_metadata` at L144-150 of the same file.

Existing stamp already puts four properties on `cam_data` (the camera data-block, not the object):

```python
def _stamp_metadata(cam_data: bpy.types.Camera, scale: float, source_path: str) -> None:
    """Write round-trip metadata onto the camera's data-block so extract
    can undo the scale and provenance-check the source."""
    cam_data["forge_bake_version"] = 1
    cam_data["forge_bake_source"] = "flame"
    cam_data["forge_bake_scale"] = scale
    cam_data["forge_bake_input_path"] = os.path.abspath(source_path)
```

**Extend that function** to accept an optional dict and apply each key/value:

```python
def _stamp_metadata(
    cam_data: bpy.types.Camera,
    scale: float,
    source_path: str,
    custom_properties: Optional[dict] = None,
) -> None:
    """..."""
    cam_data["forge_bake_version"] = 1
    cam_data["forge_bake_source"] = "flame"
    cam_data["forge_bake_scale"] = scale
    cam_data["forge_bake_input_path"] = os.path.abspath(source_path)
    if custom_properties:
        for key, value in custom_properties.items():
            cam_data[key] = value
```

Caller update in `_bake` (L202): read `data.get("custom_properties")` (top-level v5 JSON key per D-10) and pass it through:

```python
_stamp_metadata(cam.data, scale, args.in_path, data.get("custom_properties"))
```

**Gotchas:**
- bpy custom-property slots accept `str | int | float | list | dict` natively; D-10 restricts to `str | int | float`, which is the safe subset. Don't expand the accepted types without revisiting D-10.
- Apply to `cam.data` (the camera data-block), **not** `cam` (the object). `cam.data` is what `extract_camera.py` reads, and Blender custom properties survive across .blend saves as ID-block data. This is already the convention here (L202).
- **No `from __future__ import annotations`** in this file today (see L58-65: module uses plain imports, not forward refs). Don't add it — this script is deliberately standalone for Blender's bpy-bundled Python and avoids CPython-version-specific niceties that aren't needed here.
- `Optional` is not currently imported in this file. Planner: add `from typing import Optional` at module top alongside existing stdlib imports.

---

### 3. `forge_flame/fbx_ascii.py::fbx_to_v5_json` — optional passthrough

**File:** `forge_flame/fbx_ascii.py` L710-778
**Role:** Pure converter (numpy-free, Flame-free; safe to import anywhere)
**Analog:** the function itself — extending its existing keyword-only signature.

Only applies if planner picks Option A from §1.7.

Current signature (L710-719):

```python
def fbx_to_v5_json(
    fbx_path: str,
    out_json_path: str,
    *,
    width: int = 0,
    height: int = 0,
    film_back_mm: Optional[float] = None,
    frame_rate: str = "23.976 fps",
    camera_name: Optional[str] = None,
) -> dict:
```

Extension:

```python
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
) -> dict:
```

Payload stamp (L766-771) grows one conditional key:

```python
payload = {
    "width": int(width),
    "height": int(height),
    "film_back_mm": float(film_back_mm),
    "frames": frames,
}
if custom_properties:
    payload["custom_properties"] = dict(custom_properties)
```

**Gotchas:**
- `dict(custom_properties)` creates a shallow copy so caller mutations after the call don't affect the written JSON. Small detail, but matches the defensive style seen elsewhere in the file (e.g., `list(action.selected_nodes.get_value())` at `fbx_io.py:81`).
- **Google-style docstring** — extend the existing `Args:` block with a new bullet for `custom_properties` using the same format as the existing bullets (see L722-741).
- `Optional[dict]` — matches the existing type-hint style in this file (L716, `Optional[float]`; L718, `Optional[str]`).
- `from __future__ import annotations` is already at the top of this module (confirmed via the established convention in `forge_flame/blender_bridge.py:35` and `forge_flame/fbx_io.py:33`). Do not re-add.
- **Tests to extend:** the file has a companion test file (follow the `test_<module>.py` convention per CLAUDE.md "Naming Patterns"). The plan should add at least one test case covering `custom_properties={"forge_bake_action_name": "Action_01"}` round-trip through the JSON.

---

### 4. `.planning/config.json` — new key + reader helper

**File:** `.planning/config.json` (add one key)
**Analog:** existing top-level keys `parallelization: true`, `commit_docs: true` (see `.planning/config.json` L3-4).

Addition:

```json
{
  "...": "...",
  "blender_launch_focus_steal": false
}
```

Default `false` per EXP-05 and D-02. Boolean, top-level.

**Reader helper (NEW, lives in `flame/camera_match_hook.py`):**

No existing reader for `.planning/config.json` in any Python file (confirmed by grep). Add a minimal one — Claude's discretion bullet 4 ("read once at handler start or re-read per invocation") — recommend **per-invocation** for simplicity:

```python
def _read_launch_focus_steal() -> bool:
    """Read blender_launch_focus_steal from .planning/config.json.

    Returns False if the file is missing, unreadable, or the key is absent.
    Defaults to False per EXP-05 (Blender launches in background by default).
    Tolerant of any I/O or JSON failure — launch preference is non-critical.
    """
    import json
    this_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(this_dir)
    config_path = os.path.join(repo_root, ".planning", "config.json")
    try:
        with open(config_path) as f:
            return bool(json.load(f).get("blender_launch_focus_steal", False))
    except Exception:
        return False
```

**Path resolution analog:** mirrors the `this_dir / parent` walk at `camera_match_hook.py:51-54` (`_ensure_forge_core_on_path`). That idiom is the established pattern for "find something relative to this file".

**Gotcha:** when the hook is installed to `/opt/Autodesk/shared/python/camera_match/`, there is no `.planning/` sibling — the `try/except` correctly returns `False`, and the installed deployment silently gets the default. That matches D-02 (`false` default) and is the expected install-time behavior. If a downstream user wants focus-steal on an installed deployment, the install story for `.planning/config.json` is a separate concern (not in this phase).

**Gotcha — Flame module reload (per CLAUDE.md + `memory/flame_module_reload.md`):** if you edit the reader helper and Flame is already running, menu callbacks captured at hook-registration time do NOT refresh. The user must restart Flame to pick up new UI handler code. This doesn't affect the config-read path itself (which re-reads per invocation), but does affect the helper definition. Document this in the plan's test section.

---

## Shared Patterns (cross-cutting, apply to all modified code)

### Error surfacing via `flame.messages.show_in_dialog`

**Source:** already ubiquitous in `flame/camera_match_hook.py` (e.g., L1829, L1838, L1867, L1898, L1914, L1927). Signature is stable:

```python
flame.messages.show_in_dialog(
    title="Export Camera to Blender",
    message="<one or more lines>",
    type="error",   # or "info", "warning"
    buttons=["OK"],
)
```

Apply to every error branch in the reworked handler. Do NOT introduce any new toast / console-only / logger-only error path (per D-15).

### Duck-typing over `isinstance` on Flame objects

**Source:** `forge_flame/fbx_io.py:65` (`hasattr(n, attr) for attr in ("position", "rotation", "fov", "focal")`) and the ubiquitous `_val` helper at `camera_match_hook.py:1685`:

```python
def _val(x):
    return x.get_value() if hasattr(x, "get_value") else str(x)
```

Apply this pattern to the `action.resolution` probe (per D-09). Expected shape after probe confirms: `hasattr(action, "resolution") and hasattr(action.resolution, "get_value")`. Do NOT use `isinstance(action, flame.PyActionNode)` — the existing codebase deliberately avoids that for unit-testability (per CLAUDE.md "Duck Typing" section).

### `from __future__ import annotations` at top of every module

**Source:** CLAUDE.md "Code Style" + `forge_flame/blender_bridge.py:35`, `forge_flame/fbx_io.py:33`, `forge_flame/wiretap.py:19`.

Apply to `forge_flame/fbx_ascii.py` edits (already has it). **Do NOT add** to `tools/blender/bake_camera.py` (Blender bpy script, not a forge module — keeps its current plain-import style). `flame/camera_match_hook.py` currently uses `from __future__ import print_function` (py2-legacy), not `annotations` — do not change that without a broader sweep.

### Google-style docstrings with "why this module/function exists"

**Source:** CLAUDE.md "Comments and Documentation" + every file's top-of-module docstring. Already-reviewed examples:

- `forge_flame/fbx_io.py:1-31` — "why FBX is the animated route" + "Perspective exclusion gotcha"
- `forge_flame/blender_bridge.py:1-33` — "what we need from Blender and how we find it"
- `tools/blender/bake_camera.py:1-56` — "axis convention + scale semantics"

Apply to:
- The reworked `_export_camera_to_blender` docstring: update L1794-1815 to reflect the new flow (no dialogs on happy path, temp dir, `~/forge-bakes/` output, launch instead of reveal). Keep the "Flow:" bullet style already there.
- The `fbx_to_v5_json` `custom_properties` kwarg Args bullet (if Option A chosen).
- The new `_read_launch_focus_steal` helper docstring — follow the one-line + Args-less pattern of `_val` (L1685-1691) since it takes no args.

### Snake_case everywhere, constants ALL_CAPS

**Source:** CLAUDE.md "Naming Patterns".

All new names must be snake_case (`tmp_dir`, `blend_path`, `custom_properties`, `focus_steal`, `_read_launch_focus_steal`). No new module-level constants needed for this phase, but if one is added (e.g., a hard-coded `~/forge-bakes` path) it should be ALL_CAPS per convention (e.g., `_DEFAULT_BAKE_DIR = "~/forge-bakes"`).

### Forge-bridge probing discipline (for the Action.resolution task)

**Source:** `memory/flame_bridge_probing.md` + `memory/flame_bridge.md`.

Per D-09, the plan MUST include a probe task before the implementation task. Contract:
- POST code to `http://127.0.0.1:9999/exec` (bridge must be running)
- Keep the probe **non-destructive** (get_value only, no set_value, no node creation)
- Return structured JSON (success + payload, OR error + traceback)
- Document the confirmed shape of `action.resolution` in the plan's probe-results section before the impl task begins

This is a read-only research activity — does not count as an "implementation task". The pattern-mapper is not probing; that's the planner's / executor's job.

---

## No Analog Found

| Item | Reason | Fallback |
|------|--------|----------|
| `action.resolution` PyAttribute shape | Not used anywhere in the current codebase. Only `clip.resolution` is probed (`forge_flame/wiretap.py:142`). EXP-02 is the first user. | D-09 mandates a forge-bridge probe task before implementation. Plan must block on its results. |
| `open -a -g Blender <path>` on macOS | No existing use. | D-02 is the decision-of-record. `man open` confirms `-g` = "do not bring application to foreground". |
| `subprocess.Popen(..., start_new_session=True)` on Linux | No existing use. | D-02 is the decision-of-record. Python docs confirm `start_new_session=True` calls `setsid` in the child. |
| `.planning/config.json` Python reader | No existing reader (grep confirmed). | §4 above defines the helper inline. |

---

## Gotchas Summary (executor checklist)

1. **Perspective camera filter** — never remove. Two guards exist (`_find_action_cameras:1719` and `fbx_io.py:140`); both stay. Reference: `memory/flame_perspective_camera.md`.
2. **FBX is mandatory for animated cameras** — PyAttribute has no keyframe API. Reference: `memory/flame_keyframe_api.md`. This phase doesn't touch the FBX route, but don't accidentally replace it with a PyAttribute write.
3. **Flame module reload caveat** — menu callback identities are captured at hook registration; Flame restart required for UI-handler changes. Reference: `memory/flame_module_reload.md` + CLAUDE.md "Entry Points / Menu callbacks captured at hook-registration time".
4. **`tempfile.TemporaryDirectory` auto-cleans on both success AND failure** — use `tempfile.mkdtemp` + explicit `shutil.rmtree` to honor D-14 (preserve on failure).
5. **Never silently default plate resolution** — D-08. Three-tier fallback then error dialog. The existing `_scan_first_clip_metadata` fallback-to-1920x1080 (L1776) is a bug under the new policy; refactor the sentinel or add an explicit "no clip found" path.
6. **Zero-dialog applies to happy path only** — D-15. Every failure branch still dialogs.
7. **forge-bridge probe before impl** — D-09. Discipline per `memory/flame_bridge_probing.md` (non-destructive, get-only, structured response).
8. **`_val` helper everywhere** — don't call `.get_value()` directly on potentially-stringified Flame attrs. Use `_val(x)` (L1685).
9. **Duck-type, don't `isinstance`** — CLAUDE.md convention. Applies especially to the new `action.resolution` probe.
10. **Snake_case + `from __future__ import annotations`** — except `tools/blender/bake_camera.py` which intentionally stays plain for bpy portability.

---

## Metadata

**Analog search scope:** `flame/`, `forge_flame/`, `tools/blender/`, `.planning/`
**Files scanned (read):** 6 (`flame/camera_match_hook.py`, `forge_flame/blender_bridge.py`, `forge_flame/fbx_io.py`, `forge_flame/fbx_ascii.py`, `forge_flame/wiretap.py`, `tools/blender/bake_camera.py`, `flame/apply_solve.py`, `.planning/config.json`)
**Memory docs referenced:** `flame_keyframe_api.md`, `flame_perspective_camera.md`, `flame_bridge_probing.md`, `flame_bridge.md`, `flame_module_reload.md`, `flame_rotation_convention.md`
**Pattern extraction date:** 2026-04-19
