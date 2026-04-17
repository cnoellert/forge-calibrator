# forge-calibrator — Session Passoff (v3)

## Current state — camera now faces the right way; residual in-plane rotation is the open item

Big wins this session:
- **Rotation convention was wrong.** Prior session added a `RY_180` flip to convert solver→Flame frame. Verified empirically (Flame Top view + the default fresh-camera look direction) that Flame's identity camera looks `-Z_local` like OpenGL, so no flip is needed. Removed. Memory file corrected.
- **cam_back must be at Flame's native pixel scale.** Flame uses 1 world unit ≈ 1 image pixel. Default camera sits at `h / (2·tan(vfov/2))` — ~5755 units for a 3456px-tall, 33°-vfov plate. Old `cam_back = 10` made solved geometry microscopic (500× smaller than the scene). Now auto-computed.
- **Origin control point landed.** Draggable white crosshair handle defaults to VP1 line-0 ∩ VP2 line-0 intersection. Solver places camera so world origin projects to that pixel at `cam_back` distance — matches fSpy's workflow.
- **3-lines-per-VP toggle.** "3 lines per VP (least-squares)" checkbox in VANISHING POINTS group. When enabled, each VP gets a 3rd line (default stacked in the middle of the image) and VP position is the homogeneous-SVD fit over all 3 lines. Reduces residual in-plane rotation caused by 2-line imprecision.
- **Flame-correct defaults.** VP1 = -X, VP2 = -Y (changed from prior -Z).

Verified render: user applied a calibrated camera to a plate of a tiled wall+stairs; a surface parented to an axis at world origin now renders **on the correct wall plane** (image attached in session). Small residual in-plane tilt remains — expected to improve with 3-line mode or more precise VP line placement.

---

## Key files + where the math lives

### `flame/camera_match_hook.py`
- **`_fit_vp(lines_px)`** — least-squares VP fit via SVD. Lines → homogeneous 3-vectors `(a,b,c)`; VP = eigenvector of smallest eigenvalue of `sum(L_i L_i^T)`. Reduces to exact 2-line intersection when N=2.
- **`_solve_lines(vp1_lines, vp2_lines, ...)`** — entry from UI. Fits each VP, packs into 8-point form, delegates to `_solve`.
- **`_solve(pts_px, w, h, ax1, ax2, origin_px=None, cam_back=None)`** — full 2VP math. Rotation decomposition uses Flame's inverted-XYZ Euler recipe (`Rx(-rx)·Ry(-ry)·Rz(rz)`). **No RY_180.** Camera position computed from `origin_px` ray scaled to `cam_back`.
- **`ImageWidget`** — 12 points (3 lines × 2 endpoints × 2 VPs). `self.three_lines` toggles between 2- and 3-line mode by gating which point indices render and which lines feed the solver.
- **`_draw_plane_overlay`** — grid step now `cam_back / 20`; out-of-plane arrow now `3·step`. Both visible at native Flame scale.

### Memory files (at `/Users/cnoellert/.claude/projects/-Users-cnoellert-Documents-GitHub-forge-calibrator/memory/`)
- `flame_rotation_convention.md` — **UPDATED this session**. The OLD claim (identity looks +Z, need RY_180) is wrong and has been corrected in place.
- `flame_bridge.md` — live HTTP exec endpoint for Flame (unchanged).
- `forge_ui_style.md` — shared palette (unchanged).

### Deploy + reload workflow
```bash
cp /Users/cnoellert/Documents/GitHub/forge-calibrator/flame/camera_match_hook.py \
   /opt/Autodesk/shared/python/camera_match/camera_match.py
rm -rf /opt/Autodesk/shared/python/camera_match/__pycache__
curl -sS -X POST http://127.0.0.1:9999/exec -H "Content-Type: application/json" \
  -d '{"code":"import sys, importlib; importlib.reload(sys.modules[\"camera_match\"]); print(\"reloaded\")"}'
```
**Always close + reopen the Camera Match window after reload** — module reload doesn't refresh already-instantiated Qt dialogs.

---

## Open items (priority order)

### 1. Verify 3-line mode reduces in-plane tilt (primary open question)
User hasn't yet tested 3-line mode on the wall shot. Expected workflow: enable the checkbox, drag the 3rd red line onto a 3rd horizontal grout line, 3rd green line onto a 3rd vertical grout line. Re-solve. Apply. Compare residual tilt of the surface-at-origin in Flame's render against the prior 2-line render. If tilt drops meaningfully, 3-line mode has done its job. If it's the same, the 2-line residual is from something else (lens distortion, non-orthogonal world VPs, Flame surface default orientation).

### 2. Refine VP1∩VP2 origin default when lines 0 don't share a corner
Current default: `line(points[0],points[1]) ∩ line(points[6],points[7])`. If user's line 0 of each VP don't visually share a scene corner, the default pixel isn't meaningful and they have to drag. Options: (a) leave as-is (user always drags when needed), (b) auto-detect: if default lies outside image bounds or far from any endpoint cluster, fall back to principal point. (a) is fine short-term.

### 3. Per-line residual display (nice-to-have)
When in 3-line mode, show each line's perpendicular distance to the fitted VP as a small label next to the line. Big residual = bad line. Helps the user identify which line is "lying" to the solver.

### 4. EXIF focal length prior (future)
If the plate's EXIF has a reliable focal length + sensor size, we could bypass the 2-VP orthocenter focal derivation and accept any VP configuration (even non-orthogonal in world). For conform'd plates, EXIF is often stripped, so this is a "when we have metadata" feature.

### 5. Stray debug markers, legacy files (from v1 passoff, still open)
- Delete `matchbox/` files (abandoned approach).
- Delete `flame/apply_solve.py`, `flame/solve_and_update.py` (abandoned Matchbox path).
- Keep `flame/action_export.py` (shared helpers) and `flame/rotation_diagnostic.py` (useful tool).

---

## Trace file

`/tmp/forge_camera_match_trace.json` — written on every solve. Fields of interest:
- `inputs.origin_px`, `inputs.cam_back_requested` (user-specified) + `inputs.cam_back_resolved` (actual value used)
- `stages.origin_px_resolved` — final origin pixel (after auto-default if user didn't drag)
- `stages.origin_in_cam`, `stages.cam_position_world` — the position math
- `stages.cam_rot_cam_to_world` — solver's cam→world (OpenGL convention, -Z forward)
- `stages.cam_rot_flame_convention` — now **equals** `cam_rot_cam_to_world` (no RY_180 flip); left in trace for clarity
- `stages.flame_euler_deg` — (rx, ry, rz) pushed to Flame
- `stages.R_recon_matches_cam_rot_flame` — self-consistency check, should always be true
- `applied_to_flame` — appended on Apply click; contains read-back position/rotation/fov/focal/film_type from the Flame camera after Apply

---

## Known working test setup

- Desktop: `gen_0260_v00`
- Clip: `testImage` (5184×3456, aspect 1.5:1)
- VP1 = -X on horizontal wall grout, VP2 = -Y on vertical grout (mortar lines between bricks)
- Solved focal ~40–42mm, vfov ~32–34°
- Camera position ~(2500, 2000, 5000) in Flame world units
- axis1 at origin (scale 100,100,100) + surface1 child renders on the wall plane. Residual in-plane rotation visible; next session's job to drive it down via 3-line mode.
