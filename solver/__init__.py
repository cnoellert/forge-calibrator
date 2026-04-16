"""
Flame Camera Match Solver

Camera calibration from vanishing points, ported from fSpy.
Reference: Guillou, Meneveaux, Maisel, Bouatouch —
"Using Vanishing Points for Camera Calibration and Coarse 3D Reconstruction
from a Single Image" (IRISA)
"""

from .coordinates import px_to_image_plane, image_plane_to_px
from .math_util import (
    line_intersection,
    orthogonal_projection_on_line,
    orthocentre,
)
from .solver import (
    compute_focal_length,
    compute_camera_rotation_matrix,
    axis_assignment_matrix,
    compute_view_transform,
    compute_translation,
    solve_2vp,
    solve_1vp,
)
