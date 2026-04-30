# 260430-hn7 Bridge Transcript — Frame-Parking Probe

Bridge contract: `POST /exec` to `http://127.0.0.1:9999/exec` returns
`{result, stdout, stderr, error, traceback}`. `result` is the `repr()` of the
last expression in the code body (REPL contract — see
`memory/flame_bridge_repl_contract.md`).

---

## Pre-flight (orchestrator-verified)

**Verified by orchestrator at 2026-04-30T19:45:00Z** — bridge alive, Flame on
`gen_0460` (148 nodes), user green-lit READ-ONLY probing against
`gen_0460_graded` / `graded_02` clips (R8).

Started: **2026-04-30T19:45:30Z**

---

## Phase 1.1 — Locate test clip

**Request 1:**
```python
import flame
[(n.name.get_value(), type(n).__name__) for n in flame.batch.nodes if n.name.get_value() in ('gen_0460_graded', 'graded_02')]
```

**Response:**
```json
{"result": "[]", "stdout": "", "stderr": "", "error": null, "traceback": null}
```

Neither exact name present. Falling back per plan §1.1 to "any PyClipNode with
duration > 1, document substitution".

**Request 2:**
```python
import flame
[(n.name.get_value(), type(n).__name__) for n in flame.batch.nodes if type(n).__name__ == "PyClipNode"][:30]
```

**Response (trimmed):**
```
[('gen_0460_graded_L01', 'PyClipNode'),
 ('gen_0460_graded_L02', 'PyClipNode'),
 ('gen_0180_graded_L01', 'PyClipNode'),
 ...
```

**Selected:** `gen_0460_graded_L01` — first PyClipNode in the batch and a
near-perfect match for the requested `gen_0460_graded` semantics (it's the L01
layer of the same shot). Substitution documented.

---

## Phase 1.2 — Introspect frame attributes

**Request 3:**
```python
import flame
clip = next(n for n in flame.batch.nodes if n.name.get_value() == "gen_0460_graded_L01")
[a for a in dir(clip) if any(k in a.lower() for k in ('frame','time','dur'))]
```

**Response:**
```json
{"result": "[]", "stdout": "", "stderr": "", "error": null, "traceback": null}
```

PyClipNode (the schematic node) has NO frame-related attributes.

**Request 4:**
```python
import flame
clip = next(n for n in flame.batch.nodes if n.name.get_value() == "gen_0460_graded_L01")
[a for a in dir(clip) if not a.startswith("_")]
```

**Response:**
```json
{"result": "['attributes', 'cache_range', 'clear_schematic_colour', 'clip', 'delete', 'duplicate', 'input_sockets', 'load_node_setup', 'output_sockets', 'parent', 'save_node_setup', 'set_context', 'set_version_uid', 'sockets', 'version_uid', 'version_uids']"}
```

**Key:** `clip.clip` reaches the underlying `PyClip`. PyClipNode exposes
**no player navigation** — just the schematic-graph wrapper.

**Request 5:**
```python
import flame
cn = next(n for n in flame.batch.nodes if n.name.get_value() == "gen_0460_graded_L01")
pc = cn.clip
(type(pc).__name__, [a for a in dir(pc) if any(k in a.lower() for k in ('frame','time','dur','start','end'))])
```

**Response:**
```json
{"result": "('PyClip', ['change_start_frame', 'duration', 'flush_renders', 'frame_rate', 'is_rendered', 'render', 'start_frame'])"}
```

PyClip exposes `start_frame`, `duration`, `frame_rate`, `change_start_frame` —
NO `current_time`, NO `go_to_frame`, NO setter. Frame-range data only.

---

## Phase 1.3 — Read frame range + dimensions

**Request 6:**
```python
import flame
cn = next(n for n in flame.batch.nodes if n.name.get_value() == "gen_0460_graded_L01")
pc = cn.clip
{"duration": pc.duration, "start_frame": pc.start_frame, "frame_rate": pc.frame_rate, "name": pc.name.get_value() if hasattr(pc.name, 'get_value') else str(pc.name), "width": getattr(pc, "width", None), "height": getattr(pc, "height", None), "bit_depth": getattr(pc, "bit_depth", None)}
```

**Response:**
```json
{"result": "{'duration': 00:00:02+01, 'start_frame': 991, 'frame_rate': '23.976 fps', 'name': 'gen_0460_graded_L01', 'width': 4448, 'height': 3096, 'bit_depth': 16}"}
```

Multi-frame clip confirmed:
- start_frame: **991**
- duration: **00:00:02+01** (= 49 frames at 23.976 fps)
- resolution: **4448x3096, 16-bit**

---

## Phase 2 — Search for parking API

**Request 7 — full PyClip dir():**
```python
[a for a in dir(pc) if not a.startswith("_")]
```

**Response:**
```
['archive_date', 'archive_error', 'attributes', 'audio_tracks', 'bit_depth',
 'cache_media', 'cached', 'change_dominance', 'change_start_frame',
 'clear_colour', 'close_container', 'colour_primaries', 'commit',
 'create_marker', 'creation_date', 'cut', 'duration', 'essence_uid',
 'flush_cache_media', 'flush_renders', 'frame_rate', 'get_colour_space',
 'get_wiretap_node_id', 'get_wiretap_storage_id', 'has_deliverables',
 'has_history', 'height', 'is_rendered', 'markers', 'matrix_coefficients',
 'open_as_sequence', 'open_container', 'original_source_uid', 'parent',
 'proxy_resolution', 'ratio', 'reformat', 'render', 'sample_rate', 'save',
 'scan_mode', 'source_uid', 'start_frame', 'subtitles',
 'transfer_characteristics', 'unlinked', 'versions', 'width']
```

**Verdict:** PyClip has NO `current_time`, NO `go_to_frame`, NO
`set_current_time`, NO equivalent. The "transient navigation" attribute
hypothesized in 260430-e5y's `TODO(next-spike)` does not exist on PyClip.

**Request 8 — flame.batch player attrs:**
```python
[a for a in dir(flame.batch) if any(k in a.lower() for k in ('frame','time','current','player'))]
```

**Response:**
```json
{"result": "['current_iteration', 'current_iteration_number', 'frame_all', 'frame_selected', 'save_current_iteration']"}
```

(`current_iteration` is iteration history — N/A. `frame_all`/`frame_selected`
are viewport zoom — N/A.)

`flame.batch` has no player-frame control either.

**Request 9 — PyExporter attrs:**
```python
e = flame.PyExporter()
[a for a in dir(e) if not a.startswith("_")]
```

**Response:**
```
['Audio', 'Autodesk', 'BackgroundJobSettings', 'Distribution_Package',
 'Flow_Production_Tracking', 'Image_Sequence', 'Movie', 'PresetType',
 'PresetVisibility', 'Project', 'Sequence_Publish', 'Shared', 'Shotgun',
 'User', 'export', 'export_all_subtitles', 'export_between_marks',
 'export_subtitles_as_files', 'foreground', 'get_presets_base_dir',
 'get_presets_dir', 'include_subtitles', 'keep_timeline_fx_renders',
 'use_top_video_track', 'warn_on_mixed_colour_space', 'warn_on_no_media',
 'warn_on_pending_render', 'warn_on_reimport_unsupported', 'warn_on_unlinked',
 'warn_on_unrendered']
```

**Key knob:** `export_between_marks` — Boolean. Pairs with **mark in/out
set on the clip's segment** (see Request 12).

**Request 10 — help() on PyExporter.export():**
```python
help(e.export)
```

**Response (stdout):**
```
export(self, sources, preset_path, output_directory [, background_job_settings=None [, hooks=None [, hooks_user_data=None]]]) -> None
```

`export()` itself has **no frame parameter**. Range is implicit (clip
duration) unless `export_between_marks=True` and marks are set.

**Request 11 — search PyClip for marks/ranges:**
```python
[a for a in dir(pc) if any(k in a.lower() for k in ('mark','cut','in','out','sub','clone','copy','range'))]
```

**Response:**
```json
{"result": "['__init__', '__init_subclass__', '__subclasshook__', 'change_dominance', 'close_container', 'create_marker', 'cut', 'markers', 'open_container', 'original_source_uid', 'subtitles', 'unlinked']"}
```

`cut` is a destructive split. `markers` are on-clip notes (not range
limiters). No transient-clone API at the PyClip level.

**Request 12 — PyClip.versions[0] dir:**
```python
v = pc.versions
(len(v), [a for a in dir(v[0]) if not a.startswith("_")] if v else None)
```

**Response:**
```json
{"result": "(1, ['attributes', 'copy_to_media_panel', 'create_track', 'import_DolbyVision_xml', 'parent', 'stereo', 'tracks'])"}
```

**Request 13 — tracks[0] dir:**
```python
tracks = pc.versions[0].tracks
(len(tracks), [a for a in dir(tracks[0]) if not a.startswith("_")] if tracks else None)
```

**Response:**
```json
{"result": "(1, ['attributes', 'copy_to_media_panel', 'cut', 'insert_transition', 'parent', 'segments', 'transitions'])"}
```

**Request 14 — segment dir for marks:**
```python
seg = pc.versions[0].tracks[0].segments[0]
(type(seg).__name__, [a for a in dir(seg) if any(k in a.lower() for k in ('mark','in','out','start','end','frame','time','head','tail','src','rec'))])
```

**Response:**
```json
{"result": "('PySegment', ['__init__', '__init_subclass__', 'change_start_frame', 'container_clip', 'create_marker', 'create_unlinked_segment', 'head', 'markers', 'original_source_uid', 'record_duration', 'record_in', 'record_out', 'slide_keyframes', 'source_frame_rate', 'source_in', 'source_out', 'source_unlinked', 'start_frame', 'tail', 'trim_head', 'trim_tail'])"}
```

**THIS is the parking surface.** The clip's `versions[0].tracks[0].segments[0]`
exposes `record_in`, `record_out`, `source_in`, `source_out`, `head`, `tail`,
`trim_head`, `trim_tail`. Mark-in/mark-out for a single-frame export would
mean setting `record_in == record_out` (or `source_in == source_out`) and
flipping `e.export_between_marks = True`.

**HOWEVER** — these are persistent edit-data attributes on the segment, not
the transient navigation state R8 green-lit. Setting them mutates the clip's
edit data. The "set + export + restore" pattern is feasible IF restoration is
guaranteed, but if the export crashes or the bridge dies between set and
restore, the clip is left mutated. Per R8's spirit (no persistent state
changes on gen_0460), this needs a different approach.

**Better pattern (untested this spike):** export the full multi-frame clip
once, then have the recipe pick the correct file from the output directory by
frame index. See Phase 3 below — the underlying export is per-frame faithful,
which is the foundation for that approach.

---

## Phase 3 — Two-frame comparison (PARTIAL — alternate approach)

Since direct parking has no API on PyClip, we changed Phase 3 to
characterize the full-clip export shape — does it produce per-frame files?

**Request 15 — full clip export to /tmp/forge_park_full/:**
```python
import flame, os, time
out = "/tmp/forge_park_full/"
os.makedirs(out, exist_ok=True)
for f in os.listdir(out):
    p=os.path.join(out,f)
    if os.path.isfile(p): os.remove(p)
cn = next(n for n in flame.batch.nodes if n.name.get_value() == "gen_0460_graded_L01")
pc = cn.clip
e = flame.PyExporter()
e.foreground = True
PRESET = "/opt/Autodesk/presets/2026.2.1/export/presets/flame/file_sequence/PNG/PNG (8-bit).xml"
t0 = time.perf_counter()
e.export(pc, PRESET, out)
dt = time.perf_counter() - t0
files = sorted(os.listdir(out))
(round(dt,3), len(files), files[:3], files[-3:] if len(files)>3 else None)
```

**Response:**
```json
{"result": "(17.495, 49, ['gen_0460_graded_L01.00786578.png', 'gen_0460_graded_L01.00786579.png', 'gen_0460_graded_L01.00786580.png'], ['gen_0460_graded_L01.00786624.png', 'gen_0460_graded_L01.00786625.png', 'gen_0460_graded_L01.00786626.png'])",
 "stdout": "FORGE publish: pre_export: forge=False preset='/opt/Autodesk/presets/2026.2.1/export/presets/flame/file_sequence/PNG/PNG (8-bit).xml'\n",
 "stderr": "", "error": null, "traceback": null}
```

**Findings:**
- 49 files produced, matching `duration = 02:01 ≈ 49 frames at 23.976 fps`
- Latency: **17.495s for 49 frames at 4448x3096** → ~0.357s/frame amortized
- Filename pattern: `<clip_name>.<TIMECODE_FRAME>.png` where `TIMECODE_FRAME`
  is the source TC-derived frame number (`00786578..00786626`),
  NOT `start_frame=991..1039`. The TC starts at `00786578` (= 09:06:51:18 at
  23.976) — a record-side reference frame.
- File order is monotonic ascending by TC frame number.

**Request 16 — verify per-frame distinctness (bash, not bridge):**
```bash
shasum -a 256 /tmp/forge_park_full/gen_0460_graded_L01.{00786578,00786600,00786626}.png
ls -la /tmp/forge_park_full/gen_0460_graded_L01.{00786578,00786600,00786626}.png
```

**Output:**
```
9bcee6aeb47a5b39b035b22a6af55f99e30645e8876d38f5f3883fe9d4b7b25d  ...00786578.png  (15554560 bytes)
c0fc60479680a38c6944ab12dcaea4d7fef7c8165ca63253b27541cff7693e82  ...00786600.png  (15553024 bytes)
b2f1be62d83b0375e879e29a9eb6b11dea615983d6afb8187e5878b820da3f23  ...00786626.png  (15528448 bytes)
```

**3 distinct hashes, 3 different file sizes** — the export is per-frame
faithful. This satisfies the spirit of "frame-A != frame-B at the byte
level" — albeit derived from a single full export, not two parked exports.

---

## Phase 4 — Crash event

**Request 17 (FAILED — bridge died):**
```python
import flame
cn = next(n for n in flame.batch.nodes if n.name.get_value() == "gen_0460_graded_L01")
pc = cn.clip
seg = pc.versions[0].tracks[0].segments[0]
{"record_in": str(seg.record_in), "record_out": str(seg.record_out), "source_in": str(seg.source_in), "source_out": str(seg.source_out), "head": seg.head, "tail": seg.tail, "start_frame": seg.start_frame}
```

**Response:**
```
curl: (7) Failed to connect to 127.0.0.1 port 9999 after 0 ms: Couldn't connect to server
```

**Two retry probes after 3s and 5s waits — both failed identically.**
Bridge is hard-down. Per R5 SIGSEGV stop-rule: STOP, save partial findings,
mark BLOCKED, exit. No further retries.

**Likely cause:** segment introspection on a high-resolution
(`4448x3096, 16-bit, 49-frame`) production clip's `record_in`/`source_in`
PyTime conversion may be the SIGSEGV trigger. Today's session has now had
**3 prior Flame crashes** (per orchestrator pre-flight: 2 prior; this is +1).
Pattern: bridge calls that touch segment-time data on production clips can
crash Flame — consistent with `memory/flame_bridge_qt_main_thread.md` and
`memory/flame_sigsegv_cascade_lesson.md`.

Aborted: **2026-04-30T19:55:30Z**
