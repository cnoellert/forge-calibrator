# Probe 4 — Sidecar Comment-Node JSON Round-Trip — SKIPPED

**Skipped:** 2026-04-30T20:55:00Z
**Reason:** Architectural fallback collapsed by upstream finding — Comment-node sidecar is unbuildable without a write path that the matchbox cannot provide.

## Why skipped

Probe 4 was queued as the architectural fallback IF Probes 1-3 all died: store the VP values in a Comment node next to the matchbox, read them back via PyAttribute. The READBACK side (`comment.text.get_value()`) would almost certainly work — text attributes are basic PyAttribute surfaces.

But during synthesis, the sidecar architecture hit a deeper kill: **there is no plausible WRITE path**.

For a Comment-node sidecar to be useful, something has to populate it with the current VP values whenever the artist edits the matchbox UI. The candidates are:

1. **Artist manually populates it** — terrible UX; defeats the entire point of the matchbox UI.
2. **The matchbox shader writes to it** — impossible. GLSL can render pixels; it cannot mutate Flame's batch graph or Python state.
3. **A right-click hook that runs at solve-time** — but the hook's job is to READ the values; if it can't read them off the matchbox in the first place (Probes 1-2), it can't write them to a sidecar either.

The Comment-node round-trip itself is trivially testable, but proving it works does not unblock anything. The bottleneck is upstream: **no Python read path exists for matchbox uniforms**, period — and that breaks the sidecar's writer side, not its reader side.

## The actual remaining architecture

The viable pivot identified during synthesis is **Option 2 from the closing discussion**: re-purpose the existing pixel-encoding pattern in `CameraMatch.1.glsl` (which already writes solver outputs to bottom-left pixels for expression linking) to ALSO encode the VP **inputs** into a separate pixel region. The right-click handler then snapshots the matchbox output via `PyExporter().export()` (the recommended path from spike 260430-ddi), decodes the input pixels in Python, and runs the solver headlessly. This keeps the matchbox UI advantages (axis widgets in the viewport, visual feedback, no PySide2 dialog) and uses the snapshot transport that 260430-ddi already validated as bridge-safe.

That is its own implementation spike, not a Probe-4-shaped probe. The next planner takes ownership.

## No /exec call made

R6 honored — no state mutation. R1 honored — no probe issued.

## Verdict

**SKIPPED — fallback collapsed.** The Comment-node sidecar is not a viable architecture because the matchbox cannot programmatically write to it. Pivot to pixel-encoded inputs + snapshot decode (next-planner territory).
