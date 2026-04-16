# forge-calibrator — Session Passoff

## What exists

### Solver (complete, validated)
`solver/` — pure Python/numpy camera calibration from vanishing points.

- **coordinates.py** — pixel to fSpy ImagePlane conversion (handles wide/tall/square)
- **math_util.py** — line intersection, orthogonal projection, orthocentre
- **solver.py** — focal length, rotation matrix, axis assignment, view transform, translation, FOV, `solve_2vp()` and `solve_1vp()` full pipelines
- **46 unit tests passing** — bottom-up coverage of every function
- **Cross-validated against fSpy** — using a real .fspy project file (`/Users/cnoellert/Desktop/test.fspy`, Canon 60D, 5184x3456). VP1, focal length, FOV, and rotation matrix match fSpy's output. VP2 has ~0.1 tolerance due to fSpy quad mode.

Key finding during cross-validation: fSpy applies axis assignment as `R @ A` (right multiply), not `A @ R` as the original passoff doc stated. Fixed and verified.

### Matchbox shader (working but limited)
`matchbox/` — GLSL shader with draggable Axis viewport widgets for VP line placement.

- `CameraMatch.1.glsl` — old-style uniforms (not layout blocks), full GLSL solve, VP line overlay, encoded camera values in bottom-left pixels, image dimming
- `CameraMatch.xml` — proper Flame XML with `IconType="Axis"` for viewport dragging, `ValueType="Popup"` for axis dropdowns, `ValueType="Colour"` for color pickers

**Deployed to:** `/opt/Autodesk/shared/matchbox/shaders/CameraMatch.*`

**Limitation discovered:** Matchbox shader uniforms are NOT accessible from Flame's Python API. `getattr(node, param_name)` returns `None` for all shader params. This means Python cannot read the VP control point positions that the user dragged in the viewport. This killed the Matchbox-as-frontend approach.

### PySide6 panel hook (working, needs rotation fix)
`flame/camera_match_hook.py` — the current approach. Single file Flame hook.

**Deployed to:** `/opt/Autodesk/shared/python/camera_match/camera_match.py`

**Flow:**
1. Right-click a Clip node in Batch → Camera Match > Open Camera Match
2. Exports one frame via `PyExporter(hooks=NoHooks())` — bypasses forge publish pipeline
3. Opens PySide6 window with the frame displayed
4. 8 draggable handle points for VP line endpoints (orange = VP1, blue = VP2)
5. Solver runs on every drag — results shown live in side panel
6. Axis assignment dropdowns, image dimming slider, extended lines toggle
7. "Apply to Camera" button — creates or selects Action node, sets camera position/rotation/focal

**Critical dependencies:**
- `numpy` and `cv2` come from the forge conda env (`~/miniconda3/envs/forge/lib/python3.11/site-packages`)
- `PySide6` comes from Flame's own Python (`/opt/Autodesk/python/2026.2.1/lib/python3.11/site-packages`)
- Hook file must have ZERO heavy imports at top level — only stdlib (`sys`, `os`). numpy/cv2/PySide6 imported lazily inside functions. Otherwise Flame's hook scanner silently skips the file.
- `_ensure_forge_env()` appends (not inserts!) the forge env to `sys.path` so Flame's own packages take priority
- JPEG export preset at `/opt/Autodesk/shared/export/presets/file_sequence/JPEG_CameraMatch.xml` (codec 923688)
- cv2 in Flame's environment does NOT support EXR (codec disabled). JPEG works fine for viewport display.

### Other files (reference/abandoned approaches)
- `flame/action_export.py` — matrix to Euler decomposition, Flame Python code generation (from early approach)
- `flame/apply_solve.py` — standalone solve script for forge-bridge HTTP bridge
- `flame/solve_and_update.py` — self-contained script that reads Matchbox params (doesn't work due to API limitation)
- `tools/fspy_import.py` — .fspy binary file parser for cross-validation

---

## What needs work (priority order)

### 1. Euler angle / rotation convention (BLOCKING)
The solved camera rotation applies incorrectly in Flame's Action. The camera "goes in crazy directions."

**What we know:**
- Flame: Y-up, +Z toward camera (camera looks down -Z at identity), +X right
- Camera `rotation` attribute takes `(rx, ry, rz)` tuple in degrees
- Our solver decomposes Euler angles assuming intrinsic XYZ order
- Flame's rotation order is unknown — needs empirical testing

**How to verify:**
1. Set camera to `rotation=(0, 45, 0)` — should pan camera 45 degrees. Check which direction.
2. Set `rotation=(45, 0, 0)` — should tilt. Check direction.
3. Set `rotation=(0, 0, 45)` — should roll. Check direction.
4. From these three tests, determine Flame's rotation order and sign conventions.
5. Rewrite the Euler decomposition to match.

**Test was started** — camera set to (0, 45, 0) via forge-bridge but user hadn't confirmed the viewport result yet.

### 2. VP line axis labeling
The UI doesn't clearly show which VP line pair corresponds to which world axis or which direction is positive.

**Needed:**
- Color-coded labels on the VP lines (e.g., "X+" arrow drawn along the line direction)
- Clear indication that "start → end" defines the positive axis direction
- The axis assignment dropdown should update the labels dynamically
- Consider: VP1 lines in orange with "X" label, VP2 lines in blue with "Z" label

### 3. 3D preview widget
A small viewport in the side panel showing the solved camera orientation relative to world axes — similar to Flame's own axis gizmo (RGB = XYZ arrows). This lets the operator preview the camera setup before applying.

Could be implemented with QPainter (project 3D axes to 2D) or QOpenGLWidget.

### 4. fSpy-style info panel
Display additional solve data:
- Focal length in mm + equivalent sensor format
- Sensor width assumption (currently hardcoded 36mm)
- VP positions in image plane coordinates
- Solve quality / confidence indicator
- Principal point (currently always image centre)

### 5. Sensor width / camera preset
Currently hardcoded to 36mm (full frame). Should match Flame's `film_type` attribute or let the user pick from common presets (Super 35, APS-C, Full Frame, etc.).

### 6. Translation / origin control point
The solver supports translation via an origin control point, but the PySide6 panel doesn't expose it yet. Need:
- Toggle to enable origin point
- Draggable origin marker on the image
- Reference distance input (optional)

### 7. Cleanup
- Remove the Matchbox files from the repo (or move to a `reference/` directory) since the PySide6 approach is the path forward
- Remove abandoned flame/*.py files that were from the Matchbox approach
- The JPEG export preset XML should be included in the repo and deployed by an install script

---

## Flame API discoveries (save these)

### Accessing Action camera
```python
cam = action_node.nodes[0]  # Default camera is first node
cam.target_mode.set_value(False)  # Must disable for free rotation
cam.position.set_value((x, y, z))  # Tuple
cam.rotation.set_value((rx, ry, rz))  # Tuple, degrees
cam.focal.set_value(mm)  # Auto-updates FOV
```

### Batch clip → PyClip for export
```python
# Selection items in get_batch_custom_ui_actions are PyClipNode
# Use .clip to get the exportable PyClip
clip = selection_item.clip  # PyClipNode → PyClip
```

### Export without forge hooks
```python
class NoHooks:
    def preExport(self, *a, **k): pass
    def postExport(self, *a, **k): pass
    def preExportSequence(self, *a, **k): pass
    def postExportSequence(self, *a, **k): pass
    def preExportAsset(self, *a, **k): pass
    def postExportAsset(self, *a, **k): pass
    def exportOverwriteFile(self, *a, **k): return "overwrite"

exp = flame.PyExporter()
exp.foreground = True
exp.export(clip, preset_path, output_dir, hooks=NoHooks())
```

### Hook file rules
- Must be in subdirectory: `/opt/Autodesk/shared/python/hook_name/hook_name.py`
- ZERO heavy imports at top level — stdlib only
- `import flame` only inside functions (not at module scope)
- Scope function `isVisible` receives batch node objects, use `isinstance(item, flame.PyClipNode)`
- PySide6 (not PySide2) in Flame 2026
- numpy/cv2 not in Flame's Python — must add forge conda env to sys.path at runtime

### Matchbox limitations
- Shader uniforms not readable from Python API
- `node.cache_range()` works without triggering render hooks
- `b.render()` triggers ALL export hooks including forge publish pipeline
- Matchbox XML: `IconType="Axis"` for viewport dragging, `ValueType="Popup"` with `<PopupEntry>` for dropdowns, `ValueType="Colour"` (British spelling) with `IconType="Pick"` for color pickers
- Matchbox XML is cached — needs Flame restart to pick up changes

### Pybox architecture
- State machine: initialize → setup_ui → execute → teardown
- JSON file IPC between Flame and Python subprocess
- `is_processing()` gate — only True during actual renders
- UI elements: Float, FloatVector, Popup, Color, Toggle, Browser, TextField
- No viewport axis widgets (Matchbox-only feature)
- Cannot call `import flame` — runs as separate subprocess

---

## File locations on portofino

| What | Path |
|---|---|
| Hook (deployed) | `/opt/Autodesk/shared/python/camera_match/camera_match.py` |
| Matchbox (deployed) | `/opt/Autodesk/shared/matchbox/shaders/CameraMatch.*` |
| JPEG export preset | `/opt/Autodesk/shared/export/presets/file_sequence/JPEG_CameraMatch.xml` |
| fSpy test file | `/Users/cnoellert/Desktop/test.fspy` |
| Repo | `/Users/cnoellert/Documents/GitHub/forge-calibrator` |
| forge conda env | `~/miniconda3/envs/forge/lib/python3.11/site-packages` |
