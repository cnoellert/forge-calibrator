---
created: 2026-04-29T18:30:00Z
updated: 2026-04-29T20:00:00Z
status: closed_uat_passed
priority: high
area: blender-addon
title: forge_sender addon breaks on Blender 5.1 — Action.fcurves removed (slotted-actions migration)
quick_task: 260429-gde
fix_commits:
  - a3cf531  # test: failing tests for _iter_action_fcurves three-tier walk (TDD-RED)
  - f064824  # fix: version-tolerant fcurves walk for Blender slotted-actions API (TDD-GREEN)
  - bc21b3e  # docs: STATE.md + PLAN/RESEARCH/SUMMARY artifacts
  - 543f458  # build: repackage forge_sender v1.3.5 addon zip
files:
  - tools/blender/forge_sender/flame_math.py    # _iter_action_fcurves + rewritten _drain (three-tier walk)
  - tests/test_forge_sender_flame_math.py       # FCV-01..FCV-07 (bpy-free duck-typed)
  - tools/blender/forge_sender-v1.3.5.zip       # repackaged zip with the fix (v1.3.4 deleted)
---

## Closed 2026-04-29 — UAT passed on portofino + flame-01

Bake → Send to Flame round-trip clean on Blender 5.1 on both machines
after reinstalling `forge_sender-v1.3.5.zip`. AttributeError gone,
keyframes preserved both directions (Flame → Blender → Flame). Original
repro site (flame-01) confirmed by user as "working perfect backwards
and forwards."

**Memory crumb:** `memory/blender_slotted_actions_fcurves_api.md` written
during the fix (auto-memory dir). Indexed in `MEMORY.md`.



## Problem

Send-to-Flame from the Blender addon raises on flame-01 with Blender 5.1:

```
File "/home/cnoellert/.config/blender/5.1/scripts/addons/forge_sender/flame_math.py",
  line 111, in _drain
    for fcurve in anim.action.fcurves:
                  ^^^^^^^^^^^^^^^^^^^
AttributeError: 'Action' object has no attribute 'fcurves'
```

`Action.fcurves` was the legacy direct-fcurves accessor on `bpy.types.Action`. Blender
4.4 introduced **slotted actions** (data-block "slot" system that lets one Action drive
multiple objects with their own animation channels). By 5.x, the legacy `.fcurves`
attribute is gone — fcurves now live under `action.layers[*].strips[*].channelbag(slot).fcurves`.

CLAUDE.md targets "Blender 4.5+" but doesn't pin an upper bound. The codebase predates
the slotted-actions migration; flame-01 was the first cold-install with a 5.x daily
driver and surfaced the gap immediately.

## Diagnosis

`flame_math.py:108-115`:

```python
def _drain(anim):
    if anim is None or anim.action is None:
        return
    for fcurve in anim.action.fcurves:           # <-- AttributeError on 5.1
        for kp in fcurve.keyframe_points:
            frames.add(int(round(kp.co[0])))

_drain(cam.animation_data)
_drain(cam.data.animation_data)
```

The writer side (`bake_camera.py:328-330`) uses `obj.keyframe_insert(...)` which is
high-level and version-stable; that path likely still works on 5.1 (Blender autocreates
a slotted Action). The reader side (this todo) is what's broken.

## Solution sketch

Replace the direct `.fcurves` walk with a version-tolerant iterator:

```python
def _iter_fcurves(action, slot=None):
    # 4.x legacy + 4.4 mixed-mode actions still expose .fcurves
    fcurves = getattr(action, "fcurves", None)
    if fcurves:
        for fc in fcurves:
            yield fc
        return
    # Slotted actions (4.4+, mandatory in 5.x): walk layers/strips/channelbags
    for layer in getattr(action, "layers", ()):
        for strip in layer.strips:
            # If a slot is bound, prefer channelbag(slot); otherwise enumerate all
            if slot is not None and hasattr(strip, "channelbag"):
                cb = strip.channelbag(slot)
                if cb:
                    for fc in cb.fcurves:
                        yield fc
                    continue
            for cb in getattr(strip, "channelbags", ()):
                for fc in cb.fcurves:
                    yield fc

def _drain(anim):
    if anim is None or anim.action is None:
        return
    slot = getattr(anim, "action_slot", None)
    for fc in _iter_fcurves(anim.action, slot):
        for kp in fc.keyframe_points:
            frames.add(int(round(kp.co[0])))
```

Verify the slot-binding semantics in Blender's Python API (use context7 / Blender docs
search for `bpy.types.Action.layers`, `bpy.types.ActionStrip.channelbag`,
`bpy.types.AnimData.action_slot`) before locking the implementation — the API for
walking a slotted action is the part most likely to drift between minor versions.

## Reproduction

1. Blender 5.1 (or any 4.4+ version where the action was created without the legacy
   `.fcurves` shim).
2. Open a `.blend` produced by `tools/blender/bake_camera.py` (any forge bake).
3. In Blender: N-panel → FORGE → Send to Flame.
4. Observe the AttributeError in Blender's system console / status bar.

## Reproduction on portofino (after install of 5.1)

The new glob default `/Applications/Blender*.app/Contents/MacOS/Blender` (landed in
quick task `260429-fk5`, commit `f49bc49`) sorts descending, so once Blender 5.1 is
installed alongside 4.5 on portofino, `resolve_blender_bin()` will pick 5.1 first and
the same AttributeError will fire here. Installing 5.1 on portofino is the planned
next step to enable local fix verification.

## Scope

This blocks the Blender→Flame round-trip on Blender 5.1 (and by extension flame-01,
which uses 5.1 as its only Blender install). The Flame→Blender direction (`bake_camera.py`)
is unverified on 5.1 — needs spot-check during the fix cycle.

Reading-only side (the addon's send operator) is the user-facing failure point. The
CLI extract path (`tools/blender/extract_camera.py`) imports the same `flame_math.py`
and has the same bug — though that path is rarely exercised standalone.

## Memory crumb to write

After fix lands: `memory/blender_slotted_actions_fcurves_api.md` capturing the
4.4+/5.x slotted-actions API change pattern, so the next module that walks fcurves
gets it right the first time.
