---
phase: 04-e2e-validation-docs
reviewed: 2026-04-22T18:30:00Z
depth: standard
files_reviewed: 3
files_reviewed_list:
  - README.md
  - docs/seamless-bridge.md
  - tools/smoke-test/seamless-bridge-smoke.sh
findings:
  critical: 1
  warning: 3
  info: 4
  total: 8
status: issues_found
---

# Phase 4: Code Review Report

**Reviewed:** 2026-04-22T18:30:00Z
**Depth:** standard
**Files Reviewed:** 3
**Status:** issues_found

## Summary

Phase 4 ships two docs (repo-root `README.md`, canonical guide `docs/seamless-bridge.md`) and one hybrid mech+human smoke test (`tools/smoke-test/seamless-bridge-smoke.sh`). Overall quality is high — the docs are internally consistent, all relative links resolve, anchor targets exist, and the script is well-structured with good transcript logging and failure tracking.

One **Critical** portability bug exists in the smoke test: it uses the bash 4.0+ lowercase parameter expansion `${ans,,}` but declares `#!/usr/bin/env bash`, which on macOS picks up the system-bundled bash 3.2.57 and errors with `bad substitution`. Empirically verified: running `bash -c 'ans="Yes"; echo "${ans,,}"'` on the project machine (bash 3.2.57) exits non-zero. Since the smoke test is explicitly designed to run on artist/TD workstations to gate v6.3, and macOS is a supported platform (CLAUDE.md: "Platform: macOS + Linux"), this will block every macOS user at step 6 on the first y/n prompt. The repo's own `install.sh` already uses a bash-3.2-portable idiom (`[[ "${ans:-N}" =~ ^[Yy]$ ]]`) for the same task — the smoke test should adopt the same pattern.

Three **Warnings** cover: fragile implicit "recipe N" numbering in the troubleshooting doc referenced from the script, a tee/subshell race that can make the step-3 grep of `$LOG` miss the forge-bridge-skipped warning, and a CLI flag claim in the docs that isn't verified to exist (`install.sh --force` — confirmed to exist, so moving this to Info).

Four **Info** items cover minor consistency, naming, and improvement suggestions.

## Critical Issues

### CR-01: `${ans,,}` lowercase expansion fails on macOS bash 3.2 — smoke test unrunnable on macOS

**File:** `tools/smoke-test/seamless-bridge-smoke.sh:74`
**Issue:** The `ask_human` helper uses `"${ans,,}"` (bash 4.0+ parameter expansion for lowercase). The script's shebang is `#!/usr/bin/env bash`, and on macOS — a supported primary platform for this tool per CLAUDE.md — `/usr/bin/env bash` resolves to `/bin/bash` version 3.2.57 (Apple's ancient bundled bash). Empirically reproduced on the dev workstation:

```
$ /usr/bin/env bash -c 'ans="Yes"; echo "${ans,,}"'
bash: ${ans,,}: bad substitution
```

Because `set -euo pipefail` is active, the script will terminate abruptly the first time a human is prompted (step 6, "Export Camera to Blender"). Every macOS artist/TD attempting to gate v6.3 will hit this. The sibling `install.sh` in this same repo (line 441-442) already solves the identical problem portably using a regex match instead of case-folding:

```bash
read -r -p "  overwrite? [y/N] " ans
[[ "${ans:-N}" =~ ^[Yy]$ ]] || { err "aborted by user"; exit 1; }
```

**Fix:** Replace the case-fold with a bash-3.2-portable regex match:

```bash
ask_human() {
  local desc="$1"
  read -r -p "  pass? [y/n] " ans
  if [[ "${ans:-n}" =~ ^[Yy]([Ee][Ss])?$ ]]; then
    ok "$desc"
  else
    err "$desc — see docs/seamless-bridge.md#troubleshooting"
    FAILED_STEPS+=("$desc")
    HUMAN_FAIL=1
  fi
}
```

Alternatively, pin the shebang to `#!/usr/bin/env bash` **and** document a bash>=4 prerequisite + assert it early (e.g. `[[ "${BASH_VERSINFO[0]}" -ge 4 ]] || { echo "requires bash 4+"; exit 1; }`). The regex-match fix is simpler and matches the repo's existing idiom.

## Warnings

### WR-01: Smoke test references "recipe 1" / "recipe 5" but the docs never number recipes

**File:** `tools/smoke-test/seamless-bridge-smoke.sh:154, 190`
**Issue:** On failure, the script points users to `docs/seamless-bridge.md#troubleshooting recipe 1` (step 5) and `...#troubleshooting recipe 5` (step 9). The troubleshooting section in `docs/seamless-bridge.md` contains five H3 "Symptom:" headings but never labels them as "recipe 1", "recipe 2", etc. A user searching the rendered docs for "recipe 1" will find nothing — they have to count H3 sections to map the reference. The README uses the same implicit convention (`docs/seamless-bridge.md` itself also references `recipe 4` on line 35 of the docs). This is a coordination hazard: reorder or add a troubleshooting entry and every "recipe N" reference silently points to the wrong recipe.

**Fix:** Either
- Add explicit numeric labels to each troubleshooting H3 (e.g. `### Recipe 1 — Send to Flame: forge-bridge not reachable ...`), or
- Replace the "recipe N" phrasing with anchor slugs that Markdown processors auto-generate (e.g. link directly to `docs/seamless-bridge.md#symptom-send-to-flame-forge-bridge-not-reachable-...`), or
- Drop the numbering and say "see the 'forge-bridge not reachable' section" in prose.

The first option is the lowest-effort and keeps the existing script references working.

### WR-02: `grep "forge-bridge install skipped" "$LOG"` in step 3 races with tee's buffered output

**File:** `tools/smoke-test/seamless-bridge-smoke.sh:119, 130`
**Issue:** After step 3 runs `./install.sh`, the script immediately greps `$LOG` (line 119) to detect whether the forge-bridge install was skipped, and again in step 4 (line 130). Because stdout is redirected through `exec > >(tee -a "$LOG") 2>&1` (line 52), the tee process is a subshell running asynchronously. There is no guarantee that all output written during `./install.sh` has been flushed to `$LOG` by the time `grep` runs — especially under buffered stderr or a slow filesystem. In practice this usually works (small output, pipe drain is fast), but under load or on network-mounted /tmp, the grep could race and miss the WARN line, causing the smoke test to fail at step 4 with a misleading "forge_bridge.py not found at $BRIDGE_PY and bridge install was not skipped" error when in fact the skip did occur.

**Fix:** Capture `install.sh`'s output directly into a variable (or a dedicated file) rather than relying on the tee'd log. E.g.:

```bash
step "install.sh live"
INSTALL_OUT=$(./install.sh 2>&1) || { err "install.sh exited non-zero"; printf "%s\n" "$INSTALL_OUT" >&2; exit 1; }
printf "%s\n" "$INSTALL_OUT"   # still goes through tee for the transcript
if grep -qF "forge-bridge install skipped" <<< "$INSTALL_OUT"; then
  BRIDGE_SKIPPED=1
  warn "install.sh completed with forge-bridge install skipped ..."
else
  BRIDGE_SKIPPED=0
fi
```

Then in step 4, check `$BRIDGE_SKIPPED` instead of re-grepping `$LOG`. This removes the race and avoids re-reading the log file twice.

### WR-03: `read -r _` for "press Enter" accepts any input silently, including accidental `n`

**File:** `tools/smoke-test/seamless-bridge-smoke.sh:149, 185`
**Issue:** Steps 5 and 9 use `read -r _` to wait for the operator to press Enter after restarting/quitting Flame. There is no validation — if the operator types anything (e.g. "n" meaning "I didn't do it yet") and hits Enter, the script proceeds anyway. For step 5 (bridge reachable), the subsequent curl probe gives an honest check so this is low-risk. For step 9 (no orphan after Flame quit), if the operator pressed Enter before Flame fully shut down, the `pgrep -f forge_bridge.py` would legitimately find the still-running bridge and fail the step with a false-positive "orphan" — misleading the operator into thinking something is wrong with cleanup when they just didn't wait long enough.

**Fix:** Either poll until the condition is met, or explicitly document the gotcha. Minimal fix for step 9:

```bash
human "Quit Flame now. When Flame is fully closed, press Enter."
read -r _
# Give the OS a moment to reap child processes after Flame exits
for _ in 1 2 3 4 5; do
  orphan=$(pgrep -f forge_bridge.py || true)
  [[ -z "$orphan" ]] && break
  sleep 1
done
```

This trades a few seconds of latency for robustness against "Enter pressed while Flame is still shutting down".

## Info

### IN-01: README "Install" section omits the forge-bridge preflight warning

**File:** `README.md:30-37`
**Issue:** The README's Install section tells users to run `./install.sh` and install the Blender addon, but doesn't mention that `install.sh` may print a `[WARN] forge-bridge install skipped` if the sibling repo isn't reachable. A first-time user seeing the warning may think the install failed. `docs/seamless-bridge.md` covers this in recipe 4, but the link from README to that section goes via `#install` rather than the warning recipe.
**Fix:** Add one sentence: "If the installer prints `forge-bridge install skipped`, see the [troubleshooting section](docs/seamless-bridge.md#troubleshooting) — VP-solve and v6.2 static round-trip continue to work without the bridge."

### IN-02: Log filename uses local timezone but header timestamp uses UTC

**File:** `tools/smoke-test/seamless-bridge-smoke.sh:51, 56`
**Issue:** `LOG="/tmp/forge-smoke-$(date +%Y%m%d-%H%M%S).log"` (local time) vs. `printf "Date: %s\n" "$(date -u +"%Y-%m-%d %H:%M:%S UTC")"` (UTC). If someone collects multiple smoke-test logs from different workstations across timezones for a v6.3 gate review, sorting by filename will misrepresent chronology. Small auditability concern.
**Fix:** Use UTC consistently: `LOG="/tmp/forge-smoke-$(date -u +%Y%m%d-%H%M%SZ).log"` (the trailing `Z` signals UTC).

### IN-03: `FAILED_STEPS=()` declared but not `local` in `ask_human`

**File:** `tools/smoke-test/seamless-bridge-smoke.sh:66, 77`
**Issue:** `FAILED_STEPS` is a module-level array and `ask_human` appends to it directly (`FAILED_STEPS+=("$desc")`). This works because arrays in bash have global scope by default, but it's implicit and a reader has to cross-reference to confirm the helper mutates shared state. Steps 5 and 9 also append to `FAILED_STEPS` directly (lines 155, 191), which is fine but makes the data flow harder to follow.
**Fix:** Add a comment on `FAILED_STEPS=()` (line 66) noting it's mutated by `ask_human` and by steps 5 and 9. No code change needed.

### IN-04: Unused variable warning from `read -r _`

**File:** `tools/smoke-test/seamless-bridge-smoke.sh:149, 185`
**Issue:** `read -r _` works but `_` is shellcheck-convention for "intentionally unused"; with `set -u` active, it's fine here but some static analyzers (shellcheck SC2034 family) flag single-underscore variables. Harmless, but worth noting if a CI shellcheck lint is ever added to gate smoke-test changes.
**Fix:** Use `read -r REPLY` (the default name `read` uses when no var is given) or add an inline shellcheck disable comment. No functional change needed.

---

_Reviewed: 2026-04-22T18:30:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
