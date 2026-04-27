---
created: 2026-04-27T01:25:33.446Z
title: Wiretap "No route to host" blocks Camera Calibrator on legacy clips
area: general
files:
  - flame/camera_match_hook.py:305
  - forge_flame/wiretap.py:148-175
  - forge_core/image/buffer.py
---

## Problem

`wiretap_rw_frame` and the WireTap Python SDK both fail with `"No route to host"` / `"No route"` when reading frames from clips whose wiretap node id references a remote storage host (e.g., `flame-01`) that is currently unreachable. Surfaces in `flame/camera_match_hook.py:305` → `forge_flame.wiretap.extract_frame_bytes` → `wiretap_rw_frame` CLI subprocess.

User-visible symptom: dialog *"Could not read frame from clip source. Check the clip's media path is accessible."* even though the underlying media filesystem path (`/Volumes/raid/FlameMedia/...`) is locally accessible from a shell.

### Diagnosis (verified 2026-04-26 via forge-bridge probes against `testImage` clip)

- `clip.clip.get_wiretap_node_id()` returns a valid id like `/projects/1d386f3a-fd6f-43a4-b78a-b96aac922eb2/.../...` — node id structure is fine.
- `clip.resolution.get_value()` returns sensible `(5184, 3456, 8)` — Flame can read clip metadata locally.
- `WireTapServerHandle("127.0.0.1:IFFFS")` connects fine; `WireTapNodeHandle(server, nid)` constructs OK.
- BUT `nh.getClipFormat(fmt)` returns `False` with `nh.lastError() == "No route to host"`.
- The CLI fails identically with default host, `-h 127.0.0.1:IFFFS`, and `-h localhost:IFFFS` — same `No route` error every time.
- `mount` shows `flame-01` as an autofs entry that is NOT currently mounted (`/System/Volumes/Data/mnt/flame-01/{projects,media}`). Wiretap server likely tries to route to `flame-01` because that's the storage host registered for these clip nodes.
- The clip is in the same project UUID (`1d386f3a-...`) as the currently-open Flame project, so it's not a project mismatch.
- Code paths involved (`forge_flame/wiretap.py`, `forge_core/image/buffer.py`, `_read_source_frame`) have not been modified since commit `302960d` on 2026-04-17 — this is infrastructure drift, not a regression.

A full Flame restart did NOT cure the issue, ruling out simple session-state corruption.

## Solution

Triage at start of next session, in order of likelihood:

1. **Confirm `flame-01` is the unreachable host.** `ping flame-01`, `showmount -e flame-01` (if NFS), check Flame's stone server config for which host owns project UUID `1d386f3a-...`.
2. **Bring `flame-01` back online** — most likely cure for "this clip used to work yesterday". Could be a network blip, autofs stuck, or the host machine actually offline.
3. **Re-cache the clip's media to the local stone server** — re-issues a wiretap node id rooted at `127.0.0.1`, no remote routing needed. Interactive Flame work.
4. **Defensive fallback in `extract_frame_bytes`** — when wiretap returns `No route`, fall back to reading the underlying file directly off `media_folder` via cv2/imageio. Unblocks the calibrator on legacy clips. Trade-off: bypasses Flame's color/format pipeline, so OCIO probe via `get_clip_colour_space` would also need a fallback path.
5. **Improve user-visible error message** — surface the actual wiretap stderr (`No route to host`) in the dialog body so users get a fighting chance at diagnosis without bridge probes. Cheap, recommended regardless.

### Memory crumbs

- `memory/flame_wiretap_no_route_after_sigsegv.md` — captures the post-SIGSEGV pattern (was the original suspect, but full Flame restart didn't fix it; remote-host routing is the real issue).
- `memory/flame_bridge_qt_main_thread.md` — saved during this session: don't drive QDialog through the bridge; that's what triggered the SIGSEGV that initiated the chase.

### Suggested priority

Medium. Doesn't block the v6.3 multi-camera-picker rollout (Phase 04.4) since that work is upstream of frame reading. Would block production use of the calibrator on any project whose media lives on currently-unreachable remote stones.
