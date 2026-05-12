---
quick_id: 260512-third-axis-handedness
status: complete
date: 2026-05-12
---

# Audit third-axis handedness in calibrator overlay

## Goal

Recover the previously verified overlay convention after live testing showed the Action result was still incorrect.

## Diagnosis

History review found commit `32c7bfc`, which explicitly verified that the overlay should draw the positive missing-axis family (`+X`, `+Y`, or `+Z`) and should not mirror the solver's signed cross product. The overlay is an artist-facing reference; the solver's signed axis math is a separate code path.

## Scope

- Preserve the positive missing-axis overlay convention from `32c7bfc`.
- Do not change solver math without a fresh live-Flame proof.
- Use native `1.0x` scene scale as the default regression test path.

## Reopened Diagnosis

Live testing showed the signed-overlay experiment did not fix the Action result. Commit history points to native-scale behavior after `1412555` + `32c7bfc` as the known-good anchor, and to the May 12 scene-scale change as the only committed geometry change since then. Next test should compare `1.0x` against the smaller scale values.
