# Phase 2: Blender Addon - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-21
**Phase:** 02-blender-addon
**Areas discussed:** JSON transport, Extraction logic reuse, Target Action resolution, Error taxonomy, Packaging + install, Panel UI scope, Sync vs async send, Frame-rate fidelity

---

## JSON transport mechanism

| Option | Description | Selected |
|--------|-------------|----------|
| 1a | Keep file-path only; bridge writes POSTed JSON to a Flame-side tempdir, then calls `v5_json_to_fbx(path)` | |
| 1b | Addon writes JSON to a shared temp path; POSTs just the path (brittle, assumes aligned paths) | |
| 1c | Add sibling `v5_json_str_to_fbx(json_str, …)` that accepts JSON in memory | ✓ |

**User's choice:** 1c
**Notes:** Avoids cross-process temp-file sharing; keeps the file-path function for CLI callers (`roundtrip_selftest.sh`, manual invocations) unchanged.

---

## Extraction logic reuse

| Option | Description | Selected |
|--------|-------------|----------|
| 2a | Duplicate ~100 LOC of Euler math into the addon | |
| 2b | Extract shared `tools/blender/forge_sender/flame_math.py`; both `extract_camera.py` and the addon import | ✓ |
| 2c | Addon shells out to `extract_camera.py` as a subprocess from inside Blender | |

**User's choice:** 2b
**Notes:** Cheap one-time refactor; prevents drift between the two callsites on Flame Euler decomposition math.

---

## Target Action resolution on the Flame side

| Option | Description | Selected |
|--------|-------------|----------|
| 3a | Current batch only, exact match, fail-loud on 0 or 2+ matches | ✓ |
| 3b | Current batch + prefix-fuzzy fallback when exact misses | |
| 3c | Scan all open batches (wider net) | |
| 3d | Exact match; on 2+ auto-pick first with a warning in the response | |

**User's choice:** 3a
**Notes:** User confirmed "on target" — silent fallbacks violate Core Value; Phase 1 precedent (D-08: "fidelity trumps frictionless UX") carries forward.

---

## Error taxonomy + popup surface

| Option | Description | Selected |
|--------|-------------|----------|
| 4a | 3-tier (preflight / transport / remote) + provenance guard (`forge_bake_source == "flame"`) | ✓ |
| 4b | Same 3 tiers but drop the `forge_bake_source` provenance guard | |
| 4c | One-size popup: every failure → `"Send failed: {reason}"` | |
| 4d | Finer taxonomy: parse bridge traceback and map known Flame errors to distinct popups | |

**User's choice:** 4a
**Notes:** User confirmed "on target". 3-tier model with provenance guard adds ~5 LOC and catches the "wrong camera picked from bpy outliner" failure mode.

---

## Packaging + install flow

| Option | Description | Selected |
|--------|-------------|----------|
| 5a | Directory package `tools/blender/forge_sender/`; manual artist install; Phase 4 docs | ✓ |
| 5b | Same package, but `install.sh` also drops the zip at a known path | |
| 5c | Single-file addon with math duplicated (rejects 2b) | |

**User's choice:** 5a
**Notes:** "As long as the install instructions are clear we can trust an artist or pipeline TD to put it in the right place." `install.sh` stays focused on `/opt/Autodesk/shared/python/`.

---

## Panel UI scope

| Option | Description | Selected |
|--------|-------------|----------|
| 6a | Button + metadata readout + disabled-button when preflight fails | ✓ |
| 6b | Button only | |
| 6c | Rich UI: target-Action override input, frame-range display, bridge-status indicator | |

**User's choice:** 6a
**Notes:** Minimum necessary surface for the artist to see where the camera is going before clicking; disabled-state doubles as preflight communication.

---

## Sync vs async send

| Option | Description | Selected |
|--------|-------------|----------|
| 7a | Synchronous blocking operator with a 5 s HTTP timeout | ✓ |
| 7b | Modal operator with a worker thread (non-blocking during call) | |
| 7c | Sync with a shorter timeout (1-2 s) | |

**User's choice:** 7a
**Notes:** Typical round-trip is sub-second; 500 ms Blender freeze is invisible; 5 s gives a clean bridge-down failure. Threading adds ~40 LOC and bpy thread-safety risk with no practical win.

---

## Frame-rate round-trip fidelity

| Option | Description | Selected |
|--------|-------------|----------|
| 8a | Supplement Phase 1: stamp `forge_bake_frame_rate` during export | |
| 8b | Bridge queries `flame.batch.frame_rate.get_value()` at import time | ✓ |
| 8c | Hardcode `"23.976 fps"` and document the limitation | |

**User's choice:** 8b — "sounds smart"
**Notes:** Frame rate belongs to the Flame session, not Blender; querying at import is source-of-truth and keeps Phase 1 closed. Requires a one-probe-per-request discipline probe task (D-18) to confirm the API shape before implementation begins.

---

## Claude's Discretion

Items deferred to the planner/executor without further user input:
- Whether operator and panel classes live in `__init__.py` or split into `operator.py` / `panel.py`
- Exact v5 JSON payload embedding inside the bridge `{"code": "..."}` body
- Exact popup wording within the D-09 structural constraints
- HTTP timeout value if 5 s proves too short during live validation
- N-panel tab category string (default `Forge`)
- `requests` vs `urllib.request` for the HTTP transport
- Shape of the bridge's created-camera-name response payload (single string / list / mapping)

## Deferred Ideas

- `install.sh` drops the addon zip (5b rejected)
- Rich panel UI with overrides (6c rejected)
- Async / threaded send (7b rejected)
- Fuzzy Action matching and cross-batch scanning (3b / 3c rejected)
- Phase 1 supplement for `forge_bake_frame_rate` (contingency only under D-19)
- MULT-01 (multi-camera in one send), POLISH-01, POLISH-02, POLISH-03 — v2 scope, already deferred

## Folded Todos

- `2026-04-21-verify-multi-camera-picker-in-live-uat.md` — folded as FOLDED-01; pre-implementation verification sweep inside Phase 2.
