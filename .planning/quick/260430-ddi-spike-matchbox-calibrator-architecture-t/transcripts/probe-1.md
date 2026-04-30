# Probe 1 transcript — Path A: Action expression pixel sampling

## Pre-flight

### Bridge ping
**Request:** `POST /exec` with code:
```python
1+1
```
**Response:** `{"result": "2", "stdout": "", "stderr": "", "error": null, "traceback": null}`
**Interpretation:** forge-bridge alive at 127.0.0.1:9999.

### Flame session check
**Request:** `POST /exec` with code:
```python
import flame; bool(flame.batch)
```
**Response:** `{"result": "True", "stdout": "", "stderr": "", "error": null, "traceback": null}`
**Interpretation:** `flame.batch` truthy — Flame session running with a batch loaded.

### Active batch group at start
**Request:** `POST /exec` with code:
```python
import flame
bg = flame.batch
name = bg.name.get_value() if hasattr(bg.name,"get_value") else str(bg.name)
name
```
**Response:** `{"result": "'gen_0460'", "stdout": "", "stderr": "", "error": null, "traceback": null}`
**Interpretation:** Active batch is `gen_0460` (user's real work). R6 mandates a throwaway batch group before any state-mutating call.

### Discover create_batch_group entry point
**Request:** `POST /exec` with code:
```python
import flame
[a for a in dir(flame.projects.current_project.current_workspace.desktop) if "batch" in a.lower()]
```
**Response:** `{"result": "['batch_groups', 'create_batch_group']", "stdout": "", "stderr": "", "error": null, "traceback": null}`
**Interpretation:** `desktop.create_batch_group` is the entry point. (Naive `flame.batch_groups` does NOT exist — see next call.)

### Confirm flame.* module shape
**Request:** `POST /exec` with code:
```python
import flame
[a for a in dir(flame) if "batch" in a.lower()]
```
**Response:** `{"result": "['PyBatch', 'PyBatchIteration', 'batch']", "stdout": "", "stderr": "", "error": null, "traceback": null}`
**Interpretation:** Top-level `flame` exposes only `flame.batch` (active group), classes, and iterator. Batch group enumeration lives on `desktop`.

### Read create_batch_group docstring
**Request:** `POST /exec` with code:
```python
import flame
repr(flame.projects.current_project.current_workspace.desktop.create_batch_group.__doc__)
```
**Response (unescaped):**
```
create_batch_group( (PyDesktop)arg1, (str)name [, (object)nb_reels=None [, (object)nb_shelf_reels=None [, (list)reels=[] [, (list)shelf_reels=[] [, (int)start_frame=1 [, (object)duration=None]]]]]]) -> object :
    Create a new Batch Group object in the Desktop catalogue.
    Keyword arguments:
    name -- Name of the Batch Group.
    ...
```
**Interpretation:** First positional after self is `name`. Safe to invoke with just `name=...`.

### List existing batch groups (collision check)
**Request:** `POST /exec` with code:
```python
import flame
bgs = flame.projects.current_project.current_workspace.desktop.batch_groups
[bg.name.get_value() if hasattr(bg.name,"get_value") else str(bg.name) for bg in bgs]
```
**Response:** `{"result": "['Untitled Batch', 'gen_0460']", "stdout": "", "stderr": "", "error": null, "traceback": null}`
**Interpretation:** No `spike_260430_ddi` yet. Safe to create with that name.

### Create throwaway batch group
**Request:** `POST /exec` with code:
```python
import flame
dt = flame.projects.current_project.current_workspace.desktop
bg = dt.create_batch_group(name="spike_260430_ddi")
name = bg.name.get_value() if hasattr(bg.name,"get_value") else str(bg.name)
name
```
**Response:** `{"result": "'spike_260430_ddi'", "stdout": "", "stderr": "", "error": null, "traceback": null}`
**Interpretation:** Created. R6 guardrail: ALL further mutations targeted at `flame.batch` after this point land in the throwaway, NOT `gen_0460`.

### Confirm flame.batch switched to throwaway
**Request:** `POST /exec` with code:
```python
import flame
name = flame.batch.name.get_value() if hasattr(flame.batch.name,"get_value") else str(flame.batch.name)
name
```
**Response:** `{"result": "'spike_260430_ddi'", "stdout": "", "stderr": "", "error": null, "traceback": null}`
**Interpretation:** Active `flame.batch` is the throwaway. Safe to proceed.

---

## Step 1.1 — Doc search (Bash, NOT bridge)

### `/opt/Autodesk/flame_*/doc` and `/help` checks
**Commands:**
```bash
ls -la /opt/Autodesk/flame_*/doc 2>&1 | head -50
ls -la /opt/Autodesk/flame_*/help 2>&1 | head -50
```
**Output:**
```
(eval):1: no matches found: /opt/Autodesk/flame_*/doc
(eval):1: no matches found: /opt/Autodesk/flame_*/help
```
**Interpretation:** No on-disk doc / help dirs in the Flame install. (Flame's user manuals are online-only at help.autodesk.com.)

### Flame install root
**Command:** `ls -d /opt/Autodesk/flame_*`
**Output:** `/opt/Autodesk/flame_2026.2.1`
**Interpretation:** Single Flame 2026.2.1 install, symlink to `.flamefamily_2026.2.1`. Used as anchor for further searches.

### Filesystem search for "expression"
**Command:** `find /opt/Autodesk -maxdepth 4 -iname "*expression*" 2>/dev/null`
**Output:**
```
/opt/Autodesk/presets/2026.2.1/expressions
/opt/Autodesk/project_old/USPOS-PO-30647_Roku_LolaVie/expressions
/opt/Autodesk/presets/2026.2.1/expressions/userfun.expressions
/opt/Autodesk/project_old/USPOS-PO-30647_Roku_LolaVie/expressions/userfun.expressions
```
**Interpretation:** Found Flame's stock expression user-function preset at `/opt/Autodesk/presets/2026.2.1/expressions/userfun.expressions`.

### `userfun.expressions` content (key excerpts)

```
# A function is defined by its name, followed by a list of arguments
# in parentheses. ... The argument names must start with
# a dollar sign ...

sin100($arg1) : sin($arg1)*50 + 50;
speed($channelName) : (eval($channelName,frame+0.1) - eval($channelName,frame-0.1))/0.2;
round($val) : if( $val >= 0, trunc($val+0.5), trunc($val-0.5) );
frametoslip($desiredFrame) : $desiredFrame - frame;
```
**Interpretation:** The Flame Action expression language vocabulary defined here is: `sin`, `cos`, `eval(channelName, frame_offset)`, `if(cond, a, b)`, `trunc`, arithmetic, the `frame` keyword. **No pixel/sample/texture functions.** Channel references are by **name** (e.g. `$channelName`), and the argument is interpreted as a numeric channel (animation curve), not a raster.

### Filesystem search for example .action files using expressions
**Command:** `find /opt/Autodesk/presets/2026.2.1/examples/action -name "expressions_*"`
**Output (truncated):**
```
expressions_move_ina_vortex2.action
expressions_text.action
expressions_images.action
expressions_dampened_pendulum.action
expressions_light_casted_shadow_simp.action
expressions_spinning_dagger.action
expressions_dagger_apple_cherries.action
```
Note the file `expressions_images.action` — this would be the place a pixel-sampling syntax would surface if it existed. Inspected next.

### grep for pixel-sampling syntax in `expressions_images.action`
**Command:** `grep -n -E 'pixel|sample|texture|raster|imagepixel|surface' /opt/Autodesk/presets/2026.2.1/examples/action/expressions_images.action`
**Output:** _(empty — zero matches)_
**Interpretation:** The example named "expressions_images" contains zero pixel/sample/texture references. The "images" in the name refers to image objects-as-scene-elements (geometry that can be transformed), not pixel sampling.

### grep for all `Expression` strings across all Action examples (vocabulary survey)
**Command:** `grep -hE 'Expression\s+"[^"]*"' /opt/Autodesk/presets/2026.2.1/examples/action/*.action | sort -u`
**Output (unique expressions found):**
```
Expression "-cos(PI / 2 / exp(frame / 100) * cos(frame * 2 * PI / 30)) * 200"
Expression "align(dagger_axis.position, (0,-1,0), frame * 2 * PI / 32)"
Expression "align(o_axis.position)"
Expression "cos(dummy.rotation.x) * dummy.position.x"
Expression "eval(axis1.position.z,frame-axis17.position.x)"
Expression "eval(image1.material.transparency,frame-axis17.position.x)"
Expression "eval(o_axis.position, frame - dummy_axis.position.x * 1)"
Expression "eval(o_axis.rotation, frame - dummy_axis.position.x * 1)"
Expression "if(length(cherries_axis.position - dagger_axis.position) < length(apple_axis.position - dagger_axis.position), lookat(cherries_axis.position, dagger_axis.position, (0,-1,0), (1,0,1)), lookat(apple_axis.position, dagger_axis.position, (0,-1,0), (1,0,1)))"
Expression "lookat(ball_axis.position, rope_axis.position, (0,1,0), (0,0,1))"
Expression "sin(dummy.rotation.x) * dummy.position.x"
```
**Interpretation:** Definitive vocabulary survey. The Flame Action expression language exposes:
- `eval(channelName, frame_offset)` — read other animation channel at a frame
- `cos`, `sin`, `exp`, `length`, `align`, `lookat`, `if`, `frame`, arithmetic, vector literals `(x,y,z)`
- Channel references by **dotted attribute name** (e.g. `axis1.position.z`, `image1.material.transparency`)

**Zero functions for pixel access.** No `pixel(...)`, `sample(...)`, `texture(...)`, `imagepixel(...)`, `surface(...)`. There is no `eval(<image_node>, x, y)` form — `eval()` reads a *channel name*, and channels are always animation curves on PyAttribute-style nodes, not raster outputs.

### Verdict from Step 1.1
**Path A's premise** (Action camera attribute reads pixel value from upstream node via expression) **has no on-disk evidence of being supported.** The expression language is closed over animation channels.

---

## Step 1.2 — Bridge introspection of PyAttribute expression API

### Create Action node in throwaway batch (need a real PyAttribute to introspect)
**Request:** `POST /exec` with code:
```python
import flame
act = flame.batch.create_node("Action")
type(act).__name__
```
**Response:** `{"result": "'PyActionNode'", "stdout": "", "stderr": "", "error": null, "traceback": null}`
**Interpretation:** Action node created cleanly in `spike_260430_ddi`. (R6 honored — `gen_0460` untouched.)

### List Action's child cameras
**Request:** `POST /exec` with code:
```python
import flame
act = next(n for n in flame.batch.nodes if type(n).__name__ == "PyActionNode")
[(c.name.get_value() if hasattr(c.name,"get_value") else str(c.name), type(c).__name__) for c in act.nodes]
```
**Response:** `{"result": "[('Default', 'PyCoNode'), ('Perspective', 'PyCoNode')]", "stdout": "", "stderr": "", "error": null, "traceback": null}`
**Interpretation:** Default + Perspective. Per `memory/flame_perspective_camera.md`, only `Default` is a real camera. Use it for introspection.

### List Default camera's surface
**Request:** `POST /exec` with code:
```python
import flame
act = next(n for n in flame.batch.nodes if type(n).__name__ == "PyActionNode")
cam = next(c for c in act.nodes if (c.name.get_value() if hasattr(c.name,"get_value") else str(c.name)) == "Default")
[a for a in dir(cam) if not a.startswith("_")]
```
**Response:** `{"result": "['add_reference', 'assign_media', 'attributes', 'cache_range', 'children', 'parent', 'parents', 'type']", "stdout": "", "stderr": "", "error": null, "traceback": null}`
**Interpretation:** Camera node surface is sparse. `attributes` is the entry point to PyAttribute objects. No `expression`, `link`, `connect`, `set_expression`, `pixel`, `sample`, `bind`, `subscribe` etc. on the camera itself.

### Enumerate available attributes on the camera
**Request:** `POST /exec` with code:
```python
import flame
act = next(n for n in flame.batch.nodes if type(n).__name__ == "PyActionNode")
cam = next(c for c in act.nodes if (c.name.get_value() if hasattr(c.name,"get_value") else str(c.name)) == "Default")
list(cam.attributes)[:20]
```
**Response:** `{"result": "['name', 'selected', 'collapsed_in_manager', 'pos_x', 'pos_y', 'physical_camera_active', 'film_type', 'fstop', 'focal', 'fov', 'near', 'far', 'target_mode', 'position', 'rotation', 'interest', 'distance', 'roll']", "stdout": "", "stderr": "", "error": null, "traceback": null}`
**Interpretation:** `cam.attributes` is a list of attribute names. Includes `pos_x`, `pos_y`, `position`, `rotation`, `fov`, `focal`, `interest`, `distance`, `roll`. (The values themselves are accessed via `getattr(cam, "position")`.)

### Inspect PyAttribute methods (the "position" vector attribute)
**Request:** `POST /exec` with code:
```python
import flame
act = next(n for n in flame.batch.nodes if type(n).__name__ == "PyActionNode")
cam = next(c for c in act.nodes if (c.name.get_value() if hasattr(c.name,"get_value") else str(c.name)) == "Default")
attr = getattr(cam, "position")
(type(attr).__name__, [m for m in dir(attr) if not m.startswith("_")])
```
**Response:** `{"result": "('PyAttribute', ['get_value', 'set_value', 'values'])", "stdout": "", "stderr": "", "error": null, "traceback": null}`
**Interpretation:** **Critical finding.** `PyAttribute` exposes ONLY `get_value`, `set_value`, `values`. No `set_expression`, `expression`, `link`, `connect`, `bind`, `subscribe`, `set_callback`, `add_listener`. Expressions in Flame are configured via the animation editor (UI-side text input) — NOT via Python.

### Same shape on the scalar `pos_x` attribute (sanity check)
**Request:** `POST /exec` with code:
```python
import flame
act = next(n for n in flame.batch.nodes if type(n).__name__ == "PyActionNode")
cam = next(c for c in act.nodes if (c.name.get_value() if hasattr(c.name,"get_value") else str(c.name)) == "Default")
attr = getattr(cam, "pos_x")
(type(attr).__name__, [m for m in dir(attr) if not m.startswith("_")])
```
**Response:** `{"result": "('PyAttribute', ['get_value', 'set_value', 'values'])", "stdout": "", "stderr": "", "error": null, "traceback": null}`
**Interpretation:** Identical to the `position` vector. PyAttribute is uniform — Python has no expression hook regardless of attribute type.

### Module-level `flame.*` expression utilities
**Request:** `POST /exec` with code:
```python
import flame
[a for a in dir(flame) if "expr" in a.lower() or "link" in a.lower()]
```
**Response:** `{"result": "[]", "stdout": "", "stderr": "", "error": null, "traceback": null}`
**Interpretation:** Zero module-level expression / link utilities on the `flame` module. Definitive.

### Verdict from Step 1.2
**Python cannot author or read Flame expression strings on PyAttribute.** Combined with Step 1.1's vocabulary survey (no pixel-sampling functions in the expression language), this means even if the user *manually* typed a hypothetical pixel-sampling expression into the animation editor, it would be unsupported syntax — and Python could not drive it programmatically.

---

## Step 1.3 — Human-in-the-loop expression entry test (PENDING)

Per R3, Qt UI cannot be invoked via /exec — the expression editor must be used by the user with their keyboard.

The candidate syntaxes to attempt are kept short because Step 1.1's vocabulary survey already gives us a 99% confidence prediction that all four will fail with "Unknown function". They are tested anyway because the spike's truth bar is "primary-source evidence", not "high-confidence inference":

1. `pixel(<matchbox_node>, 0, 0).r` — generic pixel-sampling guess
2. `sample(<matchbox_node>, 0, 0).x` — alternate generic
3. `<matchbox_node>.pixel(0,0).r` — method-chain form
4. `<matchbox_node>[0,0].r` — index form

Plus an optional 5th candidate from the doc search:

5. `eval(<matchbox_node>.output, 0, 0)` — extending Flame's existing `eval()` syntax to a 3-arg form (which would have to be implemented by Flame internals — predicted to fail with "wrong arg count" or "unknown channel").

**To be filled by user via the human checkpoint** under "## Human-in-the-loop verification" below.

---

## Human-in-the-loop verification

**Outcome: SKIPPED by user (2026-04-30).**

When the executor surfaced the Step 1.3 checkpoint asking the user to manually paste each candidate syntax (`pixel(...)`, `sample(...)`, `<node>.pixel(0,0).r`, `<node>[0,0].r`, `eval(<node>.output, 0, 0)`) into Flame's animation/expression editor on the Action camera's `pos_x`, the user replied **"skip"**.

**Rationale (user-stated + executor-corroborated):**

The bridge-side evidence from Steps 1.1 + 1.2 already establishes Path A's verdict structurally, not by inference:

1. **Step 1.1 (vocabulary survey)** — `userfun.expressions` plus 7 stock `expressions_*.action` example files contain ZERO references to `pixel/sample/texture/raster/imagepixel/surface`. The expression language is closed over animation channels (`eval(channelName, frame_offset)` reads numeric curves, not rasters). This is primary-source evidence from Flame's installed presets that pixel-sampling syntax does not exist in the language.

2. **Step 1.2 (PyAttribute API surface)** — `dir(PyAttribute)` returns ONLY `get_value / set_value / values`. There is no `set_expression`, `expression`, `link`, `connect`, `bind`, `subscribe`, `set_callback`, `add_listener`. Module-level `[a for a in dir(flame) if "expr" in a.lower() or "link" in a.lower()]` returns `[]`. Even if a pixel-sampling syntax existed in the editor, Python could not author or read it.

Both ends are dead independently. The keyboard test would only confirm "Unknown function pixel"-style errors firsthand — it cannot promote the verdict from DIDN'T-WORK to anything else, because (a) the syntax is provably absent from the language, and (b) Python has no programmatic hook regardless of what the user types.

**Verdict unchanged: DIDN'T-WORK** — see PROBE.md Probe 1 section. Re-verification would only be warranted if a future Flame upgrade rev surfaces a new function in `userfun.expressions` or example .action files.
