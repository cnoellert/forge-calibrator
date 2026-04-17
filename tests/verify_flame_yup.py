"""
End-to-end verification: feed the test.fspy fixture through the Flame solver
(VP1=-X, VP2=-Y, Y-up) and check that:
  1. R reconstructed from Flame Euler matches the original cam_rot      (Euler decomp correct)
  2. World axes project back to the user-marked VP pixels                (full rotation correct)
  3. Camera position matches fSpy's clean Y-up output (4.36, 4.29, 7.97) (translation correct)
     after rescaling from cam_back=10 to fSpy's reported scale.

Reference: fSpy with VP1=-x, VP2=-y on the test.fspy fixture reports
  position = (4.360661, 4.289890, 7.970780)
  axis-angle = (-0.7565, 0.6318, 0.1690), angle = 36.03625 deg
  hfov = 47.98872 deg, vfov = 33.05551 deg, focal = 25.04994 mm (sensor 22.3x14.9)
"""
import sys
import os
import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from flame.camera_match_hook import _solve_lines

# fSpy fixture: same lines as tests/test_cross_validate.py
W, H = 5184, 3456

VP1_LINE1_P1_REL = (0.42601555503030025, 0.40415286833528946)
VP1_LINE1_P2_REL = (0.9000365618654662,  0.5454031009322207)
VP1_LINE2_P1_REL = (0.41739415081491654, 0.04953202027892652)
VP1_LINE2_P2_REL = (0.9507110122414305,  0.14287330297426987)

# Third VP lines (used for FromThirdVanishingPoint principal point)
VP3_LINE1_P1_REL = (0.27460364961614336, 0.3697670902400505)
VP3_LINE1_P2_REL = (0.034850686400703726, 0.6025881122656513)
VP3_LINE2_P1_REL = (0.5599874891798862,  0.7298908694518256)
VP3_LINE2_P2_REL = (0.46349688070409634, 0.943814342052108)


def rel_to_px(rx, ry):
    return [rx * W, ry * H]


# VP1 lines: list of ((x0,y0), (x1,y1)) pairs
vp1_lines = [
    (rel_to_px(*VP1_LINE1_P1_REL), rel_to_px(*VP1_LINE1_P2_REL)),
    (rel_to_px(*VP1_LINE2_P1_REL), rel_to_px(*VP1_LINE2_P2_REL)),
]
# Quad mode synthesizes vp2_lines from vp1 endpoints, so pass empty list
vp2_lines = []
vp3_lines = [
    (rel_to_px(*VP3_LINE1_P1_REL), rel_to_px(*VP3_LINE1_P2_REL)),
    (rel_to_px(*VP3_LINE2_P1_REL), rel_to_px(*VP3_LINE2_P2_REL)),
]

# Origin pixel from test.fspy (controlPointsStateBase.origin in rel coords)
ORIGIN_REL = (0.425954240741137, 0.4039816947015791)
origin_px = rel_to_px(*ORIGIN_REL)

# axis indices: -X=1, -Y=3 (Flame Y-up); quad_mode=True (matches fSpy file)
result = _solve_lines(
    vp1_lines, vp2_lines, W, H,
    ax1=1, ax2=3,
    origin_px=origin_px, cam_back=10.0,
    vp3_lines=vp3_lines, quad_mode=True,
)

assert result is not None, "solver returned None"

print("=" * 70)
print("FLAME SOLVER OUTPUT (VP1=-X, VP2=-Y, cam_back=10)")
print("=" * 70)
print(f"position    : {tuple(round(x, 6) for x in result['position'])}")
print(f"rotation deg: {tuple(round(x, 4) for x in result['rotation'])}")
print(f"focal mm    : {round(result['focal_mm'], 4)}  (fSpy reports 25.0499)")
print(f"hfov deg    : {round(result['hfov_deg'], 4)} (fSpy reports 47.9887)")
print(f"vfov deg    : {round(result['vfov_deg'], 4)} (fSpy reports 33.0555)")

# Reload trace to inspect intermediates
import json
with open("/tmp/forge_camera_match_trace.json") as fp:
    trace = json.load(fp)

print()
print("=" * 70)
print("CHECK 1: R reconstructed from Flame Euler matches cam_rot_flame")
print("=" * 70)
print(f"R_recon_matches_cam_rot_flame: {trace['stages']['R_recon_matches_cam_rot_flame']}")

print()
print("=" * 70)
print("CHECK 2: World axes project to user-marked VP pixels")
print("=" * 70)
proj = trace['stages']['world_axis_projections']
vp1_px = trace['stages']['vp1_px']
vp2_px = trace['stages']['vp2_px']

print(f"VP1 (fitted) at pixel: ({vp1_px[0]:.1f}, {vp1_px[1]:.1f})")
print(f"  -X projects to    : {proj['-X'].get('pixel', proj['-X'])}")
print(f"  +X projects to    : {proj['+X'].get('pixel', proj['+X'])}")
print(f"VP2 (fitted) at pixel: ({vp2_px[0]:.1f}, {vp2_px[1]:.1f})")
print(f"  -Y projects to    : {proj['-Y'].get('pixel', proj['-Y'])}")
print(f"  +Y projects to    : {proj['+Y'].get('pixel', proj['+Y'])}")

# Numeric assertion: -X axis must land within 1 pixel of VP1, -Y within 1 pixel of VP2
neg_x_proj = np.array(proj['-X']['pixel'])
neg_y_proj = np.array(proj['-Y']['pixel'])
vp1_arr = np.array(vp1_px)
vp2_arr = np.array(vp2_px)
err_x = np.linalg.norm(neg_x_proj - vp1_arr)
err_y = np.linalg.norm(neg_y_proj - vp2_arr)
print(f"  -X projection error vs VP1: {err_x:.4f} px")
print(f"  -Y projection error vs VP2: {err_y:.4f} px")

print()
print("=" * 70)
print("CHECK 3: Position matches fSpy's Y-up output (rescaled)")
print("=" * 70)
# Our cam_back=10 matches fSpy's DEFAULT_CAMERA_DISTANCE_SCALE=10, so positions
# should match fSpy directly (no rescale needed).
fspy_pos = np.array([4.360661, 4.289890, 7.970780])
our_pos = np.array(result['position'])
err_pos = np.linalg.norm(our_pos - fspy_pos)
print(f"fSpy position : {tuple(fspy_pos)}")
print(f"our position  : {tuple(round(float(x), 6) for x in our_pos)}")
print(f"error (units) : {err_pos:.6f}")

print()
print("=" * 70)
print("VERDICT")
print("=" * 70)
ok = (
    trace['stages']['R_recon_matches_cam_rot_flame']
    and err_x < 1.0
    and err_y < 1.0
    and err_pos < 0.05
)
print("ALL CHECKS PASSED" if ok else "FAILURES — see above")
sys.exit(0 if ok else 1)
