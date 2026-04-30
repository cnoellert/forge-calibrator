---
quick_id: 260430-iv3
status: complete
verdict: KILLED — no Python read path for matchbox uniforms
mode: spike
type: research-only
wave: 1
depends_on: [260430-ddi]
started: "2026-04-30T20:44:15Z"
completed: "2026-04-30T20:55:30Z"
duration_min: 11
files_modified:
  - .planning/quick/260430-iv3-spike-matchbox-uniform-readback-via-flam/260430-iv3-PROBE.md
  - .planning/quick/260430-iv3-spike-matchbox-uniform-readback-via-flam/transcripts/probe-0.md
  - .planning/quick/260430-iv3-spike-matchbox-uniform-readback-via-flam/transcripts/probe-1.md
  - .planning/quick/260430-iv3-spike-matchbox-uniform-readback-via-flam/transcripts/probe-2.md
  - .planning/quick/260430-iv3-spike-matchbox-uniform-readback-via-flam/transcripts/probe-3.md
  - .planning/quick/260430-iv3-spike-matchbox-uniform-readback-via-flam/transcripts/probe-4.md
key_findings:
  - Matchbox shader uniforms are NOT Python-readable in Flame 2026.2.1 — confirmed at PyNode, batch, and module levels
  - Animate gesture has zero observable effect on the matchbox PyNode surface (channels stay NoneType)
  - input_sockets/output_sockets/sockets are schematic socket labels (e.g. ['Input 1']), not shader uniforms
  - flame.batch.mimic_link surfaces post-Animate but is type-restricted (equal node types only) — kills the link-picker discovery angle
  - Sidecar Comment-node fallback is unbuildable — reader works, writer has no candidate (matchbox can't populate it)
  - Architectural pivot identified: pixel-encoded INPUTS + snapshot decode, mirroring the existing out_pos_x/out_focal_mm pattern
---

# Quick Task 260430-iv3 — Matchbox Uniform Readback via Flame Channel API — Summary

## One-liner

Matchbox shader uniforms (`vp1_l1_start`, `vp2_l1_end`, etc.) are **not Python-readable** in Flame 2026.2.1 via any introspection surface tested. The proposed "matchbox-as-storage" architecture (where right-click headlessly reads VP values off the matchbox PyNode) is dead. The viable pivot is **pixel-encoded inputs + snapshot decode** — extend the existing pixel-encoding pattern (already used for solver outputs `out_pos_x` etc.) to also encode the VP inputs into a separate pixel region, then snapshot via `flame.PyExporter().export()` and decode in numpy.

## Verdict

**KILLED.** Channel-API readback (un-animated and post-Animate), expression-link picker discovery (incl. `mimic_link`), and Comment-node sidecar are all dead architectures for matchbox uniform readback. Two probes ran (1, 2); two probes were SKIPPED with reasoned justification (3, 4).

## Why this matters

The user's intuition that "something doesn't add up" with the prior 260430-ddi spike's Path B verdict was directionally correct — the channel-pointer language in `save_node_setup` XML implied a registry that should be Python-reachable. This spike resolved the question with primary-source evidence: the channel registry simply does not contain matchbox uniforms. The "GPU pipeline state lives somewhere readable" assumption is wrong for matchbox specifically; the values exist GPU-side but never surface to the Python introspection layer.

This finding closes a class of architectural ideas (sidecar Comment node, channel-direct-read, expression-link discovery) and points the next planner cleanly at the one remaining viable path.

## What was learned

1. **All 11 candidate channel containers on the matchbox PyNode return `NoneType`** — `channels`, `animation_data`, `animation`, `anim_data`, `channel`, `anim`, `animations`, `parameters`, `params`, `uniforms`, `inputs`. Identical result before AND after Animate. The permissive `__getattr__` returns None silently for missing names, so `is_none: True` across all candidates is the actual signal that no channel container exists at all.

2. **`mb.attributes` is a schematic-node metadata `list`** with 16 fixed entries (`pos_x`, `pos_y`, `name`, `collapsed`, `note`, `note_collapsed`, `selected`, `type`, `resolution`, `schematic_colour`, `schematic_colour_label`, `bypass`, `shader_name`, `resolution_mode`, `scaling_presets_value`, `adaptive_mode`). NO shader uniforms appear. Unchanged by Animate.

3. **`input_sockets` / `output_sockets` / `sockets`** exist as `list/list/dict` but hold only schematic socket labels (e.g. `['Input 1']` — the matchbox's "Front" texture-input renamed to "Input 1"). `first_item_type: str`. Not a shader-uniform surface.

4. **`flame.batch.<chan|anim|expr|link>*`** is empty pre-Animate; post-Animate the only addition is `mimic_link`. User confirmed Mimic Link is type-restricted (equal node types only), so an Action axis cannot mimic_link to a matchbox uniform. Link picker IS the channel registry; the registry has no matchbox-uniform entries; the lone added surface is type-incompatible.

5. **`get_attribute()` is not a method on PyNode.** Six name-format attempts (`vp1_l1_start`, `VP1_L1_Start`, `L1 Start`, `L1Start`, `vp1_l1_start_x`, `vp1_l1_start.x`) all failed with `TypeError: 'NoneType' object is not callable` — `mb.get_attribute` returned None via the permissive `__getattr__`.

6. **Animate spawned no sibling Channel-bearing node.** Batch graph identical pre/post Animate: `[('testImage', 'PyClipNode'), ('CameraMatch', 'PyNode')]`.

7. **Sidecar Comment-node architecture is unbuildable** — not because the reader fails (PyAttribute round-trip on a text field would work), but because there is no plausible WRITER path. Matchbox GLSL can't mutate Python state; right-click hooks can't read the uniforms in order to write them out; manual artist population defeats the matchbox UI advantages.

## Architectural pivot identified

**Pixel-encoded inputs + snapshot decode.** The matchbox already uses this pattern in the other direction — `out_pos_x`, `out_pos_y`, `out_focal_mm`, etc. are encoded into bottom-left pixels for downstream Action expression linking (per the shader header comment). Extending the same pattern to inputs:

- Add a small pixel region (e.g. top-left 4×4) to the shader output that encodes the 8 VP `vec2` uniforms as known-bit-depth color samples + a sentinel for round-trip verification.
- Right-click handler calls `flame.PyExporter().export(matchbox_clip, png_8bit_preset, tmp_dir)` — the snapshot path validated by 260430-ddi.
- Python decodes the input pixels (numpy / PIL — already available in the forge env) and recovers VP coordinates within bit-depth precision (~1/255 for 8-bit; bump to 16-bit if more precision needed).
- Solver runs headlessly on the decoded values; results written to the Action camera as today.

This keeps the matchbox UI advantages (axis widgets in viewport, real-time visual feedback, lives in batch graph, no PySide2 dialog), reuses existing snapshot infrastructure, and uses an already-proven encoding pattern.

## Three implementation directions for the next planner

| Direction | Approach | Pros | Cons |
|-----------|----------|------|------|
| **A (recommended)** | Pixel-encoded inputs + snapshot decode | Clean architectural fit; matchbox stays as artist surface; reuses validated snapshot path; same pattern already in shader for outputs | New shader pixel region to design; bit-depth round-trip needs verification; preset-path resolution from 260430-ddi still open |
| **B (fallback)** | Re-do PySide2 line-drawing UI (v5.x architecture) | Proven; values are directly readable from Qt widgets | Focus-steal/blocking issues; loses "lives in batch graph"; loses real-time viewport visual feedback |
| **C (long-term)** | Wait for Flame to expose matchbox uniforms via Python API in a future version | Zero engineering effort | Indefinite timeline; not actionable now |

**Recommended:** Direction A. First task should be a 45-60 min pixel-encoding feasibility spike that resolves two known unknowns: (1) on-disk PNG-8bit Image_Sequence preset path (260430-ddi's bridge crashed on `get_presets_base_dir` before resolution), and (2) bit-depth + colour-space round-trip fidelity (does the GLSL → framebuffer → PNG → numpy chain preserve the encoded values within the precision VP coordinates need).

## Files created

- `260430-iv3-PROBE.md` — Findings document with per-probe Question/Approach/Result/Verdict/Evidence, Recommendation Matrix (5 rows incl. the pivot), Next Planning Step, 2 Memory Crumb Candidates, Self-check (10/10 ✓)
- `transcripts/probe-0.md` — Pre-flight bridge ping + throwaway batch group setup (written by executor)
- `transcripts/probe-1.md` — Verbatim /exec request + response for un-animated channel introspection
- `transcripts/probe-2.md` — Verbatim /exec request + response for post-Animate introspection (incl. `input_sockets`/`output_sockets`/`sockets` follow-up + `mimic_link` discovery)
- `transcripts/probe-3.md` — SKIPPED-with-rationale (mimic_link type-restricted)
- `transcripts/probe-4.md` — SKIPPED-with-rationale (sidecar writer path collapsed)

## Files NOT modified

No production code outside `.planning/quick/260430-iv3-spike-matchbox-uniform-readback-via-flam/` was touched. Verified by `git status`.

The matchbox shader (`matchbox/CameraMatch.1.glsl`, `matchbox/CameraMatch.xml`) is **not modified** — the pixel-encoding pivot is the next planner's territory and requires a feasibility spike before any shader edits land.

## Memory crumb candidates

Two candidates flagged for user authoring (per CLAUDE.md memory-crumb discipline):

1. **`flame_matchbox_uniforms_not_python_readable.md`** — Matchbox shader uniforms are not Python-readable at any layer (PyNode, module, batch, channel, attribute, link). Animate has no observable effect. Architectural implication: any matchbox→Python data flow must use an out-of-band transport (e.g., pixel encoding into the rendered output).
2. **`flame_mimic_link_type_restricted.md`** — Flame's `mimic_link` mechanism only links between equal node types. Surfaces post-Animate as `flame.batch.mimic_link`. Combined with the empty `flame.batch.<chan|anim>*` registries, this kills the "discover channel paths via the link picker" pattern for cross-type targets.

## Cleanup

- Throwaway batch group `spike_260430_iv3` is left intact in the user's current Flame project (per the orchestrator's normal cleanup discipline — user can right-click → Delete in the Desktop at convenience). The matchbox node and its animated `vp1_l1_start = (0.42, 0.69)` keyframe survive there as a reproduction case if needed.

## Self-check

- [x] Verdict written: KILLED — no Python read path for matchbox uniforms
- [x] Architectural pivot identified with concrete first task for next planner
- [x] All four probes have a verdict and an evidence transcript
- [x] Recommendation Matrix populated (5 rows incl. the pivot)
- [x] Memory crumb candidates flagged
- [x] R1/R2/R5/R6/R7 all honored
- [x] Bridge state at exit: UP
- [x] No production code outside `.planning/quick/260430-iv3-...` modified

## Note for orchestrator

Bridge is UP at spike exit. Next /gsd-quick or /gsd-plan-phase invocation can proceed without restart. The pixel-encoding feasibility spike (next planner's first task) will need bridge access for the snapshot round-trip step.
