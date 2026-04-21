---
phase: 02-blender-addon
plan: 01
subsystem: testing
tags: [flame-bridge, probe, uat, folded-01, d-18, d-19, frame-rate, multi-camera-picker]

requires:
  - phase: 01-flame-to-blender
    provides: "Existing _pick_camera dropdown + forge_bake_camera_name stamp path in flame/camera_match_hook.py (the paths this plan live-verified)"

provides:
  - "D-18 frame_rate API probe run and saved to memory/flame_batch_frame_rate.md"
  - "D-19 contingency triggered and locked: frame_rate ladder owned by the Blender addon side (forge_bake_frame_rate prop → scene.render.fps/fps_base → popup)"
  - "FOLDED-01 multi-camera picker 4-check sweep: PASSED — Perspective filtered, order deterministic, Cancel clean, picker→stamp integrity verified via exported JSON"
  - "Phase 1 supplement queued as optional pending todo: stamp forge_bake_frame_rate in tools/blender/bake_camera.py (non-blocking — ladder fallback #2 covers this case)"
  - "Four cosmetic Phase 1 follow-ups discovered and captured in the completed picker-UAT todo: /tmp vs $TMPDIR path bug in the plan criterion (macOS), nvidia-smi leak in error output, temp-dir retained on failure, empty-camera bake UX"
affects: [02-02-shared-math, 02-03-blender-addon]

tech-stack:
  added: []
  patterns:
    - "One-probe-per-request bridge discipline enforced throughout (ping → targeted attr probe → follow-up), with findings saved to memory BEFORE any subsequent probe"
    - "Caller-owned frame rate: v5_json_str_to_fbx(..., frame_rate=<float>) — Plan 02-02's sibling function takes fps as a kwarg rather than probing Flame; the Blender addon side derives it"

key-files:
  created:
    - "/Users/cnoellert/.claude/projects/-Users-cnoellert-Documents-GitHub-forge-calibrator/memory/flame_batch_frame_rate.md"
  modified:
    - ".planning/todos/completed/2026-04-21-verify-multi-camera-picker-in-live-uat.md"
    - ".planning/STATE.md"

key-decisions:
  - "D-17 disproven: flame.batch.frame_rate is a plain NoneType slot returning None even with a loaded Batch + clip + Action. Not a PyAttribute, no .get_value() method."
  - "D-19 recovery adopted with a specific ladder owned by Plan 02-03's addon: (1) cam['forge_bake_frame_rate'] custom prop, (2) bpy.context.scene.render.fps / fps_base, (3) popup asking the user. No more Flame-side probing for frame rate."
  - "FOLDED-01 closed PASS: the multi-camera picker correctly filters Perspective, orders entries deterministically, cancels cleanly, and routes the pick to the correct JSON stamp. Phase 2 implementation is unblocked."
  - "Full .blend round-trip on a real solved camera was deferred — the Default camera had no solve data so the bake correctly rejected empty frames. Picker→stamp integrity (the thing the picker affects) is independently verified via exported JSON. Full end-to-end will be exercised in Wave 4 UAT."

patterns-established:
  - "Probing discipline preserved across sessions: ping first, one probe per request, save findings to memory immediately, never re-probe without explicit approval"
  - "Fallback-ladder pattern for host-state lookups where the host API is unreliable: authoritative stamp → scene-derived default → user-provided"

requirements-completed: ["IMP-03", "IMP-04"]

duration: ~35min
completed: 2026-04-21
---

# Phase 02: Blender-Addon — Plan 01 Summary

**Two live-Flame probes closed: D-18 disproved the `flame.batch.frame_rate` API assumption and locked D-19 recovery; FOLDED-01 multi-camera picker sweep passed all four checks, unblocking Phase 2 implementation.**

## Performance

- **Duration:** ~35 min (live probes + user-driven UAT)
- **Completed:** 2026-04-21
- **Tasks:** 4
- **Files modified:** 3

## Accomplishments

- **D-18 probe done, findings saved** (`memory/flame_batch_frame_rate.md`): three isolated bridge probes confirm `flame.batch.frame_rate` is a plain `NoneType` slot — the `.get_value()` call form raises `AttributeError`, and the attribute stays `None` even with a Batch + clip + Action loaded. The D-17 assumption encoded in CONTEXT is structurally wrong.
- **D-19 recovery locked** — caller-owned frame rate with a three-level ladder on the Blender addon side. Plan 02-02's `v5_json_str_to_fbx` takes `frame_rate` as a kwarg (already true in the plan's signature); Plan 02-03's addon derives the value from either a stamped custom property, Blender's scene fps, or a user popup. No more Flame-side frame-rate probing anywhere in the pipeline.
- **FOLDED-01 picker sweep PASSED** — all four checks green: Perspective filtered from the dropdown, entries in deterministic order (confirmed stable across two opens), Cancel aborts cleanly with no leftover temp dir under `$TMPDIR/forge_bake_*`, and picker→stamp integrity verified (user picked `Default`, exported JSON showed `forge_bake_camera_name: "Default"`).
- **Four cosmetic Phase 1 follow-ups captured** — discovered in passing during the picker UAT, recorded in the completed todo for later cleanup (not Phase 2 scope).

## Task Commits

1. **Task 1: Ping-only bridge liveness check** — verified inline (no file changes, no commit)
2. **Task 2: D-18 probe — flame.batch.frame_rate shape** — findings written to `memory/flame_batch_frame_rate.md` (auto-memory store, not tracked in git)
3. **Task 3: FOLDED-01 multi-camera picker 4-check sweep** — todo moved from `pending/` to `completed/` with results appended
4. **Task 4: Update STATE.md with Wave 1 findings** — D-19 trigger recorded, picker todo reference removed, Last Activity/Current Position/Session Continuity refreshed

All four tasks are bundled in a single Wave 1 commit rather than atomic per-task commits because three of the four are pure probe/UAT + in-place planning-doc edits with no source-code changes.

## Files Created/Modified

- `~/.claude/projects/-Users-cnoellert-Documents-GitHub-forge-calibrator/memory/flame_batch_frame_rate.md` — D-18 probe findings (three probe calls with full repr/type output + decision trail). Lives in auto-memory, not git-tracked.
- `.planning/todos/completed/2026-04-21-verify-multi-camera-picker-in-live-uat.md` — moved from `pending/` with 4-check PASS results and four cosmetic discoveries appended
- `.planning/STATE.md` — Decisions list extended with D-19 + FOLDED-01 bullets; picker todo reference removed from Pending Todos; Current Position updated to "1 of 4 complete"; Last Activity/Session Continuity refreshed

## Decisions Made

- **D-17 → D-19 pivot locked.** `flame.batch.frame_rate` returned `None` under every tested condition (empty batch, loaded batch with clip, Action selected). The attribute is NOT a `PyAttribute`, does NOT expose `.get_value()`, and is NOT auto-populated from clip state. D-17 is unrecoverable in the probed Flame 2026.2.1 configuration. Adopted D-19 with a specific three-level ladder (custom prop → scene fps → popup) owned by the Blender addon.
- **Phase 1 supplement classified as non-blocking.** Stamping `forge_bake_frame_rate` in `tools/blender/bake_camera.py` is additive robustness, not a prerequisite — ladder fallback #2 (`scene.render.fps / fps_base`) handles the no-stamp case correctly. Captured as a low-priority pending todo for later.
- **Check 4 accepted at JSON stamp-integrity level.** Full `.blend` round-trip with a real solved camera was deferred to Wave 4 UAT because the user's test camera (`Default`) had no solve data and the downstream bake correctly rejected empty frames. The picker's only job is to route the pick to the correct stamp, which was independently verified via the exported JSON (`forge_bake_camera_name: "Default"` matches the user's pick).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 — Missing Coverage] Plan criterion `ls /tmp/forge_bake_*` is wrong on macOS**
- **Found during:** Task 3 (picker UAT Check 3)
- **Issue:** The plan's Check 3 acceptance criterion checks `/tmp/forge_bake_*` for leftover temp dirs, but on macOS the bake uses `$TMPDIR` (under `/var/folders/...`). `/tmp` is never populated. The criterion was vacuously true regardless of actual cleanup behavior.
- **Fix:** Verified the actual bake temp path (`$TMPDIR/forge_bake_*`) for Check 3 instead. The substantive finding (Cancel produces no new temp dir) is recorded in the completed todo; the criterion itself was adapted in the results block.
- **Files modified:** `.planning/todos/completed/2026-04-21-verify-multi-camera-picker-in-live-uat.md`
- **Verification:** `ls /var/folders/30/.../T/` after Cancel showed no new `forge_bake_*` dir (only the pre-existing one from an earlier unrelated bake attempt)
- **Committed in:** (bundled in Wave 1 commit)

**2. [Rule 4 — Scope Expansion] Captured four cosmetic Phase 1 follow-ups as discoveries**
- **Found during:** Task 3 (picker UAT, while baking `Default`)
- **Issue:** The `Default`-camera bake failed with three side-issues surfaced in the error dialog: `nvidia-smi: command not found` leak on macOS, temp dir retained under `$TMPDIR` on failure, generic `no frames in JSON` message when a camera has no solve data. Also noticed the `/tmp` vs `$TMPDIR` criterion bug above.
- **Fix:** Recorded all four under a "Discovered side-issues" block in the completed todo so they aren't lost, explicitly scoped as Phase 1 polish follow-ups (not Phase 2 work). No code changes.
- **Files modified:** `.planning/todos/completed/2026-04-21-verify-multi-camera-picker-in-live-uat.md`
- **Verification:** Items are a documentation-only capture; no runtime change
- **Committed in:** (bundled in Wave 1 commit)

---

**Total deviations:** 2 captured (1 criterion bug, 1 scope capture)
**Impact on plan:** Neither affects the Wave 1 goal or downstream plans. The criterion bug is a plan-authoring fix; the scope capture keeps useful discoveries from being lost without derailing Phase 2.

## Issues Encountered

- **Bridge dropped between probes.** After two successful isolated probes, the bridge became unreachable on 127.0.0.1:9999 (connection refused). User confirmed this was because Flame had been closed and restarted. Resolved by pinging again once Flame + hook were live, then resuming with a batch+clip loaded.
- **`Default` camera had no solve data.** The user's first Check 4 attempt picked a newly-created `Default` camera with no keyframes, which the bake correctly rejected (`no frames in JSON`). This was initially ambiguous but resolved by reading the preserved `baked.json` (`"frames": []`) directly and confirming the `forge_bake_camera_name` stamp was correct. Full end-to-end bake on a real solved camera was deferred to Wave 4 UAT.

## User Setup Required

None — no external configuration. All changes are planning-doc edits + an auto-memory reference document.

## Next Phase Readiness

- **Plan 02-02 unblocked.** Its `v5_json_str_to_fbx(..., frame_rate=...)` signature already takes fps as a caller-provided kwarg, which is exactly what the D-19 recovery requires. No plan revisions needed.
- **Plan 02-03 scope clarified.** The addon owns the frame-rate ladder. The Phase 1 `forge_bake_frame_rate` stamp is optional (robustness only) — the addon can ship without it.
- **Phase 2 implementation path is clean.** No remaining gating assumptions, no blocking probes, no open picker concerns.
- **Optional pre-work:** one small Phase 1 quick-task to stamp `forge_bake_frame_rate` during Blender bake — additive, low priority, can happen any time before or during Wave 3.

---
*Phase: 02-blender-addon*
*Completed: 2026-04-21*
