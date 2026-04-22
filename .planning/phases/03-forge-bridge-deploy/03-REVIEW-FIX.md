---
phase: 03-forge-bridge-deploy
fixed_at: 2026-04-21T22:00:00Z
review_path: .planning/phases/03-forge-bridge-deploy/03-REVIEW.md
iteration: 1
findings_in_scope: 3
fixed: 3
skipped: 0
status: all_fixed
---

# Phase 3: Code Review Fix Report

**Fixed at:** 2026-04-21
**Source review:** .planning/phases/03-forge-bridge-deploy/03-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope (Critical + Warning): 3
- Fixed: 3
- Skipped: 0

Scope for this pass was `critical_warning` — all three Warning findings were
fixed. The four Info findings (IN-01 through IN-04) are out of scope for this
pass; note that WR-02's fix incidentally reads `FORGE_BRIDGE_SOURCE_KIND`
(previously dead per IN-01), so IN-01's concern is partially addressed as a
side effect.

## Fixed Issues

### WR-01: `FORGE_BRIDGE_VERSION` interpolated into an `eval`-ed command without validation

**Files modified:** `install.sh`
**Commit:** 6a9292f
**Applied fix:** Added a strict-shape validation block right after the `err()`
helper is defined (first point in the script where we can emit a coloured
error), before arg parsing. The regex
`^v[0-9]+\.[0-9]+\.[0-9]+([-.][A-Za-z0-9]+)*$` matches `v1.3.0` and reasonable
variants (`v2.0.0-rc1`, `v1.3.0.dev1`) while rejecting shell metacharacters.
On mismatch the script emits a clear error via the existing `err()` helper
and exits 2 (matching the existing "unknown argument" exit code). Verified
that the payload `FORGE_BRIDGE_VERSION='v1.3.0"; rm -rf ~; echo "'` is
rejected cleanly. This also protects the D-10 retry-hint `printf` because
the validation runs unconditionally before any interpolation occurs.

### WR-02: `FORGE_BRIDGE_REPO` path interpolated into an `eval`-ed command

**Files modified:** `install.sh`
**Commit:** e194f48
**Applied fix:** Added `FORGE_BRIDGE_SOURCE_ARGV` (a bash argv array) alongside
the existing `FORGE_BRIDGE_SOURCE_CMD` in `_resolve_forge_bridge_source`. For
the two `local` KIND branches (explicit `FORGE_BRIDGE_REPO` and sibling
auto-detect), the function now sets both `SOURCE_ARGV=(bash "${path}/scripts/install-flame-hook.sh")`
(execution form) and `SOURCE_CMD` (display form for the dry-run "would execute"
line only). At the call site (`step "forge-bridge"` block), the invocation now
branches on `FORGE_BRIDGE_SOURCE_KIND`: `local` runs `"${FORGE_BRIDGE_SOURCE_ARGV[@]}"`,
`curl` falls back to the existing `eval "$FORGE_BRIDGE_SOURCE_CMD"` (required
because curl|bash is a shell pipeline that argv form cannot express — the
version tag in that string is now validated per WR-01, so it is no longer an
injection surface). Verified with a live test at path
`/tmp/wr02-test/evil";rm -rf nothing;echo "/scripts/` that the literal
bracketed string flows through as a single argv element (bash reports "no
such file or directory" rather than shelling out).

### WR-03: `_bridge_rm_force` emits past-tense "removed" message under `--dry-run`

**Files modified:** `install.sh`
**Commit:** 84ac649
**Applied fix:** Wrapped the unconditional `ok "[forge-bridge] --force: removed
existing ..."` in `if (( ! DRY_RUN )); then ... fi` so the confirmation only
fires on real runs. Under `--dry-run --force`, the user now sees the `[dry] rm
-f ...` line from the `run` wrapper but no misleading "removed" follow-up.
Added an inline comment referencing D-12 and WR-03 so the suppression logic
is self-documenting.

## Verification

Full end-to-end checks after all three commits applied:

- `bash -n install.sh` — parses cleanly
- `./install.sh --help` — exits 0
- `./install.sh --dry-run` — runs end-to-end, D-12 contract intact (no curl,
  no shell-out, no `/opt/Autodesk/` mutation)
- `./install.sh --dry-run --force` — runs end-to-end, no misleading "removed"
  message post-dry-rm
- `FORGE_BRIDGE_VERSION='bad tag with spaces' ./install.sh --help` — rejected
  with clear error, exit 2
- Injection payload `'v1.3.0"; rm -rf ~; echo "'` rejected at validation step
- Argv-array form verified to pass evil paths as literal argv elements (no
  shell reparsing)
- D-07 section order preserved (`> forge-bridge` before `> Install`)
- D-09/D-10/D-11 failure contract preserved (code paths untouched)

## Skipped Issues

None.

---

_Fixed: 2026-04-21_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
