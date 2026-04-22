#!/usr/bin/env bash
set -euo pipefail
# E2E smoke test for the seamless Flame↔Blender bridge (v6.3). Closes DOC-01.
#
# What this is:
#   A hybrid shell-script + inline human checklist that serves as the
#   authoritative gate for cutting v6.3. The script mechanizes what can be
#   automated (working-tree check, install dry-run + live, forge_bridge.py
#   syntax, curl bridge probe, pgrep orphan check, pytest) and prompts the
#   operator inline for the Flame/Blender interactive steps.
#
# Usage:
#   ./tools/smoke-test/seamless-bridge-smoke.sh   (run from repo root)
#
# Steps:
#   1. [mech]  Working-tree clean
#   2. [mech]  install.sh dry-run
#   3. [mech]  install.sh live
#   4. [mech]  forge_bridge.py sanity (ast.parse)
#   5. [human+mech] Bridge reachable after Flame boot (curl 200)
#   6. [human] Export Camera to Blender
#   7. [human] Send to Flame
#   8. [human] Camera appears in target Action
#   9. [human+mech] No orphan bridge after Flame quit (pgrep)
#  10. [mech]  pytest
#
# Output:
#   Full transcript tee'd to /tmp/forge-smoke-YYYYMMDD-HHMMSS.log
#   (git rev + timestamp in the header for audit provenance)
#
# Exit codes:
#   0  all 10 steps passed (every [mech] succeeded and every [human] answered y)
#   1  any [mech] failure OR any [human] step answered n
#
# Non-destructive: does not touch ~/forge-bakes/, /opt/Autodesk/, or require
# --force. Safe to re-run on an already-installed workstation.

# ---- colour helpers (only if stdout is a tty) ---------------------------------
if [[ -t 1 ]]; then
  C_OK=$'\033[32m' C_WARN=$'\033[33m' C_ERR=$'\033[31m' C_DIM=$'\033[2m' C_END=$'\033[0m'
else
  C_OK="" C_WARN="" C_ERR="" C_DIM="" C_END=""
fi
ok()    { printf "  %s✓%s %s\n" "$C_OK"   "$C_END" "$*"; }
warn()  { printf "  %s!%s %s\n" "$C_WARN" "$C_END" "$*"; }
err()   { printf "  %s✗%s %s\n" "$C_ERR"  "$C_END" "$*" >&2; }
step()  { printf "\n%s>%s %s\n" "$C_DIM"  "$C_END" "$*"; }
human() { printf "\n  %s[HUMAN]%s %s\n" "$C_WARN" "$C_END" "$*"; }

# ---- transcript logging (D-05) ------------------------------------------------
LOG="/tmp/forge-smoke-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee -a "$LOG") 2>&1

# ---- log header (D-Claude's-Discretion item 6) --------------------------------
printf "\n=== forge-calibrator seamless-bridge smoke test ===\n"
printf "Date:       %s\n" "$(date -u +"%Y-%m-%d %H:%M:%S UTC")"
printf "Log:        %s\n" "$LOG"
printf "Host:       %s\n" "$(uname -n)"
printf "OS:         %s\n" "$(uname -s -r)"
printf "Git rev:    %s\n" "$(git rev-parse HEAD 2>/dev/null || echo unknown)"
printf "Git desc:   %s\n" "$(git describe --tags 2>/dev/null || echo unknown)"
printf "====================================================\n\n"

# ---- failure-tracking globals -------------------------------------------------
HUMAN_FAIL=0
FAILED_STEPS=()

# ---- helper: ask_human "description" ------------------------------------------
# Encapsulates the y/n prompt idiom (D-Claude's-Discretion item 4).
# On y/yes: ok. On anything else: err, append to FAILED_STEPS, set HUMAN_FAIL=1.
ask_human() {
  local desc="$1"
  read -r -p "  pass? [y/n] " ans
  # Bash 3.2-portable case-insensitive match (macOS ships bash 3.2; ${var,,} is bash 4+)
  case "$ans" in
    [Yy]|[Yy][Ee][Ss]) ok "$desc" ;;
    *)                 err "$desc — see docs/seamless-bridge.md#troubleshooting"
                       FAILED_STEPS+=("$desc")
                       HUMAN_FAIL=1 ;;
  esac
}

# All steps are idempotent + non-destructive (D-04).

# ==============================================================================
# Step 1: Working-tree clean [mech]
# ==============================================================================
step "Working-tree clean"
dirty=$(git status --porcelain 2>/dev/null \
  | grep -v '^.. \.claude/' \
  | grep -v '^.. \.planning/phases/04-e2e-validation-docs/' \
  || true)
if [[ -n "$dirty" ]]; then
  err "working tree has uncommitted changes (after ignoring .claude/ and in-phase .planning/):"
  printf "%s\n" "$dirty" >&2
  exit 1
fi
ok "working tree clean (ignoring .claude/ and in-phase .planning/)"

# ==============================================================================
# Step 2: install.sh dry-run [mech]
# ==============================================================================
step "install.sh dry-run"
if ! ./install.sh --dry-run; then
  err "install.sh --dry-run exited non-zero"
  exit 1
fi
ok "install.sh --dry-run passed"

# ==============================================================================
# Step 3: install.sh live [mech]
# ==============================================================================
step "install.sh live"
if ! ./install.sh; then
  err "install.sh exited non-zero"
  exit 1
fi
# D-10 warn-and-continue: if the forge-bridge install was skipped, record a
# warning but do not fail the step — VP-solve and v6.2 static round-trip still work.
if grep -qF "forge-bridge install skipped" "$LOG" 2>/dev/null; then
  warn "install.sh completed with forge-bridge install skipped (D-10 warn-and-continue); smoke test continues"
fi
ok "install.sh live passed"

# ==============================================================================
# Step 4: forge_bridge.py sanity [mech]
# ==============================================================================
step "forge_bridge.py sanity"
BRIDGE_PY="/opt/Autodesk/shared/python/forge_bridge/scripts/forge_bridge.py"
if [[ ! -f "$BRIDGE_PY" ]]; then
  if grep -qF "forge-bridge install skipped" "$LOG" 2>/dev/null; then
    warn "forge_bridge.py not found — forge-bridge install was skipped (D-10 warn-and-continue); skipping syntax check"
  else
    err "forge_bridge.py not found at $BRIDGE_PY and bridge install was not skipped — check install.sh output"
    exit 1
  fi
else
  if ! python3 -c "import ast, sys; ast.parse(open(sys.argv[1]).read())" "$BRIDGE_PY"; then
    err "forge_bridge.py failed Python syntax check (ast.parse)"
    exit 1
  fi
  ok "forge_bridge.py syntax check passed"
fi

# ==============================================================================
# Step 5: Bridge reachable after Flame boot [human + mech] (D-15 first half)
# ==============================================================================
step "Bridge reachable after Flame boot"
human "Restart Flame now. When the batch view is up and the Camera Match hook has loaded, press Enter."
read -r _
code=$(curl -s http://localhost:9999/ -o /dev/null -w "%{http_code}\n" || echo "000")
if [[ "$code" == "200" ]]; then
  ok "bridge reachable (HTTP $code)"
else
  err "bridge unreachable (HTTP $code) — see docs/seamless-bridge.md#troubleshooting recipe 1"
  FAILED_STEPS+=("Bridge reachable after Flame boot")
  HUMAN_FAIL=1
fi

# ==============================================================================
# Step 6: Export Camera to Blender [human]
# ==============================================================================
step "Export Camera to Blender"
human "In Flame: right-click the Action → Camera Match → Export Camera to Blender. Blender should open on the baked camera (zero dialogs)."
ask_human "Export Camera to Blender"

# ==============================================================================
# Step 7: Send to Flame [human]
# ==============================================================================
step "Send to Flame"
human "In Blender: edit the camera (move/rotate, scrub or add a keyframe). Open the N-panel (N key) → Forge tab → click 'Send to Flame'. Expect the success popup 'Sent to Flame: camera X in Action Y'."
ask_human "Send to Flame"

# ==============================================================================
# Step 8: Camera appears in target Action [human]
# ==============================================================================
step "Camera appears in target Action"
human "In Flame: verify the new camera appears in the target Action with keyframes preserved (scrub the batch timeline)."
ask_human "Camera appears in target Action"

# ==============================================================================
# Step 9: No orphan bridge after Flame quit [human + mech] (D-15 second half)
# ==============================================================================
step "No orphan bridge after Flame quit"
human "Quit Flame now. When Flame is fully closed, press Enter."
read -r _
orphan=$(pgrep -f forge_bridge.py || true)
if [[ -z "$orphan" ]]; then
  ok "no orphan forge_bridge.py process found"
else
  err "orphan forge_bridge.py process(es) still running: $orphan — see docs/seamless-bridge.md#troubleshooting recipe 5"
  FAILED_STEPS+=("No orphan bridge after Flame quit")
  HUMAN_FAIL=1
fi

# ==============================================================================
# Step 10: pytest [mech]
# ==============================================================================
step "pytest"
if ! pytest -q; then
  err "pytest -q exited non-zero"
  exit 1
fi
ok "pytest -q all tests passed"

# ==============================================================================
# Done — final exit guard
# ==============================================================================
step "Done"
if (( HUMAN_FAIL )); then
  err "smoke test FAILED — the following human-verified steps did not pass:"
  for s in "${FAILED_STEPS[@]}"; do
    err "  - $s"
  done
  err "report to the troubleshooting section of docs/seamless-bridge.md"
  err "full transcript: $LOG"
  exit 1
fi

ok "smoke test PASSED — all 10 steps green"
ok "transcript: $LOG"
exit 0
