"""Phase 04.3 Task 1 spike (final) — found candidate convention.

Discovered: with positive-roll convention in look-at + extrinsic xyz extraction,
the magnitudes match (1.814, 1.058, 1.252) — the hand-decomposed value.
Now test combinations to find the unique combo that produces +1.814, +1.058, +1.252
without sign flips.
"""
import sys
sys.path.insert(0, "/Users/cnoellert/Documents/GitHub/forge-calibrator")

import numpy as np
from scipy.spatial.transform import Rotation

target_hand = (1.814, 1.058, 1.252)
target_flame = (1.8193, 1.0639, 1.2529)

# Build the look-at matrix manually with controllable sign for roll
def build_R(roll_sign):
    """Build look-at R using a configurable roll sign.
    roll_sign = -1 reproduces the current rotation_matrix_from_look_at;
    roll_sign = +1 is the alternative."""
    position = np.array([0.0, 57.774681, 2113.305420])
    aim = np.array([0.355065, 57.133656, 2093.318848])
    up_ref = np.array([0.0, 30.0, 0.0])
    roll_deg = 1.252521

    forward = (aim - position) / np.linalg.norm(aim - position)
    right = np.cross(forward, up_ref)
    right = right / np.linalg.norm(right)
    up_cam = np.cross(right, forward)

    theta = np.radians(roll_sign * roll_deg)
    ct, st = np.cos(theta), np.sin(theta)
    right_rolled = right * ct + np.cross(forward, right) * st
    up_rolled = up_cam * ct + np.cross(forward, up_cam) * st

    R = np.column_stack((right_rolled, up_rolled, -forward))
    return R


def report(label, rxd, ryd, rzd):
    dh = (rxd - target_hand[0], ryd - target_hand[1], rzd - target_hand[2])
    df = (rxd - target_flame[0], ryd - target_flame[1], rzd - target_flame[2])
    md = max(abs(x) for x in dh)
    mf = max(abs(x) for x in df)
    sign_flag = ""
    if all(d <= 0.01 for d in (abs(rxd) - target_hand[0], abs(ryd) - target_hand[1], abs(rzd) - target_hand[2])):
        sign_flag = " [magnitudes match!]"
    print(f"{label:60s}: ({rxd:+.6f}, {ryd:+.6f}, {rzd:+.6f})  hand={md:.4f}  flame={mf:.4f}{sign_flag}")


for roll_sign in [-1, +1]:
    R = build_R(roll_sign)
    print(f"=== roll_sign={roll_sign:+d} ===")
    for seq in ["xyz", "XYZ", "zyx", "ZYX", "xzy", "yzx"]:
        try:
            triple = Rotation.from_matrix(R).as_euler(seq, degrees=True)
            report(f"  {seq}", triple[0], triple[1], triple[2])
        except Exception as e:
            print(f"  {seq}: ERROR {e}")
    print()

# So if (-1.814, -1.058, -1.252) at roll_sign=+1, xyz works,
# we need to flip ALL three signs for the final convention. That means:
# R = sign-flip-all(xyz extraction) of [look-at with roll_sign=+1]
# Equivalently: rx = -extrinsic_x(R), ry = -extrinsic_y(R), rz = -extrinsic_z(R)
# where R uses roll_sign=+1 in look-at.
#
# Or even simpler: the existing rotation_matrix_from_look_at with its
# current roll_sign=-1 gives R, and we want to extract R such that it matches
# (1.814, 1.058, 1.252). The relation between R(roll_sign=-1) and R(roll_sign=+1)
# is that one is the transpose-related rotation about forward by 2*roll.

print()
print("=== Final candidate: use existing look-at (roll_sign=-1) and try sign-flipped extrinsic xyz ===")
R_existing = build_R(-1)
triple = Rotation.from_matrix(R_existing).as_euler("xyz", degrees=True)
rx, ry, rz = triple
print(f"existing R extrinsic xyz: ({rx:.6f}, {ry:.6f}, {rz:.6f})")
# negate all three:
print(f"negated:                  ({-rx:.6f}, {-ry:.6f}, {-rz:.6f})")
# negate first two:
print(f"first two negated:        ({-rx:.6f}, {-ry:.6f}, {rz:.6f})")
# Try with R built using opposite roll
R_alt = build_R(+1)
triple = Rotation.from_matrix(R_alt).as_euler("xyz", degrees=True)
print(f"alt R(roll=+) xyz:        ({triple[0]:.6f}, {triple[1]:.6f}, {triple[2]:.6f})")
print(f"alt R(roll=+) xyz negated:({-triple[0]:.6f}, {-triple[1]:.6f}, {-triple[2]:.6f})")
