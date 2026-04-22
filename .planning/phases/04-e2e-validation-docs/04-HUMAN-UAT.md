---
status: partial
phase: 04-e2e-validation-docs
source: [04-VERIFICATION.md]
started: 2026-04-22T19:44:44Z
updated: 2026-04-22T20:15:00Z
---

## Current Test

[awaiting Phase 4.1 resolution of empty-camera bake UX before re-attempting Test 1]

## Tests

### 1. Full smoke test live run on production stack
expected: Script exits 0. All 6 mechanical steps pass automatically. All 4 human-verified steps answerable with `y`. Transcript at `/tmp/forge-smoke-*.log`. DOC-01 acceptance event.
result: blocked
notes: |
  Ran on Portofino (macOS, bash 3.2). Step 1 initially failed on an untracked
  sibling phase dir (`.planning/phases/04.1-*/`); fixed in `1813e18` (broadened
  the filter to exclude all `.planning/` metadata, committed `.gitkeep` for
  04.1). Re-ran: steps 1–5 expected to pass. Step 6 (Export Camera to Blender
  from a fresh Camera Match solve) failed with:

    Blender bake failed (exit 1):
    /bin/sh: nvidia-smi: command not found          [benign macOS noise]
    /var/folders/.../forge_bake_*/baked.json: no frames in JSON

  Root cause: Camera Match produces a static single-frame camera; the Action
  has no keyframes. `forge_flame/camera_io.py` writes `"frames": []`;
  `tools/blender/bake_camera.py:215` raises SystemExit. This is Phase 4.1
  polish item #2 ("empty-camera Flame→Blender bake UX") — a pre-existing
  Phase 1/2 bug surfaced correctly by the Phase 4 smoke test doing its job.

  DOC-01 runtime closure is DEFERRED to after Phase 4.1 Plan 4.1-01 (empty-
  camera bake UX fix) lands. Phase 4 ships the correct artifacts; DOC-01
  re-verification will re-run this smoke test.

### 2. Install section walkthrough for pipeline TDs
expected: Installer emits `> forge_core + forge_flame`, `> forge-bridge`, `> Install`, `> tools/blender` section headers. No preflight failures on a correctly configured machine. After Flame restart, bridge probe `curl -s http://localhost:9999/ -o /dev/null -w "%{http_code}\n"` returns 200.
result: pending
notes: Independent of Test 1's blocker. Can be exercised once a TD is ready to walk through it.

### 3. Ctrl-F troubleshooting usability check
expected: Each of the 5 Symptom strings is the first Ctrl-F hit in a rendered markdown viewer. The fix copy is clear and actionable. Decide whether WR-01 needs addressing before v6.3 ships.
result: pending
notes: Also independent. Reviewer judgment call on WR-01.

## Summary

total: 3
passed: 0
issues: 1
pending: 2
skipped: 0
blocked: 1

## Gaps

- **Gap-04-UAT-01:** Test 1 blocked by Phase 4.1 polish item #2 (empty-camera Flame→Blender bake UX). The smoke test artifact is correct; the product bug it exposed lives in `tools/blender/bake_camera.py` (`no frames in JSON` exit) and `forge_flame/camera_io.py` (static Action → empty `frames[]`). Route to `/gsd-plan-phase 4.1`; re-run Test 1 after 4.1-01 lands.
