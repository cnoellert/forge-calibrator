---
status: partial
phase: 03-forge-bridge-deploy
source: [03-VERIFICATION.md]
started: 2026-04-21T22:00:00Z
updated: 2026-04-21T22:15:00Z
---

## Current Test

Test 2 (D-11 failure-path) pending operator decision.

## Tests

### 1. Live non-dry-run install confirmation
expected: Run `./install.sh` (or `./install.sh --force` if a prior hook exists). The `> forge-bridge` section emits `✓ [forge-bridge] installed at /opt/Autodesk/shared/python/forge_bridge/scripts/forge_bridge.py` and `✓ [forge-bridge] next Flame boot will spawn the bridge on http://127.0.0.1:9999 ...`. Follow-up check: `test -f /opt/Autodesk/shared/python/forge_bridge/scripts/forge_bridge.py && python3 -c 'import ast; ast.parse(open("/opt/Autodesk/shared/python/forge_bridge/scripts/forge_bridge.py").read())' && echo OK` returns 0.
result: passed
evidence: |
  Operator ran `./install.sh --force` from /Users/cnoellert/Documents/GitHub/forge-calibrator on 2026-04-21.
  - `> forge-bridge` section ran before `> Install` (D-07 confirmed live)
  - Local clone detected at ../forge-bridge, version v1.3.0-3-gc9910b7 (FORGE_BRIDGE_SOURCE_KIND=local → argv-array invocation, WR-02 fix exercised)
  - `_bridge_rm_force` emitted "✓ [forge-bridge] --force: removed existing ..." under real --force (WR-03 guard correctly only suppresses under --dry-run)
  - Hook landed: /opt/Autodesk/shared/python/forge_bridge/scripts/forge_bridge.py, 22741 bytes, cnoellert:wheel
  - D-15 ast.parse check: OK
  - Both success lines present verbatim, including the "(verification deferred to Phase 4 E2E per D-14)" scope-boundary callout
  - Camera Match `> Install` ran after bridge step, script exited 0

### 2. D-11 exit-code discipline under real failure
expected: Simulate a bridge-install failure — e.g., `FORGE_BRIDGE_VERSION=v9.99.99 ./install.sh` to force a curl 404, OR unset `FORGE_BRIDGE_REPO` + offline the machine. install.sh emits the D-10 warning as a single unbroken paragraph on stderr, CONTINUES to the `> Install` Camera Match section, and the overall script exits 0 (camera-match succeeded, only bridge failed per D-11). No orphan exit. No aborted install.
result: [pending]

### 3. Phase 4 scope items (BRG-01/BRG-02 live) — scope-boundary deferral
expected: After a successful live install + Flame restart, verify the bridge is reachable via `curl -s http://localhost:9999/ -o /dev/null -w "%{http_code}\n"` (expected: 200). Then kill Flame and confirm no orphan `forge_bridge` / `python` process remains in `ps`. This closes BRG-01 and BRG-02 LIVE. Note: these items are explicitly Phase 4 scope per D-14 — listed here so the scope boundary is traceable.
result: [pending]

## Summary

total: 3
passed: 1
issues: 0
pending: 2
skipped: 0
blocked: 0

## Gaps
