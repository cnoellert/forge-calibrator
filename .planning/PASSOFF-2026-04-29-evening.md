---
created: 2026-04-29T20:15:00Z
session: 2026-04-29 evening
topic: 260429-gde — Blender 5.x slotted-actions fcurves migration; round-trip unblocked on flame-01 + portofino
follows: PASSOFF-2026-04-29.md
---

# Session Passoff — 2026-04-29 evening

## What landed this session

One quick task (`260429-gde`) shipped end-to-end with both portofino and
flame-01 UAT pass. This is the highest-priority pending todo from the
day-session passoff (the round-trip blocker on Blender 5.1) — closed.

| Quick | Description | Code commits | Build commit | Docs/closure commits |
|-------|-------------|--------------|--------------|----------------------|
| `260429-gde` | Version-tolerant fcurves walk for Blender slotted-actions API (5.x compat fix in `flame_math.py`) | `a3cf531` `f064824` | `543f458` (zip repackage) | `bc21b3e` `f27219d` `7cabf0f` `7ee89a9` `36cf922` (passoff) `9319dbd` (user-docs sync) |

**Tests:** 457 passed, 2 skipped (was 450/2 — +7 new `TestIterActionFcurves` cases). No regressions.

**Push state:** `origin/main` is in sync with `main` at `9319dbd`.

**Pending todos closed:** 1 (`2026-04-29-blender-51-slotted-actions-fcurves-api-migration.md` →
`completed/closed_uat_passed`).

## `260429-gde` summary

**Goal:** unblock Flame↔Blender round-trip on Blender 5.x. `Action.fcurves`
was removed in 5.0 alongside the slotted-actions migration; flame-01's
"Send to Flame" was crashing with `AttributeError: 'Action' object has
no attribute 'fcurves'`.

**Fix:** new `_iter_action_fcurves(action, anim_data=None)` helper in
`tools/blender/forge_sender/flame_math.py` with a three-tier walk:

- **Tier 1** — `bpy_extras.anim_utils.action_get_channelbag_for_slot(action, slot)`
  for bound slots. This is the official Blender migration helper; we use
  it rather than hand-rolling the slot→channelbag lookup.
- **Tier 2** — manual `action.layers[*].strips[*].channelbags[*].fcurves`
  walk for the unbound-slot edge case.
- **Tier 3** — legacy `getattr(action, "fcurves", None)` for 4.5 actions
  still in proxy mode (the project's stated minimum).

`_drain` now consumes the helper and stays version-tolerant from 4.5
through 5.x. The `bpy_extras.anim_utils` import is **lazy inside Tier 1**
so the bpy-free duck-typed tests stay portable on the forge env (no
`bpy` import at test time, per the existing pattern in
`tests/test_forge_sender_flame_math.py`).

**Untouched (verified during planning):**
- `tools/blender/extract_camera.py` — inherits the fix transitively via
  `from flame_math import`.
- `tools/blender/bake_camera.py` — writer-side; `keyframe_insert`
  auto-creates slotted plumbing on 4.4+ per RESEARCH A2. No change
  needed.
- `CLAUDE.md` "Blender 4.5+" — the project still supports 4.5; this is
  additive.

**Memory crumb:** `memory/blender_slotted_actions_fcurves_api.md` written
during the fix; indexed in `MEMORY.md`. Captures the cutoff versions
(4.4 introduced slotted; 5.0 removed the `.fcurves` proxy), the official
migration helper name, and the writer-side no-change rationale so the
next module that walks fcurves gets it right the first time.

## The v1.3.5 zip repackage — the deployment lesson

After the source fix landed at `f064824`, portofino UAT failed with the
**same pre-fix traceback**: `for fcurve in anim.action.fcurves` at
`flame_math.py:111` (which doesn't exist in the patched source). Root
cause: the user's reinstall pulled from `tools/blender/forge_sender-v1.3.4.zip`
(dated 2026-04-27), which predated the fix. The source patch was
correct; the deployment artifact was stale.

Cure: bumped `bl_info` to `(1, 3, 5)`, deleted the v1.3.4 zip, rebuilt
`forge_sender-v1.3.5.zip` from current source, committed and pushed
(`543f458`). Reinstall from v1.3.5 → both portofino and flame-01 UAT
clean.

**Lesson for the next addon-touching quick task:** the plan must include
a "rezip + version bump" task whenever `tools/blender/forge_sender/`
source changes. Otherwise the fix is stranded behind whatever zip is
sitting in `tools/blender/`. This is analogous to the
`flame_install_pycache_gap.md` memory crumb: the source patch is
necessary but not sufficient — the deployment artifact has to track it.

**Worth a memory crumb?** Probably yes. Filing as a follow-up note
rather than a separate todo since it's planning-process advice, not a
code bug. (Candidate path: `memory/blender_addon_zip_must_track_source.md`.)

## User-docs sync (the third-order miss)

After UAT pass on both machines, user asked whether install docs were
current. They weren't. `README.md:59` and `docs/seamless-bridge.md:67`
still pointed at `tools/blender/forge_sender-v1.3.4.zip` — which had been
deleted in `543f458`. A tester following those docs would have hit
"file does not exist" in Blender's installer.

Patched in `9319dbd`:
- Both zip references bumped to `forge_sender-v1.3.5.zip`
- Artist version-check bullet bumped from `1.3.4` to `1.3.5`
- Changelog blurb extended with: "v1.3.5 added Blender 5.x compatibility
  for the removed `Action.fcurves` API"

Audit also confirmed the rest of the user-facing docs are accurate:
"Using Send to Flame" workflow, "How forge-bridge autostart works",
"Multi-camera Apply Camera flow", and all troubleshooting symptoms still
match the shipped behavior.

**This compounds the deployment-lesson takeaway above.** Source patch +
zip repackage + user-docs version bump are all the same logical change
when an addon's bl_info version moves. A future quick-task plan that
touches `tools/blender/forge_sender/` should bake all three into the
task list — not catch them as serial deviations.

## UAT confirmation

**portofino (Mac, Blender 5.1):**
- Reinstalled v1.3.5 → enabled → restarted Blender
- Bake → Send to Flame round-trip clean. AttributeError gone.

**flame-01 (Linux, Blender 5.1):**
- Same v1.3.5 reinstall procedure
- User confirmed: *"Working perfect backwards and forwards."*
- This is the original repro site filed in yesterday's day-session
  passoff under "flame-01 first-light findings."

## Pending todos at session end

| Status | Todo | Next action |
|--------|------|-------------|
| 🟡 portofino_verified_pending_flame01 | `2026-04-27-camera-scope-export-nonetype-regression-on-cold-install.md` | Unchanged. flame-01 cold-install retest at HEAD. Outcome (a) closes; outcome (b) ships diag JSON. The next-session entry point now that round-trip is unblocked. |
| ⏸️ infra-not-code | `2026-04-27-wiretap-no-route-to-host-blocks-camera-calibrator-on-legacy-.md` | Unchanged. Mount autofs entry on portofino OR add defensive code-side fallback. Lowest priority. |
| ⏸️ backlog | `2026-04-29-blender-binary-picker-ui-tweak.md` | Unchanged. In-UI Blender binary picker. Low priority — env var + glob defaults cover the common cases. |

The Blender 5.1 fcurves todo that headed this list at session start is
now in `completed/` — not in the table.

## Next-session entry points

**(a) Camera-scope NoneType retest on flame-01** — the only "high-value
binary outcome" item left. Now that the addon round-trip is shipping
on flame-01, retest is unblocked. Procedure documented in the todo's
`next_steps` and the camera-scope debug session. If it passes, one more
pending todo closes. If it fails, ships diag JSON that re-opens the
debug session with platform-specific evidence (RHEL 9 x86_64 vs the
macOS arm64 that's been the dev environment).

**(b) Wiretap autofs mount fix on portofino** — separate thread, infra
not code. Lowest priority.

**(c) Blender binary picker UI tweak** — backlog. Punt.

## State snapshot

- Active branch: `main` at `7ee89a9`
- `origin/main`: in sync
- forge-bridge on portofino: alive, 127.0.0.1:9999
- forge-bridge on flame-01: alive (last confirmed in day session;
  not re-probed this session)
- Blender on portofino: 5.1 installed (alongside or replacing 4.5;
  the new `260429-fk5` glob defaults will sort-pick whichever is
  highest)
- Blender on flame-01: 5.1
- Test suite: 457 passed, 2 skipped; pytest-blender plugin disabled
  via `-p no:pytest-blender` per existing convention
- Active pending todos: 3 (all carried, none new)
- Active addon zip: `tools/blender/forge_sender-v1.3.5.zip`

## Memory crumbs touched this session

- **New:** `memory/blender_slotted_actions_fcurves_api.md` — written by
  the executor during the fix, indexed in `MEMORY.md`. Captures the
  three-tier iterator pattern, cutoff versions, and the writer-side
  no-change rationale.
- **Candidate (not yet written):**
  `memory/blender_addon_zip_must_track_source.md` — the v1.3.5
  repackage lesson. Filing as a candidate; can write next session if
  the same gap recurs (one-shot lessons sometimes don't need a crumb).

## What this session did NOT do

- Run camera-scope NoneType retest on flame-01 — round-trip unblock
  was the gate; that retest is now ready for the next session.
- Touch the wiretap "No route" infra issue.
- Write the `blender_addon_zip_must_track_source.md` memory crumb (see
  candidate note above).
- Bump CLAUDE.md's "Blender 4.5+" line — intentionally untouched; the
  project still supports 4.5 and the fix is additive.

## Reference: full commit list since 5d8989b (day-session passoff)

```
9319dbd docs(quick-260429-gde): bump README + seamless-bridge install steps to forge_sender v1.3.5
36cf922 docs(passoff): 2026-04-29 evening — 260429-gde shipped, round-trip clean on portofino + flame-01
7ee89a9 docs(todos): full closure on slotted-actions todo — flame-01 UAT also passed
7cabf0f docs(todos): add closure note + fix-commit log to slotted-actions todo
f27219d docs(todos): close Blender 5.1 slotted-actions fcurves todo — UAT passed on portofino
543f458 build(quick-260429-gde): repackage forge_sender v1.3.5 addon zip with slotted-actions fcurves fix
bc21b3e docs(quick-260429-gde): version-tolerant fcurves walk for Blender slotted-actions API (5.x compat fix in flame_math.py)
f064824 fix(quick-260429-gde): version-tolerant fcurves walk for Blender slotted-actions API
a3cf531 test(quick-260429-gde): add failing tests for _iter_action_fcurves three-tier walk
```

9 commits: 1 test, 1 fix, 1 docs (PLAN/RESEARCH/SUMMARY/STATE),
1 build (zip repackage), 3 todo-closure passes (initial close, closure
note, full-machine closure), 1 evening passoff, 1 user-docs sync
(README + seamless-bridge.md install steps).
