---
phase: quick-260505-mrv
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - flame/apply_solve.py                  # DELETE
  - flame/solve_and_update.py             # DELETE
  - flame/action_export.py                # DELETE
  - flame/camera_match_hook.py            # comment-only edits at ~2516, ~2543
  - CLAUDE.md                             # reclassify forge-bridge as dev-only; drop solve_and_update.py reference
  - .planning/codebase/STACK.md           # drop solve_and_update.py reference
  - .planning/codebase/STRUCTURE.md       # remove three "Legacy diagnostic script" rows
  - PASSOFF.md                            # mark removal-candidates note as completed
autonomous: true
requirements:
  - PHASE-B-DELETE-DEAD-SCRIPTS
  - PHASE-B-CLAUDEMD-RECLASSIFY-FORGE-BRIDGE
  - PHASE-B-CODEBASE-DOC-REFRESH

must_haves:
  truths:
    - "flame/apply_solve.py, flame/solve_and_update.py, flame/action_export.py no longer exist on disk"
    - "No remaining import or code-callsite references to the three deleted modules anywhere in the repo (comments allowed only if reframed as historical context)"
    - "install.sh deploys nothing referencing the three deleted modules (no copy lines, no preflight checks)"
    - "CLAUDE.md classifies forge-bridge as a dev-only Tier-3 probe tool, not a calibrator runtime dependency"
    - "STACK.md and STRUCTURE.md are consistent with the post-deletion file tree"
    - "Full pytest suite passes with `pytest tests/ -p no:pytest-blender`"
    - "On Flame boot, the previously-logged `[PYTHON HOOK] Ignoring python hooks from /opt/Autodesk/shared/python/apply_solve.py` warning no longer occurs (verified after next install + Flame restart — out of scope for this quick task; documented in commit body)"
  artifacts:
    - path: "flame/apply_solve.py"
      provides: "MUST NOT EXIST after this plan"
    - path: "flame/solve_and_update.py"
      provides: "MUST NOT EXIST after this plan"
    - path: "flame/action_export.py"
      provides: "MUST NOT EXIST after this plan"
    - path: "CLAUDE.md"
      provides: "Updated Constraints + Tech Stack sections"
      contains: "forge-bridge"
    - path: ".planning/codebase/STACK.md"
      provides: "Tech stack doc with no reference to solve_and_update.py"
    - path: ".planning/codebase/STRUCTURE.md"
      provides: "Directory layout with no rows for the three deleted scripts"
  key_links:
    - from: "Flame hook scanner at /opt/Autodesk/shared/python/"
      to: "apply_solve.py top-level pickup"
      via: "absence of the file post-install"
      pattern: "apply_solve\\.py NOT in install tree"
    - from: "flame/camera_match_hook.py:_infer_plate_resolution comments"
      to: "historical pattern provenance (no longer points to a deleted file)"
      via: "rewritten or dropped citation"
      pattern: "no remaining `flame/apply_solve\\.py:` substring in camera_match_hook.py"
---

<objective>
Phase B of the forge family architecture cleanup (continuing from Phase A discussion captured in
`memory/forge_family_tier_model.md` and `memory/forge_identity.md`).

Delete the three Matchbox-era "diagnostic scripts" that no live code path imports, fix the
production hook-load error they cause when picked up by Flame's hook scanner from
`/opt/Autodesk/shared/python/`, and reclassify forge-bridge in CLAUDE.md as a dev-only Tier-3
probe tool (not a calibrator runtime dependency).

Purpose:
  - Remove a class of production warnings (`[PYTHON HOOK] Ignoring python hooks from
    .../apply_solve.py`) that fires on Flame boot whenever the install gets flattened
    (documented in `.planning/phases/04.2-aim-target-rig-camera-orientation-round-trip/
    04.2-HUMAN-UAT.md` lines 50-127).
  - Bring CLAUDE.md and codebase/{STACK,STRUCTURE}.md into agreement with the actual three-tier
    forge family architecture: forge-bridge is dev-time tooling (analogous to pytest), NOT a
    runtime dep of the calibrator hook.
  - Close the "still candidates for removal" note from PASSOFF.md line 171 — that note has been
    open since at least the Wiretap migration.

Output:
  - Three .py files removed from `flame/`.
  - Two comment lines in `flame/camera_match_hook.py` rewritten to drop the dead-file citation.
  - CLAUDE.md Constraints + Tech Stack sections corrected.
  - .planning/codebase/{STACK,STRUCTURE}.md corrected.
  - PASSOFF.md historical note resolved.
  - Full pytest suite green (542 tests, gated with `-p no:pytest-blender` per
    `memory/forge_pytest_blender_session_exit.md`).

OUT OF SCOPE (deferred to their own future phases per the orchestrator's <background>):
  - forge-blender migration (FBX/Blender bits — large, separate)
  - forge-io repo scaffold (greenfield — separate)
  - Any forge_flame/, forge_core/, or Blender-side changes
  - Renaming/restructuring the forge_flame namespace
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@CLAUDE.md
@.planning/codebase/STACK.md
@.planning/codebase/STRUCTURE.md
@flame/apply_solve.py
@flame/solve_and_update.py
@flame/action_export.py
@install.sh

<!-- Critical background captured by the orchestrator's safety audit (2026-05-05): -->

<audit_findings>

1. **Closed dead-set verified.** `grep -rn` across all .py files shows that the only import
   edge involving any of the three target files is `flame/apply_solve.py:30`:
       `from flame.action_export import camera_solve_to_flame_params, matrix_to_euler_xyz`
   The three files form a closed cycle. Nothing in `forge_core/`, `forge_flame/`,
   `flame/camera_match_hook.py`, `tools/blender/`, or `tests/` imports any of them.

2. **Hook references are comments only.** `flame/camera_match_hook.py` lines 2516 and 2543
   cite `flame/apply_solve.py:269` as a pattern source in code comments inside
   `_infer_plate_resolution`. The actual code at those lines does NOT import or call
   apply_solve — it just references it as historical provenance for the
   `flame.batch.width/height` Tier-2 fallback. The cited line `apply_solve.py:269` reads
   `width = int(b.width.get_value())` — same pattern, but no live dependency on the file.

3. **Production bug being fixed.** The install copies `flame/apply_solve.py` to
   `/opt/Autodesk/shared/python/apply_solve.py` (under flattened-install conditions).
   Flame's hook scanner picks it up at boot, tries `from flame.action_export import …`,
   fails with `ModuleNotFoundError("No module named 'flame.action_export'; 'flame' is not
   a package")`, and logs the warning. Deleting these three files removes the warning
   class entirely.

4. **forge-bridge is Tier 3 dev-only** per `memory/forge_family_tier_model.md`:
       Tier 3 — Shared libraries  forge-core (pure-numpy math)
                                  forge-io (pixels in + OCIO; sketch as of 2026-05)
                                  forge-bridge (dev-time RPC into Flame)
   The calibrator's hook never imports forge-bridge. The only places that did were these
   three Matchbox-era scripts (now being deleted). After deletion, the calibrator has zero
   forge-bridge runtime dependencies; install.sh still deploys the bridge for dev probes,
   which is correct per the Tier-3 model.

5. **Matchbox direction shelved 2026-05-01** per `memory/matchbox_direction_shelved.md`.
   PySide2 line-drawing is the artist surface. These three scripts predate that decision
   and were never wired into the PySide2 path.

6. **install.sh has no references to the deleted files** — verified by grep. The bridge
   install section (`step "forge-bridge"`) is unrelated and stays as-is.

7. **PASSOFF.md line 171** explicitly lists `flame/apply_solve.py` and
   `flame/solve_and_update.py` as "still candidates for removal" since at least the
   Wiretap migration. Update to reflect that they have now been removed.

8. **Test gate.** Per `memory/forge_pytest_blender_session_exit.md`, run pytest with
   `-p no:pytest-blender` to avoid the plugin exiting the session if Blender isn't on
   PATH in the dev shell. Either `-p no:pytest-blender` or
   `BLENDER_EXECUTABLE=/path/to/Blender pytest tests/` works.

</audit_findings>

<commit_style>
Repo convention from `git log --oneline -5`:
    docs(quick-260501-u7q): tester install-rollout polish — …
    feat(quick-260501-u7q): extend install.sh conda preflight …
    fix(scale-picker): drop plate-specific distance subtitle, …
Use `<type>(quick-260505-mrv): <subject>` shape. Two commits planned (see Tasks 1 + 2);
final test-run task is verification only and does NOT add a third commit.
</commit_style>

<interfaces>
<!-- The two comment-only edits inside flame/camera_match_hook.py.                   -->
<!-- Existing text quoted verbatim — preserve indentation and surrounding lines.     -->
<!-- Goal: keep the historical-pattern context, drop the now-invalid file:line cite. -->

LINE 2515-2516 — change:
```
      2. flame.batch.width/height -- batch-level fallback; same pattern
         used at flame/apply_solve.py:269.
```
To:
```
      2. flame.batch.width/height -- batch-level fallback; same one-liner
         (`int(flame.batch.width.get_value())`) was used by the legacy
         Matchbox-era apply_solve.py before its removal in
         quick-260505-mrv (Phase B forge family cleanup).
```

LINE 2543 — change:
```
    # Tier 2 — flame.batch.width/height (analog: flame/apply_solve.py:269).
```
To:
```
    # Tier 2 — flame.batch.width/height (legacy Matchbox-era apply_solve.py
    # used the same one-liner before its removal in quick-260505-mrv).
```

Net: zero behavioural change, zero file:line citations to deleted files, history preserved.
</interfaces>

</context>

<tasks>

<task type="auto">
  <name>Task 1: Delete the three dead Matchbox-era scripts and fix hook comments</name>
  <files>
    flame/apply_solve.py,
    flame/solve_and_update.py,
    flame/action_export.py,
    flame/camera_match_hook.py
  </files>
  <action>
    1. `git rm flame/apply_solve.py flame/solve_and_update.py flame/action_export.py`
       (use `git rm`, not plain `rm`, so the deletions are staged in the same commit as the
       hook comment edits). All three are dead per the audit findings — nothing outside the
       three-file cycle imports them.

    2. Edit `flame/camera_match_hook.py` per the `<interfaces>` block in <context>:
         - Lines 2515-2516 (inside `_infer_plate_resolution` docstring): replace the
           `flame/apply_solve.py:269` citation with the historical-context wording shown.
         - Line 2543 (Tier 2 inline comment): replace the `(analog: flame/apply_solve.py:269)`
           citation with the historical-context wording shown.
       Preserve indentation. No other lines change. No imports added or removed.

    3. Sanity-check before commit: `grep -n "apply_solve\|action_export\|solve_and_update"
       flame/camera_match_hook.py` must return zero matches (the rewrites drop the file:line
       form and use prose like "legacy Matchbox-era apply_solve.py" instead — no `apply_solve.py`
       substring should remain). Adjust the wording in the rewritten comments if needed.

       NOTE: We accept "apply_solve" appearing in the rewritten prose if it reads naturally —
       grep is for the file:line form (`apply_solve.py:269`) and any remaining `from flame.…`
       imports. The acceptance criterion is "no broken file-path citations and no live import
       references", not "the literal word never appears."

    4. Commit:
       ```
       git commit -m "refactor(quick-260505-mrv): remove dead Matchbox-era scripts (Phase B forge family cleanup)

       Delete flame/apply_solve.py, flame/solve_and_update.py, and flame/action_export.py.
       These three files form a closed dead set — verified via grep across all .py files
       that nothing outside the cycle imports any of them. They are leftover from the
       shelved Matchbox calibrator direction (memory/matchbox_direction_shelved.md,
       2026-05-01); the live calibrator surface is the PySide2 line-drawing window.

       Production fix: when the install layout flattens (per the rsync-with-trailing-slashes
       failure mode documented in .planning/phases/04.2-aim-target-rig-camera-orientation-
       round-trip/04.2-HUMAN-UAT.md L50-127), apply_solve.py lands at the top of
       /opt/Autodesk/shared/python/. Flame's hook scanner picks it up, tries the
       'from flame.action_export import …' line, and logs:

           ModuleNotFoundError: No module named 'flame.action_export';
                                'flame' is not a package
           [PYTHON HOOK] An error occurred. Ignoring python hooks from
           /opt/Autodesk/shared/python/apply_solve.py

       Deleting the source removes the warning class entirely.

       Also drops two now-broken citations in flame/camera_match_hook.py:_infer_plate_resolution
       (lines ~2516, ~2543) that pointed at flame/apply_solve.py:269. The historical pattern
       context is preserved in prose form so the Tier-2 fallback's provenance stays readable.

       No behavioural change to the live hook. No import edges added or removed. Tests
       remain green (verified via 'pytest tests/ -p no:pytest-blender' in Task 3 below)."
       ```
  </action>
  <verify>
    <automated>
      ! [ -e flame/apply_solve.py ] &&
      ! [ -e flame/solve_and_update.py ] &&
      ! [ -e flame/action_export.py ] &&
      [ -z "$(grep -nE 'apply_solve\.py:[0-9]+|action_export\.py:[0-9]+|solve_and_update\.py:[0-9]+' flame/camera_match_hook.py 2>/dev/null)" ] &&
      [ -z "$(grep -rnE 'from flame\.(apply_solve|action_export|solve_and_update)' --include='*.py' . 2>/dev/null)" ] &&
      python3 -c "import ast; ast.parse(open('flame/camera_match_hook.py').read())"
    </automated>
  </verify>
  <done>
    - All three .py files are absent from `flame/` (and staged as deletions in git).
    - No remaining file:line citations of the form `apply_solve.py:NNN` (or the other two)
      anywhere in `flame/camera_match_hook.py`.
    - No `from flame.{apply_solve,action_export,solve_and_update}` imports anywhere in the
      tree.
    - `flame/camera_match_hook.py` still parses as valid Python (catches accidental syntax
      breakage from the two comment edits).
    - Single commit landed with the message above.
  </done>
</task>

<task type="auto">
  <name>Task 2: Reclassify forge-bridge as dev-only in CLAUDE.md and update codebase docs</name>
  <files>
    CLAUDE.md,
    .planning/codebase/STACK.md,
    .planning/codebase/STRUCTURE.md,
    PASSOFF.md
  </files>
  <action>
    Four doc edits, all in one commit:

    A. **CLAUDE.md, line 13** (Constraints section, "Runtime dependencies" line) — current text:
       ```
       - **Runtime dependencies**: numpy + opencv-python in a conda `forge` env (dev-side);
         PyOpenColorIO from Flame's bundled Python (NOT installed in forge — version-conflict
         risk); Wiretap SDK from Flame; Blender 4.5+ as a subprocess; forge-bridge as the
         HTTP RPC endpoint into Flame's Python.
       ```
       Replace with:
       ```
       - **Runtime dependencies**: numpy + opencv-python in a conda `forge` env (dev-side);
         PyOpenColorIO from Flame's bundled Python (NOT installed in forge — version-conflict
         risk); Wiretap SDK from Flame; Blender 4.5+ as a subprocess.
       - **Dev-only tooling**: forge-bridge is a Tier-3 dev-time RPC probe (HTTP /exec into
         Flame's Python at 127.0.0.1:9999), analogous to pytest. NOT a calibrator runtime
         dependency — the hook never imports it. install.sh deploys it for dev convenience;
         see `memory/forge_family_tier_model.md`.
       ```
       Line 17's mention of forge-bridge in the **Security posture** bullet stays as-is —
       it accurately describes the bridge's network binding when it IS installed.

    B. **CLAUDE.md, line 42** (Key Dependencies → Critical → numpy line) — current text:
       ```
       - numpy - Solver math: 2VP intersection, FOV/focal conversion, rotation composition
         (Euler ZYX), matrix transforms. Inlined into `solve_and_update.py` for forge-bridge
         HTTP execution.
       ```
       Replace with:
       ```
       - numpy - Solver math: 2VP intersection, FOV/focal conversion, rotation composition
         (Euler ZYX), matrix transforms.
       ```
       (Drop the second sentence — `solve_and_update.py` no longer exists.)

    C. **.planning/codebase/STACK.md, line 55** (Key Dependencies → Critical → numpy bullet) —
       same edit as B above. Current:
       ```
       - numpy - Solver math: 2VP intersection, FOV/focal conversion, rotation composition
         (Euler ZYX), matrix transforms. Inlined into `solve_and_update.py` for forge-bridge
         HTTP execution.
       ```
       Replace with:
       ```
       - numpy - Solver math: 2VP intersection, FOV/focal conversion, rotation composition
         (Euler ZYX), matrix transforms.
       ```

    D. **.planning/codebase/STRUCTURE.md, lines 11-15** (Directory Layout → flame/ subtree) —
       remove the three "Legacy diagnostic script" rows. Current:
       ```
       ├── flame/                         # Flame batch hook entry point
       │   ├── __init__.py
       │   ├── camera_match_hook.py       # Main hook (1697 LOC, ~93KB) — entry point
       │   ├── action_export.py           # Legacy diagnostic script
       │   ├── apply_solve.py             # Legacy diagnostic script
       │   ├── solve_and_update.py        # Legacy diagnostic script
       │   └── rotation_diagnostic.py     # Legacy diagnostic script
       ```
       Replace with:
       ```
       ├── flame/                         # Flame batch hook entry point
       │   ├── __init__.py
       │   ├── camera_match_hook.py       # Main hook (~93KB) — entry point
       │   ├── scale_picker_dialog.py     # Forge-themed PySide6 scale picker (quick-260501-knl)
       │   └── rotation_diagnostic.py     # Legacy diagnostic script (review separately)
       ```
       Notes:
         - Drop the LOC count from the camera_match_hook.py row — that 1697 figure is from
           2026-04-19 and is now stale (file is closer to 2700 LOC). Keep the size feel
           ("~93KB") which is more stable across edits.
         - Add `scale_picker_dialog.py` since it's been shipping since quick-260501-knl
           (commit 699c601) and is part of the install — `install.sh` SOURCE_SCALE_PICKER
           references it explicitly. The doc tree has been silently out-of-date on this
           since early May.
         - `rotation_diagnostic.py` is NOT in scope for this Phase B cleanup. Leave it
           with a "review separately" note. (Audit it in a separate quick task if/when
           someone wants to verify it's also dead.)

    E. **PASSOFF.md, line 171** — current text contains:
       ```
       …`flame/apply_solve.py`, `flame/solve_and_update.py`, `matchbox/` from earlier passoffs
       are still candidates for removal.…
       ```
       Replace with:
       ```
       …`flame/apply_solve.py` and `flame/solve_and_update.py` were removed in
       quick-260505-mrv (2026-05-05) along with `flame/action_export.py`. `matchbox/` stays
       as a repo artifact of the shelved direction (memory/matchbox_direction_shelved.md).…
       ```
       Preserve the rest of the surrounding paragraph verbatim.

    F. Commit:
       ```
       git commit -m "docs(quick-260505-mrv): reclassify forge-bridge as dev-only; refresh codebase docs after script deletion

       CLAUDE.md:
         - Constraints: split runtime deps from dev-only tooling. forge-bridge moves from
           runtime-dep list to its own 'Dev-only tooling' bullet, framed as a Tier-3 RPC
           probe (memory/forge_family_tier_model.md). The calibrator hook never imports it.
         - Key Dependencies: drop the 'Inlined into solve_and_update.py for forge-bridge
           HTTP execution' clause from the numpy line — solve_and_update.py was deleted
           in the previous commit.

       .planning/codebase/STACK.md:
         - Same numpy-line edit as CLAUDE.md (the two docs duplicate this bullet).

       .planning/codebase/STRUCTURE.md:
         - Remove the three 'Legacy diagnostic script' rows for action_export.py,
           apply_solve.py, and solve_and_update.py from the flame/ subtree.
         - Add the missing scale_picker_dialog.py row (shipping since quick-260501-knl).
         - Drop stale 1697 LOC count on camera_match_hook.py row.

       PASSOFF.md:
         - Resolve the 'still candidates for removal' note (line 171) — those files
           are now removed.

       No code changes in this commit. Verification: 'pytest tests/ -p no:pytest-blender'
       still passes (confirmed in the next task)."
       ```
  </action>
  <verify>
    <automated>
      ! grep -qE 'forge-bridge as the HTTP RPC endpoint' CLAUDE.md &&
      ! grep -q 'solve_and_update\.py' CLAUDE.md &&
      ! grep -q 'solve_and_update\.py' .planning/codebase/STACK.md &&
      ! grep -qE 'action_export\.py|apply_solve\.py|solve_and_update\.py' .planning/codebase/STRUCTURE.md &&
      grep -q 'scale_picker_dialog\.py' .planning/codebase/STRUCTURE.md &&
      grep -q 'Dev-only tooling' CLAUDE.md &&
      ! grep -q 'still candidates for removal' PASSOFF.md
    </automated>
  </verify>
  <done>
    - CLAUDE.md no longer lists forge-bridge as a runtime dep; reclassified under "Dev-only
      tooling" with a pointer to the tier-model memory.
    - CLAUDE.md no longer references the deleted `solve_and_update.py`.
    - STACK.md no longer references the deleted `solve_and_update.py`.
    - STRUCTURE.md's flame/ subtree shows the actual current contents
      (camera_match_hook.py, scale_picker_dialog.py, rotation_diagnostic.py, __init__.py)
      with no rows for any of the three deleted scripts.
    - PASSOFF.md line 171's "still candidates for removal" note is resolved.
    - Single commit landed with the message above.
  </done>
</task>

<task type="auto">
  <name>Task 3: Verify install.sh has no broken references and run the full test suite</name>
  <files>
    (none modified — verification-only)
  </files>
  <action>
    1. Audit install.sh for any references to the three deleted modules. Per the orchestrator's
       audit, none should exist — this is the belt-and-suspenders pass:
       ```
       grep -nE 'apply_solve|action_export|solve_and_update' install.sh
       ```
       Expected output: empty. If anything turns up, STOP and report — would mean the audit
       missed an install copy line and the plan needs an amendment task.

    2. Audit any remaining references in the wider tree (scripts/, README.md, docs/, etc.):
       ```
       grep -rnE 'apply_solve|action_export|solve_and_update' \
           --include='*.py' --include='*.sh' --include='*.md' \
           --exclude-dir=__pycache__ --exclude-dir=.planning --exclude-dir=.git \
           . 2>/dev/null
       ```
       Expected: empty (the .planning/ exclusion is deliberate — phase summaries from old
       phases naturally cite these historical files and SHOULD stay as historical record).
       If anything outside .planning/ turns up, STOP and report.

    3. Run the full pytest suite with the pytest-blender plugin disabled per
       `memory/forge_pytest_blender_session_exit.md`:
       ```
       cd /Users/cnoellert/Documents/GitHub/forge-calibrator
       conda run -n forge pytest tests/ -p no:pytest-blender -q
       ```
       Expected: all tests pass. Per STATE.md, the suite was last reported at "542/2 tests
       still green" after quick-260501-u7q (2026-05-02). Number of tests may differ slightly
       — what matters is zero failures.

    4. If pytest reports failures, STOP and report. Do NOT amend, do NOT make additional
       changes — the deletions are conservative (closed dead set, no live imports), so
       any failure indicates either:
         (a) the audit missed a callsite (revert the deletions, investigate)
         (b) a pre-existing flake unrelated to this work (rerun the failing test in
             isolation; if still fails, capture in the SUMMARY)
         (c) an environment problem (Blender plugin, conda env drift, etc.)

    5. No commit in this task — it's verification only. The two prior commits are the
       deliverables.
  </action>
  <verify>
    <automated>
      [ -z "$(grep -nE 'apply_solve|action_export|solve_and_update' install.sh 2>/dev/null)" ] &&
      [ -z "$(grep -rnE 'apply_solve|action_export|solve_and_update' --include='*.py' --include='*.sh' --include='*.md' --exclude-dir=__pycache__ --exclude-dir=.planning --exclude-dir=.git . 2>/dev/null)" ] &&
      conda run -n forge pytest tests/ -p no:pytest-blender -q
    </automated>
  </verify>
  <done>
    - install.sh contains zero references to the three deleted modules.
    - No references outside `.planning/` (historical phase summaries are preserved).
    - Full pytest suite passes with `pytest tests/ -p no:pytest-blender`.
    - No new commits in this task — verification only.
  </done>
</task>

</tasks>

<verification>
After all three tasks land, verify the post-state:

1. **File deletions landed:**
   ```
   ls flame/ | grep -E 'apply_solve|action_export|solve_and_update'   # must be empty
   git log --oneline -3 | head -3                                      # 2 new commits visible
   ```

2. **Hook is import-clean:**
   ```
   grep -nE 'from flame\.(apply_solve|action_export|solve_and_update)' \
       --include='*.py' -r .                                           # must be empty
   ```

3. **Comment citations are gone:**
   ```
   grep -nE 'apply_solve\.py:[0-9]+' flame/camera_match_hook.py        # must be empty
   ```

4. **Doc consistency:**
   ```
   grep -c 'forge-bridge' CLAUDE.md          # still nonzero (Security posture mention stays)
   grep -c 'solve_and_update' CLAUDE.md      # 0
   grep -c 'solve_and_update' .planning/codebase/STACK.md  # 0
   ```

5. **Tests green:**
   ```
   conda run -n forge pytest tests/ -p no:pytest-blender -q
   ```

6. **Out-of-scope deferred items NOT touched** (sanity):
   ```
   git diff HEAD~2 --stat | grep -E 'forge_core/|forge_flame/|tools/blender/'
   # must be empty — Phase B is hook + docs only
   ```
</verification>

<success_criteria>
Plan succeeds when ALL of the following are true:

  - The three target files are absent from `flame/` and the deletions are committed.
  - `flame/camera_match_hook.py` still parses as valid Python and contains no `*.py:NNN`
    citations of any deleted file.
  - No `from flame.{apply_solve,action_export,solve_and_update}` import statements exist
    anywhere in the tree.
  - CLAUDE.md classifies forge-bridge as Tier-3 dev-only tooling (not a runtime dep).
  - CLAUDE.md, STACK.md, and STRUCTURE.md contain zero stale references to the deleted
    scripts.
  - PASSOFF.md's "still candidates for removal" note is resolved.
  - install.sh contains zero references to the deleted scripts.
  - The full pytest suite passes with `pytest tests/ -p no:pytest-blender`.
  - Exactly two commits land (Task 1 = deletion + hook comments; Task 2 = doc updates).
    Task 3 is verification-only and produces no commit.
  - No files in `forge_core/`, `forge_flame/`, `tools/blender/`, or any test file are
    modified — Phase B is hook + docs only.

DEFERRED to a future install + Flame restart (NOT part of this plan's pass criteria, but
documented in the Task 1 commit body):
  - The `[PYTHON HOOK] Ignoring python hooks from .../apply_solve.py` warning disappears
    on next Flame boot. (Out of scope for the dev-side cleanup quick task; will be
    confirmed naturally on the next install rollout.)
</success_criteria>

<output>
After completion, create
`.planning/quick/260505-mrv-phase-b-remove-dead-matchbox-era-scripts/260505-mrv-SUMMARY.md`
covering:
  - The three files deleted, why they were dead (closed cycle audit), and what production
    bug class their absence fixes.
  - The CLAUDE.md / STACK.md / STRUCTURE.md / PASSOFF.md edits and how they reflect the
    Tier-3 forge family architecture decided this session.
  - Two commit SHAs.
  - pytest result line.
  - Pointer to the deferred items the orchestrator flagged out-of-scope (forge-blender
    migration, forge-io scaffold, forge_flame namespace restructuring) so the next planning
    session can pick them up.
</output>
