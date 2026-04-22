---
status: resolved
phase: 03-forge-bridge-deploy
source: [03-VERIFICATION.md]
started: 2026-04-21T22:00:00Z
updated: 2026-04-21T22:30:00Z
---

## Current Test

All resolved. Test 1 + Test 2 passed live. Test 3 deferred to Phase 4 per D-14.

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
result: passed
evidence: |
  Operator temporarily moved sibling clone (`mv ../forge-bridge ../forge-bridge.bak`) to force the curl path, then ran `FORGE_BRIDGE_REPO="" FORGE_BRIDGE_VERSION=v9.99.99 ./install.sh` on 2026-04-21.
  - curl returned "(56) The requested URL returned error: 404" as expected for the bogus tag
  - `[WARN]` paragraph emitted via single `printf ... >&2` with all required tokens:
    - reason substituted: `(sibling installer exited non-zero)` (D-10 first %s)
    - dynamic version in retry URL: `curl ... /v9.99.99/scripts/install-flame-hook.sh | bash` — confirms D-10 retry-hint uses `${FORGE_BRIDGE_VERSION}` dynamic substitution per plan-02 §interfaces, NOT literal `v1.1.0` from CONTEXT.md
    - both retry hints present: `FORGE_BRIDGE_REPO=<path>` AND the curl form
    - "VP-solve and v6.2 static round-trip still work" token preserved
    - "forge-bridge not reachable at http://127.0.0.1:9999" message preserved
  - install.sh CONTINUED past the failure to `> Install` section (Camera Match), which ran normally with the overwrite prompt
  - `echo "exit=$?"` after script returned: `exit=0` — D-11 discipline confirmed (bridge failure did not propagate)
  - Sibling clone restored via `mv ../forge-bridge.bak ../forge-bridge`

### 3. Phase 4 scope items (BRG-01/BRG-02 live) — scope-boundary deferral
expected: After a successful live install + Flame restart, verify the bridge is reachable via `curl -s http://localhost:9999/ -o /dev/null -w "%{http_code}\n"` (expected: 200). Then kill Flame and confirm no orphan `forge_bridge` / `python` process remains in `ps`. This closes BRG-01 and BRG-02 LIVE. Note: these items are explicitly Phase 4 scope per D-14 — listed here so the scope boundary is traceable.
result: deferred
evidence: |
  Deferred to Phase 4 per D-14 (scope boundary). Phase 4's E2E smoke test harness owns the live Flame-boot/Flame-quit lifecycle verification. Not a gap for Phase 3.

## Summary

total: 3
passed: 2
issues: 0
pending: 0
skipped: 0
blocked: 0
deferred: 1

## Gaps

None.
