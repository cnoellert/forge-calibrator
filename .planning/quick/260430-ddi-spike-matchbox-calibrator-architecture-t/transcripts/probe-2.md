# Probe 2 transcript — Path B: Matchbox uniform readback

## R6 guardrail

Active batch is `spike_260430_ddi` (throwaway). Verified by Probe 1 pre-flight transcript above. All Probe 2 mutations land in the throwaway, never `gen_0460`.

---

## Step 2.0 — Setup: drop CameraMatch matchbox into throwaway batch

### Discover create_node signature
**Request:** `POST /exec` with code:
```python
import flame
repr(flame.batch.create_node.__doc__)
```
**Response (unescaped):**
```
create_node( (PyBatch)arg1, (str)node_type [, (str)file_path='']) -> object :
    Create a Batch node object in the Batch schematic.
    Keyword argument:
    node_type -- Must be a value from the PyBatch.node_types or the name of a node in the User, Project, or Shared bin.
```
**Interpretation:** Second arg is a file path. For Matchbox, that's the shader XML.

### Find Matchbox node type
**Request:** `POST /exec` with code:
```python
import flame
[t for t in flame.batch.node_types if "match" in t.lower() or "shader" in t.lower() or "matchbox" in t.lower()]
```
**Response:** `{"result": "['Match Grain', 'Matchbox']"}`
**Interpretation:** `"Matchbox"` is the node-type string.

### Locate CameraMatch.xml on disk
**Command:** `find /opt/Autodesk -maxdepth 6 -iname 'CameraMatch*'`
**Output:**
```
/opt/Autodesk/shared/matchbox/shaders/CameraMatch.xml
/opt/Autodesk/shared/matchbox/shaders/CameraMatch.1.glsl
```

### Create the matchbox node
**Request:** `POST /exec` with code:
```python
import flame
mb = flame.batch.create_node("Matchbox", "/opt/Autodesk/shared/matchbox/shaders/CameraMatch.xml")
(type(mb).__name__, mb.name.get_value() if hasattr(mb.name,"get_value") else str(mb.name))
```
**Response:** `{"result": "('PyNode', 'Camera Match')", "stdout": "", "stderr": "", "error": null, "traceback": null}`
**Interpretation:** Matchbox created; node class is `PyNode` (not `PyMatchboxNode` or `PyShader`); display name is `"Camera Match"` (matches the matchbox XML's `Name="Camera Match"` attribute).

---

## Step 2.1 — Discover matchbox PyNode surface

### Public attribute surface
**Request:** `POST /exec` with code:
```python
import flame
mb = next(n for n in flame.batch.nodes if (n.name.get_value() if hasattr(n.name,"get_value") else str(n.name)) == "Camera Match")
[a for a in dir(mb) if not a.startswith("_")]
```
**Response:** `{"result": "['attributes', 'cache_range', 'clear_schematic_colour', 'delete', 'duplicate', 'input_sockets', 'load_node_setup', 'output_sockets', 'parent', 'save_node_setup', 'set_context', 'sockets']"}`
**Interpretation:** Matchbox PyNode has 12 public methods. **No `parameters`, `uniforms`, `params`, `controls`, `shader`, or any per-uniform accessor.** The candidate surface is `attributes`, `save_node_setup`, `load_node_setup`.

### Enumerate `attributes` (the schematic-node attribute list)
**Request:** `POST /exec` with code:
```python
import flame
mb = next(n for n in flame.batch.nodes if (n.name.get_value() if hasattr(n.name,"get_value") else str(n.name)) == "Camera Match")
(type(mb.attributes).__name__, list(mb.attributes)[:60])
```
**Response:** `{"result": "('list', ['pos_x', 'pos_y', 'name', 'collapsed', 'note', 'note_collapsed', 'selected', 'type', 'resolution', 'schematic_colour', 'schematic_colour_label', 'bypass', 'shader_name', 'resolution_mode', 'scaling_presets_value', 'adaptive_mode'])"}`
**Interpretation:** **Critical finding.** `mb.attributes` is the schematic-node metadata only (16 entries: `pos_x/pos_y` are schematic UI coords, `name`, `bypass`, `shader_name`, `resolution`, etc.). **Zero entries for matchbox uniforms** — no `out_pos_x`, `out_rot_x`, `vp1_l1_start`, `image_opacity`, etc. The shader's per-uniform parameters are not exposed through `mb.attributes`.

### Sample three sentinel attributes to confirm
**Request:** `POST /exec` with code:
```python
import flame
mb = next(n for n in flame.batch.nodes if (n.name.get_value() if hasattr(n.name,"get_value") else str(n.name)) == "Camera Match")
attr_results = []
for a in ["shader_name", "type", "resolution"]:
    try:
        v = getattr(mb, a).get_value()
    except Exception as e:
        v = f"<{type(e).__name__}: {e}>"
    attr_results.append((a, v))
attr_results
```
**Response:** `{"result": "[('shader_name', 'Camera Match'), ('type', 'Matchbox'), ('resolution', <flame.PyResolution object at 0xa87ad36a0>)]"}`
**Interpretation:** `shader_name='Camera Match'`, `type='Matchbox'` — node-class metadata. Confirms `attributes` is for the schematic node, not the shader's uniforms.

### grep dir() for parameter/uniform/shader accessor names
**Request:** `POST /exec` with code:
```python
import flame
mb = next(n for n in flame.batch.nodes if (n.name.get_value() if hasattr(n.name,"get_value") else str(n.name)) == "Camera Match")
[a for a in dir(mb) if "param" in a.lower() or "unif" in a.lower() or "shader" in a.lower()]
```
**Response:** `{"result": "[]"}`
**Interpretation:** Zero entries with `param`, `unif`, or `shader` in dir(). Definitive: there is no per-uniform accessor in the documented surface.

### Probe `hasattr` for plausible accessor names — and the gotcha
**Request:** `POST /exec` with code:
```python
import flame
mb = next(n for n in flame.batch.nodes if (n.name.get_value() if hasattr(n.name,"get_value") else str(n.name)) == "Camera Match")
(hasattr(mb, "parameters"), hasattr(mb, "uniforms"), hasattr(mb, "params"), hasattr(mb, "controls"), hasattr(mb, "shader"))
```
**Response:** `{"result": "(True, True, True, True, True)"}`
**Surprise:** all five returned True. Followup probe disambiguates:

**Request:** `POST /exec` with code:
```python
import flame
mb = next(n for n in flame.batch.nodes if (n.name.get_value() if hasattr(n.name,"get_value") else str(n.name)) == "Camera Match")
[(n, type(getattr(mb, n)).__name__) for n in ["parameters", "uniforms", "params", "controls", "shader", "foobar_doesnt_exist"]]
```
**Response:** `{"result": "[('parameters', 'NoneType'), ('uniforms', 'NoneType'), ('params', 'NoneType'), ('controls', 'NoneType'), ('shader', 'NoneType'), ('foobar_doesnt_exist', 'NoneType')]"}`
**Interpretation:** **Critical gotcha.** Matchbox `PyNode` has a permissive `__getattr__` that returns `None` for ANY unknown name (including `foobar_doesnt_exist`). This means `hasattr` is meaningless on this object — only `dir()` is the ground truth. The "True"s above are false positives.

### Try direct dotted access for the actual uniform names
**Request:** `POST /exec` with code:
```python
import flame
mb = next(n for n in flame.batch.nodes if (n.name.get_value() if hasattr(n.name,"get_value") else str(n.name)) == "Camera Match")
results = []
for name in ["out_pos_x", "Position_X", "position_x", "out_focal_mm"]:
    a = getattr(mb, name)
    results.append((name, type(a).__name__, str(a)[:80]))
results
```
**Response:** `{"result": "[('out_pos_x', 'NoneType', 'None'), ('Position_X', 'NoneType', 'None'), ('position_x', 'NoneType', 'None'), ('out_focal_mm', 'NoneType', 'None')]"}`
**Interpretation:** Confirmed — every plausible per-uniform access returns `None`. The matchbox PyNode does not expose its shader uniforms via Python attribute access.

---

## Step 2.2 — Probe save_node_setup as a possible round-trip path

### Read save_node_setup docstring
**Request:** `POST /exec` with code:
```python
import flame
mb = next(n for n in flame.batch.nodes if (n.name.get_value() if hasattr(n.name,"get_value") else str(n.name)) == "Camera Match")
repr(mb.save_node_setup.__doc__)
```
**Response:**
```
save_node_setup( (PyNode)arg1, (str)file_name) -> bool :
    Save a Node setup. A path and a file name must be defined as arguments.
```
**Interpretation:** Single-arg save to disk. Worth probing whether the resulting file contains current uniform values (which would enable a save→parse readback path, though heavy).

### Save the matchbox setup to /tmp
**Request:** `POST /exec` with code:
```python
import flame, tempfile, os
mb = next(n for n in flame.batch.nodes if (n.name.get_value() if hasattr(n.name,"get_value") else str(n.name)) == "Camera Match")
fd, path = tempfile.mkstemp(prefix="matchbox_save_", suffix=".dat")
os.close(fd)
ok = mb.save_node_setup(path)
(ok, path)
```
**Response:** `{"result": "(True, '/var/folders/30/sdkv1lw160v8bq48pwrlbqwm0000gn/T/matchbox_save_ahjf0n7u.dat')"}`
**Interpretation:** Returned `True`; file path returned.

### Inspect produced files
**Command:** `ls -la /var/folders/.../matchbox_save_ahjf0n7u.dat*`
**Output:**
```
-rw-------  ...  0 Apr 30 09:52 /var/folders/.../matchbox_save_ahjf0n7u.dat
-rw-rw-rw-  ...  8817 Apr 30 09:52 /var/folders/.../matchbox_save_ahjf0n7u.dat.1.glsl
-rw-rw-rw-  ...  4829 Apr 30 09:52 /var/folders/.../matchbox_save_ahjf0n7u.dat.matchbox_node
-rw-rw-rw-  ...  10910 Apr 30 09:52 /var/folders/.../matchbox_save_ahjf0n7u.dat.xml
```
**Interpretation:** `save_node_setup` produces 4 files: an empty `.dat` marker, a `.dat.xml` (10KB shader-preset definition), a `.dat.matchbox_node` (4.8KB node-instance state), and a `.dat.1.glsl` (8.8KB copy of the GLSL source).

### `.dat.xml` content (truncated to relevant tail)
```xml
<Uniform Name="out_pos_x" Type="float" Default="0.0" ...></Uniform>
<Uniform Name="out_pos_y" Type="float" Default="0.0" ...></Uniform>
<Uniform Name="out_pos_z" Type="float" Default="0.0" ...></Uniform>
<Uniform Name="out_rot_x" Type="float" Default="0.0" ...></Uniform>
<Uniform Name="out_rot_y" Type="float" Default="0.0" ...></Uniform>
<Uniform Name="out_rot_z" Type="float" Default="0.0" ...></Uniform>
<Uniform Name="out_focal_mm" Type="float" Default="0.0" ...></Uniform>
<Uniform Name="out_hfov" Type="float" Default="0.0" ...></Uniform>
<Uniform Name="out_vfov" Type="float" Default="0.0" ...></Uniform>
```
**Interpretation:** `.dat.xml` is a **verbatim copy of the matchbox shader preset XML** — same Uniform definitions with `Default=` values. **No "current value" override section.** It's the schema, not the state.

### `.dat.matchbox_node` content (the per-instance state file)
```xml
<Setup>
  <Base>
    <Version>21.020000</Version>
    <NAME>Camera Match</NAME>
    <Note><![CDATA[...]]></Note>
    ...
  </Base>
  <State>
    ...
    <ShaderParameters>
      <Parameter><X><Channel Name="X"><Uncollapsed/></Channel></X><Y>...</Y><Icon>True</Icon></Parameter>  // vp1_l1_start (vec2)
      <Parameter><X>...</X><Y>...</Y><Icon>True</Icon></Parameter>                                       // vp1_l1_end
      ... (8 vec2 line endpoints)
      <Parameter><value>1</value></Parameter>      // vp1_axis (int popup)
      <Parameter><value>5</value></Parameter>      // vp2_axis (int popup)
      <Parameter><value>0</value></Parameter>      // use_origin (bool)
      <Parameter>...origin_pt vec2...</Parameter>
      <Parameter><Data><Channel Name="Image_Opacity"><Uncollapsed/></Channel></Data></Parameter>
      <Parameter><Data><Channel Name="Line_Width"><Uncollapsed/></Channel></Data></Parameter>
      <Parameter><Data><Channel Name="Line_Opacity"><Uncollapsed/></Channel></Data></Parameter>
      <Parameter><value>1</value></Parameter>      // show_vp_markers
      <Parameter><value>1</value></Parameter>      // show_extended
      <Parameter><value>1</value></Parameter>      // show_info
      <Parameter><R>...</R><G>...</G><B>...</B></Parameter>     // vp1_color (vec3)
      <Parameter><R>...</R><G>...</G><B>...</B></Parameter>     // vp2_color (vec3)
      <Parameter><Data><Channel Name="Position_X"><Uncollapsed/></Channel></Data></Parameter>
      <Parameter><Data><Channel Name="Position_Y"><Uncollapsed/></Channel></Data></Parameter>
      <Parameter><Data><Channel Name="Position_Z"><Uncollapsed/></Channel></Data></Parameter>
      <Parameter><Data><Channel Name="Rotation_X"><Uncollapsed/></Channel></Data></Parameter>
      <Parameter><Data><Channel Name="Rotation_Y"><Uncollapsed/></Channel></Data></Parameter>
      <Parameter><Data><Channel Name="Rotation_Z"><Uncollapsed/></Channel></Data></Parameter>
      <Parameter><Data><Channel Name="Focal_Length"><Uncollapsed/></Channel></Data></Parameter>
      <Parameter><Data><Channel Name="H_FOV"><Uncollapsed/></Channel></Data></Parameter>
      <Parameter><Data><Channel Name="V_FOV"><Uncollapsed/></Channel></Data></Parameter>
    </ShaderParameters>
    ...
  </State>
</Setup>
```
**Interpretation:** **Decisive structural finding.**

- For **int popups + bools** (`vp1_axis=1`, `vp2_axis=5`, `use_origin=0`, `show_vp_markers=1`, `show_extended=1`, `show_info=1`): the file stores `<value>N</value>` flat scalars — readable from disk.
- For **float / vec2 / vec3 uniforms** (including ALL of the `out_*` solver outputs — `Position_X` through `V_FOV`): the file stores **only a channel-name pointer** (`<Channel Name="Position_X">`) with no inline scalar value. The actual scalar/animation curve data lives elsewhere in Flame's animation cache, which `save_node_setup` does NOT serialize.

This means **the save→parse path cannot read a current `out_pos_x` scalar** from a `save_node_setup` file. Even with a save round-trip, Path B's premise (read `out_*` uniform values via Python) does not work.

---

## Probe 2a — LIVE READBACK (set sentinel + read back)

**Skipped — no API surface to attempt the test.** The matchbox PyNode wrapper has no method, attribute, or accessor that maps to the shader's per-uniform values. Without a `set_value`/`get_value` entry point on the uniform side, neither writing a sentinel `42.0` to `out_pos_x` nor reading it back is possible from Python.

**Verdict:** **DISCOVERY-BLOCKED** for live readback — the API surface required for the test simply does not exist on the documented PyNode wrapper.

## Probe 2b — SAVE-REQUIRED

**Skipped — Step 2.2's structural inspection of `save_node_setup` output rules it out.** The float `out_*` uniforms are stored as channel-name pointers in the saved file, not as flat scalars. Even with a save round-trip, the current value cannot be read back. Save→parse cannot satisfy the requirement.

**Verdict:** **NOT-READABLE** via save→parse.

---

## Probe 2 overall verdict

**NOT-READABLE.** The matchbox PyNode wrapper exposes no per-uniform value accessor (verified via `dir()` and through `save_node_setup` file inspection). Path B as originally framed — a Python-driven round-trip that writes `out_*` solved values into the matchbox and then has the user read them via the matchbox UI / expression linking — would still work for the **write side** if there were a setter (and there isn't one for floats), but the **read side** for verification is dead.

Caveat / not-covered escape hatches:
- `flame.execute_shortcut(...)` could theoretically toggle UI actions (untested for matchbox per-uniform mutation; would need a documented shortcut name).
- `mb.attributes[...]` returns Python `PyAttribute` objects but only for the schematic-node metadata, not for the shader uniforms — confirmed.
- Animation channels (`Position_X`, `Rotation_X`, etc.) are visible in the file as channel pointers; they may be reachable from inside Flame's animation editor (ie, expression linking) but per Probe 1 step 1.2 PyAttribute has no `set_expression` from Python.


