---
slug: camera-scope-nonetype-flame01
status: fixed_pending_live_verify
created: 2026-04-28T16:00:00Z
updated: 2026-04-28T16:25:00Z
resolved_commit: 70b3b79
trigger: |
  Camera-scope export 'NoneType' object is not callable regression on cold-install — recurs despite Phase 04.4 fix (commits f1e8853 + c680636). See .planning/todos/pending/2026-04-27-camera-scope-export-nonetype-regression-on-cold-install.md for full diagnostic context.
goal: find_and_fix
related_todos:
  - .planning/todos/pending/2026-04-27-camera-scope-export-nonetype-regression-on-cold-install.md
related_phases:
  - 04.4 (GAP-04.4-UAT-04 — premature closure)
related_commits:
  - f1e8853   # callable(getattr(parent, "export_fbx", None)) hardening
  - c680636   # install.sh recursive __pycache__ purge across camera_match + forge_core + forge_flame
  - 5926742   # diagnostic instrumentation removal (closure commit — instrumentation no longer in tree)
---

# Debug Session: camera-scope-nonetype-flame01

## Symptoms

### Expected behavior
Right-click on a Camera node inside an Action's schematic editor →
FORGE → Camera → Export Camera to Blender. The FBX is written
successfully, Blender launches in background, the bake script runs,
the .blend file opens (or path is surfaced to the user).

### Actual behavior
Tier-1 Flame dialog appears immediately:
**"Failed to write FBX: 'NoneType' object is not callable"**

Same surface symptom as GAP-04.4-UAT-04, which we thought was closed
in Phase 04.4. **Regression confirmed on flame-01 cold install
(2026-04-27)** — fresh RHEL 9 x86_64 workstation, no prior forge
install, env created from forge-env.yml, install.sh ran clean, all
sibling pycaches purged, forge-bridge v1.3.0 deployed and listening
on 127.0.0.1:9999.

### Error message (verbatim from Tier-1 dialog)
`Failed to write FBX: 'NoneType' object is not callable`

### Timeline
- 2026-04-27 AM: GAP-04.4-UAT-04 surfaced on dev workstation
  (macOS arm64, Flame 2026.2.1).
- 2026-04-27 mid-day: closed by hardening
  `_first_camera_in_action_selection` fast-path filter to require
  `callable(getattr(parent, "export_fbx", None))` (`f1e8853`),
  plus recursive `__pycache__` purge across `camera_match`,
  `forge_core`, `forge_flame` in `install.sh` (`c680636`). Live-verified
  on dev workstation after clean Flame restart.
- 2026-04-27 evening: cold install on **flame-01** (RHEL 9 x86_64,
  clean host, no prior forge install). Hook code on disk contains
  `f1e8853`; install.sh logged the pycache purge cleanly. Symptom
  reproduces immediately on Camera-scope right-click. User reports
  "same as we've been battling".
- 2026-04-28: filing this debug session as the next-cycle follow-up
  to the prematurely-closed GAP-04.4-UAT-04.

### Reproduction (current best guess — needs flame-01 reconfirmation)
1. Clean RHEL 9 Flame workstation, no prior forge install
2. `git clone` forge-calibrator at HEAD `5b47653` or later
3. `conda env create -f forge-env.yml`
4. `bash install.sh --force`
5. Launch Flame 2026.2.1
6. Open a Batch with at least one Action containing a Camera node
7. Double-click into the Action's schematic editor
8. Right-click the Camera node → FORGE → Camera → Export Camera to Blender
9. Observe the "Failed to write FBX: 'NoneType' object is not callable" dialog

**Action-scope right-click (right-click Action node in Batch top-level,
not a Camera inside its schematic) is UNTESTED on flame-01** —
status unknown.

## Current Focus

hypothesis: |
  H1 (asymmetric-fix): the Phase 04.4 hardening was applied to the
  fast path in `_first_camera_in_action_selection` but NOT to the
  `flame.batch.nodes` fallback scan. On flame-01 the fast path
  rejects a stably-broken cam.parent proxy, the fallback runs, finds
  an Action wrapper whose `.export_fbx is None`, and returns it
  unchecked. Downstream `action.export_fbx(...)` at fbx_io.py:152
  raises 'NoneType' object is not callable.

  H2 (RULED OUT) — see Eliminated section.
  H3 (third bypass path) — UNLIKELY; no such path in the post-04.4
  source; left as an open possibility pending flame-01 evidence.
test: |
  Two complementary tests:
  (T1) Static reproduction in pytest — extend the existing broken-
       proxy regression in tests/test_camera_match_hook.py to also
       cover the case where `flame.batch.nodes` returns a wrapper
       with `.export_fbx is None`. Should currently FAIL (return the
       broken wrapper), prove the bug at code level without flame-01.
  (T2) Live flame-01 evidence — re-instrument the pre-call diagnostic
       block (removed in 5926742) so the next failure on flame-01
       captures `type(cam.parent).__name__`, `type(returned_action).__name__`,
       and `callable(getattr(returned_action, "export_fbx", None))`.
       Single-shot log to /tmp/forge_export_camera_pre_call.log.
expecting: |
  T1 fails on current main (proves H1 at the code level).
  T2 on flame-01 shows: returned_action came from the fallback path,
     callable(export_fbx) is False, type(.).__name__ likely
     "PyActionFamilyNode" or similar base-class wrapper.
next_action: |
  Two viable next moves — orchestrator to surface choice to user:
  (A) Ship the symmetry fix BLIND (mirror the callable-export_fbx
      filter into the fallback + add a regression test). Low risk,
      tests prove behavior at code level. May not fully fix flame-01
      if BOTH paths return broken wrappers (then user gets the clean
      "Right-click a Camera node inside an Action's schematic..."
      dialog instead of the cryptic NoneType — better UX, but still
      doesn't bake).
  (B) Re-instrument first, ship fix after flame-01 evidence confirms
      the fallback wrapper-class shape. Higher confidence, longer
      cycle (needs user to drive flame-01 forge-bridge probe).
  Recommendation: (A) with a contingent (B) — symmetry fix is correct
  regardless of platform, lands a regression test, and improves
  worst-case UX. If symptom persists on flame-01 after the fix, we
  re-instrument with one less hypothesis to discriminate.
reasoning_checkpoint: |
  Two facts that surprised me on first read of the todo and which a
  fresh agent should pressure-test:
  - The Phase 04.4 closure attributed PyActionFamilyNode exposure to
    "transient state cleared by full Flame restart" — but flame-01
    has had no prior session/crash, so transience can't explain
    recurrence. The wrapper-class behaviour is a stable property
    of the (Flame version × OS × hardware) tuple, not a transient.
  - macOS arm64 (dev) vs RHEL 9 x86_64 (flame-01) is the biggest
    delta we haven't isolated. Wrapper-class identity may be
    platform-dependent — e.g. PyAction subclassing PyActionFamilyNode
    on Linux but not macOS, or vice versa.

## Evidence

- timestamp: 2026-04-28T16:10:00Z
  source: static-analysis (STEP 1 — main-context read of post-f1e8853 source)
  finding: |
    The Phase 04.4 hardening at `flame/camera_match_hook.py:1948` adds
    `callable(getattr(parent, "export_fbx", None))` to the FAST-PATH
    filter only. The FALLBACK scan at `flame/camera_match_hook.py:
    1954-1969` (`for n in flame.batch.nodes:`) has NO equivalent guard
    — it only checks `type_val == "Action"` (line 1959) and
    `hasattr(n, "nodes")` (line 1961). If any Action wrapper surfaced
    by `flame.batch.nodes` has `.export_fbx == None`, the fallback
    returns it unchecked, and the downstream `action.export_fbx(...)`
    call at `forge_flame/fbx_io.py:152` raises
    `'NoneType' object is not callable`. Verified: a project-wide grep
    for `callable(getattr` returns exactly one hit (line 1948) — the
    fix is asymmetric.
  call_path_for_camera_scope_export: |
    Right-click Camera in Action schematic
    -> get_action_custom_ui_actions (registered in 04.4-03 Wave 2)
    -> _export_camera_from_action_selection(selection)               # hook.py:2346
    -> _first_camera_in_action_selection(selection)                  # hook.py:1888
       fast path: cam.parent + filter (callable export_fbx, line 1948)
       fallback: scan flame.batch.nodes (NO callable filter, line 1954)
       returns: (action_node, cam_node)
    -> _export_camera_pipeline(action_node, cam_node, label)         # hook.py:2374
    -> fbx_io.export_action_cameras_to_fbx(action, ...)              # hook.py:2523
    -> with _selection_restored(action):
           action.selected_nodes.set_value(cameras)                  # fbx_io:151
           ok = action.export_fbx(...)                               # fbx_io:152  <-- raises here
       except Exception as e:
           dialog "Failed to write FBX: {e}"                         # hook.py:2531
  rules_out: |
    H2 (fallback returns None, caller doesn't gate). The caller DOES
    gate at hook.py:2358: `if action_node is None or cam_node is None:
    -> show "Right-click a Camera node inside an Action's schematic..."
    dialog`. The user's reported error is "Failed to write FBX:
    'NoneType' object is not callable" — different dialog, fired only
    after action_node is non-None. So action_node was NON-None but
    its `.export_fbx` was None. → the fallback returned a wrapper
    whose .export_fbx is None.
  ranking: |
    H1 (fallback returns broken proxy, unchecked) — STRONGLY SUPPORTED
       by the asymmetric-fix evidence above.
    H2 — RULED OUT by the dialog-text discrimination above.
    H3 (third bypass path) — UNLIKELY, no such path appears in source;
       both right-click handlers route through
       _first_camera_in_action_selection / _first_action_in_selection.
  why_dev_workstation_passed: |
    On dev workstation post-restart, the FAST path returned a healthy
    parent (the "transient PyActionFamilyNode" cleared by restart). The
    fallback was never exercised on dev. On flame-01 cold-install with
    no prior session, the fast path either rejects a stably-broken
    proxy (and the fallback gets exercised, returning another broken
    wrapper) OR the platform-dependent wrapper-class shape on RHEL 9
    routes through the fallback by default. Either way, the missing
    guard in the fallback is the proximate cause.

## Eliminated

- hypothesis: H2 — fallback returns None and caller doesn't gate
  reason: |
    The user's dialog text "Failed to write FBX: 'NoneType' object is
    not callable" is emitted by hook.py:2531 — that path is reached
    only when `action_node is not None`. If H2 were correct the user
    would see the "Right-click a Camera node inside an Action's
    schematic..." dialog from hook.py:2360 instead.
  ruled_out_at: 2026-04-28T16:10:00Z (STEP 1 static analysis)

## Resolution

root_cause: |
  Asymmetric Phase 04.4-07 fix. The hardening at
  flame/camera_match_hook.py:1948 added
  `callable(getattr(parent, "export_fbx", None))` to the FAST-PATH
  filter only. The flame.batch.nodes fallback scan at lines 1955-1969
  had no equivalent guard — it filtered on type-string "Action" and
  hasattr(n, "nodes") only. On the dev workstation, the broken-proxy
  state cleared on Flame restart so the fast path returned a healthy
  parent and the fallback was never exercised under broken-proxy
  conditions. On flame-01 cold-install (RHEL 9 x86_64) the broken-
  proxy shape is stable (no prior session to clear), the fast path
  correctly rejects it, the fallback runs, finds an Action wrapper
  whose .export_fbx is None, and returns it unchecked. Downstream
  `action.export_fbx(...)` at forge_flame/fbx_io.py:152 then raises
  `'NoneType' object is not callable`.

fix: |
  flame/camera_match_hook.py — add the same callable-export_fbx guard
  to the fallback scan loop. After the `hasattr(n, "nodes")` check,
  also `if not callable(getattr(n, "export_fbx", None)): continue`.
  Comment cross-references Phase 04.4-07 to make the symmetry intent
  explicit. Worst case (BOTH paths reject everything) the helper now
  returns (None, item) and the caller surfaces the clean
  "Right-click a Camera node..." dialog instead of the cryptic
  NoneType — strict UX improvement either way.

verification: |
  Static / pytest only — flame-01 evidence not yet captured.
  - tests/test_camera_match_hook.py: new test
    `test_first_camera_fallback_skips_action_with_broken_export_fbx`
    covers two cases (only-broken in batch.nodes → (None, cam);
    broken+healthy same cam by identity → returns healthy). Test
    FAILS on pre-fix HEAD, PASSES on post-fix HEAD (manually
    verified via `git stash`).
  - Full suite green: 427 passed, 2 skipped (pre-existing live-
    flame/network-gated skips).

files_changed:
  - flame/camera_match_hook.py            # symmetry fix + cross-ref comment
  - tests/test_camera_match_hook.py       # new regression test (~76 lines)

commit: 70b3b79

next_steps: |
  USER ACTION (flame-01 live verification):
  1. cd to forge-calibrator on flame-01, `git pull` to fetch 70b3b79.
  2. `bash install.sh --force` (purges sibling pycaches per c680636).
  3. Restart Flame.
  4. Open a Batch with an Action that has a Camera, double-click into
     the Action's schematic, right-click the Camera → FORGE → Camera →
     Export Camera to Blender.
  5. Three possible outcomes:
     (a) Export succeeds → fix complete, file matching todo as
         resolved + close this debug session.
     (b) Dialog says "Right-click a Camera node inside an Action's
         schematic. Perspective cameras are not supported." → fix
         IMPROVED UX but the underlying wrapper-shape problem on
         RHEL 9 is real; need a third resolution path. Re-open this
         session with `/gsd-debug continue camera-scope-nonetype-flame01`
         and pursue Path B (re-instrument).
     (c) Same cryptic "Failed to write FBX: 'NoneType' object is not
         callable" → diagnosis was wrong; re-instrument and
         re-investigate from scratch.

  CONTINGENT (if outcome b or c on flame-01):
  Re-add the lightweight diagnostic block (removed in 5926742) so
  flame-01 can capture type(action).__name__,
  type(cam.parent).__name__, callable(getattr(parent, "export_fbx",
  None)), and the fallback-scan result. Single-shot log to
  /tmp/forge_export_camera_pre_call.log. Then either add a third
  resolution path (e.g. flame.batch.get_node by name) or escalate
  to Autodesk support with the wrapper-class survey.

phase_04_4_followup: |
  This is a true regression on Phase 04.4's GAP-04.4-UAT-04 closure
  (the closure was premature). Suggest the user file this against
  v6.4 milestone or as a 04.4-08 hotfix plan after live verification
  on flame-01 succeeds — purely a planning decision; investigation
  + fix work is done.
