# Phase 04.4 deferred items

## Deferred from Plan 04.4-05

### Stale "Camera Match hook loaded" string in `tools/blender/forge_sender/__init__.py` line 265

- **Discovered during:** Plan 04.4-05 cross-file synchronization audit (R-08).
- **Location:** `tools/blender/forge_sender/__init__.py` line 265 (inside `FORGE_OT_send_to_flame.execute`'s ConnectionError/Timeout handler).
- **Issue:** The bridge-unreachable error message in the *original* `FORGE_OT_send_to_flame` operator still emits `"is Flame running with the Camera Match hook loaded?"`, while the three other bridge-unreachable sites in the same file (lines 386, 439, 508 — in the choose-action operator and helper paths added by Plan 04.4-04) have been updated to `"is Flame running with the Camera Calibrator hook loaded?"`.
- **Impact:** A user hitting the original Send-to-Flame path on a stamped camera with the bridge down will see the old "Camera Match" wording, which contradicts both the docs (`docs/seamless-bridge.md` lines 100, 184) and the rebrand. Functionally harmless — only cosmetic / brand drift. The doc symptom string is anchored on the *new* wording per Plan 04.4-05's must-haves.truths.
- **Why deferred:** Plan 04.4-05 is scope-limited to `docs/seamless-bridge.md` per its `files_modified` field. Out-of-scope code changes are forbidden by the executor's scope-boundary rule.
- **Suggested fix:** A one-line `Edit` in `__init__.py` line 265 changing `"Camera Match hook loaded"` to `"Camera Calibrator hook loaded"`. Should be folded into Plan 04.4-04's verifier or a small follow-up fix.
