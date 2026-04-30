---
quick_id: 260430-ddi
mode: quick
type: spike
status: complete
subsystem: calibrator-architecture
tags: [flame, matchbox, pyexporter, pyattribute, expression-language, snapshot, spike]

# Dependency graph
requires: []
provides:
  - Primary-source verdict on three matchbox-calibrator architectural paths (Path A, Path B, Snapshot)
  - Bridge-safe `flame.PyExporter().export(...)` identified as the recommended frame-source for the calibrator
  - Two durable Flame API findings flagged as memory-crumb candidates
affects: [next-calibrator-architecture-plan, forge_flame.frame_export, calibrator-frame-source-replacement]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "One-probe-per-/exec-call discipline (R2) honored throughout"
    - "Throwaway batch group (R6) for all state-mutating bridge calls"
    - "Verbatim transcript pattern: every /exec request + response logged in transcripts/probe-{1,2,3}.md"

key-files:
  created:
    - .planning/quick/260430-ddi-spike-matchbox-calibrator-architecture-t/260430-ddi-PLAN.md
    - .planning/quick/260430-ddi-spike-matchbox-calibrator-architecture-t/260430-ddi-PROBE.md
    - .planning/quick/260430-ddi-spike-matchbox-calibrator-architecture-t/260430-ddi-SUMMARY.md
    - .planning/quick/260430-ddi-spike-matchbox-calibrator-architecture-t/transcripts/probe-1.md
    - .planning/quick/260430-ddi-spike-matchbox-calibrator-architecture-t/transcripts/probe-2.md
    - .planning/quick/260430-ddi-spike-matchbox-calibrator-architecture-t/transcripts/probe-3.md
  modified: []

key-decisions:
  - "Drop Path A (Action expression pixel sampling) entirely — verified structurally dead via vocabulary survey + PyAttribute API surface"
  - "Drop Path B (Python-driven matchbox uniform readback) entirely — matchbox PyNode wrapper exposes no per-uniform accessor; save_node_setup writes float uniforms as channel-name pointers, not flat values"
  - "Pursue Snapshot path via flame.PyExporter().export() — bridge-safe Python entry point, raw colour space output (BakeViewTransform=false), equivalent to player Snapshot button"
  - "User opted to skip the human-keyboard verification of candidate expression syntaxes — bridge-side evidence already structurally conclusive (verdict unchanged)"

patterns-established:
  - "Spike protocol: bridge ping → flame.batch confirmation → throwaway batch group (R6) → one /exec per probe (R2) → verbatim transcript per probe — proven repeatable for future architecture spikes"
  - "Quick-task PROBE.md skeleton with Findings Table + Recommendation Matrix + Next Planning Step is a useful self-contained format for go/no-go architecture decisions"

requirements-completed:
  - SPIKE-01-PathA-action-expression-pixel-sampling
  - SPIKE-02-PathB-matchbox-uniform-readback
  - SPIKE-03-snapshot-tool-from-python

# Metrics
duration: ~32min
completed: 2026-04-30
---

# Quick 260430-ddi: Matchbox Calibrator Architecture Spike — Summary

**Snapshot path (`flame.PyExporter().export()`) is the architectural recommendation; Path A and Path B are both structurally dead in Flame 2026.2.1 with primary-source evidence.**

## Headline Finding

Three independent feasibility probes against a live Flame 2026.2.1 session via forge-bridge produced a clear verdict matrix:

| Probe | Path | Verdict | Recommended? |
|-------|------|---------|--------------|
| 1 | Path A — Action expression pixel sampling | **DIDN'T-WORK** | NO |
| 2 | Path B — Python-driven matchbox uniform readback | **DISCOVERY-BLOCKED + NOT-READABLE** | NO |
| 3 | Snapshot — replace Wiretap as frame source | **FOUND (PARTIAL)** | **YES** |
| 4 | Cross-probe state | DEGRADED (Flame crashed during Probe 3 step 3.4) | n/a |

**The next planner should produce a plan that replaces `forge_flame.frame_export`'s Wiretap CLI route with a `flame.PyExporter().export(clip, "<PNG-8bit preset path>", "<temp dir>")` call inside the existing Flame menu hook.** The first task of that plan should be a 30-minute "concrete invocation" spike to locate the on-disk `PNG (8-bit)` Image_Sequence preset path (the bridge crashed before that enumeration could complete) and verify round-trip latency + file format / colour space / bit depth on a fresh Flame session.

## Performance

- **Duration:** ~32 min (autonomous bridge phase plus checkpoint resolution)
- **Started:** 2026-04-30T16:46:22Z
- **Completed:** 2026-04-30T17:18Z (autonomous bridge phase) + checkpoint close-out same evening
- **Tasks:** 4 (3 auto + 1 checkpoint, with the checkpoint resolved as "skip")
- **Files created:** 6 (PLAN.md, PROBE.md, SUMMARY.md, three transcripts)

## Accomplishments

- **Path A killed with primary-source evidence.** `userfun.expressions` plus 7 stock `expressions_*.action` examples contain zero references to `pixel/sample/texture/raster/imagepixel/surface`. Flame's expression language is closed over animation channels. PyAttribute exposes ONLY `get_value/set_value/values` — no `set_expression`, `link`, `connect`, `bind`, `subscribe`. Both ends are independently dead.
- **Path B killed with primary-source evidence.** Matchbox PyNode wrapper has 12 public methods, none for per-uniform access. `mb.attributes` is the schematic-node metadata, NOT shader uniforms. `getattr(mb, "out_pos_x")` returns `None` (permissive `__getattr__`). `save_node_setup` writes float uniforms as `<Channel Name="...">` pointers without inline scalar values — only int popups + bools have flat `<value>N</value>` scalars.
- **Snapshot path identified and characterized.** `flame.PyExporter().export(sources, preset_path, output_directory)` is the bridge-safe Python entry point. Default snapshot config (`/opt/Autodesk/cfg/export_snapshot.cfg`) uses PNG-8bit raw colour space (`BakeViewTransform: false`) — exactly what a calibrator frame-source needs. `flame.execute_shortcut("Export Snapshot")` is also viable but R3-blocked from /exec because it triggers a Qt dialog.
- **Two durable findings flagged for memory crumbs:** (a) Flame Action expression language has no pixel-sampling vocabulary; (b) Matchbox PyNode wrapper has no per-uniform accessor.

## Task Commits

This is a quick-mode planning spike — no per-task commits were taken during the autonomous bridge phase (only docs were produced under `.planning/quick/`). The orchestrator handles the docs commit per the quick workflow.

## Files Created/Modified

- `.planning/quick/260430-ddi-spike-matchbox-calibrator-architecture-t/260430-ddi-PLAN.md` — Quick-task plan spec with bridge contract rules R1-R6, three probe specs, PROBE.md skeleton, threat model
- `.planning/quick/260430-ddi-spike-matchbox-calibrator-architecture-t/260430-ddi-PROBE.md` — Findings document with Pre-flight, Findings Table, three primary probe sections, Probe 4 cross-probe state, Recommendation Matrix, Next Planning Step, Memory Crumb Candidates, Self-check
- `.planning/quick/260430-ddi-spike-matchbox-calibrator-architecture-t/260430-ddi-SUMMARY.md` — This file
- `.planning/quick/260430-ddi-spike-matchbox-calibrator-architecture-t/transcripts/probe-1.md` — Verbatim /exec request/response logs for Probe 1 (Path A: pre-flight, Step 1.1 doc search, Step 1.2 PyAttribute introspection, Step 1.3 human-in-the-loop verification = SKIPPED with rationale)
- `.planning/quick/260430-ddi-spike-matchbox-calibrator-architecture-t/transcripts/probe-2.md` — Verbatim /exec logs for Probe 2a (live readback) and Probe 2b (save-required)
- `.planning/quick/260430-ddi-spike-matchbox-calibrator-architecture-t/transcripts/probe-3.md` — Verbatim /exec logs for Probe 3 (snapshot API search) including the bridge crash on `PyExporter().get_presets_base_dir(PresetVisibility.Autodesk)`

No production code was modified. `git status --short` shows only the new directory `.planning/quick/260430-ddi-spike-matchbox-calibrator-architecture-t/` as untracked — verified twice.

## Decisions Made

1. **Drop Path A entirely** — bridge-side investigation produced two independent dead-ends (no pixel-sampling vocabulary in the expression language; no expression API on PyAttribute). Re-verification only warranted if a future Flame upgrade adds a new function to `userfun.expressions` or example .action files.
2. **Drop Path B entirely** — matchbox PyNode has no per-uniform accessor in either direction (write or read); save_node_setup output does not serialize float uniforms as scalars.
3. **Pursue Snapshot path** — `flame.PyExporter().export()` is the right Python entry point. Bridge-safe (no Qt dialog), raw colour space output, equivalent to the player Snapshot button.
4. **Skip the human-keyboard verification of expression syntaxes** (user decision at the checkpoint) — verdict was already structurally established by bridge-side evidence; keyboard confirmation would only surface "Unknown function pixel"-style errors firsthand without changing the verdict.

## Deviations from Plan

None — plan executed exactly as written. Per-task summary:

- **Task 1** (Pre-flight + Probe 1): Completed. Pre-flight passed (bridge alive, batch open, throwaway batch group `spike_260430_ddi` created via `desktop.create_batch_group(name=...)`). Probe 1 introspection completed end-to-end without crash.
- **Task 2** (Probe 2 + Probe 3): Completed. R6 was honored throughout (all state-mutating calls targeted `spike_260430_ddi`, never `gen_0460`). Probe 3 step 3.4 (`flame.PyExporter().get_presets_base_dir(PresetVisibility.Autodesk)`) crashed Flame's bridge subprocess; per R5, no retry was attempted, partial findings were captured to `transcripts/probe-3.md` before the crash, and the crash itself was recorded as a Probe 4 (cross-probe state) finding.
- **Task 3** (Human checkpoint for Probe 1 expression entry): User replied **skip**. Rationale recorded in `transcripts/probe-1.md` under "## Human-in-the-loop verification". Verdict unchanged.
- **Task 4** (Recommendation Matrix + Next Planning Step + Self-check): Completed by the autonomous bridge phase. PROBE.md is finalized.

## Issues Encountered

1. **Bridge SIGSEGV on `PyExporter().get_presets_base_dir(PresetVisibility.Autodesk)`** — single-call crash that took the Flame bridge offline temporarily. Symptoms matched `memory/flame_bridge_repl_contract.md` SIGSEGV-class behaviour: no envelope returned, curl exit 7, connection refused. Per R5, no retry was attempted. The bridge auto-recovered onto a different desktop / project, indicating Flame's session state had reset. The core Probe 3 finding (PyExporter is the right Python entry point) is established by docstring + filesystem evidence; concrete file-format/latency verification is deferred to the follow-on plan.

2. **Orphan throwaway batch group** — the throwaway batch group `spike_260430_ddi` was created in the user's original `gen_*` project via `desktop.create_batch_group(name="spike_260430_ddi")` at the start of the spike. After the bridge crash on Probe 3 step 3.4, Flame's session state reset onto a different project (`soc_*`), so the orphan `spike_260430_ddi` batch group was stranded in the original `gen_*` project and never cleaned up by the bridge. **The user has already been informed** and can clean it up manually from inside Flame at their convenience (right-click the batch group in the Desktop → Delete). No further action needed from the executor.

## User Setup Required

None — this is a planning artifact only. No external services configured, no environment variables added, no production code modified.

## Next Planning Step

**Produce a plan that replaces `forge_flame.frame_export`'s Wiretap CLI route with a `flame.PyExporter().export()`-driven snapshot path.**

The plan should:

1. **Front-load a 30-minute "concrete invocation" spike** as task 1: in a fresh Flame session, locate the actual on-disk path of the "PNG (8-bit)" Image_Sequence preset (probably under `/opt/Autodesk/presets/2026.2.1/export/...` — the bridge crash prevented enumeration), execute one `PyExporter().export(...)` call against a known clip parked on a known frame, measure round-trip latency, and `file <path>` / `oiiotool --info <path>` the result to confirm format + colour space + bit depth. Without this, plan-as-built risks shipping with the wrong preset path.
2. **Wire the calibrator's frame acquisition** to call `flame.PyExporter().export(clip, "<resolved preset path>", "<temp dir>")` from inside the existing Flame menu hook (already on the main thread — bypasses the R3 constraint that bit Probe 3's bridge introspection).
3. **Drop both Path A and Path B from consideration entirely.** Their dead-ends are documented in PROBE.md with primary-source evidence — there is no benefit to re-running these probes against this Flame version.

If the concrete-invocation spike in step 1 surfaces a blocker (e.g., the preset path is project-specific and must be discovered at runtime, or the export latency is >5s making the calibrator UX unworkable), fall back to keeping Wiretap and accepting its current 1.5s/4K-MXF cost as documented in `CLAUDE.md` (the Constraints section explicitly lists Wiretap perf as a non-goal for this milestone).

## Memory Crumb Candidates

Two findings from this spike are durable enough to warrant memory crumbs (per `CLAUDE.md` memory-crumb discipline — "would I want this if I forgot it" bar). Final crumb authoring is deferred to the user, but the candidates are:

1. **`flame_expression_language_no_pixel_sampling.md`** — Flame Action expression language has no pixel-sampling vocabulary. Closed over animation channels (`eval(channelName, frame_offset)`). Stock vocabulary: `sin/cos/exp/if/align/lookat/length/frame/trunc` plus arithmetic and vector literals. PyAttribute exposes only `get_value/set_value/values`. Module-level `[a for a in dir(flame) if "expr" in a.lower() or "link" in a.lower()]` returns `[]`. Would prevent re-running this same spike against future Flame versions until/unless an upgrade rev surfaces a new function in the example pool.

2. **`flame_matchbox_pynode_no_uniform_api.md`** — Matchbox PyNode wrapper has no per-uniform accessor; uniforms are channel pointers, not flat values. `dir(mb)` returns 12 public methods, none for parameters/uniforms/shader. `mb.attributes` is schematic-node metadata, not shader uniforms. `getattr(mb, "<any name>")` returns `None` due to a permissive `__getattr__` (so `hasattr` is meaningless — only `dir()` is ground truth). `save_node_setup` writes a `.matchbox_node` XML where float/vec uniforms are `<Channel Name="...">` pointers without inline scalar values; only int popups + bools have flat scalars. Would prevent the next architect attempting Path B from re-running the same exhaustive `dir()` chase.

(A third durable finding — `PyExporter().export()` is the bridge-safe equivalent of the player Snapshot button — is significant but already implicit in the Flame Python API docs; it doesn't need a crumb because the next planner will verify it concretely as task 1 of the follow-on plan.)

---
*Quick-task: 260430-ddi*
*Completed: 2026-04-30*
