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
#   ./install.sh --yes            # non-interactive auto-create of forge env if missing
#
# Environment overrides:
#   FORGE_ENV     conda forge env path (default: $HOME/miniconda3/envs/forge)
#
# forge-bridge (Tier-3 dev-time RPC into Flame) is not installed by this script.
# Deploy it from the forge-bridge repo if you need HTTP /exec probes; see
# memory/forge_family_tier_model.md and CLAUDE.md.
#

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_HOOK="$REPO_ROOT/flame/camera_match_hook.py"
SOURCE_FORGE_CORE="$REPO_ROOT/forge_core"
SOURCE_FORGE_FLAME="$REPO_ROOT/forge_flame"

INSTALL_DIR="/opt/Autodesk/shared/python/camera_match"
# forge_core (host-agnostic) and forge_flame (Flame-specific adapters like the
# Wiretap reader) both ship as SIBLINGS of camera_match/ under /opt/Autodesk/
# shared/python/. The hook imports both by absolute path, so they must be
# importable alongside camera_match at runtime.
FORGE_CORE_DEST="/opt/Autodesk/shared/python/forge_core"
FORGE_FLAME_DEST="/opt/Autodesk/shared/python/forge_flame"
WIRETAP_CLI="/opt/Autodesk/wiretap/tools/current/wiretap_rw_frame"
OCIO_GLOB="/opt/Autodesk/colour_mgmt/configs/flame_configs/*/aces2.0_config/config.ocio"
FLAME_PYOCIO_GLOB="/opt/Autodesk/python/*/lib/python3.11/site-packages/PyOpenColorIO"

DRY_RUN=0
FORCE=0
YES=0

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

_home_for_user() {
  local user="$1"
  local home=""
  if [[ -n "$user" ]]; then
    home="$(dscl . -read "/Users/$user" NFSHomeDirectory 2>/dev/null | awk '{print $2}' || true)"
    if [[ -z "$home" ]]; then
      home="$(getent passwd "$user" 2>/dev/null | awk -F: '{print $6}' || true)"
    fi
    if [[ -z "$home" && -d "/Users/$user" ]]; then
      home="/Users/$user"
    fi
  fi
  printf "%s" "${home:-$HOME}"
}

INVOKING_USER="${SUDO_USER:-${USER:-}}"
INVOKING_HOME="$(_home_for_user "$INVOKING_USER")"
FORGE_ENV="${FORGE_ENV:-$INVOKING_HOME/miniconda3/envs/forge}"

_resolve_conda_bin() {
  local conda_bin=""
  conda_bin="$(command -v conda 2>/dev/null || true)"
  if [[ -n "$conda_bin" ]]; then
    printf "%s" "$conda_bin"
    return 0
  fi

  local candidate
  for candidate in \
    "$INVOKING_HOME/miniconda3/bin/conda" \
    "$INVOKING_HOME/anaconda3/bin/conda" \
    "$HOME/miniconda3/bin/conda" \
    "$HOME/anaconda3/bin/conda"
  do
    if [[ -x "$candidate" ]]; then
      printf "%s" "$candidate"
      return 0
    fi
  done

  return 1
}

CONDA_BIN="$(_resolve_conda_bin || true)"

# ---- arg parsing --------------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)     DRY_RUN=1 ; shift ;;
    --force)       FORCE=1 ; shift ;;
    --yes|-y)      YES=1 ; shift ;;
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

# ---- precheck: forge conda env ------------------------------------------------
step "Forge conda env"
FORGE_PY="$FORGE_ENV/bin/python"
FORGE_ENV_YML="$REPO_ROOT/forge-env.yml"
PREFLIGHT_FAIL=0

# Auto-create branch: --force or --yes triggers create-without-prompt; otherwise
# prompt the user (default N). On 'n' we print the copy-pasteable one-liner and
# fail preflight so the existing exit-1 path catches it.
_create_forge_env() {
  if [[ ! -f "$FORGE_ENV_YML" ]]; then
    err "cannot auto-create — $FORGE_ENV_YML not found in repo root"
    return 1
  fi
  run "\"$CONDA_BIN\" env create -f \"$FORGE_ENV_YML\""
  return $?
}

if [[ -z "$CONDA_BIN" || ! -x "$CONDA_BIN" ]]; then
  err "conda not found on PATH"
  warn "install miniconda from https://docs.conda.io/projects/miniconda/"
  warn "then create the forge env: conda env create -f forge-env.yml"
  if [[ "$INVOKING_HOME" != "$HOME" ]]; then
    warn "also checked $INVOKING_HOME/miniconda3/bin/conda and $INVOKING_HOME/anaconda3/bin/conda"
  fi
  PREFLIGHT_FAIL=1
elif [[ ! -x "$FORGE_PY" ]]; then
  warn "forge env not found at $FORGE_ENV"
  if (( FORCE )) || (( YES )); then
    ok "auto-creating forge env (--force or --yes set)"
    if _create_forge_env && [[ -x "$FORGE_PY" || $DRY_RUN -eq 1 ]]; then
      ok "forge env ready"
    else
      err "auto-create failed — fix the conda error above and re-run"
      PREFLIGHT_FAIL=1
    fi
  else
    read -r -p "  auto-create forge env now? [y/N] " ans
    if [[ "${ans:-N}" =~ ^[Yy]([Ee][Ss])?$ ]]; then
      if _create_forge_env && [[ -x "$FORGE_PY" || $DRY_RUN -eq 1 ]]; then
        ok "forge env ready"
      else
        err "auto-create failed — fix the conda error above and re-run"
        PREFLIGHT_FAIL=1
      fi
    else
      warn "create it manually: conda env create -f forge-env.yml"
      PREFLIGHT_FAIL=1
    fi
  fi
fi

# Re-check after the create branch above — if we still don't have a python, OR
# we auto-created in dry-run mode (binary won't exist), bail without trying to
# probe deps. If the binary IS present, run the dep probe.
if (( ! PREFLIGHT_FAIL )) && [[ -x "$FORGE_PY" ]]; then
  ok "python: $("$FORGE_PY" --version 2>&1)"
  if ! "$FORGE_PY" -c "import numpy, cv2" >/dev/null 2>&1; then
    err "forge env missing numpy or cv2"
    warn "fix with: conda env update -f forge-env.yml --prune"
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

# nuke pycache across camera_match + sibling forge_core/forge_flame trees so
# Flame doesn't serve stale bytecode. Pre-260427 this only purged
# camera_match/__pycache__; UAT GAP-04.4-UAT-04 (round 2) hit a stale .pyc in
# forge_flame/__pycache__ that masked a Plan 04.4-07 source update and produced
# a misleading 'NoneType' object is not callable in the hook callback. The
# rsync --exclude above keeps dev-side .pyc out of the install, but Flame
# regenerates .pyc at import time — so any stale .pyc that Flame wrote on its
# previous boot can outlive a new source drop. See
# memory/flame_install_pycache_gap.md.
run "find \"$INSTALL_DIR\" \"$FORGE_CORE_DEST\" \"$FORGE_FLAME_DEST\" -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true"
ok "cleared __pycache__ across camera_match + forge_core + forge_flame"

# Purge stale Matchbox-era hooks at $INSTALL_DIR root. These were never copied
# by the current install.sh, but a pre-260427 install or manual dev copy may
# have left them behind — Flame's hook scanner picks them up at boot and
# crashes on `from flame.action_export import ...` (now-missing module).
# Source files deleted in quick-260505-mrv. Idempotent: rm -f survives missing.
run "rm -f \"$INSTALL_DIR/apply_solve.py\" \"$INSTALL_DIR/action_export.py\" \"$INSTALL_DIR/solve_and_update.py\""
ok "purged stale Matchbox-era scripts (if present)"

# Purge stale Blender round-trip artifacts at $INSTALL_DIR root and
# /opt/Autodesk/shared/forge_blender_scripts/. These were never copied
# by the post-strip install.sh, but a pre-strip install left them behind.
# Source files deleted in quick-260505-tb3. Idempotent: rm survives missing.
run "rm -f \"$INSTALL_DIR/scale_picker_dialog.py\""
run "rm -rf /opt/Autodesk/shared/forge_blender_scripts/"
ok "purged stale Blender round-trip artifacts (if present)"

# ---- done ---------------------------------------------------------------------
step "Done"
# ---- scope boundary ------------------------------------------------------------
# install.sh does NOT:
#   - Start or restart Flame
#   - Install or configure forge-bridge (separate repo / dev workflow)
cat <<EOF

Next steps:

  1. Restart Flame so Batch loads the Camera Match hook from $INSTALL_DIR.

  2. To reload the live Camera Match module without a Flame restart:

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

EOF
