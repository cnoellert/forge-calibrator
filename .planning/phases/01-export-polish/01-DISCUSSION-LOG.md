# Phase 1: Export Polish - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-19
**Phase:** 01-export-polish
**Areas discussed:** Blender launch mechanism, Default .blend output path, Action resolution readback, Metadata stamping, Camera picker, Temp file handling, Error dialog policy

---

## Mode

User ran `/gsd-discuss-phase 1` in standard (discuss) mode, then asked for "recos for all with a focus on simplicity". All 7 identified gray areas were presented with Claude's recommended pick and rationale; user replied "Those work for me. Approved" — recommendations captured verbatim as decisions.

---

## 1. Blender launch mechanism (EXP-01, EXP-05)

| Option | Description | Selected |
|--------|-------------|----------|
| (a) Finder reveal only | Keep current `reveal_in_file_manager`; user double-clicks the .blend to open Blender. Minimal change but contradicts "Blender launches" wording. | |
| (b) Headless bake + separate Popen to open Blender | Keep `run_bake` untouched; after success spawn Blender on the .blend. macOS `open -a Blender [-g]` for focus control; Linux `Popen(..., start_new_session=True)`. Drop the Finder reveal on success; keep as launch-failure fallback. | ✓ |
| (c) Merge bake + open into one foreground Blender run | Single Blender invocation writes the .blend and stays open. Lower subprocess count but rewrites the tested v6.2 bake path. | |

**User's choice:** (b). Minimum delta to the tested v6.2 path; isolates launch concern; maps cleanly to `blender_launch_focus_steal`.

---

## 2. Default .blend output path (EXP-01, EXP-03)

| Option | Description | Selected |
|--------|-------------|----------|
| Fixed scratch in `/tmp` | `/tmp/forge_bakes/...` — may be cleaned by OS on reboot. | |
| `~/forge-bakes/{action}_{cam}.blend`, overwrite on collision | User-owned, durable, discoverable. Overwrite keeps the latest bake without clutter. | ✓ |
| Flame project dir | Tied to project layout; varies across sites. | |
| Config-driven path | Adds config surface for a v1 that doesn't need it. | |

**User's choice:** `~/forge-bakes/{action}_{cam}.blend`, overwrite on collision, not config-driven in v1.

---

## 3. Action resolution readback (EXP-02)

| Option | Description | Selected |
|--------|-------------|----------|
| `action.resolution` only, dialog on miss | Strict to requirement wording; no safety net. | |
| Three-tier fallback (action → batch → clip scan), hard error if all fail | Graceful degradation without silent lying. Requires live probe of `PyActionNode.resolution` shape. | ✓ |
| Silent fallback to 1920×1080 | Simple but silently ships wrong numbers — breaks the "geometrically faithful" core value. | |

**User's choice:** Three-tier fallback with hard error on total failure. Plan must include a live-Flame probe for `action.resolution` shape.

---

## 4. Metadata stamping path (EXP-04)

| Option | Description | Selected |
|--------|-------------|----------|
| (a) Extend v5 JSON with `custom_properties` dict; `bake_camera.py` applies them | One pipe, both sides already speak JSON. No new CLI surface. No second Blender subprocess. | ✓ |
| (b) Pass as CLI flags to `bake_camera.py` | Grows the CLI surface and duplicates what JSON already transports. | |
| (c) Stamp via a second Blender subprocess post-bake | Redundant Blender launch. Slower. More failure modes. | |

**User's choice:** (a). Properties stamped in v1: exactly `forge_bake_action_name` and `forge_bake_camera_name`. No version or frame-range stamping yet.

---

## 5. Camera picker when Action has multiple non-Perspective cameras

| Option | Description | Selected |
|--------|-------------|----------|
| Keep current (auto-pick if 1, dialog if ≥2) | Zero-dialog happy path applies to the 1-camera case. Multi-cam is rare; fidelity matters more than one extra click. | ✓ |
| Auto-pick first always | Silent failure mode when user intended the other camera. Fidelity-risky. | |
| Always dialog | Breaks the zero-dialog promise. | |

**User's choice:** Keep current behavior unchanged.

---

## 6. Temp file cleanup (EXP-03)

| Option | Description | Selected |
|--------|-------------|----------|
| `tempfile.mkdtemp(prefix="forge_bake_")` + try/finally; cleanup on success; keep on failure and log path in error dialog | Matches EXP-03 exactly. Failure path gives debug artifacts for free without cluttering `~/forge-bakes/`. | ✓ |
| Always cleanup | Loses debug artifacts on failure. | |
| Copy intermediates next to .blend on failure | Clutters the user-visible directory. | |

**User's choice:** Cleanup on success only; keep temp dir on failure and surface its path in the error dialog.

---

## 7. Error dialog policy

| Option | Description | Selected |
|--------|-------------|----------|
| Keep existing `flame.messages.show_in_dialog` on all error paths | Zero-dialog is a happy-path goal, not a silencing rule. Errors must be visible. No change to working behavior. | ✓ |
| Swap to console-only + non-blocking toast | Artists don't watch Flame's console; failures would go invisible. | |
| Structured return + caller decides | Over-engineered for a single call site. | |

**User's choice:** No change. Keep `flame.messages.show_in_dialog` on error paths.

---

## Claude's Discretion

- v5 JSON schema: exact key name / nesting for `custom_properties` (top-level vs. `meta.custom_properties`) — pick during planning
- Whether `fbx_to_v5_json` grows a passthrough parameter vs. the hook stamps post-conversion — pick during planning
- Error message wording for resolution-readback failure
- Single vs. per-invocation read of `blender_launch_focus_steal` from `.planning/config.json`

## Deferred Ideas

- POLISH-01: "Last .blend per Action" memory (v2)
- POLISH-02: Version stamping into custom properties (v2)
- MULT-01: Multi-camera export (v2)
- Config-driven output path override (not needed for v1)
- Finder reveal as a user-triggered action (POLISH-03 territory)
