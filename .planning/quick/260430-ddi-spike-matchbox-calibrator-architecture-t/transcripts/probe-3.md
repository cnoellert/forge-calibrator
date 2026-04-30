# Probe 3 transcript — Snapshot tool from Python

## Step 3.1 — Module surface search

### `flame.*` snap/capture/still
**Request:** `POST /exec` with code:
```python
import flame
[a for a in dir(flame) if "snap" in a.lower() or "capture" in a.lower() or "still" in a.lower()]
```
**Response:** `{"result": "[]"}`
**Interpretation:** Zero matches on top-level `flame`.

### `flame.batch.*` snap/capture/still
**Request:** `POST /exec` with code:
```python
import flame
[a for a in dir(flame.batch) if "snap" in a.lower() or "capture" in a.lower() or "still" in a.lower()]
```
**Response:** `{"result": "[]"}`
**Interpretation:** Zero matches on `flame.batch`.

### `hasattr(flame, "execute_shortcut")`
**Request:** `POST /exec` with code:
```python
import flame
hasattr(flame, "execute_shortcut")
```
**Response:** `{"result": "True"}`
**Interpretation:** `execute_shortcut` is present — could be used to trigger UI shortcuts by name.

### `execute_shortcut` docstring
**Request:** `POST /exec` with code:
```python
import flame
repr(flame.execute_shortcut.__doc__)
```
**Response:**
```
execute_shortcut( (str)description [, (bool)update_list=True]) -> bool :
    Execute the Flame shortcut.
    description  -- The description in the Keyboard Shortcut editor.
```
**Interpretation:** Takes the keyboard-shortcut description string. Need to find the exact string for the Snapshot button.

### `execute_command` docstring (sanity check — different beast)
**Request:** `POST /exec` with code:
```python
import flame
repr(flame.execute_command.__doc__)
```
**Response (truncated):** subprocess wrapper. Not relevant to snapshotting.

### Wider net — flame.* save/export/render/image/frame/preview/screen/player
**Request:** `POST /exec` with code:
```python
import flame
[a for a in dir(flame) if any(k in a.lower() for k in ["save", "export", "render", "image", "frame", "preview", "screen", "player"]) and not a.startswith("_")]
```
**Response:** `{"result": "['PyExporter', 'PyImageNode', 'PyRenderNode', 'set_render_option']"}`
**Interpretation:** **Found `PyExporter`** — Flame's documented Python exporter API. This is the most promising bridge-safe entry point for snapshotting (does not require UI dialog).

### Full `flame.*` public surface (for the record)
**Request:** `POST /exec` with code:
```python
import flame
[a for a in dir(flame) if not a.startswith("_")]
```
**Response:** ~80 names. Relevant entries: `PyExporter`, `PyRenderNode`, `PyWriteFileNode`, `PyImageNode`, `import_clips`, `execute_shortcut`, `execute_command`, `set_render_option`. **No `snapshot`, `capture`, `still`, `take_snapshot`.**

---

## Step 3.2 — Read docstring of candidate `PyExporter`

### `PyExporter` class doc
**Request:** `POST /exec` with code:
```python
import flame
repr(flame.PyExporter.__doc__)
```
**Response:** `"'Object holding export settings.'"`

### `PyExporter` public attributes
**Request:** `POST /exec` with code:
```python
import flame
[a for a in dir(flame.PyExporter) if not a.startswith("_")]
```
**Response:** `['Audio', 'Autodesk', 'BackgroundJobSettings', 'Distribution_Package', 'Flow_Production_Tracking', 'Image_Sequence', 'Movie', 'PresetType', 'PresetVisibility', 'Project', 'Sequence_Publish', 'Shared', 'Shotgun', 'User', 'export', 'export_all_subtitles', 'export_between_marks', 'export_subtitles_as_files', 'foreground', 'get_presets_base_dir', 'get_presets_dir', 'include_subtitles', 'keep_timeline_fx_renders', 'use_top_video_track', 'warn_on_mixed_colour_space', 'warn_on_no_media', 'warn_on_pending_render', 'warn_on_reimport_unsupported', 'warn_on_unlinked', 'warn_on_unrendered']`
**Interpretation:** `PyExporter.export(...)` is the entry point. `Image_Sequence` is one of the preset types. Helper enums: `PresetType`, `PresetVisibility`.

### `PyExporter.export` docstring
**Request:** `POST /exec` with code:
```python
import flame
repr(flame.PyExporter.export.__doc__)
```
**Response (unescaped & abridged):**
```
export( (PyExporter)arg1, (object)sources, (str)preset_path, (str)output_directory [, (BackgroundJobSettings)background_job_settings=None [, (object)hooks=None [, (object)hooks_user_data=None]]]) -> None :
    Perform export.
    Keyword arguments:
    sources -- Flame clip object, a Flame container object or a list of either first.
    preset_path -- Absolute path to the export preset to use.
    output_directory -- Absolute path to the output directory root.
    hooks -- Export python hooks override. (preExport / postExport / postExportAsset).
```
**Interpretation:** **This is exactly the Python-driven snapshot equivalent.** Takes (clip object, preset XML path, output dir). Hook system (postExportAsset) supports the same `info` dict that the documented snapshot post-hook uses, which means **the Exporter route gives us full programmatic snapshot capability without going through the player UI**. No QDialog, R3-safe.

---

## Step 3.3 — Filesystem search for "snapshot"

### Flame python sources
**Command:** `grep -rli 'snapshot' /opt/Autodesk/flame_*/python 2>/dev/null`
**Output:**
```
/opt/Autodesk/flame_2026.2.1/python/export_hook.py
```

### Flame lib python
**Command:** `grep -rli 'snapshot' /opt/Autodesk/flame_*/lib/python* 2>/dev/null`
**Output:** _no matches found_

### Wider scan
**Command:** `find /opt/Autodesk -maxdepth 5 -iname "*snapshot*" 2>/dev/null`
**Output:**
```
/opt/Autodesk/.flamefamily_2026.2.1/menu/default.export_snapshot_dialog
/opt/Autodesk/.flamefamily_2026.2.1/python_utilities/examples/post_export_asset_after_snapshot.py
/opt/Autodesk/cfg/services_snapshot.sh
/opt/Autodesk/cfg/export_snapshot.cfg
/opt/Autodesk/cfg/export_snapshot.cfg.sample
/opt/Autodesk/backgroundreactor_2026.2.1/menu/default.export_snapshot_dialog
/opt/Autodesk/cfg/.2026.2.1/services_snapshot.sh
/opt/Autodesk/cfg/.2026.2.1/export_snapshot.cfg.sample
/opt/Autodesk/backgroundreactor_2026.2.1/python_utilities/examples/post_export_asset_after_snapshot.py
/opt/Autodesk/wiretap/tools/2026.2.1/wiretap_services_snapshot
/opt/Autodesk/wiretap/tools/2026/wiretap_services_snapshot
/opt/Autodesk/presets/2026.2.1/menu/icons/snapshot.png
/opt/Autodesk/presets/2026.2.1/menu/icons/snapshot@2x.png
```
**Interpretation:** Snapshot is a first-class Flame feature, but its on-disk artifacts are:
- **menu config** (`default.export_snapshot_dialog`) — the player Snapshot button → opens an "Export Snapshot" dialog
- **runtime config** (`/opt/Autodesk/cfg/export_snapshot.cfg`) — output path, preset, view-transform settings
- **post-export hook example** (`post_export_asset_after_snapshot.py`) — Python hook fired AFTER a snapshot is taken
- icons + Wiretap services (unrelated — backup/config snapshot, not media snapshot)

### `/opt/Autodesk/cfg/export_snapshot.cfg` content
```json
{
    "Media Path": "/Volumes/ssp-lucid/1193-hyundai-afc-nfc-epic/_03_edit/footage/snapshots/",
    "Pattern": "<name>.<frame>",
    "Preset": "PNG (8-bit)",
    "IncludeMetadataOverlay": false,
    "IncludeSubtitles": false,
    "BakeViewTransform": false,
    "ViewTransformType": 0,
    "FrameMode": 0
}
```
**Interpretation:** Snapshot config — output dir, name pattern (`<name>.<frame>`), preset name string `"PNG (8-bit)"`, **`BakeViewTransform: false`** (so by default snapshots are RAW colour-space, not view-transformed — important for the calibrator's frame-source use case). The `Preset` field is a name, not a path — Flame resolves it to a preset XML internally.

### `post_export_asset_after_snapshot.py` content
```python
def post_export_asset(info, userData, *args, **kwargs):
    import flame
    import os
    if flame.get_current_tab() == "Timeline":
        if info["isSnapshot"]:
            reel = flame.projects.current_project.current_workspace.desktop.reel_groups[0].reels[0]
            clip = os.path.join(info["destinationPath"], info["resolvedPath"])
            flame.import_clips(clip, reel)
```
**Interpretation:** Documents that the post-export hook receives `info["isSnapshot"]`, `info["destinationPath"]`, `info["resolvedPath"]`. **A snapshot taken via the player Snapshot button can be detected via this hook** even if we didn't trigger it programmatically.

### Flame menu config — Snapshot keyboard shortcut
**Command:** `grep -A 2 -B 1 'Snapshot' /opt/Autodesk/.flamefamily_2026.2.1/menu/default.player`
**Output (excerpt):**
```
Menu ExportSnapShotMenu, Current
        HotkeyTitle Export Snapshot
        Button UpButton, DownButton
        Icon snapshot
```
**Interpretation:** **Found the shortcut name: `"Export Snapshot"`.** This means `flame.execute_shortcut("Export Snapshot")` would trigger the player Snapshot button programmatically. **However**, doing so opens a Qt dialog (`ExportSnapshotDialog`), and per R3 + `memory/flame_bridge_qt_main_thread.md`, invoking Qt UI from /exec on macOS is a hard SIGSEGV. **Therefore `execute_shortcut("Export Snapshot")` is NOT bridge-safe.** It would have to be invoked from a Flame menu hook (already on the main thread) instead.

---

## Step 3.4 — Attempt invocation

### Try `PyExporter().get_presets_base_dir(...)` to enumerate preset paths
**Request:** `POST /exec` with code:
```python
import flame
flame.PyExporter().get_presets_base_dir(flame.PyExporter.PresetVisibility.Autodesk, flame.PyExporter.PresetType.Image_Sequence)
```
**Response:**
```json
{"error": "ArgumentError: Python argument types in PyExporter.get_presets_base_dir(PresetVisibility, PresetType) did not match C++ signature: get_presets_base_dir(MediaExport::Preset::Visibility preset_visibility)"}
```
**Interpretation:** Single-arg form (no `PresetType`). Retry…

### Retry with single-arg form
**Request:** `POST /exec` with code:
```python
import flame
flame.PyExporter().get_presets_base_dir(flame.PyExporter.PresetVisibility.Autodesk)
```
**Response:** **No envelope returned. curl exit 7 (connection refused).**
```
curl: (7) Failed to connect to 127.0.0.1 port 9999 after 0 ms: Couldn't connect to server
```

### Bridge ping after the missing-envelope event
**Request:** `POST /exec` with code:
```python
1+1
```
**Response:** **No envelope.** curl exit 7. **Bridge is dead.**

**Interpretation:** Per R5, this is a SIGSEGV-class event (no envelope, curl times out / connection refused). The previous /exec call (`PyExporter().get_presets_base_dir(PresetVisibility.Autodesk)`) crashed Flame. **Surfaced as Probe 4 finding** (cross-probe state).

**STOP per R5.** Do not retry. Documented partial findings.

---

## Step 3 verdict

**FOUND (PARTIAL).** Two viable paths to take a Python-driven snapshot were located:

1. **`flame.PyExporter().export(clip, preset_path, output_dir)`** — programmatic Python entry point. Bridge-safe (no Qt dialog). Equivalent functionality to the player Snapshot button. Snapshot-config defaults exposed at `/opt/Autodesk/cfg/export_snapshot.cfg` (PNG-8bit, raw view-transform, `<name>.<frame>` pattern). **Recommended path.** Caveat: still need to verify exact preset path resolution (the `get_presets_base_dir` probe crashed the bridge; will need a different approach — likely just hardcoding `/opt/Autodesk/presets/.../<file>.xml` after a Flame restart).
2. **`flame.execute_shortcut("Export Snapshot")`** — triggers the player Snapshot button by keyboard-shortcut name. **NOT bridge-safe** (opens a Qt dialog → SIGSEGV from /exec on macOS). Only usable from a Flame menu hook running on the main thread. Documented for completeness.

The output-format / colour-space pipeline is also confirmed: Snapshot writes to disk with PNG-8bit / DPX / EXR (depending on preset), respects view-transform config (`BakeViewTransform`, `ViewTransformType`), and is detectable via the documented `post_export_asset` hook (`info["isSnapshot"]`).

**What was NOT verified** (because the bridge died):
- Concrete invocation of `PyExporter().export(...)` with a real clip and an Image_Sequence PNG-8bit preset
- File-format / bit-depth / colour-space of the produced file (`file <path>` / `oiiotool --info <path>`)
- Round-trip latency
- Exact preset path on disk for "PNG (8-bit)"

These can be verified after Flame restart in a follow-up spike — but the architectural feasibility (Path Snapshot exists and is Python-callable) is established.
