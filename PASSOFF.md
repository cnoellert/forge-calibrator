# forge-calibrator — Session Passoff (v4)

## Current state — Camera Match is feature-complete; next is packaging it as an installer

This session focused on (1) tightening the calibration math, (2) integrating the tool with Flame's batch in a real way (Action wiring, schematic placement, axis drops), and (3) replacing the broken PyExporter preview pipeline with a Wiretap-based single-frame reader plus OCIO-backed colour management. Camera Match is now usable on real production plates with native Flame colour decoding and proper rolloff.

---

## Big wins this session

### Solver / math
- **Per-line residual labels in 3-line mode.** Each user-drawn line gets a small `Δ<N>px` pill near its midpoint showing the perpendicular distance from that line to the fitted VP. Zero residual = exact agreement; large residual = "this line is lying to the solver." Only shown in 3-line mode (2-line is always exact intersection).
- **Critical 3-line packing fix.** `_solve_lines._pack` was passing user line 0 as-is to `_solve`, which recomputes the VP via two-line intersection. In 3-line mode the LSQ-fitted VP doesn't sit exactly on user line 0, so the solver was using a VP biased toward whichever line happened to be `lines[0]`. New pack passes two synthetic "lines" that **both terminate at the fitted VP**, so `line_isect` returns it exactly. 2-line mode behavior unchanged (still collapses to exact intersection).

### Apply pipeline
- **Filter Perspective from camera dropdown.** Flame's Action node has a built-in "Perspective" viewport camera that's almost never the intended apply target — overwriting it changes the Action's tumble view, not the rendered scene. Filtered out of the dropdown. "Default" (the render camera) and any user-named cameras still appear.
- **Wire new Action's Back to the calibrated clip.** On "Create new Action" we call `flame.batch.connect_nodes(clip, "Default", action, "Default")` — `"Default"` on Action's input maps to Background per the docs.
- **Position new Action near the clip in the schematic.** `action.pos_x.set_value(int(clip.pos_x.get_value()) + 370)`. Note: `pos_x`/`pos_y` are int-typed PyAttributes; `set_value()` rejects floats with a confusing C++ converter error. Always cast to `int()`.
- **Optional axes at line endpoints.** New "APPLY OPTIONS → Drop axes at line endpoints" checkbox. When on, every active VP line endpoint is back-projected through the solved camera onto the VP plane at world origin, and an Axis is dropped at each world position inside the new/selected Action. Named `knot_vp1_L0a`, `knot_vp1_L0b`, etc. Useful for anchoring geometry to real scene features (corners, grout intersections).

### Frame selection + media reading (the hard part)
- **Frame spinner for multi-frame clips.** Range = `[start_frame, start_frame + duration - 1]` from `clip.clip.start_frame`. Hidden for 1-frame stills. Triggers a re-read on change.
- **Replaced PyExporter with Wiretap CLI.** `flame.PyExporter` exports image-sequence presets ignore in/out marks for some sources — we kept getting full-clip dumps even with `export_between_marks = True`. Direct cv2/ffmpeg can't decode Sony/ARRI proprietary MXF wrappers (`could not resolve file descriptor strong ref`). Switched to `/opt/Autodesk/wiretap/tools/current/wiretap_rw_frame` which reads one frame by Wiretap node ID. ~1.5s per frame for a 4608×3164 32-bit float MXF. See `memory/wiretap_frame_read.md` for the recipe.
- **Fixed type mismatch in `_launch_camera_match`.** Was passing `item.clip` (PyClip) but `_open_camera_match` needs the PyClipNode for `pos_x`, `connect_nodes`, etc. Now passes the node directly; `_read_source_frame` reaches through `.clip` for the PyClip-only `get_wiretap_node_id()`.

### Colour management
- **OCIO preview transform via ACES 2.0 SDR.** Source dropdown in the side panel; user picks ARRI LogC4 / LogC3 / Linear AWG4 / ACEScg / etc. Pipeline is **DisplayViewTransform** (not `getProcessor(src, dst)`) using config `aces2.0_config/config.ocio` with display=`sRGB - Display`, view=`ACES 2.0 - SDR 100 nits (Rec.709)`. This gives **soft highlight rolloff** instead of hard-clipping to white — important for marking VP lines against bright skies.
- **Auto-detect source colour space from Wiretap.** `WireTapClipFormat.colourSpace()` returns the tagged source (`"LogC4 / ARRI Wide Gamut 4"`, `"Rec.709 video"`, etc.). At open time we map it to a dropdown option. For display-encoded sources (Rec.709 video / sRGB JPEGs) the dropdown auto-selects `"Display passthrough"` — no transform applied, since the bytes are already display-ready. Wiretap tag also lands in the dropdown's tooltip for sanity-checking.
- **GBR channel reorder + vertical flip on raw buffers.** Wiretap's raw float buffer is bottom-up (OpenGL convention) AND delivered as **GBR**, not RGB despite the `format_tag: rgb_float_le` label. Empirically: full reverse `[::-1, :, ::-1]` left G/B swapped; correct mapping is `arr[::-1][..., [2, 0, 1]]`. There's also a 16-byte header before the pixel payload.

---

## Key files + where things live

### `flame/camera_match_hook.py` (single 1900-line file)

- `_fit_vp(lines_px)` and `_line_residual_px(...)` — least-squares VP fit + scoring helper.
- `_solve_lines(...)` and `_solve(...)` — core math; the `_pack` fix lives here.
- `_read_source_frame(clip, target_frame=None, source_colourspace=None)` — Wiretap-based reader. Returns uint8 RGB. Handles uint8 sources (passthrough), float sources (OCIO DisplayViewTransform when source_colourspace is set, else clip-and-quantise passthrough).
- `_clip_wiretap_colour_space(clip)` and `_map_wiretap_cs_to_dropdown(wt_cs)` — auto-detect helpers.
- `_get_ocio_processor(src_cs)` — caches CPU processors per source. Uses `OCIO.DisplayViewTransform` so the ACES RRT+ODT actually applies.
- `ImageWidget` — viewport with VP handles, plane overlay, residual labels, back-projection helper, `endpoint_axes()` method.
- `CameraMatchWindow` — side panel UI: Frame spinner, Source dropdown, VP axis combos, mode toggles, Display group, Solved Camera readout, Apply options group, Apply / Close buttons.
- `_launch_camera_match(selection)` and `get_batch_custom_ui_actions()` — hook entry points.

### Memory files (`/Users/cnoellert/.claude/projects/-Users-cnoellert-Documents-GitHub-forge-calibrator/memory/`)
- `flame_rotation_convention.md` — unchanged.
- `flame_bridge.md` — unchanged.
- `forge_ui_style.md` — unchanged.
- **`wiretap_frame_read.md` — NEW.** wiretap_rw_frame recipe + GBR/flip/header gotchas.
- **`flame_module_reload.md` — NEW.** namespace-package drift workaround (gc + exec into live module dict).

### Deploy + reload workflow
```bash
cp /Users/cnoellert/Documents/GitHub/forge-calibrator/flame/camera_match_hook.py \
   /opt/Autodesk/shared/python/camera_match/camera_match.py
rm -rf /opt/Autodesk/shared/python/camera_match/__pycache__
```
Then reload (the standard `importlib.reload(sys.modules["camera_match"])` is fragile — see `memory/flame_module_reload.md` for the gc-based exec-injection that actually picks up new code in live UI):
```python
import sys, gc, types
src = open('/opt/Autodesk/shared/python/camera_match/camera_match.py').read()
code = compile(src, '/opt/Autodesk/shared/python/camera_match/camera_match.py', 'exec')
for o in gc.get_objects():
    if (isinstance(o, types.ModuleType)
        and getattr(o,'__name__','')=='camera_match'
        and (getattr(o,'__file__',None) or '').endswith('.py')):
        exec(code, o.__dict__)
        sys.modules['camera_match'] = o
```
**Always close + reopen the Camera Match window after reload** — Qt dialog state is captured at construction.

---

## Open items (priority order)

### 1. Installer (next session's primary task)
The tool currently requires manual `cp` to `/opt/Autodesk/shared/python/camera_match/` and assumes a working `forge` conda env at `~/miniconda3/envs/forge/` with numpy / opencv-python / PyOpenColorIO. Need an installer that:
- Copies the hook to the right location.
- Verifies (or installs) the forge conda env with required deps.
- Confirms the wiretap CLI exists at `/opt/Autodesk/wiretap/tools/current/wiretap_rw_frame`.
- Confirms an OCIO config exists at the expected ACES 2.0 path.
- Drops a stub `__init__.py` in the install dir to prevent the namespace-package drift documented in memory.

### 2. Cleanup of dead code
`_JPEG_PRESET` constant and `_NoHooks` class are still present but unused after the Wiretap migration. Safe to delete:
```python
_JPEG_PRESET = "/opt/Autodesk/shared/export/presets/file_sequence/JPEG_CameraMatch.xml"
class _NoHooks(object): ...
```
Also `flame/apply_solve.py`, `flame/solve_and_update.py`, `matchbox/` from earlier passoffs are still candidates for removal.

### 3. UI testing of "Drop axes at line endpoints"
The end-to-end Apply path with the checkbox checked hasn't been driven through the UI yet. Math is verified (`_back_project_to_plane` and `endpoint_axes` work in isolation), and Action axis creation is verified, but the button click path needs a smoke test on a real solve.

### 4. Optional: target colour space dropdown
Currently the OCIO target is hard-coded to display=`sRGB - Display` + view=`ACES 2.0 - SDR 100 nits (Rec.709)`. For users with HDR monitors or P3 displays, a Target dropdown would be useful. Low priority.

### 5. Stylistic polish
The Source / Frame controls don't have QSS styling for `QSpinBox` and `QComboBox` overrides specific to those rows — they pick up the global rules but could be tightened.

---

## Trace file

`/tmp/forge_camera_match_trace.json` — written on every solve. Contents unchanged from v3:
- `inputs.origin_px`, `inputs.cam_back_resolved`, `stages.origin_px_resolved`
- `stages.cam_position_world`, `stages.cam_rot_cam_to_world`, `stages.flame_euler_deg`
- `applied_to_flame` block when Apply is clicked

---

## Known working test setup

- Desktop: `gen_0260_v00`
- Stills clip: `testImage` (5184×3456 sRGB JPG/TIFF) — auto-detects as Display passthrough
- Moving clip: `A_0001C004_260216_051739_h1CNN` (4608×3164, 3667 frames, ARRI LogC4 / Wide Gamut 4 MXF) — auto-detects as ARRI LogC4
- Frame range for the MXF: 1001..4667
- Both decode cleanly through Wiretap; both render correctly with auto-selected colour space
