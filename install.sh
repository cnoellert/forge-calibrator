#!/usr/bin/env bash
# Camera Match installer for Flame.
#
# Copies the hook into Flame's shared Python tree, drops a stub __init__.py
# to stabilise the module under Flame's namespace-package loader (without it,
# Flame reloads pick up a stale module dict — see memory/flame_module_reload.md),
# then verifies the three runtime dependencies the hook expects:
#
#   1. numpy + opencv-python in the forge conda env (cv2 for drawing overlays,
#      numpy for the solver). PyOpenColorIO comes from Flame's bundled Python,
#      not forge — don't install it in forge or versions will conflict.
#   2. wiretap_rw_frame CLI — the single-frame reader that replaced PyExporter.
#   3. A shipped aces2.0_config OCIO config resolvable via glob (see
#      _resolve_ocio_config_path in camera_match_hook.py).
#
# Usage:
#   ./install.sh                  # install to /opt/Autodesk/shared/python/camera_match
#   ./install.sh --dry-run        # print actions, change nothing
#   ./install.sh --install-dir X  # override target
#   ./install.sh --force          # overwrite without prompting
#
# Environment overrides:
#   FORGE_BRIDGE_VERSION    git tag of forge-bridge to deploy (default: v1.3.0)
#   FORGE_BRIDGE_REPO       absolute path to a local forge-bridge clone; when set,
#                           install.sh uses that clone's scripts/install-flame-hook.sh
#                           instead of curl-fetching the pinned tag from GitHub
#   FORGE_ENV               conda forge env path (default: $HOME/miniconda3/envs/forge)
#

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_HOOK="$REPO_ROOT/flame/camera_match_hook.py"
SOURCE_FORGE_CORE="$REPO_ROOT/forge_core"
SOURCE_FORGE_FLAME="$REPO_ROOT/forge_flame"
SOURCE_BLENDER_SCRIPTS="$REPO_ROOT/tools/blender"

INSTALL_DIR="/opt/Autodesk/shared/python/camera_match"
# forge_core (host-agnostic) and forge_flame (Flame-specific adapters like the
# Wiretap reader) both ship as SIBLINGS of camera_match/ under /opt/Autodesk/
# shared/python/. The hook imports both by absolute path, so they must be
# importable alongside camera_match at runtime.
FORGE_CORE_DEST="/opt/Autodesk/shared/python/forge_core"
FORGE_FLAME_DEST="/opt/Autodesk/shared/python/forge_flame"
# tools/blender/ ships OUTSIDE /opt/Autodesk/shared/python/ deliberately —
# these scripts top-import bpy/mathutils, which fails under Flame's hook
# loader (the hook path is /opt/Autodesk/shared/python/). forge_flame
# .blender_bridge resolves scripts to this path at runtime (see
# _script_candidates there) so the Flame batch hook can shell out to
# bake_camera.py / extract_camera.py via `blender --background --python`.
BLENDER_SCRIPTS_DEST="/opt/Autodesk/shared/forge_blender_scripts"
FORGE_ENV="${FORGE_ENV:-$HOME/miniconda3/envs/forge}"
WIRETAP_CLI="/opt/Autodesk/wiretap/tools/current/wiretap_rw_frame"
OCIO_GLOB="/opt/Autodesk/colour_mgmt/configs/flame_configs/*/aces2.0_config/config.ocio"
FLAME_PYOCIO_GLOB="/opt/Autodesk/python/*/lib/python3.11/site-packages/PyOpenColorIO"

# ---- forge-bridge integration (Phase 3) ---------------------------------------
# Pinned forge-bridge release tag. The sibling repo at github.com/cnoellert/forge-bridge
# owns the Flame hook that auto-spawns the 127.0.0.1:9999 /exec server on Flame boot.
# Upgrading this pin is a deliberate code change + review step (per D-04). Confirmed
# current tag at time of writing: v1.3.0 (2026-04-21 — see .planning/phases/
# 03-forge-bridge-deploy/03-CONTEXT.md §D-04).
FORGE_BRIDGE_VERSION="${FORGE_BRIDGE_VERSION:-v1.3.0}"

# Optional override: absolute path to a local forge-bridge clone. When set, install.sh
# prefers this clone's scripts/install-flame-hook.sh over the curl fallback. Leaving it
# unset triggers the sibling-directory auto-detect in _resolve_forge_bridge_source below
# (per D-01 / D-02).
FORGE_BRIDGE_REPO="${FORGE_BRIDGE_REPO:-}"

# Hook's installed location — matches the forge-bridge sibling installer's default. We
# track it here so --force can explicitly rm the old file before reinstall (per D-13).
FORGE_BRIDGE_HOOK_PATH="/opt/Autodesk/shared/python/forge_bridge/scripts/forge_bridge.py"

DRY_RUN=0
FORCE=0

# ---- colour helpers (only if stdout is a tty) ---------------------------------
if [[ -t 1 ]]; then
  C_OK=$'\033[32m' C_WARN=$'\033[33m' C_ERR=$'\033[31m' C_DIM=$'\033[2m' C_END=$'\033[0m'
else
  C_OK="" C_WARN="" C_ERR="" C_DIM="" C_END=""
fi
ok()   { printf "  %s✓%s %s\n" "$C_OK"   "$C_END" "$*"; }
warn() { printf "  %s!%s %s\n" "$C_WARN" "$C_END" "$*"; }
err()  { printf "  %s✗%s %s\n" "$C_ERR"  "$C_END" "$*" >&2; }
step() { printf "\n%s>%s %s\n" "$C_DIM" "$C_END" "$*"; }

# ---- forge-bridge version validation (WR-01) ---------------------------------
# FORGE_BRIDGE_VERSION is interpolated into (a) the curl URL in
# _resolve_forge_bridge_source's fallback branch and (b) the D-10 retry-hint
# printf on failure. Both paths eventually flow through `eval` (via run()) or
# raw printf substitution, so a value like  v1.3.0"; rm -rf ~; echo "  would
# break out of the surrounding quotes. Lock the shape to a strict semver tag
# (vN.N.N optionally followed by -prerelease or .build segments) before any
# downstream code reads the variable. Intentionally placed AFTER the err()
# helper is defined and BEFORE the arg-parser / bridge section so the check
# runs on every invocation, including --help and --dry-run.
if [[ ! "${FORGE_BRIDGE_VERSION}" =~ ^v[0-9]+\.[0-9]+\.[0-9]+([-.][A-Za-z0-9]+)*$ ]]; then
  err "FORGE_BRIDGE_VERSION=${FORGE_BRIDGE_VERSION} is not a valid semver tag (expected vN.N.N, optionally -prerelease or .build)"
  exit 2
fi

# ---- arg parsing --------------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)     DRY_RUN=1 ; shift ;;
    --force)       FORCE=1 ; shift ;;
    --install-dir) INSTALL_DIR="$2" ; shift 2 ;;
    -h|--help)
      sed -n '3,29p' "$0" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *) err "unknown argument: $1" ; exit 2 ;;
  esac
done

run() {
  if (( DRY_RUN )); then
    printf "    %s[dry]%s %s\n" "$C_DIM" "$C_END" "$*"
  else
    eval "$*"
  fi
}

# ---- forge-bridge source resolver --------------------------------------------
# Resolves where the forge-bridge installer lives, in the priority order locked
# in .planning/phases/03-forge-bridge-deploy/03-CONTEXT.md §D-01:
#   1. $FORGE_BRIDGE_REPO (explicit path override) — if set AND points at a clone
#      that contains scripts/install-flame-hook.sh, use it.
#   2. Sibling-clone auto-detect: ../forge-bridge/, $HOME/Documents/GitHub/forge-bridge/,
#      $HOME/code/forge-bridge/ — first hit wins.
#   3. Curl fallback against the pinned FORGE_BRIDGE_VERSION tag on GitHub.
#
# On success, sets three globals (SOURCE_KIND picks which of the invocation
# forms the install-step call site uses — see the KIND switch at `step
# "forge-bridge"` below):
#   FORGE_BRIDGE_SOURCE_KIND   — one of: local, curl
#   FORGE_BRIDGE_SOURCE_ARGV   — (local only) bash argv array; invoked as
#                                `"${FORGE_BRIDGE_SOURCE_ARGV[@]}"` so the
#                                operator-supplied clone path never flows
#                                through `eval` (per WR-02).
#   FORGE_BRIDGE_SOURCE_CMD    — human-readable command string for display
#                                (used by the `[dry-run] would execute: …`
#                                print). For curl KIND, it is ALSO the
#                                execution form since curl|bash needs shell
#                                pipeline semantics; the embedded
#                                FORGE_BRIDGE_VERSION is validated against a
#                                strict regex at script start (per WR-01), so
#                                there is no injection surface through this
#                                string.
# Also prints the D-03 info line so the user knows which copy is being deployed.
# Returns 0 on success (a source is available), 1 if no local clone found AND the
# host is offline / curl missing (deferred — this function never probes curl; we
# optimistically construct the URL and let Plan 03-02's install step surface the
# curl failure via D-09/D-10).
_resolve_forge_bridge_source() {
  local candidate

  # (1) explicit FORGE_BRIDGE_REPO override
  if [[ -n "${FORGE_BRIDGE_REPO:-}" ]]; then
    if [[ -f "${FORGE_BRIDGE_REPO}/scripts/install-flame-hook.sh" ]]; then
      FORGE_BRIDGE_SOURCE_KIND="local"
      # WR-02: operator-supplied path goes into an argv array, NOT an
      # eval-ed string. The display-CMD is a quoted rendition for the
      # dry-run "would execute" line only; it is never eval'd.
      FORGE_BRIDGE_SOURCE_ARGV=(bash "${FORGE_BRIDGE_REPO}/scripts/install-flame-hook.sh")
      FORGE_BRIDGE_SOURCE_CMD="bash \"${FORGE_BRIDGE_REPO}/scripts/install-flame-hook.sh\""
      ok "[forge-bridge] using local clone at ${FORGE_BRIDGE_REPO}"
      # D-06: surface the clone's HEAD so pin-vs-clone drift is visible.
      local head_ref
      if head_ref=$(git -C "${FORGE_BRIDGE_REPO}" describe --tags --always --dirty 2>/dev/null); then
        ok "[forge-bridge] local clone version: ${head_ref}"
      else
        warn "[forge-bridge] local clone version: (git describe failed — clone may be shallow)"
      fi
      return 0
    else
      warn "[forge-bridge] FORGE_BRIDGE_REPO=${FORGE_BRIDGE_REPO} does not contain scripts/install-flame-hook.sh — falling through to auto-detect"
    fi
  fi

  # (2) sibling-clone auto-detect
  for candidate in \
      "${REPO_ROOT}/../forge-bridge" \
      "${HOME}/Documents/GitHub/forge-bridge" \
      "${HOME}/code/forge-bridge"; do
    if [[ -f "${candidate}/scripts/install-flame-hook.sh" ]]; then
      FORGE_BRIDGE_SOURCE_KIND="local"
      # WR-02: argv-array form, same rationale as the explicit-override branch.
      # The hardcoded candidate prefixes are not operator-controlled, but we
      # keep the eval-free form uniform so the call site has a single invocation
      # pattern for all "local" KIND cases.
      FORGE_BRIDGE_SOURCE_ARGV=(bash "${candidate}/scripts/install-flame-hook.sh")
      FORGE_BRIDGE_SOURCE_CMD="bash \"${candidate}/scripts/install-flame-hook.sh\""
      ok "[forge-bridge] using local clone at ${candidate}"
      local head_ref
      if head_ref=$(git -C "${candidate}" describe --tags --always --dirty 2>/dev/null); then
        ok "[forge-bridge] local clone version: ${head_ref}"
      else
        warn "[forge-bridge] local clone version: (git describe failed — clone may be shallow)"
      fi
      return 0
    fi
  done

  # (3) curl fallback. Keeps the string form because curl|bash is a shell
  # pipeline (argv invocation cannot express it). FORGE_BRIDGE_VERSION is
  # validated against ^v[0-9]+\.[0-9]+\.[0-9]+(...)$ at script start per
  # WR-01, so this interpolation is no longer an injection surface.
  FORGE_BRIDGE_SOURCE_KIND="curl"
  FORGE_BRIDGE_SOURCE_CMD="curl -fsSL https://raw.githubusercontent.com/cnoellert/forge-bridge/${FORGE_BRIDGE_VERSION}/scripts/install-flame-hook.sh | FORGE_BRIDGE_VERSION=${FORGE_BRIDGE_VERSION} bash"
  ok "[forge-bridge] fetching ${FORGE_BRIDGE_VERSION} from GitHub"
  return 0
}

# ---- forge-bridge --force helper ---------------------------------------------
# Under --force, explicitly delete any previously-installed forge_bridge.py so the
# reinstall is unambiguous. The sibling installer overwrites via plain `cp` anyway,
# but this makes --force's intent readable in install.sh itself (per D-13).
_bridge_rm_force() {
  if (( FORCE )); then
    if [[ -f "${FORGE_BRIDGE_HOOK_PATH}" ]]; then
      run "rm -f \"${FORGE_BRIDGE_HOOK_PATH}\""
      # Suppress the past-tense "removed" line under dry-run (per WR-03): the
      # `run` wrapper above only printed what WOULD execute; saying "removed"
      # here would contradict D-12 ("dry-run prints what would execute and
      # skips"). Real runs still get the confirmation.
      if (( ! DRY_RUN )); then
        ok "[forge-bridge] --force: removed existing ${FORGE_BRIDGE_HOOK_PATH}"
      fi
    fi
  fi
}

printf "Camera Match installer\n"
printf "  repo:       %s\n" "$REPO_ROOT"
printf "  install to: %s\n" "$INSTALL_DIR"
printf "  forge env:  %s\n" "$FORGE_ENV"
(( DRY_RUN )) && warn "dry-run mode — no files will be changed"

# ---- source sanity ------------------------------------------------------------
step "Source"
if [[ ! -f "$SOURCE_HOOK" ]]; then
  err "missing source hook: $SOURCE_HOOK"
  exit 1
fi
ok "hook present ($(wc -l < "$SOURCE_HOOK" | tr -d ' ') lines)"
if [[ ! -d "$SOURCE_FORGE_CORE" ]]; then
  err "missing source forge_core: $SOURCE_FORGE_CORE"
  exit 1
fi
ok "forge_core present ($(find "$SOURCE_FORGE_CORE" -name '*.py' -not -path '*/__pycache__/*' | wc -l | tr -d ' ') .py files)"
if [[ ! -d "$SOURCE_FORGE_FLAME" ]]; then
  err "missing source forge_flame: $SOURCE_FORGE_FLAME"
  exit 1
fi
ok "forge_flame present ($(find "$SOURCE_FORGE_FLAME" -name '*.py' -not -path '*/__pycache__/*' | wc -l | tr -d ' ') .py files)"
if [[ ! -d "$SOURCE_BLENDER_SCRIPTS" ]]; then
  err "missing source tools/blender: $SOURCE_BLENDER_SCRIPTS"
  exit 1
fi
ok "tools/blender present ($(find "$SOURCE_BLENDER_SCRIPTS" -maxdepth 1 -type f | wc -l | tr -d ' ') files)"

# ---- precheck: forge conda env ------------------------------------------------
step "Forge conda env"
FORGE_PY="$FORGE_ENV/bin/python"
PREFLIGHT_FAIL=0
if [[ ! -x "$FORGE_PY" ]]; then
  err "forge python not found at $FORGE_PY"
  warn "create it with: conda create -n forge python=3.11 numpy opencv-python"
  PREFLIGHT_FAIL=1
else
  ok "python: $("$FORGE_PY" --version 2>&1)"
  # Probe deps from within the forge env
  if ! "$FORGE_PY" -c "import numpy, cv2" >/dev/null 2>&1; then
    err "forge env missing numpy or cv2"
    warn "install with: $FORGE_ENV/bin/pip install numpy opencv-python"
    PREFLIGHT_FAIL=1
  else
    ok "deps: numpy $("$FORGE_PY" -c 'import numpy;print(numpy.__version__)')" \
       ", cv2 $("$FORGE_PY" -c 'import cv2;print(cv2.__version__)')"
  fi
fi

# ---- precheck: wiretap CLI ----------------------------------------------------
step "Wiretap single-frame reader"
if [[ ! -x "$WIRETAP_CLI" ]]; then
  err "wiretap_rw_frame not found or not executable: $WIRETAP_CLI"
  warn "this is the reader the hook uses for all clip frames — tool won't work without it"
  PREFLIGHT_FAIL=1
else
  # Resolve the /current/ symlink so user sees which Flame version is active
  TARGET=$(readlink "$(dirname "$WIRETAP_CLI")" 2>/dev/null || echo "?")
  ok "$WIRETAP_CLI (current → $TARGET)"
fi

# ---- precheck: Flame-bundled PyOpenColorIO -----------------------------------
step "PyOpenColorIO (from Flame's bundled Python)"
# shellcheck disable=SC2086
FLAME_PYOCIO=( $FLAME_PYOCIO_GLOB )
if [[ ${#FLAME_PYOCIO[@]} -eq 0 || ! -d "${FLAME_PYOCIO[0]}" ]]; then
  err "no PyOpenColorIO found under /opt/Autodesk/python/*/lib/python3.11/site-packages"
  warn "Flame install may be broken; OCIO preview will fail"
  PREFLIGHT_FAIL=1
else
  for p in "${FLAME_PYOCIO[@]}"; do
    ok "$p"
  done
fi

# ---- precheck: aces2.0_config OCIO --------------------------------------------
step "OCIO config (aces2.0_config)"
# shellcheck disable=SC2086
OCIO_HITS=( $OCIO_GLOB )
if [[ ${#OCIO_HITS[@]} -eq 0 || ! -f "${OCIO_HITS[0]}" ]]; then
  err "no aces2.0_config/config.ocio found under /opt/Autodesk/colour_mgmt/configs/flame_configs/*"
  warn "the hook's resolver will return None and fall back to passthrough (float sources will look clipped)"
  PREFLIGHT_FAIL=1
else
  for p in "${OCIO_HITS[@]}"; do
    ok "$p"
  done
fi

# ---- halt if precheck failed --------------------------------------------------
if (( PREFLIGHT_FAIL )); then
  err "preflight failed — fix the issues above and re-run"
  exit 1
fi

# ---- forge-bridge install (Phase 3: BRG-01/02/03/04) --------------------------
# Runs BEFORE the Camera Match install (per D-07) so bridge-install failures
# surface in terminal output BEFORE "camera_match installed" — clearer failure
# semantics than the reverse order. If the bridge install fails, we warn and
# continue: VP-solve + v6.2 static round-trip do not need forge-bridge, so
# deploying Camera Match alone is still useful. Only v6.3 Send-to-Flame breaks
# until the bridge is deployed (the Blender addon's Transport Tier popup already
# covers that runtime failure mode — see .planning/phases/02-blender-addon/).
#
# D-14 reminder: this section does NOT try to start Flame or curl 127.0.0.1:9999.
# BRG-01/BRG-02 live verification is Phase 4's E2E smoke test. Here we only
# verify the hook FILE lands at FORGE_BRIDGE_HOOK_PATH and parses as Python.
step "forge-bridge"
BRIDGE_OK=1
BRIDGE_FAIL_REASON=""

# D-01/D-03/D-06: resolve source. Always succeeds (either local hit or curl command
# constructed). Sibling installer not yet invoked.
_resolve_forge_bridge_source

# D-13: --force ⇒ rm -f the old hook file before invoking the sibling installer.
_bridge_rm_force

# D-12: dry-run prints what would execute and skips. Note: `run` already handles
# dry-run for the sibling-installer invocation itself, but we additionally print
# the [dry-run] would-execute line so the user sees WHICH installer path (local
# vs curl) would run.
if (( DRY_RUN )); then
  printf "    %s[dry-run]%s would execute: %s\n" "$C_DIM" "$C_END" "$FORGE_BRIDGE_SOURCE_CMD"
else
  # Invoke the sibling installer. Failure ⇒ mark bridge failed, remember the reason,
  # but do NOT exit (D-09). The sibling installer uses `set -euo pipefail`, so any
  # internal failure (curl 404, mkdir permission denied, python3 ast.parse fail)
  # surfaces as a non-zero exit.
  #
  # The `if ...; then ... else` construct bypasses `set -e` inside the
  # conditional, so a non-zero exit from the sibling installer routes to the
  # `else` branch instead of aborting the outer script. No `|| true` + `$?` dance
  # needed. (Note: if the sibling's own ast.parse fails internally, we classify
  # it as "sibling installer exited non-zero" rather than a D-15-specific reason.
  # This is fine — D-10's copy doesn't require the reason to be ast-specific, and
  # the retry guidance the user sees is identical either way.)
  #
  # WR-02: switch on FORGE_BRIDGE_SOURCE_KIND so operator-supplied paths never
  # flow through eval. `local` KIND invokes the argv array directly (the path
  # is an array element, never re-parsed as shell). `curl` KIND uses eval
  # because curl|bash is a shell pipeline that argv form cannot express — the
  # embedded FORGE_BRIDGE_VERSION is validated against a strict semver regex
  # at script start per WR-01, so the curl string is not an injection surface.
  if [[ "${FORGE_BRIDGE_SOURCE_KIND}" == "local" ]]; then
    if "${FORGE_BRIDGE_SOURCE_ARGV[@]}"; then
      : # sibling installer succeeded — fall through to D-15 sanity check below
    else
      BRIDGE_OK=0
      BRIDGE_FAIL_REASON="sibling installer exited non-zero"
    fi
  else
    if eval "$FORGE_BRIDGE_SOURCE_CMD"; then
      : # sibling installer succeeded — fall through to D-15 sanity check below
    else
      BRIDGE_OK=0
      BRIDGE_FAIL_REASON="sibling installer exited non-zero"
    fi
  fi
fi

# D-15: post-install sanity check. Skip under --dry-run (nothing was installed).
# Skip if we already know the bridge failed (no point checking a file we didn't try
# to install). This is the belt-and-suspenders check: the sibling installer already
# does its own ast.parse at lines 62-67 of install-flame-hook.sh, but running it
# again in OUR installer gives us clear ownership of the failure classification.
if (( ! DRY_RUN )) && (( BRIDGE_OK )); then
  if [[ ! -f "$FORGE_BRIDGE_HOOK_PATH" ]]; then
    BRIDGE_OK=0
    BRIDGE_FAIL_REASON="hook not found at $FORGE_BRIDGE_HOOK_PATH after install"
  elif ! python3 -c "import ast, sys; ast.parse(open(sys.argv[1]).read())" "$FORGE_BRIDGE_HOOK_PATH" >/dev/null 2>&1; then
    BRIDGE_OK=0
    BRIDGE_FAIL_REASON="hook at $FORGE_BRIDGE_HOOK_PATH failed python3 ast.parse sanity check"
  fi
fi

# Report outcome. On success, single ok line + fall through to Camera Match install.
# On failure, emit the D-10 warning VERBATIM as a SINGLE paragraph (NOT two `warn`
# calls — see plan's <interfaces> block for rationale). BRIDGE_FAIL_REASON fills
# the ${reason} slot; FORGE_BRIDGE_VERSION fills the retry-hint URL tag.
if (( DRY_RUN )); then
  ok "[forge-bridge] dry-run complete — skipped actual install and sanity check"
elif (( BRIDGE_OK )); then
  ok "[forge-bridge] installed at $FORGE_BRIDGE_HOOK_PATH"
  ok "[forge-bridge] next Flame boot will spawn the bridge on http://127.0.0.1:9999 (verification deferred to Phase 4 E2E per D-14)"
else
  # D-10: this warning copy is the contractual user-facing message on failure.
  # Any edit here is a user-visible breaking change — treat as a CONTEXT.md update.
  # Emitted as a single bare `printf` (not `warn`) to avoid the double `  ! ` prefix
  # collision between the `warn` helper and the embedded `[WARN]` token, and to
  # preserve D-10's single-paragraph contract. Writes to stderr to match the
  # `warn`/`err` convention. Uses `$C_WARN`/`$C_END` so TTY colouring is consistent.
  printf "  %s[WARN]%s forge-bridge install skipped (%s). VP-solve and v6.2 static round-trip still work. v6.3 Send-to-Flame will fail with \"forge-bridge not reachable at http://127.0.0.1:9999\" until the bridge is deployed. To retry: FORGE_BRIDGE_REPO=<path> ./install.sh   OR   curl -fsSL https://raw.githubusercontent.com/cnoellert/forge-bridge/%s/scripts/install-flame-hook.sh | bash\n" \
    "$C_WARN" "$C_END" "$BRIDGE_FAIL_REASON" "$FORGE_BRIDGE_VERSION" >&2
fi

# ---- target dir + existing install -------------------------------------------
step "Install"
TARGET_HOOK="$INSTALL_DIR/camera_match.py"
TARGET_INIT="$INSTALL_DIR/__init__.py"
TARGET_PYCACHE="$INSTALL_DIR/__pycache__"

if [[ ! -d "$INSTALL_DIR" ]]; then
  run "mkdir -p \"$INSTALL_DIR\""
  ok "created $INSTALL_DIR"
else
  if [[ -f "$TARGET_HOOK" && $FORCE -eq 0 && $DRY_RUN -eq 0 ]]; then
    warn "existing install: $TARGET_HOOK"
    read -r -p "  overwrite? [y/N] " ans
    [[ "${ans:-N}" =~ ^[Yy]$ ]] || { err "aborted by user"; exit 1; }
  fi
  ok "using existing $INSTALL_DIR"
fi

# copy hook
run "cp \"$SOURCE_HOOK\" \"$TARGET_HOOK\""
ok "wrote $TARGET_HOOK"

# stub __init__.py — prevents the namespace-package drift documented in
# memory/flame_module_reload.md. Needs to exist; contents don't matter.
run "printf '# Camera Match package marker — keeps Flame'\\''s loader from treating\\n# this directory as a namespace package, which breaks importlib.reload.\\n' > \"$TARGET_INIT\""
ok "wrote $TARGET_INIT"

# sync forge_core/ and forge_flame/ alongside camera_match/. rsync --delete
# so a removed module on the source side actually disappears on the install
# side; __pycache__ excluded so bytecode from local dev doesn't stomp Flame's.
step "forge_core + forge_flame"
_sync_dir() {
  local src="$1" dst="$2" label="$3"
  if command -v rsync >/dev/null 2>&1; then
    run "rsync -a --delete --exclude __pycache__ \"$src/\" \"$dst/\""
    ok "synced $label: $src → $dst"
  else
    # rsync absent → fall back to rm -rf + cp -a. Slower but correct.
    run "rm -rf \"$dst\""
    run "cp -a \"$src\" \"$dst\""
    run "find \"$dst\" -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true"
    ok "copied $label: $src → $dst"
  fi
}
_sync_dir "$SOURCE_FORGE_CORE"       "$FORGE_CORE_DEST"       "forge_core"
_sync_dir "$SOURCE_FORGE_FLAME"      "$FORGE_FLAME_DEST"      "forge_flame"
# tools/blender ships to /opt/Autodesk/shared/forge_blender_scripts/ — OUTSIDE
# Flame's hook scan path (/opt/Autodesk/shared/python/). Safe to sync the whole
# tree (bake, extract, forge_sender/) because Flame never imports from here.
_sync_dir "$SOURCE_BLENDER_SCRIPTS"  "$BLENDER_SCRIPTS_DEST"  "tools/blender"

# nuke pycache so Flame doesn't serve stale bytecode
if [[ -d "$TARGET_PYCACHE" ]]; then
  run "rm -rf \"$TARGET_PYCACHE\""
  ok "cleared $TARGET_PYCACHE"
fi

# ---- done ---------------------------------------------------------------------
step "Done"
# ---- scope boundary ------------------------------------------------------------
# install.sh does NOT:
#   - Start or restart Flame
#   - Curl 127.0.0.1:9999 to prove the bridge is reachable
#   - Kill any running Flame / forge-bridge process
# Live end-to-end verification (BRG-01 bridge starts on Flame boot, BRG-02 bridge
# dies cleanly on Flame quit) is Phase 4's E2E smoke test — see .planning/phases/
# 03-forge-bridge-deploy/03-CONTEXT.md §D-14. Phase 3's verification is strictly
# "the hook file landed at FORGE_BRIDGE_HOOK_PATH and parses as Python" (D-15).
cat <<EOF

Next steps:

  1. Restart Flame. On next boot, both the Camera Match hook AND the forge-bridge
     hook register — forge-bridge will start listening on http://127.0.0.1:9999.
     If the forge-bridge install was skipped (see the [WARN] above), v6.3
     Send-to-Flame will fail until the bridge is deployed; VP-solve and v6.2
     static round-trip still work.

  2. To reload the live Camera Match module without a restart (bridge still needs
     a restart to register):

     import sys, gc, types
     src = open('$TARGET_HOOK').read()
     code = compile(src, '$TARGET_HOOK', 'exec')
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

EOF
