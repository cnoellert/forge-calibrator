"""
forge_core — host-agnostic building blocks for Forge camera tools.

Contents:
    solver/   — vanishing-point camera calibration (pure numpy, no Flame / no Qt)

Everything in this package is usable from any Python context:
    - the Flame hook (via the forge conda env + Flame's bundled Python)
    - trafFIK and other downstream tools
    - CLI scripts and notebooks
    - the test suite

Flame-specific glue (Wiretap readers, Action-node integration, batch UI,
ZYX Euler decomposition for Action cameras) lives under flame/ at the
repo root, not here.
"""
