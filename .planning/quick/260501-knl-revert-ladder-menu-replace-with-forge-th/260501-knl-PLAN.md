---
phase: quick-260501-knl
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - flame/scale_picker_dialog.py
  - flame/camera_match_hook.py
  - tests/test_hook_export_camera_to_blender.py
  - tests/test_scale_picker_dialog.py
autonomous: true
requirements:
  - DIALOG-MODULE-01     # New module flame/scale_picker_dialog.py exporting `pick_scale(parent=None, default=100.0) -> Optional[float]`, forge-themed QDialog with 5 buttons (0.01x .. 100x), default highlights `default`-matching button, ESC/cancel returns None
  - DIALOG-WIRING-02     # Two thin wrappers in camera_match_hook.py: `_export_camera_to_blender_with_picker` and `_export_camera_from_action_selection_with_picker`. Each calls `pick_scale(default=100.0)`; on None returns silently; on float forwards to the underlying export entry with `flame_to_blender_scale=scale`.
  - REVERT-MENU-03       # `get_batch_custom_ui_actions()` "Camera" subgroup goes back to 2 entries (Open Camera Calibrator + 1 Export Camera to Blender, scoped to Action via _scope_batch_action). The default entry's `execute` is `_export_camera_to_blender_with_picker`, NOT `_export_camera_to_blender`.
  - REVERT-MENU-04       # `get_action_custom_ui_actions()` root group goes back to 1 entry. The single entry's `execute` is `_export_camera_from_action_selection_with_picker`.
  - PRESERVE-FACTORY-05  # `_LADDER_MENU_STOPS` and `_make_export_callback(scale, *, camera_scope=False)` STAY in camera_match_hook.py (the dialog's button click handlers can use the factory to produce the underlying callable).
  - PRESERVE-PIPELINE-06 # `_export_camera_pipeline`, `_export_camera_to_blender`, `_export_camera_from_action_selection` keep their keyword-only `flame_to_blender_scale: float = 100.0` parameter (the kwarg plumbing from i31 stays — only the menu shape reverts).
  - PRESERVE-CANARY-07   # `blender_bridge.run_bake(..., scale=1000.0, ...)` at line ~2979 stays byte-identical; `grep -c "scale=1000.0" flame/camera_match_hook.py` returns 2 unchanged.
  - TESTS-SURGICAL-08    # Existing TestLadderMenuFactory test class is rewritten in place: shape tests change to "1 Action-scoped entry per surface"; default-entry tests change to "wrapper calls pick_scale; on 100.0 forwards to _export_camera_to_blender(flame_to_blender_scale=100.0); on None no export"; per-stop dispatch tests + factory routing tests + signature test + canary test STAY.
  - TESTS-DIALOG-09      # New test module `tests/test_scale_picker_dialog.py` covers: 5 expected button labels, default=100.0 highlights "100x" button as default, button click → dialog accepts with that scale, ESC/reject → returns None.

must_haves:
  truths:
    - "After this plan ships, get_batch_custom_ui_actions()'s 'Camera' subgroup contains exactly 2 entries: 'Open Camera Calibrator' (clip-scoped) + 'Export Camera to Blender' (Action-scoped), and the Action-scoped entry's execute callable is _export_camera_to_blender_with_picker — i.e. ONE Action-scoped menu entry per surface, NOT 6"
    - "After this plan ships, get_action_custom_ui_actions()'s root group contains exactly 1 entry: 'Export Camera to Blender', whose execute callable is _export_camera_from_action_selection_with_picker — i.e. ONE Action-scoped menu entry per surface, NOT 6"
    - "pick_scale(parent=None, default=100.0) returns the scale value (float) when a button is clicked, and None when the dialog is rejected (ESC, X, cancel)"
    - "pick_scale(default=100.0) builds a QDialog whose '100x' button is the dialog's default button (responds to Enter; visually marked as primary per setDefault(True) + objectName='primary' per the existing _pick_camera precedent)"
    - "ESC / dialog rejection returns None and triggers NO export call (verified by both the dialog's unit test asserting None return AND the wrapper's unit test asserting underlying export is not invoked)"
    - "The literal 'scale=1000.0' appears exactly 2 times in flame/camera_match_hook.py — byte-identical to the i31 baseline; viewport-nav CLI arg untouched"
    - "scale_picker_dialog.py applies the forge palette per memory/forge_ui_style.md: dialog bg #282c34, FORGE orange #E87E24 on default button, window title 'FORGE — Export Camera to Blender — Scale', dialog margins (16,14,16,14); style sheet imported from camera_match_hook._FORGE_SS (do NOT redefine the palette in two places)"
    - "_LADDER_MENU_STOPS and _make_export_callback factory both still exist in flame/camera_match_hook.py at module scope — the per-stop dispatch tests still pass against them"
    - "All three signatures (_export_camera_pipeline, _export_camera_to_blender, _export_camera_from_action_selection) still declare flame_to_blender_scale as KEYWORD_ONLY with default 100.0 — the i31 plumbing is preserved end-to-end"
  artifacts:
    - path: "flame/scale_picker_dialog.py"
      provides: "pick_scale(parent=None, default=100.0) -> Optional[float] — modal forge-themed PySide6 QDialog with 5 scale buttons; returns chosen scale or None"
      contains: "def pick_scale"
    - path: "flame/camera_match_hook.py"
      provides: "Two new thin wrappers (_export_camera_to_blender_with_picker, _export_camera_from_action_selection_with_picker); reverted menu registrations on both surfaces; preserved factory + pipeline kwarg plumbing"
      contains: "_export_camera_to_blender_with_picker"
    - path: "tests/test_hook_export_camera_to_blender.py"
      provides: "Surgical updates to TestLadderMenuFactory — menu shape tests now assert 1 entry per surface; default-entry tests now exercise the wrapper + mocked pick_scale; per-stop factory tests + canary + signature tests stay"
      contains: "_export_camera_to_blender_with_picker"
    - path: "tests/test_scale_picker_dialog.py"
      provides: "Headless PySide6 unit tests for pick_scale: button labels, default selection, click → returns scale, ESC → returns None"
      contains: "def test_pick_scale"
  key_links:
    - from: "flame/camera_match_hook.py::get_batch_custom_ui_actions"
      to: "flame/camera_match_hook.py::_export_camera_to_blender_with_picker"
      via: "execute field in 'Export Camera to Blender' dict (Action-scoped)"
      pattern: "_export_camera_to_blender_with_picker"
    - from: "flame/camera_match_hook.py::get_action_custom_ui_actions"
      to: "flame/camera_match_hook.py::_export_camera_from_action_selection_with_picker"
      via: "execute field in single root 'Export Camera to Blender' dict"
      pattern: "_export_camera_from_action_selection_with_picker"
    - from: "flame/camera_match_hook.py::_export_camera_to_blender_with_picker"
      to: "flame/scale_picker_dialog.py::pick_scale"
      via: "Lazy import inside the wrapper body (matches the lazy-import pattern used by _pick_camera at line ~2364)"
      pattern: "from .* import pick_scale|from scale_picker_dialog import|import scale_picker_dialog"
    - from: "flame/camera_match_hook.py::_export_camera_to_blender_with_picker"
      to: "flame/camera_match_hook.py::_export_camera_to_blender"
      via: "scale = pick_scale(default=100.0); if scale is None: return; _export_camera_to_blender(selection, flame_to_blender_scale=scale)"
      pattern: "_export_camera_to_blender\\(selection, flame_to_blender_scale="
    - from: "flame/scale_picker_dialog.py::pick_scale"
      to: "flame/camera_match_hook.py::_FORGE_SS"
      via: "from camera_match_hook import _FORGE_SS (lazy import inside pick_scale body to avoid module-load cycle)"
      pattern: "_FORGE_SS"
---

<objective>
Replace the 5-stop ladder right-click menu (added by quick 260501-i31, commit
6200771) with a SINGLE forge-themed PySide6 modal dialog. The artist gets ONE
menu entry per surface; clicking it opens a dialog with 5 scale buttons; picking
a button fires the export with that scale; ESC/cancel = no export.

Purpose: i31's flat-sibling ladder (6 entries per surface) bloats the
right-click menu. A single dialog gives the same 5 choices in a discoverable
forge-themed UI without polluting the menu surface. Default selection is
`100x` — the studio default that has shipped on every plate so far — so the
common case is one click + Enter.

Output:
- New module `flame/scale_picker_dialog.py` exporting
  `pick_scale(parent=None, default=100.0) -> Optional[float]`. Modal QDialog
  with 5 buttons (`0.01x` / `0.1x` / `1x` / `10x` / `100x` plus subtitles).
  Returns chosen scale on click, None on ESC/cancel.
- Two thin wrappers in `flame/camera_match_hook.py`
  (`_export_camera_to_blender_with_picker`,
  `_export_camera_from_action_selection_with_picker`) that call `pick_scale`
  and forward to the existing entry points with `flame_to_blender_scale=`.
- `get_batch_custom_ui_actions()` and `get_action_custom_ui_actions()` revert
  to the pre-i31 menu shape (1 entry per surface) but with the new wrapper
  callables.
- Surgical updates to `tests/test_hook_export_camera_to_blender.py`:
  shape tests change ladder→single-entry; default-entry tests cover the
  wrapper; per-stop factory tests + canary + signature test stay.
- New `tests/test_scale_picker_dialog.py` covering dialog construction +
  button-click + cancel behavior with a real headless QApplication.

What stays (do NOT touch — load-bearing carry-over from i31/em8/dpa):
- `forge_flame.fbx_ascii.fbx_to_v5_json(..., flame_to_blender_scale=...)`
  kwarg (commit 9265f86 — em8).
- `_export_camera_pipeline`, `_export_camera_to_blender`,
  `_export_camera_from_action_selection` keyword-only
  `flame_to_blender_scale: float = 100.0` parameter (commit 6200771 — i31).
- `_LADDER_MENU_STOPS = (0.01, 0.1, 1.0, 10.0, 100.0)` and
  `_make_export_callback(scale, *, camera_scope=False)` factory at module
  scope (commit 6200771). The dialog's button click handlers may use the
  factory to produce the per-stop callable; KEEP IT REGARDLESS — also
  defended by tests A/B/C/I from i31 which stay green.
- `blender_bridge.run_bake(..., scale=1000.0, ...)` viewport-nav CLI arg
  (line ~2979). Byte-identical: canary `grep -c "scale=1000.0"` returns 2.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@./CLAUDE.md
@.planning/STATE.md
@flame/camera_match_hook.py
@tests/test_hook_export_camera_to_blender.py
@.planning/quick/260501-i31-scale-ladder-right-click-menu-action-cam/260501-i31-PLAN.md
@.planning/quick/260501-i31-scale-ladder-right-click-menu-action-cam/260501-i31-SUMMARY.md

<forge_ui_style_quick_reference>
Reproduced from `~/.claude/.../memory/forge_ui_style.md` so the executor does
not need to re-read it. Reference implementation in this repo:
`flame/camera_match_hook.py::_FORGE_SS` (lines 271-308; module-level constant
hoisted in Plan 04.4-02). The dialog MUST `from camera_match_hook import
_FORGE_SS` and apply via `dialog.setStyleSheet(_FORGE_SS)` — NO new palette,
NO redefining colors. The single-source-of-truth rule from
`memory/forge_ui_style.md` is mandatory.

Palette (FYI; only used for inline overrides on the per-button styling that
_FORGE_SS does not cover):
- Dialog bg: `#282c34`; input bg: `#1e2028`; FORGE orange: `#E87E24` (hover
  `#f59035`); text primary `#ccc`; text dim `#888`; separator `#3a3f4f`;
  secondary button bg `#333`.

Layout conventions enforced by _FORGE_SS + the existing _pick_camera dialog
(lines 2352-2424 — the closest precedent for what we are building):
- Dialog margins: `(16, 14, 16, 14)`; vertical spacing 12px; row spacing 8px.
- Window title: `"FORGE — <Tool Name>"` (em dash). For this dialog use:
  `"FORGE — Export Camera to Blender — Scale"`.
- Header label: `"color: #E87E24; font-weight: bold; font-size: 14px;"` —
  primary header text inside the dialog body.
- Subtitle / dim labels: `"color: #888; font-size: 11px;"`.
- Primary button: `objectName="primary"` + `setDefault(True)`. The
  `QPushButton#primary` selector inside `_FORGE_SS` (line 301-304) handles
  the orange bg + white text + bold styling. So highlighting the default
  button = setting object name to "primary" + calling setDefault(True), NOT
  re-styling inline.
- Secondary buttons: default QPushButton selector (lines 297-300 of
  _FORGE_SS) — `#333` bg, `#ccc` text, `#555` border.
- HLine separator (`QFrame.HLine`, color `#3a3f4f`) between header section
  and button row, matching `_pick_camera`'s sep1/sep2 pattern.
</forge_ui_style_quick_reference>

<existing_pyside_precedents_in_hook>
Three existing PySide6 surfaces in flame/camera_match_hook.py to mirror:

1. **Module-level style sheet** (lines 271-308): `_FORGE_SS` constant —
   the canonical forge palette as a single CSS string. The dialog must
   import + apply this; do NOT redefine.

2. **_pick_camera** (lines 2352-2424): the closest-shape precedent. Lazy
   imports PySide6 inside the function body (so module load does not
   require PySide6 on the test path). Uses QVBoxLayout with margins
   (16,14,16,14), spacing 12; QLabel header in FORGE orange; QFrame.HLine
   separators; QHBoxLayout button row with cancel on left + primary on
   right; `setObjectName("primary")` + `setDefault(True)` on primary
   button. Returns None on dialog.exec() != Accepted. Mirror this shape
   for the scale picker (vertical layout: header, separator, button row,
   separator, cancel button).

3. **CameraMatchWindow** (lines 1222-1500-ish): bigger calibrator UI;
   uses `setStyleSheet(_FORGE_SS)` at line 1227. Header label inline
   styled. Less relevant — we want the small dialog precedent
   (_pick_camera), not the calibrator.

For the new module's PySide6 import strategy: do the lazy import inside
the function body, exactly like _pick_camera — that way
`tests/test_hook_export_camera_to_blender.py` can keep PySide6 stubbed and
the existing test infrastructure does not break.
</existing_pyside_precedents_in_hook>

<exact_insertion_points>
All line numbers from `flame/camera_match_hook.py` at HEAD (commit
`6200771ffe...`).

**Files to edit:**

A. NEW FILE — `flame/scale_picker_dialog.py` — see `<dialog_module_design>`
   below.

B. `flame/camera_match_hook.py`:

   - **Line 2630** — `def _export_camera_to_blender(selection, *, flame_to_blender_scale=100.0):` — DO NOT TOUCH the signature. STAYS.
   - **Line 2690** — `def _export_camera_from_action_selection(selection, *, flame_to_blender_scale=100.0):` — DO NOT TOUCH the signature. STAYS.
   - **Lines 2729-2762** — `_LADDER_MENU_STOPS` + `_make_export_callback` — STAYS UNCHANGED.
   - **Insert NEW wrappers** AFTER `_make_export_callback`'s closing line
     (around line 2762) and BEFORE `_export_camera_pipeline` (around line
     2768). See `<wrapper_design>` below.
   - **Lines 3078-3119** — `get_batch_custom_ui_actions()` "Camera" subgroup
     `actions` list. REVERT to 2 entries (Open Camera Calibrator + 1
     Export Camera to Blender). The Export entry's `execute` becomes
     `_export_camera_to_blender_with_picker`. DELETE all 5 ladder dicts
     (lines ~3089-3117 — the entire block from the "Quick 260501-i31:
     5 ladder-stop siblings" comment through the closing `}` of the
     `Export to Blender @ 100x` dict).
   - **Lines 3149-3189** — `get_action_custom_ui_actions()` root `actions`
     list. REVERT to 1 entry. The entry's `execute` becomes
     `_export_camera_from_action_selection_with_picker`. DELETE all 5
     ladder dicts (the entire "Quick 260501-i31" block + the 5 dicts).
   - **Line ~2979** — `blender_bridge.run_bake(..., scale=1000.0, ...)` —
     DO NOT TOUCH. Canary depends on this line being byte-identical.
     Confirm via `grep -c "scale=1000.0" flame/camera_match_hook.py` ==
     2 both before and after the edit.

C. `tests/test_hook_export_camera_to_blender.py`:

   - **Lines 416-444** — `test_batch_menu_shape` — REWRITE per
     `<test_surgery_E>` below.
   - **Lines 449-474** — `test_action_menu_shape` — REWRITE per
     `<test_surgery_F>` below.
   - **Lines 360-411** — `test_default_entry_still_uses_scale_100_action_scope`
     and `test_default_entry_still_uses_scale_100_camera_scope` — REWRITE
     to test the WRAPPERS (not the originals) per `<test_surgery_D>` below.
   - **Lines 276-355** — Tests A (per-stop Action), B (per-stop Camera),
     C (camera_scope routing) — STAY UNCHANGED. They test the factory,
     which still exists.
   - **Lines 479-492** — Test G (viewport-nav canary) — STAYS UNCHANGED.
     `scale=1000.0` count must remain 2.
   - **Lines 497-510** — Test H (no-new-PySide-widgets in factory) — STAYS
     UNCHANGED. The factory itself still does not introduce widgets;
     the new dialog lives in a separate module.
   - **Lines 515-540** — Test I (signature shape) — STAYS UNCHANGED. The
     three signatures still carry the kwarg.
   - **NEW** — at end of class, add 2 new tests for the wrappers per
     `<test_new_J_K>` below.

D. NEW FILE — `tests/test_scale_picker_dialog.py` — see `<dialog_test_module>`
   below.
</exact_insertion_points>

<dialog_module_design>
File: `flame/scale_picker_dialog.py`. Single function exported. Lazy
PySide6 import inside the function body (matches `_pick_camera` pattern
at line 2364). NO module-level Qt imports (so test files that stub PySide6
do not need to load this module's heavy imports until pick_scale is
actually called).

```python
"""Forge-themed scale picker dialog for the Flame -> Blender export menu.

Lives in flame/ alongside camera_match_hook.py because it is a UI surface
for that hook's right-click handlers. The hook's wrappers
(_export_camera_to_blender_with_picker,
_export_camera_from_action_selection_with_picker) call pick_scale() to
let the artist choose a flame_to_blender_scale before firing the export.

Why a separate module: keeps the hook's growing 3000+ LOC monolith from
gaining another 100 LOC of Qt scaffolding, and lets the dialog be
unit-tested with a real headless QApplication without dragging in the
hook's heavy stub apparatus (the hook's tests stub PySide6, so dialog
construction tests need their own module that imports PySide6 for real).

Forge UI style is mandatory per memory/forge_ui_style.md: this module
imports the canonical _FORGE_SS palette from camera_match_hook so the
dialog matches the calibrator + _pick_camera + forge_cv_align tools.
"""

from __future__ import annotations

from typing import Optional


_LADDER_STOPS = [
    # (label, scale_value, subtitle)
    ("0.01x", 0.01, "enormous"),
    ("0.1x",  0.1,  "very large"),
    ("1x",    1.0,  "architectural"),
    ("10x",   10.0, "large building"),
    ("100x",  100.0, "indoor room"),
]


def pick_scale(parent=None, default: float = 100.0) -> Optional[float]:
    """Modal forge-themed scale picker.

    Returns the chosen scale (one of 0.01, 0.1, 1.0, 10.0, 100.0) when
    the artist clicks a button. Returns None when the dialog is rejected
    (ESC, the X close box, or no choice made).

    `default` selects which button is the dialog's default (responds to
    Enter, visually highlighted as primary). Must match one of
    _LADDER_STOPS' scale values; otherwise no button is highlighted as
    default (still functional, just no Enter shortcut).

    The dialog applies the canonical forge palette via _FORGE_SS imported
    from camera_match_hook. Window title: 'FORGE — Export Camera to
    Blender — Scale'. Margins (16, 14, 16, 14), spacing 12 — matches
    _pick_camera's layout exactly.
    """
    # Lazy imports — same pattern as _pick_camera. Keeps this module
    # safe to import on test paths that stub PySide6.
    from PySide6.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout,
        QLabel, QPushButton, QFrame,
    )
    from PySide6.QtCore import Qt  # noqa: F401  — kept for future use

    # Import _FORGE_SS lazily too — avoids any import cycle in the
    # (unlikely) event camera_match_hook ever imports back from here.
    from camera_match_hook import _FORGE_SS

    dialog = QDialog(parent)
    dialog.setWindowTitle("FORGE — Export Camera to Blender — Scale")
    dialog.setMinimumWidth(560)
    dialog.setStyleSheet(_FORGE_SS)

    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(16, 14, 16, 14)
    layout.setSpacing(12)

    header = QLabel("Choose Scene Scale")
    header.setStyleSheet(
        "color: #E87E24; font-weight: bold; font-size: 14px;")
    layout.addWidget(header)

    subtitle = QLabel(
        "Divisor applied to camera position when baking to Blender. "
        "100x is the studio default (room-scale scenes).")
    subtitle.setStyleSheet("color: #888; font-size: 11px;")
    subtitle.setWordWrap(True)
    layout.addWidget(subtitle)

    sep1 = QFrame()
    sep1.setFrameShape(QFrame.HLine)
    sep1.setObjectName("sep")
    layout.addWidget(sep1)

    # Track the chosen scale via closure-captured mutable.
    chosen = {"value": None}

    def _make_click_handler(scale_value):
        def _handler():
            chosen["value"] = scale_value
            dialog.accept()
        return _handler

    btn_row = QHBoxLayout()
    btn_row.setSpacing(8)

    for label, scale_value, sub in _LADDER_STOPS:
        # Each button is a small vertical column: big label on top, small
        # subtitle below. Implemented as a single QPushButton with a
        # multi-line text — keeps the test surface simple (each button is
        # one widget the tests can locate by label match).
        btn = QPushButton(f"{label}\n{sub}")
        btn.setMinimumHeight(56)
        btn.setMinimumWidth(96)
        if scale_value == default:
            btn.setObjectName("primary")
            btn.setDefault(True)
            btn.setAutoDefault(True)
        btn.clicked.connect(_make_click_handler(scale_value))
        btn_row.addWidget(btn)

    layout.addLayout(btn_row)

    sep2 = QFrame()
    sep2.setFrameShape(QFrame.HLine)
    sep2.setObjectName("sep")
    layout.addWidget(sep2)

    cancel_row = QHBoxLayout()
    cancel_row.addStretch()
    cancel_btn = QPushButton("Cancel")
    cancel_btn.clicked.connect(dialog.reject)
    cancel_row.addWidget(cancel_btn)
    layout.addLayout(cancel_row)

    if dialog.exec() != QDialog.Accepted:
        return None
    return chosen["value"]
```

Notes:
- Each button's text is `f"{label}\n{sub}"` — a single QPushButton with
  newline-separated text. This keeps button location in tests trivial
  (`button.text().startswith("0.01x")`) without the complexity of
  building per-button QVBoxLayout sub-widgets.
- `chosen` is a single-element dict instead of `nonlocal` — avoids
  Python scoping subtleties inside nested functions and keeps the test
  surface uniform.
- `setMinimumWidth(560)` is wide enough to fit 5 buttons * 96px
  minimum + spacing within the 16,14,16,14 margins.
- Default button highlight: setObjectName("primary") triggers the
  `QPushButton#primary` styling block in _FORGE_SS (orange bg, white
  text, no border, bold). setDefault(True) makes Enter trigger that
  button. setAutoDefault(True) ensures it stays the default even if
  another button gets focus via Tab — important for the keyboard flow.
- ESC handling is automatic from QDialog: pressing ESC fires reject(),
  which makes exec() return Rejected, which makes pick_scale return
  None.
- The X close box at the window-manager level also fires reject().
</dialog_module_design>

<wrapper_design>
Insert into `flame/camera_match_hook.py` AFTER `_make_export_callback`'s
closing line (around line 2762) and BEFORE `_export_camera_pipeline`
(around line 2768). The wrappers are the new menu callables; they call
pick_scale and forward to the existing pipeline entry points.

```python
# Quick 260501-knl: replace i31's 5-sibling ladder menu with a single
# entry per surface that opens a forge-themed scale picker dialog.
# The wrappers below are the new menu callables; the dialog lives in
# flame/scale_picker_dialog.py.
#
# Lazy import of pick_scale: same pattern as _pick_camera's lazy
# PySide6 import — keeps the test path that stubs PySide6 from having
# to also stub the dialog module.
def _export_camera_to_blender_with_picker(selection):
    """Action-scope menu wrapper. Opens the scale picker; on a chosen
    scale, fires _export_camera_to_blender(selection, flame_to_blender_scale=scale).
    On ESC/cancel, returns silently with no export call.

    Studio default is 100.0 — the dialog's '100x' button is highlighted
    as primary so the artist can hit Enter for the common case.
    """
    from scale_picker_dialog import pick_scale
    scale = pick_scale(default=100.0)
    if scale is None:
        return  # ESC / cancel / X — no export
    _export_camera_to_blender(selection, flame_to_blender_scale=scale)


def _export_camera_from_action_selection_with_picker(selection):
    """Camera-scope menu wrapper. Opens the scale picker; on a chosen
    scale, fires _export_camera_from_action_selection(selection,
    flame_to_blender_scale=scale). On ESC/cancel, returns silently."""
    from scale_picker_dialog import pick_scale
    scale = pick_scale(default=100.0)
    if scale is None:
        return  # ESC / cancel / X — no export
    _export_camera_from_action_selection(
        selection, flame_to_blender_scale=scale)
```

Import path: when this hook runs inside Flame, both
`camera_match_hook.py` and `scale_picker_dialog.py` are deployed to
`/opt/Autodesk/shared/python/camera_match/` (per `install.sh`'s sibling
layout). Flame's hook loader puts that directory on sys.path, so a flat
`from scale_picker_dialog import pick_scale` works without package
prefix. Verify post-install with the install.sh check sequence in UAT.

If install.sh does NOT currently copy `flame/scale_picker_dialog.py` to
`/opt/Autodesk/shared/python/camera_match/`, the executor MUST update
install.sh to do so. (Read install.sh first to confirm.)
</wrapper_design>

<menu_shape_after_revert>

`get_batch_custom_ui_actions()` "Camera" subgroup `actions` list — REVERTED:

```python
"actions": [
    {
        "name": "Open Camera Calibrator",
        "isVisible": _scope_batch_clip,
        "execute": _launch_camera_match,
    },
    {
        "name": "Export Camera to Blender",
        "isVisible": _scope_batch_action,
        "execute": _export_camera_to_blender_with_picker,
    },
],
```

Two entries total (1 clip-scoped + 1 Action-scoped). The 5 ladder dicts
(lines ~3089-3117) and the entire "Quick 260501-i31:" comment block
get DELETED.

`get_action_custom_ui_actions()` root group `actions` list — REVERTED:

```python
"actions": [
    {
        "name": "Export Camera to Blender",
        "isVisible": _scope_action_camera,
        "execute": _export_camera_from_action_selection_with_picker,
    },
],
```

One entry total. The 5 ladder dicts (lines ~3158-3187) and the entire
"Quick 260501-i31:" comment block get DELETED.
</menu_shape_after_revert>

<test_surgery_D>
REWRITE `test_default_entry_still_uses_scale_100_action_scope` and
`test_default_entry_still_uses_scale_100_camera_scope` (lines 360-411)
to test the WRAPPERS instead of the originals. The originals are no
longer wired to the menu, so the regression they guard against has
moved up a level.

**`test_wrapper_action_scope_forwards_picked_scale`** (replaces lines 360-389):
```python
def test_wrapper_action_scope_forwards_picked_scale(self, monkeypatch):
    """When the picker returns 100.0, the wrapper invokes
    _export_camera_to_blender(selection, flame_to_blender_scale=100.0).
    Regression guard for the studio-default behavior surfaced via the
    new menu wiring."""
    calls = []

    def _recorder(selection, *, flame_to_blender_scale):
        calls.append((selection, flame_to_blender_scale))

    monkeypatch.setattr(
        _hook_module, "_export_camera_to_blender", _recorder)

    # Stub the scale_picker_dialog module since it is imported lazily.
    fake_picker = types.ModuleType("scale_picker_dialog")
    fake_picker.pick_scale = lambda parent=None, default=100.0: 100.0
    monkeypatch.setitem(sys.modules, "scale_picker_dialog", fake_picker)

    sentinel = object()
    _hook_module._export_camera_to_blender_with_picker(sentinel)

    assert len(calls) == 1
    assert calls[0][0] is sentinel
    assert calls[0][1] == 100.0
```

**`test_wrapper_action_scope_cancel_skips_export`** (NEW, paired with above):
```python
def test_wrapper_action_scope_cancel_skips_export(self, monkeypatch):
    """When the picker returns None (ESC/cancel), the wrapper invokes
    NO export. Defends the 'cancel = no-op' contract."""
    calls = []

    def _recorder(selection, *, flame_to_blender_scale):
        calls.append((selection, flame_to_blender_scale))

    monkeypatch.setattr(
        _hook_module, "_export_camera_to_blender", _recorder)

    fake_picker = types.ModuleType("scale_picker_dialog")
    fake_picker.pick_scale = lambda parent=None, default=100.0: None
    monkeypatch.setitem(sys.modules, "scale_picker_dialog", fake_picker)

    _hook_module._export_camera_to_blender_with_picker(object())

    assert calls == []
```

**`test_wrapper_camera_scope_forwards_picked_scale`** (replaces lines 391-411):
```python
def test_wrapper_camera_scope_forwards_picked_scale(self, monkeypatch):
    """Camera-scope wrapper: picker returns scale -> Camera-scope export
    fires with that scale."""
    calls = []

    def _recorder(selection, *, flame_to_blender_scale):
        calls.append((selection, flame_to_blender_scale))

    monkeypatch.setattr(
        _hook_module, "_export_camera_from_action_selection", _recorder)

    fake_picker = types.ModuleType("scale_picker_dialog")
    fake_picker.pick_scale = lambda parent=None, default=100.0: 10.0
    monkeypatch.setitem(sys.modules, "scale_picker_dialog", fake_picker)

    sentinel = object()
    _hook_module._export_camera_from_action_selection_with_picker(sentinel)

    assert len(calls) == 1
    assert calls[0][0] is sentinel
    assert calls[0][1] == 10.0
```

**`test_wrapper_camera_scope_cancel_skips_export`** (NEW, paired):
```python
def test_wrapper_camera_scope_cancel_skips_export(self, monkeypatch):
    """Camera-scope wrapper: picker returns None -> NO export."""
    calls = []

    def _recorder(selection, *, flame_to_blender_scale):
        calls.append((selection, flame_to_blender_scale))

    monkeypatch.setattr(
        _hook_module, "_export_camera_from_action_selection", _recorder)

    fake_picker = types.ModuleType("scale_picker_dialog")
    fake_picker.pick_scale = lambda parent=None, default=100.0: None
    monkeypatch.setitem(sys.modules, "scale_picker_dialog", fake_picker)

    _hook_module._export_camera_from_action_selection_with_picker(object())

    assert calls == []
```

Add `import types` to the test file's imports if not already present
(it IS already present — line 33).
</test_surgery_D>

<test_surgery_E>
REWRITE `test_batch_menu_shape` (lines 416-444) for the reverted shape.

```python
def test_batch_menu_shape(self):
    """get_batch_custom_ui_actions()'s 'Camera' subgroup has 2 dicts:
    1 clip-scoped 'Open Camera Calibrator' + 1 Action-scoped
    'Export Camera to Blender' (now wired to the picker wrapper).
    Reverted from i31's 7-entry shape per quick 260501-knl."""
    groups = _hook_module.get_batch_custom_ui_actions()
    camera_groups = [g for g in groups if g.get("name") == "Camera"]
    assert len(camera_groups) == 1, \
        f"Expected exactly 1 'Camera' group; got {len(camera_groups)}"

    actions = camera_groups[0]["actions"]
    assert len(actions) == 2, \
        f"Expected 2 entries in 'Camera' subgroup; got {len(actions)}"

    action_scoped = [
        a for a in actions
        if a.get("isVisible") is _hook_module._scope_batch_action
    ]
    assert len(action_scoped) == 1, \
        f"Expected 1 Action-scoped entry; got {len(action_scoped)}"

    assert action_scoped[0]["name"] == "Export Camera to Blender"
    assert action_scoped[0]["execute"] is \
        _hook_module._export_camera_to_blender_with_picker, (
        "Action-scoped 'Export Camera to Blender' must wire to the "
        "picker wrapper, NOT directly to _export_camera_to_blender — "
        "the dialog is the new menu surface."
    )
```
</test_surgery_E>

<test_surgery_F>
REWRITE `test_action_menu_shape` (lines 449-474) for the reverted shape.

```python
def test_action_menu_shape(self):
    """get_action_custom_ui_actions()'s root group has exactly 1 dict
    (the picker-wrapped Export Camera to Blender). Reverted from i31's
    6-entry shape per quick 260501-knl."""
    groups = _hook_module.get_action_custom_ui_actions()
    assert len(groups) == 1, \
        f"Expected exactly 1 root group; got {len(groups)}"

    actions = groups[0]["actions"]
    assert len(actions) == 1, \
        f"Expected 1 entry in root group; got {len(actions)}"

    assert actions[0]["name"] == "Export Camera to Blender"
    assert actions[0]["isVisible"] is _hook_module._scope_action_camera
    assert actions[0]["execute"] is \
        _hook_module._export_camera_from_action_selection_with_picker, (
        "Camera-scoped entry must wire to the picker wrapper, NOT "
        "directly to _export_camera_from_action_selection."
    )
```

Also DELETE the class-level constant `_LADDER_LABELS_AFTER_DEFAULT`
(lines 265-271) — no longer referenced by E or F. The per-stop dispatch
tests (A, B) inline their parametrize values; the constant has no
remaining consumer.
</test_surgery_F>

<test_new_J_K>
After test I (signature shape, lines 515-540), append two new tests
that defend the new module surface beyond the wrapper tests:

**`test_wrappers_exist_and_are_callable`**:
```python
def test_wrappers_exist_and_are_callable(self):
    """The two new menu wrapper functions must exist at module scope
    and be 1-arg callables (the menu callback shape Flame expects)."""
    import inspect

    for fn_name in (
        "_export_camera_to_blender_with_picker",
        "_export_camera_from_action_selection_with_picker",
    ):
        fn = getattr(_hook_module, fn_name, None)
        assert callable(fn), f"{fn_name} must be a callable at module scope"
        sig = inspect.signature(fn)
        # 1 positional 'selection' arg (matches Flame menu callback shape).
        assert len(sig.parameters) == 1, (
            f"{fn_name} must take exactly 1 arg (selection); "
            f"got {list(sig.parameters)}"
        )
```

**`test_factory_still_present`** (defends PRESERVE-FACTORY-05):
```python
def test_factory_still_present(self):
    """quick 260501-knl reverts the menu but KEEPS _make_export_callback
    and _LADDER_MENU_STOPS. Tests A/B/C/I depend on them. This test
    also catches accidental factory deletion during the revert."""
    assert hasattr(_hook_module, "_make_export_callback"), \
        "_make_export_callback factory must STAY (per PRESERVE-FACTORY-05)"
    assert hasattr(_hook_module, "_LADDER_MENU_STOPS"), \
        "_LADDER_MENU_STOPS constant must STAY"
    assert _hook_module._LADDER_MENU_STOPS == (0.01, 0.1, 1.0, 10.0, 100.0)
```
</test_new_J_K>

<dialog_test_module>
NEW FILE — `tests/test_scale_picker_dialog.py`. Real PySide6, real
QApplication, no stubs — this test module is intentionally separate
from `test_hook_export_camera_to_blender.py` (which stubs PySide6) so
that real Qt construction is exercised.

Headless PySide6 testing pattern: instantiate
`QApplication.instance() or QApplication([])` once at module load. Each
test calls pick_scale via a button-click trampoline (a QTimer.singleShot
that fires after exec() starts and clicks the chosen button or sends
ESC). This pattern works headlessly without pytest-qt.

```python
"""Unit tests for flame/scale_picker_dialog.py::pick_scale.

Uses a real PySide6 QApplication (NOT the MagicMock stub used by
test_hook_export_camera_to_blender.py). This module does not import
camera_match_hook directly to avoid pulling in the hook's heavy
dependency chain — pick_scale's lazy import of _FORGE_SS from
camera_match_hook is monkeypatched via a stub module.
"""

from __future__ import annotations

import os
import sys
import types

import pytest

# --- Path setup: add the repo's flame/ directory to sys.path so the
#     dialog module's `from camera_match_hook import _FORGE_SS` lazy
#     import finds our stub (installed below) AND the dialog module
#     itself can be imported via plain `import scale_picker_dialog`. ---
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_FLAME_DIR = os.path.join(_REPO_ROOT, "flame")
sys.path.insert(0, _FLAME_DIR)

# Install a minimal camera_match_hook stub exposing _FORGE_SS (so the
# dialog's `from camera_match_hook import _FORGE_SS` resolves without
# loading the real 3000-LOC hook). The actual stylesheet content is
# unimportant for these tests — what matters is that pick_scale can
# import + apply *something*.
_camera_match_hook_stub = types.ModuleType("camera_match_hook")
_camera_match_hook_stub._FORGE_SS = ""  # empty stylesheet is fine
sys.modules.setdefault("camera_match_hook", _camera_match_hook_stub)


# --- QApplication: real, single instance for the whole test module ---
@pytest.fixture(scope="module", autouse=True)
def _qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app
    # Don't quit() — pytest may run other Qt-using modules after this
    # one; QApplication is process-wide and meant to be reused.


# --- Helper: trampoline that clicks a button or rejects after exec() ---
def _click_button_after_show(label_prefix):
    """Return a QTimer-bound callable that, after the dialog shows,
    finds the button whose text starts with label_prefix and clicks it.
    """
    from PySide6.QtCore import QTimer

    def _setup(dialog):
        from PySide6.QtWidgets import QPushButton
        def _do_click():
            for btn in dialog.findChildren(QPushButton):
                if btn.text().startswith(label_prefix):
                    btn.click()
                    return
            # Fallback: reject if no matching button (test will fail loudly)
            dialog.reject()
        QTimer.singleShot(0, _do_click)

    return _setup


def _reject_after_show(dialog):
    """Reject the dialog (simulates ESC) after exec() starts."""
    from PySide6.QtCore import QTimer
    QTimer.singleShot(0, dialog.reject)


# --- Test 1: 5 buttons with the expected labels ---
def test_pick_scale_constructs_dialog_with_5_scale_buttons(monkeypatch):
    """The dialog must contain 5 QPushButtons with text starting with
    each of the 5 ladder labels (0.01x, 0.1x, 1x, 10x, 100x)."""
    import scale_picker_dialog
    from PySide6.QtWidgets import QPushButton

    captured = {}

    # Monkeypatch QDialog.exec to capture the dialog and reject without
    # showing — we only need to assert on the constructed widget tree.
    from PySide6.QtWidgets import QDialog
    original_exec = QDialog.exec
    def _fake_exec(self):
        captured["dialog"] = self
        return QDialog.Rejected
    monkeypatch.setattr(QDialog, "exec", _fake_exec)

    result = scale_picker_dialog.pick_scale(default=100.0)
    assert result is None  # we rejected

    dialog = captured["dialog"]
    btn_labels = [b.text().split("\n", 1)[0]
                  for b in dialog.findChildren(QPushButton)]
    # Filter out the Cancel button.
    scale_labels = [l for l in btn_labels if l != "Cancel"]
    assert scale_labels == ["0.01x", "0.1x", "1x", "10x", "100x"]


# --- Test 2: default=100.0 highlights the "100x" button as default ---
def test_pick_scale_default_100_highlights_100x_button(monkeypatch):
    """default=100.0 -> the '100x' button has setDefault(True) and
    objectName='primary' (the forge-style primary marker)."""
    import scale_picker_dialog
    from PySide6.QtWidgets import QPushButton, QDialog

    captured = {}
    def _fake_exec(self):
        captured["dialog"] = self
        return QDialog.Rejected
    monkeypatch.setattr(QDialog, "exec", _fake_exec)

    scale_picker_dialog.pick_scale(default=100.0)

    dialog = captured["dialog"]
    primary_buttons = [
        b for b in dialog.findChildren(QPushButton)
        if b.text().startswith("100x")
    ]
    assert len(primary_buttons) == 1
    assert primary_buttons[0].isDefault(), \
        "100x button must be the dialog's default (Enter triggers it)"
    assert primary_buttons[0].objectName() == "primary", \
        "100x button must have objectName='primary' for forge styling"

    # And the other buttons must NOT be marked primary.
    other_scale_buttons = [
        b for b in dialog.findChildren(QPushButton)
        if not b.text().startswith("100x")
        and b.text() != "Cancel"
    ]
    for b in other_scale_buttons:
        assert b.objectName() != "primary", (
            f"Non-default button {b.text()!r} must NOT be marked primary"
        )


# --- Test 3: parametrized — clicking each button returns its scale ---
@pytest.mark.parametrize("label_prefix,expected_scale", [
    ("0.01x", 0.01),
    ("0.1x", 0.1),
    ("1x", 1.0),
    ("10x", 10.0),
    ("100x", 100.0),
])
def test_pick_scale_returns_scale_on_button_click(
    monkeypatch, label_prefix, expected_scale,
):
    """Clicking each ladder button closes the dialog and returns that
    button's scale value."""
    import scale_picker_dialog
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QDialog, QPushButton

    # We need to actually exec() the dialog so the click handler runs,
    # but exec() blocks. Use a QTimer to schedule the click + accept.
    # The trampoline finds the button by label and clicks it.
    original_exec = QDialog.exec
    def _exec_with_trampoline(self):
        def _do_click():
            for btn in self.findChildren(QPushButton):
                if btn.text().startswith(label_prefix) and btn.text() != "Cancel":
                    btn.click()
                    return
            self.reject()
        QTimer.singleShot(0, _do_click)
        return original_exec(self)
    monkeypatch.setattr(QDialog, "exec", _exec_with_trampoline)

    result = scale_picker_dialog.pick_scale(default=100.0)
    assert result == expected_scale


# --- Test 4: ESC / reject returns None ---
def test_pick_scale_cancel_returns_none(monkeypatch):
    """Rejecting the dialog (ESC, X, Cancel button) returns None."""
    import scale_picker_dialog
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QDialog

    original_exec = QDialog.exec
    def _exec_with_reject(self):
        QTimer.singleShot(0, self.reject)
        return original_exec(self)
    monkeypatch.setattr(QDialog, "exec", _exec_with_reject)

    result = scale_picker_dialog.pick_scale(default=100.0)
    assert result is None


# --- Test 5: cancel button click also returns None ---
def test_pick_scale_cancel_button_returns_none(monkeypatch):
    """Clicking the explicit Cancel button (not just ESC) returns None."""
    import scale_picker_dialog
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QDialog, QPushButton

    original_exec = QDialog.exec
    def _exec_with_cancel_click(self):
        def _click_cancel():
            for btn in self.findChildren(QPushButton):
                if btn.text() == "Cancel":
                    btn.click()
                    return
            self.reject()
        QTimer.singleShot(0, _click_cancel)
        return original_exec(self)
    monkeypatch.setattr(QDialog, "exec", _exec_with_cancel_click)

    result = scale_picker_dialog.pick_scale(default=100.0)
    assert result is None


# --- Test 6: default not in ladder -> no button is primary ---
def test_pick_scale_unknown_default_no_primary(monkeypatch):
    """If `default` does not match any ladder stop, no button is
    highlighted as primary (still functional, just no Enter shortcut).
    Defends against silent crashes on unexpected default values."""
    import scale_picker_dialog
    from PySide6.QtWidgets import QDialog, QPushButton

    captured = {}
    def _fake_exec(self):
        captured["dialog"] = self
        return QDialog.Rejected
    monkeypatch.setattr(QDialog, "exec", _fake_exec)

    scale_picker_dialog.pick_scale(default=42.0)

    dialog = captured["dialog"]
    primary = [b for b in dialog.findChildren(QPushButton)
               if b.objectName() == "primary"]
    assert primary == [], \
        "Unknown default must produce no primary button"
```

**On QTimer.singleShot in test 3 / test 4 / test 5**: `singleShot(0, ...)`
schedules the callback to run on the next event-loop tick after exec()
starts pumping events. The callback fires, clicks the button or calls
reject(), exec() returns, and pick_scale returns the captured value.
This is the standard pytest-qt-free pattern for headless QDialog
testing.

**On test 1 / 2 / 6 monkeypatching exec**: these tests do NOT need the
event loop to run — they only need to inspect the constructed widget
tree before exec returns. A monkeypatched exec that captures `self` and
returns Rejected synthesizes the "dialog was built but rejected" path.

**Run convention**: `pytest tests/test_scale_picker_dialog.py -v -p no:pytest-blender`
— same -p flag as the rest of the suite (per
`memory/forge_pytest_blender_session_exit.md`).

**Headless concern**: macOS may show a brief dock icon when QApplication
spins up; on Linux without an X server you may need `QT_QPA_PLATFORM=offscreen`
in the env. The executor should set this in the verify command.
</dialog_test_module>

<install_sh_check>
The new module `flame/scale_picker_dialog.py` must be deployed alongside
`camera_match_hook.py` to `/opt/Autodesk/shared/python/camera_match/`
for the lazy `from scale_picker_dialog import pick_scale` to resolve at
runtime.

Read `install.sh` (the project root has it per CLAUDE.md). If it copies
the entire `flame/` directory, no change needed. If it copies
`camera_match_hook.py` by name, add `scale_picker_dialog.py` to the
copy list.

Verify post-edit by re-reading the deploy step in install.sh and
confirming both files end up under `/opt/Autodesk/shared/python/camera_match/`.
</install_sh_check>

<test_runner_convention>
The forge env's `pytest-blender` plugin exits the session before
collection if a Blender binary isn't on PATH (memory crumb
`forge_pytest_blender_session_exit.md`). ALL pytest invocations in this
plan MUST pass `-p no:pytest-blender` (hyphen, not underscore).
</test_runner_convention>

<constraints_recap>
- ONE entry per right-click surface after this lands. The 6-per-surface
  shape from i31 is GONE.
- The dialog runs from a Flame menu callback (main thread), NOT from
  forge-bridge — `flame_bridge_qt_main_thread.md` does NOT apply.
- Forge UI style is single-source-of-truth: the dialog imports
  `_FORGE_SS` from `camera_match_hook.py` and applies it via
  `setStyleSheet`. NO new palette, NO redefining colors.
- ESC / X / Cancel button MUST close the dialog cleanly with NO export
  call. Both the dialog test (test 4 + test 5) AND the wrapper test
  (test_wrapper_*_cancel_skips_export) defend this contract.
- NO new Python dependencies. PySide6 is already used by the calibrator
  and _pick_camera.
- The viewport-nav `blender_bridge.run_bake(..., scale=1000.0, ...)` at
  line ~2979 stays byte-identical (canary test G unchanged: count == 2).
- The `_make_export_callback` factory and `_LADDER_MENU_STOPS` constant
  STAY — they have test coverage (A, B, C, I) that must remain green.
  Test K (`test_factory_still_present`) catches accidental deletion.
- `_export_camera_pipeline`, `_export_camera_to_blender`, and
  `_export_camera_from_action_selection` keep their kw-only
  `flame_to_blender_scale=100.0` parameter (test I unchanged).
- Tests for the dialog live in a SEPARATE test module
  (`tests/test_scale_picker_dialog.py`) because the existing
  `tests/test_hook_export_camera_to_blender.py` stubs PySide6 with
  MagicMock — incompatible with real Qt construction.
</constraints_recap>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add scale_picker_dialog module + two menu wrappers + revert i31 menu shape on both surfaces + surgical test updates + new dialog test module</name>
  <files>flame/scale_picker_dialog.py, flame/camera_match_hook.py, tests/test_hook_export_camera_to_blender.py, tests/test_scale_picker_dialog.py, install.sh</files>
  <behavior>
    Production code:

    1. NEW file `flame/scale_picker_dialog.py` exporting
       `pick_scale(parent=None, default=100.0) -> Optional[float]`.
       Implementation per `<dialog_module_design>`. Lazy PySide6 imports
       inside the function body. Lazy `from camera_match_hook import _FORGE_SS`.
       5 QPushButton scale buttons (`0.01x` / `0.1x` / `1x` / `10x` / `100x`)
       arranged in a horizontal row with newline-separated label+subtitle
       text. Default button (matching `default` arg) gets
       `setObjectName("primary")` + `setDefault(True)` + `setAutoDefault(True)`.
       Cancel button at the bottom right.
       Returns chosen scale (float) on accept, None on reject (ESC/X/Cancel).

    2. `flame/camera_match_hook.py`:
       a. Insert `_export_camera_to_blender_with_picker(selection)` and
          `_export_camera_from_action_selection_with_picker(selection)`
          at module scope, AFTER `_make_export_callback`'s closing line
          (around line 2762) and BEFORE `_export_camera_pipeline` (around
          line 2768). Both lazy-import `from scale_picker_dialog import
          pick_scale`. Implementation per `<wrapper_design>`.
       b. `get_batch_custom_ui_actions()` "Camera" subgroup `actions` list
          REVERTED to 2 entries — DELETE all 5 ladder dicts (lines ~3089-3117)
          plus the "Quick 260501-i31:" comment block. The remaining
          "Export Camera to Blender" entry's `execute` becomes
          `_export_camera_to_blender_with_picker`. Final shape per
          `<menu_shape_after_revert>`.
       c. `get_action_custom_ui_actions()` root `actions` list REVERTED to
          1 entry — DELETE all 5 ladder dicts (lines ~3158-3187) plus the
          "Quick 260501-i31:" comment block. The remaining entry's
          `execute` becomes `_export_camera_from_action_selection_with_picker`.
          Final shape per `<menu_shape_after_revert>`.
       d. `_LADDER_MENU_STOPS` constant — UNCHANGED (still defined at line
          ~2730).
       e. `_make_export_callback(scale, *, camera_scope=False)` — UNCHANGED
          (still defined at lines ~2733-2762).
       f. `_export_camera_pipeline`, `_export_camera_to_blender`,
          `_export_camera_from_action_selection` signatures — UNCHANGED.
       g. Line ~2979 (`blender_bridge.run_bake(..., scale=1000.0, ...)`) —
          UNCHANGED (byte-identical).
       h. Confirm with `grep -c "scale=1000.0" flame/camera_match_hook.py`
          == 2 both before and after.

    3. `install.sh` — verify it deploys `flame/scale_picker_dialog.py`
       to `/opt/Autodesk/shared/python/camera_match/` alongside
       `camera_match_hook.py`. If the script copies by name (not by
       wildcard / directory), add the new file to the copy list.
       Otherwise no change.

    Tests:

    4. `tests/test_hook_export_camera_to_blender.py`:
       a. DELETE the class-level constant `_LADDER_LABELS_AFTER_DEFAULT`
          at lines 265-271 (no longer referenced after E and F rewrites).
       b. REWRITE `test_default_entry_still_uses_scale_100_action_scope`
          (lines 360-389) per `<test_surgery_D>` first test.
       c. ADD `test_wrapper_action_scope_cancel_skips_export` per
          `<test_surgery_D>` second test.
       d. REWRITE `test_default_entry_still_uses_scale_100_camera_scope`
          (lines 391-411) per `<test_surgery_D>` third test.
       e. ADD `test_wrapper_camera_scope_cancel_skips_export` per
          `<test_surgery_D>` fourth test.
       f. REWRITE `test_batch_menu_shape` (lines 416-444) per
          `<test_surgery_E>`.
       g. REWRITE `test_action_menu_shape` (lines 449-474) per
          `<test_surgery_F>`.
       h. APPEND `test_wrappers_exist_and_are_callable` and
          `test_factory_still_present` per `<test_new_J_K>`.
       i. STAYS UNCHANGED:
          - Test A (test_factory_dispatches_per_stop_action_scope, parametrized)
          - Test B (test_factory_dispatches_per_stop_camera_scope, parametrized)
          - Test C (test_factory_camera_scope_routing)
          - Test G (test_viewport_nav_canary_unchanged) — count == 2 invariant
          - Test H (test_no_new_pyside_widgets_in_factory) — factory body
            still must not contain dialog tokens
          - Test I (test_pipeline_signature_has_keyword_only_scale_default_100)

    5. NEW file `tests/test_scale_picker_dialog.py` per
       `<dialog_test_module>`. 6 + 5(parametrized in test 3) = 10 collected
       items. Real PySide6, real QApplication, no stubs of PySide6 (the
       `camera_match_hook` import is stubbed via a small types.ModuleType
       to avoid loading the 3000-LOC hook).

    6. Run pytest:
       ```
       cd /Users/cnoellert/Documents/GitHub/forge-calibrator
       QT_QPA_PLATFORM=offscreen pytest tests/test_scale_picker_dialog.py -v -p no:pytest-blender
       pytest tests/test_hook_export_camera_to_blender.py -v -p no:pytest-blender
       pytest tests/ -p no:pytest-blender
       ```
       All three must be GREEN. Full-suite count: was 508/0/2 after i31;
       expected after this plan: ~510-515 / 0 / 2 (delta = +2 wrapper-cancel
       tests + 2 wrapper-existence/factory-still-present tests + 6
       individual dialog tests + 4 parametrized dialog tests - 0 deletions
       = ~+14 net new collected items vs i31 baseline; minus the
       parametrize x 5 deletion if E/F's old labels-list assertions count
       as separate items... safest framing: "no test count regression,
       new dialog tests + new wrapper tests are net-additive").
  </behavior>
  <action>
    1. **Create `flame/scale_picker_dialog.py`** with the exact body from
       `<dialog_module_design>`. ~145 LOC including docstrings.

    2. **Edit `flame/camera_match_hook.py`** in this order:

       a. **Insert new wrappers** after `_make_export_callback`'s closing
          line. Locate by searching for the line
          `    return _cb` immediately followed by a blank line and then
          `# RESEARCH §P-02 + Open Question OQ-2`-style comment OR
          `def _export_camera_pipeline(`. Insert the two wrapper functions
          from `<wrapper_design>` directly between `_make_export_callback`
          and the next function. Add a blank line above and below the new
          block to keep PEP8 spacing.

       b. **Revert get_batch_custom_ui_actions Camera subgroup**.
          Replace lines ~3089-3117 (the 5 ladder dicts + their leading
          "Quick 260501-i31" comment block) with NOTHING. The remaining
          `actions` list ends after the "Export Camera to Blender" dict's
          closing `},`. Then change the `execute` field of THAT dict
          from `_export_camera_to_blender` to
          `_export_camera_to_blender_with_picker`. The final structure
          matches `<menu_shape_after_revert>` exactly.

       c. **Revert get_action_custom_ui_actions root actions list**.
          Replace lines ~3158-3187 (the 5 ladder dicts + leading "Quick
          260501-i31" comment block) with NOTHING. Then change the
          `execute` field of the remaining single dict from
          `_export_camera_from_action_selection` to
          `_export_camera_from_action_selection_with_picker`.

       d. **Verify the canary**: run
          `grep -c "scale=1000.0" /Users/cnoellert/Documents/GitHub/forge-calibrator/flame/camera_match_hook.py` —
          MUST return 2 after edits (same as before — the count was 2 on
          HEAD per i31 SUMMARY).

       e. **Verify factory STILL exists**: run
          `grep -n "def _make_export_callback\\|_LADDER_MENU_STOPS = " flame/camera_match_hook.py` —
          MUST show both at module scope (around lines 2730 and 2733).

    3. **Read `install.sh`**:
       ```bash
       cat /Users/cnoellert/Documents/GitHub/forge-calibrator/install.sh
       ```
       Look at how `camera_match_hook.py` reaches
       `/opt/Autodesk/shared/python/camera_match/`:
         - If install.sh `cp -r flame/* ...` (whole-directory): no edit
           needed — `scale_picker_dialog.py` rides along automatically.
         - If install.sh `cp flame/camera_match_hook.py ...` (named file):
           add a sibling `cp flame/scale_picker_dialog.py
           /opt/Autodesk/shared/python/camera_match/scale_picker_dialog.py`
           line in the same block.
         - If install.sh uses `rsync flame/ .../camera_match/`: no edit
           needed.
       Edit only if necessary; add a comment line above the new cp call
       referencing this quick: `# Added by quick 260501-knl — scale picker dialog`.

    4. **Edit `tests/test_hook_export_camera_to_blender.py`**:

       a. Delete `_LADDER_LABELS_AFTER_DEFAULT` constant (lines 265-271).
       b. Replace `test_default_entry_still_uses_scale_100_action_scope`
          (lines 360-389) with `test_wrapper_action_scope_forwards_picked_scale`
          per `<test_surgery_D>`.
       c. Add `test_wrapper_action_scope_cancel_skips_export` immediately
          after.
       d. Replace `test_default_entry_still_uses_scale_100_camera_scope`
          (lines 391-411) with `test_wrapper_camera_scope_forwards_picked_scale`
          per `<test_surgery_D>`.
       e. Add `test_wrapper_camera_scope_cancel_skips_export` immediately
          after.
       f. Replace `test_batch_menu_shape` (lines 416-444) per
          `<test_surgery_E>`.
       g. Replace `test_action_menu_shape` (lines 449-474) per
          `<test_surgery_F>`.
       h. Append `test_wrappers_exist_and_are_callable` and
          `test_factory_still_present` per `<test_new_J_K>` AFTER test I.

    5. **Create `tests/test_scale_picker_dialog.py`** with the exact body
       from `<dialog_test_module>`. ~180 LOC.

    6. **Run pytest** with the mandatory `-p no:pytest-blender` and the
       headless Qt env var:
       ```
       cd /Users/cnoellert/Documents/GitHub/forge-calibrator
       QT_QPA_PLATFORM=offscreen pytest tests/test_scale_picker_dialog.py -v -p no:pytest-blender
       pytest tests/test_hook_export_camera_to_blender.py -v -p no:pytest-blender
       pytest tests/ -p no:pytest-blender
       ```
       All three must be GREEN. If any test fails:
       - Test A/B/C failures → factory was accidentally deleted; restore.
       - Test G failure → `scale=1000.0` count drifted; revert any edits
         that touched the run_bake call line.
       - Test I failure → a signature was accidentally mutated; restore
         the kw-only parameter.
       - Test H failure → factory body now contains forbidden Qt tokens
         (you put dialog code in `_make_export_callback` instead of the
         new wrapper); move the dialog call out.
       - Dialog tests failing on `QT_QPA_PLATFORM` → ensure the env var
         is set in the test invocation.
       - `test_wrappers_exist_and_are_callable` failure → wrappers not
         at module scope or take wrong number of args.
       - `test_factory_still_present` failure → factory was deleted.
  </action>
  <verify>
    <automated>cd /Users/cnoellert/Documents/GitHub/forge-calibrator && QT_QPA_PLATFORM=offscreen pytest tests/test_scale_picker_dialog.py -v -p no:pytest-blender 2>&1 | tail -25 && echo "---HOOK TESTS---" && pytest tests/test_hook_export_camera_to_blender.py -v -p no:pytest-blender 2>&1 | tail -30 && echo "---FULL SUITE---" && pytest tests/ -p no:pytest-blender 2>&1 | tail -10 && echo "---CANARY---" && grep -c "scale=1000.0" flame/camera_match_hook.py && echo "---FACTORY STILL THERE---" && grep -n "def _make_export_callback\|^_LADDER_MENU_STOPS = " flame/camera_match_hook.py && echo "---WRAPPERS LIVE---" && grep -n "def _export_camera_to_blender_with_picker\|def _export_camera_from_action_selection_with_picker" flame/camera_match_hook.py && echo "---NO LADDER ENTRIES IN MENU---" && grep -c "Export to Blender @ " flame/camera_match_hook.py</automated>
  </verify>
  <done>
    - `flame/scale_picker_dialog.py` exists, exports `pick_scale(parent=None, default=100.0) -> Optional[float]`.
    - `flame/camera_match_hook.py::_export_camera_to_blender_with_picker(selection)` and `_export_camera_from_action_selection_with_picker(selection)` exist at module scope.
    - `get_batch_custom_ui_actions()` "Camera" subgroup has exactly 2 entries; the Action-scoped one's `execute` is `_export_camera_to_blender_with_picker`.
    - `get_action_custom_ui_actions()` root has exactly 1 entry; its `execute` is `_export_camera_from_action_selection_with_picker`.
    - `_LADDER_MENU_STOPS` and `_make_export_callback` UNCHANGED at module scope.
    - `_export_camera_pipeline`, `_export_camera_to_blender`, `_export_camera_from_action_selection` signatures UNCHANGED (kw-only `flame_to_blender_scale=100.0`).
    - `grep -c "scale=1000.0" flame/camera_match_hook.py` returns 2 (canary).
    - `grep -c "Export to Blender @ " flame/camera_match_hook.py` returns 0 (no ladder labels remain in the file).
    - `tests/test_scale_picker_dialog.py` 10+ collected items, all GREEN.
    - `tests/test_hook_export_camera_to_blender.py::TestLadderMenuFactory` GREEN with the surgical updates (A/B/C/G/H/I unchanged, D rewritten + 2 cancel-companion tests added, E/F rewritten for revert shape, J/K added at end).
    - `pytest tests/ -p no:pytest-blender` GREEN — full suite passes with no regressions vs i31 baseline (508/0/2).
    - install.sh confirmed (or updated) to deploy scale_picker_dialog.py to /opt/Autodesk/shared/python/camera_match/.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Flame menu dispatch -> Python callback | Flame caches the registered `execute` callable at hook-registration time. After this revert, that callable is `_export_camera_*_with_picker`, which opens a QDialog on the main thread. No untrusted-input crossing. |
| Python wrapper -> QDialog event loop | The dialog's button-click handlers run synchronously in the Flame main thread; no concurrency, no threading. Confirms `flame_bridge_qt_main_thread.md` does NOT apply (that constraint is bridge-specific). |
| pick_scale -> _export_camera_to_blender / _export_camera_from_action_selection | The chosen `scale` (float, one of 5 hardcoded ladder values) flows in via the kw-only parameter. The dialog can only return values from `_LADDER_STOPS`; bake-side validator (per 260501-dpa) catches any out-of-ladder value. |

This is an internal VFX post-production tool with no untrusted-input
surface (per CLAUDE.md security posture). The threat model below covers
correctness/integrity threats only.

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-quick-260501-knl-01 | Tampering (factory accidentally deleted during revert) | Someone could "clean up" by deleting `_make_export_callback` and `_LADDER_MENU_STOPS` since the menu no longer references them | mitigate | Test K (`test_factory_still_present`) asserts both still exist at module scope. Tests A/B/C from i31 (per-stop dispatch) still depend on the factory and would fail loudly if removed. |
| T-quick-260501-knl-02 | Tampering (default scale silently changes) | The wrapper's `default=100.0` argument to pick_scale could regress to a different value | mitigate | Wrapper tests (test_wrapper_*_forwards_picked_scale) use a stub `pick_scale` that always returns 100.0; if the wrapper passes a different default, the test still passes — but the human UAT (Flame restart + dialog opens with 100x highlighted) catches it. Test 2 of the dialog module (`test_pick_scale_default_100_highlights_100x_button`) defends the dialog side. |
| T-quick-260501-knl-03 | Information Disclosure (viewport-nav scale=1000.0 inadvertently changed) | The `run_bake(..., scale=1000.0, ...)` line at ~2979 could be touched while editing the surrounding pipeline body | mitigate | Test G (canary, unchanged from i31) reads the source file and asserts the literal string `"scale=1000.0"` count is exactly 2. |
| T-quick-260501-knl-04 | Denial of Service (cancel path silently runs export) | Bug in the wrapper could fire the export when pick_scale returns None (e.g., `if scale is None: pass` instead of `return`) | mitigate | Tests `test_wrapper_*_cancel_skips_export` directly assert the underlying export is NOT called when the picker returns None. Dialog test 4 (`test_pick_scale_cancel_returns_none`) defends the dialog side. |
| T-quick-260501-knl-05 | Tampering (palette drift; dialog adopts a non-forge color set) | A future edit could redefine colors in the new module instead of importing _FORGE_SS | mitigate | Per `memory/forge_ui_style.md`, the dialog MUST `from camera_match_hook import _FORGE_SS`. The dialog body in `<dialog_module_design>` enforces this; any drift would be caught at code review. (No automated test guards this — but the human UAT step "verify dialog matches calibrator's color scheme" catches visible drift.) |
| T-quick-260501-knl-06 | Repudiation (install.sh forgets to deploy the new module) | The new dialog module is in flame/ but might not reach /opt/Autodesk/shared/python/camera_match/, causing `from scale_picker_dialog import pick_scale` to fail at runtime | mitigate | Action step 3 mandates reading install.sh and verifying (or adding) the deploy step. UAT step 1 (`bash install.sh`) plus UAT step 2 (clicking the menu entry) catches a missing deploy at human-test time. |
| T-quick-260501-knl-07 | Elevation of Privilege | N/A | accept | No privilege boundary touched. Pure Python wrappers + Qt dialog; runs inside Flame's existing hook process. |

</threat_model>

<verification>
## Local automated gate (this plan)

```bash
cd /Users/cnoellert/Documents/GitHub/forge-calibrator
# 1. New dialog tests are GREEN with real PySide6 (headless)
QT_QPA_PLATFORM=offscreen pytest tests/test_scale_picker_dialog.py -v -p no:pytest-blender
# 2. Reworked hook tests are GREEN
pytest tests/test_hook_export_camera_to_blender.py -v -p no:pytest-blender
# 3. Full suite — no regression on the existing 508+ tests
pytest tests/ -p no:pytest-blender
# 4. Viewport-nav canary
test "$(grep -c 'scale=1000.0' flame/camera_match_hook.py)" = "2"
# 5. No ladder labels remain in the hook source
test "$(grep -c 'Export to Blender @ ' flame/camera_match_hook.py)" = "0"
# 6. Factory + ladder constant still present
grep -q "def _make_export_callback" flame/camera_match_hook.py
grep -q "_LADDER_MENU_STOPS = (0.01, 0.1, 1.0, 10.0, 100.0)" flame/camera_match_hook.py
# 7. New wrappers present
grep -q "def _export_camera_to_blender_with_picker" flame/camera_match_hook.py
grep -q "def _export_camera_from_action_selection_with_picker" flame/camera_match_hook.py
# 8. New dialog module present
test -f flame/scale_picker_dialog.py
```

## Manual UAT (per `flame_module_reload.md` — requires full Flame restart)

```
1. bash install.sh                          # deploy hook + new dialog module
2. Quit and re-launch Flame 2026.2.1
3. Open Batch with an Action node containing a non-Perspective camera
4. Right-click the Action node
   -> FORGE > Camera should show:
      - Open Camera Calibrator (clip-scoped; not visible on Action right-click)
      - Export Camera to Blender                <- ONLY one entry (no @ Nx siblings)
5. Click "Export Camera to Blender"
   -> Forge-themed modal dialog opens, titled "FORGE — Export Camera to Blender — Scale"
   -> 5 buttons in a row, each with the scale label on top + subtitle below
   -> "100x" button is visually highlighted (orange bg, white text — primary style)
   -> "100x" button has keyboard focus (responds to Enter)
6. Hit ESC
   -> Dialog closes silently. No error dialog. No Blender launch. No JSON written.
7. Right-click the Action again, click "Export Camera to Blender" again
   -> Same dialog opens
8. Click "0.01x"
   -> Dialog closes; Blender launches with the camera at ~83km from origin
   -> .blend file is created at ~/forge-bakes/<action>_<cam>.blend
9. Right-click the Action again -> Export Camera to Blender
10. Hit Enter (no mouse — should trigger the default 100x button)
    -> Dialog closes; Blender launches with camera at ~83m (room scale)
11. Right-click the Action again -> Export Camera to Blender
12. Click the "Cancel" button (bottom-right)
    -> Dialog closes silently. No export.
13. Right-click a Camera node INSIDE an Action's schematic
    -> Single "Export Camera to Blender" entry (no @ Nx siblings)
14. Click it
    -> Same forge-themed dialog opens
15. Pick "1x"
    -> Camera-scope path runs; Blender opens with camera at raw Flame-pixel
       position (no divisor)
16. Visually compare the dialog's color scheme to the existing
    "Camera Calibrator" window (FORGE > Camera > Open Camera Calibrator on
    a clip): same dark grey background, same FORGE-orange accent, same
    button styling. If colors drift, the executor missed the
    `from camera_match_hook import _FORGE_SS` import.
```

## Out of scope (next session — explicit deferrals)

- Persistent preference (last-used scale across Flame sessions): per the
  task spec, deliberately not implemented. Each menu open is a fresh choice.
- Keyboard shortcuts inside the dialog (number keys 1-5 mapped to
  buttons): nice-to-have, not in scope. Default Enter for "100x" + Tab
  to navigate is sufficient.
- "Remember choice" checkbox in the dialog: deferred.
- Calibrated reference-distance UI: separate phase.
- Geometry scaling (only camera positions are scaled today): deferred.
- Matchbox-side anything: shelved 2026-05-01.
- Documentation of per-stop physical semantics in user docs: deferred to
  the same docs quick that 260501-i31 SUMMARY listed as next-step.
- Extracting a shared `_forge_style.py` palette module (recommended by
  `memory/forge_ui_style.md` "if more tools land here"): not in scope —
  this dialog imports from camera_match_hook and that single
  source-of-truth is sufficient for now.
</verification>

<success_criteria>
This plan is COMPLETE when:

- [ ] `flame/scale_picker_dialog.py` exists, exports
      `pick_scale(parent=None, default=100.0) -> Optional[float]`, and
      its body matches `<dialog_module_design>` (lazy PySide6 imports,
      lazy `from camera_match_hook import _FORGE_SS`, 5 scale buttons,
      default highlight on `default`-matching button via
      `setObjectName("primary")` + `setDefault(True)`, ESC/Cancel
      returns None).
- [ ] `flame/camera_match_hook.py::_export_camera_to_blender_with_picker(selection)`
      exists at module scope; lazy-imports `pick_scale`; on `None`
      returns silently; on float forwards to
      `_export_camera_to_blender(selection, flame_to_blender_scale=scale)`.
- [ ] `flame/camera_match_hook.py::_export_camera_from_action_selection_with_picker(selection)`
      exists at module scope with the symmetric Camera-scope behavior.
- [ ] `get_batch_custom_ui_actions()` "Camera" subgroup has exactly 2
      `actions` entries; the Action-scoped one's `execute` is
      `_export_camera_to_blender_with_picker`.
- [ ] `get_action_custom_ui_actions()` root has exactly 1 entry; its
      `execute` is `_export_camera_from_action_selection_with_picker`.
- [ ] `_LADDER_MENU_STOPS = (0.01, 0.1, 1.0, 10.0, 100.0)` UNCHANGED at
      module scope.
- [ ] `_make_export_callback(scale, *, camera_scope=False)` UNCHANGED at
      module scope.
- [ ] `_export_camera_pipeline`, `_export_camera_to_blender`,
      `_export_camera_from_action_selection` UNCHANGED — keyword-only
      `flame_to_blender_scale: float = 100.0` parameter still present.
- [ ] `grep -c "scale=1000.0" flame/camera_match_hook.py` returns 2
      (viewport-nav canary unchanged from i31 baseline).
- [ ] `grep -c "Export to Blender @ " flame/camera_match_hook.py`
      returns 0 (no ladder labels remain in the hook source).
- [ ] install.sh confirmed to deploy `flame/scale_picker_dialog.py` to
      `/opt/Autodesk/shared/python/camera_match/` (or updated to do so).
- [ ] `tests/test_hook_export_camera_to_blender.py::TestLadderMenuFactory`
      GREEN with the surgical updates:
      - A (test_factory_dispatches_per_stop_action_scope, x5 parametrize) UNCHANGED.
      - B (test_factory_dispatches_per_stop_camera_scope, x5 parametrize) UNCHANGED.
      - C (test_factory_camera_scope_routing) UNCHANGED.
      - D-1 (test_wrapper_action_scope_forwards_picked_scale) REWRITTEN.
      - D-2 (test_wrapper_action_scope_cancel_skips_export) NEW.
      - D-3 (test_wrapper_camera_scope_forwards_picked_scale) REWRITTEN.
      - D-4 (test_wrapper_camera_scope_cancel_skips_export) NEW.
      - E (test_batch_menu_shape) REWRITTEN — asserts 2 entries / 1 Action-scoped.
      - F (test_action_menu_shape) REWRITTEN — asserts 1 entry.
      - G (test_viewport_nav_canary_unchanged) UNCHANGED — count == 2.
      - H (test_no_new_pyside_widgets_in_factory) UNCHANGED.
      - I (test_pipeline_signature_has_keyword_only_scale_default_100) UNCHANGED.
      - J (test_wrappers_exist_and_are_callable) NEW.
      - K (test_factory_still_present) NEW.
      - The class-level `_LADDER_LABELS_AFTER_DEFAULT` constant DELETED.
- [ ] `tests/test_scale_picker_dialog.py` 10+ collected items GREEN
      under `QT_QPA_PLATFORM=offscreen pytest ... -p no:pytest-blender`:
      - test 1: 5 scale buttons with expected labels.
      - test 2: default=100.0 highlights "100x" as primary + default.
      - test 3 (parametrize x5): each button click returns its scale.
      - test 4: ESC / reject returns None.
      - test 5: explicit Cancel button click returns None.
      - test 6: unknown default produces no primary button.
- [ ] `pytest tests/ -p no:pytest-blender` GREEN with no regressions
      vs the i31 baseline (508/0/2).
- [ ] Commit follows GSD quick-task style:
      `feat(quick-260501-knl): replace 5-stop ladder menu with single forge-themed scale picker dialog`
</success_criteria>

<output>
After completion, create:
`.planning/quick/260501-knl-revert-ladder-menu-replace-with-forge-th/260501-knl-SUMMARY.md`

Include in the summary:
- Files modified (with line counts) and the new files created.
- Confirmation that `_LADDER_MENU_STOPS` + `_make_export_callback`
  factory + the three signatures (kw-only `flame_to_blender_scale=100.0`)
  are PRESERVED end-to-end (i31 plumbing intact, only the menu shape
  reverted).
- Confirmation that the viewport-nav `scale=1000.0` CLI arg at
  `run_bake` is byte-identical (canary count = 2).
- Test count delta vs the i31 baseline (508/0/2).
- A note on the dialog module deployment: confirmed install.sh deploys
  `flame/scale_picker_dialog.py` to
  `/opt/Autodesk/shared/python/camera_match/` (state whether install.sh
  needed editing or rode along via wildcard copy).
- A note on the forge UI style import: the dialog imports `_FORGE_SS`
  from camera_match_hook (single source of truth per
  `memory/forge_ui_style.md`); palette is NOT redefined in the new
  module.
- Flame restart requirement for UAT (per `memory/flame_module_reload.md`):
  `bash install.sh` + full Flame restart needed for the menu shape
  change to take effect (Flame caches the dispatch table; live-reload
  via gc/exec does NOT refresh it).
- A one-line "next phase" reminder: persistent last-used-scale memory
  and number-key shortcuts inside the dialog are the natural follow-ups
  if artist UAT surfaces them as friction.
</output>
</content>
</invoke>