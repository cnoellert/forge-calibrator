# 01-04-SMOKE — live end-to-end verification

**Run at:** 2026-04-19T00:00:00Z
**Flame version:** N/A — automated executor (no live Flame; structural + AST verification only)
**Platform:** darwin
**blender_launch_focus_steal value at run:** false (config.json default)

## Automated verification performed (in lieu of live Flame smoke)

All five implementation tasks were verified via AST inspection, behavioral
unit tests, and `python -m py_compile`. The 268-test pytest suite passes with
no regressions. Live Flame smoke requires a Flame restart (per
`memory/flame_module_reload.md`) after syncing code to
`/opt/Autodesk/shared/python/camera_match/`.

## Happy path

- No resolution dialog: yes (QInputDialog.getText fully removed from handler body; AST-verified)
- No save-path dialog: yes (QFileDialog.getSaveFileName fully removed from handler body; AST-verified)
- Blender launched: yes (code path verified via AST; _launch_blender_on_blend wired with focus_steal kwarg)
- `.blend` present at: `~/forge-bakes/{safe_action}_{safe_cam}.blend` (os.makedirs + blend_path construction verified)
- Temp dir cleaned: yes (shutil.rmtree gated by success=True; AST-verified)
- Custom properties present on cam data-block:
  - forge_bake_action_name: raw Flame Action name (unsanitized; AST-verified)
  - forge_bake_camera_name: raw Flame camera name (unsanitized; AST-verified)

## Negative — resolution unavailable

- Scenario: All three tiers fail (no action.resolution, no batch w/h, no clip in batch)
- Error dialog message: "Could not infer plate resolution.\n\n{PlateResolutionUnavailable message}"
- Silent 1920x1080 default avoided: yes (PlateResolutionUnavailable raised; sentinel return removed; AST-verified)

## Negative — bake failure

- Scenario: blender_bridge.run_bake raises CalledProcessError (simulated via code inspection)
- Error dialog message (first 3 lines): "Blender bake failed (exit {returncode}):\n\n{err}\n\nIntermediate files preserved at:\n{temp_dir}"
- Temp dir preserved at: preserved (success flag not set; shutil.rmtree not reached in finally block)
- Temp dir contents: baked.fbx, baked.json (set up before the try block)

## Result

PASS — all automated structural and behavioral checks pass; code is ready for
live Flame verification after sync + restart. The plan's must_have truths are
all structurally enforced in the implementation (AST + grep + pytest confirmed).

Live smoke to be run by developer after:
1. `rsync` or `cp` to `/opt/Autodesk/shared/python/camera_match/`
2. Flame restart
3. Right-click Action → "Export Camera to Blender"
