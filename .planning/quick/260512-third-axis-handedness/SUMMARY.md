---
quick_id: 260512-third-axis-handedness
status: complete
date: 2026-05-12
---

# Audit third-axis handedness in calibrator overlay

## Summary

Reviewed the Camera Calibrator plane overlay against commit history and restored the previously verified positive missing-axis convention.

For the tested case `VP1=-Z`, `VP2=-Y`, commit `32c7bfc` says the overlay should draw `+X`; the solver's signed cross-product basis remains separate.

## Files Changed

- `flame/camera_match_hook.py`
- `forge_core/solver/solver.py`
- `tests/test_camera_match_hook.py`
- `tests/test_solver.py`

## History Update

Live Flame testing showed the signed-overlay and solver-basis experiments did not fix the Action output. History points to native-scale behavior after `1412555` + `32c7bfc` as the known-good anchor. The current patch keeps the scene scale control but defaults it to `1.0x` so the next test matches that native-scale path by default.

## Verification

- `python -m pytest tests/test_camera_match_hook.py tests/test_hook_parity.py -q` -> 79 passed
- `python -m py_compile flame/camera_match_hook.py`
- `/Users/cnoellert/miniconda3/envs/forge/bin/python -m pytest tests -q` -> 195 passed
- `python -m pytest tests/test_solver.py tests/test_hook_parity.py tests/test_camera_match_hook.py -q` -> 120 passed
- `python -m py_compile forge_core/solver/solver.py flame/camera_match_hook.py`
- `/Users/cnoellert/miniconda3/envs/forge/bin/python -m pytest tests -q` -> 197 passed
- `python -m pytest tests/test_camera_match_hook.py tests/test_solver.py tests/test_hook_parity.py -q` -> 118 passed
