---
phase: 01-export-polish
fixed_at: 2026-04-20T00:00:00Z
review_path: .planning/phases/01-export-polish/01-REVIEW.md
iteration: 1
findings_in_scope: 2
fixed: 2
skipped: 0
status: all_fixed
---

# Phase 01: Code Review Fix Report

**Fixed at:** 2026-04-20T00:00:00Z
**Source review:** .planning/phases/01-export-polish/01-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 2 (WR-01, WR-02; no Critical findings)
- Fixed: 2
- Skipped: 0

Scope was `critical_warning`, so the four Info findings (IN-01..IN-04) were
not touched in this iteration.

Post-fix verification: full pytest suite (`python -m pytest`) was executed
after both commits landed and all **280 tests pass** in 0.83s. No test
regressions were introduced. Both fixes also passed Python AST syntax
validation before commit (Tier 2 verification).

## Fixed Issues

### WR-01: Reserved `forge_bake_*` keys can be overwritten by caller-supplied `custom_properties`

**Files modified:** `tools/blender/bake_camera.py`
**Commit:** `4a7dff6`
**Applied fix:** Introduced a module-level `_RESERVED_STAMP_KEYS` frozenset
listing the four round-trip stamps (`forge_bake_version`,
`forge_bake_source`, `forge_bake_scale`, `forge_bake_input_path`). Rewrote
`_stamp_metadata` to:

1. Apply `custom_properties` FIRST, skipping any key in
   `_RESERVED_STAMP_KEYS` and emitting a `bake_camera: ignoring reserved
   custom_properties key '<key>' (would clobber round-trip stamp)`
   warning to stderr so the skip is visible in Blender subprocess logs.
2. Write the four reserved stamps LAST so they cannot be clobbered even
   if the explicit-reject branch is bypassed in a future refactor
   (defence-in-depth — loud reject + silent write-last).

This preserves the round-trip scale invariant that CLAUDE.md identifies
as the tool's core value: `extract_camera.py` reads `forge_bake_scale`
and multiplies position back up, so a clobbered scale would silently
produce a geometrically-wrong camera. Also hardens the
`forge_bake_source` provenance gate that Phase 2's "Send to Flame"
addon will rely on.

Docstring updated to document the reserved-key guard. No behavioural
change for the current trusted single-caller (hook on the same machine)
because the hook never sends reserved keys in its `custom_properties`.

### WR-02: `_sanitize_name_component` allows `.`, `..`, and all-punctuation names to pass through

**Files modified:** `flame/camera_match_hook.py`
**Commit:** `84bc57a`
**Applied fix:** Extended `_sanitize_name_component` past the
whitelist-regex step with two extra guards:

1. `safe.lstrip(".")` — strips leading dots so `.hidden`, `.`, `..`,
   `...` cannot produce Unix dotfiles or traversal-looking path
   components inside the final `{action}_{cam}.blend`.
2. `if not any(c.isalnum() for c in safe): return "unnamed"` — replaces
   the old `safe.strip("_")` predicate. The old predicate only caught
   all-underscore inputs; the new predicate also catches `---`, `...`,
   `___`, and mixed-punctuation inputs that contain no alphanumeric
   content.

Verified the new behaviour against all five cases the review called out
plus the happy path via a Python harness:

| input          | output      |
|----------------|-------------|
| `"."`          | `"unnamed"` |
| `".."`         | `"unnamed"` |
| `"..."`        | `"unnamed"` |
| `"---"`        | `"unnamed"` |
| `"___"`        | `"unnamed"` |
| `".hidden"`    | `"hidden"`  |
| `"Action_01"`  | `"Action_01"` |
| `"My Cam"`     | `"My_Cam"`  |
| `"Cam/01"`     | `"Cam_01"`  |
| `""`           | `"unnamed"` |
| `"a.b"`        | `"a.b"`     |
| `"_underscore"`| `"_underscore"` |

Docstring updated to document the leading-dot strip and the
alnum-required predicate, and to explicitly mention the
`---` / `...` / `"."` edge cases the old `strip("_")` predicate missed.

IN-04 flagged that this helper has no unit tests. That test-addition
work is Info-severity and out of scope for this fix pass
(`fix_scope: critical_warning`); the semantic behaviour has been
spot-checked interactively above and the full pytest suite (280 tests)
still passes unchanged.

## Skipped Issues

None. Both in-scope findings were successfully fixed.

---

_Fixed: 2026-04-20T00:00:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
