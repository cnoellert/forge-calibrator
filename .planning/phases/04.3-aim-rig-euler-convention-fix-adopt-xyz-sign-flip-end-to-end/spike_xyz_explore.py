"""Phase 04.3 Task 1 spike (deeper) — explore which Euler convention reproduces
the hand-decomposed (1.814, 1.058, 1.252) from the look-at output.
"""
import sys
sys.path.insert(0, "/Users/cnoellert/Documents/GitHub/forge-calibrator")

import numpy as np
from forge_core.math.rotations import rotation_matrix_from_look_at

R = rotation_matrix_from_look_at(
    position=(0.0, 57.774681, 2113.305420),
    aim=(0.355065, 57.133656, 2093.318848),
    up=(0.0, 30.0, 0.0),
    roll_deg=1.252521,
)

print("R =")
print(R)
print()

target = (1.814, 1.058, 1.252)
flame_truth = (1.8193, 1.0639, 1.2529)

def decompose_with(label, rx, ry, rz):
    rxd, ryd, rzd = np.degrees([rx, ry, rz])
    dh = (rxd - target[0], ryd - target[1], rzd - target[2])
    df = (rxd - flame_truth[0], ryd - flame_truth[1], rzd - flame_truth[2])
    md = max(abs(x) for x in dh)
    mf = max(abs(x) for x in df)
    print(f"{label:40s}: ({rxd:+.6f}, {ryd:+.6f}, {rzd:+.6f})   maxd_hand={md:.4f}   maxd_flame={mf:.4f}")

# Variant 1: existing _zyx — R = Rz(+rz)·Ry(-ry)·Rx(-rx)
# Substitution α=-rx, β=-ry, γ=+rz → standard ZYX-positive
rx = -np.arctan2(R[2, 1], R[2, 2])
ry = -np.arcsin(-R[2, 0])
rz =  np.arctan2(R[1, 0], R[0, 0])
decompose_with("_zyx (current Free-rig)", rx, ry, rz)

# Variant 2: planned _xyz — R = Rz(-rz)·Ry(-ry)·Rx(-rx)
# α=-rx, β=-ry, γ=-rz → standard ZYX-positive in (α,β,γ)
rx = -np.arctan2(R[2, 1], R[2, 2])
ry = -np.arcsin(-R[2, 0])
rz = -np.arctan2(R[1, 0], R[0, 0])
decompose_with("_xyz planned (rz sign-flip only)", rx, ry, rz)

# Variant 3: TRUE intrinsic XYZ-positive: R = Rx(rx)·Ry(ry)·Rz(rz)
# Standard intrinsic XYZ derivation:
# R[0,2] = sin(ry)
# ry = asin(R[0,2])
# R[0,0] = cos(ry)·cos(rz) → rz = atan2(-R[0,1], R[0,0])
# R[1,2] = -sin(rx)·cos(ry) → rx = atan2(-R[1,2], R[2,2])
ry = np.arcsin(R[0, 2])
rx = np.arctan2(-R[1, 2], R[2, 2])
rz = np.arctan2(-R[0, 1], R[0, 0])
decompose_with("intrinsic XYZ-positive Rx·Ry·Rz", rx, ry, rz)

# Variant 4: extrinsic XYZ-positive: R = Rz(rz)·Ry(ry)·Rx(rx) (= intrinsic ZYX of same triple)
# This is what some conventions call "Euler XYZ" too.
# Already covered by variant 1 with sign flips.

# Variant 5: R = Rx(-rx)·Ry(-ry)·Rz(-rz) — XYZ matrix order, all signs negated
# Substitution α=-rx, β=-ry, γ=-rz → standard XYZ-positive
# β = arcsin(R[0,2]) → ry = -arcsin(R[0,2])
# rx = -atan2(-R[1,2], R[2,2]) = atan2(R[1,2], R[2,2])
# rz = -atan2(-R[0,1], R[0,0]) = atan2(R[0,1], R[0,0])
ry = -np.arcsin(R[0, 2])
rx =  np.arctan2(R[1, 2], R[2, 2])
rz =  np.arctan2(R[0, 1], R[0, 0])
decompose_with("R = Rx(-rx)·Ry(-ry)·Rz(-rz)", rx, ry, rz)

# Variant 6: R = Rx(-rx)·Ry(-ry)·Rz(+rz)  (XYZ with X,Y negated only)
# α=-rx, β=-ry, γ=+rz → standard XYZ-positive in (α,β,γ)
# rx = -atan2(R[1,2], R[2,2])
# ry = -arcsin(R[0,2])
# rz = atan2(-R[0,1], R[0,0])
ry = -np.arcsin(R[0, 2])
rx = -np.arctan2(-R[1, 2], R[2, 2])
rz =  np.arctan2(-R[0, 1], R[0, 0])
decompose_with("R = Rx(-rx)·Ry(-ry)·Rz(+rz)  XYZ-with-XY-neg", rx, ry, rz)

# Variant 7: R = Rx(rx)·Ry(ry)·Rz(rz), basic XYZ with all positive (extrinsic XYZ rotation order)
# Same as variant 3 above with no sign flips on extraction.
# Skip.

# Variant 8: try using scipy if available — known-good reference
try:
    from scipy.spatial.transform import Rotation
    print()
    print("scipy.spatial.transform.Rotation reference (returns degrees):")
    rot = Rotation.from_matrix(R)
    for seq in ["xyz", "XYZ", "zyx", "ZYX", "xzy", "yzx"]:
        triple = rot.as_euler(seq, degrees=True)
        print(f"  {seq}: ({triple[0]:+.6f}, {triple[1]:+.6f}, {triple[2]:+.6f})")
except ImportError:
    print("(scipy not available — skipping)")
