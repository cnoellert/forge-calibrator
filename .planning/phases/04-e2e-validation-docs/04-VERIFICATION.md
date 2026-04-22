---
phase: 04-e2e-validation-docs
verified: 2026-04-22T19:44:44Z
status: human_needed
score: 9/11
overrides_applied: 0
re_verification: false
human_verification:
  - test: "Run tools/smoke-test/seamless-bridge-smoke.sh against a live Flame 2026.2.1 + Blender 4.5+ workstation"
    expected: "Script exits 0 with all 10 steps green, including the 4 human-verified steps answered y — confirms the complete right-click→edit→send loop works without visiting Flame's batch menu for the return trip"
    why_human: "Requires a live Flame session, a Blender installation with the forge_sender addon installed, and forge-bridge running. Cannot be exercised in static verification."
  - test: "Open docs/seamless-bridge.md and follow the Install section as a first-time pipeline TD (no prior knowledge)"
    expected: "All four deploy targets appear in install.sh output with no errors; the bridge probe returns HTTP 200; the Camera Match hook loads on Flame restart"
    why_human: "Requires a live Flame + install.sh run to confirm the section accurately guides a TD through preflight, deployment, and verification."
  - test: "Ctrl-F search for the verbatim text of each of the 5 Symptom headings in docs/seamless-bridge.md using a rendered markdown viewer (GitHub, VS Code preview, or browser)"
    expected: "Each Symptom heading is the first search hit — text matches exactly what Blender/install.sh emits at runtime, enabling Ctrl-F from the error popup to the fix in one jump"
    why_human: "Grep anchors confirm literal string presence (automated checks passed). A human reviewer must confirm the rendered headings are readable and the fix copy is actionable for an artist who has just seen the error in production."
---

# Phase 4: E2E Validation + Docs — Verification Report

**Phase Goal:** The complete right-click→edit→send loop is validated on the production stack, and users have documentation covering what changed, how to install, and how to troubleshoot
**Verified:** 2026-04-22T19:44:44Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | A new user reading README.md understands what forge-calibrator does, what changed in v6.3, and how to install it in under 60 seconds | VERIFIED | README.md exists (59 lines), H1 + 7 H2 sections in CONTEXT D-08 order, core value sentence verbatim, 3 What's-new bullets, Install summary, all pointers present |
| 2 | An artist who sees a Tier 1/2/3 error popup can Ctrl-F the verbatim error text and land on the matching troubleshooting recipe in docs/seamless-bridge.md | VERIFIED | All 4 grep-anchor directions pass: source files contain the verbatim strings; doc Symptom headings reproduce them exactly. Recipe 1+5 share the `forge-bridge not reachable` anchor; Recipe 2 uses `active camera is missing`; Recipe 3 uses `Send to Flame failed:`; Recipe 4 uses `forge-bridge install skipped` |
| 3 | A pipeline TD reading docs/seamless-bridge.md#install can deploy the hook + bridge + Blender addon without consulting any other doc | VERIFIED (artifact) / HUMAN NEEDED (runtime) | `### For pipeline TDs` section present with preflight list, four deploy targets named (`> forge_core + forge_flame`, `> forge-bridge`, `> Install`, `> tools/blender`), FORGE_BRIDGE_REPO/VERSION env vars documented, idempotence noted. Runtime confirmation requires live install run — routed to human verification |
| 4 | Every troubleshooting recipe Symptom heading grep-matches the verbatim literal in its source file (4 grep checks pass; recipe 5 shares recipe 1's anchor) | VERIFIED | All 8 bidirectional grep-F checks pass. Recipe 5 correctly shares the recipe 1 anchor text and adds `lsof -i :9999` diagnostic |
| 5 | README.md links to PASSOFF.md for v4→v6.2 history and to docs/seamless-bridge.md for install/troubleshooting deep-dives — no duplication | VERIFIED | `PASSOFF.md` relative link present; `docs/seamless-bridge.md` linked from What's-new bullets, Install section, Validation section, and Troubleshooting section; `docs/seamless-bridge.md` footer links back to README via `../README.md`; no content duplication between the two files |
| 6 | Running `./tools/smoke-test/seamless-bridge-smoke.sh` exits 0 if and only if all 10 steps pass | VERIFIED (artifact) / HUMAN NEEDED (runtime) | Script exists, is executable (+x), passes `bash -n` (221 lines). Final guard: `if (( HUMAN_FAIL )); then … exit 1; fi; exit 0` — exit 0 is only reachable when HUMAN_FAIL=0 and no mech step called `exit 1` |
| 7 | On any [mech] failure the script exits non-zero with the failure line echoed | VERIFIED | All 5 mech steps use `if ! <command>; then err "…"; exit 1; fi` pattern. Step 5 (curl non-200) and step 9 (pgrep hit) set HUMAN_FAIL=1 and append to FAILED_STEPS, causing exit 1 at the final guard |
| 8 | On any [human] step answered `n`, the script exits non-zero with step description + troubleshooting pointer | VERIFIED | `ask_human()` on non-y: `err "$desc — see docs/seamless-bridge.md#troubleshooting"`, `FAILED_STEPS+=("$desc")`, `HUMAN_FAIL=1`. Final guard emits `report to the troubleshooting section of docs/seamless-bridge.md` verbatim (D-06 requirement) |
| 9 | Full run transcript lands at `/tmp/forge-smoke-YYYYMMDD-HHMMSS.log` with git rev + timestamp in header | VERIFIED | `LOG="/tmp/forge-smoke-$(date +%Y%m%d-%H%M%S).log"` + `exec > >(tee -a "$LOG") 2>&1`; header block prints `git rev-parse HEAD` and `git describe --tags` with `\|\| echo unknown` fallback |
| 10 | Phase 3 HUMAN-UAT Test 3 is folded in: step 5 probes bridge-reachable-after-boot, step 9 confirms no-orphan-after-quit | VERIFIED | Step 5 uses verbatim `curl -s http://localhost:9999/ -o /dev/null -w "%{http_code}\n"` (install.sh:519-522 idiom); step 9 uses `pgrep -f forge_bridge.py \|\| true`; both are `[human + mech]` hybrid steps per D-15 |
| 11 | Script is idempotent and non-destructive — safe to re-run on an already-installed workstation without --force | VERIFIED | Negative greps pass: no `rm -rf`, no `install.sh --force`, no `sudo `, no direct `> /opt/Autodesk/` write redirects. Step 3 calls `./install.sh` (idempotent by design); all other mech steps are read-only |

**Score:** 9/11 truths fully verified programmatically; 2 routed to human verification (truths 6 and partial-3 — runtime closure of the smoke test loop)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `README.md` | Repo-root overview + v6.3 what's new + install summary + validation pointer + history pointer + troubleshooting link | VERIFIED | 59 lines (target: 40-80). H1 `# forge-calibrator`. All 7 H2 sections in D-08 order. Core value verbatim. No github.com URLs. No emojis. No migration section. |
| `docs/seamless-bridge.md` | Canonical user guide: overview, install (TD + artist), autostart, Send-to-Flame walkthrough, 5 troubleshooting recipes | VERIFIED | 170 lines (target: 90-200). H1 `# Seamless Flame↔Blender bridge`. All 5 H2 sections in D-09 order. Two H3 install subsections. All 5 recipes with Symptom/Likely cause/Fix format. No internal jargon. Footer link to `../README.md`. |
| `tools/smoke-test/seamless-bridge-smoke.sh` | Hybrid [mech]+[human] E2E smoke test for seamless bridge v6.3 | VERIFIED | 222 lines (target: 180-280). Executable (+x). `bash -n` clean. Shebang `#!/usr/bin/env bash`. `set -euo pipefail`. All 10 steps + Done header. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| README.md | docs/seamless-bridge.md | relative markdown links | VERIFIED | Links in What's-new bullets, Install section, Validation section, Troubleshooting section |
| README.md | PASSOFF.md | relative markdown link in History section | VERIFIED | `[PASSOFF.md](PASSOFF.md)` in History section |
| docs/seamless-bridge.md (recipe 1 Symptom) | tools/blender/forge_sender/__init__.py:240 | grep-anchor | VERIFIED | Bidirectional grep-F passes: source line 240 contains `"Send to Flame: forge-bridge not reachable at http://127.0.0.1:9999"`; doc Symptom heading reproduced verbatim |
| docs/seamless-bridge.md (recipe 2 Symptom) | tools/blender/forge_sender/preflight.py:54 | grep-anchor | VERIFIED | Bidirectional grep-F passes: source line 54 `active camera is missing '{key}'`; doc Symptom contains `active camera is missing 'forge_bake_action_name'` |
| docs/seamless-bridge.md (recipe 3 Symptom) | tools/blender/forge_sender/transport.py:220 | grep-anchor | VERIFIED | Bidirectional grep-F passes: source line 220 `"Send to Flame failed: {error}"` (not "Send failed:" — D-14 source-authoritative); doc Symptom `### Symptom: Send to Flame failed: {error}` |
| docs/seamless-bridge.md (recipe 4 Symptom) | install.sh:425 | grep-anchor | VERIFIED | Bidirectional grep-F passes: source printf emits `forge-bridge install skipped`; doc Symptom `[WARN] forge-bridge install skipped (sibling installer exited non-zero)` |
| tools/smoke-test/seamless-bridge-smoke.sh (step 5) | forge-bridge HTTP endpoint | curl http://localhost:9999/ | VERIFIED | `curl -s http://localhost:9999/ -o /dev/null -w "%{http_code}\n"` present |
| tools/smoke-test/seamless-bridge-smoke.sh (step 3) | install.sh (real run) | subprocess invocation | VERIFIED | `./install.sh` called in step 3 conditional |
| tools/smoke-test/seamless-bridge-smoke.sh (step 4) | /opt/Autodesk/shared/python/forge_bridge/scripts/forge_bridge.py | ast.parse syntax check | VERIFIED | `python3 -c "import ast, sys; ast.parse(open(sys.argv[1]).read())" "$BRIDGE_PY"` |
| tools/smoke-test/seamless-bridge-smoke.sh (step 9) | forge_bridge.py process (orphan check) | pgrep | VERIFIED | `pgrep -f forge_bridge.py \|\| true` |
| tools/smoke-test/seamless-bridge-smoke.sh (step 10) | pytest suite | subprocess invocation | VERIFIED | `pytest -q` in conditional |
| tools/smoke-test/seamless-bridge-smoke.sh (failure messaging) | docs/seamless-bridge.md#troubleshooting | stderr message string | VERIFIED | `docs/seamless-bridge.md#troubleshooting` present; `report to the troubleshooting section of docs/seamless-bridge.md` exact D-06 string present |

### Data-Flow Trace (Level 4)

Not applicable — phase 4 delivers static documentation and a shell script. No dynamic data rendering. Level 4 trace skipped.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| bash syntax valid | `bash -n tools/smoke-test/seamless-bridge-smoke.sh` | exit 0 | PASS |
| Script is executable | `test -x tools/smoke-test/seamless-bridge-smoke.sh` | exit 0 | PASS |
| Step headers all present | 11 grep-qF assertions | all exit 0 | PASS |
| Idempotence: no rm -rf | `! grep -qF "rm -rf"` | exit 0 | PASS |
| Idempotence: no --force | `! grep -qF "install.sh --force"` | exit 0 | PASS |
| Idempotence: no sudo | `! grep -qF "sudo "` | exit 0 | PASS |
| Full smoke test execution | `./tools/smoke-test/seamless-bridge-smoke.sh` | SKIP — requires live Flame + Blender | SKIP |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| DOC-01 | 04-02-PLAN.md | E2E smoke test passes on Flame 2026.2.1 + Blender 4.5+: full right-click→edit→send loop without Flame batch menu return trip | ARTIFACT DELIVERED — runtime closure pending | `tools/smoke-test/seamless-bridge-smoke.sh` (222 lines, executable, bash -n clean) exists and is the authoritative gate. First green live run closes DOC-01. Routed to human verification. |
| DOC-02 | 04-01-PLAN.md | User-facing doc covering: what changed from v6.2, how to install the addon, how forge-bridge autostart works, troubleshooting recipes | VERIFIED | `README.md` (v6.3 what's-new, install summary) + `docs/seamless-bridge.md` (full install TD+artist, autostart explanation, 5 grep-anchored troubleshooting recipes). All D-07 through D-17 items satisfied. |

No orphaned requirements — REQUIREMENTS.md maps exactly DOC-01 and DOC-02 to Phase 4, both accounted for.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| tools/smoke-test/seamless-bridge-smoke.sh | 155, 191 | References to "recipe 1" / "recipe 5" in error messages but docs/seamless-bridge.md has no numbered recipe labels — users searching for "recipe 1" will find nothing | Warning (WR-01 from 04-REVIEW.md) | Low — user can still find the correct section by reading context; docs are functional. Open by design per code review. |
| docs/seamless-bridge.md | 35 | Internal reference "recipe 4 below" (within the Install > For pipeline TDs section) — self-reference to an unnumbered recipe | Info | Negligible — the cross-reference is within the same file and the user can scroll to Troubleshooting. Same root cause as WR-01. |

No blockers found. No `TODO`/`FIXME`/placeholder comments in the three artifacts. No empty implementations. No hardcoded empty data flowing to rendering. No emojis in either doc.

**CR-01 status:** Fixed in commit d96c8ab. The `${ans,,}` bash 4.0+ lowercase expansion was replaced with a bash 3.2-portable `case "$ans" in [Yy]|[Yy][Ee][Ss])` pattern. Confirmed by grep: `${ans,,}` is absent; `case "$ans"` is present.

**WR-02 status (tee subshell race):** Open warning. The smoke test greps `$LOG` for `forge-bridge install skipped` in steps 3 and 4. Under buffered output the grep could race the tee subshell. In practice this is low-probability on local filesystems, and the failure mode (false-negative grep causes step 4 to exit 1 with a misleading message) is recoverable by re-running. Accepted per code review — non-blocking for phase completion.

**WR-03 status (read -r _ accepts premature Enter):** Open warning. Steps 5 and 9 use `read -r _` to wait for the operator. If Enter is pressed before Flame fully shuts down, the pgrep in step 9 could give a false-positive orphan. Accepted per code review — non-blocking. Polled-retry fix deferred.

### Human Verification Required

#### 1. Full smoke test live run on production stack

**Test:** From a freshly installed workstation (Flame 2026.2.1 running, forge_sender addon installed in Blender 4.5+, install.sh completed successfully), run `./tools/smoke-test/seamless-bridge-smoke.sh` from the repo root.

**Expected:** Script exits 0. All 6 mechanical steps pass automatically. All 4 human-verified steps are answerable with `y` (Blender opens on baked camera with no dialogs; Send to Flame success popup appears; new camera with keyframes appears in the target Action; no orphan pgrep after Flame quit). Transcript written to `/tmp/forge-smoke-*.log`. This is the DOC-01 acceptance event.

**Why human:** Requires a live Flame session, a Blender installation with the forge_sender addon, and forge-bridge running on port 9999. Cannot be substituted with static analysis or mocked.

#### 2. Install section walkthrough for pipeline TDs

**Test:** Follow `docs/seamless-bridge.md#install` → `### For pipeline TDs` on a workstation that has not had forge-calibrator installed before (or with `/opt/Autodesk/shared/python/` cleared). Run `./install.sh` and verify each of the four deploy targets in the installer output.

**Expected:** Installer emits `> forge_core + forge_flame`, `> forge-bridge`, `> Install`, `> tools/blender` section headers. No preflight failures on a correctly configured machine. After Flame restart, bridge probe `curl -s http://localhost:9999/ -o /dev/null -w "%{http_code}\n"` returns 200.

**Why human:** Requires a live Flame install environment and a clean or simulated-fresh `/opt/Autodesk/` state. Also validates that the section names in the doc match actual install.sh output headers, which the grep-anchors partially cover but a live run confirms unambiguously.

#### 3. Ctrl-F troubleshooting usability check (light — reviewer)

**Test:** Open `docs/seamless-bridge.md` in a rendered markdown viewer (GitHub web UI, VS Code preview, or browser). Trigger each of the five error conditions (or just copy the Symptom strings) and Ctrl-F search the rendered document.

**Expected:** Each search lands on the correct Symptom heading immediately. The fix copy is clear and actionable. No recipe is confusingly numbered (WR-01 applies here — "recipe 1" and "recipe 5" in the smoke test error messages will not have a Ctrl-F target in the rendered doc; reviewer should confirm whether this is acceptable to ship or should be addressed before v6.3 cuts).

**Why human:** Rendered markdown appearance and Ctrl-F usability are not verifiable via grep. The WR-01 discrepancy (smoke test error messages reference "recipe N" labels that don't exist in the doc) is a UX judgment call: the reviewer should decide whether to add numeric labels to the Symptom headings before shipping v6.3.

---

## Gaps Summary

No gaps blocking goal achievement. All three artifacts exist, are substantive, and are wired correctly via relative links and grep anchors. The two open code review warnings (WR-01 recipe numbering, WR-02 tee race) are non-blocking by design.

The phase cannot be marked `passed` because ROADMAP Success Criterion 1 (smoke test passes the full cycle on the production stack) is a runtime event that requires human execution. The smoke test artifact is correctly delivered and verified statically. DOC-01 closes on the first successful live run.

**Recommended next action:** Schedule a workstation session with a TD or artist to run the smoke test. Record the exit code and transcript path in a re-verification run of this file. Once the live run is confirmed, re-run `/gsd-verify-work` — status should upgrade to `passed`.

---

_Verified: 2026-04-22T19:44:44Z_
_Verifier: Claude (gsd-verifier)_
