# forge-calibrator — Session Passoff (v2)

## Current state — working but alignment not yet perfect

The tool now produces a camera that **faces the correct direction** (major bug from v1 is fixed). It has a full fSpy-style UI with plane overlay, chevron direction markers, +/− axis labels, and forge-native styling. But when the user adds a surface to verify by resting it on the X/Y plane, the surface still does not sit perfectly flush with the wall in the plate. Two possibilities remain open: (1) small VP-line placement inaccuracy, or (2) a residual convention mismatch we haven't isolated. The trace file lets us diagnose without redoing work.

---

## What changed this session (in order of bug severity)

### 1. Euler decomposition convention — FIXED
Flame's Action camera rotation uses **two non-standard conventions stacked**:

```
R_flame_internal(rx, ry, rz) = Rx(-rx) · Ry(-ry) · Rz(rz)          [XYZ order, X/Y sign-inverted]
```
**And** Flame's identity camera looks **+Z_local → +Z world**, not -Z like OpenGL. This was the source of the "camera faces wrong way" bug. The solver uses OpenGL convention (-Z forward), so the cam→world matrix must be rotated 180° around Y before decomposing:

```python
RY_180 = np.array([[-1, 0, 0], [0, 1, 0], [0, 0, -1]])
R_for_flame = R_solver @ RY_180
# Then decompose:
rx = atan2( R[1,2], R[2,2])
ry = atan2(-R[0,2], cy)
rz = atan2(-R[0,1], R[0,0])
```

**Verified** via FBX export + direct forward-vector math. See `memory/flame_rotation_convention.md`.

Fixed in:
- `flame/camera_match_hook.py` (`_solve`)
- `flame/action_export.py` (`matrix_to_euler_xyz`)
- `flame/solve_and_update.py` (`euler_from_matrix`)

### 2. FOV was wrong — FIXED
Apply was setting `cam.focal` only; Flame's default film back is 16mm Super 16 which made FOV 21.9° instead of 47°. Flame's `cam.fov` is **vertical** FOV — set it directly from `result["vfov_deg"]`.

### 3. Camera position default — CHANGED
Apply now places the camera 10 world-units *back* along its view direction (`pos = -10 * forward_world`), so the auto-added `cam_match_origin` axis at world `(0,0,0)` sits in front of the camera rather than at it. Translation doesn't affect VP projection.

### 4. UI overhauled to forge style
- Full forge palette (`#282c34` bg, `#E87E24` accent, monospaced values). Reference: `/opt/Autodesk/shared/python/forge_cv_align/forge_cv_align.py`. Memory: `memory/forge_ui_style.md`.
- VP line color now tracks the chosen axis (RGB = XYZ; positive bright, negative dim).
- Chevron marker at ~62% along each line **pointing toward the VP** (intersection of the pair). Resolves the "which direction is positive" confusion.
- Axis label pill on VP-facing end (`+X` bold) and opposite end (`−X` dim).
- `Show plane overlay` checkbox in DISPLAY group — projects a 2D grid of the VP-defined plane into the image (plane is offset 10 units along camera forward so it renders as a visible region, not a line).
- Out-of-plane arrow at grid center pointing in the third axis direction.

### 5. Persistent diagnostic trace — NEW
Every solve writes `/tmp/forge_camera_match_trace.json` with:
- `inputs.points_px` (8 drag points) + axis assignments
- `stages.vp1_px`, `vp2_px` — VP intersection in pixel coords
- `stages.u_ax1_in_cam`, `v_ax2_in_cam`, `ww_cross` — camera-space axis vectors
- `stages.cam_rot_cam_to_world` — OpenGL convention cam→world
- `stages.cam_rot_flame_convention` — after RY_180 multiply
- `stages.flame_euler_deg` — applied rotation
- `stages.R_recon_matches_cam_rot_flame` — true if decomposition is self-consistent
- `stages.world_axis_projections` — which world axes project where in the image
- `applied_to_flame` (added on Apply click) — exact values written + intended values

**Known trace logging bug:** the `world_axis_projections.pixel` values are missing a `* f_relative` multiplier in the ipx/ipy formula — the direction is correct but the pixel magnitude is wrong. Cosmetic only (the solver math it reports on is right). To fix: in `_solve`'s `project_world_dir`, multiply `v[0]/-v[2]` and `v[1]/-v[2]` by `f` before converting to pixel.

---

## Remaining issue — surface alignment with wall

Latest test with VP1=-X, VP2=-Y: solved Euler `(-149.10°, 22.47°, 167.39°)`, vfov 33.14°, fov 34.25°. Camera now faces toward the scene and origin is 10 units ahead. When the user adds a Surface with parent Axis at world origin, the surface appears in the upper-right of the rendered output — tilted, not obviously aligned with the wall grout. Reasons we haven't pinned down:

1. **Size/clipping:** At axis scale (100,100,100), the surface is huge relative to the 10-unit camera-origin distance; a 1920×1080 surface at 100× scale with origin 10 units in front of camera will clip through the camera's near plane and render as a weird partial quad. **Try:** scale down to e.g. (1.0, 1.0, 1.0) and see if it still looks misaligned.
2. **Plane orientation test isn't robust yet:** because axis and surface are both AT origin (= 10 units in front of camera), they're close to the camera — small calibration errors project to large visual errors. Moving them OUT along the out-of-plane axis (e.g. set `axis1.position.z = 100`) would put them farther from camera where small errors are less visible.
3. **Residual convention issue:** unlikely since the rotation fix was mathematically verified, but the visual remains off. The plane-overlay grid should answer this — if the grid aligns with grout across the whole image, calibration is correct and the surface misalignment is just placement.

**Before anything else, next session should:**
- Re-open Camera Match, confirm plane overlay grid aligns with the wall grout pattern. If it does, calibration is correct and the issue is purely surface placement; if it doesn't, the solver has a residual bug.
- Inspect `/tmp/forge_camera_match_trace.json` (`stages.R_recon_matches_cam_rot_flame` should be `true`).

---

## Architecture + known APIs (unchanged)

### Solver (`solver/`)
Pure Python/numpy, 46 unit tests passing. Cross-validated against fSpy. Key functions: `solve_2vp()`, `solve_1vp()`.

### Hook (`flame/camera_match_hook.py`)
Single-file Flame hook. Deployed to `/opt/Autodesk/shared/python/camera_match/camera_match.py`.

Top-level structure:
- `_ensure_forge_env()` — adds forge conda env site-packages to sys.path
- `_solve()` — inlined numpy solver with full math trace logging (line ~47-250)
- `_export_frame()` — exports one frame via `PyExporter(hooks=NoHooks())`
- `_open_camera_match()` — Qt window and image widget (line ~300-1000)
- `_launch_camera_match()` + `get_batch_custom_ui_actions()` — menu registration

### forge-bridge live Python endpoint
`http://127.0.0.1:9999/exec` — POST JSON `{"code": "..."}` to run Python in Flame's interpreter. `flame` module is importable. Documented in `memory/flame_bridge.md`.

### Deployed files
| What | Path |
|---|---|
| Hook (deployed) | `/opt/Autodesk/shared/python/camera_match/camera_match.py` |
| JPEG export preset | `/opt/Autodesk/shared/export/presets/file_sequence/JPEG_CameraMatch.xml` |
| Forge style reference | `/opt/Autodesk/shared/python/forge_cv_align/forge_cv_align.py` |
| fSpy test file | `/Users/cnoellert/Desktop/test.fspy` |

### Deploy workflow (for next session)
```bash
# Edit repo file, then:
cp /Users/cnoellert/Documents/GitHub/forge-calibrator/flame/camera_match_hook.py \
   /opt/Autodesk/shared/python/camera_match/camera_match.py
rm -rf /opt/Autodesk/shared/python/camera_match/__pycache__
curl -sS -X POST http://127.0.0.1:9999/exec -H "Content-Type: application/json" \
  -d '{"code":"import sys, importlib; importlib.reload(sys.modules[\"camera_match\"]); print(\"reloaded\")"}'
```
User must **close + reopen** the Camera Match window after each reload — Qt dialog instances don't pick up new methods via module reload, only fresh instantiation does.

---

## Punch list (priority order)

### 1. Diagnose the residual surface misalignment (BLOCKING visual confidence)
First check: does the plane overlay grid align with wall grout across the whole image? If yes → calibration is correct, surface placement is the issue (path: scale/position the surface sensibly and re-test). If no → there's a bug in the solver I haven't found yet. Use the trace file.

### 2. Fix trace projection units (cosmetic)
In `_solve`'s `project_world_dir`, add `* f` to ipx/ipy before pixel conversion. 3-line fix. Will make `world_axis_projections.pixel` values match `vp1_px`/`vp2_px` exactly.

### 3. Origin control point (feature #6 from original passoff)
Let the user click a pixel on the image that corresponds to world origin — the solver translates the camera position to anchor there. Without this, the wall-alignment test requires manual Axis placement.

### 4. Camera-back offset toggle
The current default is `pos = -10 * forward` to separate camera from origin. Some workflows may prefer `pos = (0,0,0)`. Consider making it a checkbox in the DISPLAY group.

### 5. Delete stray debug markers
The `plus_x, plus_y, plus_z, minus_x, minus_y, minus_z` axis markers added during rotation-convention testing can't be deleted via the Python API (`n.delete()` returns NoneType error). User has to manually delete them in Action UI, or they accumulate.

### 6. Cleanup items from original passoff
- Delete `matchbox/` files (abandoned approach) or move to `reference/`
- Delete `flame/apply_solve.py`, `flame/solve_and_update.py` (abandoned Matchbox path)
- Keep `flame/action_export.py` (shared helpers) and `flame/rotation_diagnostic.py` (useful tool)

---

## Memory files (at `/Users/cnoellert/.claude/projects/-Users-cnoellert-Documents-GitHub-forge-calibrator/memory/`)

- `MEMORY.md` — index
- `flame_rotation_convention.md` — the RY_180 fix documented in full
- `flame_bridge.md` — how to drive Flame via HTTP during development
- `forge_ui_style.md` — the shared palette/layout all forge tools use

---

## Test scene (in Flame right now)
- Batch: `gen_0260_v00`
- Clip: `testImage` (5184×3456)
- Action: `action1` — contains applied camera at `(3.82, 4.75, 7.93)`, rotation `(-149.10, 22.47, 167.39)`, fov 33.14° (vertical). Also `cam_match_origin` axis at world origin (scale 1.0 set via bridge), plus user's `axis1` + `surface1` at origin (scale 5.0).
- Last trace: `/tmp/forge_camera_match_trace.json` — inspect with `jq`.
