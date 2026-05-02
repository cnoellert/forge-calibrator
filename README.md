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

### Prereqs

- **Flame 2026.2.1** on macOS or Linux (older versions untested; Windows not supported).
- **conda** (any flavor — full Anaconda or miniconda from
  https://docs.conda.io/projects/miniconda/). The installer creates the `forge`
  env from `forge-env.yml` if it is missing.
- **Blender 4.5+** for the Flame↔Blender round-trip leg. Install the addon zip
  per [docs/seamless-bridge.md#for-artists](docs/seamless-bridge.md#for-artists).

### One-line install

```bash
git clone https://github.com/cnoellert/forge-calibrator.git \
    && cd forge-calibrator && ./install.sh
```

The installer is idempotent — safe to re-run. On a host that lacks the `forge`
conda env, it prompts to auto-create from `forge-env.yml`; pass `--yes` for
non-interactive auto-create (CI), or `--force` to skip every prompt.

### Verify

1. Restart Flame. Wait 15-30 s after the splash for the workspace to settle (a
   first-import-after-boot race can crash on the very first round-trip — see
   [docs/seamless-bridge.md#troubleshooting](docs/seamless-bridge.md#troubleshooting)).
2. Probe forge-bridge:
   ```bash
   curl -s http://localhost:9999/ -o /dev/null -w "%{http_code}\n"
   # expect: 200
   ```
3. Right-click any Action in a Batch — confirm the **FORGE → Camera** submenu
   is present.

For the full walkthrough (preflight detail, what deploys where, offline /
air-gapped installs, artist addon setup, and 6+ troubleshooting recipes), see
[docs/seamless-bridge.md](docs/seamless-bridge.md).

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
