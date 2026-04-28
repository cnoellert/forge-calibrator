---
slug: camera-scope-nonetype-flame01
status: fixed_pending_flame01_verify
created: 2026-04-28T16:00:00Z
updated: 2026-04-28T19:35:00Z
resolved_commit: 1412555
trigger: |
  Camera-scope export 'NoneType' object is not callable regression on cold-install — recurs despite Phase 04.4 fix (commits f1e8853 + c680636). See .planning/todos/pending/2026-04-27-camera-scope-export-nonetype-regression-on-cold-install.md for full diagnostic context.
goal: find_and_fix
related_todos:
  - .planning/todos/pending/2026-04-27-camera-scope-export-nonetype-regression-on-cold-install.md
related_phases:
  - 04.4 (GAP-04.4-UAT-04 — premature closure)
related_commits:
  - f1e8853   # callable(getattr(parent, "export_fbx", None)) hardening (Phase 04.4-07, fast path only)
  - c680636   # install.sh recursive __pycache__ purge across camera_match + forge_core + forge_flame
  - 5926742   # diagnostic instrumentation removal (closure commit — instrumentation no longer in tree)
  - 70b3b79   # FIX 1: mirror callable-export_fbx guard into batch.nodes fallback scan (symmetric guard)
  - 9bd5bd0   # FIX 2: 3-step resolution — direct parent → promote-by-name → batch.nodes name-match; adds diag JSON
  - bacdc2c   # FIX 3: return action.nodes' cam wrapper not selection wrapper (fixes silent empty FBX)
  - 1412555   # FIX 4: restore cam.target_mode.set_value(False) in calibrator apply (fixes silent solver corruption)
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
  to the prematurely-closed GAP-04.4-UAT-04. Cascade of 4 additional
  fixes landed across the day (portofino-driven); HEAD is 1412555.

### Reproduction (current best guess — needs flame-01 reconfirmation at HEAD 1412555)
1. Clean RHEL 9 Flame workstation, no prior forge install
2. `git clone` forge-calibrator at HEAD `1412555` or later
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
  RESOLVED (all four hypotheses confirmed and fixed). See Resolution
  for the full cascade root-cause narrative.

next_action: |
  flame-01 live verification at HEAD 1412555. See next_steps.

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
  Both facts remain true and inform why flame-01 verification still
  matters — the 3-step resolution was designed to handle wrapper-class
  shape variation across platform/context, so if flame-01 still fails
  we have the diag JSON at /tmp/forge_camera_match_diag.json to
  capture the hook-callback-context shapes.

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

- timestamp: 2026-04-28T17:00:00Z
  source: live-probe (portofino, macOS arm64, hook callback context)
  finding: |
    Portofino reproduction confirmed that even after the symmetric guard
    (70b3b79), the export returned True but the written FBX was empty:
    4435 bytes, no Model:: blocks, no NodeAttribute blocks, only the
    FBX SDK's stock 'Producer Perspective' default. Downstream error:
    "no cameras found named 'Default'". Root cause: the 3-step resolution
    in 9bd5bd0 was resolving the correct Action but returning the
    SELECTION's cam wrapper rather than the cam wrapper from
    action.nodes. Flame's action.selected_nodes.set_value([cam]) silently
    no-ops when handed a wrapper not in action.nodes — the cam selection
    is dropped before export_fbx runs. The exported FBX therefore contains
    no camera geometry matching the requested name.

- timestamp: 2026-04-28T17:30:00Z
  source: live-probe (portofino, macOS arm64, calibrator apply flow)
  finding: |
    After the export-side fixes landed, a second regression surface
    appeared in the calibrator apply flow: the solved camera was applied
    with wrong values. Probe confirmed: cam.target_mode is a real
    PyAttribute (get_value() = False). Commit 19e6d17 (04.2-02) had
    deleted the `cam.target_mode.set_value(False)` call after a probe
    that incorrectly reported target_mode as None — that probe was run
    in a context where the attribute was not visible. Without the
    explicit Free-rig forcing, Flame's creation path now produces a
    Target-rig camera; position/rotation/fov are then interpreted
    relative to an aim target rather than as absolute world transforms,
    silently corrupting solver output. Restoring the call (1412555)
    with a defensive try/except for version-safety resolves this.

- timestamp: 2026-04-28T19:10:00Z
  source: live-probe (portofino, macOS arm64, mid-session degraded)
  finding: |
    Mid-session retest at HEAD 1412555 reproduced the user-visible
    failure with a clean dialog ("Right-click a Camera node inside an
    Action's schematic..."). The diag JSON written by Step 3's failure
    path showed three identical PyActionFamilyNode wrappers (id
    16533679328) returned by cam.parent, flame.batch.get_node("action1"),
    AND the flame.batch.nodes scan — all with `.export_fbx == None`.
    Initially read this as proof the LAYER 2 hypothesis was wrong
    (i.e. promote-by-name doesn't actually promote the wrapper class).
    SELF-CORRECTION (see next evidence entry): this snapshot was a
    degraded session-state artifact, not a durable invariant.
  diag_json_excerpt: |
    selection: PyCoNode "Default" (Camera)
    parent: PyActionFamilyNode "action1", id 16533679328, export_fbx is None
    promote_by_name_attempt: PyActionFamilyNode "action1", id 16533679328 (same object)
    batch_nodes scan: PyActionFamilyNode "action1", id 16533679328 (same object)

- timestamp: 2026-04-28T19:35:00Z
  source: live-test (portofino, macOS arm64, fresh Flame restart)
  finding: |
    After full Flame restart (the prior session had crashed during a
    Camera-scope export attempt), the SAME workflow on a fresh session
    SUCCEEDED — Camera-scope export wrote a valid FBX, Blender launched
    cleanly. Proves the cascade fixes are correct in a healthy session.
    The mid-session degraded readings (prior evidence entry) were
    session-state corruption, not a durable wrapper-class quirk. Phase
    04.4's "transient state cleared by full Flame restart" hypothesis
    holds; the recurrence on flame-01 cold-install was a different
    instance of the same transient-state class (no prior session, but
    likely the install.sh deploy + Flame's first-load state on RHEL 9
    presented the same degraded wrapper shape).
  pattern: |
    PyActionFamilyNode-with-None-export_fbx is a degraded wrapper that
    appears in hook callback context under at least two conditions:
    (a) a Flame session has accumulated state corruption (often after a
        crash or prolonged calibrator iteration); restart cures it.
    (b) a fresh Flame session in a particular environment shape (e.g.
        flame-01 RHEL 9 cold install with no prior session) — root
        cause not yet isolated to a clean reproducer.
    The cascade's 3-step resolution is correct but cannot rescue case
    (a) once Flame has degraded; the only cure for (a) is restart. For
    (b) we need flame-01 reverification at HEAD 1412555.
  see_also: memory/flame_camera_scope_session_state_decay.md

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
  MULTI-LAYER cascade rooted in wrapper-class identity instability
  across hook-callback context and bridge-probe context on Flame 2026.2.1.
  Four distinct failure layers were found and fixed in order:

  LAYER 1 (70b3b79 — symmetric callable guard):
  Phase 04.4-07 hardened the fast path in `_first_camera_in_action_selection`
  with `callable(getattr(parent, "export_fbx", None))` but left the
  `flame.batch.nodes` fallback scan unguarded. On flame-01 cold-install
  (RHEL 9 x86_64) the broken-proxy shape is stable; the fast path rejects
  it and the fallback returns an unchecked Action wrapper with
  `.export_fbx == None`. Downstream `action.export_fbx(...)` at
  forge_flame/fbx_io.py:152 raises 'NoneType' object is not callable.
  Fix: mirror the callable guard into the fallback scan.

  LAYER 2 (9bd5bd0 — 3-step resolution with get_node-by-name promotion):
  Even with the symmetric guard, bridge probes saw a healthy state but
  the hook callback context continued to fail. Bridge runs off-main-thread
  and cannot observe the hook callback context. The wrapper instance
  returned by cam.parent in the hook callback is a degraded base wrapper
  (PyActionFamilyNode without .export_fbx); flame.batch.get_node(parent_name)
  returns the specialized PyActionNode wrapper that bridge sees as healthy.
  The 2-step fallback (direct parent → batch.nodes scan) was insufficient
  because wrapper identity is NOT preserved between the hook selection and
  action.nodes — `inode is item` returns False for the same logical camera.
  Fix: 3-step resolution: (1) direct parent + callable filter, (2) promote
  by name via flame.batch.get_node, (3) batch.nodes scan with identity-then-
  name match using parent_name for disambiguation. On total failure, write
  /tmp/forge_camera_match_diag.json capturing hook-context wrapper-class shapes.

  LAYER 3 (bacdc2c — return action.nodes' cam wrapper not selection wrapper):
  Steps 2 and 3 resolved the correct Action but returned the SELECTION's cam
  wrapper (a different Python object from action.nodes' copy). Flame's
  action.selected_nodes.set_value([cam]) silently no-ops when handed a wrapper
  not in action.nodes — the camera selection is dropped, export_fbx runs with
  no camera selection, and the written FBX is empty (4435 bytes, no Model:: or
  NodeAttribute blocks, only the stock 'Producer Perspective' default). The
  "no cameras found named 'Default'" downstream error was the diagnostic clue.
  Fix: extract `_find_cam_in_action_nodes` helper; Steps 2 and 3 now look up
  the cam by name inside action.nodes after resolving the Action.

  LAYER 4 (1412555 — restore cam.target_mode.set_value(False) in calibrator apply):
  A separate silent corruption in the calibrator apply flow. Commit 19e6d17
  (04.2-02) deleted `cam.target_mode.set_value(False)` after a probe incorrectly
  reported target_mode as None (probe ran in a context where the attribute was
  not visible). Live re-probe 2026-04-28 on Flame 2026.2.1 confirmed cam.target_mode
  is a real PyAttribute (get_value() = False). Without the explicit Free-rig
  forcing, Flame's creation path produces a Target-rig camera; position/rotation/fov
  are interpreted relative to an aim target, silently corrupting solver output.
  Fix: restore the call with a defensive try/except for version-safety.

fix: |
  Four commits, all on flame/camera_match_hook.py and tests/test_camera_match_hook.py:

  70b3b79 — Symmetric callable guard: after `hasattr(n, "nodes")` in the
    fallback scan, also `if not callable(getattr(n, "export_fbx", None)): continue`.
    Worst case (both paths reject everything) → (None, cam) → caller shows the
    clean "Right-click a Camera node..." dialog.

  9bd5bd0 — 3-step resolution in `_first_camera_in_action_selection`:
    Step 1: cam.parent direct (existing fast path, callable-export_fbx filter).
    Step 2: promote by name — flame.batch.get_node(parent_name) — returns
      the specialized PyActionNode wrapper even when bridge can't observe the
      hook callback context.
    Step 3: flame.batch.nodes scan with identity-then-name match; parent_name
      disambiguates same-named cams across Actions.
    On total failure: write /tmp/forge_camera_match_diag.json (overridable via
    FORGE_CAMERA_MATCH_DIAG_PATH) capturing hook-context wrapper-class shapes.

  bacdc2c — `_find_cam_in_action_nodes(action, cam_name)` helper: after Steps 2/3
    resolve the Action, look up the cam by name inside action.nodes and return
    THAT wrapper. Step 1 unchanged (cam.parent → parent.nodes wrapper identity
    holds when parent is healthy, which is the Step 1 precondition).

  1412555 — Restore `cam.target_mode.set_value(False)` in calibrator apply flow,
    wrapped in try/except for version-safety. Forces Free-rig unconditionally so
    position/rotation/fov are absolute world transforms as the solver expects.

verification: |
  All verification through portofino (macOS arm64, Flame 2026.2.1):
  - 70b3b79: static + pytest only. Regression test
    `test_first_camera_fallback_skips_action_with_broken_export_fbx`
    FAILS pre-fix, PASSES post-fix.
  - 9bd5bd0: live portofino probe confirmed the 3-step resolution
    surfaces the healthy specialized PyActionNode wrapper from the
    hook callback context. 3 new regression tests: Step 2 promotion,
    Step 3 name-match, Step 3 parent_name disambiguation. Suite green
    (430 passed, 2 skipped).
  - bacdc2c: live portofino test confirmed action.export_fbx returns
    True AND FBX contains the expected Model:: + NodeAttribute blocks.
    Tests updated to assert action.nodes wrapper return. Suite green
    (430 passed, 2 skipped).
  - 1412555: live portofino re-probe confirmed cam.target_mode is a
    real PyAttribute. Calibrator apply flow produces Free-rig camera
    with correct solver values. Suite green (430 passed, 2 skipped).
  - END-TO-END (2026-04-28T19:35Z): live Camera-scope export on
    portofino fresh Flame session at HEAD 1412555 succeeded — wrote a
    valid FBX, Blender launched cleanly. This is the post-cascade
    end-to-end verification that was missing from the doc reconciliation
    in fc9a7df.

  Mid-session caveat: a degraded-wrapper failure DID reproduce on
  portofino during the same testing session (after several calibrator
  iterations + a SIGSEGV). That failure showed PyActionFamilyNode for
  cam.parent + flame.batch.get_node + flame.batch.nodes scan (same id,
  no callable export_fbx). Clean Flame restart cured it. This pattern
  is now captured in memory/flame_camera_scope_session_state_decay.md.

  flame-01 (RHEL 9 x86_64) live verification NOT YET RUN at HEAD 1412555.

files_changed:
  - flame/camera_match_hook.py     # all four commits; primary file across the cascade
  - tests/test_camera_match_hook.py  # 70b3b79 (+76 lines), 9bd5bd0 (+147 lines), bacdc2c (tests updated)

commit: 1412555

next_steps: |
  flame-01 (RHEL 9 x86_64) live verification — the only remaining
  unknown. Portofino end-to-end is green at HEAD 1412555.

  USER ACTION on flame-01:
  1. cd to forge-calibrator on flame-01, `git pull` to fetch HEAD
     (1412555 + the doc commits — current HEAD is fc9a7df or later).
  2. `bash install.sh --force` (purges sibling pycaches per c680636).
  3. Restart Flame fully (NOT a session reload — hook callbacks are
     captured at registration time).
  4. Open a Batch with an Action that has a Camera, double-click into
     the Action's schematic, right-click the Camera → FORGE → Camera →
     Export Camera to Blender.
  5. Two possible outcomes:
     (a) Export succeeds → fix complete on flame-01. Also do one
         calibrator apply pass to verify Free-rig (the LAYER 4 fix).
         Then close this debug session and the matching todo.
     (b) Any failure dialog → check /tmp/forge_camera_match_diag.json
         on flame-01 for hook-context wrapper-class shapes. The diag
         will discriminate between session-state decay (clean Flame
         restart cures it — see memory/flame_camera_scope_session_state_decay.md)
         and a durable wrapper-class quirk specific to RHEL 9 cold
         install. Re-open this session with
         `/gsd-debug continue camera-scope-nonetype-flame01` and
         surface the diag JSON as new evidence.

  Note on session-state decay (added 2026-04-28 from portofino
  retest): if the failure repros mid-session on a workstation that
  previously worked, try a clean Flame restart FIRST before assuming
  a code bug. Mid-session degradation can present the same diag-JSON
  shape (PyActionFamilyNode everywhere, same wrapper id, no callable
  export_fbx) as the flame-01 cold-install failure but is not a code
  defect.

phase_04_4_followup: |
  This is a true regression on Phase 04.4's GAP-04.4-UAT-04 closure
  (the closure was premature). The full 4-commit cascade (70b3b79 through
  1412555) constitutes the complete fix. Suggest filing this as a 04.4-08
  hotfix after live verification on flame-01 succeeds — purely a planning
  decision; all investigation and fix work is done.
