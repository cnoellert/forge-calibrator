"""
forge_flame — Flame-specific adapters for Forge camera tools.

Unlike ``forge_core`` which is host-agnostic, everything in this package
touches Flame's API (PyClip, Wiretap SDK, batch.Action). Not importable
from trafFIK or any non-Flame tool — the Wiretap SDK only exists inside
a Flame install.

Contents:
    adapter.py — solve_for_flame() (packing + Euler decomposition)
    wiretap.py — get_clip_colour_space(), extract_frame_bytes()

Ships alongside forge_core/ at install time (see install.sh).

History: pre-quick-260505-tb3 this package also contained
blender_bridge / fbx_ascii / fbx_io / camera_io modules supporting
a Flame↔Blender camera round-trip. That surface was stripped 2026-05-05
(Phase A2) — the export half lives on in forge-blender Phase 6 via
git-history cherry-pick from this repo. See
.planning/notes/blender-strip-pending.md for the decision chain.
"""
