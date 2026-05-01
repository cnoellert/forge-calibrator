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


# --- Test 1: 5 buttons with the expected labels ---
def test_pick_scale_constructs_dialog_with_5_scale_buttons(monkeypatch):
    """The dialog must contain 5 QPushButtons with text starting with
    each of the 5 ladder labels (0.01x, 0.1x, 1x, 10x, 100x)."""
    import scale_picker_dialog
    from PySide6.QtWidgets import QPushButton, QDialog

    captured = {}

    # Monkeypatch QDialog.exec to capture the dialog and reject without
    # showing — we only need to assert on the constructed widget tree.
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
    # The trampoline finds the button by EXACT label-prefix match (so
    # "1x" doesn't match "10x" or "100x") and clicks it.
    original_exec = QDialog.exec
    def _exec_with_trampoline(self):
        def _do_click():
            for btn in self.findChildren(QPushButton):
                first_line = btn.text().split("\n", 1)[0]
                if first_line == label_prefix and btn.text() != "Cancel":
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
