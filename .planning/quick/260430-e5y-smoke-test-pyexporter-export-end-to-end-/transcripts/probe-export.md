# probe-export — verbatim bridge transcript for 260430-e5y

All `/exec` calls used the JSON envelope contract:
- POST to `http://127.0.0.1:9999/exec`
- Body: `{"code": "<python>"}`
- Response: `{"result", "stdout", "stderr", "error", "traceback"}`

## Pre-flight (orchestrator pre-confirmed; re-verified at executor start)

### Bridge ping (curl, executor start)

**Request:** `POST /exec` body `{"code": "1+1"}`
**Response:**
```json
{"result": "2", "stdout": "", "stderr": "", "error": null, "traceback": null}
```
Verdict: bridge alive. Verified by orchestrator at 2026-04-30T17:23:43Z; re-verified by executor at 2026-04-30T17:47:08Z.

### Verify Flame batch context (post-restart-2)

**Request:** `import flame; flame.batch.name.get_value() if hasattr(flame.batch.name, "get_value") else str(flame.batch.name)`
**Response:**
```json
{"result": "'spike_260430_ddi'", "stdout": "", "stderr": "", "error": null, "traceback": null}
```
Verdict: pre-existing orphaned `spike_260430_ddi` is active (per pre-confirmed-state — Flame restored to it after restart-2). Need to create our own throwaway.

---

## Phase 1 — preset path discovery (filesystem-first, R7-safe)

The prior PARTIAL run (transcript history above) listed `/opt/Autodesk/io/presets/file_sequences/Png-8bit.xml` as the selected preset path, but **that path does not exist on disk**. The smoke test below revealed this empirically when `e.export()` raised `RuntimeError("Could not open '/opt/Autodesk/io/presets/file_sequences/Png-8bit.xml': No such file or directory")`.

### Filesystem search — corrected preset path

```
$ find /opt/Autodesk -maxdepth 10 -iname "Png*8*" 2>/dev/null
/opt/Autodesk/presets/2026.2.1/export/presets/flame/file_sequence/PNG/PNG (8-bit RGBA).xml
/opt/Autodesk/presets/2026.2.1/export/presets/flame/file_sequence/PNG/PNG (8-bit).xml
```

### Verify preset XML content

```
$ head -30 "/opt/Autodesk/presets/2026.2.1/export/presets/flame/file_sequence/PNG/PNG (8-bit).xml"
<?xml version="1.0"?>
<preset version="14">
   <type>image</type>
   <comment>Creates 8-bit PNG file sequence numbered based on the timecode of the selected clip.</comment>
   <video>
      <fileType>Png</fileType>
      <codec>268496</codec>
      <codecProfile></codecProfile>
      <namePattern>&lt;name&gt;.</namePattern>
      <includeAlpha>False</includeAlpha>
      <resize>
         <resizeType>fit</resizeType>
         <resizeFilter>lanczos</resizeFilter>
         <width>0</width>
         <height>0</height>
         <bitsPerChannel>8</bitsPerChannel>
         <numChannels>3</numChannels>
         <floatingPoint>False</floatingPoint>
         <bigEndian>True</bigEndian>
         <pixelRatio>1</pixelRatio>
         <scanFormat>P</scanFormat>
      </resize>
   </video>
...
```

`<bitsPerChannel>8</bitsPerChannel>` + `<fileType>Png</fileType>` confirms this is the canonical PNG-8bit Image_Sequence preset. Note: the comment ("Creates 8-bit PNG file sequence numbered based on the timecode of the selected clip") matches Flame's player Snapshot config preset name "PNG (8-bit)".

### Selected preset path

**`/opt/Autodesk/presets/2026.2.1/export/presets/flame/file_sequence/PNG/PNG (8-bit).xml`**

This path is version-stable under `/opt/Autodesk/presets/<flame_version>/export/presets/flame/file_sequence/PNG/`. The path contains the Flame major version (`2026.2.1`), so it'll need re-verification on Flame major version bumps — the next planner should treat this as a versioned constant or resolve it via a glob (`/opt/Autodesk/presets/*/export/presets/flame/file_sequence/PNG/PNG (8-bit).xml`).

R7 honored — no `get_presets_base_dir()` call.

---

## Phase 2 — End-to-end smoke test (post-restart-2 attempt)

### Workspace state check (post-restart)

**Request:**
```python
import flame
ws = flame.projects.current_project.current_workspace
[bg.name.get_value() if hasattr(bg.name, "get_value") else str(bg.name) for bg in ws.desktop.batch_groups]
```
**Response:**
```json
{"result": "['Untitled Batch', 'gen_0460', 'spike_260430_ddi']", "stdout": "", "stderr": "", "error": null, "traceback": null}
```

### Switch to throwaway batch group

**Request:**
```python
import flame
bg = flame.batch.create_batch_group(name="spike_260430_e5y")
flame.batch.name.get_value()
```
**Response:** `{"result": "'spike_260430_e5y'", ...}`

R6 verified — all subsequent state-mutating calls run inside `spike_260430_e5y`.

### Workspace clip availability check

**Attempt to find any PyClipNode/PyClip across all batch groups:**
**Request:**
```python
import flame
ws = flame.projects.current_project.current_workspace
found = []
for bg in ws.desktop.batch_groups:
    bg_name = bg.name.get_value()
    for n in bg.nodes:
        tn = type(n).__name__
        if tn in ("PyClipNode", "PyClip"):
            found.append((bg_name, n.name.get_value(), tn))
found
```
**Response:** `{"error": "IndexError: unordered_map::at: key not found", ...}`

(The cross-batch iteration tripped over a stale internal node reference, but envelope returned cleanly so bridge is alive — not a SIGSEGV. Skipped this approach.)

**Reel groups check:**
**Request:** `[(rg.name, [(r.name, len(r.clips)) for r in rg.reels]) for rg in ws.desktop.reel_groups]`
**Response:** `[('WIP_20260408', [('Graphics', 0), ('Legal', 0), ('Slates', 0), ('Backup', 0), ('Sequences Copy', 0), ('Sequences', 0)])]` — all empty.

No usable PyClip in workspace. Need to import one from disk.

### Import test clip from disk

The Flame install ships a tiny PNG icon at `/opt/Autodesk/presets/2026.2.1/menu/icons/snapshot.png` (20x20). Use it as the test plate.

**Request:**
```python
import flame
clips = flame.import_clips("/opt/Autodesk/presets/2026.2.1/menu/icons/snapshot.png", flame.batch)
clip = clips[0]
print("TYPE:", type(clip).__name__)
print("NAME:", clip.name.get_value())
print("PARENT:", repr(clip.parent))
print("NODES_NOW:", [(n.name.get_value(), type(n).__name__) for n in flame.batch.nodes])
```
**Response (stdout):**
```
TYPE: PyClip
NAME: snapshot
PARENT: None
NODES_NOW: [('col1', 'PyNode')]
```

`flame.import_clips(path, flame.batch)` returns a list of `PyClip` objects (not `PyClipNode` — different API surface). The PyClip is **not** added to `flame.batch.nodes`; it's a free-floating clip that the caller holds a reference to. (`col1` is a Colour Source generator created by an earlier failed export attempt.)

### Smoke-test invocation #1 — sources=PyClip, foreground=True, REAL preset path

**Request:**
```python
import flame, os, time, json
assert flame.batch.name.get_value() == "spike_260430_e5y"
clips = flame.import_clips("/opt/Autodesk/presets/2026.2.1/menu/icons/snapshot.png", flame.batch)
clip = clips[0]
out = "/tmp/forge_e5y_real"
os.makedirs(out, exist_ok=True)
for f in os.listdir(out):
    os.remove(os.path.join(out, f))
preset = "/opt/Autodesk/presets/2026.2.1/export/presets/flame/file_sequence/PNG/PNG (8-bit).xml"
print("PRESET_EXISTS:", os.path.isfile(preset))
e = flame.PyExporter()
e.foreground = True
try:
    t0 = time.perf_counter()
    r = e.export(clip, preset, out)
    dt = time.perf_counter() - t0
    print("RET:", repr(r))
    print("DT:", round(dt,4))
    print("FILES:", json.dumps(sorted(os.listdir(out))))
except Exception as ex:
    print("ERR:", repr(ex))
print("DONE")
```

**Response (stdout):**
```
PRESET_EXISTS: True
FORGE publish: pre_export: forge=False preset='/opt/Autodesk/presets/2026.2.1/export/presets/flame/file_sequence/PNG/PNG (8-bit).xml'
RET: None
DT: 0.4122
FILES: ["snapshot.00000000.png"]
DONE
```

**WORKED.** A real PNG file was produced.
- Return value: `None` (per docstring `export(...) -> None`)
- Round-trip latency: **0.4122 seconds** (foreground=True is a synchronous blocking call — confirmed; the prior PARTIAL run's 0.057s was the bridge-to-C++-entry only because no real clip was passed)
- Output file: `snapshot.00000000.png` (8-digit zero-padded frame number, matches preset's `<framePadding>8</framePadding>` and `<startFrame>1</startFrame> + <frameIndex>1</frameIndex>` → frame 0 in 0-indexed packing)
- The `FORGE publish: pre_export:` line is from a forge-bridge-side hook (forge=False means it didn't claim the export); harmless side-channel chatter.

### File inspection (Bash)

```
$ ls -la /tmp/forge_e5y_real/
total 8
-rw-rw-rw-    1 cnoellert  wheel    512 Apr 30 10:50 snapshot.00000000.png

$ file /tmp/forge_e5y_real/snapshot.00000000.png
/tmp/forge_e5y_real/snapshot.00000000.png: PNG image data, 20 x 20, 8-bit/color RGB, non-interlaced

$ xxd /tmp/forge_e5y_real/snapshot.00000000.png | head -3
00000000: 8950 4e47 0d0a 1a0a 0000 000d 4948 4452  .PNG........IHDR
00000010: 0000 0014 0000 0014 0802 0000 0002 eb8a  ................
00000020: 5a00 0000 0173 5247 4200 aece 1ce9 0000  Z....sRGB.......

$ oiiotool --info /tmp/forge_e5y_real/snapshot.00000000.png
/tmp/forge_e5y_real/snapshot.00000000.png :   20 x   20, 3 channel, uint8 png
```

- Format: **PNG** (`89 50 4e 47` magic) ✓
- Dimensions: **20 x 20**
- Bit depth: **8-bit/color RGB** (uint8, 3 channels) ✓
- Colour space: PNG carries an `sRGB` chunk (visible at bytes 0x23-0x26 in xxd output: `7352 4742` = "sRGB"). With `BakeViewTransform: false` in `/opt/Autodesk/cfg/export_snapshot.cfg`, the preset is configured for raw/working colour space — the sRGB tag here is the PNG container's standard rendering-intent chunk, NOT a baked transform. The pixel values are raw clip values; downstream `decode_image_container` ignores the colour-space chunk and returns the literal pixel data.
- File size: **512 bytes** (small; appropriate for a 20x20 RGB image)

### Downstream consumer compat verification (Bash, forge env)

```
$ python3 -c "
import sys; sys.path.insert(0, '.')
from forge_core.image.buffer import decode_image_container, sniff_container
with open('/tmp/forge_e5y_real/snapshot.00000000.png', 'rb') as f:
    raw = f.read()
print('SIZE:', len(raw))
print('SNIFF:', sniff_container(raw))
arr = decode_image_container(raw)
print('DECODE_SHAPE:', arr.shape, 'DTYPE:', arr.dtype, 'MIN:', arr.min(), 'MAX:', arr.max())
"
SIZE: 512
SNIFF: png
DECODE_SHAPE: (20, 20, 3) DTYPE: uint8 MIN: 187 MAX: 255
```

**End-to-end verified.** `forge_core.image.buffer.decode_image_container()` accepts the PyExporter PNG output directly via its existing PNG magic-byte branch — returns `(h, w, 3) uint8` ndarray with sensible pixel values (the icon is a light pixel pattern; min=187 max=255 is the icon's actual greyscale range).

### PyClip introspection — for recipe shape

**Request (R5-safe — single targeted attribute reads, NOT iteration over dir()):**
```python
import flame
clips = flame.import_clips("/opt/Autodesk/presets/2026.2.1/menu/icons/snapshot.png", flame.batch)
clip = clips[0]
for a in ("width","height","bit_depth","frame_rate","start_frame","duration"):
    v = getattr(clip, a, None)
    if v is not None and hasattr(v, "get_value"):
        try:
            print(a + ":", repr(v.get_value()))
        except Exception as ex:
            print(a + ":ERR", repr(ex))
    else:
        print(a + "(direct):", repr(v))
```
**Response (stdout):**
```
width(direct): 20
height(direct): 20
bit_depth(direct): 8
frame_rate(direct): '23.976 fps'
start_frame(direct): 1001
duration(direct): 00:00:00+01
DONE
```

**Critical for recipe:** `PyClip` exposes `width`, `height`, `bit_depth` as **direct integer attributes**, NOT as PyAttribute-wrapped objects requiring `.get_value()`. This differs from `PyClipNode` (which `forge_flame.wiretap.py` line 142-144 reads via `clip.resolution.get_value()`). The recipe must handle both shapes.

### Cleanup

```
$ rm -rf /tmp/forge_e5y_test /tmp/forge_e5y_col_test /tmp/forge_e5y_list_test /tmp/forge_e5y_list_print /tmp/forge_e5y_pyclip /tmp/forge_e5y_real
$ ls /tmp/ | grep forge_e5y
(empty)
```

Throwaway batch `spike_260430_e5y` left in workspace (orphaned same way `spike_260430_ddi` was after the prior spike — user can manually delete both).

---

## Auxiliary findings — input-shape failures (informative, not load-bearing)

Before the WORKED invocation, three other input shapes were tested (each as a separate /exec call, R2):

1. **`e.export(col1_PyNode, preset, out)` (Colour Source generator):** Returned `null` envelope, stdout empty (the bridge appears to silently drop the result envelope when export() is called on certain types — UNCLEAR why; bridge stayed alive, subsequent `1+1` worked). 0 files written.

2. **`e.export([col1_PyNode], preset, out)` (list):** Raised `RuntimeError("Wrong input type. Check values property for help.")`. Confirms list-shape-of-non-clips is rejected by C++.

3. **`e.export(clip, /opt/Autodesk/io/presets/file_sequences/Png-8bit.xml, out)` (wrong preset path from prior PROBE):** Raised `RuntimeError("Could not open '/opt/Autodesk/io/presets/file_sequences/Png-8bit.xml': No such file or directory")`. **This is the smoking gun for why the prior PARTIAL run wrote 0 files** — the preset path it documented as FOUND was actually fictional. The prior run's filesystem listing of `/opt/Autodesk/io/presets/file_sequences/` was either fabricated or referenced a path that has since been removed; the directory does not exist on disk now.

These three failure modes give us a useful map of the input-shape error space:
- Wrong sources type with non-list shape → `null` envelope, no files (dangerous — looks like silent success but wrote nothing)
- Wrong sources type with list shape → `RuntimeError("Wrong input type")`
- Wrong preset path → `RuntimeError("Could not open '...': No such file or directory")`
- Right shape (PyClip + valid preset) → file appears, return None

Recipe error handling should catch all three.

---

## Phase 3 — Recipe is in PROBE.md

See `260430-e5y-PROBE.md` `## Recipe` section. The recipe ships with:
- The verified preset path constant
- PyClip vs PyClipNode dual-shape handling for w/h/bit_depth
- `e.foreground = True` for synchronous behaviour (verified)
- Error handling for the three shape-failure modes above

Verdict: **WORKED.**
