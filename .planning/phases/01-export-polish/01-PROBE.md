# 01-PROBE — action.resolution shape (live Flame 2026.2.1)

**Run at:** 2026-04-20T05:17:22Z
**Flame version:** 2026.2.1
**Bridge endpoint:** http://127.0.0.1:9999/exec
**Discipline:** one probe per request, non-destructive, per memory/flame_bridge_probing.md

## Step 1 — bridge ping
- Request: `print(2 + 2)`
- Result: `"4\n"`
- Status: ok

## Step 2 — Action node present in batch
- Action names found: `['action1']`
- Target action for probes below: `action1`
