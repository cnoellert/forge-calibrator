---
quick_id: 260430-e5y
status: complete
verdict: WORKED
date: 2026-04-30
follows: 260430-ddi
artifacts:
  - .planning/quick/260430-e5y-smoke-test-pyexporter-export-end-to-end-/260430-e5y-PROBE.md
  - .planning/quick/260430-e5y-smoke-test-pyexporter-export-end-to-end-/transcripts/probe-export.md
---

# 260430-e5y Summary — PyExporter().export() smoke-test

## Verdict

**WORKED.** `flame.PyExporter().export()` is a viable Wiretap replacement
for the calibrator's frame source. End-to-end round-trip in **0.41s** on a
20×20 test plate with a real PNG on disk that decodes cleanly through
`forge_core.image.buffer.decode_image_container`.

## Headline findings

1. **Real preset path located** —
   `/opt/Autodesk/presets/2026.2.1/export/presets/flame/file_sequence/PNG/PNG (8-bit).xml`.
   The prior 260430-ddi PROBE's
   `/opt/Autodesk/io/presets/file_sequences/Png-8bit.xml` was fictitious
   (smoke test exposed it with a clean `RuntimeError("No such file")`).

2. **`e.foreground = True` is required** before `e.export()` — otherwise
   the export runs async and the file isn't on disk when we try to read it.

3. **PyClip and PyClipNode have different shapes for resolution.** PyClip
   exposes `width`/`height`/`bit_depth` as direct integer attributes;
   PyClipNode wraps them in `resolution.get_value()`. The recipe handles
   both via try/except fallthrough — a wrinkle the existing
   `forge_flame/wiretap.py` doesn't have to deal with.

4. **R5/R6/R7 honored.** Throwaway `spike_260430_e5y` batch group, no
   `get_presets_base_dir()` call (which SIGSEGV'd in 260430-ddi), no
   SIGSEGV this run. Two non-spike Flame restarts earlier in the day
   delayed but did not block this spike.

## Recipe (in PROBE.md)

25-line `extract_frame_via_export(clip, target_frame=None)` function ready
to lift into `forge_flame/frame_export.py`. Signature shape-matches the
existing `forge_flame.wiretap.extract_frame_bytes` for drop-in
replacement. One `TODO(next-spike)` for player-frame-parking (the test
plate was single-frame so parking was a no-op — needs a 15-min validation
against a multi-frame plate before implementation).

## Cleanup notes

Two orphaned throwaway batch groups left in the workspace from today's
spike thrash:
- `spike_260430_ddi` (from 260430-ddi)
- `spike_260430_e5y` (this spike)

User can delete both manually at convenience. No code-side cleanup
needed.

## Next planning step

The next planner should:

1. **Run a 15-min frame-parking spike** against a real multi-frame plate
   (NOT in `spike_*` — needs a real plate with ≥2 frames from production
   work). Confirm `clip.current_time = target_frame` (or equivalent)
   parks the clip before `e.export()` reads the right frame.

2. **Then plan the implementation phase** that:
   - Creates `forge_flame/frame_export.py` with the recipe lifted from
     PROBE.md
   - Adds a `frame_source={"wiretap","export"}` config knob to
     `camera_match_hook.py` for A/B testing in production
   - Adds 5 tests (4 unit, 1 integration — see PROBE.md "Next Planning
     Step" §4 for the matrix)
   - Keeps Wiretap as runtime fallback for 1-2 weeks before retirement
     (sanity gate against unforeseen clip-type variance)

The preset path is version-pinned (`2026.2.1`) — switch to glob if a
tester reports a Flame major-version bump.

## Files

- `260430-e5y-PROBE.md` — findings + 25-LOC recipe + next-planner checklist
- `transcripts/probe-export.md` — verbatim /exec request+response log
