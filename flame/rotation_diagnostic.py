"""
Flame rotation convention diagnostic.

Paste the contents of this file into Flame's Python console (or run as a
scripted hook). It creates a fresh Action node, sets the camera to three
isolated rotations, and dumps each resulting world matrix.

From three matrices we can solve for Flame's Euler order and sign conventions
mathematically.

Run inside Flame with a Batch group open.
"""

import flame
import threading


TEST_ROTATIONS = [
    ("yaw",   (0.0, 45.0, 0.0)),
    ("pitch", (45.0, 0.0, 0.0)),
    ("roll",  (0.0, 0.0, 45.0)),
    ("compound", (30.0, 45.0, 15.0)),  # non-commutative — reveals order
]


def _dump_attrs(obj, name, depth=0):
    """Print non-underscore attrs of obj. Helps locate matrix-like accessors."""
    prefix = "  " * depth
    print(f"{prefix}{name} ({type(obj).__name__}):")
    for attr in sorted(dir(obj)):
        if attr.startswith("_"):
            continue
        try:
            v = getattr(obj, attr)
        except Exception as e:
            print(f"{prefix}  {attr} = <err {e}>")
            continue
        # Attempt get_value for PyAttribute types
        gv = None
        if hasattr(v, "get_value"):
            try:
                gv = v.get_value()
            except Exception as e:
                gv = f"<get_value err {e}>"
        vr = repr(v)
        if len(vr) > 120:
            vr = vr[:120] + "..."
        print(f"{prefix}  {attr} = {vr}" + (f"   .get_value()={gv!r}" if gv is not None else ""))


def _try_read_matrix(cam):
    """Try a handful of known matrix attribute paths. Return whatever works."""
    candidates = [
        "world_matrix", "matrix", "global_matrix", "local_matrix",
        "transform", "world_transform", "global_transform",
    ]
    for name in candidates:
        attr = getattr(cam, name, None)
        if attr is None:
            continue
        val = attr.get_value() if hasattr(attr, "get_value") else attr
        print(f"  {name} = {val!r}")
    # Also attempt decomposed readback
    for name in ("position", "rotation", "focal_length", "focal", "film_back_width"):
        attr = getattr(cam, name, None)
        if attr is None:
            continue
        try:
            val = attr.get_value() if hasattr(attr, "get_value") else attr
            print(f"  {name} = {val!r}")
        except Exception as e:
            print(f"  {name} = <err {e}>")


def _find_or_create_action(name="CamRotDiag"):
    b = flame.batch
    for n in b.nodes:
        nm = n.name.get_value() if hasattr(n.name, "get_value") else str(n.name)
        if nm == name:
            return n
    return b.create_node("Action", name=name)


def run():
    """Create Action, cycle rotations, dump state."""
    done = threading.Event()

    def _do():
        try:
            action = _find_or_create_action("CamRotDiag")
            cam = action.camera

            print("=" * 70)
            print("CAMERA ATTRIBUTE DUMP (first pass)")
            print("=" * 70)
            _dump_attrs(cam, "cam")

            # Disable target mode so Euler angles are authoritative
            if hasattr(cam, "target_mode"):
                try:
                    cam.target_mode.set_value(False)
                except Exception as e:
                    print(f"target_mode set failed: {e}")

            # Zero position to isolate rotation
            try:
                cam.position.set_value((0.0, 0.0, 0.0))
            except Exception:
                try:
                    cam.position.x.set_value(0.0)
                    cam.position.y.set_value(0.0)
                    cam.position.z.set_value(0.0)
                except Exception as e:
                    print(f"position zero failed: {e}")

            for label, rot in TEST_ROTATIONS:
                print()
                print("=" * 70)
                print(f"ROTATION TEST: {label} = {rot}")
                print("=" * 70)
                try:
                    cam.rotation.set_value(rot)
                except Exception:
                    cam.rotation.x.set_value(rot[0])
                    cam.rotation.y.set_value(rot[1])
                    cam.rotation.z.set_value(rot[2])
                # Give Flame a moment to update
                _try_read_matrix(cam)

            print()
            print("=" * 70)
            print("DONE. Copy everything above between the === lines")
            print("and paste back to the chat.")
            print("=" * 70)

        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"ERROR: {e}")
        finally:
            done.set()

    flame.schedule_idle_event(_do)
    done.wait(timeout=15)


if __name__ == "__main__":
    run()
