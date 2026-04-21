# Phase 2: Blender Addon - Context

**Gathered:** 2026-04-21
**Status:** Ready for planning

<domain>
## Phase Boundary

Build the "Send to Flame" Blender addon that reads stamped metadata from a forge-baked camera, extracts per-frame T/R/focal/film-back to the v5 JSON contract, and POSTs to forge-bridge to trigger `v5_json_to_fbx` + `import_fbx_to_action` inside Flame's Python — completing the return trip without the user visiting Flame's batch menu (IMP-06).

**In scope:** Blender addon directory package (`tools/blender/forge_sender/`); shared Euler/axis-swap/keyframe-walk math extracted from `extract_camera.py`; new `v5_json_str_to_fbx` sibling in `forge_flame/fbx_ascii.py` for in-memory JSON; bridge-side target-Action resolution + `flame.batch.frame_rate` probe; N-panel UI + operator + preflight validation + HTTP transport + info-popup surfacing; pre-work verification sweep for the Phase 1 multi-camera picker (FOLDED-01).

**Out of scope** (belongs to later phases or v2):
- forge-bridge autostart / lifecycle (Phase 3, BRG-01…BRG-04)
- `install.sh` deploying the addon zip — artists install manually (Phase 4 docs cover this)
- User-facing docs / troubleshooting recipes (Phase 4, DOC-02)
- E2E smoke test on Flame 2026.2.1 + Blender 4.5+ (Phase 4, DOC-01)
- Multi-camera round-trip in one send (MULT-01, v2)
- Lights / meshes / materials in the return trip (Out of Scope)
- "Last .blend per Action" memory, extra version stamps (POLISH-01, POLISH-02)
- Phase 1 export handler changes — Phase 1 stays closed; D-15 picks the frame-rate path that needs no Phase 1 churn

</domain>

<decisions>
## Implementation Decisions

### JSON transport to Flame (IMP-04)
- **D-01:** Add a new sibling function `v5_json_str_to_fbx(json_str, out_fbx_path, *, camera_name, frame_rate, pixel_to_units)` in `forge_flame/fbx_ascii.py` alongside the existing `v5_json_to_fbx` at line 1230. The new function parses with `json.loads(json_str)` and reuses the existing template-mutate emit path unchanged. The file-path variant stays as-is for CLI callers (`roundtrip_selftest.sh`, `extract_camera.py` consumers, anyone scripting).
- **D-02:** The addon serializes its v5 JSON dict via `json.dumps()` and POSTs to forge-bridge at `http://127.0.0.1:9999/exec`. The bridge body is the standard `{"code": "<python>"}` contract per `memory/flame_bridge_probing.md`; the Flame-side Python string passes the JSON payload into `v5_json_str_to_fbx` and then into `import_fbx_to_action`. The exact embedding mechanism (JSON literal inside the `code` string vs bridge-exposed payload context) is Claude's Discretion — both are single-body POSTs.
- **D-03:** Bridge-side scratch directory uses `tempfile.mkdtemp(prefix="forge_send_")` for the intermediate `.fbx`. On success, the dir is removed; on failure, the dir path is included in the bridge response so it can surface in the Blender popup for forensic inspection. Mirrors Phase 1 D-14.

### Extraction logic location (IMP-03)
- **D-04:** The per-frame Blender→v5 math lives in a single shared module `tools/blender/forge_sender/flame_math.py` containing: `_rot3_to_flame_euler_deg`, the `_R_Z2Y` axis-swap matrix, `_resolve_scale`, `_camera_keyframe_set`, and the frame-walk loop that builds the `frames` list for the v5 JSON. Both the addon operator and `tools/blender/extract_camera.py` import from this module.
- **D-05:** `extract_camera.py` refactors to import from `flame_math.py` via a `sys.path.insert(0, os.path.join(os.path.dirname(__file__), "forge_sender"))` shim at the top of the file. The math body moves out of `extract_camera.py` into `flame_math.py`; `extract_camera.py` keeps only CLI/argparse + orchestration. All existing tests covering the round-trip math must still pass after the move.

### Target Action resolution on the Flame side (IMP-02, IMP-04)
- **D-06:** Bridge-side resolution scope is the **current batch only** — iterate `flame.batch.nodes`, filter for PyActionNode via duck-typing (`hasattr(n, "import_fbx")`), match by exact name against the stamped `forge_bake_action_name`.
- **D-07:** Count policy is fail-loud:
  - 0 matches → bridge returns `error`: `"No Action named '{name}' in current batch — was it renamed or deleted?"`
  - 1 match → proceed with `import_fbx_to_action`
  - 2+ matches → bridge returns `error`: `"Ambiguous: {N} Actions named '{name}' — rename to disambiguate and resend"`
- **D-08:** No fuzzy matching, no cross-batch scanning, no auto-pick on ambiguity. Silent fallback on a geometric-fidelity tool violates Core Value. Carries forward the Phase 1 D-08 principle ("fidelity trumps frictionless UX").

### Error taxonomy + popup surface (IMP-02, IMP-05)
- **D-09:** Three-tier error model surfaced in Blender via operator `self.report({'ERROR'}, ...)` + `bpy.ops.wm.info` popups:
  1. **Preflight (addon-side, before POST)** — distinct popup text for each:
     - (a) No active object in the 3D viewport
     - (b) Active object is not a camera (`obj.type != 'CAMERA'`)
     - (c) Active camera missing `forge_bake_action_name` or `forge_bake_camera_name` on `cam.data` — the popup names the missing key verbatim (IMP-02 literal requirement)
     - (d) `cam.data["forge_bake_source"] != "flame"` — provenance guard; rejects non-forge-baked cameras that happen to have some custom properties set
  2. **Transport (addon-side, POST failed)** — single popup on `requests.ConnectionError` / `Timeout`: `"forge-bridge not reachable at 127.0.0.1:9999 — is Flame running?"`
  3. **Remote (bridge returned `error` or `traceback` in its response envelope)** — single generic popup formatted as `"Send failed: {error}\n\n{traceback}"`, using the `error` and `traceback` fields from the bridge response per `memory/flame_bridge.md`. No per-exception-class parsing on the addon side — let the Flame traceback speak.
- **D-10:** Success popup format: `"Sent to Flame: camera '{created_name}' in Action '{action_name}'"`. The bridge response includes the created camera name(s) returned by `import_fbx_to_action` (which returns a list of newly created nodes).

### Packaging + install (IMP-01)
- **D-11:** The addon is a directory package committed at `tools/blender/forge_sender/` with these files:
  - `__init__.py` — `bl_info` (version `(1, 0, 0)`, category `"Import-Export"`, `"blender": (4, 5, 0)`), `register()` / `unregister()` wiring, class imports.
  - `flame_math.py` — shared Euler / axis-swap / keyframe-walk helper (D-04).
  - `transport.py` — `requests.post()` call, JSON payload construction, bridge-response parsing.
  - `preflight.py` — local validation returning either `None` or an error message (D-09 Tier 1).
  - Operator + panel classes: Claude's Discretion whether they live in `__init__.py` or split into `operator.py` / `panel.py`.
- **D-12:** The installable zip is produced by a trivial shell command (`cd tools/blender && zip -r forge_sender-v1.0.0.zip forge_sender/`) and distributed to artists by whatever means the team uses (email, internal file share). `install.sh` does NOT drop the addon — `install.sh` owns `/opt/Autodesk/shared/python/` (Flame-side deploy) and mixing Blender-side artifacts muddies that contract. Clear install docs (Phase 4) suffice: artists / pipeline TDs know how to install a Blender addon from a zip.
- **D-13:** `requests` is bundled with Blender 4.5's Python (no `pip install` inside Blender). If a future Blender bundle drops it, fall back to `urllib.request` per Claude's Discretion.

### Panel UI scope (IMP-01)
- **D-14:** N-panel tab name: `Forge`. Panel rows, top-to-bottom:
  ```
  Target Action: {forge_bake_action_name}
  Target Camera: {forge_bake_camera_name}
  [     Send to Flame     ]
  ```
- **D-15:** If preflight Tier 1 fails (no active camera / missing metadata / wrong provenance), the two metadata labels are replaced with a single warning row `⚠ Not a Flame-baked camera` and the Send button is disabled (operator `poll()` returns False). No config surface, no override inputs — the artist's signal is "bake from Flame to get a valid return-trip camera" and the absence of valid metadata is itself the diagnostic.

### Send semantics — sync vs async (IMP-04)
- **D-16:** Operator is a standard synchronous Blender operator (not modal). Single `requests.post(url, json=..., timeout=5)` call, wrapped in `try/except (requests.exceptions.ConnectionError, requests.exceptions.Timeout)`. Typical round-trip is sub-second; a 500 ms Blender freeze is invisible to the artist; 5 s gives a clean failure mode when the bridge is down. No worker threads, no bpy thread-safety landmines.

### Frame-rate round-trip fidelity
- **D-17:** Bridge-side Python queries `flame.batch.frame_rate.get_value()` at import time and passes the returned string to `v5_json_str_to_fbx(..., frame_rate=<value>)`. Frame rate is a property of the Flame session, not Blender — querying at import is the source-of-truth approach and keeps Phase 1's export handler closed (no revisit of D-11 in Phase 1 CONTEXT).
- **D-18:** Before the implementation tasks run, a forge-bridge probe task MUST confirm the API shape: that `flame.batch.frame_rate` exists, that `.get_value()` returns a string (and ideally one of the keys already in `forge_flame.fbx_ascii._FPS_FROM_FRAME_RATE`), and that unexpected strings trigger a clean error rather than a silent fallback to 24 fps. Follow `memory/flame_bridge_probing.md`: one probe per request, ping-only first, save findings to memory before asking for a Flame restart.
- **D-19:** If the probed shape turns out to be incompatible (no `frame_rate` on batch, returns a float, fails to match the `_FPS_FROM_FRAME_RATE` keys), fall back to stamping `forge_bake_frame_rate` as a Phase 1 supplement via a quick task. This is a contingency, not the default path — D-17 is the working assumption.

### Folded Todos

- **FOLDED-01:** `.planning/todos/pending/2026-04-21-verify-multi-camera-picker-in-live-uat.md` — folded into Phase 2 scope as a pre-implementation verification sweep. Rationale: the Phase 2 round-trip lands on whichever camera was selected at Phase 1 export time; if the picker silently chose the wrong camera in a multi-camera Action, Phase 2 would import onto an unintended Flame target without the artist noticing. The 4-check sweep (Perspective absent from picker, deterministic order, cancel aborts cleanly, `forge_bake_camera_name` matches selection) must run before Phase 2 implementation begins. On completion, close the todo and note the result in the phase SUMMARY.

### Claude's Discretion

Items the planner/executor can decide without re-consulting the user:
- Whether operator and panel classes live in `__init__.py` or split into `operator.py` / `panel.py`.
- Exact embedding of the v5 JSON payload in the bridge `{"code": "..."}` body — JSON literal inside the code string vs bridge-exposed payload context object. Bridge mechanics per `memory/flame_bridge.md`.
- Exact popup wording within the D-09 structure (must name the missing key in Tier 1(c), must include the bridge URL in Tier 2, must include Flame's traceback verbatim in Tier 3).
- HTTP timeout if 5 s proves too short during live validation — planner may bump to 10 s.
- N-panel tab category string (default `Forge`); if convention dictates another name, planner may adjust.
- `requests` vs `urllib.request` for the HTTP transport — `requests` preferred; `urllib` acceptable fallback.
- Whether the bridge returns the created camera name(s) as a single string, a list, or a mapping — pick whatever makes D-10's popup formatting cleanest.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements / project docs
- `.planning/REQUIREMENTS.md` §Import (IMP-01…IMP-06)
- `.planning/PROJECT.md` §Active, §Key Decisions, §Constraints, §Out of Scope
- `.planning/ROADMAP.md` Phase 2 Success Criteria (4 items)
- `.planning/STATE.md` §Blockers/Concerns (forge-bridge interface coordination, 2100-LOC hook monolith)

### Prior phase context (locked decisions carried forward)
- `.planning/phases/01-export-polish/01-CONTEXT.md` — stamping contract (D-10/D-11), v5 JSON schema extension, tempdir-cleanup-on-success pattern (D-14), silent-fallback ban (D-08), error-dialog convention (D-15)

### Code to modify
- `forge_flame/fbx_ascii.py` — add `v5_json_str_to_fbx` sibling near `v5_json_to_fbx` at line 1230
- `tools/blender/extract_camera.py` — refactor to import shared math from `forge_sender/flame_math.py` (D-05)
- `tools/blender/forge_sender/` — NEW directory package: `__init__.py`, `flame_math.py`, `transport.py`, `preflight.py` (+ optional `operator.py`, `panel.py`)

### Code to reference (unchanged)
- `forge_flame/fbx_io.py:173` — `import_fbx_to_action` signature; bridge-side target for D-06/D-07 resolution logic
- `forge_flame/fbx_ascii.py:1230` — `v5_json_to_fbx` (reference for the string-input sibling; shares everything below `json.load`)
- `forge_flame/fbx_ascii.py:57-87` — `_FPS_FROM_FRAME_RATE`, `ktime_per_frame`, `ktime_from_frame` (frame-rate string format reference for D-18)
- `tools/blender/bake_camera.py:145-202` — `_RESERVED_STAMP_KEYS`, `_stamp_metadata`; what's on `cam.data`, what the addon reads back
- `tools/blender/extract_camera.py:90-146` — reference math + keyframe walker that moves into `flame_math.py`
- `flame/camera_match_hook.py:2090-2194` — Phase 1 export handler (stamping pipeline, tempdir pattern, error-dialog convention to mirror)

### Memory docs (gotchas that must be respected)
- `~/.claude/projects/-Users-cnoellert-Documents-GitHub-forge-calibrator/memory/flame_bridge.md` — forge-bridge `/exec` endpoint + response envelope (`result`, `stdout`, `stderr`, `error`, `traceback`)
- `~/.claude/projects/-Users-cnoellert-Documents-GitHub-forge-calibrator/memory/flame_bridge_probing.md` — JSON payload contract + probing discipline for the D-18 frame-rate probe
- `~/.claude/projects/-Users-cnoellert-Documents-GitHub-forge-calibrator/memory/flame_keyframe_api.md` — why animated I/O goes through FBX (context for `v5_json_to_fbx` existence)
- `~/.claude/projects/-Users-cnoellert-Documents-GitHub-forge-calibrator/memory/flame_perspective_camera.md` — Perspective cam exclusion rule (relevant to FOLDED-01 picker sweep)
- `~/.claude/projects/-Users-cnoellert-Documents-GitHub-forge-calibrator/memory/flame_rotation_convention.md` — Flame Euler ZYX convention (used by `flame_math.py`)
- `~/.claude/projects/-Users-cnoellert-Documents-GitHub-forge-calibrator/memory/flame_fbx_bake_semantics.md` — KTime pre-roll / trailing artifact handling (frame-rate related)

### Related todo (folded into scope)
- `.planning/todos/pending/2026-04-21-verify-multi-camera-picker-in-live-uat.md` — 4-check picker verification sweep (FOLDED-01)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `forge_flame/fbx_ascii.v5_json_to_fbx` — template-mutate emit path; the new string-input sibling shares all of it after `json.loads(json_str)` replaces the file read.
- `forge_flame/fbx_io.import_fbx_to_action` — already carries the right defaults for the return trip (cameras only, `create_media=False`, `auto_fit=False`, `bake_animation=False` since the FBX already has baked AnimCurves).
- `forge_flame/fbx_ascii._FPS_FROM_FRAME_RATE` — the authoritative mapping for frame-rate strings Flame emits; D-18 probe must confirm `flame.batch.frame_rate.get_value()` returns one of these keys.
- `tools/blender/extract_camera.py:90-111` — `_rot3_to_flame_euler_deg` (moves into `flame_math.py`).
- `tools/blender/extract_camera.py:114-116` — `_R_Z2Y` axis-swap matrix (moves into `flame_math.py`).
- `tools/blender/extract_camera.py:124-146` — `_camera_keyframe_set` frame walker (moves into `flame_math.py`).
- `tools/blender/extract_camera.py:154-164` — `_resolve_scale` (moves into `flame_math.py`).
- `tools/blender/bake_camera.py:145-202` — the stamping mechanism that ran at bake; the addon reads those same keys back.

### Established Patterns
- Duck-typing on Flame objects (`hasattr` over `isinstance`) — apply to `flame.batch.nodes` filter in D-06 target-Action resolution.
- Two-surface error strategy — Blender side uses `self.report({'ERROR'}, ...)` in the operator plus `bpy.ops.wm.info` for the success-case popup; Flame side lets tracebacks propagate through the bridge response envelope (no Flame-side dialogs during bridge execution).
- `tempfile.mkdtemp(prefix="forge_...")` with on-success cleanup + on-failure preservation — reuse on the bridge side for the FBX scratch dir (D-03).
- One-probe-per-request bridge discipline — mandatory for the D-18 `flame.batch.frame_rate` shape probe.
- v5 JSON contract is the single bridge format between Blender and Flame — extend via `v5_json_str_to_fbx`, do not introduce a parallel JSON schema.

### Integration Points
- New directory: `tools/blender/forge_sender/` (four core Python files; optional split of operator/panel).
- New function: `forge_flame/fbx_ascii.v5_json_str_to_fbx` (sibling of existing file-path variant).
- Modified file: `tools/blender/extract_camera.py` (math moves to `forge_sender/flame_math.py`; keeps CLI surface unchanged).
- No changes to `flame/camera_match_hook.py` — Phase 1 is closed; D-17 frame-rate strategy avoids revisiting.
- No changes to `tools/blender/bake_camera.py` — stamped metadata contract is already sufficient.

</code_context>

<specifics>
## Specific Ideas

- **Zero Flame-side UI trigger.** The whole phase's success criterion is "user never visits Flame's batch menu for the return trip" (IMP-06). Every design choice — sync POST, bridge-owned Action resolution, no Flame-side dialogs during import — reinforces this.
- **Popup copy matches Phase 1 tone** — direct, names the missing thing, offers the user-facing fix. No jargon like "PyAttribute" or "PyActionNode" in popups; use "Action" and "camera".
- **Artist / pipeline-TD audience for install.** User explicitly chose manual zip install + clear docs over install.sh automation. Phase 4 docs must walk the flow: unzip (if needed) → Blender Preferences → Add-ons → Install from file → point at the zip → enable checkbox → close Preferences → panel appears in N-panel `Forge` tab.
- **Geometric fidelity trumps UX smoothness.** Hard errors on missing metadata, ambiguous Action, or unknown frame rate are correct behavior — not a UX failing. Silent fallbacks to a default Action or default frame rate would violate the project's Core Value.
- **Pre-work probe gate.** D-18 (`flame.batch.frame_rate` shape) and FOLDED-01 (multi-camera picker sweep) both run before implementation. Neither is optional — they de-risk assumptions that would otherwise silently break the round-trip.
- **Drift discipline.** Decision 2b ships one copy of the Flame Euler math in `flame_math.py`. Any future change there touches both the addon and `extract_camera.py` simultaneously — that is a feature, not a hazard.

</specifics>

<deferred>
## Deferred Ideas

- **`install.sh` drops the addon zip** (5b, rejected) — deferred until artists push back on the manual install step. Phase 4 docs cover the manual path for now.
- **Rich panel UI** (6c, rejected) — target-Action override input, frame-range display, bridge-status indicator, version badges. Belongs in v2 polish; D-14/D-15 minimal panel is sufficient for v1.
- **Async/threaded send** (7b, rejected) — modal operator + worker thread. If the 5 s blocking window turns out to be a real UX issue during live testing, promote to a quick task; not a v1 concern.
- **Fuzzy Action matching** (3b, rejected) and **cross-batch scanning** (3c, rejected) — current-batch + exact-match only. If users consistently hit ambiguity, add a disambiguation popup with candidate names in a later phase.
- **Phase 1 supplement to stamp `forge_bake_frame_rate`** — contingency path under D-19, triggered only if the D-18 probe finds the Flame API surface incompatible. Not the default.
- **MULT-01** (multi-camera round-trip in one send) — v2 scope; v1 sends one camera at a time.
- **POLISH-01** ("Last .blend per Action" memory) — v2 scope.
- **POLISH-02** (additional version stamps beyond `forge_bake_version`) — v2 scope.
- **POLISH-03** (Finder / file-manager integration hints) — v2 scope.

### Reviewed Todos (not folded)

None — the single matching todo (multi-camera picker UAT) was folded into scope as FOLDED-01.

</deferred>

---

*Phase: 02-blender-addon*
*Context gathered: 2026-04-21*
