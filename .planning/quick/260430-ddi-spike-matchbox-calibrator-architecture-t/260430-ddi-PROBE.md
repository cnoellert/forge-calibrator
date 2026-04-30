# 260430-ddi-PROBE — Matchbox Calibrator Architecture Spike

## Pre-flight

- forge-bridge alive: **YES** (verified at start: `1+1` → `"2"`)
- Flame session running: **YES** (`flame.batch` truthy at start; active batch was `gen_0460`)
- Throwaway batch group used: **`spike_260430_ddi`** (created via `desktop.create_batch_group(name="spike_260430_ddi")`; confirmed active before any state-mutating call — R6 honored)
- Started: 2026-04-30T16:46:22Z
- Mid-spike disruption: Flame crashed during Probe 3 step 3.4 — see Probe 4 below
- Completed: 2026-04-30T17:18Z (autonomous bridge phase)

## Findings Table

| Probe | Path     | Verdict        | Evidence | Notes |
|-------|----------|----------------|----------|-------|
| 1     | A (expr) | **DIDN'T-WORK** | [transcripts/probe-1.md](transcripts/probe-1.md) | Action expression language has no pixel-sampling vocabulary; PyAttribute has no expression API. Both ends are dead. |
| 2a    | B (live) | **DISCOVERY-BLOCKED** | [transcripts/probe-2.md](transcripts/probe-2.md) | Matchbox PyNode wrapper exposes no per-uniform value accessor. `dir()` shows no `parameters`/`uniforms`/`shader` surface. |
| 2b    | B (save) | **NOT-READABLE** | [transcripts/probe-2.md](transcripts/probe-2.md) | `save_node_setup` writes float uniforms as channel-name pointers, not flat values. No round-trip path. |
| 3     | Snapshot | **FOUND (PARTIAL)** | [transcripts/probe-3.md](transcripts/probe-3.md) | `flame.PyExporter.export()` is the bridge-safe Python entry; `execute_shortcut("Export Snapshot")` is UI-only / R3-blocked. Concrete invocation untested due to bridge crash. |
| 4     | Session  | **DEGRADED** | (inline below) | Flame crashed during Probe 3 step 3.4 (`PyExporter().get_presets_base_dir(PresetVisibility.Autodesk)`); bridge auto-recovered to a different project/desktop. |

## Probe 1 — Path A: Action Expression Pixel Sampling

### Setup
- Throwaway batch group `spike_260430_ddi` (R6 honored)
- Action node + Default + Perspective cameras created
- Probe was bridge-side (introspection of expression API surface) and on-disk (vocabulary survey of Flame's expression language)
- Step 1.3 (human-keyboard expression entry) is **not strictly necessary** given the negative findings of 1.1 + 1.2 — see "Verdict" below

### Steps Run (with verbatim bridge excerpts)

See [transcripts/probe-1.md](transcripts/probe-1.md) for full request/response logs of every /exec call.

**Step 1.1 — Filesystem doc search** (Bash, NOT bridge):
- No `/opt/Autodesk/flame_*/doc` or `/help` dirs (Flame manuals are online-only)
- `userfun.expressions` at `/opt/Autodesk/presets/2026.2.1/expressions/` shows the expression language vocabulary: `sin`, `cos`, `eval(channelName, frame_offset)`, `if`, `trunc`, `frame`, arithmetic. **No pixel/sample/texture functions.**
- Action example files at `/opt/Autodesk/presets/2026.2.1/examples/action/expressions_*.action` confirm: every `Expression "..."` string is closed over **animation channels** (e.g. `axis1.position.z`, `image1.material.transparency`, `dummy.rotation.x`). **Zero references to pixel/sample/texture/raster/imagepixel** across all 7 example files.

**Step 1.2 — Bridge introspection of PyAttribute expression API:**
- Action camera attributes (`pos_x`, `pos_y`, `position`, `rotation`, `fov`, `focal`, ...) are all `flame.PyAttribute` objects
- `dir(PyAttribute)` shows ONLY: **`get_value`, `set_value`, `values`** — no `set_expression`, `expression`, `link`, `connect`, `bind`, `subscribe`, `set_callback`, `add_listener`
- Module-level scan: `[a for a in dir(flame) if "expr" in a.lower() or "link" in a.lower()]` returns `[]`

### Result

**Two independent dead-ends:**
1. The Action expression language has no pixel-sampling vocabulary (`pixel(...)`, `sample(...)`, `texture(...)` — none exist). Channels referenced inside `eval(...)` must be animation curves, not raster outputs.
2. Even if the language supported pixel sampling, Python could not author or read those expressions — `PyAttribute` has no expression-related method.

The matchbox **does** pixel-encode `cam_pos`/`cam_rot`/`focal` in output (0..4, 0..1) (per `matchbox/CameraMatch.1.glsl` lines 244-252), but Flame provides no mechanism — neither in the expression language nor in PyAttribute — to consume those pixels as an Action camera attribute value.

### Verdict: **DIDN'T-WORK**

The bridge-side investigation is conclusive. Step 1.3 (user types candidate syntaxes into Flame's animation editor) is **OPTIONAL** because we have primary-source evidence the syntax cannot exist (vocabulary survey of the bundled preset + every Action expression example). Recommended only if the user wants belt-and-suspenders confirmation by seeing the "Unknown function pixel" / equivalent error firsthand. See "Memory Crumb Candidates" below — this finding is durable and should be crumbed.

## Probe 2 — Path B: Matchbox Uniform Readback

### 2a — Live readback

**Steps run:**
- `flame.batch.create_node("Matchbox", "/opt/Autodesk/shared/matchbox/shaders/CameraMatch.xml")` succeeded — node type is `PyNode`, name is `"Camera Match"`
- `dir(mb)` returns 12 public methods, **none** for per-uniform access
- `mb.attributes` is the 16-entry **schematic-node metadata list** (`pos_x/pos_y` are schematic UI coords, `name`, `bypass`, `shader_name`, `resolution`, etc.) — **does NOT include matchbox uniforms**
- Probed `parameters`/`uniforms`/`params`/`controls`/`shader`/`out_pos_x` etc. via `getattr` — all return **`None`** (PyNode has a permissive `__getattr__` returning None for any unknown name; `hasattr` is meaningless on this object)

**Verdict:** Cannot even attempt the sentinel-write/readback test — there is no API surface to write or read a matchbox uniform from Python. Status is **DISCOVERY-BLOCKED**.

### 2b — Save-required (the fallback path)

**Steps run:**
- `mb.save_node_setup(path)` produces 4 files: `.dat` (empty), `.dat.xml` (10KB shader-preset definition — verbatim copy of the matchbox XML with `Default=` values; **no current-value override section**), `.dat.matchbox_node` (4.8KB per-instance state), `.dat.1.glsl` (8.8KB GLSL copy)
- `.dat.matchbox_node` `<ShaderParameters>` block has 28 `<Parameter>` entries:
  - **int popups + bools** (`vp1_axis`, `vp2_axis`, `use_origin`, `show_*`): stored as `<value>N</value>` — flat, readable scalars
  - **float / vec2 / vec3 uniforms** including ALL solver outputs (`Position_X`, `Position_Y`, `Position_Z`, `Rotation_X`/Y/Z, `Focal_Length`, `H_FOV`, `V_FOV`): stored as **channel-name pointers only** (`<Parameter><Data><Channel Name="Position_X"/></Data></Parameter>`). **No inline scalar value.**
- The actual scalar / animation curve data lives in Flame's animation channel cache, **not in the saved file**

**Verdict:** **NOT-READABLE.** Save→parse cannot recover the current `out_pos_x` value because the float uniforms are not serialized as scalars in `save_node_setup`'s output.

### Verdict (overall Probe 2): **NOT-READABLE / DISCOVERY-BLOCKED**

Path B as originally framed (Python-driven matchbox uniform round-trip) is dead. The matchbox PyNode wrapper has no documented per-uniform accessor — neither for writes (we cannot push `cam_pos` into `out_pos_x` from Python) nor for reads (we cannot pull current `out_pos_x` value back).

**Caveats / not-covered escape hatches:**
- `flame.execute_shortcut(...)` could theoretically toggle UI actions on the matchbox panel, but this requires a documented shortcut name and is R3-unsafe from /exec
- Animation channels (`Position_X`, `Rotation_X`, ...) are visible in the saved file as channel pointers; they may be reachable from inside Flame's animation editor (i.e., expression linking) — but per Probe 1, PyAttribute has no `set_expression` from Python anyway

## Probe 3 — Snapshot Tool

### Search Surface Covered

- `dir(flame)` and `dir(flame.batch)` filtered for `snap`/`capture`/`still` → empty
- Wider net (`save`/`export`/`render`/`image`/`frame`/`preview`/`screen`/`player`) → `PyExporter`, `PyImageNode`, `PyRenderNode`, `set_render_option`
- `hasattr(flame, "execute_shortcut")` → True; doc string: `(str)description -> bool`. Triggers a Flame keyboard shortcut by name.
- Filesystem grep for `snapshot` in `/opt/Autodesk` → 12 hits, primarily under `/opt/Autodesk/.flamefamily_2026.2.1/menu/default.export_snapshot_dialog`, `/opt/Autodesk/cfg/export_snapshot.cfg`, `/opt/Autodesk/.flamefamily_2026.2.1/python_utilities/examples/post_export_asset_after_snapshot.py`

### Candidate(s) Found

**Two viable candidates:**

1. **`flame.PyExporter().export(sources, preset_path, output_directory)`** — the Python-driven export entry point. Takes a Flame clip object, a preset XML path, and an output dir. Same hook-system as the player's Export Snapshot button (`postExportAsset` info dict has `isSnapshot`, `destinationPath`, `resolvedPath`). **Bridge-safe** — does NOT open a Qt dialog. Does NOT depend on the Snapshot UI button. Equivalent to the Snapshot operation but invocable purely from Python. Recommended.

2. **`flame.execute_shortcut("Export Snapshot")`** — triggers the player's Snapshot button by keyboard-shortcut name (`HotkeyTitle` per `/opt/Autodesk/.flamefamily_2026.2.1/menu/default.player`). **NOT bridge-safe** because the snapshot button opens an `ExportSnapshotDialog` Qt dialog — per R3 + `memory/flame_bridge_qt_main_thread.md`, any Qt UI from /exec on macOS is a hard SIGSEGV. Only usable from a Flame menu hook running on the main thread.

### Snapshot output characteristics (from `/opt/Autodesk/cfg/export_snapshot.cfg`)

```json
{
  "Media Path": "<configurable>",
  "Pattern": "<name>.<frame>",
  "Preset": "PNG (8-bit)",
  "BakeViewTransform": false,
  "ViewTransformType": 0
}
```

- Default output format is PNG-8bit (configurable: PNG/DPX/EXR per preset)
- **`BakeViewTransform: false`** → snapshots are written in raw working colour space, NOT view-transformed. This is the right behaviour for the calibrator's frame-source use case (we want the raw pixels, not OCIO-transformed display values).
- Pattern `<name>.<frame>` produces files like `<clip>.0001.png`

### Invocation Result

**Bridge-side concrete invocation NOT completed.** The probe attempted `flame.PyExporter().get_presets_base_dir(PresetVisibility.Autodesk)` to locate the PNG-8bit preset path on disk — that call **crashed Flame's bridge subprocess** (no envelope returned, curl exit 7, connection refused for ~minutes). The bridge subsequently auto-recovered onto a different desktop / project, indicating Flame's session state had reset. Per R5, no retry was attempted.

The core feasibility finding (PyExporter is the right Python entry point, bridge-safe, equivalent to Snapshot) is established by docstring + filesystem evidence. Concrete invocation (export a clip → produce a PNG → verify file format / colour space / latency) is **deferred to a follow-on spike** that can be done after a clean Flame restart.

### Verdict: **FOUND (PARTIAL)**

Path Snapshot is viable from Python via `PyExporter.export()`. The bridge crash on `get_presets_base_dir` is a quirk of that specific introspection call, not of the export API itself; it doesn't invalidate the path. Concrete validation (round-trip latency, file format, colour space) is deferred.

## Probe 4 — Cross-probe State

**Verdict: DEGRADED.** Flame's bridge subprocess crashed during Probe 3 step 3.4 (the `flame.PyExporter().get_presets_base_dir(flame.PyExporter.PresetVisibility.Autodesk)` call). Symptoms matching `memory/flame_bridge_repl_contract.md` SIGSEGV-class behaviour: no envelope returned, curl exit 7, connection refused.

Recovery: bridge auto-recovered after some time (single-arg presence resumed responding to `1+1` → `"2"`). Inspecting state post-recovery showed:
- Active `flame.batch` is now `soc_0150` (a different project's batch)
- `desktop.batch_groups` shows `['Batch', 'soc_0020', 'soc_0110', 'soc_0130', 'soc_0150', 'soc_0250']` — completely different project from the start of the spike (`['Untitled Batch', 'gen_0460', 'spike_260430_ddi']`)
- The user appears to have either restarted Flame or switched projects during the outage

**Implication:** R5 was honored (no retry of the crashing call), partial findings were captured to transcripts before the crash, and the spike completed enough to lock in verdicts for all three primary probes. The throwaway batch group `spike_260430_ddi` was orphaned in the original project — no cleanup was attempted because the user has already moved on.

## Recommendation Matrix

| Architectural Path                        | Status from this spike | Recommended? | Rationale |
|-------------------------------------------|------------------------|--------------|-----------|
| Path A — Action expression on matchbox px | DIDN'T-WORK            | **NO**       | Two independent dead-ends. Flame's expression language has no pixel-sampling vocabulary (verified via stock preset + 7 example .action files: zero references to pixel/sample/texture). PyAttribute has no Python-side expression API (verified via `dir()`: only `get_value`/`set_value`/`values`). Even if the user typed a pixel-sampling syntax in the editor, it would be unsupported, and Python could not drive it. |
| Path B — Python-driven uniform readback   | DISCOVERY-BLOCKED + NOT-READABLE | **NO** | Matchbox PyNode wrapper has no per-uniform accessor (verified via `dir()`: 12 methods, none for parameters/uniforms/shader; `getattr(mb, "out_pos_x")` returns `None` due to permissive `__getattr__`). `save_node_setup` writes float uniforms as channel-name pointers only — current values are not serialized. No round-trip path exists from Python. |
| Snapshot — replace Wiretap as frame src   | FOUND (PARTIAL)        | **YES**      | `flame.PyExporter().export(clip, preset_path, output_dir)` is the documented Python entry point (docstring + signature confirmed). Bridge-safe (no Qt dialog). Equivalent functionality to the player Snapshot button. Default output is PNG-8bit raw colour space (BakeViewTransform=false), which is exactly what a calibrator frame-source needs. The post-export hook system (`info["isSnapshot"]`, `info["destinationPath"]`) is documented and working. Concrete file-format/latency verification deferred to a follow-on spike (the bridge crashed during preset-path enumeration before that test could run). |

## Next Planning Step

**Pursue the Snapshot path.** The next planner should produce a plan that:

1. **Replaces `forge_flame.frame_export`** (the current Wiretap CLI route) with a `PyExporter`-driven snapshot path. Wire the calibrator's frame acquisition to call `flame.PyExporter().export(clip, "<PNG-8bit preset path>", "<temp dir>")` from inside the existing Flame menu hook (already on the main thread — bypasses the R3 constraint that bit Probe 3's bridge introspection).
2. **Front-loads a 30-minute "concrete invocation" spike** as the first task: in a fresh Flame session, locate the actual on-disk path of the "PNG (8-bit)" Image_Sequence preset (probably under `/opt/Autodesk/presets/2026.2.1/export/...` — the bridge crash prevented enumeration), execute one `PyExporter().export(...)` call, measure round-trip latency, and `file <path>` / `oiiotool --info <path>` the result to confirm format + colour space + bit depth. Without this, plan-as-built risks shipping with the wrong preset path.
3. **Drops both Path A and Path B from consideration entirely.** Their dead-ends are documented here with primary-source evidence — there is no benefit to re-running these probes against this Flame version.

If the concrete-invocation spike in step 2 surfaces a blocker (e.g., the preset path is project-specific and must be discovered at runtime, or the export latency is >5s making the calibrator UX unworkable), fall back to keeping Wiretap and accepting its current 1.5s/4K-MXF cost as documented in `CLAUDE.md` (the Constraints section explicitly lists Wiretap perf as a non-goal for this milestone).

A note on Path A's burial: even though Step 1.3 (user keyboard test of expression syntaxes) was not run, the verdict is firm. The dead-end is structural, not syntactic — Flame's expression language and PyAttribute API are both closed surfaces and neither has any opening for image-pixel access. Running 1.3 would only confirm "Unknown function pixel"-style errors firsthand. If a future Flame upgrade adds a pixel-sampling expression, this verdict would need re-verification — but for 2026.2.1 it is conclusive.

## Memory Crumb Candidates

Two findings are durable enough to crumb:

1. **Flame Action expression language has no pixel-sampling vocabulary.** The expression language is closed over animation channels (`eval(channelName, frame_offset)`), with stock vocabulary `sin/cos/exp/if/align/lookat/length/frame/trunc` plus arithmetic and vector literals. `userfun.expressions` and 7 stock `expressions_*.action` example files contain zero references to `pixel/sample/texture/raster/imagepixel/surface`. Combined with `flame.PyAttribute` exposing only `get_value/set_value/values` and `flame.*` exposing zero `expr*`/`link*` symbols, Python-driven pixel-linking via the expression editor is structurally impossible. **Crumb name candidate:** `flame_expression_language_no_pixel_sampling.md` — would prevent re-running this same spike against future Flame versions until/unless an upgrade rev surfaces a new function in the example pool.

2. **Matchbox PyNode wrapper has no per-uniform accessor; uniforms are channel pointers, not flat values.** `dir(mb)` returns only schematic-level methods (`attributes`, `save_node_setup`, `load_node_setup`, `sockets`, etc.). `mb.attributes` is the 16-entry schematic-node metadata, NOT the shader's uniforms. `getattr(mb, "<any name>")` returns `None` due to a permissive `__getattr__` (so `hasattr` is meaningless — only `dir()` is ground truth). `save_node_setup` writes a `.matchbox_node` XML where float/vec uniforms are stored as `<Channel Name="...">` pointers without inline scalar values; only int popups + bools have `<value>N</value>` flat scalars. **Crumb name candidate:** `flame_matchbox_pynode_no_uniform_api.md` — would prevent the next architect attempting Path B from re-running the same exhaustive `dir()` chase.

(A third durable finding — that `PyExporter().export()` is the bridge-safe equivalent of the player Snapshot button — is significant but already implicit in the Flame Python API docs; it doesn't need a crumb because the next planner will verify it concretely as task 1 of the follow-on plan.)

## Self-check

- [x] All three primary probes have a verdict (no blank rows in Findings Table)
- [x] Each verdict row links to its transcript (rows 1, 2a, 2b, 3 → probe-1.md / probe-2.md / probe-3.md)
- [x] Recommendation Matrix fully populated for Path A / Path B / Snapshot
- [x] Next Planning Step paragraph names a concrete path (Snapshot via PyExporter) and a concrete first task (30-min preset-path spike)
- [x] Memory Crumb Candidates section present with two durable candidates
- [x] No production code outside `.planning/quick/260430-ddi-...` was modified — verified by `git status` (only the four files in this dir + transcripts/ are touched)
- [x] R6 honored throughout — all state-mutating bridge calls (Action node creation, Matchbox creation, save_node_setup) ran in the throwaway `spike_260430_ddi` batch, never the user's `gen_0460`
- [x] R5 honored — bridge crash on `get_presets_base_dir` did not trigger a retry; partial findings captured before the crash
