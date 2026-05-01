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
dialog matches the calibrator + _pick_camera + forge_cv_align tools. Do
NOT redefine palette colors in this module — single source of truth.

Pattern parity: the lazy PySide6 import inside pick_scale mirrors the
_pick_camera precedent at camera_match_hook.py:2352-2424. Test paths
that stub PySide6 (test_hook_export_camera_to_blender.py) can import
this module without dragging in real Qt; only the dedicated dialog
test module (test_scale_picker_dialog.py) instantiates real Qt.
"""

from __future__ import annotations

from typing import Optional


# Discrete log10 ladder, mirrors _LADDER_MENU_STOPS in camera_match_hook
# and _FLAME_TO_BLENDER_SCALE_LADDER in tools/blender/bake_camera.py.
# Subtitle text is human-readable physical scale guidance for the artist.
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
    (ESC, the X close box, or the explicit Cancel button).

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

    # Track the chosen scale via closure-captured mutable so the inner
    # click handlers can write it without `nonlocal` scoping issues.
    chosen = {"value": None}

    def _make_click_handler(scale_value):
        def _handler():
            chosen["value"] = scale_value
            dialog.accept()
        return _handler

    btn_row = QHBoxLayout()
    btn_row.setSpacing(8)

    for label, scale_value, sub in _LADDER_STOPS:
        # Each button is a single QPushButton with newline-separated
        # text (label on top, subtitle below). Single-widget-per-button
        # keeps test location trivial: filter by btn.text().split("\n", 1)[0].
        btn = QPushButton(f"{label}\n{sub}")
        btn.setMinimumHeight(56)
        btn.setMinimumWidth(96)
        if scale_value == default:
            # Default button highlighting: setObjectName("primary") triggers
            # the QPushButton#primary block in _FORGE_SS (orange bg, white
            # text, bold). setDefault(True) makes Enter trigger this button.
            # setAutoDefault(True) keeps it the default even if another
            # button gets focus via Tab.
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

    # ESC and the window-manager X both fire reject() automatically via
    # QDialog's built-in handling. exec() returns Rejected -> we return None.
    if dialog.exec() != QDialog.Accepted:
        return None
    return chosen["value"]
