---
created: 2026-04-27T20:00:00Z
title: Camera-scope export NoneType regression recurs on cold-install (deeper than Phase 04.4 fix)
area: hook
files:
  - flame/camera_match_hook.py:1881  # _first_camera_in_action_selection
  - flame/camera_match_hook.py:2295  # _export_camera_to_blender (Action-scope)
  - flame/camera_match_hook.py:2331  # _export_camera_from_action_selection (Camera-scope)
  - forge_flame/fbx_io.py:152        # action.export_fbx call site
---

## Problem

Right-click on a Camera node inside an Action's schematic → FORGE → Camera →
Export Camera to Blender → Tier-1 dialog **"Failed to write FBX: 'NoneType'
object is not callable"**. Same user-visible symptom as GAP-04.4-UAT-04
which we thought was closed in Phase 04.4 by:

- Hardening the fast-path filter in `_first_camera_in_action_selection`
  to require `callable(getattr(parent, "export_fbx", None))` (commit
  `f1e8853`).
- Adding the recursive `__pycache__` purge to `install.sh` across
  `camera_match`, `forge_core`, `forge_flame` (commit `c680636`).

The fix was live-verified on the developer's primary Flame workstation
after a clean Flame restart. **However, the regression recurs on
flame-01 cold install** (clean RHEL 9 host, no prior forge install,
forge env created from `forge-env.yml`, `bash install.sh` ran clean,
forge-bridge fetched v1.3.0 via curl-fallback, all sibling pycaches
purged). User reports "same as we've been battling" — symptom is
identical.

This rules out the leading hypothesis that the `PyActionFamilyNode`
exposure was a transient state from earlier crashes. It reproduces on
a Flame instance that has had no crashes, no probes, no sessions.

## Diagnosis (current understanding)

Phase 04.4 root-caused the immediate failure to a `cam.parent` returning
a `PyActionFamilyNode` base-class wrapper whose `.export_fbx` is None.
The current fast-path filter rejects that proxy correctly — so the
fallback `flame.batch.nodes` scan must also be returning a broken
wrapper, OR the fallback never finds the cam, OR there's a third path
that bypasses both.

**What we don't know yet (because the diagnostic instrumentation was
removed in the closure commit `5926742`):**

- What `type(action).__name__` is at the moment of the failed call on
  flame-01.
- Whether `flame.batch.nodes` enumeration returns broken proxies on
  flame-01 the same way it did on the dev workstation.
- Whether the fast-path callable check is even firing — maybe the cold
  install loaded a different code path.

**What we do know:**

- The hook source on flame-01 contains the post-fix code (verified by
  `git log --oneline` on the cloned repo: HEAD is `5b47653`, contains
  `f1e8853`).
- `install.sh` deployed the new code to
  `/opt/Autodesk/shared/python/camera_match/camera_match.py` (verified
  by file size 121,561 bytes — matches dev workstation).
- All sibling pycaches purged (cleared at end of install.sh).
- forge-bridge v1.3.0 deployed and started (port 9999 LISTEN on
  127.0.0.1).

## Reproduction (current best guess)

1. Clean RHEL 9 Flame workstation, no prior forge install
2. `git clone` forge-calibrator at HEAD `5b47653` or later
3. `conda env create -f forge-env.yml`
4. `bash install.sh --force`
5. Launch Flame
6. Open a Batch with at least one Action containing a Camera node
7. Double-click into the Action's schematic editor
8. Right-click the Camera node → FORGE → Camera → Export Camera to Blender
9. Observe the NoneType dialog

Action-scope right-click (right-click the Action in Batch, not a Camera
inside its schematic) is currently UNTESTED on flame-01 and may or may
not also fail.

## Next steps

1. **Re-instrument**: re-add the diagnostic block from session
   2026-04-27 (see git log for `forge_export_camera_pre_call.log`
   format) to capture context at the moment of failure on flame-01.
   Compare with the dev-workstation failure shape captured 2026-04-27.
2. **Probe via bridge** while flame-01 is in the failed state — capture
   `type(cam.parent).__name__`, `flame.batch.get_node(action_name)`
   wrapper class, and `flame.batch.nodes` action survey from the
   bridge context (which earlier evidence suggests returns DIFFERENT
   wrapper classes than the hook callback context).
3. **Rule out hardware/OS axis**: macOS arm64 (dev workstation) vs
   RHEL 9 x86_64 (flame-01) is the biggest delta we haven't tested
   under controlled conditions. The wrapper-class behaviour might be
   platform-dependent.

## Scope

This is a real regression, not a doc gap. **Phase 04.4's GAP-04.4-UAT-04
closure was premature** — the fix works on the dev workstation but is
demonstrably incomplete. Reopening 04.4 vs. spinning a 04.4-08 hotfix
plan vs. v6.4 milestone item is a planning-cycle decision; the
investigation work is the same regardless of where it lives.
