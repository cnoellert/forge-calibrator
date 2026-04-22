---
phase: 03-forge-bridge-deploy
plan: 01
subsystem: install
tags: [install, bash, forge-bridge, env-vars, helpers, dry-run, force]
requirements_addressed: [BRG-04]
dependency_graph:
  requires: []
  provides:
    - "install.sh constants: FORGE_BRIDGE_VERSION, FORGE_BRIDGE_REPO, FORGE_BRIDGE_HOOK_PATH"
    - "install.sh helpers: _resolve_forge_bridge_source(), _bridge_rm_force()"
    - "install.sh --help surfaces FORGE_BRIDGE_VERSION / FORGE_BRIDGE_REPO / FORGE_ENV env vars"
  affects:
    - "Plan 03-02 (bridge install step — consumes these primitives)"
tech_stack:
  added: []
  patterns:
    - "env-override-then-default (${VAR:-default}) extended to two new bridge env vars"
    - "Comment-block + section-marker convention preserved for new helper fns"
    - "Top-of-file docstring + sed-slice --help pattern preserved (slice widened 3,23p → 3,29p)"
key_files:
  created: []
  modified:
    - install.sh
decisions:
  - "D-01: three-tier source priority (FORGE_BRIDGE_REPO env > sibling auto-detect > curl fallback) encoded in _resolve_forge_bridge_source"
  - "D-02: env var named FORGE_BRIDGE_REPO (not FORGE_BRIDGE_LOCAL) for symmetry with FORGE_BRIDGE_VERSION"
  - "D-03: both source paths print explicit info line (`[forge-bridge] using local clone at …` / `[forge-bridge] fetching … from GitHub`)"
  - "D-04: FORGE_BRIDGE_VERSION pinned to v1.3.0 (confirmed 2026-04-21 as current sibling-repo tag)"
  - "D-05: curl fallback pipes FORGE_BRIDGE_VERSION through to sibling bash invocation so pin is honoured"
  - "D-06: local-clone path prints `git describe --tags --always --dirty` output so pin-vs-clone drift is visible"
  - "D-08: Environment overrides block added to top-of-file docstring; sed slice widened 3,23p → 3,29p"
  - "D-13: _bridge_rm_force() explicit rm of FORGE_BRIDGE_HOOK_PATH under --force documents intent"
metrics:
  duration: "2m"
  completed: "2026-04-22"
  tasks: 2
  files_modified: 1
  loc_delta: "+108 / -1"
  tests_added: 0
  commits: 2
---

# Phase 3 Plan 01: install.sh forge-bridge plumbing — Summary

**One-liner:** Added forge-bridge constants (v1.3.0 version pin, FORGE_BRIDGE_REPO env override), source-resolver + --force helper functions, and --help docstring wiring to `install.sh` — pure primitives with zero runtime behavior change (Plan 03-02 consumes them).

## What Landed

### Task 1 — constants + docstring (commit `052bd51`)

**File: `install.sh`**

1. **Top-of-file docstring extension** (new lines 21–28):
   - Inserted "Environment overrides" block after the `Usage:` section documenting `FORGE_BRIDGE_VERSION` (default `v1.3.0`), `FORGE_BRIDGE_REPO` (path to local clone), and `FORGE_ENV` (existing, re-documented for discoverability).
   - Preserved the leading `# ` on each comment line so the existing `sed 's/^# \{0,1\}//'` help-stripper keeps working. Added a trailing `#` padding line at line 28 to preserve the convention of ending the docstring one line before `set -euo pipefail`.

2. **Widened --help sed slice** (line 93): `sed -n '3,23p'` → `sed -n '3,29p'`. Upper bound extended by 6 to cover the 6 new docstring lines (22–27) plus the trailing `#` padding (28) plus the blank line (29). Verified via `./install.sh --help` that all three env vars surface in output.

3. **forge-bridge constants block** (new lines 54–70, inserted after `FLAME_PYOCIO_GLOB=…` and before `DRY_RUN=0`):
   ```
   FORGE_BRIDGE_VERSION="${FORGE_BRIDGE_VERSION:-v1.3.0}"   # D-04
   FORGE_BRIDGE_REPO="${FORGE_BRIDGE_REPO:-}"                # D-02
   FORGE_BRIDGE_HOOK_PATH="/opt/Autodesk/shared/python/forge_bridge/scripts/forge_bridge.py"  # D-13
   ```
   All three use the existing `${VAR:-default}` convention so `set -u` stays happy.

**Diff:** +27 insertions / -1 deletion (sed slice edit). One line above the plan's `~25 added lines` guideline because the comment-heavy constants block is deliberately verbose per the plan's own code examples — every constant carries its rationale + D-XX anchor inline for future reviewers.

### Task 2 — helper functions (commit `f0906ed`)

**File: `install.sh`**

Added two helper functions immediately after the existing `run()` function (new lines 107–189):

1. **`_resolve_forge_bridge_source()`** (lines 108–174) — implements D-01 + D-03 + D-05 + D-06:
   - Priority 1: Honour `FORGE_BRIDGE_REPO` env var if set and the clone contains `scripts/install-flame-hook.sh`; fall through with a warn if the path is set but invalid.
   - Priority 2: Sibling-clone auto-detect across `${REPO_ROOT}/../forge-bridge`, `$HOME/Documents/GitHub/forge-bridge`, `$HOME/code/forge-bridge` — first hit wins.
   - Priority 3: Curl fallback; command string pipes `FORGE_BRIDGE_VERSION=${FORGE_BRIDGE_VERSION}` through to the sibling's bash invocation so the pin is preserved (D-05 — without this, the sibling installer silently defaults to its internal `v1.1.0`).
   - Sets two globals for Plan 03-02's consumption: `FORGE_BRIDGE_SOURCE_KIND` (`local` | `curl`) and `FORGE_BRIDGE_SOURCE_CMD` (the bash command string).
   - Prints D-03 info copy verbatim on both local and curl paths.
   - For local paths, prints `git describe --tags --always --dirty` output as a "local clone version" line (D-06), with a warn fallback if `git describe` fails (e.g., shallow clone).

2. **`_bridge_rm_force()`** (lines 177–186) — implements D-13:
   - Under `--force`, explicit `rm -f "${FORGE_BRIDGE_HOOK_PATH}"` if the hook already exists.
   - Uses `run` so `--dry-run` auto-propagates.
   - Plain `cp` in the sibling installer would overwrite anyway; the explicit `rm` documents intent in install.sh itself for anyone reviewing the --force semantics.

**Behavioral invariance:** Both helpers are defined but NEVER called from any existing code path. `grep -nE '_resolve_forge_bridge_source|_bridge_rm_force' install.sh` returned zero call sites outside the function definitions themselves. Plan 03-02 is the sole consumer.

**Diff:** +81 insertions / -0 deletions (helpers + comment blocks only).

## Verification Results

All 14 must-haves from the plan's `<verification>` section passed:

| # | Check | Result |
|---|-------|--------|
| 1 | `bash -n install.sh` | OK |
| 2 | `FORGE_BRIDGE_VERSION="${FORGE_BRIDGE_VERSION:-v1.3.0}"` present | OK |
| 3 | `FORGE_BRIDGE_REPO="${FORGE_BRIDGE_REPO:-}"` present | OK |
| 4 | `FORGE_BRIDGE_HOOK_PATH=…` present | OK |
| 5 | `_resolve_forge_bridge_source() {` defined | OK |
| 6 | `_bridge_rm_force() {` defined | OK |
| 7 | `FORGE_BRIDGE_VERSION=${FORGE_BRIDGE_VERSION} bash` in curl cmd (D-05) | OK |
| 8 | `[forge-bridge] using local clone at` print (D-03) | OK |
| 9 | `[forge-bridge] fetching ${FORGE_BRIDGE_VERSION} from GitHub` print (D-03) | OK |
| 10 | `[forge-bridge] local clone version:` print (D-06) | OK |
| 11 | `--help` surfaces `FORGE_BRIDGE_VERSION` | OK |
| 12 | `--help` surfaces `FORGE_BRIDGE_REPO` | OK |
| 13 | `--help` surfaces `FORGE_ENV` (belt-and-suspenders sed-slice check) | OK |
| 14 | `./install.sh --help` exits 0 | OK |

### Behavioral invariance (critical)

Ran `./install.sh --dry-run` on the agent's worktree. Output contains EVERY pre-plan section marker in the expected order with NO new `[forge-bridge]` lines — the helpers are defined but unreferenced, so runtime behavior is byte-for-byte identical to the baseline:

- `> Source` — present, unchanged
- `> Forge conda env` — present, unchanged
- `> Wiretap single-frame reader` — present, unchanged
- `> PyOpenColorIO (from Flame's bundled Python)` — present, unchanged
- `> OCIO config (aces2.0_config)` — present, unchanged
- `> Install` — present, unchanged
- `> forge_core + forge_flame` — present, unchanged
- `> Done` — present, unchanged (with the same "Next steps" reload snippet)

Zero `[forge-bridge]` lines in the output — confirms helpers are idle. Plan 03-02 wires them in.

## Decisions Implemented

| D-XX | Where | How |
|------|-------|-----|
| D-01 | `_resolve_forge_bridge_source()` | Three-tier priority loop: FORGE_BRIDGE_REPO override → sibling auto-detect (3 paths) → curl fallback |
| D-02 | constants block + docstring | Env var named `FORGE_BRIDGE_REPO` (path to clone), symmetric with `FORGE_BRIDGE_VERSION` |
| D-03 | `_resolve_forge_bridge_source()` prints | `[forge-bridge] using local clone at {path}` on local path; `[forge-bridge] fetching {VERSION} from GitHub` on curl path |
| D-04 | `FORGE_BRIDGE_VERSION="${FORGE_BRIDGE_VERSION:-v1.3.0}"` | v1.3.0 pinned as constant, inline comment documents the 2026-04-21 confirmation + upgrade-is-code-change policy |
| D-05 | curl cmd string | `… \| FORGE_BRIDGE_VERSION=${FORGE_BRIDGE_VERSION} bash` — pin propagates to sibling installer's env read |
| D-06 | `_resolve_forge_bridge_source()` local path | `git describe --tags --always --dirty` output printed as `[forge-bridge] local clone version: {ref}` with warn fallback |
| D-08 | top-of-file docstring + sed slice widening | Environment overrides block added; sed `3,23p` → `3,29p` |
| D-12 | `_bridge_rm_force()` via `run` wrapper | Dry-run auto-propagates because `run "rm -f …"` honours `DRY_RUN=1`; the resolver itself is read-only (no mutations) so needs no `run` wrapper |
| D-13 | `_bridge_rm_force()` | Explicit `rm -f "${FORGE_BRIDGE_HOOK_PATH}"` when `FORCE=1` makes --force intent readable in install.sh itself |

D-07, D-09, D-10, D-11, D-14, D-15 apply to Plan 03-02's install step — not implemented here.

## Deviations from Plan

### [Rule 3 - Sed-slice arithmetic crosscheck] No deviation; plan's math was correct after re-verification.

- **Found during:** Task 1 before committing.
- **Issue:** The plan instructed widening `sed -n '3,23p'` to `sed -n '3,29p'` but also cautioned to re-read install.sh and confirm line numbers hadn't shifted.
- **Check performed:** After inserting the 6-line Environment overrides block (22–27) plus the `#` padding (28), `set -euo pipefail` landed at line 30, with a blank line at 29. Upper bound of `3,29p` correctly includes the full docstring + padding, matching the original convention (slice-end-one-past-last-docstring-line = blank line before `set -euo pipefail`).
- **Fix:** None needed — plan's `3,29p` recommendation was exact.
- **Files modified:** n/a (validation, no change).

### [Rule 3 - Diff size exceeds plan guideline by 2 lines] Flagged for transparency; no action taken.

- **Found during:** Task 1 pre-commit diff review.
- **Issue:** Plan's acceptance criterion said `git diff install.sh | grep -cE '^[+-]' | head -1` should show "no more than ~25 added lines". Actual count: 30 (27 insertions + 1 deletion + 2 file-header lines for `+++`/`---`). Pure insertion count is 27 — 2 above the `~25` guideline.
- **Root cause:** The forge-bridge constants block is comment-heavy by design (every constant carries its rationale + D-XX anchor inline per the plan's own code examples). This is intentional documentation density, not scope creep.
- **Fix:** Proceeded with commit — the "~25" was a soft guideline and the excess is pure comment. Flagged here so the verifier can confirm.
- **Files modified:** n/a (intentional docstring verbosity).

**No auth gates, architectural changes, or out-of-scope discoveries** during execution. The plan was exhaustively researched in the CONTEXT gathering phase and executed 1:1.

## Known Stubs

None. The helpers are deliberately unreferenced — that's the explicit scope of this plan (plumbing only, Plan 03-02 consumes). This is not a "stub" in the sense of a hardcoded empty UI — the functions have real behavior, they just aren't invoked yet. Plan 03-02 is the caller.

## Threat Flags

None. Plan 03-01 adds constants + helpers + docstring only; it does not execute any external script, fetch remote content, or write to `/opt/Autodesk/`. All threats surfaced in the `<threat_model>` are deferred to Plan 03-02 where the helpers are actually invoked.

## Commits

| # | Hash | Scope | Message |
|---|------|-------|---------|
| 1 | `052bd51` | Task 1 | feat(03-01): add forge-bridge constants, env-var reads, --help docstring |
| 2 | `f0906ed` | Task 2 | feat(03-01): add _resolve_forge_bridge_source and _bridge_rm_force helpers |

Post-commit deletion check after both commits: zero deletions (only the 1-character sed slice edit, which is a modification not a deletion). Clean working tree after Task 2.

## Ready For

**Plan 03-02** — wire the helpers into the install flow:
- Insert `> forge-bridge` section before `> Install` (D-07 ordering).
- Call `_resolve_forge_bridge_source` → `_bridge_rm_force` → `run "${FORGE_BRIDGE_SOURCE_CMD}"` → D-15 post-install `python3 -c "ast.parse(...)"` sanity check.
- On failure, emit D-10 warning copy and continue (D-09 warn+continue semantics; D-11 exit-code-reflects-camera-match-state).
- Nothing else for 03-02 to change in install.sh's preflight / sync sections.

## Self-Check: PASSED

**Files created:**
- `FOUND: .planning/phases/03-forge-bridge-deploy/03-01-SUMMARY.md` (this file)

**Files modified:**
- `FOUND: install.sh` (253 → 359 lines, +108 / -1 across 2 commits)

**Commits:**
- `FOUND: 052bd51` — feat(03-01): add forge-bridge constants, env-var reads, --help docstring
- `FOUND: f0906ed` — feat(03-01): add _resolve_forge_bridge_source and _bridge_rm_force helpers

**Must-haves:** 14/14 PASSED (see Verification Results table above).

**Behavioral invariance:** CONFIRMED via `./install.sh --dry-run` — zero `[forge-bridge]` lines in output, all 8 pre-existing section markers unchanged.
