"""Phase 04.3 Task 1 spike — hand-decompose rotation_matrix_from_look_at output
under the new XYZ-signflip convention R = Rz(-rz)·Ry(-ry)·Rx(-rx).

Camera1 reference inputs from CONTEXT.md §specifics (unscaled, world-space,
FBX-stored roll sign).
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Documents", "GitHub", "forge-calibrator")))

# Direct path
sys.path.insert(0, "/Users/cnoellert/Documents/GitHub/forge-calibrator")

import numpy as np
from forge_core.math.rotations import rotation_matrix_from_look_at

R = rotation_matrix_from_look_at(
    position=(0.0, 57.774681, 2113.305420),
    aim=(0.355065, 57.133656, 2093.318848),
    up=(0.0, 30.0, 0.0),
    roll_deg=1.252521,            # FBX-stored sign per CONTEXT.md §specifics
)

# Hand-decompose using XYZ-signflip convention R = Rz(-rz)·Ry(-ry)·Rx(-rx).
# atan2 indices derived symbolically (see plan <symbolic_derivation_for_xyz_decomposer>).
cb = np.sqrt(R[0, 0] ** 2 + R[1, 0] ** 2)
gimbal = cb <= 1e-6
print(f"cb = {cb:.10f}  gimbal = {gimbal}")
if not gimbal:
    rx = -np.arctan2(R[2, 1], R[2, 2])
    ry = -np.arcsin(-R[2, 0])
    rz = -np.arctan2(R[1, 0], R[0, 0])           # NOTE leading minus — sign-flipped vs _zyx
else:
    rx = 0.0
    ry = -np.arcsin(-R[2, 0])
    rz =  np.arctan2(R[0, 1], R[1, 1])           # gimbal: first-arg sign-flipped vs _zyx

rx_deg, ry_deg, rz_deg = np.degrees([rx, ry, rz])
print(f"hand-decomposed XYZ-signflip: ({rx_deg:.8f}, {ry_deg:.8f}, {rz_deg:.8f})")

# Compare to the CONTEXT.md hand-decomposed value (1.814, 1.058, 1.252).
target_hand = (1.814, 1.058, 1.252)
delta_hand = (rx_deg - target_hand[0], ry_deg - target_hand[1], rz_deg - target_hand[2])
print(f"target hand-decomposed: {target_hand}")
print(f"delta from hand:        ({delta_hand[0]:+.6f}, {delta_hand[1]:+.6f}, {delta_hand[2]:+.6f})")

# Compare to Flame viewport ground truth (1.8193, 1.0639, 1.2529).
target_flame = (1.8193, 1.0639, 1.2529)
delta_flame = (rx_deg - target_flame[0], ry_deg - target_flame[1], rz_deg - target_flame[2])
print(f"Flame viewport truth:   {target_flame}")
print(f"delta from Flame:       ({delta_flame[0]:+.6f}, {delta_flame[1]:+.6f}, {delta_flame[2]:+.6f})")

# Branch decision
max_delta_hand = max(abs(d) for d in delta_hand)
max_delta_flame = max(abs(d) for d in delta_flame)
print(f"\nmax |delta| from hand-decomposed: {max_delta_hand:.6f}°")
print(f"max |delta| from Flame truth:     {max_delta_flame:.6f}°")
print(f"\n=== Branch decision ===")
if max_delta_hand <= 1e-3:
    print("Branch A (PASS): all axes within 1e-3° of hand-decomposed (1.814, 1.058, 1.252).")
    print("Convention is the entire culprit — PROCEED to Tasks 2-5 unchanged.")
else:
    print("Branch B (FAIL): hand-decomposed value not reproduced from look-at output.")
    print("Look-at construction has residual basis-construction issue — STOP, write SPIKE,")
    print("surface to user.")
