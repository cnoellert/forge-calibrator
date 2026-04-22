---
phase: 03-forge-bridge-deploy
reviewed: 2026-04-21T00:00:00Z
depth: standard
files_reviewed: 1
files_reviewed_list:
  - install.sh
findings:
  critical: 0
  warning: 3
  info: 4
  total: 7
status: issues_found
---

# Phase 3: Code Review Report

**Reviewed:** 2026-04-21
**Depth:** standard
**Files Reviewed:** 1
**Status:** issues_found

## Summary

Phase 3 adds forge-bridge deployment to `install.sh` via a new `> forge-bridge`
section, two helpers (`_resolve_forge_bridge_source`, `_bridge_rm_force`), two
env vars (`FORGE_BRIDGE_VERSION`, `FORGE_BRIDGE_REPO`), and a D-15 `ast.parse`
sanity check. The implementation follows the documented D-09/D-10/D-11 exit-code
contract correctly — bridge failure is non-fatal, the warning copy is emitted
verbatim as a single `printf` paragraph to stderr, and the dry-run guard reaches
both the sibling-installer invocation and the post-install sanity check.

The main concerns are shell-injection hazards introduced by the pre-existing
`run() { eval "$*"; }` pattern being extended to two new env-var-influenced
call sites. These are low-exploitability in a single-user VFX workstation
context (the user can already run arbitrary shell), but the pattern is still
worth flagging because this is root-adjacent code dropping files into
`/opt/Autodesk/shared/python/`, and a pasted env var from a tutorial or a
dotfile typo could produce a confusing `eval` failure mode. Two cosmetic
dry-run issues and one dead variable round out the findings. No bugs in the
D-09/D-10/D-11 exit-code logic, no secrets, no path traversal.

## Warnings

### WR-01: `FORGE_BRIDGE_VERSION` interpolated into an `eval`-ed command without validation

**File:** `install.sh:170`
**Issue:** The curl-fallback branch stores the pinned tag in `FORGE_BRIDGE_SOURCE_CMD`
by direct string interpolation, then the install step runs `eval "$FORGE_BRIDGE_SOURCE_CMD"`
(line 326). If a user sets `FORGE_BRIDGE_VERSION='v1.3.0"; rm -rf ~; echo "'`
(copy-paste error, malicious dotfile, CI misconfig, etc.), the command breaks
out of the curl URL and executes arbitrary shell. The same unvalidated value
is also interpolated into the D-10 retry-hint copy (line 366), so the printed
"retry" command a user sees after a failure is also corruptible. Exploitability
is low in a single-user VFX workstation, but the installer is advertised as
root-adjacent ("drops files into /opt/Autodesk/shared/python/") and the trust
boundary is worth hardening.
**Fix:** Validate the tag shape before use. Git tags for forge-bridge follow
`vN.N.N` — a tight regex catches everything else:
```bash
if [[ ! "$FORGE_BRIDGE_VERSION" =~ ^v[0-9]+\.[0-9]+\.[0-9]+([-.][A-Za-z0-9]+)*$ ]]; then
  err "FORGE_BRIDGE_VERSION=${FORGE_BRIDGE_VERSION} is not a valid semver tag (expected vN.N.N)"
  exit 2
fi
```
Place this at the top of `_resolve_forge_bridge_source` before the curl branch
(or unconditionally right after the env-var read on line 60, which also
protects the D-10 printf copy).

### WR-02: `FORGE_BRIDGE_REPO` path interpolated into an `eval`-ed command

**File:** `install.sh:134`
**Issue:** `FORGE_BRIDGE_SOURCE_CMD="bash \"${FORGE_BRIDGE_REPO}/scripts/install-flame-hook.sh\""`
embeds a user-supplied absolute path inside double quotes that are then re-parsed
by `eval` at line 326. A path like `/tmp/x";rm -rf ~;echo "` escapes the quote
boundary — the `[[ -f … ]]` check passes because bash test `-f` does not care
about embedded quotes, but `eval` does. Same low-exploitability caveat as WR-01,
same pattern. The auto-detect branch at line 156 uses hardcoded candidates, so
it is not exposed.
**Fix:** Use `printf -v` / array-based invocation instead of `eval`:
```bash
# In _resolve_forge_bridge_source:
FORGE_BRIDGE_SOURCE_ARGV=(bash "${FORGE_BRIDGE_REPO}/scripts/install-flame-hook.sh")
# In the install block (line 326), replace `eval "$FORGE_BRIDGE_SOURCE_CMD"` with:
if "${FORGE_BRIDGE_SOURCE_ARGV[@]}"; then
```
For the curl branch, you can still keep a string (since the curl URL is controlled
by you once WR-01's validation is in place) and switch on `FORGE_BRIDGE_SOURCE_KIND`
to pick the invocation style. This also retires the only `eval` the Phase 3
code added, which is good defense-in-depth.

### WR-03: `_bridge_rm_force` emits past-tense "removed" message under `--dry-run`

**File:** `install.sh:179-186`
**Issue:** The `rm -f` itself goes through `run` which honours `DRY_RUN` (so no
actual mutation leaks — good). But the subsequent unconditional
`ok "[forge-bridge] --force: removed existing ${FORGE_BRIDGE_HOOK_PATH}"` at
line 183 fires whether or not the `rm` actually happened. Under
`./install.sh --dry-run --force`, the terminal shows:
```
    [dry] rm -f "/opt/Autodesk/shared/python/forge_bridge/scripts/forge_bridge.py"
  ✓ [forge-bridge] --force: removed existing /opt/…/forge_bridge.py
```
which reads as a success message for a no-op. This contradicts the D-12 contract
("dry-run prints what would execute and skips"). It is cosmetic — no file was
actually removed — but it is misleading for an installer where dry-run accuracy
is the whole point.
**Fix:** Suppress or reword the `ok` under dry-run:
```bash
_bridge_rm_force() {
  if (( FORCE )); then
    if [[ -f "${FORGE_BRIDGE_HOOK_PATH}" ]]; then
      run "rm -f \"${FORGE_BRIDGE_HOOK_PATH}\""
      if (( ! DRY_RUN )); then
        ok "[forge-bridge] --force: removed existing ${FORGE_BRIDGE_HOOK_PATH}"
      fi
    fi
  fi
}
```

## Info

### IN-01: `FORGE_BRIDGE_SOURCE_KIND` is set but never read

**File:** `install.sh:133, 155, 169`
**Issue:** All three branches of `_resolve_forge_bridge_source` assign
`FORGE_BRIDGE_SOURCE_KIND` ("local" / "local" / "curl"), but the variable is
never read anywhere else in the script. The function's docstring (lines 117-118)
advertises it as part of the contract. Either it is dead code, or a planned
consumer was dropped during plan 03-02 execution.
**Fix:** Either delete the three assignments (and drop the docstring line), or
use it — e.g. to drive the WR-02 array-vs-string branching, or to label the
`[forge-bridge] installed at …` success line with the source kind.

### IN-02: D-15 ast.parse failure mode misattributes missing `python3`

**File:** `install.sh:343-346`
**Issue:** The check `python3 -c "import ast, sys; ast.parse(...)" 2>&1` runs
unconditionally after a successful sibling-install. If `python3` is not on PATH
(unusual on a Flame host, but not impossible in a stripped container or a CI
sandbox), the shell exits non-zero and `BRIDGE_FAIL_REASON` gets set to
"hook at … failed python3 ast.parse sanity check" — but the real cause is a
missing interpreter, not a malformed hook. The D-10 warning copy the user sees
would then tell them to re-run the install, which will fail again for the
same reason.
**Fix:** Guard the call site so the failure is self-describing:
```bash
if ! command -v python3 >/dev/null 2>&1; then
  BRIDGE_OK=0
  BRIDGE_FAIL_REASON="python3 not on PATH — cannot run D-15 ast.parse sanity check"
elif ! python3 -c "import ast, sys; ast.parse(open(sys.argv[1]).read())" "$FORGE_BRIDGE_HOOK_PATH" >/dev/null 2>&1; then
  BRIDGE_OK=0
  BRIDGE_FAIL_REASON="hook at $FORGE_BRIDGE_HOOK_PATH failed python3 ast.parse sanity check"
fi
```

### IN-03: D-10 warning copy hardcodes the FORGE_BRIDGE_VERSION into the retry URL even when the local-clone path failed

**File:** `install.sh:365-366`
**Issue:** If the failure reason was "sibling installer exited non-zero" while
installing from a local `FORGE_BRIDGE_REPO`, the retry hint still points at
the GitHub URL for the pinned tag. A user who was deliberately testing a
local clone will be confused about why the retry switches to curl.
**Fix:** Low-priority; swap the retry hint based on `FORGE_BRIDGE_SOURCE_KIND`
(see IN-01 — one more reason to actually use it):
```bash
if [[ "${FORGE_BRIDGE_SOURCE_KIND:-}" == "local" ]]; then
  retry_hint="FORGE_BRIDGE_REPO=<path> ./install.sh"
else
  retry_hint="curl -fsSL https://raw.githubusercontent.com/cnoellert/forge-bridge/${FORGE_BRIDGE_VERSION}/scripts/install-flame-hook.sh | bash"
fi
```
Skipping this is fine — the D-10 copy is contractual and both retry options
are already listed.

### IN-04: `_resolve_forge_bridge_source` runs `git describe` on every invocation

**File:** `install.sh:138, 159`
**Issue:** The `git -C "$path" describe --tags --always --dirty` call is a
harmless read (so no `--dry-run` leak), but it runs against the caller's
sibling clone every run, which on a shallow clone or a CI checkout can emit
a surprising stderr message. You already redirect `2>/dev/null`, so noise is
suppressed. Purely a style note — the `ok`/`warn` line emitted here is useful
diagnostic context and worth keeping. No fix needed; flagged so future readers
know it is intentional.

---

_Reviewed: 2026-04-21_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
