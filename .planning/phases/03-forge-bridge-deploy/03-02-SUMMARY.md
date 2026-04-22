---
phase: 03-forge-bridge-deploy
plan: 02
subsystem: install
tags: [install, bash, forge-bridge, deploy, section-ordering, failure-handling, dry-run]
requirements_addressed: [BRG-01, BRG-02, BRG-03, BRG-04]
dependency_graph:
  requires:
    - "install.sh helpers from Plan 03-01: _resolve_forge_bridge_source, _bridge_rm_force"
    - "install.sh constants from Plan 03-01: FORGE_BRIDGE_VERSION (v1.3.0), FORGE_BRIDGE_REPO, FORGE_BRIDGE_HOOK_PATH"
    - "forge-bridge sibling repo at github.com/cnoellert/forge-bridge (pinned v1.3.0 tag or local clone)"
  provides:
    - "install.sh `> forge-bridge` install step — invokes the sibling installer, runs D-15 sanity check, emits D-10 warning on failure and continues"
    - "install.sh `> Done` heredoc updated to mention bridge registration + post-boot smoke-test"
  affects:
    - "Phase 4 E2E smoke test (BRG-01/BRG-02 live verification — this plan intentionally stops short of live)"
tech_stack:
  added: []
  patterns:
    - "`if eval \"...\"; then ... else ...` idiom for running a sub-shell command without tripping `set -e` in the outer script (D-09 warn-and-continue)"
    - "Single-`printf` form for multi-clause user-facing warning (avoids the `warn` helper's `  ! ` prefix clashing with an embedded `[WARN]` token)"
    - "Belt-and-suspenders sanity check: sibling installer's own ast.parse + our D-15 ast.parse for clean failure classification ownership"
key_files:
  created: []
  modified:
    - install.sh
decisions:
  - "D-07: bridge section runs BEFORE Camera Match install (fb line 296, inst line 370) so failure semantics fire in terminal-readable order"
  - "D-08: `step \"forge-bridge\"` header matches existing section-marker convention"
  - "D-09: sibling-installer non-zero exit OR D-15 failure ⇒ BRIDGE_OK=0 + BRIDGE_FAIL_REASON set; script does NOT call `exit`"
  - "D-10: warning emitted as single `printf` to stderr with `$C_WARN`/`$C_END` (NOT via `warn`, to preserve the single-paragraph contract)"
  - "D-11: exit code follows the Camera Match section's outcome; bridge-only failure lets install.sh exit 0 with warning"
  - "D-12: dry-run prints `[dry-run] would execute: <resolved cmd>`, skips sibling installer AND D-15 sanity check (both would touch /opt/Autodesk/)"
  - "D-13: `_bridge_rm_force` (from Plan 03-01) called unconditionally — no-op under --force absent"
  - "D-14: no live Flame smoke test here; scope-boundary comment above `cat <<EOF` documents deferral to Phase 4"
  - "D-15: `test -f \"$FORGE_BRIDGE_HOOK_PATH\"` + `python3 -c 'import ast, sys; ast.parse(open(sys.argv[1]).read())' \"$FORGE_BRIDGE_HOOK_PATH\"`"
metrics:
  duration: "5m"
  completed: "2026-04-21"
  tasks: 2
  files_modified: 1
  loc_delta: "+107 / -2"
  tests_added: 0
  commits: 2
---

# Phase 3 Plan 02: install.sh `> forge-bridge` section + Done-block update — Summary

**One-liner:** Wired Plan 03-01's forge-bridge primitives into install.sh by adding a `> forge-bridge` install section (line 296, before `> Install` at 370) that invokes the resolved sibling installer under D-09 warn-and-continue semantics, runs the D-15 ast.parse sanity check, and emits the D-10 failure copy as a single unbroken paragraph — plus a Done-block refresh mentioning the bridge alongside Camera Match and documenting the scope boundary.

## What Landed

### Task 1 — `> forge-bridge` install section (commit `7004768`)

**File: `install.sh`**

Inserted a 73-line section between the preflight halt (line 282, unchanged) and the `step "Install"` line (now at 370). Exact body lives at **lines 285–368** in the post-Task-1 file. Sequence inside the section:

1. **Line 296** — `step "forge-bridge"` header (matches D-08 naming).
2. **Lines 297–298** — initialise `BRIDGE_OK=1` / `BRIDGE_FAIL_REASON=""` state.
3. **Lines 302** — `_resolve_forge_bridge_source` (Plan 03-01 helper) picks local-clone-vs-curl, sets `FORGE_BRIDGE_SOURCE_KIND` + `FORGE_BRIDGE_SOURCE_CMD`, prints the D-03 info line. D-01 priority (`FORGE_BRIDGE_REPO` env → sibling auto-detect → curl fallback) lives in the helper.
4. **Line 305** — `_bridge_rm_force` (Plan 03-01 helper) — rm's `$FORGE_BRIDGE_HOOK_PATH` under `--force`, no-op otherwise. Honors `run` dry-run propagation internally.
5. **Lines 311–336** — dry-run branch prints `[dry-run] would execute: <cmd>`; non-dry-run branch invokes the resolved command via `if eval "$FORGE_BRIDGE_SOURCE_CMD"; then ... else BRIDGE_OK=0; BRIDGE_FAIL_REASON="sibling installer exited non-zero"; fi`. The `if`-wrapper is the key D-09 enabler — `set -e` in the outer script is bypassed inside the conditional, so a non-zero exit from the sibling routes to the `else` branch instead of aborting install.sh.
6. **Lines 342–351** — D-15 sanity check, gated by `(( ! DRY_RUN )) && (( BRIDGE_OK ))`. Runs `[[ -f "$FORGE_BRIDGE_HOOK_PATH" ]]` first (clear error text if the installer silently didn't drop the file), then `python3 -c "import ast, sys; ast.parse(open(sys.argv[1]).read())"` (catches truncated/mangled payloads).
7. **Lines 357–367** — outcome report: success prints two `ok` lines, failure prints the D-10 warning as a single `printf` with `$C_WARN`/`$C_END` TTY colouring, `$BRIDGE_FAIL_REASON` in the `(reason)` slot and `$FORGE_BRIDGE_VERSION` in the retry-hint URL tag.

**Why single `printf` over `warn`:** the `warn` helper prepends `  ! ` already; the D-10 copy embeds `[WARN]` as the leading token to preserve contractual paragraph shape; two levels of prefix would visually collide. A bare `printf ... >&2` lets the `[WARN]` token live inside the paragraph exactly as D-10 specifies while still writing to stderr like `warn`/`err`. Verified by the `grep -q 'forge-bridge install skipped.*VP-solve and v6.2 static round-trip still work'` must-have — that regex only matches when the entire sentence lives on one logical line, which the single-`printf` form produces.

**Diff:** +85 / -0 on install.sh.

### Task 2 — Done heredoc + scope-boundary comment (commit `d32bed4`)

**File: `install.sh`**

Two edits to the tail of the file:

1. **Scope-boundary comment block** (lines 425–433, immediately above `cat <<EOF`): documents that install.sh deliberately does NOT start Flame, curl `127.0.0.1:9999`, or kill any processes, and points to Phase 4's E2E smoke test for live BRG-01/BRG-02 verification per D-14. Future auditors reading the "Done" section get an explicit scope marker.
2. **Next-steps heredoc refresh** (lines 436–463): step 1 now mentions both the Camera Match hook AND the forge-bridge hook register and references the `[WARN]` fallback; step 2 is reframed as "reload without restart" (with an explicit note that the bridge itself still needs a restart); step 3 unchanged; new step 4 adds the post-Flame-boot smoke-test one-liner `curl -s http://localhost:9999/ -o /dev/null -w "%{http_code}\n"` with expected-response annotation.

**Diff:** +22 / -2 on install.sh.

## Verification Results

All 15 must-haves from the plan's `<verification>` section passed. Output captured 2026-04-21:

| # | Check | Result |
|---|-------|--------|
| 1 | `bash -n install.sh` | PARSE_OK |
| 2 | `grep -q '^step "forge-bridge"$' install.sh` | OK (line 296) |
| 3 | Bridge section precedes Install (`awk` positional check) | OK (fb=296, inst=370) |
| 4 | D-10 warning is a SINGLE logical line | OK (line 365 `printf` hit) |
| 5 | `http://127.0.0.1:9999` present in warning | OK |
| 6 | Retry hint local `FORGE_BRIDGE_REPO=<path> ./install.sh` | OK |
| 7 | Retry hint curl form with version slot filled by printf | OK |
| 8 | D-15 sanity check `python3 -c "import ast ...` | OK |
| 9 | `eval "$FORGE_BRIDGE_SOURCE_CMD"` call site | OK (line 326) |
| 10 | Scope-boundary comment block | OK (line 425) |
| 11 | `./install.sh --help` exits 0 | OK |
| 12 | `./install.sh --dry-run` prints `[dry-run] would execute:` | OK |
| 13 | `./install.sh --dry-run` prints `forge-bridge` | OK |
| 14 | `./install.sh --dry-run` exits 0 | OK |
| 15 | `FORGE_BRIDGE_REPO=/nonexistent` triggers fallthrough warn | OK |

### Captured `./install.sh --dry-run` output (forge-bridge section only)

```
> forge-bridge
  ✓ [forge-bridge] using local clone at /Users/cnoellert/Documents/GitHub/forge-bridge
  ✓ [forge-bridge] local clone version: v1.3.0
    [dry-run] would execute: bash "/Users/cnoellert/Documents/GitHub/forge-bridge/scripts/install-flame-hook.sh"
  ✓ [forge-bridge] dry-run complete — skipped actual install and sanity check
```

Resolver picked the sibling clone at `~/Documents/GitHub/forge-bridge` (priority 2 of D-01); reports v1.3.0 from `git describe --tags --always --dirty` (D-06). Command that WOULD execute is shown but NOT fired — no curl, no shell-out to the sibling installer, no touch of `/opt/Autodesk/` — satisfying D-12.

### Updated `> Done` heredoc (captured from dry-run tail)

```
> Done

Next steps:

  1. Restart Flame. On next boot, both the Camera Match hook AND the forge-bridge
     hook register — forge-bridge will start listening on http://127.0.0.1:9999.
     If the forge-bridge install was skipped (see the [WARN] above), v6.3
     Send-to-Flame will fail until the bridge is deployed; VP-solve and v6.2
     static round-trip still work.

  2. To reload the live Camera Match module without a restart (bridge still needs
     a restart to register):

     import sys, gc, types
     src = open('/opt/Autodesk/shared/python/camera_match/camera_match.py').read()
     code = compile(src, '/opt/Autodesk/shared/python/camera_match/camera_match.py', 'exec')
     for o in gc.get_objects():
         if (isinstance(o, types.ModuleType)
             and getattr(o, '__name__', '') == 'camera_match'
             and (getattr(o, '__file__', None) or '').endswith('.py')):
             exec(code, o.__dict__)
             sys.modules['camera_match'] = o

  3. Close and reopen any Camera Match windows (Qt state is captured at construction).

  4. Live smoke-test the bridge after Flame has fully booted:

       curl -s http://localhost:9999/ -o /dev/null -w "%{http_code}\n"
       # expect: 200
```

## Decisions Implemented

| D-XX | Where | How |
|------|-------|-----|
| D-07 | Section inserted between preflight halt and `step "Install"` | Bridge section at line 296; Camera Match `step "Install"` at line 370 — strict file-order precedence confirmed by `awk` check #3 |
| D-08 | `step "forge-bridge"` header | Uses the existing `step` printer so the `> forge-bridge` marker matches `> Source` / `> Install` / etc. visual convention |
| D-09 | `if eval "$FORGE_BRIDGE_SOURCE_CMD"; then ... else BRIDGE_OK=0` | The `if`-wrapper bypasses `set -e`, so sibling-installer failure routes to the else-branch without aborting install.sh. Camera Match section runs unconditionally after. |
| D-10 | Single `printf ... >&2` at line 365 | Verbatim copy from CONTEXT.md; `${BRIDGE_FAIL_REASON}` fills the (reason) slot; `${FORGE_BRIDGE_VERSION}` fills the curl-URL version tag so a bumped pin auto-updates the retry hint |
| D-11 | No `exit` call anywhere in the bridge section | install.sh's last-command-wins default exit takes the Camera Match outcome; bridge-only failure yields exit 0 with warning |
| D-12 | `if (( DRY_RUN )); then printf "[dry-run] would execute: ..."; else eval ...; fi` + D-15 gated on `(( ! DRY_RUN ))` | No sibling installer runs, no sanity check runs, no `/opt/Autodesk/` touched under dry-run |
| D-13 | `_bridge_rm_force` called unconditionally (no-op when FORCE=0) | Plan 03-01's helper owns the FORCE gating internally |
| D-14 | Scope-boundary comment block above `cat <<EOF` | Explicit "install.sh does NOT: start/curl/kill" enumeration with pointer to Phase 4 E2E smoke test |
| D-15 | Lines 342–351: `[[ ! -f "$FORGE_BRIDGE_HOOK_PATH" ]]` + `python3 -c 'import ast, sys; ast.parse(...)' "$FORGE_BRIDGE_HOOK_PATH"` | Failure of either check sets BRIDGE_OK=0 with a specific BRIDGE_FAIL_REASON string |

## Deviations from Plan

### [Minor — plan-verify-regex vs prescribed-content mismatch] `grep -q 'forge-bridge hook register'` doesn't match

- **Found during:** Task 2 post-edit verification.
- **Issue:** The plan's acceptance criterion includes `grep -q 'forge-bridge hook register' install.sh`. This check assumes the phrase lives on a single line, but the plan-prescribed heredoc text wraps it across two lines (`forge-bridge\n     hook register` — an 80-column-friendly break inside "forge-bridge\n     hook register — forge-bridge will start listening..."). The file content matches the plan's prescribed text exactly; the plan's own verify-regex is just single-line where the content is multi-line.
- **Fix:** Verified via multiline grep that the exact phrase is present at lines 438–439:
  ```
  438:  1. Restart Flame. On next boot, both the Camera Match hook AND the forge-bridge
  439:     hook register — forge-bridge will start listening on http://127.0.0.1:9999.
  ```
  No text change needed; the content is exactly what the plan prescribed. Flagging here for the verifier so the regex miss isn't misread as a scope gap.
- **Files modified:** n/a (plan-regex observation, not a fix).

### [Observational — no live non-dry-run install run]

- **Found during:** Summary-writing phase.
- **Issue:** Plan's output spec includes "Confirmation that `test -f /opt/Autodesk/shared/python/forge_bridge/scripts/forge_bridge.py` AFTER a non-dry-run run of `./install.sh` returns 0 (the hook actually landed) — if the executor runs the installer for real during Phase 3 execution".
- **Decision:** Did NOT run a non-dry-run `./install.sh` from inside the executor worktree. Rationale: a real install would mutate `/opt/Autodesk/shared/python/` on the user's workstation, which is outside Phase 3's dry-run-only scope and outside the GSD parallel-executor's implicit "don't touch the broader system" boundary. The user can run the installer for real at their discretion once the phase orchestrator merges this wave.
- **Files modified:** n/a.

No auth gates, no architectural changes, no Rule-4 escalations. The plan was exhaustively pre-negotiated in CONTEXT.md D-07–D-15 and executed verbatim.

## Known Stubs

None. Every codepath in the bridge section has live behavior:
- Success path: two `ok` lines + fall through to Camera Match install
- Dry-run path: prints the resolved command + skip-sanity-check `ok` line
- Failure path: D-10 warning, `BRIDGE_OK=0` state, continue to Camera Match

No hardcoded empty values, no placeholder text, no "TODO" markers. The deferred D-14 items (live Flame smoke test) are explicitly out-of-scope and documented via the scope-boundary comment — not stubs.

## Threat Flags

None — all threats in the plan's `<threat_model>` (T-03-04 through T-03-09) have either accept or mitigate dispositions that are fully covered by the code landed here:
- T-03-06 (eval of `FORGE_BRIDGE_SOURCE_CMD`) — mitigated: command string is constructed from hard-coded literals + `FORGE_BRIDGE_VERSION` pin + operator-controlled env/path, all same-trust-tier with running install.sh itself.
- T-03-07 (bridge failure aborts install) — mitigated: explicit `BRIDGE_OK` flag + `if eval; else` idiom + no-`exit`-in-section confirmed.
- T-03-04/05/08/09 — accept per internal VFX workstation security posture (CLAUDE.md §Security posture).

No new network endpoints, no new schema at trust boundaries, no new auth paths, no new filesystem access patterns beyond what was already reasoned in the threat register.

## TDD Gate Compliance

Plan type: `execute` (not `tdd`). TDD gate enforcement does not apply. Tasks were executed in `type="auto" tdd="false"` mode; verification is via bash-level must-haves + dynamic `--help`/`--dry-run` runs rather than RED/GREEN commits.

## Commits

| # | Hash | Scope | Message |
|---|------|-------|---------|
| 1 | `7004768` | Task 1 | feat(03-02): add > forge-bridge install section with D-09/D-10/D-11 failure handling |
| 2 | `d32bed4` | Task 2 | docs(03-02): update Done heredoc to mention bridge + add scope-boundary comment |

Both commits used `--no-verify` per the worktree-parallel-execution convention. No files deleted by either commit; only install.sh modified (wc -l: 357 → 464 across the two commits; +107 / -2 cumulative diff).

## Ready For

**Phase 4** — the E2E smoke test. Phase 4 picks up:
- BRG-01 live verification: start Flame, confirm bridge listens on `127.0.0.1:9999` within N seconds of boot
- BRG-02 live verification: kill Flame, confirm no orphan bridge process
- BRG-03 inherited: bridge binds 127.0.0.1 only (already covered by sibling-repo design; Phase 4 does the negative test)
- End-to-end v6.3 Send-to-Flame round-trip through the deployed bridge

All five Phase 3 scope items are now shipped: pinned version (D-04), source resolver (D-01), dry-run semantics (D-12), failure handling (D-09/D-10/D-11), and hook-file sanity check (D-15). Plan 03-02 closes BRG-04 (install.sh deploys forge-bridge) and produces the install-time evidence that BRG-01/02/03 are in place for Phase 4 to live-verify.

## Self-Check

**Files created:**
- FOUND: `.planning/phases/03-forge-bridge-deploy/03-02-SUMMARY.md` (this file)

**Files modified:**
- FOUND: `install.sh` (357 → 464 lines, +107 / -2 across 2 commits on top of Plan 03-01's post-wave-1 state)

**Commits:**
- FOUND: `7004768` — feat(03-02): add > forge-bridge install section with D-09/D-10/D-11 failure handling
- FOUND: `d32bed4` — docs(03-02): update Done heredoc to mention bridge + add scope-boundary comment

**Must-haves:** 15/15 PASSED (see Verification Results table above).

**Self-Check: PASSED**
