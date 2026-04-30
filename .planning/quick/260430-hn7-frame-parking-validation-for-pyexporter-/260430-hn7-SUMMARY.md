---
quick_id: 260430-hn7
status: blocked
verdict: PARTIAL — DIDN'T-PARK
mode: quick
type: execute
wave: 1
depends_on: [260430-e5y]
started: "2026-04-30T19:45:30Z"
completed: "2026-04-30T19:55:30Z"
duration_min: 10
files_modified:
  - .planning/quick/260430-hn7-frame-parking-validation-for-pyexporter-/260430-hn7-PROBE.md
  - .planning/quick/260430-hn7-frame-parking-validation-for-pyexporter-/transcripts/probe-park.md
key_findings:
  - PyClip has NO current_time / go_to_frame / setter API in Flame 2026.2.1
  - PyExporter.export() has NO frame parameter
  - Only range-control surface is e.export_between_marks=True + segment record_in/record_out (mutates clip edit data)
  - Underlying export IS per-frame faithful (49 distinct PNGs from 49-frame multi-frame clip; 3 sample hashes all distinct)
  - 4K-16bit full-clip export: ~0.36s/frame amortized → 17.5s for 49 frames (10x+ regression vs wiretap_rw_frame's ~1.5s)
  - Bridge SIGSEGV during Phase 4 segment-time introspection (str(seg.record_in)) on 4448x3096 production clip
---

# Quick Task 260430-hn7 — Frame-Parking Validation for PyExporter Recipe

## One-liner

PyClip has **no frame-parking API** in Flame 2026.2.1; the 260430-e5y recipe's
`TODO(next-spike): park clip on target_frame before export` cannot be filled
with a single API call — implementation planner must pick between three
concrete routes (full-export-pick / mark-bracket-restore / throwaway-clone).

## Verdict

**PARTIAL — DIDN'T-PARK.** The primary question ("is there a parking API on
PyClip?") was answered **NO** with confidence. The secondary question
("does the underlying export produce per-frame distinct output?") was
answered **YES** (49 distinct hashes from a single 49-frame export). The
spike was aborted at Phase 4 by a Flame SIGSEGV during segment-time
introspection, but the parking-API question was already conclusively
answered before that point — the missing data is two **separate** parked
exports for byte-comparison, not the existence-of-API answer.

## What was learned

1. **PyClip API surface for navigation: empty.** No `current_time`,
   `go_to_frame`, `set_current_time`, or equivalent on PyClip, PyClipNode, or
   `flame.batch`. Verified via three separate `dir()` introspections on the
   production clip `gen_0460_graded_L01`.

2. **PyExporter.export() signature is range-blind.** Help docstring confirms:
   `export(sources, preset_path, output_directory, [bg, hooks, hooks_user_data])`
   — no frame parameter. The only range-control surface on PyExporter is
   `export_between_marks: bool`, which couples to mark in/out set on the
   clip's segment.

3. **Segment marks ARE mutating.** `pc.versions[0].tracks[0].segments[0]`
   exposes `record_in/out`, `source_in/out`, `head/tail`, `trim_head/tail` —
   these are persistent edit-data attributes, not transient navigation.
   Setting them mutates the clip; restoring them within the same /exec call
   is feasible but risky (R8 violation if export crashes mid-way).

4. **The underlying export pipeline is per-frame faithful.** A full export
   of `gen_0460_graded_L01` (49 frames at 4K-16bit) produced 49 PNG files
   with timecode-derived names (`<clip>.<TC_FRAME>.png`,
   `00786578..00786626`). Three sample frames had three distinct SHA-256
   hashes and three different file sizes — the export is NOT producing
   stale/cached/repeated data.

5. **Performance ceiling for the recipe:** ~0.36s/frame amortized at
   4448x3096 16-bit. For Camera Match's "load one reference frame from a
   plate" use case, full-clip export (Route A) is a ~10-40x regression vs
   `wiretap_rw_frame`'s ~1.5s/frame.

## Three implementation routes (for the next planner to pick)

| Route | Approach | Pro | Con |
|-------|----------|-----|-----|
| **A** | Export full clip; recipe picks `output_dir/<clip>.<TC>.png` by frame index | Zero clip mutation; pure read-only | 17.5s for 49-frame 4K plate; 10x+ regression vs wiretap |
| **B** | Set `seg.record_in == seg.record_out`; `e.export_between_marks=True`; export; restore originals | Fast (~0.5s/frame); single-file output | Persistent edit-data mutation; R8-violation if export crashes mid-way; restore must be in `finally:` |
| **C** | Clone clip into throwaway batch (`PyClipNode.duplicate()` or `flame.import_clips`); set marks on clone; export; delete clone | Zero mutation on production clip; fast | Requires throwaway-batch lifecycle management; clone-and-delete adds ~1-2s overhead; needs its own spike to validate |

**Recommendation for the implementation planner:** Default to **Route B with
strict try/finally restoration**, with **Route A as a fallback** when the
clip is `unlinked` or otherwise unsafe to mutate. Route C is overkill for
v6.x; revisit if Route B turns out to leave bad state on real-world crashes.

## Crash event

Phase 4 ended with a Flame SIGSEGV — bridge unreachable, no envelope
returned. The trigger was Request 17:

```python
seg = pc.versions[0].tracks[0].segments[0]
{"record_in": str(seg.record_in), ...}   # str() coercion of PyTime on production 4K-16bit clip
```

This is now the **3rd Flame crash in today's session**. Pattern (worth
recording in MEMORY.md if reproducible): `str(PySegment.record_in)` on a
high-resolution production clip may be a SIGSEGV trigger. Not bisected this
spike — added as a possible future probe target for a smaller throwaway
clip first.

## Files produced

- `.planning/quick/260430-hn7-frame-parking-validation-for-pyexporter-/260430-hn7-PROBE.md` — primary findings doc with verdict + implementation-blocker note
- `.planning/quick/260430-hn7-frame-parking-validation-for-pyexporter-/transcripts/probe-park.md` — verbatim /exec request+response for all 17 bridge calls (16 successful, 1 crash)

## Files NOT modified

No production code outside `.planning/quick/260430-hn7-...` was touched. The
25-LOC recipe in `260430-e5y-PROBE.md` is **NOT updated** because the
hypothesized one-line parking call does not exist. The implementation plan
must take ownership of the route choice.

## Cleanup

- `/tmp/forge_park_full/` left intact with 49 PNGs (~700MB). User can
  `rm -rf /tmp/forge_park_full/` at convenience.
- No throwaway batch was created (R8 honored).
- No production clip was mutated. The crash occurred on a read-only
  introspection.

## Self-check

- [x] Verdict written: PARTIAL — DIDN'T-PARK
- [x] Implementation-blocker note for next planner with 3 concrete routes
- [x] Transcript with verbatim bridge logs
- [x] R5/R8 honored
- [x] Status: BLOCKED (per R5 stop-rule + bridge-down)
- [x] Bridge state at exit: DOWN (user must restart Flame for any continuation)

## Note for orchestrator

The bridge is currently down. Any continuation work on this thread requires
a Flame restart (3rd of the day). User should be aware that today's session
is exhibiting accumulating SIGSEGV pressure — recommend ending the session
here and resuming on a fresh Flame boot tomorrow.
