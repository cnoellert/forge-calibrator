---
status: partial
phase: 03-forge-bridge-deploy
source: [03-VERIFICATION.md]
started: 2026-04-21T22:00:00Z
updated: 2026-04-21T22:00:00Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. Live non-dry-run install confirmation
expected: Run `./install.sh` (or `./install.sh --force` if a prior hook exists). The `> forge-bridge` section emits `✓ [forge-bridge] installed at /opt/Autodesk/shared/python/forge_bridge/scripts/forge_bridge.py` and `✓ [forge-bridge] next Flame boot will spawn the bridge on http://127.0.0.1:9999 ...`. Follow-up check: `test -f /opt/Autodesk/shared/python/forge_bridge/scripts/forge_bridge.py && python3 -c 'import ast; ast.parse(open("/opt/Autodesk/shared/python/forge_bridge/scripts/forge_bridge.py").read())' && echo OK` returns 0.
result: [pending]

### 2. D-11 exit-code discipline under real failure
expected: Simulate a bridge-install failure — e.g., `FORGE_BRIDGE_VERSION=v9.99.99 ./install.sh` to force a curl 404, OR unset `FORGE_BRIDGE_REPO` + offline the machine. install.sh emits the D-10 warning as a single unbroken paragraph on stderr, CONTINUES to the `> Install` Camera Match section, and the overall script exits 0 (camera-match succeeded, only bridge failed per D-11). No orphan exit. No aborted install.
result: [pending]

### 3. Phase 4 scope items (BRG-01/BRG-02 live) — scope-boundary deferral
expected: After a successful live install + Flame restart, verify the bridge is reachable via `curl -s http://localhost:9999/ -o /dev/null -w "%{http_code}\n"` (expected: 200). Then kill Flame and confirm no orphan `forge_bridge` / `python` process remains in `ps`. This closes BRG-01 and BRG-02 LIVE. Note: these items are explicitly Phase 4 scope per D-14 — listed here so the scope boundary is traceable.
result: [pending]

## Summary

total: 3
passed: 0
issues: 0
pending: 3
skipped: 0
blocked: 0

## Gaps
