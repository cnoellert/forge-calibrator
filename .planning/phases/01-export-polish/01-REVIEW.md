---
phase: 01-export-polish
reviewed: 2026-04-19T22:40:00Z
depth: standard
files_reviewed: 4
files_reviewed_list:
  - flame/camera_match_hook.py
  - forge_flame/fbx_ascii.py
  - tests/test_fbx_ascii.py
  - tools/blender/bake_camera.py
findings:
  critical: 0
  warning: 2
  info: 4
  total: 6
status: issues_found
---

# Phase 01: Code Review Report

**Reviewed:** 2026-04-19T22:40:00Z
**Depth:** standard
**Files Reviewed:** 4
**Status:** issues_found

## Summary

Phase 01 delivered a solid zero-dialog rewrite of `_export_camera_to_blender`, a
well-bounded `custom_properties` passthrough through `fbx_to_v5_json` and
`_stamp_metadata`, and defense-in-depth helpers (`_sanitize_name_component`,
`_infer_plate_resolution`, `PlateResolutionUnavailable`, `_launch_blender_on_blend`,
`_read_launch_focus_steal`). The code is well-documented, carefully rationalised
against the plan's decisions (D-02/D-07/D-08/D-11/D-14), argv-list subprocess
calls are used consistently (no shell expansion), and the happy path is
genuinely dialog-free when a single non-Perspective camera is present.

Two warnings flag correctness risks that could bite the round-trip guarantee
(reserved-key collision in `_stamp_metadata`) and filesystem safety edge cases
(`_sanitize_name_component` lets `.` / `..` / `---` pass through verbatim).
Four info items note minor code-quality issues: inaccurate rationale comment,
an unused Optional import in bake_camera.py's type hint pattern, a redundant
`os` import inside the handler, and test coverage gaps for non-happy-path
custom_properties inputs.

No critical issues found. No security vulnerabilities in the narrow sense
(argv-list subprocess, 127.0.0.1 trust envelope per CLAUDE.md, no shell
expansion, no eval, no hardcoded secrets). All Flame rotation-convention
call sites are unchanged by this phase.

## Warnings

### WR-01: Reserved `forge_bake_*` keys can be overwritten by caller-supplied `custom_properties`

**File:** `tools/blender/bake_camera.py:167-173`
**Issue:** `_stamp_metadata` writes the reserved round-trip stamps
(`forge_bake_version`, `forge_bake_source`, `forge_bake_scale`,
`forge_bake_input_path`) **before** applying `custom_properties`. A caller
(or a malicious/buggy upstream JSON producer) can clobber these by passing
`custom_properties={"forge_bake_scale": 999}` in the v5 JSON.

This matters because `extract_camera.py` reads `forge_bake_scale` and
multiplies position back up for the lossless round-trip that CLAUDE.md
identifies as the tool's core value ("geometrically faithful to the plate,
and the Flame-Blender round-trip must preserve that fidelity end-to-end").
A silently clobbered scale produces geometrically wrong cameras with no
warning. Phase 2's "Send to Flame" addon will also read these properties
for provenance checks; overwriting `forge_bake_source` from `"flame"` to
anything else silently breaks the provenance gate.

Today the only caller is the trusted hook on the same machine, so this is
a defensive-coding issue rather than an exploit, but the JSON file sits on
disk between bake and extract (and may be shared/edited) — the trust
boundary is not purely in-process.

**Fix:** Reverse the precedence so reserved keys win, or reject reserved keys
explicitly:

```python
_RESERVED_KEYS = {
    "forge_bake_version",
    "forge_bake_source",
    "forge_bake_scale",
    "forge_bake_input_path",
}

def _stamp_metadata(
    cam_data: bpy.types.Camera,
    scale: float,
    source_path: str,
    custom_properties: Optional[dict] = None,
) -> None:
    # Apply caller properties first, then overwrite with reserved stamps so
    # the round-trip scale/provenance invariants cannot be clobbered.
    if custom_properties:
        for key, value in custom_properties.items():
            if key in _RESERVED_KEYS:
                print(
                    f"bake_camera: ignoring reserved custom_properties "
                    f"key {key!r} (would clobber round-trip stamp)",
                    file=sys.stderr,
                )
                continue
            cam_data[key] = value
    cam_data["forge_bake_version"] = 1
    cam_data["forge_bake_source"] = "flame"
    cam_data["forge_bake_scale"] = scale
    cam_data["forge_bake_input_path"] = os.path.abspath(source_path)
```

Mirror the same guard in `forge_flame/fbx_ascii.py::fbx_to_v5_json` only if
you plan to stamp reserved keys at that layer (currently it doesn't, so the
JSON layer is fine — the risk is localised to the Blender bake step).

### WR-02: `_sanitize_name_component` allows `.`, `..`, and all-punctuation names to pass through

**File:** `flame/camera_match_hook.py:1822-1850`
**Issue:** The regex whitelist `[A-Za-z0-9._-]` correctly scrubs shell
metacharacters, but it lets these edge cases through unchanged:

- `.`   -> `.`     (becomes `._{cam}.blend` — legal but surprising)
- `..`  -> `..`    (becomes `.._{cam}.blend` — legal but resembles traversal)
- `...` -> `...`   (becomes `..._{cam}.blend`)
- `---` -> `---`   (kept; only all-underscore triggers the `unnamed` fallback)
- `.hidden` -> `.hidden` (creates a hidden dotfile on Unix)

The `safe.strip("_")` fallback check only catches all-underscore results, not
all-punctuation results. The composite filename pattern
`{safe_action}_{safe_cam}.blend` does prevent actual path escape (because
the `.blend` suffix and the underscore separator anchor the name inside
`~/forge-bakes/`), so this is NOT a critical path traversal. But:

1. A Flame Action literally named `.` gives `~/forge-bakes/._Cam.blend`, a
   macOS AppleDouble sidecar-looking file that some tools filter out.
2. A camera named `.hidden` silently creates a dotfile that `ls` hides,
   confusing users trying to locate their export.
3. The docstring on line 1833 explicitly calls out `..`-chain traversal as a
   concern the helper defends against — but it doesn't actually collapse `..`.

**Fix:** Extend the fallback predicate to reject names that are all
punctuation or start with `.`:

```python
_SANITIZE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]")

def _sanitize_name_component(name: str) -> str:
    safe = _SANITIZE_NAME_RE.sub("_", str(name))[:64]
    # Strip leading dots (no hidden files) and require at least one alnum.
    safe = safe.lstrip(".")
    if not any(c.isalnum() for c in safe):
        return "unnamed"
    return safe
```

Add a unit test in `tests/test_camera_match_hook.py` (or a new module)
covering: `"."`, `".."`, `"..."`, `"---"`, `".hidden"`, and the existing
happy-path `"Action_01"`. This helper is currently untested despite being
on the security-adjacent path.

## Info

### IN-01: `_export_camera_to_blender` n_frames-vs-cleanup comment is misleading

**File:** `flame/camera_match_hook.py:2087, 2150-2154`
**Issue:** The comments at lines 2087 and 2150-2154 claim reading `json_path`
after `success = True` would "race the cleanup". That is not accurate — the
cleanup runs inside the `finally:` block (line 2163-2167) which executes only
AFTER the `try:` body has finished. Reading `json_path` after `success = True`
but still inside the `try:` body would be safe. The code ordering as written
works correctly; the rationale in the comment is just wrong and will confuse
a future maintainer who reaches for the comment as authoritative.

**Fix:** Rewrite the comment to state the real reason: the frame-count read
is cosmetic and was placed here to keep the "everything worked" flag
assignment as the last statement in the try body:

```python
# Frame count for the info dialog. Kept inside the try block because
# the tempfile lives until `finally` runs; the `success = True`
# assignment below must be the last statement in the try body so
# the finally-block cleanup correctly mirrors "try succeeded".
```

### IN-02: Redundant `import os` inside `_export_camera_to_blender`

**File:** `flame/camera_match_hook.py:2023` (also present at 249)
**Issue:** `os` is imported at module top (line 16) and re-imported inside
the handler body. This is pre-existing style in this file (line 249 does
the same), and Python's import cache makes it free, but it adds noise.
Not introduced by this phase but inherited in the rewritten handler.

**Fix:** Remove `import os` from the handler body. The module-top import
is in scope.

### IN-03: `from typing import Optional` added but `| None` style would match project convention elsewhere

**File:** `tools/blender/bake_camera.py:63`
**Issue:** Other files in this repo (e.g. `forge_flame/fbx_io.py`,
`forge_core/solver/solver.py`) use `from __future__ import annotations`
with `Optional[X]` via `typing.Optional`. `bake_camera.py` does NOT use
`from __future__ import annotations` (it's a standalone Blender script),
so `Optional` at runtime is required. This is correct. However the
CLAUDE.md convention note says "Generic types use `from typing import
Optional, Tuple, Sequence`", and `bake_camera.py` only needed `Optional`,
which it added — so this is consistent.

This is a non-issue; flagged only to confirm the review traced the import
and the pattern is right.

**Fix:** None required.

### IN-04: Test coverage gap — new helpers have no unit tests

**File:** `flame/camera_match_hook.py:1797-1981`
**Issue:** The four new module-level helpers — `_read_launch_focus_steal`,
`_sanitize_name_component`, `_infer_plate_resolution`,
`_launch_blender_on_blend` — have no unit tests in `tests/`. The phase
summary mentions a smoke test (01-04-SMOKE.md) but only
`fbx_to_v5_json(custom_properties=...)` has per-unit coverage.

Each helper is cleanly unit-testable:

- `_read_launch_focus_steal`: pass via monkeypatched `__file__` / tmp config.
- `_sanitize_name_component`: pure function, no Flame dependency — perfect
  unit test target (see WR-02 for specific cases to cover).
- `_infer_plate_resolution`: use a mock `action_node` and monkeypatch
  `flame` module + `_scan_first_clip_metadata` to exercise all three tiers
  and the `PlateResolutionUnavailable` path.
- `_launch_blender_on_blend`: patch `subprocess.Popen` and assert argv
  shape for darwin/linux/other.

Without these, regressions in the filesystem-safety and resolution-fallback
paths won't be caught until the next live-Flame smoke.

**Fix:** Add `tests/test_camera_match_hook.py` covering at minimum:

- `_sanitize_name_component` with WR-02's edge cases plus happy path.
- `_infer_plate_resolution` tier fallback order and the Unavailable raise.
- `_launch_blender_on_blend` argv shape per platform (patch `sys.platform`
  and `subprocess.Popen`).
- `_read_launch_focus_steal` with missing file, malformed JSON, key
  absent, key true, key false.

---

_Reviewed: 2026-04-19T22:40:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
