---
quick_id: 260501-rus
mode: quick
type: execute
wave: 1
depends_on: [260501-dpa, 260501-em8, 260501-knl]
files_modified:
  - tools/blender/bake_camera.py
  - forge_flame/camera_io.py
  - forge_flame/fbx_ascii.py
  - flame/scale_picker_dialog.py
  - flame/camera_match_hook.py
  - tests/test_bake_camera.py
  - tests/test_blender_roundtrip.py
  - tests/test_scale_picker_dialog.py
  - tests/test_hook_export_camera_to_blender.py
  - .planning/todos/pending/2026-05-02-flame-blender-scale-roundtrip-uat.md
autonomous: true
requirements: [LADDER-V2-CANONICAL, LADDER-V2-DEFAULT-INTERIOR, LADDER-V2-DEPRECATED-COMPAT, LADDER-V2-SEMANTIC-LABELS]

must_haves:
  truths:
    - "Bake-side validator accepts the 7 new canonical stops {1, 10, 100, 1000, 10000, 100000, 1000000} AND the 2 deprecated stops {0.01, 0.1} for back-compat with already-baked .blend files"
    - "Dialog presents 7 buttons in physical-scale order: Landscape ×10⁰ | Outdoor ×10¹ | Soundstage ×10² | Interior ×10³ | Tabletop ×10⁴ | Product ×10⁵ | Macro ×10⁶"
    - "Interior (1000.0) is the dialog's default button (setDefault + objectName='primary' + Enter shortcut); deprecated stops are NEVER offered in the dialog"
    - "Hook hardcoded default at the call site flips 100.0 → 1000.0 (the new studio sweet spot — Interior)"
    - "Bit-exact position parity holds across all 7 new canonical stops in the round-trip parity tests (deltas at IEEE-754 floor, same as 260501-dpa baseline)"
    - "Pre-existing parity tests for the deprecated {0.01, 0.1} stops continue to pass (deprecated values are still valid bake-side inputs)"
    - "JSON contract field `flame_to_blender_scale` value semantics unchanged — raw float divisor; only the canonical stop set + default + UI labels change"
    - "Queued UAT todo updated: '1x = ~833m architectural' wording replaced with 'Landscape · ×10⁰ → ~1.8km'; non-default scale exemplar reset to a value the user can pick during UAT"
    - "Full test suite green; existing test counts adjusted only where the canonical set widened (no test deletions for the deprecated stops)"
  artifacts:
    - path: "tools/blender/bake_camera.py"
      provides: "Extended _FLAME_TO_BLENDER_SCALE_LADDER + _DEPRECATED_FLAME_TO_BLENDER_SCALE_LADDER + validator that accepts the union"
      contains: "_FLAME_TO_BLENDER_SCALE_LADDER = (1.0, 10.0, 100.0, 1000.0, 10000.0, 100000.0, 1000000.0)"
    - path: "flame/scale_picker_dialog.py"
      provides: "7-button forge dialog with semantic labels + unicode superscript multipliers; Interior default"
      contains: "(\"Landscape\", 1.0,"
    - path: "flame/camera_match_hook.py"
      provides: "_LADDER_MENU_STOPS extended to 7 stops; default-call-site studio default flipped 100.0 → 1000.0"
      contains: "_LADDER_MENU_STOPS = (1.0, 10.0, 100.0, 1000.0, 10000.0, 100000.0, 1000000.0)"
    - path: "tests/test_bake_camera.py"
      provides: "Parametrized validator coverage for all 7 canonical stops + 2 deprecated stops + updated rejection set"
    - path: "tests/test_blender_roundtrip.py"
      provides: "Round-trip parity at all 7 new canonical stops (deprecated stops retained as separate parametrize for back-compat coverage)"
    - path: "tests/test_scale_picker_dialog.py"
      provides: "Button label assertions updated for the 7 semantic labels with unicode superscript; Interior default button parity"
    - path: ".planning/todos/pending/2026-05-02-flame-blender-scale-roundtrip-uat.md"
      provides: "UAT 2 narrative reworded — Landscape ~1.8km replaces 'architectural ~833m'; non-default exemplar reset"
  key_links:
    - from: "flame/scale_picker_dialog.py::pick_scale"
      to: "flame/camera_match_hook.py::_export_camera_to_blender_with_picker"
      via: "return value (float on accept, None on cancel)"
      pattern: "scale = pick_scale\\(default=1000\\.0\\)"
    - from: "flame/camera_match_hook.py::_export_camera_pipeline kwarg default"
      to: "forge_flame/fbx_ascii.py::fbx_to_v5_json flame_to_blender_scale kwarg"
      via: "v5 JSON top-level field"
      pattern: "flame_to_blender_scale=1000\\.0"
    - from: "tools/blender/bake_camera.py::_validate_flame_to_blender_scale"
      to: "_FLAME_TO_BLENDER_SCALE_LADDER + _DEPRECATED_FLAME_TO_BLENDER_SCALE_LADDER union"
      via: "membership check (in) against the union set"
      pattern: "_FLAME_TO_BLENDER_SCALE_LADDER \\+ _DEPRECATED"
---

<objective>
Extend the Flame↔Blender scale ladder from the 5-stop {0.01, 0.1, 1, 10, 100} set
shipped in 260501-dpa/i31/knl to a 7-stop semantic ladder
{1, 10, 100, 1000, 10000, 100000, 1000000} — Landscape / Outdoor / Soundstage /
Interior / Tabletop / Product / Macro. Default flips Soundstage (100.0) → Interior
(1000.0) at every default call site (dialog default button + hook hardcoded
kwarg). Bake-side validator keeps {0.01, 0.1} as deprecated-but-valid so any
.blend baked under the old contract still round-trips cleanly. Dialog re-skinned
with 7 buttons + unicode-superscript multipliers + Interior highlighted as
default. JSON contract field `flame_to_blender_scale` value semantics
UNCHANGED — still a raw float divisor; only the canonical stop set + default +
UI labels change. Queued UAT todo updated to match new physical-distance
narratives.

Purpose: better physical-scale resolution for the artist (1.8 km → 1.8 mm covered
in 7 log-decade stops) and better default for the actual production case
(interiors, not soundstages).

Output: 4 atomic commits — one per task — each green on its own.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
</execution_context>

<context>
@CLAUDE.md
@.planning/STATE.md
@.planning/quick/260501-dpa-add-flame-blender-scale-ladder-knob-roun/260501-dpa-SUMMARY.md
@.planning/quick/260501-knl-revert-ladder-menu-replace-with-forge-th/260501-knl-SUMMARY.md
@flame/scale_picker_dialog.py
@tools/blender/bake_camera.py
@flame/camera_match_hook.py
@forge_flame/camera_io.py
@forge_flame/fbx_ascii.py
@tests/test_bake_camera.py
@tests/test_blender_roundtrip.py
@tests/test_scale_picker_dialog.py
@tests/test_hook_export_camera_to_blender.py
@.planning/todos/pending/2026-05-02-flame-blender-scale-roundtrip-uat.md

<interfaces>
<!-- Key shapes the executor needs. Already exist in the codebase; widening only. -->

# tools/blender/bake_camera.py — current state (line ~200, ~309)
_FLAME_TO_BLENDER_SCALE_LADDER = (0.01, 0.1, 1.0, 10.0, 100.0)

def _validate_flame_to_blender_scale(value: float) -> float:
    v = float(value)
    if v not in _FLAME_TO_BLENDER_SCALE_LADDER:
        ladder_str = "{" + ", ".join(str(x) for x in _FLAME_TO_BLENDER_SCALE_LADDER) + "}"
        raise SystemExit(f"flame_to_blender_scale={value} is not on the allowed ladder {ladder_str}")
    return v

# flame/scale_picker_dialog.py — current state (line 35)
_LADDER_STOPS = [
    # (label, scale_value, subtitle)
    ("0.01x", 0.01, "enormous"),
    ("0.1x",  0.1,  "very large"),
    ("1x",    1.0,  "architectural"),
    ("10x",   10.0, "large building"),
    ("100x",  100.0, "indoor room"),
]
def pick_scale(parent=None, default: float = 100.0) -> Optional[float]: ...

# flame/camera_match_hook.py — current state (line ~2730, ~2779, ~2790, ~2797)
_LADDER_MENU_STOPS = (0.01, 0.1, 1.0, 10.0, 100.0)

def _export_camera_to_blender_with_picker(selection):
    from scale_picker_dialog import pick_scale
    scale = pick_scale(default=100.0)            # ← flip to 1000.0
    if scale is None: return
    _export_camera_to_blender(selection, flame_to_blender_scale=scale)

def _export_camera_from_action_selection_with_picker(selection):
    from scale_picker_dialog import pick_scale
    scale = pick_scale(default=100.0)            # ← flip to 1000.0
    ...

def _export_camera_pipeline(action, cam, label, *, flame_to_blender_scale=100.0):  # ← flip default to 1000.0
    ...

# Other call-site defaults to flip from 100.0 → 1000.0:
# - _export_camera_to_blender(selection, *, flame_to_blender_scale=100.0)
# - _export_camera_from_action_selection(selection, *, flame_to_blender_scale=100.0)
# (See lines 2700, 2782, 2793 for the chain.)

# Unicode superscripts for the multiplier suffix (semantic-label format):
# ×10⁰ ×10¹ ×10² ×10³ ×10⁴ ×10⁵ ×10⁶
# Code points: × (×) ⁰ ¹ ² ³ ⁴ ⁵ ⁶

# Test files referencing the old 5-stop set:
# tests/test_bake_camera.py:286-296   — ladder constant + parametrize
# tests/test_blender_roundtrip.py:231-232  — _LADDER constant
# tests/test_scale_picker_dialog.py:49,70  — button label list assertion
# tests/test_hook_export_camera_to_blender.py:268,292,589  — parametrize + _LADDER_MENU_STOPS assertion
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Extend bake-side ladder + validator + camera_io/fbx_ascii docstrings</name>
  <files>tools/blender/bake_camera.py, forge_flame/camera_io.py, forge_flame/fbx_ascii.py, tests/test_bake_camera.py, tests/test_blender_roundtrip.py</files>
  <action>
Widen the bake-side ladder to the 7-stop canonical set while preserving
back-compat for the deprecated 2 stops.

(1) **tools/blender/bake_camera.py (~line 200):** replace the single ladder
constant with two:
```
_FLAME_TO_BLENDER_SCALE_LADDER = (1.0, 10.0, 100.0, 1000.0, 10000.0, 100000.0, 1000000.0)
_DEPRECATED_FLAME_TO_BLENDER_SCALE_LADDER = (0.01, 0.1)
```
Comment terse — one-line each: "canonical 7-stop log10 ladder; default 1000.0
(Interior)" and "deprecated stops kept valid bake-side for back-compat with
already-baked .blend files (260501-dpa); never offered by the dialog."

(2) **`_validate_flame_to_blender_scale` (~line 309):** widen the membership
check to the union:
```
allowed = _FLAME_TO_BLENDER_SCALE_LADDER + _DEPRECATED_FLAME_TO_BLENDER_SCALE_LADDER
if v not in allowed:
    ladder_str = "{" + ", ".join(str(x) for x in _FLAME_TO_BLENDER_SCALE_LADDER) + "}"
    deprecated_str = "{" + ", ".join(str(x) for x in _DEPRECATED_FLAME_TO_BLENDER_SCALE_LADDER) + "}"
    raise SystemExit(
        f"flame_to_blender_scale={value} is not on the allowed ladder "
        f"{ladder_str} (or deprecated stops {deprecated_str})")
return v
```
The error message lists canonical stops first, deprecated parenthetically — gives
the artist the right answer if they hit the validator with a typo.

(3) **forge_flame/camera_io.py (~line 131):** update the docstring's allowed-set
reference to read:
```
Allowed values are restricted to the discrete log10 ladder
``{1.0, 10.0, 100.0, 1000.0, 10000.0, 100000.0, 1000000.0}`` (canonical) plus
``{0.01, 0.1}`` (deprecated, kept valid bake-side for back-compat).
```

(4) **forge_flame/fbx_ascii.py (~line 1087):** same update to the matching
docstring block (allowed values list).

(5) **tests/test_bake_camera.py (~line 286-310):** update `TestFlameToBlenderScaleLadder`:
- `test_ladder_constant_shape`: assert the new 7-tuple `(1.0, 10.0, 100.0, 1000.0, 10000.0, 100000.0, 1000000.0)`.
- ADD `test_deprecated_ladder_constant_shape`: assert `(0.01, 0.1)`.
- `test_validator_accepts_each_ladder_value` parametrize: `[1.0, 10.0, 100.0, 1000.0, 10000.0, 100000.0, 1000000.0]` (7 cases, was 5).
- ADD `test_validator_accepts_each_deprecated_ladder_value` parametrize: `[0.01, 0.1]` (2 cases) — proves deprecated stops still validate cleanly.
- `test_validator_rejects_off_ladder` parametrize: keep `[0.5, 2.0, 0.05, -1.0, 0.0]`. REMOVE `1000.0` from the rejection set (it's now valid). ADD `[5.0, 50.0, 500.0, 9999.99]` so the rejection coverage exercises the gaps in the new wider ladder.

(6) **tests/test_blender_roundtrip.py (~line 231-232):** update `_LADDER`:
```
_LADDER = (1.0, 10.0, 100.0, 1000.0, 10000.0, 100000.0, 1000000.0)
_DEPRECATED_LADDER = (0.01, 0.1)
```
Keep the existing `TestScaleLadderRoundTrip` parametrize using `_LADDER` (now 7 cases per existing test method × parametrize). ADD a sibling parametrize over `_DEPRECATED_LADDER` for `test_static_camera_round_trip_at_each_ladder_value` only (the central correctness property — proves deprecated stops still round-trip bit-exact). Animated parametrize stays on the canonical 7 only — deprecated coverage is just the central guard.

Run: `pytest -p no:pytest-blender tests/test_bake_camera.py tests/test_blender_roundtrip.py -x` — all green.

Atomic commit: `feat(quick-260501-rus): extend bake-side ladder to 7-stop canonical set + keep 2 deprecated stops valid for back-compat`
  </action>
  <verify>
    <automated>pytest -p no:pytest-blender tests/test_bake_camera.py tests/test_blender_roundtrip.py -x</automated>
  </verify>
  <done>
    - _FLAME_TO_BLENDER_SCALE_LADDER == (1.0, 10.0, 100.0, 1000.0, 10000.0, 100000.0, 1000000.0)
    - _DEPRECATED_FLAME_TO_BLENDER_SCALE_LADDER == (0.01, 0.1)
    - _validate_flame_to_blender_scale accepts every value in either tuple, rejects values in neither
    - Round-trip parity holds at all 7 canonical stops AND both deprecated stops (positions bit-exact)
    - camera_io.py + fbx_ascii.py docstring blocks reference the new canonical set + deprecated note
    - test_bake_camera.py + test_blender_roundtrip.py green; rejection coverage no longer includes 1000.0
  </done>
</task>

<task type="auto">
  <name>Task 2: Re-skin scale_picker_dialog with 7 semantic buttons + unicode superscripts + Interior default</name>
  <files>flame/scale_picker_dialog.py, tests/test_scale_picker_dialog.py</files>
  <action>
Replace the dialog's 5-stop ladder with the 7-stop semantic ladder and flip
the default to Interior. Deprecated stops are NEVER offered.

(1) **flame/scale_picker_dialog.py (~line 35):** replace `_LADDER_STOPS` with
the semantic 7-stop set. Use unicode superscript code points (NOT escape
sequences in source; literal characters for readability) so the button label
renders correctly under PySide6:

```
_LADDER_STOPS = [
    # (semantic_label, multiplier_suffix, scale_value, physical_distance_subtitle)
    ("Landscape",  "×10⁰", 1.0,       "~1.8 km"),
    ("Outdoor",    "×10¹", 10.0,      "~180 m"),
    ("Soundstage", "×10²", 100.0,     "~18 m"),
    ("Interior",   "×10³", 1000.0,    "~1.8 m"),
    ("Tabletop",   "×10⁴", 10000.0,   "~18 cm"),
    ("Product",    "×10⁵", 100000.0,  "~1.8 cm"),
    ("Macro",      "×10⁶", 1000000.0, "~1.8 mm"),
]
```
Distances are rounded for the 4096-wide-plate / ~97° hfov reference case the
user locked in the planning context table.

(2) **`pick_scale` signature:** flip the default kwarg:
```
def pick_scale(parent=None, default: float = 1000.0) -> Optional[float]:
```

(3) **Button construction loop (~line 126):** widen for the new tuple shape and
the new label format `{Semantic} · {×10ⁿ}`:
```
btn = QPushButton(f"{label} · {suffix}\n{sub}")
```
Bump `setMinimumWidth` to `108` (was 96) — 7 buttons need a touch more breathing
room and the longer "Soundstage · ×10²" label needs the extra width. Keep
`setMinimumHeight=56`.

Bump dialog `setMinimumWidth` to `820` (was 560) — 7 buttons × 108 + 6 spacings
× 8 + 32 margins ≈ 836; round down to 820 and let the layout breathe.

(4) **Subtitle text (~line 102):** update for the new default:
```
"Divisor applied to camera position when baking to Blender. "
"Interior (×10³) is the studio default — room-scale interiors and human-scale CG."
```

(5) **Default-button branch (~line 133-141):** logic is `if scale_value == default`
— unchanged structurally, but with `default=1000.0` the highlight now lands on
Interior. Verify with the Test 2 update below.

(6) **tests/test_scale_picker_dialog.py:**

- **Test 1 (`test_pick_scale_constructs_dialog_with_5_scale_buttons`):**
  - Rename → `test_pick_scale_constructs_dialog_with_7_scale_buttons`.
  - Update assertion: 7 button labels, each starting with the semantic prefix:
    ```
    expected_prefixes = ["Landscape", "Outdoor", "Soundstage", "Interior",
                         "Tabletop", "Product", "Macro"]
    btn_labels = [b.text().split("\n", 1)[0] for b in dialog.findChildren(QPushButton)]
    scale_labels = [l for l in btn_labels if l != "Cancel"]
    # Each label is "{Semantic} · ×10ⁿ" — assert prefix-match for stability:
    for prefix, label in zip(expected_prefixes, scale_labels):
        assert label.startswith(prefix + " · ×10"), (prefix, label)
    assert len(scale_labels) == 7
    ```

- **Test 2 (`test_pick_scale_default_100_highlights_100x_button`):**
  - Rename → `test_pick_scale_default_1000_highlights_interior_button`.
  - Call `pick_scale(default=1000.0)` (was 100.0).
  - Assert the primary button's first line starts with "Interior · ×10³".
  - Assert non-Interior buttons are NOT marked primary.

- **Test 3 (parametrized `test_pick_scale_returns_scale_on_button_click`):**
  - Replace the 5-tuple parametrize with the 7-tuple semantic parametrize:
    ```
    @pytest.mark.parametrize("label_prefix,expected_scale", [
        ("Landscape",  1.0),
        ("Outdoor",    10.0),
        ("Soundstage", 100.0),
        ("Interior",   1000.0),
        ("Tabletop",   10000.0),
        ("Product",    100000.0),
        ("Macro",      1000000.0),
    ])
    ```
  - Trampoline match condition: `if first_line.startswith(label_prefix + " · ×10")` — semantic-prefix match (the previous "exact equality" guarded against 1x-vs-10x prefix collision; semantic labels have no such collision so prefix-match is fine).
  - Calls `pick_scale(default=1000.0)`.

- **Test 4 (`test_pick_scale_cancel_returns_none`):** update `pick_scale(default=1000.0)`.
- **Test 5 (`test_pick_scale_cancel_button_returns_none`):** same default flip.
- **Test 6 (`test_pick_scale_unknown_default_no_primary`):** keep `default=42.0` — test logic unchanged.

Run: `QT_QPA_PLATFORM=offscreen pytest -p no:pytest-blender tests/test_scale_picker_dialog.py -x` — all green (10 cases unchanged in count; just relabeled + parametrize widened from 5 to 7 in Test 3 → +2 collected items net, was 10, now 12).

Atomic commit: `feat(quick-260501-rus): re-skin scale picker dialog with 7 semantic stops + Interior default`
  </action>
  <verify>
    <automated>QT_QPA_PLATFORM=offscreen pytest -p no:pytest-blender tests/test_scale_picker_dialog.py -x</automated>
  </verify>
  <done>
    - _LADDER_STOPS has 7 entries (Landscape...Macro) with unicode superscripts ×10⁰..×10⁶
    - pick_scale(default=1000.0) highlights Interior as primary + setDefault(True)
    - Each button click returns its corresponding scale (1.0, 10.0, 100.0, 1000.0, 10000.0, 100000.0, 1000000.0)
    - Deprecated stops {0.01, 0.1} NEVER appear in the dialog
    - Test module green: 12 collected items (was 10; +2 for the wider parametrize)
  </done>
</task>

<task type="auto">
  <name>Task 3: Flip hook defaults 100.0 → 1000.0 + extend _LADDER_MENU_STOPS to 7-stop set</name>
  <files>flame/camera_match_hook.py, tests/test_hook_export_camera_to_blender.py</files>
  <action>
Flip every hardcoded `flame_to_blender_scale=100.0` default in the hook to
`1000.0` (Interior — the new studio sweet spot), and extend `_LADDER_MENU_STOPS`
to the 7-stop canonical set. The factory + dialog wrappers stay structurally
identical; only the constants and defaults change.

(1) **flame/camera_match_hook.py:**

Change 1 — `_LADDER_MENU_STOPS` (~line 2730):
```
_LADDER_MENU_STOPS = (1.0, 10.0, 100.0, 1000.0, 10000.0, 100000.0, 1000000.0)
```
Update the docstring block above it to read "Discrete log10 7-stop ladder ...
Default-entry hardcode of 1000.0 is the studio-default convenience entry
(Interior — per quick 260501-rus); these are the additional artist-pickable
stops surfaced via _make_export_callback (per quick 260501-i31)."

Change 2 — picker wrapper defaults (~line 2779, ~line 2790):
```
def _export_camera_to_blender_with_picker(selection):
    ...
    scale = pick_scale(default=1000.0)   # was 100.0
    ...

def _export_camera_from_action_selection_with_picker(selection):
    ...
    scale = pick_scale(default=1000.0)   # was 100.0
    ...
```
Also update the docstring text that today says "Studio default is 100.0" → "Studio default is 1000.0 — the dialog's 'Interior · ×10³' button is highlighted as primary so the artist can hit Enter for the common case."

Change 3 — `_export_camera_pipeline` kwarg default (~line 2797):
```
def _export_camera_pipeline(action, cam, label, *, flame_to_blender_scale=1000.0):
```
And the matching docstring sentence that names "100.0 is the studio-default convenience entry (per the 260501-em8 pivot)" → "1000.0 is the studio-default convenience entry (Interior — per the 260501-rus flip; supersedes 260501-em8's 100.0 Soundstage default)."

Change 4 — find every other call-site default in this file matching the
pattern `flame_to_blender_scale=100.0` and flip to `1000.0`. Per the interfaces
block, the chain is at lines ~2700, ~2782, ~2793. Run a grep first to be safe:
```
grep -n "flame_to_blender_scale=100\\.0" flame/camera_match_hook.py
```
Every match must flip to `1000.0`. Spot-check that the `scale=1000.0`
viewport-nav hack at the `blender_bridge.run_bake` call site (separate `scale=`
kwarg, NOT `flame_to_blender_scale=`) is **untouched** — it's a completely
separate divisor and the canary test G in test_hook_export_camera_to_blender.py
asserts `source.count("scale=1000.0") == 2` (preserve byte-identity).

(2) **tests/test_hook_export_camera_to_blender.py:**

Change A — `TestLadderMenuFactory::test_factory_dispatches_per_stop_action_scope`
(~line 268): widen parametrize to 7 cases:
```
@pytest.mark.parametrize("scale", [1.0, 10.0, 100.0, 1000.0, 10000.0, 100000.0, 1000000.0])
```

Change B — `test_factory_dispatches_per_stop_camera_scope` (~line 292): same
widening to 7 cases.

Change C — `test_factory_still_present` (~line 589): assert the new 7-tuple:
```
assert _hook_module._LADDER_MENU_STOPS == (1.0, 10.0, 100.0, 1000.0, 10000.0, 100000.0, 1000000.0)
```

Change D — find every test in this file that asserts the picker-wrapper
default is 100.0 (e.g. tests that monkeypatch `pick_scale` and assert the
captured `default` kwarg equals 100.0) and flip to 1000.0. Grep first:
```
grep -n "default=100\\.0\\|default == 100\\.0\\|flame_to_blender_scale=100\\.0\\|flame_to_blender_scale == 100\\.0" tests/test_hook_export_camera_to_blender.py
```
Every match in test code that asserts the **picker default** or **studio
default** must flip to 1000.0. Be careful: parametrize cases that exercise
"100.0 is one of the valid ladder stops" should STAY (100.0 is still a
canonical stop — Soundstage). Only the **default value** assertions flip.

If unsure for a given match, the rule is: it's a default-value assertion if the
test name or comment mentions "studio default", "default-button", "Enter
parity", or the test passes 100.0 as the expected ONLY value (not as one of
several parametrized cases). Otherwise leave it.

Closure-binding tests H + I (parametrize over scale values): widen the
parametrize tuple from 5 to 7 stops.

Change E — Test G (viewport-nav canary): UNCHANGED — `scale=1000.0` is the
unrelated `blender_bridge.run_bake` divisor, not `flame_to_blender_scale`.
Asserts `source.count("scale=1000.0") == 2`. Verify this test still passes
unchanged after Change 4 above.

Run: `pytest -p no:pytest-blender tests/test_hook_export_camera_to_blender.py -x` — all green.

Atomic commit: `feat(quick-260501-rus): flip hook studio default 100.0 (Soundstage) → 1000.0 (Interior) + extend ladder menu stops to 7-stop canonical set`
  </action>
  <verify>
    <automated>pytest -p no:pytest-blender tests/test_hook_export_camera_to_blender.py -x</automated>
  </verify>
  <done>
    - _LADDER_MENU_STOPS == (1.0, 10.0, 100.0, 1000.0, 10000.0, 100000.0, 1000000.0)
    - Every flame_to_blender_scale=100.0 default in flame/camera_match_hook.py is now 1000.0
    - pick_scale(default=...) call sites pass 1000.0 (was 100.0)
    - Viewport-nav scale=1000.0 hack at run_bake call site UNCHANGED (canary test G unchanged)
    - Test parametrize widened from 5 stops to 7 stops in factory dispatch + closure-binding
    - test_factory_still_present asserts the new 7-tuple
  </done>
</task>

<task type="auto">
  <name>Task 4: Update queued UAT todo + run full test suite</name>
  <files>.planning/todos/pending/2026-05-02-flame-blender-scale-roundtrip-uat.md</files>
  <action>
Update the queued UAT todo to match the new ladder. Three narrative changes
+ one structural addition.

(1) **UAT 1 narrative (~line 42-52):** keep flow identical (default-button
parity, Enter triggers default), but update the expected outcome wording:
- "Dialog opens with `100x` highlighted as default" → "Dialog opens with `Interior · ×10³` highlighted as default"
- "Hit **Enter** (or click `100x` explicitly) → Blender opens with the camera at human-room scale (~8m back for a 1080p plate, ~76m for the 2160×4096 plate from today)" → "Hit **Enter** (or click `Interior · ×10³` explicitly) → Blender opens with the camera at room-scale (~1.8 m back for the reference 4096-wide plate; the studio sweet spot for human-scale interiors)"

(2) **UAT 2 narrative (~line 54-58):** today reads:
> "Same flow as UAT 1, but pick `1x` from the dialog. Camera should land at architectural scale (~833m back). Send-to-Flame should still return to original coords."
The "1x = ~833m architectural" wording is wrong under the new ladder. Replace with:
> "Same flow as UAT 1, but pick `Landscape · ×10⁰` from the dialog. Camera should land at landscape scale (~1.8 km back for the 4096-wide reference plate). Send-to-Flame should still return to original Flame coords. This proves the symmetry holds at a value other than the studio default — different scale values exercise the same code path with different numbers, so a bug in property-stamping logic might only surface at non-Interior values."

(3) **UAT 3 narrative (~line 60-68):** "Export at scale=100 (default dialog pick)" → "Export at scale=1000 (default dialog pick — Interior)".

(4) **UAT 5 narrative (~line 77-83):** "Click `100x` explicitly with the mouse" → "Click `Interior · ×10³` explicitly with the mouse". Diff-check unchanged structurally.

(5) **UAT 6 narrative (~line 85-94):** "no `@ Nx` siblings" wording unchanged
(it was already revert-aware after knl). No edit needed.

(6) **NEW — UAT 7: Deprecated-stop back-compat:** append a new UAT item before
the "## Resume signal" section:
```
### UAT 7: Deprecated-stop back-compat (already-baked .blend round-trip)

The 260501-rus extension widened the canonical ladder to 7 semantic stops
{1, 10, 100, 1000, 10000, 100000, 1000000} but kept {0.01, 0.1} as
deprecated-but-valid bake-side inputs so .blend files baked under the old
contract still round-trip cleanly.

1. Find a .blend baked before today (commit predates 260501-rus) — e.g.
   one of yesterday's bakes at scale=100 OR a hypothetical scale=0.1 bake
   from 260501-dpa testing. The `forge_bake_scale` custom property on the
   Blender camera names the original divisor.
2. Open it in Blender, run "Send to Flame" (forge_sender addon)
3. Verify: the returned camera lands at the original Flame coords. NO
   error about "scale not on the allowed ladder" — extract reads the
   stamped property and applies the inverse without re-validating against
   the canonical set.

**FAIL CRITERIA:** Send-to-Flame errors with "0.01 not on ladder" or
"0.1 not on ladder" — would mean the deprecated-stop tolerance broke and
existing artist .blend files are now stranded.

(NOTE: this UAT can be deferred or skipped if the studio has no live .blend
files at deprecated scales. The unit-test parity coverage for deprecated
stops in tests/test_blender_roundtrip.py is sufficient automated guard.)
```

(7) **`related_commits` frontmatter (line 12-16):** append a placeholder entry:
```
  - <pending — quick 260501-rus commits land before this UAT runs>
```
Don't list specific hashes — they don't exist yet.

(8) **`status` frontmatter:** stays `pending`.

Run the FULL test suite as the final verify step:
```
pytest -p no:pytest-blender tests/ -q
```
Expected: 522 baseline + Task 1 net (deprecated-stop coverage adds parametrize cases — exact count depends on parametrize shape, ballpark +6 to +14) + Task 2 net (parametrize widened 5→7 → +2) + Task 3 net (factory dispatch widened 5→7 in two places + closure-binding 5→7 → +6 to +10). Final count ~536-548 passed / 0 failed / 2 skipped — exact number is whatever the parametrize math produces, just confirm 0 failed and the suite is green.

Atomic commit: `docs(quick-260501-rus): update UAT todo for 7-stop semantic ladder + Interior default + deprecated-stop back-compat UAT`
  </action>
  <verify>
    <automated>pytest -p no:pytest-blender tests/ -q</automated>
  </verify>
  <done>
    - UAT 1, 2, 3, 5 narratives reference the new semantic labels + Interior default + ~1.8 km/~1.8 m physical-distance numbers
    - UAT 2 no longer says "1x = ~833m architectural" — replaced with "Landscape · ×10⁰ → ~1.8 km"
    - NEW UAT 7 covers deprecated-stop back-compat for already-baked .blend files
    - Full pytest suite green: 0 failed, 2 skipped (the pytest-blender skips), passed-count up from 522 baseline by parametrize-widening delta
    - related_commits frontmatter notes pending 260501-rus commits
  </done>
</task>

</tasks>

<verification>
After all 4 tasks land, the following must hold:

1. **Bake-side ladder is the union of canonical + deprecated:**
   - `bake_camera._FLAME_TO_BLENDER_SCALE_LADDER == (1.0, 10.0, 100.0, 1000.0, 10000.0, 100000.0, 1000000.0)`
   - `bake_camera._DEPRECATED_FLAME_TO_BLENDER_SCALE_LADDER == (0.01, 0.1)`
   - Validator accepts every value in either tuple; rejects values in neither.

2. **Dialog presents 7 semantic buttons; deprecated stops never offered:**
   - Button label format: `{Semantic} · ×10ⁿ\n{distance}` (semantic prefix on top, physical-distance subtitle below).
   - Order: Landscape → Outdoor → Soundstage → Interior → Tabletop → Product → Macro.
   - Default is Interior (1000.0) — `setDefault(True)` + `objectName="primary"` + Enter shortcut.

3. **Hook studio default flipped 100.0 → 1000.0 in every default-call-site:**
   - Picker wrappers pass `default=1000.0` to `pick_scale`.
   - `_export_camera_pipeline` kwarg default is 1000.0.
   - Every helper kwarg default chain is 1000.0.
   - `_LADDER_MENU_STOPS` is the 7-stop canonical set.
   - Viewport-nav `scale=1000.0` at `run_bake` call site is byte-identical (separate divisor; canary test G asserts unchanged).

4. **Round-trip parity holds at all 7 canonical stops + both deprecated stops:**
   - Position deltas at IEEE-754 floor (bit-exact in numpy stand-in).
   - Rotation deltas at float-epsilon (~1e-15).

5. **JSON contract field semantics unchanged:**
   - `flame_to_blender_scale` is still a raw float, written via `is not None` semantics.
   - Only the canonical stop set + default + UI labels changed; field shape and data flow are identical.

6. **UAT todo wording matches the new ladder:**
   - "1x = ~833m architectural" wording purged.
   - "Landscape · ×10⁰ → ~1.8 km" replaces it.
   - NEW UAT 7 covers deprecated-stop back-compat.

7. **Full pytest suite green:**
   - `pytest -p no:pytest-blender tests/` → 0 failed, 2 skipped.
   - Net new collected items: parametrize widenings 5→7 in multiple files, plus deprecated-stop parametrize coverage.
</verification>

<success_criteria>
- 4 atomic commits land in order, each green on its own (Task 1 → Task 2 → Task 3 → Task 4).
- Full pytest suite green at every commit boundary.
- The dialog renders 7 buttons with semantic labels + unicode superscripts; Interior highlighted as default.
- Bake validator accepts every value in {0.01, 0.1, 1, 10, 100, 1000, 10000, 100000, 1000000}; rejects everything else with the canonical+deprecated set in the error message.
- Hook studio default at every call site is 1000.0; viewport-nav 1000.0 hack at `run_bake` is byte-identical.
- Queued UAT todo updated; deprecated-stop UAT 7 added.
- No edits to the JSON-contract emit shape (`fbx_to_v5_json` `flame_to_blender_scale` kwarg behavior, `is not None` semantics).
- No regressions in tests for: viewport-nav canary G, pick_scale ESC/cancel, factory-still-present, picker-forwards-on-pick, picker-skips-on-cancel.
</success_criteria>

<output>
After completion, create `.planning/quick/260501-rus-extend-flame-blender-scale-ladder-from-5/260501-rus-SUMMARY.md`
with:
- Verdict (SHIPPED / blocked / partial)
- 4 commit hashes + one-line descriptions
- Files modified count + lines delta per file
- Round-trip parity table at the 7 new canonical stops (position max |delta|, rotation max |delta|)
- Deprecated-stop parity table at {0.01, 0.1} (proves back-compat held)
- Out of scope (deliberate): documentation for artists explaining the 7 semantic scales, persistent last-used preference, calibrated reference-distance UI (separate phase)
- Manual UAT pointer to the updated `2026-05-02-flame-blender-scale-roundtrip-uat.md` (now 7 UAT items, not 6)
</output>
