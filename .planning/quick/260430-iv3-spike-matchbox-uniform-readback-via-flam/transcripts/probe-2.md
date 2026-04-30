# Probe 2 — Channel Materialization After Animate

**Started:** 2026-04-30T20:48:00Z (approx)
**Bridge:** UP
**Active batch:** `spike_260430_iv3`
**Matchbox node:** `CameraMatch` (PyNode)
**State at probe:** L1 Start = (0.42, 0.69), **animated** (one keyframe at current frame, value unchanged); user confirmed Checkpoint B ready.

## /exec call (R1 — single request)

### Request body

```python
import flame

mb = next((n for n in flame.batch.nodes if (n.name.get_value() if hasattr(n.name, "get_value") else str(n.name)) == "CameraMatch"), None)

findings = {"resolved": mb is not None}

if mb is None:
    out = findings
else:
    candidates = ["channels", "animation_data", "animation", "anim_data", "channel", "anim", "animations",
                  "attributes", "parameters", "params", "uniforms", "inputs",
                  "input_sockets", "output_sockets", "sockets"]
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
        })

    findings["flame_module_chan"] = [a for a in dir(flame) if any(k in a.lower() for k in ["chan", "anim", "expr", "link"])]
    findings["flame_batch_chan"] = [a for a in dir(flame.batch) if any(k in a.lower() for k in ["chan", "anim", "expr", "link"])]

    iss = getattr(mb, "input_sockets", None)
    findings["input_sockets"] = {"type": type(iss).__name__, "is_none": iss is None}
    if iss is not None:
        try:
            findings["input_sockets"]["dir_sample"] = [a for a in dir(iss) if not a.startswith("_")][:30]
        except Exception as e:
            findings["input_sockets"]["dir_error"] = "{0}: {1}".format(type(e).__name__, e)
        try:
            if hasattr(iss, "keys"):
                findings["input_sockets"]["keys"] = list(iss.keys())[:60]
            elif hasattr(iss, "__iter__"):
                items = list(iss)
                findings["input_sockets"]["items"] = [str(it)[:120] for it in items[:60]]
                if items:
                    first = items[0]
                    findings["input_sockets"]["first_item_type"] = type(first).__name__
                    findings["input_sockets"]["first_item_dir"] = [a for a in dir(first) if not a.startswith("_")][:40]
            elif hasattr(iss, "__len__"):
                findings["input_sockets"]["len"] = len(iss)
        except Exception as e:
            findings["input_sockets"]["enum_error"] = "{0}: {1}".format(type(e).__name__, e)

    findings["attributes_full"] = list(mb.attributes) if mb.attributes else []
    findings["attributes_count"] = len(mb.attributes) if mb.attributes else 0
    if mb.attributes:
        findings["attributes_vp_or_l1"] = [a for a in mb.attributes if any(k in str(a).lower() for k in ["vp", "l1", "l2", "start", "end", "axis"])]

    findings["get_attribute_attempts"] = []
    for attr_name in ["vp1_l1_start", "VP1_L1_Start", "L1 Start", "L1Start", "vp1_l1_start_x", "vp1_l1_start.x"]:
        try:
            v = mb.get_attribute(attr_name) if hasattr(mb, "get_attribute") else None
            findings["get_attribute_attempts"].append({"name": attr_name, "result": repr(v)[:120], "method": "get_attribute"})
        except Exception as e:
            findings["get_attribute_attempts"].append({"name": attr_name, "error": "{0}: {1}".format(type(e).__name__, e)})

    findings["batch_nodes_post_animate"] = [(n.name.get_value() if hasattr(n.name, "get_value") else str(n.name), type(n).__name__) for n in flame.batch.nodes]
    out = findings

out
```

### Response envelope (verbatim)

```json
{
  "result": "{'resolved': True, 'candidate_types': [{'name': 'channels', 'type': 'NoneType', 'is_none': True}, {'name': 'animation_data', 'type': 'NoneType', 'is_none': True}, {'name': 'animation', 'type': 'NoneType', 'is_none': True}, {'name': 'anim_data', 'type': 'NoneType', 'is_none': True}, {'name': 'channel', 'type': 'NoneType', 'is_none': True}, {'name': 'anim', 'type': 'NoneType', 'is_none': True}, {'name': 'animations', 'type': 'NoneType', 'is_none': True}, {'name': 'attributes', 'type': 'list', 'is_none': False}, {'name': 'parameters', 'type': 'NoneType', 'is_none': True}, {'name': 'params', 'type': 'NoneType', 'is_none': True}, {'name': 'uniforms', 'type': 'NoneType', 'is_none': True}, {'name': 'inputs', 'type': 'NoneType', 'is_none': True}, {'name': 'input_sockets', 'type': 'list', 'is_none': False}, {'name': 'output_sockets', 'type': 'list', 'is_none': False}, {'name': 'sockets', 'type': 'dict', 'is_none': False}], 'flame_module_chan': [], 'flame_batch_chan': ['mimic_link'], 'input_sockets': {'type': 'list', 'is_none': False, 'dir_sample': ['append', 'clear', 'copy', 'count', 'extend', 'index', 'insert', 'pop', 'remove', 'reverse', 'sort'], 'items': ['Input 1'], 'first_item_type': 'str', 'first_item_dir': [...str methods...]}, 'attributes_full': ['pos_x', 'pos_y', 'name', 'collapsed', 'note', 'note_collapsed', 'selected', 'type', 'resolution', 'schematic_colour', 'schematic_colour_label', 'bypass', 'shader_name', 'resolution_mode', 'scaling_presets_value', 'adaptive_mode'], 'attributes_count': 16, 'attributes_vp_or_l1': [], 'get_attribute_attempts': [{'name': 'vp1_l1_start', 'error': \"TypeError: 'NoneType' object is not callable\"}, {'name': 'VP1_L1_Start', 'error': \"TypeError: 'NoneType' object is not callable\"}, {'name': 'L1 Start', 'error': \"TypeError: 'NoneType' object is not callable\"}, {'name': 'L1Start', 'error': \"TypeError: 'NoneType' object is not callable\"}, {'name': 'vp1_l1_start_x', 'error': \"TypeError: 'NoneType' object is not callable\"}, {'name': 'vp1_l1_start.x', 'error': \"TypeError: 'NoneType' object is not callable\"}], 'batch_nodes_post_animate': [('testImage', 'PyClipNode'), ('CameraMatch', 'PyNode')]}",
  "stdout": "",
  "stderr": "",
  "error": null,
  "traceback": null
}
```

## Findings

1. **Animate did NOT materialize any channel on the matchbox PyNode.** The 11 candidate channel containers (`channels`, `animation_data`, `animation`, `anim_data`, `channel`, `anim`, `animations`, `parameters`, `params`, `uniforms`, `inputs`) ALL still return `NoneType` — identical to Probe 1's un-animated result. Setting one keyframe on `vp1_l1_start` made zero observable difference at the PyNode wrapper layer.
2. **`input_sockets` / `output_sockets` / `sockets` are schematic-node sockets, NOT shader uniforms.** `input_sockets` is `list` of `str` containing `['Input 1']` (the matchbox's "Front" texture input renamed to socket label "Input 1"). `first_item_type: str` — items are plain Python strings. Dead lead.
3. **`mb.attributes` is unchanged** — still the same 16 schematic-node metadata items, none matching `vp/l1/l2/start/end/axis` filter.
4. **`get_attribute()` is not a method on PyNode.** All 6 name-format attempts (`vp1_l1_start`, `VP1_L1_Start`, `L1 Start`, `L1Start`, `vp1_l1_start_x`, `vp1_l1_start.x`) failed with `TypeError: 'NoneType' object is not callable` — `mb.get_attribute` returned None via the permissive `__getattr__`, then we tried to call None.
5. **No sibling Channel-bearing node was created by Animate.** Batch still has the same 2 nodes (`testImage`, `CameraMatch`). Animate did not spawn a sidecar.
6. **NEW LEAD — `flame.batch` post-Animate exposes `mimic_link`.** This was NOT present in Probe 1's `flame_batch_chan` (which was `[]`). `mimic_link` is Flame's "Mimic Link" channel-linking mechanism — adjacent to the expression-link path Probe 3 will test. Worth pulling forward into Probe 3.

## Verdict

**DEAD** — animated matchbox uniforms are NOT readable via the PyNode wrapper, the schematic socket lists, or any per-attribute getter. The Animate operation has zero effect on the surface area we can introspect from Python on the matchbox node itself.

This kills the "matchbox uniforms become Channels on Animate" hypothesis. The shader uniform values clearly live somewhere — Flame ships them to the GPU each frame — but that "somewhere" is not on the matchbox PyNode and is not a generic channel container we can enumerate.

Per plan stop rules: DEAD → continue to Checkpoint C → Probe 3 (expression-link picker symmetry test, with `mimic_link` lead pulled forward).

## Carry-forward for Probe 3

- **Top priority lead:** `flame.batch.mimic_link` — investigate what it accepts as a target, what it exposes as available sources. If it can enumerate per-uniform channels on the matchbox, the channel-API path is alive after all (just accessed via a different surface).
- Continue with the planned Probe 3 inspection (Action axis link picker, `flame.get_link_*`, etc.).
