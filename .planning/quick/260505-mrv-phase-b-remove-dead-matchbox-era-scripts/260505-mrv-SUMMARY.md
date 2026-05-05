---
phase: quick-260505-mrv
plan: 01
subsystem: flame-hook + project-docs
tags:
  - cleanup
  - matchbox-era
  - dead-code
  - docs
  - forge-family-tier-3
dependency-graph:
  requires:
    - "memory/forge_family_tier_model.md (Tier-3 classification of forge-bridge)"
    - "memory/matchbox_direction_shelved.md (2026-05-01 PySide2-is-the-surface decision)"
    - "memory/forge_install_pycache_gap.md (install.sh purges only camera_match/__pycache__)"
    - "memory/forge_pytest_blender_session_exit.md (-p no:pytest-blender gating)"
  provides:
    - "post-state where flame/ contains only camera_match_hook.py, scale_picker_dialog.py, rotation_diagnostic.py, __init__.py"
    - "production-bug fix: deletes the source of '[PYTHON HOOK] Ignoring python hooks from .../apply_solve.py' Flame boot warning"
    - "CLAUDE.md / STACK.md / STRUCTURE.md / PASSOFF.md aligned with three-tier forge family architecture"
  affects:
    - "next install rollout (warning class disappears on Flame restart — out of scope to verify here)"
    - "Phase B sequel work: forge-blender migration, forge-io scaffold, forge_flame namespace restructuring (all out of scope this plan)"
tech-stack:
  added: []
  patterns:
    - "git rm (atomic stage of deletions alongside same-commit comment edits)"
    - "Closed dead-set audit: grep -rn for from-imports across .py before deletion"
    - "Comment rewrite preserves historical provenance in prose form (no broken file:line citations remain)"
key-files:
  deleted:
    - "flame/apply_solve.py (~9.7KB Matchbox-era diagnostic; nothing outside the closed cycle imported it)"
    - "flame/solve_and_update.py (~8.7KB; same closed cycle)"
    - "flame/action_export.py (~9.3KB; same closed cycle)"
  modified:
    - "flame/camera_match_hook.py (2 comment-only edits at L2515-2518 + L2545-2546; zero behaviour change)"
    - "CLAUDE.md (Constraints split runtime/dev-only tooling; numpy bullet drops solve_and_update.py reference)"
    - ".planning/codebase/STACK.md (numpy bullet matches CLAUDE.md edit)"
    - ".planning/codebase/STRUCTURE.md (flame/ subtree refreshed: drop 3 deleted scripts, add scale_picker_dialog.py, drop stale 1697 LOC count)"
    - "PASSOFF.md (L171 'still candidates for removal' note resolved)"
  created: []
decisions:
  - "Reframe forge-bridge as Tier-3 dev-time tooling (analogous to pytest), NOT a calibrator runtime dependency — the hook never imports it. Per memory/forge_family_tier_model.md."
  - "Preserve historical pattern provenance in prose form when removing file:line citations, rather than deleting the comment outright — keeps Tier-2 fallback rationale readable in _infer_plate_resolution."
  - "Leave rotation_diagnostic.py in place as a 'review separately' item; out of scope for Phase B (only the closed three-file cycle was verified dead this session)."
  - "Add scale_picker_dialog.py row to STRUCTURE.md while we're touching the flame/ subtree — has been silently out-of-date since quick-260501-knl shipped (commit 699c601, 2026-05-01)."
metrics:
  duration_minutes: 3
  tasks_completed: 3
  tasks_total: 3
  files_changed: 8
  commits: 2
  test_count: 542
  test_skipped: 2
  test_failures: 0
  test_runtime_seconds: 2.7
  completed_date: "2026-05-05"
---

# Quick 260505-mrv: Phase B Forge Family Cleanup — Remove Dead Matchbox-Era Scripts Summary

**One-liner:** Deleted three Matchbox-era closed-cycle dead scripts (`flame/apply_solve.py`, `flame/solve_and_update.py`, `flame/action_export.py`) that were causing a `[PYTHON HOOK] Ignoring python hooks from .../apply_solve.py` warning on Flame boot under flattened-install conditions, and reclassified forge-bridge as Tier-3 dev-only tooling (not a calibrator runtime dependency) across CLAUDE.md, STACK.md, STRUCTURE.md, and PASSOFF.md.

## Scope Recap

Three small deliverables, two commits:

1. **Deletion + hook comment fix** (commit `69ce782`)
   - `git rm` of all three target files
   - Two comment-only rewrites in `flame/camera_match_hook.py:_infer_plate_resolution` (lines 2515-2518 and 2545-2546) to drop the now-broken `flame/apply_solve.py:269` file:line citations and replace with prose-form historical context

2. **Codebase doc refresh** (commit `4be06ea`)
   - CLAUDE.md: split Constraints "Runtime dependencies" line so forge-bridge moves from runtime-dep list into its own "Dev-only tooling" bullet (Tier-3 classification per `memory/forge_family_tier_model.md`)
   - CLAUDE.md + STACK.md: drop the "Inlined into solve_and_update.py for forge-bridge HTTP execution" trailing clause from the numpy-Critical bullet
   - STRUCTURE.md: refresh `flame/` subtree — remove three "Legacy diagnostic script" rows, add the missing `scale_picker_dialog.py` row, drop stale "1697 LOC" count on `camera_match_hook.py`
   - PASSOFF.md: resolve the line-171 "still candidates for removal" note from the Wiretap-migration era

3. **Verification gate** (no commit)
   - `install.sh` audited — zero references to the three deleted modules
   - Wider-tree audit (excluding `.planning/`) confirmed only intentional historical-prose mentions remain in PASSOFF.md and the rewritten hook comments
   - Full pytest suite: **542 passed, 2 skipped, 0 failed in 2.7s** with `-p no:pytest-blender`

## Why the Three Files Were Dead

The orchestrator's safety audit (captured in the PLAN's `<audit_findings>` block) verified this is a **closed dead set**:

- The only import edge involving any of the three was `flame/apply_solve.py:30`:
  ```python
  from flame.action_export import camera_solve_to_flame_params, matrix_to_euler_xyz
  ```
- `grep -rn` across all `.py` files showed nothing in `forge_core/`, `forge_flame/`, `flame/camera_match_hook.py`, `tools/blender/`, or `tests/` imports any of them.
- The two `flame/camera_match_hook.py` references (lines 2516 and 2543) were code-comment file:line citations only — no actual import or call edge.
- All three scripts predate the `2026-05-01` decision to make PySide2 line-drawing the artist surface (`memory/matchbox_direction_shelved.md`); they were never wired into the live PySide2 path.

## Production Bug Fixed

When the install layout flattens (per the rsync-with-trailing-slashes failure mode documented in `.planning/phases/04.2-aim-target-rig-camera-orientation-round-trip/04.2-HUMAN-UAT.md` lines 50-127), `flame/apply_solve.py` lands at the top of `/opt/Autodesk/shared/python/`. Flame's hook scanner picks it up, tries the `from flame.action_export import …` line at module load, and logs:

```
ModuleNotFoundError: No module named 'flame.action_export';
                     'flame' is not a package
[PYTHON HOOK] An error occurred. Ignoring python hooks from
/opt/Autodesk/shared/python/apply_solve.py
```

Deleting the source removes the warning class entirely. **Verification of the actual Flame-boot side-effect is deferred** to the next install rollout — out of scope for this dev-side cleanup quick task. Documented in the Task 1 commit body.

## Forge Family Three-Tier Architecture (Documented Decision)

Per `memory/forge_family_tier_model.md`:

| Tier | Members | Role |
|------|---------|------|
| Tier 1 | forge-calibrator (this repo) | Production VFX tool inside Flame |
| Tier 2 | forge-blender, forge-io | Sibling production hooks (separate repos / future) |
| Tier 3 | forge-core (pure-numpy math), forge-io (pixels + OCIO; sketch as of 2026-05), forge-bridge (dev-time RPC into Flame) | Shared libraries + dev tooling |

Before this cleanup, CLAUDE.md framed forge-bridge as a "Runtime dependency" alongside numpy/opencv/Wiretap. That was historically accurate when `solve_and_update.py` was the live solver-application path, but it has been wrong since the calibrator's hook took over the apply path. After deletion, the calibrator has **zero forge-bridge runtime dependencies**; install.sh still deploys the bridge for dev probes, which is correct per the Tier-3 model. The reframing as "Dev-only tooling, analogous to pytest" matches actual usage.

## Commits

| # | Commit | Subject | Files | Insertions / Deletions |
|---|--------|---------|-------|-------------------------|
| 1 | `69ce782` | refactor(quick-260505-mrv): remove dead Matchbox-era scripts (Phase B forge family cleanup) | 4 | +6 / −836 |
| 2 | `4be06ea` | docs(quick-260505-mrv): reclassify forge-bridge as dev-only; refresh codebase docs after script deletion | 4 | +8 / −9 |

Total: **2 commits, 8 files touched, +14 / −845 lines.**

## Test Results

```
$ conda run -n forge pytest tests/ -p no:pytest-blender -q
........................................................................ [ 13%]
........................................................................ [ 26%]
........................................................................ [ 39%]
........................................................................ [ 53%]
........................................................................ [ 66%]
........................................................................ [ 79%]
........................................................................ [ 92%]
......................................                                   [100%]
542 passed, 2 skipped in 2.70s
```

Matches STATE.md's last-recorded baseline ("542/2 tests still green" after quick-260501-u7q on 2026-05-02). Zero failures, zero new skips.

The 2 skipped tests are pre-existing wave-pointer skips from Phase 04.4 Wave 0 stubs (per STATE.md decisions log) — not introduced by this work.

## Deviations from Plan

None — plan executed exactly as written.

The Task 1 step 3 grep-sanity caveat (NOTE about `apply_solve` appearing in rewritten prose being acceptable) was the relevant judgment call: the rewritten comments do contain "apply_solve.py" in prose form (e.g., "the legacy Matchbox-era apply_solve.py before its removal in quick-260505-mrv"), and the wider-tree audit in Task 3 step 2 surfaced 3 such occurrences (PASSOFF.md L171 + the two hook-comment rewrites). All three are intentional historical-context references, not broken file:line citations or live imports — matches the plan's explicit acceptance criterion ("no broken file-path citations and no live import references", not "the literal word never appears").

## Authentication Gates

None — this is a pure code-and-docs cleanup with no external service interaction.

## Deferred / Out-of-Scope (For Future Planning Sessions)

The orchestrator's `<background>` for this plan flagged three items as **explicitly out of scope** and deferred to their own future phases. Captured here so the next planning session has the pointer:

1. **forge-blender migration** — extracting the FBX/Blender bits out of `forge_flame/` into a sibling `forge-blender` repo. Large, separate work; will need its own multi-task plan.
2. **forge-io repo scaffold** — greenfield Tier-3 library for pixels + OCIO (currently sketched in `memory/forge_family_tier_model.md` notes as of 2026-05).
3. **forge_flame namespace restructuring** — renaming/restructuring inside the current repo to align with the three-tier model. Not touched in this plan; Phase B is hook + docs only.

Two additional follow-up items surfaced incidentally during this work:

4. **`flame/rotation_diagnostic.py` audit** — left in place with a "review separately" note in STRUCTURE.md. Could be another quick task to verify it's also dead. ~4.7KB; was a sibling of the three deleted scripts.
5. **`/opt/Autodesk/shared/python/apply_solve.py` boot-warning verification** — confirm the warning class actually disappears on the next Flame restart after a fresh install rollout. Belongs to the install-rollout cycle, not this dev-side cleanup.

## Self-Check

Verified post-state on disk and in git:

- ✅ `flame/apply_solve.py` absent on disk (FOUND deletion in commit `69ce782`)
- ✅ `flame/solve_and_update.py` absent on disk (FOUND deletion in commit `69ce782`)
- ✅ `flame/action_export.py` absent on disk (FOUND deletion in commit `69ce782`)
- ✅ `flame/camera_match_hook.py` parses as valid Python (`ast.parse` OK)
- ✅ Zero `apply_solve.py:NNN` / `action_export.py:NNN` / `solve_and_update.py:NNN` file:line citations in `flame/camera_match_hook.py`
- ✅ Zero `from flame.{apply_solve,action_export,solve_and_update}` import statements anywhere in tree
- ✅ CLAUDE.md contains "Dev-only tooling" classification for forge-bridge
- ✅ CLAUDE.md no longer references `solve_and_update.py`
- ✅ STACK.md no longer references `solve_and_update.py`
- ✅ STRUCTURE.md `flame/` subtree shows actual current contents (camera_match_hook + scale_picker_dialog + rotation_diagnostic + __init__) with no rows for deleted scripts
- ✅ STRUCTURE.md adds `scale_picker_dialog.py` row (was silently missing since quick-260501-knl)
- ✅ PASSOFF.md "still candidates for removal" note resolved
- ✅ install.sh contains zero references to the three deleted modules
- ✅ Two new commits in git log (`69ce782`, `4be06ea`); zero commits from this plan in `forge_core/`, `forge_flame/`, `tools/blender/`, or any test file (Phase B = hook + docs only)
- ✅ Full pytest suite: 542 passed, 2 skipped, 0 failed

## Self-Check: PASSED
