---
phase: 03-forge-bridge-deploy
verified: 2026-04-21T00:00:00Z
status: passed
human_verification_resolved: 2026-04-21T22:30:00Z
human_verification_result: 2 passed live (live install + D-11 failure-path); 1 deferred to Phase 4 per D-14
human_verification_artifact: 03-HUMAN-UAT.md
score: 17/17 must-haves verified + 2/2 live human checks passed
overrides_applied: 0
requirements_addressed: [BRG-01, BRG-02, BRG-03, BRG-04]
human_verification:
  - test: "Run a non-dry-run ./install.sh (with --force if a prior hook exists) and confirm /opt/Autodesk/shared/python/forge_bridge/scripts/forge_bridge.py is (re)written by this installer"
    expected: "The `> forge-bridge` section emits `✓ [forge-bridge] installed at /opt/Autodesk/shared/python/forge_bridge/scripts/forge_bridge.py` AND `✓ [forge-bridge] next Flame boot will spawn the bridge on http://127.0.0.1:9999 ...`. Follow-up: `test -f /opt/Autodesk/shared/python/forge_bridge/scripts/forge_bridge.py && python3 -c 'import ast; ast.parse(open(\"/opt/Autodesk/shared/python/forge_bridge/scripts/forge_bridge.py\").read())' && echo OK` returns 0."
    why_human: "Executors (including this verifier) did not run a live non-dry-run install — doing so mutates /opt/Autodesk/shared/python/ on the operator's workstation, outside verifier scope. Both plan-01 and plan-02 summaries explicitly deferred the live install to the operator. The dry-run path proves the code is wired correctly; confirming the real install actually lands the hook file requires a human run."
  - test: "Simulate a bridge-install failure (e.g., unset FORGE_BRIDGE_REPO and temporarily offline the machine, OR set FORGE_BRIDGE_VERSION=v9.99.99 to force a curl 404) and run ./install.sh"
    expected: "D-10 warning fires as a SINGLE unbroken paragraph on stderr, install.sh CONTINUES to the `> Install` Camera Match section, and the overall script exits 0 (camera-match succeeded, only bridge failed per D-11). No orphan exit. No aborted install."
    why_human: "D-11 exit-code discipline needs a real failure injection to confirm the `if eval ...; else BRIDGE_OK=0; fi` construct actually preserves exit 0 on bridge-only failure. Hard to force programmatically without mutating the workstation's network or /opt path. Static grep confirms the code path; live verification confirms the behavior."
  - test: "After a successful live install + Flame restart, verify the bridge is reachable via curl -s http://localhost:9999/ -o /dev/null -w \"%{http_code}\\n\" (expected: 200). Then kill Flame and confirm no orphan forge_bridge process remains."
    expected: "HTTP 200 response when Flame is running; no forge_bridge / python process listed in ps after Flame quits. This closes BRG-01 and BRG-02 LIVE."
    why_human: "BRG-01 and BRG-02 live verification is explicitly deferred to Phase 4's E2E smoke test per D-14. This phase delivers install-side wiring only. Flagging here so the verifier's scope boundary is traceable to the user."
---

# Phase 3: forge-bridge-deploy Verification Report

**Phase Goal (ROADMAP.md):** "forge-bridge starts automatically when Flame boots and shuts down cleanly when Flame quits, with install.sh wiring the entire lifecycle so a fresh install works without manual bridge setup"

**Verified:** 2026-04-21
**Status:** human_needed — automated verification PASSED 17/17 must-haves; three live-system checks remain for the operator (non-dry-run install confirmation, failure-path exit-code discipline, Phase 4 E2E scope items).
**Re-verification:** No — initial verification.

## Scope Boundary (per D-14 from CONTEXT.md)

This phase delivers **install-side wiring only**. Live Flame smoke testing (bridge actually starts alongside Flame, bridge actually dies on Flame quit) is deferred to Phase 4's E2E harness. "forge-bridge starts automatically when Flame boots" is wired in this phase via `install.sh` dropping the hook file at the correct path (BRG-04); Phase 4 verifies the live startup (BRG-01 / BRG-02 live). The verifier has honored this boundary and classified the three live-system checks as `human_needed` rather than `gaps_found`.

## Goal Achievement

### Observable Truths (merged from 03-01 + 03-02 PLAN must_haves)

| #   | Truth                                                                                                                                          | Status     | Evidence                                                                                                                                                       |
| --- | ---------------------------------------------------------------------------------------------------------------------------------------------- | ---------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | install.sh defines a pinned `FORGE_BRIDGE_VERSION="v1.3.0"` constant (env-override form)                                                        | VERIFIED   | `install.sh:60` — `FORGE_BRIDGE_VERSION="${FORGE_BRIDGE_VERSION:-v1.3.0}"`                                                                                     |
| 2   | install.sh honors FORGE_BRIDGE_REPO env var (absolute path override)                                                                            | VERIFIED   | `install.sh:66` — `FORGE_BRIDGE_REPO="${FORGE_BRIDGE_REPO:-}"`; consumed by `_resolve_forge_bridge_source` at lines 157-177                                    |
| 3   | install.sh auto-detects a local clone in three fallback paths (`../forge-bridge`, `$HOME/Documents/GitHub/forge-bridge`, `$HOME/code/forge-bridge`) | VERIFIED   | `install.sh:180-201` — explicit for-loop over the three documented paths                                                                                       |
| 4   | `--dry-run` skips curl, skips sibling-installer invocation, skips /opt/Autodesk/ writes for the bridge step                                     | VERIFIED   | Live `./install.sh --dry-run` prints `[dry-run] would execute: bash "..."` and then `[forge-bridge] dry-run complete — skipped actual install and sanity check`. No curl fired, no files written. |
| 5   | `--force` plumbs into a reusable primitive that deletes pre-existing hook before reinstall                                                      | VERIFIED   | `_bridge_rm_force()` at `install.sh:217-230` checks FORCE, rms `$FORGE_BRIDGE_HOOK_PATH` via the `run` wrapper; called at line 349                              |
| 6   | `--help` output documents the new FORGE_BRIDGE_REPO and FORGE_BRIDGE_VERSION env vars                                                           | VERIFIED   | `./install.sh --help` output includes `FORGE_BRIDGE_VERSION`, `FORGE_BRIDGE_REPO`, and `FORGE_ENV` lines (confirmed by live run; sed slice widened 3,23p → 3,29p at line 108) |
| 7   | `install.sh` parses cleanly under `bash -n`                                                                                                     | VERIFIED   | `bash -n install.sh` → exit 0                                                                                                                                  |
| 8   | `install.sh -h/--help` still exits 0                                                                                                            | VERIFIED   | Live run: `EXIT=0`                                                                                                                                              |
| 9   | install.sh has a new `> forge-bridge` section emitted via the existing `step` printer                                                           | VERIFIED   | `install.sh:340` — `step "forge-bridge"`; live dry-run prints `> forge-bridge` header                                                                           |
| 10  | The `> forge-bridge` section runs BEFORE the `> Install` section (D-07)                                                                          | VERIFIED   | awk positional: `fb=340, inst=430` — bridge section precedes Install section                                                                                    |
| 11  | Non-dry-run path invokes `_resolve_forge_bridge_source` then `_bridge_rm_force` then executes the resolved sibling installer with correct env vars | VERIFIED   | `install.sh:346,349,377-391` — resolver + rm-force + kind-switch (local→argv array, curl→eval)                                                                  |
| 12  | On bridge-install failure (sibling non-zero OR D-15 sanity fails), D-10 warning emits verbatim AND install continues                            | VERIFIED   | `install.sh:377-391,399-407` sets BRIDGE_OK=0 and BRIDGE_FAIL_REASON without calling exit; `install.sh:425-426` emits the single-paragraph D-10 printf on stderr |
| 13  | Exit code reflects overall state: bridge-only fail → exit 0 (camera-match ran); camera-match fail → non-zero as before                           | VERIFIED (static) / human (live) | No `exit` call inside the `> forge-bridge` section (verified by inspection). Live failure-injection test flagged for human verification.                     |
| 14  | `--dry-run` prints `[dry-run] would execute: <resolved cmd>` and does NOT fire curl, shell out to sibling, or touch /opt/Autodesk/              | VERIFIED   | Live `./install.sh --dry-run` captures the `[dry-run] would execute: bash "..."` line + the `dry-run complete — skipped actual install and sanity check` line  |
| 15  | D-15 post-install sanity check runs: `test -f $FORGE_BRIDGE_HOOK_PATH && python3 -c 'import ast; ast.parse(...)' "$FORGE_BRIDGE_HOOK_PATH"`      | VERIFIED   | `install.sh:400-406` — `[[ ! -f "$FORGE_BRIDGE_HOOK_PATH" ]]` + `python3 -c "import ast, sys; ast.parse(open(sys.argv[1]).read())"`; gated by `(( ! DRY_RUN )) && (( BRIDGE_OK ))` |
| 16  | install.sh still parses cleanly + `--help` exits 0 after Plan 02's edits                                                                          | VERIFIED   | `bash -n install.sh` exit 0; `./install.sh --help` exit 0                                                                                                        |
| 17  | D-10 copy is single-paragraph `printf` (not two `warn` calls); includes reason substitution and FORGE_BRIDGE_VERSION retry URL                  | VERIFIED   | `install.sh:425-426` — single `printf ... >&2` with `%s` substitutions for reason + version; matches D-10 spec verbatim (with `${FORGE_BRIDGE_VERSION}` dynamic substitution in place of CONTEXT.md's literal `v1.1.0` per plan-02 §interfaces "Note on D-10 copy") |

**Score:** 17/17 truths verified via automated checks.

### Required Artifacts

| Artifact    | Expected                                                                                                                                  | Status     | Details                                                                                                                                                                                                                       |
| ----------- | ----------------------------------------------------------------------------------------------------------------------------------------- | ---------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `install.sh` | Constants (FORGE_BRIDGE_VERSION, FORGE_BRIDGE_REPO, FORGE_BRIDGE_HOOK_PATH), helpers (`_resolve_forge_bridge_source`, `_bridge_rm_force`), `> forge-bridge` section before `> Install`, D-10 copy, D-15 sanity check, D-11 exit discipline | VERIFIED   | 524 lines total. All required constants at lines 60/66/70; helpers at 153/217; bridge section at 340 (before `> Install` at 430); D-10 printf at 425-426; D-15 at 400-406; no `exit` call inside bridge section. |

### Key Link Verification

| From                                                         | To                                                                           | Via                                                                                                                                                      | Status  | Details                                                                                                                                                                                            |
| ------------------------------------------------------------ | ---------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- | ------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| install.sh constants block (top of file)                     | install.sh bridge-install section                                             | Bash variables FORGE_BRIDGE_VERSION / FORGE_BRIDGE_REPO / FORGE_BRIDGE_HOOK_PATH set before the `> forge-bridge` section runs                            | WIRED   | Constants at lines 60/66/70; referenced inside the resolver (lines 157, 208) and the bridge section (lines 400, 403, 426).                                                                         |
| install.sh preflight sections (lines 239-326)                 | install.sh new `> forge-bridge` section                                       | Linear bash execution — preflight halt on PREFLIGHT_FAIL at 323-326 ⇒ bridge section runs                                                                | WIRED   | `step "forge-bridge"` at line 340, immediately after preflight halt. No intervening `exit`.                                                                                                        |
| install.sh bridge section                                     | /opt/Autodesk/shared/python/forge_bridge/scripts/forge_bridge.py              | Resolved sibling installer (local argv-array OR curl\|bash) drops hook file at FORGE_BRIDGE_HOOK_PATH                                                    | WIRED (static) / human (live) | Static: argv-array invocation at line 378, eval "$FORGE_BRIDGE_SOURCE_CMD" at line 385; D-15 sanity check at 400-406. Live landing of the file needs a non-dry-run install (see human verification). |
| install.sh bridge-install failure path                        | User terminal (stderr warning) — install continues to Camera Match            | `printf ... >&2` at line 425-426 with D-10 copy; BRIDGE_OK=0 flag; no `exit`                                                                             | WIRED   | Single-paragraph printf form confirmed; `BRIDGE_OK=0` set at 381, 388, 401, 404 without exit; Camera Match install runs immediately after at line 430.                                             |

### Data-Flow Trace (Level 4)

Not applicable — install.sh is a deploy script, not a component that renders dynamic data. All data flows are env-var/bash-constant substitutions into shell commands and user-facing printf calls, which are directly inspectable and already covered by truths 1-17.

### Behavioral Spot-Checks

| Behavior                                                                                 | Command                                                                                                    | Result                                                                                                                                               | Status |
| ---------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| install.sh parses under bash -n                                                           | `bash -n install.sh`                                                                                        | exit 0                                                                                                                                               | PASS   |
| --help exits 0 and surfaces new env vars                                                  | `./install.sh --help`                                                                                       | exit 0; output includes `FORGE_BRIDGE_VERSION`, `FORGE_BRIDGE_REPO`, `FORGE_ENV`                                                                      | PASS   |
| --dry-run completes without side effects and prints would-execute line                    | `./install.sh --dry-run`                                                                                    | exit 0; captures `> forge-bridge\n  ✓ [forge-bridge] using local clone at .../forge-bridge\n  ✓ [forge-bridge] local clone version: v1.3.0-...\n    [dry-run] would execute: bash "..."\n  ✓ [forge-bridge] dry-run complete — skipped actual install and sanity check` | PASS   |
| Section ordering: > forge-bridge precedes > Install                                       | `awk '/^step "forge-bridge"$/ {fb=NR} /^step "Install"$/ {inst=NR} END {print fb, inst, fb<inst}' install.sh` | `340 430 1` (fb<inst true)                                                                                                                            | PASS   |
| FORGE_BRIDGE_REPO=/nonexistent triggers fallthrough warn                                  | `FORGE_BRIDGE_REPO=/nonexistent ./install.sh --dry-run`                                                     | Emits `! [forge-bridge] FORGE_BRIDGE_REPO=/nonexistent does not contain scripts/install-flame-hook.sh — falling through to auto-detect`, then finds the sibling clone | PASS   |
| WR-01 injection payload rejected (semver regex)                                           | `FORGE_BRIDGE_VERSION='v1.3.0"; rm -rf ~; echo "' ./install.sh --help`                                      | exit 2, error `FORGE_BRIDGE_VERSION=... is not a valid semver tag (expected vN.N.N, optionally -prerelease or .build)`                                | PASS   |
| WR-01 bad-tag string rejected                                                             | `FORGE_BRIDGE_VERSION='bad tag with spaces' ./install.sh --help`                                            | exit 2, same error copy                                                                                                                              | PASS   |
| WR-03 --dry-run --force does NOT emit past-tense "removed" ok line                        | `./install.sh --dry-run --force`                                                                            | Emits `[dry] rm -f "$FORGE_BRIDGE_HOOK_PATH"` from the `run` wrapper, but NO subsequent `✓ [forge-bridge] --force: removed existing ...` line        | PASS   |
| WR-02 argv-array form used for local KIND                                                  | grep `"${FORGE_BRIDGE_SOURCE_ARGV[@]}"` at install.sh call site                                            | Line 378: `if "${FORGE_BRIDGE_SOURCE_ARGV[@]}"; then` (operator-supplied paths never flow through eval)                                              | PASS   |

All nine behavioral spot-checks pass.

### Requirements Coverage

| Requirement | Source Plan       | Description                                                                                                                     | Status     | Evidence                                                                                                                                                                                                                                           |
| ----------- | ----------------- | ------------------------------------------------------------------------------------------------------------------------------- | ---------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| BRG-01      | 03-02             | forge-bridge auto-starts as a Flame-spawned subprocess when the Camera Match hook initialises (Flame boot triggers it)          | SATISFIED (install-side) / NEEDS HUMAN (live) | Install-side: `install.sh` deploys the sibling `forge_bridge.py` hook at `/opt/Autodesk/shared/python/forge_bridge/scripts/forge_bridge.py` via the resolved sibling installer. Live auto-start on Flame boot is deferred to Phase 4's E2E smoke test per D-14. |
| BRG-02      | 03-02             | Bridge process dies cleanly when Flame quits — no orphan processes, no port conflicts on the next Flame boot                     | SATISFIED (install-side) / NEEDS HUMAN (live) | Bridge lifecycle is owned by the sibling `forge_bridge.py` hook's existing design (per CONTEXT.md §Phase Boundary). This phase does not modify the hook — it only deploys it. Live shutdown verification is Phase 4.                                                |
| BRG-03      | 03-02             | Bridge binds to 127.0.0.1 only (single-user, local workstation; never exposes Flame's Python surface to the network)            | SATISFIED (inherited) / NEEDS HUMAN (negative test) | Binding is hardcoded in the sibling hook's design (per CONTEXT.md §Phase Boundary). Phase 3 deploys the hook unchanged. Phase 4 owns the negative test that the bridge does not bind to 0.0.0.0.                                                   |
| BRG-04      | 03-01, 03-02      | install.sh deploys the forge-bridge launcher alongside the Camera Match hook so a fresh install wires the production bridge without extra user steps | SATISFIED   | Entire `> forge-bridge` section at install.sh:340-427 wires resolution + `--force`-aware rm + sibling-installer invocation + D-15 sanity check + D-10/D-11 failure handling. Closed end-to-end.                                                    |

**No orphaned requirements.** REQUIREMENTS.md §Traceability maps BRG-01/02/03/04 to Phase 3; all four are claimed by plans 03-01 or 03-02 and all four are accounted for above. BRG-01/02/03 inherit install-side satisfaction from the sibling-repo design; live verification is Phase 4's scope per D-14.

### Anti-Patterns Found

No TODO/FIXME/XXX/HACK/PLACEHOLDER markers in install.sh. No empty implementations. No console.log-only code. No hardcoded empty data. All dry-run branches are genuine (verified by the --dry-run --force WR-03 fix — no more cosmetic success-on-no-op messages).

| File        | Line | Pattern | Severity | Impact     |
| ----------- | ---- | ------- | -------- | ---------- |
| install.sh  | —    | (none)  | —        | —          |

### Human Verification Required

See frontmatter `human_verification:` section. Three items routed to the operator:

1. **Live non-dry-run install confirmation** — a real `./install.sh` run to confirm `/opt/Autodesk/shared/python/forge_bridge/scripts/forge_bridge.py` is (re)written by our installer and passes the D-15 `python3 -c "import ast; ast.parse(...)"` sanity check. Static analysis confirms the code path; live verification confirms behavior end-to-end. Deferred because the verifier does not mutate the workstation outside its worktree.

2. **D-11 exit-code discipline under real failure** — simulate a bridge-install failure (e.g., `FORGE_BRIDGE_VERSION=v9.99.99` to force a curl 404, or offline the machine with FORGE_BRIDGE_REPO unset) and confirm `install.sh` emits the D-10 warning, CONTINUES to the Camera Match install, and exits 0 overall. Static analysis confirms no `exit` in the bridge section; live verification confirms the `set -e` bypass works as documented.

3. **Phase 4 scope items (BRG-01/02 live)** — full Flame-boot/Flame-quit lifecycle checks. Explicitly out-of-scope for Phase 3 per D-14 but flagged here so the verification scope boundary is traceable.

### Gaps Summary

No gaps. All 17 must-haves pass automated verification. The three human-verification items are scope-boundary deferrals (D-14) + live-system confirmations that cannot be run programmatically in the verifier's worktree without mutating `/opt/Autodesk/`. The phase's install-side wiring is complete and correct; BRG-04 is fully closed, BRG-01/02/03 inherit install-side satisfaction from the sibling-repo design per CONTEXT.md §Phase Boundary.

### Code Review Fix Audit (WR-01 / WR-02 / WR-03 regression check)

Reviewed the three Warning fixes from `03-REVIEW.md` and their commits:

| WR     | Commit    | Applied Fix                                                                                                                                                                                                                     | Regression on plan must-haves?                                                                                                                                                                                                    |
| ------ | --------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| WR-01  | `6a9292f` | Strict semver regex `^v[0-9]+\.[0-9]+\.[0-9]+([-.][A-Za-z0-9]+)*$` at install.sh:96-99, runs before arg parsing. Rejects injection payloads with exit 2. | None. D-10 copy still verbatim (uses `%s` expansion; the validated version flows through unchanged). Plan 03-01 truth 1 ("FORGE_BRIDGE_VERSION pinned to v1.3.0 env-override form") still holds. `./install.sh --help` still exits 0 with valid version (default v1.3.0 passes regex). |
| WR-02  | `e194f48` | Added `FORGE_BRIDGE_SOURCE_ARGV` array (eval-free execution form) alongside `FORGE_BRIDGE_SOURCE_CMD` (display form). Local KIND runs argv array; curl KIND still uses eval (curl\|bash pipeline needs shell semantics).         | None. Plan 03-02 truth "invokes the sibling installer under D-09 warn-and-continue" still holds — the `if argv; then ... else BRIDGE_OK=0 ...` construct at lines 377-383 preserves the `set -e` bypass semantics identically. Also verified argv invocation at line 378. |
| WR-03  | `84ac649` | Wrapped `ok "[forge-bridge] --force: removed existing ..."` in `if (( ! DRY_RUN )); then ... fi`. Suppresses misleading past-tense message under --dry-run --force.                                                             | None. D-12 dry-run contract STRENGTHENED (now honored more completely). Live `./install.sh --dry-run --force` confirms: `[dry] rm -f ...` fires from the `run` wrapper, no subsequent "removed existing" ok. Plan 03-01 truth 5 ("--force plumbs into a reusable primitive") still holds — the rm still happens on real --force runs; only the dry-run print suppressed. |

**Conclusion:** All three WR fixes strengthen the contracts without regressing any must-have. D-10 copy is unchanged. D-12 dry-run is more faithful. D-11 exit discipline is untouched. WR-01's exit-2-on-bad-version is a new hard-exit path, but it only triggers on clearly malformed input AND it runs before any plan-defined behavior — it does not change any documented success path.

### Commits Verified

| # | Hash      | Scope       | Message                                                                                   | Content Verified |
| - | --------- | ----------- | ----------------------------------------------------------------------------------------- | ---------------- |
| 1 | `052bd51` | Task 03-01-1 | feat(03-01): add forge-bridge constants, env-var reads, --help docstring                   | Yes — constants + docstring present at install.sh:22-28, 60-70, 108                                         |
| 2 | `f0906ed` | Task 03-01-2 | feat(03-01): add _resolve_forge_bridge_source and _bridge_rm_force helpers                | Yes — functions present at install.sh:153, 217                                                              |
| 3 | `7004768` | Task 03-02-1 | feat(03-02): add > forge-bridge install section with D-09/D-10/D-11 failure handling      | Yes — section at install.sh:328-427, sits before `step "Install"`                                           |
| 4 | `d32bed4` | Task 03-02-2 | docs(03-02): update Done heredoc to mention bridge + add scope-boundary comment           | Yes — scope-boundary comment at install.sh:485-493; heredoc at install.sh:494-524 mentions bridge + smoke-test |
| 5 | `84ac649` | Fix WR-03    | fix(03): WR-03 suppress dry-run past-tense 'removed' message in _bridge_rm_force           | Yes — guard at install.sh:225-227                                                                           |
| 6 | `6a9292f` | Fix WR-01    | fix(03): WR-01 validate FORGE_BRIDGE_VERSION as semver tag before interpolation            | Yes — regex guard at install.sh:96-99                                                                        |
| 7 | `e194f48` | Fix WR-02    | fix(03): WR-02 replace eval with argv-array for local-path forge-bridge source             | Yes — argv array at install.sh:163, 190; kind-switch at install.sh:377-391                                   |

---

_Verified: 2026-04-21_
_Verifier: Claude (gsd-verifier)_
