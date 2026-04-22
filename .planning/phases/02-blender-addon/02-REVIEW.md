---
phase: 02-blender-addon
reviewer: gsd-code-reviewer (Claude)
depth: standard
reviewed: 2026-04-21
files_reviewed: 11
status: issues_found
counts:
  blocker: 0
  critical: 0
  warning: 2
  info: 3
---

# Phase 2: Code Review Report

**Status:** issues_found (2 warnings, 3 info — no blockers/critical)
**Files reviewed:** 6 source + 5 test
**Depth:** standard

## Summary

Phase 2 ships a well-structured Blender addon with a duck-typed transport layer and a D-19 frame-rate ladder recovering from the disproven D-17 probe. The code adheres to CLAUDE.md conventions (duck-typing over `isinstance`, module docstrings explaining "why", `from __future__ import annotations`, snake_case + ALL_CAPS constants, `repr()`-safe dynamic-value embedding in the bridge payload). Security posture is strong — the T-02-03-01 mitigation (every dynamic value through `repr()` or `json.dumps`) is correctly applied to both `v5_json_str` and `frame_rate`.

UI-SPEC copy strings match verbatim across preflight / transport / operator. Round-trip math lives in one module (`flame_math.py`) with numpy-parallel test coverage. The two Wave 4 hotfixes (permissive `poll()`, bridge `_result` surfacing via bare expression + `ast.literal_eval`) are correctly integrated and documented.

Two correctness concerns worth addressing; three info-level items for Phase 4 polish. No blockers.

## Findings

### Warnings

#### WR-01: `_resolve_frame_rate` silently skips an explicitly stamped but unsupported `forge_bake_frame_rate` value

- **File:** `tools/blender/forge_sender/__init__.py:108-117`
- **Severity:** warning
- **Type:** correctness (Core Value — fidelity over UX smoothness)

**Issue:** Ladder step 1 reads `cam.data.get("forge_bake_frame_rate")`. If the stamp is present but not one of the nine supported Flame labels, the code silently falls through to step 2 (scene fps). The SUMMARY and inline comment describe this as intentional ("don't feed an unknown string"), but this inverts the ladder's own precedence rule — step 1 is documented as authoritative when stamped. If an artist has deliberately stamped `"12 fps"` (custom pipeline label), the addon silently uses whatever the scene fps happens to be instead of failing loud. Additionally, a mismatched type on the stamp (Blender `IDPropertyArray`, an int, etc.) coerced by `str(stamped)` gives `"[24]"` or `"24"` — same silent fall-through.

**Fix:** Fail loud when the stamp is present but unsupported:

```python
stamped = cam.data.get("forge_bake_frame_rate")
if stamped:
    label = str(stamped)
    supported = {x[0] for x in _FLAME_FPS_LABELS}
    if label in supported:
        return (label, None)
    err = (f"Send to Flame: cam.data['forge_bake_frame_rate'] "
           f"= {label!r} is not a supported Flame label. "
           f"Expected one of: {', '.join(sorted(supported))}.")
    return (None, err)
```

#### WR-02: `v5_json_str_to_fbx` silently falls back to 24 fps on unknown frame-rate keys — no fidelity gate above it

- **File:** `tools/blender/forge_sender/transport.py:82-142` (Flame-side template) + `forge_flame/fbx_ascii.py` (v5_json_str_to_fbx docstring)
- **Severity:** warning
- **Type:** correctness (Core Value — silent fps fallback violates fidelity)

**Issue:** The addon's `_FLAME_FPS_LABELS` currently hard-codes to match `_FPS_FROM_FRAME_RATE`, so a drift-free frame_rate always reaches the bridge. BUT `v5_json_str_to_fbx` silently falls back to 24 fps on unknown keys (per its own docstring), and no layer above it validates the label against `_FPS_FROM_FRAME_RATE`. Defense-in-depth missing: if the two label sets drift (see IN-02), the silent 24 fps fallback violates the Core Value.

**Fix:** Add a guard in the Flame-side template before calling `v5_json_str_to_fbx`:

```python
if frame_rate not in fbx_ascii._FPS_FROM_FRAME_RATE:
    raise RuntimeError(
        "Unknown Flame frame rate: %r — expected one of %s"
        % (frame_rate, sorted(fbx_ascii._FPS_FROM_FRAME_RATE))
    )
```

Or validate on the addon side inside `build_payload` — cheaper and fails before POST.

### Info

#### IN-01: Return type annotation on `_resolve_frame_rate` is a tuple literal, not `Tuple[...]`

- **File:** `tools/blender/forge_sender/__init__.py:104`
- **Severity:** info
- **Type:** style / conformance to CLAUDE.md §Type Hints

**Issue:** Signature reads `def _resolve_frame_rate(cam, context) -> (Optional[str], Optional[str]):`. The parentheses form a literal tuple expression in the annotation slot, not `Tuple[Optional[str], Optional[str]]`. `from __future__ import annotations` makes this non-fatal (annotation is stringified), but inconsistent with project convention and breaks `typing.get_type_hints()`.

**Fix:**
```python
from typing import Optional, Tuple
def _resolve_frame_rate(cam, context) -> Tuple[Optional[str], Optional[str]]:
```

#### IN-02: Duplicate frame-rate mapping between `_FLAME_FPS_LABELS` (addon) and `_FPS_FROM_FRAME_RATE` (fbx_ascii)

- **Files:** `tools/blender/forge_sender/__init__.py:81-91` and `forge_flame/fbx_ascii.py:59-69`
- **Severity:** info
- **Type:** drift hazard (shared-math discipline)

**Issue:** The nine frame-rate labels + numeric fps values are defined twice. Adding `"119.88 fps"` or `"120 fps"` requires editing both; silent drift causes the addon to reject labels `v5_json_str_to_fbx` accepts, or vice versa. Same "drift hazard" CONTEXT calls out for the Euler math.

**Fix:** Either import authoritative dict from `forge_flame.fbx_ascii` and derive at module load (requires `forge_flame/` on sys.path inside Blender — not guaranteed), or add a test asserting set equality. Test-based option is safer across the install boundary.

#### IN-03: Template uses `.get_value()` on `n.name` but some Flame node types may expose `.name` as a plain str

- **Files:** `tools/blender/forge_sender/transport.py:113, 132`
- **Severity:** info
- **Type:** defensive duck-typing

**Issue:** The template does `n.name.get_value() == action_name` and `[c.name.get_value() for c in created]`. PyActionNode exposes `.name` as a PyAttribute per `memory/flame_keyframe_api.md`. But the Wave 4 SUMMARY's happy-path plural popup (`RootNode_Scene5`, `Camera1_left`, etc.) suggests `import_fbx_to_action` returns internal FBX nodes whose `.name` may be a plain str. Live UAT passed — so the assumption currently holds — but fragile.

**Fix:** Duck-type the name extraction:
```python
def _node_name(n):
    name = getattr(n, "name", None)
    return name.get_value() if hasattr(name, "get_value") else str(name)
```

## Scope and Hygiene Notes (not findings)

- **Duck-typing discipline:** `preflight.py` uses `getattr(obj, "type", None) != "CAMERA"` — correct per CLAUDE.md. `test_empty_string_type_also_fails` pins falsy-but-present `.type` still fails.
- **Security:** no `eval`, no shell interpolation. The `ast.literal_eval` in `parse_envelope` is gated on `isinstance(raw, str)` and falls back to raw string on `ValueError/SyntaxError` — correct safe-subset usage. Tempdir uses `tempfile.mkdtemp` with a prefix, no user input in path — no TOCTOU.
- **Test coverage:** 27 new unit tests + 13 shared-math tests is comprehensive for covered units. Bpy-gated tests correctly use `pytest.importorskip` per CLAUDE.md.
- **Error taxonomy:** three-tier model (preflight / transport / remote) faithfully implemented; copy matches UI-SPEC §Copywriting Contract verbatim.
- **Known Phase 4 polish items** (plural popup enumerating FBX internals, Blender `sys.modules` reload, Flame FBX importer stereo-rig expansion) correctly scoped out per the review special notes.
- **Wave 4 hotfixes** (`5cff722`, `ec93c83`) cleanly integrated: permissive `poll()` with explicit `col.enabled = False` is the canonical Blender pattern; `ast.literal_eval` on string results is the correct fix for the bridge REPL-semantics quirk.

## Files Reviewed

- `forge_flame/fbx_ascii.py` (Phase 2 delta only: `_payload_to_fbx`, `v5_json_str_to_fbx`, refactored `v5_json_to_fbx` tail)
- `tools/blender/extract_camera.py`
- `tools/blender/forge_sender/__init__.py`
- `tools/blender/forge_sender/flame_math.py`
- `tools/blender/forge_sender/preflight.py`
- `tools/blender/forge_sender/transport.py`
- `tests/test_fbx_ascii.py` (delta: `TestV5JsonStrToFbx`)
- `tests/test_extract_camera.py`
- `tests/test_forge_sender_flame_math.py`
- `tests/test_forge_sender_preflight.py`
- `tests/test_forge_sender_transport.py`

## Recommended Action

Consider running `/gsd-code-review-fix 02` to auto-apply the 2 warnings and 3 info items. All are low-risk, well-scoped fixes with clear patches. None are blockers; phase completion is unaffected.
