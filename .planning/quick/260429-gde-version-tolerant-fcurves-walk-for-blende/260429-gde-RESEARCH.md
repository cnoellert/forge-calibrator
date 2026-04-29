# Quick Task: Version-Tolerant fcurves Walk for Blender Slotted-Actions API — Research

**Researched:** 2026-04-29
**Domain:** Blender Python API (`bpy`) — Action data model, slotted/layered actions, fcurves traversal
**Confidence:** HIGH on the API shape, MEDIUM on edge cases (Action without bound slot, multi-slot iteration order)

## Summary

Blender 4.4 (Mar 2025) introduced **Slotted Actions**: an `Action` is no longer a flat
collection of fcurves — it is a layered tree of `Action -> ActionLayer -> ActionStrip ->
ActionChannelbag -> FCurve`, and a single Action can drive multiple data-blocks via
**slots**. Each animated data-block's `AnimData` binds to one slot via
`anim_data.action_slot`. The fcurves for that slot live in
`action.layers[0].strips[0].channelbag(slot).fcurves`.

In **Blender 4.4** the legacy `action.fcurves` accessor was kept as a backward-compat
**proxy** that lazily created layer/strip/slot if needed. In **Blender 5.0** that proxy
was **removed entirely** (along with `action.groups` and `action.id_root`). This is
exactly the failure pattern flame-01 hit on 5.1: `'Action' object has no attribute
'fcurves'`. [CITED: developer.blender.org/docs/release_notes/5.0/python_api/]

The recommended migration path is the official utility
`bpy_extras.anim_utils.action_get_channelbag_for_slot(action, slot)`, which encodes the
"one layer, one strip" assumption Blender 4.4 enforces. It returns the channelbag for
the bound slot — and the addon walks `channelbag.fcurves` from there.
[CITED: developer.blender.org/docs/release_notes/4.4/upgrading/slotted_actions/]

The forge minimum is Blender 4.5 (CLAUDE.md). The slotted API is fully present in 4.4+,
so we don't need a pre-4.4 legacy fallback. We **do** need a `getattr(action,
"fcurves", None)` fallback for the narrow window where someone runs forge against an
Action created in 4.3 mode and loaded into 4.4/4.5 (still legacy-mode under the
backward-compat proxy). On 5.0+ that proxy is gone — no fallback needed there because
no actions can exist in legacy mode.

**Primary recommendation:** Replace `_drain` with a helper that uses
`bpy_extras.anim_utils.action_get_channelbag_for_slot` first, falls back to manual
`action.layers[*].strips[*].channelbags` iteration when no slot is bound, and falls back
finally to legacy `action.fcurves` for 4.4/4.5 actions still in legacy mode. Do **not**
touch `bake_camera.py` — `obj.keyframe_insert(...)` handles slot creation automatically
on every supported Blender version.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| fcurves iteration helper | Blender subprocess script (`tools/blender/forge_sender/flame_math.py`) | — | Runs inside `blender --background --python` and inside the addon. Pure Python + bpy duck-typing per CLAUDE.md ("Pure bpy + mathutils imports; safe to import from either the addon or from a Blender subprocess driving extract_camera.py"). |
| Test fakes for fcurves walk | dev-side pytest (`tests/test_forge_sender_flame_math.py` extension or new test file) | — | Mirror `tests/test_forge_sender_flame_math.py` pattern: `pytest.importorskip("bpy")` at module top so the math layer covers what's testable without bpy, fakes for the iterator. |
| Writer-side `keyframe_insert` | `tools/blender/bake_camera.py` lines 328-330 | — | **No change needed.** Blender 4.4+ creates a layer/strip/slot/channelbag automatically on first `keyframe_insert`. Confirmed by official migration guide. |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `bpy` (Blender bundled) | 4.4+ slotted, 5.0+ slotted-only | Animation data model | The only API for keyframe data inside Blender |
| `bpy_extras.anim_utils` | shipped with bpy 4.4+ | `action_get_channelbag_for_slot(action, slot)` convenience helper | Official utility — encodes Blender 4.4's "one layer, one strip" assumption [CITED: bpy_extras.anim_utils docs] |
| Python stdlib | 3.11 (Blender 4.5/5.0/5.1 all bundle 3.11) | Generator + getattr fallback | No third-party deps in subprocess scripts |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | (forge env) | Test runner | Run via `-p no:pytest-blender` per existing convention |
| `pytest.importorskip("bpy")` | stdlib + pytest | Skip-gating bpy-dependent tests | Matches `tests/test_forge_sender_flame_math.py:38-39` |
| Duck-typed fakes | stdlib | Mock Action/Layer/Strip/Channelbag/FCurve hierarchy | Matches `tests/test_blender_bridge.py` pattern |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `bpy_extras.anim_utils.action_get_channelbag_for_slot` | Manual `action.layers[0].strips[0].channelbag(slot)` | Functionally identical; using the official helper future-proofs against Blender lifting the "one layer, one strip" assumption later. **Recommend the official helper as primary, manual walk as the no-slot fallback.** |
| Detect `action.is_action_legacy` flag | Try-and-fallback on `.layers` then `.fcurves` | The flag exists in 4.4+ but doesn't exist on pre-4.4. The repo's minimum is 4.5 so the flag would work, but try-and-fallback is more portable and matches the existing forge style of duck-typing. |
| Build a `.blend` test fixture in CI | Pure duck-typed fakes | Heavyweight; requires Blender 5.x + git LFS or scripted .blend creation. **Skip — duck fakes verify iterator logic, integration test on flame-01 covers the live API.** |
| Keep both legacy `action.fcurves` and slotted paths | Slotted-first, legacy fallback only | Identical behavior in practice; keep both for narrow back-compat window (4.5 actions still in legacy proxy mode). On 5.0+ the legacy attr is gone so the fallback is harmless dead code. |

**Installation:** No new dependencies. `bpy_extras.anim_utils` ships inside Blender's bundled scripts.

**Version verification:**
- Blender 4.4 — slotted actions introduced, legacy `action.fcurves` proxy retained [CITED: developer.blender.org/docs/release_notes/4.4/upgrading/slotted_actions/]
- Blender 4.5 LTS — same as 4.4 (LTS branch from 4.4) [ASSUMED — release notes confirm continuity; project minimum]
- Blender 5.0 — `action.fcurves`, `action.groups`, `action.id_root` **removed** [CITED: developer.blender.org/docs/release_notes/5.0/python_api/]
- Blender 5.1 — same model as 5.0 (the version on flame-01) [CITED: empirically confirmed by yesterday's failing trace]

## Architecture Patterns

### System Architecture Diagram

```
extract_camera.py / forge_sender addon "Send to Flame" operator
   |
   v (in-Blender, subprocess context OR addon main thread)
forge_sender/flame_math.py::_camera_keyframe_set(cam_obj)
   |
   +--> _drain(cam.animation_data)        # object-level fcurves
   +--> _drain(cam.data.animation_data)   # camera-data-level fcurves (lens, etc.)
            |
            v (rewritten by this patch)
       _iter_action_fcurves(action, anim_data)
            |
            +-- Tier 1: bpy_extras.anim_utils.action_get_channelbag_for_slot(action, anim_data.action_slot)
            |     -> if returns a channelbag: yield from channelbag.fcurves
            |
            +-- Tier 2: manual slotted walk for "no slot bound" cases
            |     for layer in action.layers:
            |       for strip in layer.strips:
            |         for cbag in strip.channelbags:
            |           yield from cbag.fcurves
            |
            +-- Tier 3: legacy action.fcurves (4.5 legacy-mode actions only)
                  yield from getattr(action, "fcurves", ()) or ()
```

### Recommended Structure
```
tools/blender/forge_sender/
├── flame_math.py             # ADD _iter_action_fcurves() helper; rewrite _drain
└── (other files unchanged)

tests/
├── test_forge_sender_flame_math.py   # extend existing file with bpy-free fcurves-walk tests
                                       # OR create test_forge_sender_fcurves_walk.py if cleaner
```

### Pattern 1: Use the Official Helper (preferred)
**What:** Use `bpy_extras.anim_utils.action_get_channelbag_for_slot` as the primary path.
**When to use:** When `anim_data.action_slot` is non-None — the common case after `keyframe_insert`.
**Source:** [CITED: developer.blender.org/docs/release_notes/4.4/upgrading/slotted_actions/]

```python
# Source: developer.blender.org/docs/release_notes/4.4/upgrading/slotted_actions/
import bpy
from bpy_extras import anim_utils

suzanne = bpy.data.objects["Suzanne"]
action = suzanne.animation_data.action
action_slot = suzanne.animation_data.action_slot
channelbag = anim_utils.action_get_channelbag_for_slot(action, action_slot)

for fcurve in channelbag.fcurves:
    print(f"FCurve: {fcurve.data_path}[{fcurve.array_index}]")
```

### Pattern 2: Combined Walk with Three Tiers (the patch shape)
**What:** Single helper that handles bound-slot, unbound-slot, and legacy-mode actions.
**When to use:** Always — this replaces `_drain`'s direct `action.fcurves` walk.

```python
def _iter_action_fcurves(action, anim_data=None):
    """Version-tolerant fcurves walk for Blender 4.5..5.x.

    On 4.4+ slotted actions with a bound slot: uses the official
    bpy_extras.anim_utils.action_get_channelbag_for_slot helper.
    On 4.4+ slotted actions without a bound slot (rare): manually
    walks all channelbags in all strips of all layers.
    On 4.5 legacy-mode actions (back-compat proxy still present):
    falls back to action.fcurves.
    On 5.0+ the legacy proxy is removed — Tier 3 is harmless dead code.

    Source: developer.blender.org/docs/release_notes/4.4/upgrading/slotted_actions/
            developer.blender.org/docs/release_notes/5.0/python_api/
    """
    if action is None:
        return

    # Tier 1: official helper, when a slot is bound.
    slot = getattr(anim_data, "action_slot", None) if anim_data else None
    if slot is not None:
        try:
            from bpy_extras import anim_utils
            cbag = anim_utils.action_get_channelbag_for_slot(action, slot)
        except (ImportError, AttributeError):
            cbag = None
        if cbag is not None:
            for fc in cbag.fcurves:
                yield fc
            return

    # Tier 2: manual slotted walk (no slot bound, or helper missing).
    layers = getattr(action, "layers", None)
    if layers:
        emitted = False
        for layer in layers:
            for strip in getattr(layer, "strips", ()):
                for cbag in getattr(strip, "channelbags", ()):
                    for fc in cbag.fcurves:
                        emitted = True
                        yield fc
        if emitted:
            return

    # Tier 3: legacy-mode action.fcurves (4.4/4.5 back-compat proxy).
    legacy = getattr(action, "fcurves", None)
    if legacy:
        for fc in legacy:
            yield fc
```

Then `_drain` becomes:

```python
def _drain(anim):
    if anim is None or anim.action is None:
        return
    for fc in _iter_action_fcurves(anim.action, anim_data=anim):
        for kp in fc.keyframe_points:
            frames.add(int(round(kp.co[0])))
```

### Anti-Patterns to Avoid
- **Bare `action.fcurves` access** — crashes on 5.0+ slotted actions. The bug.
- **Hand-rolling `action.layers[0].strips[0].channelbag(slot)`** when the official helper exists — works today but skips the "one layer, one strip" abstraction Blender intends to lift later.
- **Setting `anim_data.action_slot_handle` directly** — explicitly warned against in the migration guide. Use `anim_data.action_slot = anim_data.action_suitable_slots[0]` if a binding fix-up is ever needed (out of scope for this read-only walk). [CITED: developer.blender.org/docs/release_notes/4.4/upgrading/slotted_actions/]
- **`isinstance` checks on Action** — `bpy.types.Action` is not a pythonic class hierarchy users typically pattern-match against; use duck-typing via `getattr`.
- **Iterating *all* slots' channelbags when one is bound** — would emit cross-slot fcurves into the bake. Always prefer the bound-slot path when a slot is available.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Slot -> channelbag lookup | Custom `for cb in strip.channelbags: if cb.slot_handle == bound: ...` | `bpy_extras.anim_utils.action_get_channelbag_for_slot(action, slot)` | Official helper, future-proof against the "one layer, one strip" assumption being lifted |
| Slot binding | `anim_data.action_slot_handle = N` direct assignment | `anim_data.action_slot = anim_data.action_suitable_slots[0]` (out of scope here, but document for any future code that creates Actions) | Direct handle assignment is explicitly warned against in the migration guide; can leave the data block in an inconsistent state |
| Slotted action creation in writer | Explicit `action.layers.new(...)` + `layer.strips.new(type='KEYFRAME')` + `action.slots.new(id_type='OBJECT', name=...)` + `strip.channelbag(slot, ensure=True)` | `obj.keyframe_insert(data_path, frame=N)` | Blender does all the layer/strip/slot/channelbag plumbing automatically on first `keyframe_insert`. `bake_camera.py` is correct as-is. |
| Detecting "is this legacy or slotted" | Branch on `action.is_action_legacy` / `is_action_layered` | Try slotted first, fall back to `action.fcurves` on empty result | Less branching; works on 4.4/4.5 legacy-proxy mode and on 5.x slotted-only without a special case |

**Key insight:** **The writer side needs no change.** `cam.keyframe_insert("location", frame=frame)` at `bake_camera.py:328` works identically on 4.5 and 5.x — Blender creates the slotted plumbing internally. The bug is purely in the **reader** path.

## Runtime State Inventory

> N/A for this task — pure code change to one Python file (`flame_math.py::_drain`) plus one new helper function plus tests. No rename, no data migration, no service config changes.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — `.blend` files written by `bake_camera.py` use slotted actions automatically; the new reader walks them correctly | None |
| Live service config | None | None |
| OS-registered state | None | None |
| Secrets/env vars | None — `FORGE_BLENDER_BIN`, `FORGE_BLENDER_SCRIPTS` already discovered by `forge_flame/blender_bridge.py`; not touched by this patch | None |
| Build artifacts | `tools/blender/forge_sender/__pycache__/flame_math.*.pyc` will be stale after the patch; `install.sh` already purges hook `__pycache__` but per `flame_install_pycache_gap.md` memory crumb the sibling pycaches **don't** get purged. **Recommend planner add a one-line note** to either purge `forge_sender/__pycache__` post-install or rely on the addon's own zip-reinstall path (which Blender does fresh). For the addon, reinstall via the v1.x addon zip workflow naturally picks up the new bytecode. | Reinstall addon zip on flame-01 after patch lands (standard procedure) |

## Common Pitfalls

### Pitfall 1: `anim_data.action_slot` is `None`
**What goes wrong:** Helper returns `None` → Tier 1 yields nothing → Tier 2 fires.
**Why it happens:** An Action can be assigned without a slot binding (manual scripting, or auto-assignment heuristics couldn't pick a unique slot). The migration guide notes: *"Sometimes there may not be a slot auto-assigned, resulting in the Action assignment working but not animating the object."* [CITED: developer.blender.org/docs/release_notes/4.4/upgrading/slotted_actions/]
**How to avoid:** Tier 2 (manual slotted walk over all channelbags) handles this. The output may include other-data-block fcurves if the Action is multi-slot — but in forge's case `bake_camera.py` creates single-slot Actions, so this is theoretical for our writer-produced .blends.
**Warning signs:** A `.blend` not produced by forge's bake; manually edited Actions.

### Pitfall 2: `bpy_extras.anim_utils.action_get_channelbag_for_slot` not present on older Blender
**What goes wrong:** `from bpy_extras import anim_utils` succeeds; `anim_utils.action_get_channelbag_for_slot` raises `AttributeError`.
**Why it happens:** The helper was added alongside the slotted-actions feature in 4.4. On pre-4.4 Blender (which forge doesn't formally support but tests should still survive on), it's absent.
**How to avoid:** Wrap in `try/except (ImportError, AttributeError)` (the helper does this).
**Warning signs:** Running on Blender 4.3 or earlier — minimum is 4.5 per CLAUDE.md, but defense in depth.

### Pitfall 3: `strip.channelbags` collection vs `strip.channelbag(slot)` method
**What goes wrong:** Some 4.4 builds expose only the `channelbag(slot)` method, not the `.channelbags` collection.
**Why it happens:** API churn during the 4.4 development cycle.
**How to avoid:** Tier 2's `getattr(strip, "channelbags", ())` returns empty when the collection isn't there; Tier 1's official helper handles the method-only case via `action_get_channelbag_for_slot`.
**Warning signs:** `AttributeError: 'ActionKeyframeStrip' object has no attribute 'channelbags'` on Blender 4.4.0 release — the helper's try/except + Tier 2 `getattr` together absorb this.

### Pitfall 4: Calling the helper with a `None` slot
**What goes wrong:** `action_get_channelbag_for_slot(action, None)` may raise or return nonsense.
**Why it happens:** The helper's contract assumes a real `ActionSlot`.
**How to avoid:** Gate Tier 1 entry on `slot is not None` (the helper above does this).
**Warning signs:** Logs from a non-forge-produced .blend that has Actions with unbound AnimData.

### Pitfall 5: Multi-slot Action contaminating the camera bake
**What goes wrong:** A user manually edits a forge-produced .blend, attaches additional fcurves to the Action under a second slot. Tier 2 (no slot bound) would emit those.
**Why it happens:** Slotted Actions are explicitly designed to hold multi-data-block animation.
**How to avoid:** Always pass `anim_data` to the helper; Tier 1 with `anim_data.action_slot` filters to just the camera's own fcurves.
**Warning signs:** N/A in normal forge workflows; planner should consider adding a defensive log when Tier 2 fires (the addon could `print("forge_sender: action has no bound slot, walking all channelbags", file=sys.stderr)`).

### Pitfall 6: Forgetting the camera-data path
**What goes wrong:** Patch fixes `cam.animation_data` walk but not `cam.data.animation_data` walk → lens animation drops out.
**Why it happens:** `_drain` is called twice — once on the object, once on the data-block (line 115-116 of `flame_math.py`). Both go through the same helper now, so this is automatically handled, but the test must cover both call sites.
**How to avoid:** Call `_iter_action_fcurves` from both `_drain(cam.animation_data)` AND `_drain(cam.data.animation_data)`. The patch above is symmetric across both — no change in call structure needed.
**Warning signs:** Round-trip drops focal_mm keyframes after the patch but preserves location/rotation. Test fixture should include lens animation to catch this.

## Code Examples

### Live API: bound-slot fcurves access (Blender 4.4+)
```python
# Source: developer.blender.org/docs/release_notes/4.4/upgrading/slotted_actions/
#         search result quote, exact API surface
import bpy
from bpy_extras import anim_utils

obj = bpy.data.objects["Camera"]
ad = obj.animation_data
action = ad.action
slot = ad.action_slot
channelbag = anim_utils.action_get_channelbag_for_slot(action, slot)

for fc in channelbag.fcurves:
    for kp in fc.keyframe_points:
        print(int(round(kp.co[0])))
```

### Live API: manual slotted walk (multi-slot iteration)
```python
# Source: developer.blender.org/docs/release_notes/4.4/upgrading/slotted_actions/
#         "F-Curves and Channel Groups are now stored on an infinite keyframe strip"
for layer in action.layers:
    for strip in layer.strips:
        for cbag in strip.channelbags:
            for fc in cbag.fcurves:
                print(fc.data_path, fc.array_index)
```

### Test fakes (no bpy import — duck-typed, matches forge style)
```python
# Source: tests/test_blender_bridge.py + tests/test_forge_sender_flame_math.py
# patterns. No bpy import needed for unit tests of the iterator.

class _KP:
    def __init__(self, frame: float):
        self.co = (float(frame), 0.0)

class _FCurve:
    def __init__(self, data_path: str, array_index: int, frames):
        self.data_path = data_path
        self.array_index = array_index
        self.keyframe_points = [_KP(f) for f in frames]

class _Channelbag:
    def __init__(self, slot_handle: int, fcurves):
        self.slot_handle = slot_handle
        self.fcurves = fcurves

class _Strip:
    def __init__(self, channelbags):
        self.channelbags = channelbags
    def channelbag(self, slot, ensure=False):
        # mimic Blender's strip.channelbag(slot) signature
        if slot is None:
            return None
        for cb in self.channelbags:
            if cb.slot_handle == slot.handle:
                return cb
        return None

class _Layer:
    def __init__(self, strips):
        self.strips = strips

class _SlottedAction:
    """Mimics a 5.x slotted-only Action — no .fcurves attribute."""
    def __init__(self, layers):
        self.layers = layers

class _LegacyAction:
    """Mimics a 4.5 legacy-mode Action — has .fcurves shim, empty .layers."""
    def __init__(self, fcurves):
        self.fcurves = fcurves
        self.layers = []  # forces Tier 2 to skip, Tier 3 to fire

class _Slot:
    def __init__(self, handle: int):
        self.handle = handle

class _AnimData:
    def __init__(self, action, slot=None):
        self.action = action
        self.action_slot = slot

# Mock the bpy_extras helper too, since the helper is what Tier 1 calls.
# In tests: monkeypatch flame_math's `from bpy_extras import anim_utils` to
# a fake namespace whose action_get_channelbag_for_slot does the lookup
# against the fake _Strip via the bound slot. Or pass an explicit
# _channelbag_lookup hook into _iter_action_fcurves for testability —
# planner's choice.
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `for fc in action.fcurves:` | `_iter_action_fcurves(action, anim_data)` (slotted-aware via `bpy_extras.anim_utils`) | Blender 4.4 (Mar 2025), enforced 5.0 (Oct 2025) | Required for 5.0+; works on 4.4/4.5 too |
| Single-Action-per-data-block | One Action can hold animation for many data-blocks via Slots | Blender 4.4 | Enables multi-character workflows; for forge's single-camera bake it's invisible plumbing |
| Flat fcurves list | Layered: Action → Layer → Strip → Channelbag → FCurve | Blender 4.4 | Deeper API surface; intentional design space for future NLA-style stacking |
| `action.id_root` | `action_slot.target_id_type` | Blender 5.0 | Out of scope here (forge doesn't read id_root) |
| `action.groups` | `channelbag.groups` | Blender 5.0 | Out of scope here (forge doesn't read groups) |

**Deprecated and removed:**
- `action.fcurves` — proxy in 4.4/4.5, **removed in 5.0** [CITED: developer.blender.org/docs/release_notes/5.0/python_api/]
- `action.groups` — removed in 5.0 (not used by forge)
- `action.id_root` — removed in 5.0 (not used by forge)
- Direct `anim_data.action_slot_handle = N` assignment — discouraged in the migration guide

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `bpy_extras.anim_utils.action_get_channelbag_for_slot` is present in Blender 4.5 (and 5.0/5.1) | Pattern 1, Pattern 2 | Low — explicitly documented as the migration helper added in 4.4. Try/except in Tier 1 absorbs absence by falling through to Tier 2. |
| A2 | `obj.keyframe_insert(data_path, frame=N)` on Blender 5.x creates a single-layer, single-strip, single-slot Action automatically — `bake_camera.py:328-330` needs no change | Don't Hand-Roll, A-map | Medium — the migration guide implies this ("Blender will try to auto-assign a slot") but is explicit only for high-level operators. **Recommend planner add a smoke-test task: bake → extract → diff JSON on Blender 5.1 before declaring done.** |
| A3 | Blender 4.5 retains the legacy `action.fcurves` proxy from 4.4 (4.5 LTS = 4.4 LTS branch) | Summary, Tier 3 | Low — 4.5 is documented as the LTS continuation of 4.4; no API breakage between them is documented. |
| A4 | `anim_data.action_slot` returns the bound `ActionSlot` instance; `.handle` attribute provides the int handle for matching against `Channelbag.slot_handle` | Pattern 2, test fakes | Low — confirmed against `bpy.types.AnimData.html` and `bpy.types.ActionSlot.html` API references in search results. |
| A5 | `extract_camera.py` going through `flame_math._drain` (via `build_v5_payload` → `_camera_keyframe_set` → `_drain`) means a single fix in `flame_math.py` covers both the addon AND the CLI extract path | Architectural Map | HIGH (verified) — `extract_camera.py:68-74` imports `_camera_keyframe_set` and `build_v5_payload` from `flame_math`. The CLI shares the same iterator, so one fix covers both. |
| A6 | Forge-produced .blends always have a single bound slot (created by `keyframe_insert` in `bake_camera.py`) — Tier 1 is the always-fires path; Tier 2 and Tier 3 are defensive | Pitfalls 1, 5 | Low — Tier 2/3 act as graceful degradation; even if A6 is wrong on some edge case, the iterator still emits all the fcurves. |

**Recommended user confirmation before locking implementation:** A2 — confirm via the smoke test described in `flame-01` next-session entry point. If the writer side breaks on 5.x, the fix is narrowly: add explicit `action.slots.new(id_type='OBJECT', name=cam.name)` after `_get_or_create_camera` and before the keyframe loop. But evidence strongly suggests this isn't needed.

## Open Questions

1. **Should `_iter_action_fcurves` accept the `anim_data` directly, or should the caller extract `action_slot` first?**
   - What we know: `_drain(anim)` already has `anim` in hand. Passing `anim` keeps the helper's signature symmetric with the existing call site.
   - What's unclear: Whether tests prefer to pass a fake AnimData or a fake Slot.
   - Recommendation: Pass `anim_data` (the existing variable). Helper internally does `getattr(anim_data, "action_slot", None)`. Test fakes can supply either an AnimData-like object with `.action_slot` set or a bare object — `getattr` is permissive.

2. **Should the helper warn (stderr) when it falls back from Tier 1 to Tier 2 or Tier 3?**
   - What we know: Tier 2 firing means a non-forge-produced .blend or a manually-edited Action.
   - What's unclear: Whether the addon UX wants to surface this signal.
   - Recommendation: Yes — single `print(..., file=sys.stderr)` in each fallback path. Cheap, helpful for debugging on flame-01 if the round-trip ever yields unexpected fcurves. Matches the existing `_resolve_scale` warning pattern (line 141).

3. **Does the helper need to handle multi-strip layers?**
   - What we know: Blender 4.4's "one strip per layer" is documented as a current limitation, will be lifted later.
   - What's unclear: When that lifting happens.
   - Recommendation: Iterate `layer.strips` (the helper does). Future-proof. Cost: zero — current Blender always returns a 1-element collection.

4. **Should we ship a memory crumb at `memory/blender_slotted_actions_fcurves_api.md` per the todo's "Memory crumb to write" section?**
   - What we know: The todo explicitly asks for one.
   - What's unclear: Crumb scope — just the iterator pattern, or include slot-binding semantics for any future code that needs to write Actions?
   - Recommendation: Out of scope for research; planner schedules as a post-fix task. Suggest crumb include: (a) the three-tier iterator pattern, (b) `bpy_extras.anim_utils.action_get_channelbag_for_slot` is the official helper, (c) writer-side `keyframe_insert` is unchanged, (d) version cutoff (4.4 introduced, 5.0 enforced).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Blender 5.x (subprocess + addon) | Live API verification | Yes (flame-01) | 5.1 | — |
| Blender 4.5 (subprocess + addon) | Back-compat verification | Yes (portofino currently) | 4.5 | — |
| pytest | Test suite | Yes (forge env) | bundled | — |
| `bpy` at test time | Optional integration test | No (forge env on macOS dev) | — | `pytest.importorskip("bpy")` per existing convention |
| `bpy_extras.anim_utils` at runtime | Tier 1 of helper | Yes (ships with bpy 4.4+) | per Blender | Tier 2 fallback handles absence |

**Missing dependencies with no fallback:** None.
**Missing dependencies with fallback:** `bpy` for the math layer of unit tests — using `pytest.importorskip` and duck-typed fakes per existing repo style.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (forge env) |
| Config file | None (sys.path.insert pattern with `noqa: E402`) |
| Quick run command | `pytest tests/test_forge_sender_flame_math.py -x -p no:pytest-blender` |
| Full suite command | `pytest tests/ -p no:pytest-blender` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| FCV-01 | `_iter_action_fcurves(slotted_action, anim_data_with_bound_slot)` -> yields fcurves only from the bound slot's channelbag (via `bpy_extras.anim_utils` mock) | unit | `pytest tests/test_forge_sender_flame_math.py::test_slotted_bound_slot -x -p no:pytest-blender` | Wave 0 (extend file or new file) |
| FCV-02 | `_iter_action_fcurves(slotted_action, anim_data_no_slot)` -> Tier 2 manual walk yields all channelbags | unit | `pytest tests/test_forge_sender_flame_math.py::test_slotted_no_slot_walks_all -x` | Wave 0 |
| FCV-03 | `_iter_action_fcurves(legacy_action, anim_data)` -> Tier 3 falls back to `action.fcurves` (4.5 legacy-mode case) | unit | `pytest tests/test_forge_sender_flame_math.py::test_legacy_fallback -x` | Wave 0 |
| FCV-04 | `_iter_action_fcurves(empty_slotted_action, anim_data)` -> yields nothing, no exception (5.x action with no keyframes) | unit | `pytest tests/test_forge_sender_flame_math.py::test_empty_slotted_action -x` | Wave 0 |
| FCV-05 | `_iter_action_fcurves(None, None)` -> yields nothing, no exception | unit | `pytest tests/test_forge_sender_flame_math.py::test_none_action -x` | Wave 0 |
| FCV-06 | `_iter_action_fcurves(slotted_action, anim_data_with_slot_no_helper)` -> falls through to Tier 2 when `bpy_extras.anim_utils` raises `AttributeError` | unit | `pytest tests/test_forge_sender_flame_math.py::test_helper_missing_falls_through -x` | Wave 0 |
| FCV-07 | `_camera_keyframe_set(cam_obj_with_5x_slotted_actions)` -> returns sorted unique frame list combining object-level + camera-data-level fcurves (regression for the original `_drain` interface) | unit | `pytest tests/test_forge_sender_flame_math.py::test_camera_keyframe_set_combines_object_and_data -x` | Wave 0 |
| FCV-08 | (Manual integration) On flame-01 with Blender 5.1: `bake_camera.py` writes 2-frame slotted action; `extract_camera.py` reads it back; JSON round-trip diff is empty | manual | `blender --background --python tools/blender/bake_camera.py -- --in tools/blender/sample_camera.json --out /tmp/forge_rt.blend --scale 1000 --create-if-missing && blender --background /tmp/forge_rt.blend --python tools/blender/extract_camera.py -- --out /tmp/forge_rt.json && diff tools/blender/sample_camera.json /tmp/forge_rt.json` | Manual gate |
| FCV-09 | (Manual integration) On flame-01: addon "Send to Flame" operator no longer raises `AttributeError` — round-trip succeeds | manual | UAT in Blender 5.1 N-panel | Manual gate |

### Sampling Rate
- **Per task commit:** `pytest tests/test_forge_sender_flame_math.py -x -p no:pytest-blender`
- **Per wave merge:** `pytest tests/ -p no:pytest-blender`
- **Phase gate:** Full suite green + FCV-08 + FCV-09 manual on flame-01 with Blender 5.1.

### Wave 0 Gaps
- [ ] Extend `tests/test_forge_sender_flame_math.py` (or create `tests/test_forge_sender_fcurves_walk.py` if cleaner) to cover FCV-01..FCV-07 with duck-typed fakes. The new tests do **not** need `pytest.importorskip("bpy")` — they're pure-Python iterator tests against fakes.
- [ ] Test infrastructure for monkeypatching the `bpy_extras.anim_utils` import inside `flame_math.py`. Cleanest pattern: refactor `_iter_action_fcurves` to accept an injectable `_get_channelbag_for_slot` hook (default: lazy import of `bpy_extras.anim_utils.action_get_channelbag_for_slot`), so tests pass a fake closure. Alternative: `monkeypatch.setattr` on the module's import.
- [ ] No new conftest needed.
- [ ] No framework install — pytest already in forge env.

## Project Constraints (from CLAUDE.md)

- **Tech stack:** Blender bundled Python only; `bpy` + `mathutils` + `bpy_extras` (which ships with Blender). No third-party imports. ✓ Patch respects this.
- **Platform:** macOS + Linux. ✓ No platform-specific code.
- **Compatibility:** Blender 4.5+ minimum (CLAUDE.md tech stack). Patch supports 4.5 (legacy proxy + slotted) and 5.0/5.1 (slotted-only). ✓
- **Naming:** snake_case functions; private helpers prefixed `_`. ✓ `_iter_action_fcurves` matches.
- **Docstrings:** Module + function docstrings explaining WHY (not just WHAT), Google-style with Args/Returns. ✓ Pattern shown in code examples.
- **Type hints:** `from __future__ import annotations` already at top of `flame_math.py:37`. ✓ New helper takes type hints.
- **Numeric precision:** N/A — no numeric changes; iterator only walks existing fcurves.
- **Tests:** Duck-typed fakes, no bpy import; mirror `tests/test_blender_bridge.py` and `tests/test_forge_sender_flame_math.py`. ✓
- **Round-trip parity:** Phase 04.3's "MUST stay numerically identical to forge_core.math.rotations" applies to `_rot3_to_flame_euler_deg`, NOT to the new helper. Helper has no numerical content. ✓
- **GSD enforcement:** `/gsd-quick` workflow — this research feeds the planner. ✓
- **Forge core value:** "Numbers must be geometrically faithful." A correct fcurves walk is a precondition for round-trip fidelity — any missed keyframe would silently drop animation data. ✓ Helper preserves all keyframes; the slot filter prevents cross-contamination.

## Sources

### Primary (HIGH confidence)
- [Slotted Actions Migration Guide (Blender 4.4)](https://developer.blender.org/docs/release_notes/4.4/upgrading/slotted_actions/) — official 4.4 → slotted-actions migration guide; documents `action_get_channelbag_for_slot`, slot binding semantics, and "do not assign action_slot_handle directly" warning
- [Blender 5.0 Python API Release Notes](https://developer.blender.org/docs/release_notes/5.0/python_api/) — confirms `action.fcurves`, `action.groups`, `action.id_root` removal in 5.0
- [Blender 4.4 Python API Release Notes](https://developer.blender.org/docs/release_notes/4.4/python_api/) — slotted actions Python API introduction
- [Layered Actions Design](https://developer.blender.org/docs/features/animation/animation_system/layered/) — design rationale and traversal model
- [Slotted Actions Feedback Thread](https://devtalk.blender.org/t/blender-4-4-slotted-actions-feedback/38906) — community Q&A and edge cases
- [bpy.types.Action API Reference](https://docs.blender.org/api/current/bpy.types.Action.html)
- [bpy.types.ActionSlot API Reference](https://docs.blender.org/api/current/bpy.types.ActionSlot.html)
- [bpy.types.ActionChannelbag API Reference](https://docs.blender.org/api/current/bpy.types.ActionChannelbag.html)
- [bpy.types.ActionChannelbags API Reference](https://docs.blender.org/api/current/bpy.types.ActionChannelbags.html)
- [bpy.types.AnimData API Reference](https://docs.blender.org/api/current/bpy.types.AnimData.html)
- [bpy_extras.anim_utils submodule](https://docs.blender.org/api/current/bpy_extras.anim_utils.html)
- Repo `.planning/PASSOFF-2026-04-29.md` — empirical confirmation of 5.1 failure
- Repo `.planning/todos/pending/2026-04-29-blender-51-slotted-actions-fcurves-api-migration.md` — failing trace + solution sketch
- Repo `tools/blender/forge_sender/flame_math.py:108-115` — current `_drain` site to be patched
- Repo `tools/blender/extract_camera.py:68-74` — confirms CLI shares the helper

### Secondary (MEDIUM confidence)
- [How to access fcurves in Blender 5.0 — Blender Artists thread](https://blenderartists.org/t/how-to-access-fcurves-in-blender-5-0/1623022) — community migration examples
- [Animation & Rigging release notes 4.4](https://developer.blender.org/docs/release_notes/4.4/animation_rigging/) — slotted actions feature overview

### Tertiary (LOW confidence)
- Blender 5.1-specific changes — relied on continuity from 5.0 release notes plus empirical evidence (yesterday's failing trace). No comprehensive 5.1 changelog scraped; this is fine because 5.0 enforced the slotted-only model and 5.1 hasn't reverted it.

## Metadata

**Confidence breakdown:**
- Slotted API attribute names (`layers`, `strips`, `channelbags`, `slot_handle`, `fcurves`) — HIGH (current docs + multiple sources)
- `bpy_extras.anim_utils.action_get_channelbag_for_slot` is the official helper — HIGH (documented in migration guide + community examples)
- Removal of `action.fcurves` in 5.0 — HIGH (explicit release-note quote)
- AnimData slot binding (`action_slot`) — HIGH (current docs)
- Writer-side `keyframe_insert` automatic slot creation — MEDIUM-HIGH (consistent with API design + migration guide implications; recommend FCV-08 smoke test for full confidence before declaring done)
- Test fake strategy — HIGH (matches established forge pattern in `tests/test_forge_sender_flame_math.py` and `tests/test_blender_bridge.py`)

**Research date:** 2026-04-29
**Valid until:** ~2026-05-29 (30 days; Blender 4.5 LTS is stable, 5.x point releases are out of major-API-break window per release policy)
