"""Host-agnostic math helpers used across the forge stack.

Modules here must stay dependency-light — numpy only, no host bindings
(no flame, no bpy, no Qt). That way every consumer can import them
without pulling in the full calibrator stack.
"""
