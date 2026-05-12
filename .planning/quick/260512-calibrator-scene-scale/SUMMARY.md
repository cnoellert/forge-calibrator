---
quick_id: 260512-calibrator-scene-scale
status: complete
date: 2026-05-12
---

# Calibrator scene scale and origin projection

## Summary

Added a `SCENE SCALE` selector to Camera Calibrator. The default is `0.01x`, with `0.001x`, `0.1x`, and `1.0x` available.

The adapter now treats the native solve as pixel-scaled geometry and applies a uniform `scene_scale` to camera distance and world-space positions. Projection is unchanged: FOV, focal length, rotation, VP math, and the origin pixel remain the same. Dropped helper axes inherit the scaled solve because their back-projection uses the scaled camera position.

## Files Changed

- `forge_flame/adapter.py`
- `flame/camera_match_hook.py`
- `tests/test_hook_parity.py`

## Verification

- `python -m pytest tests/test_hook_parity.py -q` -> 60 passed
- `python -m py_compile forge_flame/adapter.py flame/camera_match_hook.py`
- `/Users/cnoellert/miniconda3/envs/forge/bin/python -m pytest tests -q` -> 193 passed
- System Python full-suite attempt failed only because that interpreter lacks `cv2`; forge env passed.
