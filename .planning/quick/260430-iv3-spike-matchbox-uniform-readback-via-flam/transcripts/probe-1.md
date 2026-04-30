# Probe 1 — Channel Introspection on Un-animated Matchbox Uniform

**Started:** 2026-04-30T20:42:00Z (approx)
**Bridge:** UP (pre-flight + active-batch ping `'spike_260430_iv3'` confirmed)
**Active batch:** `spike_260430_iv3`
**Matchbox node:** `CameraMatch` (PyNode), confirmed via `flame.batch.nodes` enumeration:
`[('testImage', 'PyClipNode'), ('CameraMatch', 'PyNode')]`
**State at probe:** L1 Start = (0.42, 0.69) sentinel; un-animated; user confirmed Checkpoint A ready.

## /exec call (R1 — single request)

### Request body

```python
import flame

mb = next((n for n in flame.batch.nodes if (n.name.get_value() if hasattr(n.name, "get_value") else str(n.name)) == "CameraMatch"), None)

findings = {"resolved": mb is not None, "type": type(mb).__name__ if mb else None}

if mb is None:
    out = findings
else:
    findings["dir_filtered"] = [a for a in dir(mb) if any(k in a.lower() for k in ["chan", "anim", "curve", "expr", "link", "param", "uniform", "input", "attr"])]
    candidates = ["channels", "animation_data", "animation", "anim_data", "channel", "anim", "animations", "attributes", "parameters", "params", "uniforms", "inputs"]
    findings["candidate_types"] = []
    for name in candidates:
        try:
            obj = getattr(mb, name)
        except Exception as e:
            findings["candidate_types"].append({"name": name, "error": "{0}: {1}".format(type(e).__name__, e)})
            continue
        findings["candidate_types"].append({
            "name": name,
            "type": type(obj).__name__,
            "is_none": obj is None,
            "dir_sample": [a for a in dir(obj) if not a.startswith("_")][:30] if obj is not None else None,
        })
    findings["flame_module_chan"] = [a for a in dir(flame) if any(k in a.lower() for k in ["chan", "anim"])]
    findings["flame_batch_chan"] = [a for a in dir(flame.batch) if any(k in a.lower() for k in ["chan", "anim"])]
    findings["candidate_keys"] = {}
    for name in candidates:
        try:
            obj = getattr(mb, name)
        except Exception:
            continue
        if obj is None:
            continue
        try:
            if hasattr(obj, "keys"):
                findings["candidate_keys"][name] = list(obj.keys())[:60]
            elif hasattr(obj, "__iter__"):
                findings["candidate_keys"][name] = [str(item)[:80] for item in list(obj)[:60]]
            else:
                findings["candidate_keys"][name] = "<no keys() or __iter__ on {0}>".format(type(obj).__name__)
        except Exception as e:
            findings["candidate_keys"][name] = "<{0}: {1}>".format(type(e).__name__, e)
    out = findings

out
```

Bridge call: `curl -sS -X POST http://127.0.0.1:9999/exec -H 'Content-Type: application/json' --data-binary @/tmp/probe1_payload.json` (timeout_ms 8000)

### Response envelope (verbatim)

```json
{
  "result": "{'resolved': True, 'type': 'PyNode', 'dir_filtered': ['__delattr__', '__getattr__', '__getattribute__', '__setattr__', 'attributes', 'input_sockets'], 'candidate_types': [{'name': 'channels', 'type': 'NoneType', 'is_none': True, 'dir_sample': None}, {'name': 'animation_data', 'type': 'NoneType', 'is_none': True, 'dir_sample': None}, {'name': 'animation', 'type': 'NoneType', 'is_none': True, 'dir_sample': None}, {'name': 'anim_data', 'type': 'NoneType', 'is_none': True, 'dir_sample': None}, {'name': 'channel', 'type': 'NoneType', 'is_none': True, 'dir_sample': None}, {'name': 'anim', 'type': 'NoneType', 'is_none': True, 'dir_sample': None}, {'name': 'animations', 'type': 'NoneType', 'is_none': True, 'dir_sample': None}, {'name': 'attributes', 'type': 'list', 'is_none': False, 'dir_sample': ['append', 'clear', 'copy', 'count', 'extend', 'index', 'insert', 'pop', 'remove', 'reverse', 'sort']}, {'name': 'parameters', 'type': 'NoneType', 'is_none': True, 'dir_sample': None}, {'name': 'params', 'type': 'NoneType', 'is_none': True, 'dir_sample': None}, {'name': 'uniforms', 'type': 'NoneType', 'is_none': True, 'dir_sample': None}, {'name': 'inputs', 'type': 'NoneType', 'is_none': True, 'dir_sample': None}], 'flame_module_chan': [], 'flame_batch_chan': [], 'candidate_keys': {'attributes': ['pos_x', 'pos_y', 'name', 'collapsed', 'note', 'note_collapsed', 'selected', 'type', 'resolution', 'schematic_colour', 'schematic_colour_label', 'bypass', 'shader_name', 'resolution_mode', 'scaling_presets_value', 'adaptive_mode']}}",
  "stdout": "",
  "stderr": "",
  "error": null,
  "traceback": null
}
```

## Findings

1. **All explicit channel-shaped accessors return None.** `channels`, `animation_data`, `animation`, `anim_data`, `channel`, `anim`, `animations`, `parameters`, `params`, `uniforms`, `inputs` — every one is `NoneType`. The permissive `__getattr__` on PyNode means missing attrs silently return None (not AttributeError), so `is_none: True` is the actual signal.
2. **`mb.attributes` is a `list`, not a dict** — and contains only schematic-node metadata: `['pos_x', 'pos_y', 'name', 'collapsed', 'note', 'note_collapsed', 'selected', 'type', 'resolution', 'schematic_colour', 'schematic_colour_label', 'bypass', 'shader_name', 'resolution_mode', 'scaling_presets_value', 'adaptive_mode']`. None of our shader uniforms (`vp1_l1_start`, `vp1_l1_end`, etc.) appear. This corroborates 260430-ddi's Path B finding.
3. **`flame.chan*`/`anim*` and `flame.batch.chan*`/`anim*` are empty.** There is no module-level or batch-level channel registry at this moment.
4. **One new lead: `input_sockets`** appeared in `dir_filtered` (along with `attributes`). Not in the candidate list of this probe — worth a follow-up at Probe 2 alongside the post-Animate state.

## Verdict

**NOT-FOUND** — no channel-shaped uniform readback on the un-animated matchbox PyNode.

Per plan stop rules: NOT-FOUND → continue to Checkpoint B. Probe 2 may reveal channels that materialize only after Animate; if not, Probe 3 tests the expression-link path; if all dead, Probe 4 tests the sidecar fallback.

## Carry-forward for Probe 2

- Add `input_sockets` to the candidate list at Probe 2 (new lead from `dir_filtered`).
- The Animate operation may also expose new top-level surfaces — re-run `flame_module_chan` and `flame_batch_chan` after animation.
