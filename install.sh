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
# tools/blender/ ships as a sibling too — forge_flame.blender_bridge resolves
# scripts to this path at runtime (see _script_candidates there) so the Flame
# batch hook can shell out to bake_camera.py / extract_camera.py.
BLENDER_SCRIPTS_DEST="/opt/Autodesk/shared/python/tools/blender"
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
_sync_dir "$SOURCE_BLENDER_SCRIPTS"  "$BLENDER_SCRIPTS_DEST"  "tools/blender"

# nuke pycache so Flame doesn't serve stale bytecode
if [[ -d "$TARGET_PYCACHE" ]]; then
  run "rm -rf \"$TARGET_PYCACHE\""
  ok "cleared $TARGET_PYCACHE"
fi

# ---- done ---------------------------------------------------------------------
step "Done"
cat <<EOF

Next steps:

  1. In Flame, if Camera Match is not yet registered, restart Flame.
  2. Otherwise, reload the live module from a Python console:

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
