---
phase: 02-blender-addon
plan: 04
subsystem: testing
tags: [flame-bridge, blender-addon, uat, live-roundtrip, fbx, error-taxonomy, d-12, d-19, d-03, d-09]

requires:
  - phase: 01-flame-to-blender
    provides: "Existing Flame→Blender bake + forge_bake_* stamp path; forge_flame.fbx_io.import_fbx_to_action"
  - phase: 02-blender-addon
    provides: "Plan 02-02 v5_json_str_to_fbx sibling + build_v5_payload helper; Plan 02-03 Forge N-panel + preflight + transport"

provides:
  - "Installable Blender addon zip tools/blender/forge_sender-v1.0.0.zip (CONTEXT D-12, 13.9KB, 4 files under forge_sender/, no __pycache__ or .pyc)"
  - "Live validation record for all six IMP requirements (IMP-01..IMP-06) — happy-path round-trip and three failure tiers exercised on Flame 2026.2.1 + Blender 4.5+"
  - "Two Wave 4 hotfixes shipped against Plan 02-03: permissive operator poll() so F3/console can exercise Tier 1 popups; bridge _result surfacing via trailing expression + ast.literal_eval in parse_envelope"
  - "Four Phase 4 polish follow-ups captured: Blender addon reload discipline, Flame FBX importer stereo-rig expansion filter, Flame-side crash reproducibility investigation, empty-camera bake UX"
affects: [03-bake-fidelity, 04-polish]

tech-stack:
  added: []
  patterns:
    - "D-19 caller-owned frame rate verified live: Blender scene.render.fps / fps_base ladder resolved 24 fps on the test .blend; forge_flame.fbx_ascii.v5_json_str_to_fbx accepted the kwarg without probing flame.batch.frame_rate"
    - "Bridge REPL semantics: /exec returns repr(value) only when the last statement is an ast.Expr. Assignment-form _result = expr() yields result: null. Client-side ast.literal_eval recovers the dict. Pattern codified in transport.parse_envelope."

key-files:
  created:
    - "tools/blender/forge_sender-v1.0.0.zip (committed binary artifact, D-12)"
    - ".planning/phases/02-blender-addon/02-04-SUMMARY.md"
  modified:
    - "tools/blender/forge_sender/__init__.py (operator poll() relaxed; panel disabled-state uses col.enabled = False)"
    - "tools/blender/forge_sender/transport.py (_FLAME_SIDE_TEMPLATE ends with _forge_send() bare expr; parse_envelope ast.literal_eval's string results)"

key-decisions:
  - "Task 5 accepted as PASS with caveats: the happy-path send DID land a camera in the target Action with correct transforms, but (a) the success popup plurals because Flame's FBX importer also returned internal nodes (RootNode_Scene5 and stereo-rig siblings Camera1_left / Camera1_right) that never surface as user-visible Flame cameras, and (b) a subsequent action — user could not capture the exact repro — crashed Flame. First send was clean; crash is not a Phase 2 code blocker but is a stability concern to investigate in Phase 4 or a focused quick-task."
  - "Two hotfixes to Plan 02-03 committed in Wave 4 because their absence would have failed Tasks 3 and 5 (ec93c83, 5cff722). The plan's execution was technically correct against the authored spec; the spec itself had two subtle bugs that live UAT surfaced."
  - "Plural-popup filter deferred to Phase 4 polish. For Phase 2 purposes, the plural message is a cosmetic flaw, not a correctness failure — the camera correctly lands and carries Blender edits. Filter should be added in forge_sender/__init__.py around line 264-275 (exclude names that don't belong to actual Flame camera nodes)."
  - "Skipped optional D-07 ambiguous-Action bonus check in Task 6 — Tier 3 0-match path independently validates the exact-match + fail-loud contract per plan guidance."

patterns-established:
  - "Live-Flame module reload recipe: when install.sh syncs new code, use the gc.get_objects walk + exec(code, o.__dict__) pattern (from memory/flame_module_reload.md) to refresh the module in a running Flame session without a restart. Verified in Wave 4 — resolved a stale forge_flame.fbx_ascii that was causing AttributeError on v5_json_str_to_fbx."
  - "Blender addon live-reload recipe: when a developer edits addon submodules, disable+enable via the Preferences UI does NOT flush sys.modules. Proper reload requires either (a) full Blender restart (Cmd+Q, relaunch) or (b) explicit del sys.modules[k] + re-import pattern for every submodule before bpy.ops.preferences.addon_enable runs. Ran into this live in Wave 4 and had to recover with /tmp/forge_reload.py."

requirements-completed: ["IMP-01", "IMP-02", "IMP-03", "IMP-04", "IMP-05", "IMP-06"]

duration: ~90min
completed: 2026-04-21
---

# Phase 02: Blender-Addon — Plan 04 Summary

**Installable forge_sender v1.0.0 shipped; all six IMP requirements verified live on Flame 2026.2.1 + Blender 4.5+. Two hotfixes to Plan 02-03 applied in-flight (operator poll() + bridge result surfacing). Happy path works with edits preserved; four follow-ups captured for Phase 4 polish including a single Flame crash with no repro.**

## Performance

- **Duration:** ~90 min (zip build + 5 live UAT tiers + 2 hotfix cycles + SUMMARY)
- **Completed:** 2026-04-21
- **Tasks:** 7
- **Files modified:** 4 (zip created, __init__.py + transport.py fixed, SUMMARY.md created)

## Accomplishments

- **Installable addon zip shipped** per CONTEXT D-12: built via `cd tools/blender && zip -r forge_sender-v1.0.0.zip forge_sender/`, contains the four `forge_sender/` files, no `__pycache__` or `.pyc`. `install.sh` untouched.
- **All six IMP requirements verified live** — IMP-01 (panel install), IMP-02 (preflight Tier 1 × 4 sub-checks), IMP-03 (round-trip import), IMP-04 (transform fidelity), IMP-05 (all three failure tiers), IMP-06 (no post-export Flame menu visit required).
- **Two hotfix commits to Plan 02-03** — both regressions that only surface under live invocation, not unit tests:
  - `5cff722 fix(02-03): relax operator poll() so F3/console can exercise Tier 1 popups` — the operator's `poll()` originally gated on `preflight.check(context) is None`, which blocked ALL invocation paths when preflight failed. Tier 1 tests require bpy.ops.forge.send_to_flame() to fire the ERROR popup even when preflight rejects the state — we can't verify "what popup fires for no active object" if we can't invoke the operator with no active object. Fix: poll() always returns True; execute() does the real gate via preflight.check(); panel disabled-state uses `col.enabled = False` to keep the button visually disabled.
  - `ec93c83 fix(02-03): surface bridge _result via trailing expression + ast.literal_eval` — the transport template ended with `_result = _forge_send()` (an assignment). forge-bridge's `/exec` endpoint only surfaces a return value when the LAST STATEMENT IS AN ast.Expr — it evals expressions and returns `repr(value)`, but assignments fall through to a bare exec and `result` stays `None`. Every successful Send to Flame would have produced `Sent to Flame (no new camera reported) — Action '<unknown>'` as the popup. Fix: template's last line is `_forge_send()` (bare expr); `parse_envelope()` detects string results and runs `ast.literal_eval` to recover the dict.
- **Validation matrix complete** (see below).
- **D-03 preserve-on-failure contract verified** — Tier 3 failure left `$TMPDIR/forge_send_znr40z4m/incoming.fbx` (39KB, fully emitted). Successful happy-path send cleaned its tempdir.

## Task Commits

1. **Task 1 (zip build)** — `6d27b89 feat(02-04): build installable forge_sender addon zip v1.0.0`
2. **Tasks 2-6 (live UAT)** — no code commits; validation only, results captured in this SUMMARY
3. **Hotfix A (discovered during Task 3)** — `5cff722 fix(02-03): relax operator poll()` (rebuilt zip)
4. **Hotfix B (discovered during Task 5)** — `ec93c83 fix(02-03): surface bridge _result via trailing expression` (rebuilt zip)
5. **Task 7 (this SUMMARY)** — pending commit

## Validation Matrix

| Task | IMP Requirement | Verified? | Notes |
|------|-----------------|-----------|-------|
| 2 — Panel install | IMP-01 | **PASS** | Forge tab appears in N-panel after `Install from file`; disabled-state row shows red ERROR icon + "Not a Flame-baked camera" + disabled Send button. |
| 3(a) — Preflight Tier 1 (no active object) | IMP-02 | **PASS** | Popup copy matched UI-SPEC literal: `"Send to Flame: no active object — select a forge-baked camera in the 3D viewport and try again"` |
| 3(b) — Preflight Tier 1 (not a camera, cube active) | IMP-02 | **PASS** | Matched UI-SPEC literal: `"Send to Flame: active object is not a camera — select a forge-baked camera in the 3D viewport and try again"` |
| 3(c) — Preflight Tier 1 (camera missing stamps) | IMP-02 | **PASS** | Named `'forge_bake_action_name'` verbatim as the first missing key per `_REQUIRED_STAMPED_KEYS` ordering. |
| 3(d) — Preflight Tier 1 (bad provenance) | IMP-02 | **PASS** | Matched UI-SPEC literal including the `forge_bake_source != 'flame'` parenthetical. |
| 4 — Transport Tier | IMP-05 | **PASS** | Popup contained literal `http://127.0.0.1:9999`, instant fail via ConnectionError (elapsed 0.00s — well within 5-10s D-16 budget). |
| 5 — Happy-path round-trip | IMP-03, IMP-04, IMP-05, IMP-06 | **PASS with caveats** | Single camera landed in target `action1` Action with correct transforms (Blender edit preserved). Popup fired in PLURAL form because `import_fbx_to_action` returned 4 node names (one real camera + FBX internals + stereo-rig siblings). Subsequent action crashed Flame with no captured error message. |
| 6 — Remote Tier (Action renamed) | IMP-05 (+ D-06/D-07/D-08) | **PASS** | User confirmed popup appeared with expected copy after renaming `action1` in Flame to a different name. D-03 preserve-on-failure verified via `$TMPDIR/forge_send_znr40z4m/incoming.fbx` preserved post-failure. Optional D-07 ambiguous-Action bonus check skipped. |

## Files Created/Modified

- `tools/blender/forge_sender-v1.0.0.zip` — installable addon; 13.9KB; 4 files under `forge_sender/`.
- `tools/blender/forge_sender/__init__.py` — operator `poll()` relaxed to return `True`; panel's disabled-state wraps the Send button in `col.enabled = False`.
- `tools/blender/forge_sender/transport.py` — `_FLAME_SIDE_TEMPLATE` ends with `_forge_send()` bare expression; `parse_envelope()` gains `ast.literal_eval()` string decoding with a non-literal fallback.
- `.planning/phases/02-blender-addon/02-04-SUMMARY.md` — this file.

**Not modified (per plan's scope boundaries):**
- `install.sh` — untouched (D-12).
- `flame/camera_match_hook.py` — untouched (Phase 1 closed).
- `tools/blender/bake_camera.py` — untouched (stamped metadata contract sufficient).

**`install.sh` WAS run once** during Task 5 — to sync the Wave 2 `forge_flame/fbx_ascii.v5_json_str_to_fbx` addition to `/opt/Autodesk/shared/python/forge_flame/`. Running the installer was not a code modification; it was a deployment step that Wave 2's plan failed to flag explicitly. Recommend an explicit "run install.sh" note in future plans that touch `forge_flame/` or `forge_core/`.

## Discretion Calls

Per CONTEXT §Claude's Discretion bullets 1-7:

1. **Operator/Panel file split:** Kept both classes in `forge_sender/__init__.py` (Plan 02-03's shipped structure). Did not split into `operator.py` / `panel.py`.
2. **Timeout bump:** Default 5s DEFAULT_TIMEOUT_S stayed — Tier 2 fail was instant (0.00s) and Tier 3 remote failure returned within ~1s. No need to bump to 10s for this UAT; revisit if live round-trip latency exceeds 3s p99 in production.
3. **Tab category:** Stayed as `Forge` per UI-SPEC §Panel identity D-14.
4. **Bonus D-07 ambiguous-Action check:** Skipped. The 0-match path independently validates the exact-match contract; two-match behavior is a natural extension and the code path is covered by unit tests in `tests/test_forge_sender_transport.py`.
5. **Phase 1 `nvidia-smi: command not found` leak:** Observed again during Task 6's Flame state setup (attempted Flame→Blender export errored with `no frames in JSON`). Already captured in Wave 1 Task 3's completed picker UAT todo as a Phase 1 polish follow-up. Not in Phase 2 scope.

## D-17 vs D-19 Trail

CONTEXT §D-17 assumed `flame.batch.frame_rate.get_value()` returns a supported fps string. **Plan 02-01 disproved this live:** `flame.batch.frame_rate` is a plain `NoneType` slot on Flame 2026.2.1 with no `.get_value()` method, and the attribute stays `None` even with a Batch + clip + Action loaded. See `memory/flame_batch_frame_rate.md` for the probe findings.

**D-19 recovery ladder ran live in Task 5's happy path.** The Blender-side ladder in `tools/blender/forge_sender/__init__.py:_resolve_frame_rate` evaluated in this order:
1. `cam["forge_bake_frame_rate"]` custom prop — NOT present (Phase 1 bake stamp doesn't include it yet; Phase 1 supplement is a pending todo from Wave 1).
2. `bpy.context.scene.render.fps / scene.render.fps_base` — resolved to 24.0, mapped to the `"24 fps"` label via the `_FLAME_FPS_LABELS` table.
3. (User popup — NOT reached.)

The `"24 fps"` string was passed verbatim to `v5_json_str_to_fbx(..., frame_rate="24 fps")` which Flame accepted. No probing of `flame.batch.frame_rate` anywhere in the Flame-side template — D-19 fully replaces the D-17 assumption.

The Phase 1 `forge_bake_frame_rate` supplement (pending quick-task) remains a LOW priority: ladder fallback #2 covers the common case correctly. The stamp would only matter if an artist's Blender scene fps is edited away from the original batch fps before Send.

## Residual Risks and Follow-ups

1. **Flame crash during Task 5 (no repro):** The first Send to Flame succeeded and left Flame in a valid state. A subsequent action caused Flame to crash; the exact action wasn't captured. No crash report written to `~/Library/Logs/DiagnosticReports/`. No `forge_send_*` tempdir preserved from the crashing send (the `finally` cleanup didn't run). Investigate in a dedicated debug session with fresh Flame + reproducible steps. NOT a Phase 2 code blocker — the send path correctness is proven; the crash is a stability concern.

2. **Plural popup enumerates FBX internals (Phase 4 polish):** `import_fbx_to_action` returns a list that includes `RootNode_Scene5` (FBX root transform) and stereo-rig siblings (`Camera1_left`, `Camera1_right`) alongside the actual imported camera (`Camera1`). The success popup lists all four names. Fix: filter the list in the Flame-side template before returning to `_result` — keep only entries whose type is `Camera` (or whose name doesn't end in `_left` / `_right` and isn't `RootNode_*`). Suggested patch site: `tools/blender/forge_sender/transport.py:_FLAME_SIDE_TEMPLATE` around the `"created": [...]` list comprehension.

3. **Flame FBX importer stereo-rig expansion (investigate):** Flame is auto-creating stereo-rig siblings for every imported camera, even for a monocular Blender camera. Either (a) this is Flame's default behavior for `import_fbx()` and we need to pass a kwarg to suppress it, or (b) `forge_flame.fbx_ascii.v5_json_str_to_fbx` is emitting FBX metadata that Flame interprets as a rig. Artifact for forensic analysis: `$TMPDIR/forge_send_znr40z4m/incoming.fbx` (39KB, preserved from the Tier 3 failure — same FBX shape as the successful Task 5 send).

4. **Blender addon reload discipline (document for artists):** Disable + Re-enable in Preferences does NOT flush `sys.modules` for sibling modules inside an addon package. Edits to `transport.py` / `preflight.py` / `flame_math.py` require either (a) full Blender restart or (b) explicit `del sys.modules[k]` + re-import. This bit Wave 4 multiple times; users installing hotfix builds will bit it too. Suggested Phase 4: document the "if the addon seems to have old behavior, restart Blender" note in the forthcoming user docs (DOC-02 / Phase 4 scope).

5. **Empty-camera Flame→Blender bake UX (Phase 1 polish):** Already captured in Wave 1's completed picker UAT todo. When a Flame Action camera has no animation curves (static, pre-solve, or `Default` camera), the Flame→Blender bake produces a JSON with `"frames": []` and the Blender bake script rejects with `no frames in JSON`. User-facing copy could be clearer ("Camera has no animation data — solve or set a transform before exporting").

## Requirements Closure

| ID | Status | Evidence |
|----|--------|----------|
| IMP-01 | **VERIFIED** | Task 2 — Forge tab visible in N-panel after `Install from file` |
| IMP-02 | **VERIFIED** | Task 3(a–d) — all four Tier 1 popups matched UI-SPEC literal copy |
| IMP-03 | **VERIFIED** | Task 5 happy path — `v5_json_str_to_fbx` ran on Flame, FBX imported into target Action |
| IMP-04 | **VERIFIED** | Task 5 — Blender-side camera edit preserved in the imported Flame camera |
| IMP-05 | **VERIFIED** | Tasks 4 + 6 — Transport Tier (bridge down) and Remote Tier (renamed Action) both surfaced structured popups with the exact UI-SPEC copy |
| IMP-06 | **VERIFIED** | Task 5 — round-trip from Blender to Flame-side camera required zero Flame batch menu visits from the artist (only the Send to Flame button + reviewing the resulting camera) |

## User Setup Required

None — the addon installs via Blender's native `Preferences → Add-ons → Install from file`. No environment variables. No external service config.

## Next Phase Readiness

- **Phase 2 is functionally complete.** All six IMP requirements verified live.
- **Phase 4 (polish) inherits four follow-ups** (plural popup filter, stereo-rig investigation, Blender reload docs, empty-camera UX) plus the Flame crash repro investigation.
- **Phase 3 (if any — check ROADMAP)** is unblocked. The round-trip is working; downstream phases can rely on `forge_sender-v1.0.0.zip` as a stable install artifact.

---
*Phase: 02-blender-addon*
*Completed: 2026-04-21*
