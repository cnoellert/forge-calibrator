---
status: partial
phase: 01-export-polish
source: [01-VERIFICATION.md]
started: 2026-04-19T00:00:00Z
updated: 2026-04-19T00:00:00Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. Happy-path end-to-end: zero-dialog export to Blender
expected: Right-click an Action (single non-Perspective camera) in Flame → "Export Camera to Blender". No width/height dialog. No save-path dialog. Blender opens on `~/forge-bakes/{action}_{cam}.blend` in the background (no focus steal when default config). The `.blend` camera's custom properties show `forge_bake_action_name` and `forge_bake_camera_name` with the correct Flame Action/camera names. Temp dir under `/tmp/forge_bake_*` is gone on success. A single info summary dialog in Flame confirms the bake.
result: [pending]

## Summary

total: 1
passed: 0
issues: 0
pending: 1
skipped: 0
blocked: 0

## Gaps
