"""
forge_flame — Flame-specific adapters for Forge camera tools.

Unlike ``forge_core`` which is host-agnostic, everything in this package
touches Flame's API (PyClip, Wiretap SDK, batch.Action). Not importable
from trafFIK or any non-Flame tool — the Wiretap SDK only exists inside
a Flame install.

Contents:
    wiretap.py — get_clip_colour_space(), extract_frame_bytes()

Ships alongside forge_core/ at install time (see install.sh).
"""
