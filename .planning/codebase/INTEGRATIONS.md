# External Integrations

**Analysis Date:** 2026-05-12

## APIs and in-process services

**Autodesk Wiretap**

- CLI: `/opt/Autodesk/wiretap/tools/current/wiretap_rw_frame` — single-frame extraction
- SDK path: `/opt/Autodesk/wiretap/tools/current/python` (when used from Flame)
- Implementation: `forge_flame/wiretap.py`
- Used for: Plate preview frames for the VP line tool (colour-space tagging, raw buffer decode)

**Autodesk Flame Python API**

- PyClip / PyAction / PyBatch / PyCoNode — clip selection, Action cameras, batch menus
- Implementation: `flame/camera_match_hook.py`, `forge_flame/adapter.py`
- Used for: Batch menu registration, reading/writing camera parameters on Apply

**Autodesk OpenColorIO (Flame-bundled)**

- Module: PyOpenColorIO from Flame’s Python tree (not the conda `forge` env)
- Implementation: `forge_core/colour/ocio.py`
- Config: `/opt/Autodesk/colour_mgmt/configs/flame_configs/*/aces2.0_config/config.ocio`

**PySide6 (Flame-bundled)**

- VP line UI, dialogs, preview widget

## Data storage

- **Input:** Flame clip nodes; frames via Wiretap
- **Intermediate:** In-memory RGB / numpy arrays; optional `/tmp/forge_camera_match_trace.json` for solver diagnostics
- **Output:** Camera parameters on Action nodes (Flame internal state)

## Authentication

None — internal workstation tool inside Flame’s security boundary.

## Monitoring

- Trace JSON on solve (adapter)
- stderr from Wiretap subprocess failures surfaced in the hook UI

## CI/CD and deployment

- **`install.sh`:** Copies `camera_match/`, `forge_core/`, `forge_flame/` under `/opt/Autodesk/shared/python/`; preflight conda, Wiretap, PyOpenColorIO, OCIO; purges stale legacy files. **Does not** install or configure **forge-bridge**.
- **pytest:** 191 tests locally (no CI gate in repo)

## Optional / sibling repos (not calibrator runtime)

**forge-bridge** (`127.0.0.1:9999/exec`) — Tier-3 dev RPC into Flame’s Python. Maintained separately; developers install from the forge-bridge repo if needed. Future “Send to Flame” / round-trip UX is expected to live primarily under **forge-blender** and related repos, not this installer.

## Environment variables

- **`FORGE_ENV`** — conda env path for numpy/cv2 (see `install.sh`)

---

*Integrations refreshed 2026-05-12; Blender/FBX round-trip removed from this repo (Phase A2).*
