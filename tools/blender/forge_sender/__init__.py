"""forge_sender — Blender addon package for "Send to Flame".

This ``__init__.py`` declares the Python package boundary. Blender's
addon loader reads ``bl_info`` from here (added in Plan 02-03). For
now, the file exists so:

  - ``tools/blender/extract_camera.py`` can do::

        sys.path.insert(0, os.path.join(
            os.path.dirname(__file__), "forge_sender"))
        from flame_math import _rot3_to_flame_euler_deg, ...

  - and the pytest suite can locate ``flame_math.py`` as a top-level
    module via the same sys.path shim pattern.

No imports here — Blender 4.5's addon loader will populate this
file with ``bl_info``, ``register()`` / ``unregister()``, and class
registrations in Plan 02-03.
"""
