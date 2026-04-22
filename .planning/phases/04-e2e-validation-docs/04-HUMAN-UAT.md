---
status: partial
phase: 04-e2e-validation-docs
source: [04-VERIFICATION.md]
started: 2026-04-22T19:44:44Z
updated: 2026-04-22T19:44:44Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. Full smoke test live run on production stack
expected: Script exits 0. All 6 mechanical steps pass automatically. All 4 human-verified steps are answerable with `y` (Blender opens on baked camera with no dialogs; Send to Flame success popup appears; new camera with keyframes appears in the target Action; no orphan pgrep after Flame quit). Transcript written to `/tmp/forge-smoke-*.log`. This is the DOC-01 acceptance event.
result: [pending]

### 2. Install section walkthrough for pipeline TDs
expected: Installer emits `> forge_core + forge_flame`, `> forge-bridge`, `> Install`, `> tools/blender` section headers. No preflight failures on a correctly configured machine. After Flame restart, bridge probe `curl -s http://localhost:9999/ -o /dev/null -w "%{http_code}\n"` returns 200.
result: [pending]

### 3. Ctrl-F troubleshooting usability check
expected: Each of the 5 Symptom strings is the first Ctrl-F hit in a rendered markdown viewer. The fix copy is clear and actionable. Decide whether WR-01 (smoke-test messages reference "recipe 1"/"recipe 5" but doc has no numbered labels) needs addressing before v6.3 ships.
result: [pending]

## Summary

total: 3
passed: 0
issues: 0
pending: 3
skipped: 0
blocked: 0

## Gaps
