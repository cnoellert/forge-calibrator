---
phase: 04-e2e-validation-docs
plan: 02
subsystem: validation
tags: [validation, smoke-test, shell, v6.3, human-uat-folded, DOC-01]
completed: "2026-04-22"
duration_minutes: 8

dependency_graph:
  requires: []
  provides:
    - tools/smoke-test/seamless-bridge-smoke.sh (hybrid E2E smoke test for v6.3 seamless bridge)
  affects:
    - DOC-01 requirement (artifact in place; runtime closure pending first green live run)

tech_stack:
  added: []
  patterns:
    - Bash strict mode (set -euo pipefail) with TTY-gated ANSI colour helpers
    - Transcript tee via exec > >(tee -a "$LOG") 2>&1
    - HUMAN_FAIL + FAILED_STEPS accumulator pattern for deferred y/n failures
    - ask_human() helper encapsulating read -r -p + case statement

key_files:
  created:
    - tools/smoke-test/seamless-bridge-smoke.sh

decisions:
  - "Placed at tools/smoke-test/ per D-02 Claude's Discretion (discoverable sibling to tools/blender/)"
  - "set -euo pipefail on line 2 (immediately after shebang) to satisfy head -5 verification"
  - "Step 5 curl probe uses verbatim install.sh:519-522 idiom for consistency"
  - "Step 4 D-10 path: if forge-bridge install skipped, syntax check is warn-and-continue not a hard fail"
---

# Phase 04 Plan 02: Seamless-bridge smoke test Summary

Hybrid [mech]+[human] E2E smoke test script (221 lines, executable, `bash -n` clean) delivered at `tools/smoke-test/seamless-bridge-smoke.sh`, providing the authoritative exit-0 gate for cutting v6.3.

## What Was Built

`tools/smoke-test/seamless-bridge-smoke.sh` — a single bash script that:

- Runs mechanized preflight checks (git status, install.sh dry-run + live, forge_bridge.py ast.parse, curl 200, pgrep, pytest)
- Prompts the operator inline for the four Flame/Blender interactive steps (export, send, verify, quit)
- Records the full run transcript to `/tmp/forge-smoke-YYYYMMDD-HHMMSS.log` with git rev + timestamp in the header
- Exits 0 only when all 10 steps pass; exits 1 with FAILED_STEPS list + troubleshooting pointer on any failure
- Folds in Phase 3 HUMAN-UAT Test 3 (bridge reachable at step 5; no orphan at step 9) per D-15

## Artifact Evidence

| Check | Result |
|-------|--------|
| `test -f tools/smoke-test/seamless-bridge-smoke.sh` | PASS |
| `test -x tools/smoke-test/seamless-bridge-smoke.sh` | PASS |
| `bash -n tools/smoke-test/seamless-bridge-smoke.sh` | PASS |
| Line count | 221 (within 180-280 target) |

## Step Coverage Grep Sweep (11 `step "..."` headers)

| Step | Header | Result |
|------|--------|--------|
| 1 | `step "Working-tree clean"` | PASS |
| 2 | `step "install.sh dry-run"` | PASS |
| 3 | `step "install.sh live"` | PASS |
| 4 | `step "forge_bridge.py sanity"` | PASS |
| 5 | `step "Bridge reachable after Flame boot"` | PASS |
| 6 | `step "Export Camera to Blender"` | PASS |
| 7 | `step "Send to Flame"` | PASS |
| 8 | `step "Camera appears in target Action"` | PASS |
| 9 | `step "No orphan bridge after Flame quit"` | PASS |
| 10 | `step "pytest"` | PASS |
| Done | `step "Done"` | PASS |

## Idempotence Audit (D-04) — 4 Negative-grep Assertions

| Pattern | Result |
|---------|--------|
| `rm -rf` absent | PASS |
| `install.sh --force` absent | PASS |
| `sudo ` absent | PASS |
| `> /opt/Autodesk/` direct-write redirect absent | PASS |

## HUMAN-UAT Test 3 Fold-in Evidence (D-15)

| Fold | Pattern | Result |
|------|---------|--------|
| Step 5 — bridge-reachable-after-boot | `curl -s http://localhost:9999/` | PASS |
| Step 9 — no-orphan-after-quit | `pgrep -f forge_bridge.py` | PASS |

## Cross-plan Invariant Status

| Invariant | Status |
|-----------|--------|
| Smoke test references `docs/seamless-bridge.md#troubleshooting` (D-06 pointer) | CONFIRMED |
| README.md references `tools/smoke-test/seamless-bridge-smoke.sh` | DEFERRED — README.md not yet written; Plan 01 owns this file. Check after Plan 01 merges. |
| `docs/seamless-bridge.md` has `## Troubleshooting` H2 | DEFERRED — docs/seamless-bridge.md not yet written; Plan 01 owns this file. Check after Plan 01 merges. |

## DOC-01 Delivery Status

**Artifact in place.** `tools/smoke-test/seamless-bridge-smoke.sh` is committed and passes all static checks.

Runtime closure of DOC-01 is a RUNTIME event: DOC-01 is closed when a TD/artist runs the script against a live Flame 2026.2.1 + Blender 4.5+ + forge-bridge stack and the script exits 0. That first green live run should be recorded in the Phase 4 VERIFICATION.md as the actual DOC-01 acceptance evidence.

Pointer: `forge-calibrator/tools/smoke-test/seamless-bridge-smoke.sh`

## Deviations from Plan

None — plan executed exactly as written. The complete script was written in a single pass covering both Task 1 (preamble + helpers) and Task 2 (10 steps + final exit guard) simultaneously, with the preamble framework naturally flowing into the steps without restructuring.

## Self-Check: PASSED

- `tools/smoke-test/seamless-bridge-smoke.sh` exists and is executable: CONFIRMED
- Commit `e62fe32` exists: CONFIRMED
- `bash -n` syntax check: CONFIRMED
- All 18 grep/negative-grep assertions: CONFIRMED
