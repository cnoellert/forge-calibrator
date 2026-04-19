# forge-calibrator — Session Passoff (v6.2)

## Current state — Multi-frame animated camera round-trip shipping in Flame via ASCII-FBX bridge; next milestone is the seamless Blender addon (GSD-scoped)

## Session v6.2 recap (2026-04-19, same-day follow-on to v6.1)

- **The big pivot: animated camera I/O goes through ASCII FBX, not PyAttribute keyframing.** Live-probing Flame's `PyAttribute` surfaced that it exposes only `get_value` / `set_value` / `values`-as-bounds (tuple of `(min_bounds, max_bounds)`, NOT a keyframe list). `PyCoNode` and `PyActionNode` have no animation methods either. Attempting to drive the timebar via `flame.batch.current_frame.set_value(f)` with `auto_key=True` crashed Flame twice in a row — that path is toxic and won't be probed again. The surviving route is `PyActionNode.export_fbx(bake_animation=True, only_selected_nodes=True)` for reads and `PyActionNode.import_fbx(...)` for writes, letting Flame's own baker handle keyframing. See `memory/flame_keyframe_api.md`.
- **Blender rejects ASCII FBX; FBX Python SDK wheel is cp310 only.** Flame's `export_fbx` always emits ASCII FBX 7.7.0. Blender 4.5's `bpy.ops.import_scene.fbx` explicitly fails on ASCII inputs. The Autodesk FBX Python SDK ships as a `cp310` wheel; Flame 2026.2.1 bundles Python 3.11.5 so the wheel won't load in-process. Assimp isn't installed. The pragmatic answer: ship our own narrow ASCII FBX parser + writer, scoped to camera + AnimCurve data only.
- **`forge_flame/fbx_io.py` lands.** Thin wrapper around `action.export_fbx` / `import_fbx` that enforces Perspective-camera exclusion (built-in viewport cam, not keyframable, suspected bake-crash cause per `memory/flame_perspective_camera.md`), manages the `selected_nodes` save/restore dance for `only_selected_nodes=True`, and narrows import defaults for the camera-round-trip use case (`cameras=True`, everything else off, `auto_fit=False` so the viewport doesn't re-navigate).
- **`forge_flame/fbx_ascii.py` lands.** Tokenizer (handles strings, numbers, identifiers, the `*N { a: ... }` array form) + recursive-descent parser into `FBXNode` trees + tree serializer + camera/AnimCurve extractor (`fbx_to_v5_json`) + template-driven writer (`v5_json_to_fbx`). The writer mutates a real Flame-emitted FBX template (`forge_flame/templates/camera_baked.fbx`, captured from a live probe) rather than building structure from scratch — we inherit Flame's exact Definitions + Connections shape so `import_fbx` accepts our output without fuss. Exact NTSC FPS ratios (23.976 = 24000/1001) used for KTime conversion so round-trips land on integer frame numbers.
- **Hook rewire — both export and import handlers replaced.** `_export_camera_to_blender` now routes `action.export_fbx` → `fbx_ascii.fbx_to_v5_json` → existing `bake_camera.py` (unchanged — already multi-frame capable from v6's sketch). Export dialog drops the `@ frame` field; batch range is auto-detected from `flame.batch.start_frame + duration`. `_import_camera_from_blender` now routes extracted JSON → `fbx_ascii.v5_json_to_fbx` → `fbx_io.import_fbx_to_action`. Import creates a **new** camera (original target preserved) rather than overwriting — `import_fbx` has no update-in-place mode, and preserving the original is non-destructive. Collision naming: Flame auto-appends `1`/`2`/etc., so an import against existing `Default` produces `Default1`.
- **End-to-end live validation on Flame 2026.2.1.** Synthetic v5 JSON with `position=(0, 0, 4000)`, `rotation=(0, 0, 0)`, `focal=35mm`, `film_back=36mm` → our writer → `import_fbx` → Flame read-back: position exact, rotation exact, focal within 7e-5mm (float32), FOV = 54.43° (matches 2·atan(36/70)). For a 3-frame input, the FBX carries `KeyTime: *3` with KTimes `0, 19263476732, 38526953465` at 23.976fps — correct NTSC ratio.
- **Test count 194 → 264 (+70).** `tests/test_fbx_io.py` — 19 tests for Perspective filtering, selection save/restore, kwarg propagation, failure modes. `tests/test_fbx_ascii.py` — 51 tests covering tokenizer (empty, comments, whitespace, all number forms, bare-identifier values, the `*N` array prefix), parser (empty/scalar/nested/Properties70/Connections/array-flattening), KTime conversion round-trips across 23.976/24/25/30/60 fps, live-fixture extraction, serializer round-trip (parse → emit → parse), writer round-trip for position/rotation/focal/frame numbers, writer guards (empty frames, missing file, camera rename).
- **Known-to-future-self:** Flame's batch menu dict is captured at hook-registration time and the `gc`-based re-exec reload pattern does **NOT** refresh it. After changing a menu handler, a Flame restart is mandatory for the UI to dispatch the new code. The gc/exec pattern still works for module globals — just not menu callbacks. See `memory/flame_module_reload.md` (updated with this caveat).

## What's next (GSD milestone — seamless Blender↔Flame bridge)

The animated round-trip works but the UX still bounces off disk in three places (`.fbx`, `.json`, `.blend`) and requires the user to alt-tab back to Flame to trigger import. The cleaner shape: a Blender-side addon with a "Send to Flame" button that reads stamped metadata off the camera's custom properties (`forge_bake_action_name`, etc.) and `POST`s extract-and-import to forge-bridge's `127.0.0.1:9999/exec` endpoint. No user round-trip to Flame's menu. This is larger and cross-repo (forge-bridge becomes a production dependency requiring auto-start config), so it's being scoped under GSD rather than the informal session-notes flow.

Phases under the milestone:
1. **Polish** — intermediate files to `tempfile.mkdtemp()` cleaned on success; auto-launch Blender on export (replacing `reveal_in_file_manager`); stamp `forge_bake_action_name` + `forge_bake_camera_name` as camera custom properties on bake so the Blender addon knows its target.
2. **Blender addon** — new `tools/blender/flame_send_addon.py` with a 3D-viewport sidebar panel button, reads the stamped metadata, posts to forge-bridge.
3. **forge-bridge deploy story** — `install.sh` extension (or separate installer) that configures the bridge to start with Flame. Likely a launchd plist on macOS, systemd unit on Linux.
4. **E2E validation + docs** — full bake→edit→send cycle without alt-tabbing to Flame; update of the CAMERA-MATCH user doc.

---

## Session v6.1 recap (2026-04-19, same-day follow-on to v6.0)

- **Batch UI button landed and verified in live Flame.** Right-click an Action in Batch → "Camera Match" submenu now has "Export Camera to Blender" and "Import Camera from Blender" alongside "Open Camera Match". Full Flame → JSON → .blend → (edit in Blender) → JSON → Flame loop is clickable.
- **Orchestration split into `forge_flame/blender_bridge.py`.** Kept deliberately Flame-free and Qt-free: Blender-binary discovery (env override → platform defaults → PATH), bake/extract script resolution (env override → dev checkout → install path), CLI composition split from `subprocess.run` so argv shape is unit-testable, and `reveal_in_file_manager()` for macOS Finder / Linux xdg-open. Hook imports it for the two new handlers.
- **Scope decision: Export/Import on Action, Open on clip.** Open Camera Match stays on clip context — its workflow starts from a plate. Export/Import go on Action context — their workflow starts from a solved camera that already lives inside an Action. First ship had all three on clip scope, which put Export/Import in the wrong place; caught and fixed in the same Flame session. New helpers `_scope_batch_action` and `_first_action_in_selection` use type-string match (`_val(item.type) == "Action"`) because `flame.PyActionNode` isn't consistently exposed as a Python class across Flame versions.
- **Plate metadata from first clip in batch.** Export needs width/height/frame for the JSON, but the Action-context invocation doesn't have them directly. `_scan_first_clip_metadata()` scans `flame.batch.nodes` for the first PyClipNode and uses its `(width, height, start_frame)` as defaults; user confirms/edits via a single `WxH @ frame` dialog. Falls back to 1920x1080 @ 1 if no clip in batch.
- **`install.sh` now deploys `tools/blender/`.** Added `SOURCE_BLENDER_SCRIPTS` / `BLENDER_SCRIPTS_DEST` constants, source presence check, third `_sync_dir` call. At runtime `blender_bridge` resolves to `/opt/Autodesk/shared/python/tools/blender/` on installed Flame, or `<repo>/tools/blender/` in dev.
- **Test count 171 → 194.** `tests/test_blender_bridge.py` — 23 tests covering env override precedence for Blender bin and scripts, platform defaults, PATH fallback, error message content, CLI argv composition (including the `--` separator position and the `--create-if-missing` gate). Blender itself isn't required to run the tests.

## Session v6 recap (2026-04-19)

- **Flame ↔ Blender round-trip is functional end-to-end.** Three new Python modules plus a selftest shell script implement the pipeline that was sketched in v5. Validated against a live solved Flame camera (40° vfov, position ~5000 pixels, identity rotation): FOV round-trips to 0 delta, position to 0 delta, rotation drifts ≤1e-5° (Blender's float32 matrix_world — invisible at render scale).
- **Helpers moved to `forge_core.math.rotations`.** `compute_flame_euler_zyx` and new `flame_euler_to_cam_rot` (forward Euler → 3x3, exact inverse) now live there. Pure numpy, no host bindings — Blender-side and future-host-side code can import without pulling the solver or cv2 or OCIO. `forge_flame.adapter` re-exports both names; every existing import keeps working.
- **Single-frame `forge_flame.camera_io` bridges Flame's PyAction to the v5 JSON contract.** Reads/writes via `cam.position`, `cam.rotation`, `cam.fov` (not `cam.focal` — the hook's note about Super 16 applies here too). Handles film-back override correctly: when user pins `film_back_mm=36.0` for full-frame parity, focal is recomputed from (fov, new film_back) so the stored trio is self-consistent.
- **Test count 129 → 171.** `tests/test_blender_roundtrip.py` (13 tests — axis-map sanity, Euler helper inverse property, bake/extract math on three known-answer cameras). `tests/test_camera_io.py` (29 tests — FOV ↔ focal ↔ film-back converter correctness and input validation). Everything runs without Blender; `tools/blender/roundtrip_selftest.sh` exercises the full pipeline when Blender is available.

## Session v6 corrections to v5's Blender sketch

Three things in the v5 sketch turned out wrong or incomplete. Future-you should trust this section over the "Sketch" section below:

- **`--scale` is position-only, not lens/sensor.** v5 said "divides position + focal + sensor in lockstep to preserve FOV." That's wrong: Blender min-clamps `cam.data.lens` and `cam.data.sensor_width` at 1.0mm, so any scale factor larger than the focal value silently clips to 1.0 and the extract reads back `scale` as the lens value. FOV depends only on the lens/sensor *ratio*, which is preserved regardless of absolute values, so there's no reason to scale lens/sensor at all. Bake divides position only; extract multiplies position only.
- **`sensor_fit='VERTICAL'` required.** Blender's default `sensor_fit='AUTO'` treats `sensor_width` as horizontal for wide-aspect plates. Our JSON contract's `film_back_mm` is the vertical sensor dimension (to match Flame's `cam.fov` being VFOV). Bake pins `sensor_fit='VERTICAL'` and writes to `sensor_height`; extract reads `sensor_height`. Without this, Flame-internal round-trip still works (the same misinterpretation cancels out), but Blender's rendered FOV disagrees with Flame's — visible the first time you look through the camera in Blender.
- **Flame's Python console caches modules across runs.** Flame's long-lived Python interpreter keeps `sys.modules` warm across script runs. Updating `forge_flame/camera_io.py` on disk does not reload a session that already imported it. Any camera_io test script needs a `sys.modules` purge + re-import at the top, or it'll debug old bytecode. Cost us a confused round-trip result this session when the updated export hadn't actually loaded.

The sketch's axis-map (`Rx(+90°)`), rotation composition (`R = Rz(rz) · Ry(-ry) · Rx(-rx)`), and data contract schema all held up correctly.

## Session v5 recap (2026-04-17 → 2026-04-18)

- **OCIO path portability** — hardcoded `2026.0` in the OCIO config path replaced with a glob resolver (`resolve_flame_aces2_config`) that picks newest `flame_configs/*/aces2.0_config`. Auto-tracks Flame upgrades.
- **`install.sh` landed** — preflight checks for forge env, Wiretap CLI, Flame-bundled PyOpenColorIO, and a resolvable OCIO config. Drops a stub `__init__.py` to stop Flame's loader from namespace-drifting.
- **Big refactor: `forge_core/` and `forge_flame/` packages.** The 2242-line hook is now 1697 lines. Host-agnostic pieces (solver, OCIO pipeline, image-buffer repair, VP fitting) live in `forge_core/`; Flame-specific adapters (Wiretap reader, ZYX-Euler / cam_back / trace adapter) live in `forge_flame/`. Hook is orchestration only. Both packages ship as siblings of `camera_match/` under `/opt/Autodesk/shared/python/`.
- **Test coverage up** — 46 → 129 passing tests. New suites: `test_hook_parity.py` (adapter math + Flame-Euler round-trip + every axis pair), `test_image_buffer.py` (magic-byte gating, header strip, flip+swap combos).

## Import map (for trafFIK reuse)

    # Pure math — numpy only, no host bindings. Safe to import from any host.
    from forge_core.math.rotations import (
        compute_flame_euler_zyx, flame_euler_to_cam_rot,
    )
    from forge_core.solver.solver import solve_2vp
    from forge_core.solver.fitting import fit_vp_from_lines, line_to_vp_residual_px
    from forge_core.colour.ocio import OcioPipeline, resolve_flame_aces2_config
    from forge_core.image.buffer import (
        decode_image_container, decode_raw_rgb_buffer, apply_ocio_or_passthrough,
    )

    # Flame-only — needs Wiretap SDK, Flame-bundled Python:
    from forge_flame.wiretap import get_clip_colour_space, extract_frame_bytes
    from forge_flame.adapter import solve_for_flame, compute_flame_euler_zyx
    from forge_flame.camera_io import (
        export_flame_camera_to_json, import_json_to_flame_camera,
        vfov_deg_from_focal, focal_from_vfov_deg, film_back_from_fov_focal,
    )

    # Blender-side scripts (invoked via blender --background --python):
    #   tools/blender/bake_camera.py    — Flame JSON -> .blend
    #   tools/blender/extract_camera.py — .blend  -> Flame JSON
    # Blender ships its own Python with numpy + mathutils; these scripts
    # are self-contained and don't import forge_core / forge_flame.

---

## Previous state (v4) — Camera Match is feature-complete; next is packaging it as an installer

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

### 1. Multi-frame keyframe support in camera_io
Current `camera_io` v1 is single-frame only — matches what forge-calibrator produces today (static solves). When animated Flame cameras need round-tripping, extend `export_flame_camera_to_json` to walk Flame's PyAttribute keyframe API (untested territory; need live Flame to confirm the call shape — probably `attr.add_keyframe(frame, value)` or similar) and emit a multi-frame JSON. Bake and extract already handle multi-frame JSON correctly, so this is Flame-side only.

### 2. Blender-only install mode (carried from v6 open item #4)
The v5 installer landed but still assumes the forge conda env. For users wanting to deploy only the Blender round-trip slice (which needs neither cv2 nor OCIO, just numpy which Flame's bundled Python has anyway), a `--mode=blender-only` install mode that skips the forge env preflight would reduce deployment friction. The real blocker for "Flame-bundled Python only" mode is the cv2 call sites in Camera Match itself; see the v6 chat discussion about auditing those.

### 3. Cleanup of dead code (carried from v5)
`_JPEG_PRESET` constant and `_NoHooks` class still present but unused after the Wiretap migration. `flame/apply_solve.py`, `flame/solve_and_update.py`, `matchbox/` from earlier passoffs are still candidates for removal. Also: `_apply_camera` still inlines the action-camera discovery loop that's now available as `_find_action_cameras()` at module level — fold them together next time that path is touched (noted in the helper's docstring).

### 4. UI testing of "Drop axes at line endpoints" (carried from v5)
End-to-end Apply path with the checkbox checked hasn't been driven through the UI yet. Math is verified (`_back_project_to_plane` and `endpoint_axes` work in isolation); button-click path needs a smoke test on a real solve.

### 5. Optional: target colour space dropdown (carried from v5)
OCIO target is hard-coded to display=`sRGB - Display` + view=`ACES 2.0 - SDR 100 nits (Rec.709)`. Users with HDR monitors or P3 displays would benefit from a Target dropdown. Low priority.

### 6. Stylistic polish (carried from v5)
Source / Frame controls lack QSS styling for `QSpinBox` / `QComboBox` row overrides. Picks up global rules but could be tightened.

### 7. Nice-to-have: auto-detect plate metadata from Action's Back input
Export currently defaults plate width/height/frame from "first clip in batch" and lets the user confirm. The ideal UX would walk the Action's Back input (the clip wired to it by Camera Match's Apply) and pick up its metadata automatically. Blocked on knowing the Flame API for querying a node's input connections from the Python side — couldn't confirm the call shape without a live session.

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

---

## Flame ↔ Blender camera round-trip: as-built (v6.1)

The v5 sketch is implemented AND wired into Flame's batch menu. This section documents the actual on-disk state, the on-disk files, their CLI shape, and the validated round-trip numbers. **Prefer this section over any residual sketch prose above** — three specific claims in the sketch turned out to need correction, captured in "Session v6 corrections to v5's Blender sketch" earlier in this document.

### What lives where

| File | Role |
|---|---|
| `forge_core/math/rotations.py` | Pure-math helpers: `compute_flame_euler_zyx`, `flame_euler_to_cam_rot`. Numpy only. |
| `forge_flame/adapter.py` | Re-exports both helpers for back-compat. `solve_for_flame` still lives here. |
| `forge_flame/camera_io.py` | Flame PyAction camera ↔ v5 JSON. Single-frame v1. Handles film-back override correctly. |
| `forge_flame/blender_bridge.py` | Flame-free, Qt-free subprocess orchestration: Blender binary + script path resolution, argv composition, `subprocess.run` wrappers, `reveal_in_file_manager`. |
| `flame/camera_match_hook.py` | Adds `_export_camera_to_blender` + `_import_camera_from_blender` handlers and the `_scope_batch_action` / `_first_action_in_selection` / `_scan_first_clip_metadata` / `_find_action_cameras(only_action=...)` / `_pick_camera` helpers. `get_batch_custom_ui_actions` registers the two new menu items. |
| `tools/blender/bake_camera.py` | Runs in Blender. JSON → `.blend`. Self-contained (mathutils, not forge_core). |
| `tools/blender/extract_camera.py` | Runs in Blender. `.blend` → JSON. Self-contained. |
| `tools/blender/sample_camera.json` | 3-frame fixture for smoke testing. |
| `tools/blender/roundtrip_selftest.sh` | Shell runner: bake + extract + diff against `sample_camera.json`. |
| `tests/test_blender_roundtrip.py` | 13 tests (no Blender needed — exercises the math). |
| `tests/test_camera_io.py` | 29 tests for the FOV ↔ focal ↔ film-back converters. |
| `tests/test_blender_bridge.py` | 23 tests for path resolution + CLI argv composition. |
| `install.sh` | Deploys all three siblings (`forge_core/`, `forge_flame/`, `tools/blender/`) under `/opt/Autodesk/shared/python/`. |

### Pipeline sequence (4 legs)

```
Flame solved camera
  ─► forge_flame.camera_io.export_flame_camera_to_json       (leg 1)
  ─► /tmp/flame_cam.json
  ─► blender --background --python tools/blender/bake_camera.py -- \
        --in cam.json --out out.blend --scale 1000 --create-if-missing   (leg 2)
  ─► /tmp/forge_rt.blend
  ─► [optional: edit camera in Blender]
  ─► blender --background out.blend --python tools/blender/extract_camera.py -- \
        --out cam.json                                        (leg 3)
  ─► /tmp/forge_rt.json
  ─► forge_flame.camera_io.import_json_to_flame_camera        (leg 4)
  ─► Flame camera (round-trip target)
```

### Conventions (final, tested)

- **World up:** Flame Y-up → Blender Z-up via `Rx(+90°)` left-multiplied into the 4x4 world matrix. Pure left-multiplication is valid because both cameras share OpenGL's `-Z_local` forward convention (no camera-local correction needed).
- **Rotation decomposition:** `R = Rz(rz) · Ry(-ry) · Rx(-rx)`. Verified in `forge_core/math/rotations.py` and tested in `test_blender_roundtrip.py` + `test_hook_parity.py`.
- **Film back:** JSON's `film_back_mm` is the **vertical** sensor dimension (matches Flame's `cam.fov` being VFOV). Bake writes to `cam.data.sensor_height` with `sensor_fit='VERTICAL'`. Extract reads `sensor_height`.
- **Scale:** `--scale` divides POSITION only. Lens and sensor stay in native mm (Blender min-clamps them at 1.0mm and FOV depends only on their ratio). `forge_bake_scale` stamped on `cam.data` for lossless extract.
- **Rotation keyframing:** quaternion. Bake sets `rotation_mode='QUATERNION'` and keyframes `rotation_quaternion` to be gimbal-safe across animated frames.

### Data contract (v6, unchanged from v5 sketch)

```json
{
  "width": 5184,
  "height": 3456,
  "film_back_mm": 36.0,
  "frames": [
    {"frame": 1001,
     "position": [x, y, z],
     "rotation_flame_euler": [rx_deg, ry_deg, rz_deg],
     "focal_mm": 42.0}
  ]
}
```

Raw Flame values, no axis swap at export — Blender side does the swap. Multiple frames supported on bake/extract; camera_io v1 is single-frame only.

### Validated numbers (2026-04-19, live Flame test)

Starting state: Flame camera at `(0, 0, 4747.64)`, rotation `(0, 0, 0)`, vfov=40°, film_back_mm=36.0 override.

| Metric | Delta after full 4-leg round-trip |
|---|---|
| Position | 0.00e+00 (exact) |
| Rotation | ≤1.20e-05° (Blender float32 matrix_world) |
| FOV | 0.00e+00 (exact — pure float64 through camera_io) |

The rotation drift is the Blender-side float precision floor and is invisible at any reasonable render scale.

### Where to pick it up next

Historically this section pointed at multi-frame keyframing — that work shipped in v6.2 but via a different route than sketched here. PyAttribute has no keyframe API (see `memory/flame_keyframe_api.md`), so the implementation went through `PyActionNode.export_fbx` + a custom ASCII-FBX parser/writer in `forge_flame/fbx_ascii.py` rather than walking PyAttribute keyframes directly. The bake/extract Blender scripts described here were preserved intact — FBX becomes an intermediate that gets converted to the same v5 JSON contract they already consumed.

See the top of this file for the v6.2 recap and the next-milestone (seamless Blender↔Flame bridge) plan.
