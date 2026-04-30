# Probe 3 — Expression-Link Picker Symmetry — SKIPPED

**Skipped:** 2026-04-30T20:55:00Z
**Reason:** User domain knowledge collapsed the remaining 1% rationale.

## Why skipped

Probes 1 and 2 conclusively established that matchbox shader uniforms are not reachable via the matchbox PyNode wrapper, schematic socket lists, or any per-attribute getter — before OR after Animate. The lone post-Animate lead (`flame.batch.mimic_link`) was the last 1% argument for running Probe 3: maybe the link/mimic mechanism would enumerate matchbox uniforms as available targets and reveal the addressing scheme.

User confirmed: **Mimic Link is type-restricted — only links between equal node types.** An Action axis cannot mimic_link to a matchbox uniform regardless of how the channel registry is structured. The link picker therefore cannot enumerate matchbox uniforms as Action-axis targets, and `mimic_link` itself is dead for cross-type linking.

This is consistent with the prior probes' finding that `flame.batch.chan*` was empty — link targets ARE the channel registry, and the registry has no matchbox-uniform entries.

## No /exec call made

R6 honored — no state mutation. R1 honored — no probe issued. The spike STOP rule for "remaining probe is provably low-value" was applied.

## Verdict

**SKIPPED — provably dead** (not "untested"). Even the optimistic interpretation requires a registry that prior probes confirmed is empty, plus a cross-type link mechanism that the user confirmed Flame does not provide.
