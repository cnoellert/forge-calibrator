# Phase 1: Export Polish - Context

**Gathered:** 2026-04-19
**Status:** Ready for planning

<domain>
## Phase Boundary

Rework the Flame-side `_export_camera_to_blender` handler (`flame/camera_match_hook.py:1793`) so that right-click → "Export Camera to Blender" runs end-to-end with zero dialogs on the happy path, intermediate `.fbx`/`.json` files are written to a `tempfile.mkdtemp()` dir and cleaned on success, the exported Blender camera carries `forge_bake_action_name` + `forge_bake_camera_name` custom properties, and Blender launches on the output `.blend` with focus-steal behavior controlled by `.planning/config.json`.

**In scope:** the export handler, v5 JSON schema extension for custom properties, `bake_camera.py` stamping the properties, Blender launch spawn, Action-resolution probe.

**Out of scope** (belongs to later phases or v2):
- Any Blender-side "Send to Flame" UI (Phase 2)
- forge-bridge autostart / lifecycle (Phase 3)
- Multi-camera export (MULT-01)
- "Last .blend per Action" memory (POLISH-01)
- Version stamping beyond the two named properties (POLISH-02)
- Config-driven output path override

</domain>

<decisions>
## Implementation Decisions

### Blender launch mechanism (EXP-01, EXP-05)
- **D-01:** Keep the existing headless `run_bake` path unchanged; after a successful bake, spawn Blender separately to open the `.blend`. This preserves the tested v6.2 bake path and isolates the launch concern.
- **D-02:** Launch mechanics:
  - macOS: `open -a Blender <path>` when `blender_launch_focus_steal=true`; `open -a -g Blender <path>` when `false` (default).
  - Linux: `subprocess.Popen([blender_bin, path], start_new_session=True)` regardless of the flag; Linux focus behavior is WM-dependent and documented as best-effort.
- **D-03:** Drop the `reveal_in_file_manager` call on the success path (Blender itself is the reveal). Keep it as a fallback only when the Blender launch spawn fails.

### Default `.blend` output path (EXP-01, EXP-03)
- **D-04:** Default output location is `~/forge-bakes/{action}_{cam}.blend`. `os.makedirs(..., exist_ok=True)` at export time. User-owned, survives reboots, easy to find.
- **D-05:** Collision policy: overwrite existing files with the same name. Freshest bake wins; artists who need to keep an older bake rename it before re-baking.
- **D-06:** Not config-driven in v1. If anyone asks for a custom path, revisit in a later milestone.

### Action resolution readback (EXP-02)
- **D-07:** Three-tier fallback chain for plate resolution:
  1. `action.resolution.get_value()` (primary — per EXP-02)
  2. `flame.batch.width.get_value()` / `flame.batch.height.get_value()` (fallback; pattern already used in `flame/apply_solve.py:269`)
  3. `_scan_first_clip_metadata()` on any clip in `flame.batch.nodes` (final fallback)
- **D-08:** If all three fail, raise an error dialog explaining the condition — never fall back silently to a hard-coded 1920×1080. Geometric fidelity is the core value; silent defaults break that contract.
- **D-09:** The plan MUST include a live-Flame probe task (via forge-bridge, per `memory/flame_bridge_probing.md`) to confirm the shape of `PyActionNode.resolution` before the implementation task begins. STATE.md already flags this as unresolved.

### Metadata stamping (EXP-04)
- **D-10:** Extend the v5 JSON contract with a top-level `custom_properties` dict (`{str: str|int|float}`). `tools/blender/bake_camera.py` reads it and applies each entry to the bpy camera's `["key"] = value` custom-property slot after the camera is created/updated.
- **D-11:** Properties stamped in v1: exactly `forge_bake_action_name` and `forge_bake_camera_name`. No other fields yet. Version stamping (POLISH-02) and frame-range stamping remain deferred.
- **D-12:** The Flame-side handler writes the two property values into the v5 JSON. `fbx_to_v5_json` (`forge_flame/fbx_ascii.py:725`) may need a thin passthrough parameter to accept the dict — decide during planning (alternative: stamp the JSON after `fbx_to_v5_json` returns, purely in the hook).

### Camera picker when Action holds multiple cameras
- **D-13:** Keep the current picker behavior: auto-select when the Action has exactly one non-Perspective camera; show the picker dialog when there are two or more. Zero-dialog spec applies to the 1-camera happy path; silently auto-picking in multi-cam Actions would risk breaking fidelity on the wrong camera.

### Temp file handling (EXP-03)
- **D-14:** Intermediates go to `tempfile.mkdtemp(prefix="forge_bake_")`. On a successful export, the temp dir is removed; only the `.blend` in `~/forge-bakes/` remains visible. On any failure, the temp dir is preserved and its path is included in the error dialog so the user (or support) can inspect the intermediate `.fbx`/`.json`.

### Error dialog policy
- **D-15:** Existing `flame.messages.show_in_dialog` error handling stays. "Zero dialogs" is a happy-path goal — error paths still need to surface visibly. No new console-only or toast paths in this phase.

### Claude's Discretion
- Exact placement of the `custom_properties` key inside the v5 JSON schema (top-level vs. nested under `meta`) — decide during planning.
- Whether `fbx_to_v5_json` grows a parameter vs. the hook stamps post-conversion — decide during planning.
- Error message wording for the resolution-readback failure dialog.
- Whether `blender_launch_focus_steal` is read once at handler start or re-read per invocation — pick whichever is simpler.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements / project docs
- `.planning/REQUIREMENTS.md` §Export (EXP-01…EXP-05)
- `.planning/PROJECT.md` §Active, §Key Decisions (focus-steal default, temp cleanup, ASCII FBX route)
- `.planning/STATE.md` §Blockers/Concerns (Action.resolution probe flagged)
- `.planning/ROADMAP.md` Phase 1 success criteria

### Code to modify
- `flame/camera_match_hook.py:1793` — `_export_camera_to_blender` handler (primary target)
- `flame/camera_match_hook.py:1756` — `_scan_first_clip_metadata` (reused as third-tier fallback)
- `flame/camera_match_hook.py:1779` — `_pick_camera` (unchanged, keep behavior)
- `tools/blender/bake_camera.py` — add `custom_properties` application on the bpy camera
- `forge_flame/fbx_ascii.py:725` — `fbx_to_v5_json` (possible `custom_properties` passthrough)

### Code to reference (unchanged)
- `forge_flame/blender_bridge.py:218` — `run_bake` (headless bake, unchanged)
- `forge_flame/blender_bridge.py:260` — `reveal_in_file_manager` (fallback only on launch failure)
- `forge_flame/fbx_io.py:109` — `export_action_cameras_to_fbx` (unchanged)
- `flame/apply_solve.py:269` — existing `flame.batch.width/height` pattern (reused for fallback)
- `forge_flame/wiretap.py:148` — existing `tempfile.TemporaryDirectory` pattern

### Memory docs (gotchas that must be respected)
- `~/.claude/projects/-Users-cnoellert-Documents-GitHub-forge-calibrator/memory/flame_keyframe_api.md` — why FBX is the animated route
- `~/.claude/projects/-Users-cnoellert-Documents-GitHub-forge-calibrator/memory/flame_perspective_camera.md` — filter Perspective camera out
- `~/.claude/projects/-Users-cnoellert-Documents-GitHub-forge-calibrator/memory/flame_bridge_probing.md` — probing discipline for the `action.resolution` live check
- `~/.claude/projects/-Users-cnoellert-Documents-GitHub-forge-calibrator/memory/flame_bridge.md` — forge-bridge exec endpoint for probing

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `forge_flame/blender_bridge.run_bake` — headless Blender baking, works as-is.
- `forge_flame/fbx_io.export_action_cameras_to_fbx` — FBX export with Perspective exclusion + selection save/restore.
- `forge_flame/fbx_ascii.fbx_to_v5_json` — FBX → v5 JSON converter; likely needs one passthrough parameter.
- `_scan_first_clip_metadata` (`camera_match_hook.py:1756`) — already returns `(w, h, start_frame)` from any batch clip; fits as the third-tier fallback.
- `tempfile.TemporaryDirectory` pattern in `forge_flame/wiretap.py:148` — same idiom applies to the export handler.
- `flame.batch.width/height.get_value()` pattern in `flame/apply_solve.py:269` — reuse for the batch-level fallback.

### Established Patterns
- Error surfacing via `flame.messages.show_in_dialog` — keep using it.
- Duck-typing on Flame objects (`hasattr` over `isinstance`) — apply when probing `action.resolution`.
- Module docstrings explain "why this module exists" and gotchas — the reworked handler must follow suit.
- v5 JSON contract is the bridge between FBX converters and Blender scripts — extend it, do not bypass.

### Integration Points
- `.planning/config.json` gains one new key: `blender_launch_focus_steal` (bool, default `false`).
- `tools/blender/bake_camera.py` grows a `custom_properties` read path (no new CLI surface required).
- No new files required in `forge_flame/`; the launch spawn lives in the hook (or a small helper in `blender_bridge.py` if planning decides it is cleaner there).

</code_context>

<specifics>
## Specific Ideas

- User repeatedly emphasized **simplicity** over flexibility. When planning this phase, prefer fewest-lines-of-change and reuse over new abstractions or configuration surface.
- The zero-dialog spec is a happy-path promise, not a silencing rule — errors still dialog.
- Silent fallbacks on plate resolution are forbidden. Fidelity trumps frictionless UX here.
- User-visible surface after a successful export: the `.blend` file + Blender window. That's it. No Finder reveal, no temp artifacts, no extra toasts.

</specifics>

<deferred>
## Deferred Ideas

- **POLISH-01** — "Last .blend per Action" memory (v2)
- **POLISH-02** — Stamp bridge + hook versions into custom properties (v2)
- **MULT-01** — Multi-camera export from one Action (v2)
- **Config-driven output path override** — raised as a "could" during discussion; not needed for v1. Revisit only if an artist asks.
- **Finder reveal as a user action** — POLISH-03 territory; out of scope here.

</deferred>

---

*Phase: 01-export-polish*
*Context gathered: 2026-04-19*
