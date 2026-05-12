---
quick_id: 260512-calibrator-scene-scale
status: complete
date: 2026-05-12
---

# Calibrator scene scale and origin projection

## Goal

Make calibrator output manageable Flame values by adding a scene scale factor that scales world-space camera and helper-axis positions without changing solved projection geometry.

## Diagnosis

The adapter currently defaults to Flame-native pixel units: camera distance is `h / (2 * tan(vfov/2))`, so 8K plates can naturally produce camera translations in the thousands or tens of thousands. This is geometrically faithful but awkward in Action. Scaling all world positions by a uniform factor preserves projection while making numbers manageable.

The origin control is not a world-position picker; it chooses the image pixel that Flame world origin `(0, 0, 0)` should project through. A uniform scene scale should keep that projection fixed.

## Scope

- Add scene scale to the adapter and hook UI.
- Apply the same scale to camera position and dropped helper axes.
- Keep FOV, focal, rotation, VP solve, and origin pixel unchanged.
- Add focused tests for projection invariance and scale output.
