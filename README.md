# forge-calibrator

## What this is

A vanishing-point camera calibration tool that lives inside Autodesk Flame. A VFX
artist draws 2-3 reference lines along orthogonal scene edges in a plate; the tool
solves a camera (position, rotation, FOV, focal length) and applies it to a Flame
Action node. Recent work (v6.x) extends this with a Flame↔Blender camera round-trip
so solved cameras — static or animated — can be refined in Blender and returned
to Flame.

## Core value

**The solved camera must be geometrically faithful to the plate, and the
Flame↔Blender round-trip must preserve that fidelity end-to-end.**

## What's new in v6.3

- **Seamless Flame↔Blender round-trip** — edit the camera in Blender and send it
  back to the target Action without returning to Flame's batch menu. See
  [docs/seamless-bridge.md](docs/seamless-bridge.md) for the walkthrough.
- **forge-bridge autostart** — the bridge starts automatically when Flame boots and
  exits when Flame quits. No manual process management. See
  [docs/seamless-bridge.md#how-forge-bridge-autostart-works](docs/seamless-bridge.md#how-forge-bridge-autostart-works).
- **Blender "Send to Flame" addon** — a one-click button in the Blender 3D viewport
  N-panel (Forge tab) posts the edited camera back to the target Action. Pick an
  existing Action from a dropdown or create a new one inline. See
  [docs/seamless-bridge.md#install](docs/seamless-bridge.md#install) for install
  steps.
- **Camera-node right-click in Action schematic** — right-click a Camera node
  inside an Action's schematic editor → FORGE → Camera → Export Camera to
  Blender, bypassing the picker. Works for both Camera and Camera 3D variants.
- **Collision-guard on stamped-camera return-trip** — the rename block that
  applies the Blender-side camera name to the imported Flame camera now skips
  the rename when the target name is already taken by a sibling, preventing
  the SIGSEGV that would otherwise occur on stamped-camera round-trips
  through populated Actions.

## Install

### One-time prerequisite — `forge` conda env

```bash
conda env create -f forge-env.yml
# or (if `forge` already exists with stale deps):
conda env update -f forge-env.yml --prune
```

The env carries Python 3.11 + numpy + opencv-python. `install.sh` looks for it
at `$HOME/miniconda3/envs/forge` by default; override with `FORGE_ENV=<path>`.

### Per-machine install

- Run `./install.sh` (macOS/Linux). Idempotent — safe to re-run for
  incremental updates. The installer purges stale `.pyc` bytecode across
  `camera_match/`, `forge_core/`, and `forge_flame/` to prevent Flame from
  serving outdated modules between deploys.
- Install the Blender addon: in Blender → Edit → Preferences → Add-ons →
  Install from file → select `tools/blender/forge_sender-v1.3.4.zip` → enable
  "Forge: Send Camera to Flame".
- See [docs/seamless-bridge.md#install](docs/seamless-bridge.md#install) for the
  detailed walkthrough covering preflight checks, what deploys where, and the full
  artist addon setup.

## Validation

Run the E2E smoke test to confirm the complete right-click → edit → Send-to-Flame
loop works on your workstation:

```
./tools/smoke-test/seamless-bridge-smoke.sh
```

The script exits 0 only if every automated step passes and every human-verified step
is answered `y`. Failed steps are listed on exit with a pointer to
[docs/seamless-bridge.md#troubleshooting](docs/seamless-bridge.md#troubleshooting).

## History

For the v4→v6.2 backstory, session recaps, and design decisions that shaped the
current architecture, see [PASSOFF.md](PASSOFF.md).

## Troubleshooting

See [docs/seamless-bridge.md#troubleshooting](docs/seamless-bridge.md#troubleshooting).
