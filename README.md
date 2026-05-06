# forge-calibrator

## What this is

A vanishing-point camera calibration tool that lives inside Autodesk Flame. A VFX
artist draws 2-3 reference lines along orthogonal scene edges in a plate; the tool
solves a camera (position, rotation, FOV, focal length) and applies it to a Flame
Action node.

## Core value

**The solved camera must be geometrically faithful to the plate.**

Calibrator is single-purpose — VP solve, full stop. If the numbers are wrong, the
compositing CG won't glue to the plate and the tool fails its job.

## Features

- **VP line tool** — PySide6 line-drawing window over a tone-mapped plate frame.
  Two or three reference lines along orthogonal scene edges; the tool fits each
  vanishing point with least-squares.
- **2VP solve with auto-derived focal length** — closed-form camera intrinsics
  and rotation from two perpendicular vanishing points; principal point assumed
  at image center.
- **Direct Action apply** — solved camera writes straight into the right-clicked
  Flame Action node. Position / rotation (Flame ZYX convention) / FOV / focal
  length all populated.
- **ACES 2.0 plate preview** — single-frame Wiretap read tone-mapped through
  Flame's bundled OCIO config (RRT + ODT + sRGB display) so the artist sees the
  same gamut Flame's viewport shows.

## Install

### Prereqs

- **Flame 2026.2.1** on macOS or Linux (older versions untested; Windows not supported).
- **conda** (any flavor — full Anaconda or miniconda from
  https://docs.conda.io/projects/miniconda/). The installer creates the `forge`
  env from `forge-env.yml` if it is missing.

### One-line install

```bash
git clone https://github.com/cnoellert/forge-calibrator.git \
    && cd forge-calibrator && ./install.sh
```

The installer is idempotent — safe to re-run. On a host that lacks the `forge`
conda env, it prompts to auto-create from `forge-env.yml`; pass `--yes` for
non-interactive auto-create (CI), or `--force` to skip every prompt.

### Verify

Restart Flame. Right-click a clip in a Batch schematic — confirm the
**FORGE → Camera → Open Camera Calibrator** menu entry is present.

## History

For the v4→v6.2 backstory, session recaps, and design decisions that shaped the
current architecture, see [PASSOFF.md](PASSOFF.md).
