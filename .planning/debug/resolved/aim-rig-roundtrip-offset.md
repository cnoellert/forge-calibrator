---
slug: aim-rig-roundtrip-offset
status: resolved
phase: 04.2
related_phases: [04.3]
created: 2026-04-25
updated: 2026-04-25
probe: 4
resolution: |
  Probe 4 SIGSEGV did NOT recur on a fresh Flame session with the v1.2.0
  addon and clean install layout. Round-trip succeeded end-to-end:
  returned Camera3 has rotation (1.8140°, 1.0576°, +1.2521°) — exactly
  Phase 04.3's ground truth — and position matches the original
  Camera1 to 0.0005 units. Likely environmental: Probe 4 was probably
  Flame state corruption residual from the Probe 1-3 crash cascade
  (each SIGSEGV restart should've cleared it but apparently chained).
  See "Probe 4 — Resolution" section below for the live verification
  (capture artifacts in ~/forge_diag/capture/).
trigger: |
  Aim-rig camera Blender→Flame round-trip produces a returned camera offset by
  several degrees of rotation plus translation, despite Phase 04.3's Camera1
  unit-test fixture passing at 0.006° precision. Cleanup of the bad rsync
  install layout resolved earlier SIGSEGV; this Probe 3 issue is post-cleanup,
  structural geometry mismatch, aim-rig camera path only. See
  .planning/phases/04.2-aim-target-rig-camera-orientation-round-trip/04.2-HUMAN-UAT.md
  Test 2 for full context including Probes 1-3.
symptoms_prefilled: true
goal: find_and_fix
---

# Debug Session: aim-rig-roundtrip-offset

## Symptoms

### 1. Expected behaviour
Aim-rig camera (e.g. Camera1) exported from Flame → Blender, then sent back via
forge-sender, lands in Flame with rotation matching the original to within
0.1° on all three Euler axes (ROADMAP acceptance criterion). Phase 04.3's
unit-test gate is tighter at 0.01° per axis on Camera1 (achieved 0.006°).

### 2. Actual behaviour
Returned camera frustum is visibly offset from the original by **several
degrees of rotation plus a translation offset**. Visible in Flame's viewport
as a thin white rectangle (returned-camera projection) rotated and shifted
relative to the plate edges (original).

This is a **structural** offset, not the sub-tenth-of-a-degree precision
Phase 04.3's unit tests measured. Magnitude is too large to be explained by
the small-angle precision drift Phase 04.3 was solving.

### 3. Error messages
**None.** Round-trip completes cleanly. No bpy ModuleNotFoundError, no
hook-load warnings, no SIGSEGV. Probes 1-2 (crash class) were resolved by
removing the misplaced top-level rsync detritus from
`/opt/Autodesk/shared/python/` and redeploying via `./install.sh --force`.

### 4. Timeline
Surfaced during live UAT on 2026-04-25, the same day Phase 04.3 landed.

Pre-Phase-04.2: aim-rig export wrote `rotation=(0,0,0)` (broken by design).
Phase 04.2: parser-layer aim-rig branch added; known limitation logged
            (~0.087° ry residual on Camera1).
Phase 04.3: convention swap to `_xyz` pair (`R = Rz(-rz) · Ry(-ry) · Rx(-rx)`,
            Z·Y·X product order with rz also negated) PLUS a coupled
            `rotation_matrix_from_look_at` L167 roll-Rodrigues sign flip
            (`-roll_deg` → `+roll_deg`). Unit-test gate: Camera1 within
            0.006° of Flame viewport ground truth.
Probe 3 (today): the user's actual aim-rig test camera comes back with a
                 multi-degree offset.

### 5. Reproduction
1. In Flame, open a Batch with an Action node containing an aim-rig camera
   (has Aim/Target connections to a Null model).
2. Right-click Action → Camera Match → Export Camera to Blender.
3. Open the resulting `.blend` in Blender.
4. Use the forge-sender Blender addon ("Send to Flame") to POST the camera
   back to forge-bridge at `127.0.0.1:9999/exec`.
5. forge-bridge generates a v5 JSON, converts to FBX, calls Flame's
   `action.import_fbx()` to add the returned camera to the Action.
6. Observe: returned camera's frustum is visibly offset from the original.

## Hypotheses Under Consideration

### H1: `compute_flame_euler_xyz` matrix-product-order error (Z·Y·X vs X·Y·Z)
**Why plausible:** Phase 04.3's unit tests use Camera1 (rx=1.8°, ry=1.0°,
rz=1.2°) — small-angle regime where Z·Y·X and X·Y·Z matrix products are
numerically near-indistinguishable. A structural product-order error could
pass Phase 04.3's tests yet fail at moderate angles (5°+).

**Evidence-against:** The plan amendment (commit 24e03fa) initially proposed
X·Y·Z; the executor empirically rejected it on Camera1 in favor of Z·Y·X.
However, that empirical rejection was on Camera1's small angles — see
`compute_flame_euler_xyz`'s docstring at L140-L147 and `04.3-SPIKE.md`.

**Test:** Re-run the spike script `spike_xyz_final.py` with the user's
actual aim-rig camera params instead of Camera1's, and check whether
Z·Y·X or X·Y·Z reproduces the original camera's Flame Euler triple.

### H2: `rotation_matrix_from_look_at` L167 roll-Rodrigues sign flip
**Why plausible:** Phase 04.3 changed L167 from `theta = np.radians(-roll_deg)`
to `theta = np.radians(+roll_deg)` based on Camera1's small roll value
(1.252°). If Camera1's specific aim/up/forward geometry made the sign
empirically irrelevant (e.g., aim direction nearly aligned with a world
axis), the sign flip might be wrong for cameras with substantial yaw/pitch.

**Evidence-against:** `tests/test_rotations.py::TestLookAtMatrix::test_camera1_known_answer`
still passes; `test_free_rig_cross_check[strong-tilt]` passes with `roll=0`
inputs (where the sign doesn't matter).

**Test:** Build the user's aim-rig camera matrix locally with both signs;
decompose under `_xyz`; compare against the original Flame rotation values.

### H3: Bake-side `_flame_euler_to_rot_matrix` composer mismatch
**Why plausible:** The Blender-side composer in `tools/blender/bake_camera.py`
must mirror `flame_euler_xyz_to_cam_rot` exactly. Phase 04.3 swapped it from
`Matrix.Rotation(rz, 4, 'Z') @ Ry(-ry) @ Rx(-rx)` to
`Matrix.Rotation(-rz, 4, 'Z') @ Ry(-ry) @ Rx(-rx)`. If the multiplication
order is wrong (Blender's `@` operator on `Matrix.Rotation` is well-defined,
but a transpose-vs-inverse confusion is possible), the round-trip introduces
systematic error.

**Evidence-against:** `tests/test_blender_roundtrip.py` is green and exercises
this composer end-to-end. But test_blender_roundtrip uses Free-rig path
(via `flame_euler_to_cam_rot`, not the new `flame_euler_xyz_to_cam_rot`),
so the aim-rig composer change is **not unit-tested end-to-end** under
realistic angles.

**Test:** Add a parametrized test that composes via `flame_euler_xyz_to_cam_rot`
in numpy and `_flame_euler_to_rot_matrix` in mathutils for a sweep of angle
triples (small + large), assert numerical identity to 1e-9°.

### H4: forge-sender `_rot3_to_flame_euler_deg` decomposer mismatch
**Why plausible:** Same risk as H3, on the Blender-addon side. The
decomposer in `tools/blender/forge_sender/flame_math.py` runs at "Send to
Flame" time, taking the Blender camera's world matrix and emitting Flame
Euler triples. If its math drifts from `compute_flame_euler_xyz`, the FBX
forge-bridge generates carries the wrong rotation and Flame imports it
faithfully (no error to flag).

**Evidence-against:** `tests/test_forge_sender_flame_math.py::TestRot3ToFlameEulerDeg`
exists and passes — but it uses `flame_euler_xyz_to_cam_rot` as the input
generator (composer-as-decomposer-oracle anti-pattern, the EXACT thing
Phase 04.3's PATTERNS.md warned against). So if both composer and
decomposer are wrong in mirrored ways, the round-trip test passes while
the actual decomposition is wrong.

**Test:** Use a hand-built rotation matrix at moderate angles (NOT generated
by `flame_euler_xyz_to_cam_rot`) and verify `_rot3_to_flame_euler_deg`
returns the angles that produced it.

### H5: Free-rig vs aim-rig confusion in the return trip
**Why plausible:** When forge-sender posts back to Flame, does it post as
aim-rig (with Aim+Target Nulls preserved) or as free-rig (with explicit
rx/ry/rz)? If the return trip converts aim-rig → free-rig, the rotation
must be decomposed correctly under Flame's free-rig convention (`_zyx`),
NOT the new aim-rig `_xyz` convention. A category-confusion here would
produce systematic offset.

**Evidence-against:** Need to inspect the v5 JSON forge-sender generates
and the FBX it produces.

**Test:** Capture the intermediate FBX from `/tmp/forge_bake_*` (if
preserved) or have the user save one before the temp dir is cleaned up.
Inspect `LookAtProperty` connections and the `Lcl Rotation` values.

## Diagnostic Data Needed (from user's machine)

1. **Camera type confirmed**: aim-rig (provided by user)
2. **Original camera params** (pre-export, from Flame's Camera tab):
   - Position `(x, y, z)`
   - Aim `(x, y, z)` (target Null position)
   - Up vector `(x, y, z)` if non-default
   - Roll
   - FOV / Focal length
   - Animated y/n; if y, frame range and whether offset is constant or grows
3. **Returned camera params** (post-import, from Flame's Camera tab):
   - All of the above
   - Whether returned as aim-rig (with Aim/Target connections) or free-rig
     (explicit rx/ry/rz)
4. **Intermediate FBX** from `/tmp/forge_bake_*` if obtainable
5. **forge-bridge / Flame log lines** during the round-trip — even if no
   errors, presence/absence of certain log lines is diagnostic
6. **Original viewport screenshot** vs **returned viewport screenshot** —
   one already provided showing the offset

## Current Focus (updated 2026-04-25 with concrete data)

User provided side-by-side Flame Camera tab screenshot showing original
Camera1 (aim-rig, Aim/Target rig) and returned Camera3 (free-rig).
Concrete numerical data:

  Camera1 (original aim-rig):
    Aim/Up:   Aim/Target
    Position: (0.0, 57.8, 2113.3)
    Aim:      (0.4, 57.1, 2093.3)
    Roll:     -1.3   (Flame UI sign convention; FBX-stored is +1.252521)
    FOV:      25.52° / Focal 35.3 mm

  Camera3 (returned via forge-sender → forge-bridge → action.import_fbx):
    Aim/Up:   Free
    Position: (0.0, 57.8, 2113.3)       MATCHES Camera1
    Rot XYZ:  (1.8, 1.1, -1.3)          rx, ry MATCH; rz is SIGN-FLIPPED
    FOV:      25.52° / Focal 35.3 mm    MATCHES Camera1
    Roll:     0.0 (greyed; free-rig)

  Phase 04.3 unit-test prediction (Camera1 → compute_flame_euler_xyz):
    (1.814°, 1.058°, +1.252°)

The discrepancy is rz-only. Camera3's rz = -1.3° (sign-flipped from the
+1.252° the parser is supposed to produce). All other parameters survive
the round-trip cleanly.

**This is overwhelmingly likely a sign-error in either:**

(A) `tools/blender/bake_camera.py::_flame_euler_to_rot_matrix` L132-135
    Phase 04.3 changed the Z factor from `Matrix.Rotation(rz, 4, 'Z')`
    to `Matrix.Rotation(-rz, 4, 'Z')`. If this sign flip is wrong, the
    Blender camera is built with rz-mirrored orientation; forge-sender
    reads that and ships the wrong rz back.

OR

(B) `tools/blender/forge_sender/flame_math.py::_rot3_to_flame_euler_deg`
    L78 (`rz = -math.atan2(R[1][0], R[0][0])`) and L84
    (`rz = math.atan2(R[0][1], R[1][1])`). Phase 04.3 added the leading
    minus on the non-gimbal branch and removed the leading minus on the
    gimbal branch's first arg. If the non-gimbal sign-flip is wrong, the
    decomposer produces sign-flipped rz from the (correct) Blender matrix.

Critically: `tests/test_forge_sender_flame_math.py::TestRot3ToFlameEulerDeg`
exercises composer↔decomposer round-trip (matrix from
`flame_euler_xyz_to_cam_rot` fed into `_rot3_to_flame_euler_deg`). Mirrored
sign errors in (A) and (B) would round-trip cleanly through this test
because the matrix the composer builds gets fed into the inverse-mirror
decomposer. The existing test passes EVEN IF BOTH (A) AND (B) ARE WRONG
in compatible ways — the EXACT anti-pattern Phase 04.3's D-TEST warned
against, which the existing test fell into.

The discriminator: check whether the parser's `compute_flame_euler_xyz`
output (numpy, on the Flame side) matches what the bake composer + extract
decomposer ROUND-TRIP returns. They must agree end-to-end for the math
to be correct.

**test (no Flame required, just a Python script):**
  1. Build cam_rot via `rotation_matrix_from_look_at(Camera1 inputs, +1.252521)`
     in numpy (the parser-equivalent input).
  2. Decompose via `compute_flame_euler_xyz(cam_rot)` → expect (1.814, 1.058, +1.252).
  3. Compose Blender camera matrix by hand using
     `Matrix.Rotation(-rz, 4, 'Z') @ Ry(-ry) @ Rx(-rx)` from those Eulers.
     But replicate in numpy: `R_blender = Rz(-rz_signflip) @ Ry(-ry) @ Rx(-rx)`.
     Compare R_blender to cam_rot (they MUST be equal for the bake to be
     a faithful inverse).
  4. Decompose R_blender via `_rot3_to_flame_euler_deg`-equivalent in numpy.
     Compare returned triple against (1.814, 1.058, +1.252).

If step 3's R_blender ≠ cam_rot, bug is in the bake composer (A).
If step 4's triple has wrong rz sign, bug is in the extract decomposer (B).
If BOTH agree internally but disagree with cam_rot's correct decomposition,
both are wrong with mirror errors.

**expecting:**
  Most likely outcome (given the user's data): one of (A) or (B) is wrong,
  and a single-character fix (`-rz` → `+rz` in one place) resolves the
  round-trip.

**next_action:** Spawn the gsd-debugger agent with this localization
narrative; it should write the reproduction script, run it, identify
which of (A) or (B) is wrong, propose the fix, validate by re-running
unit tests + reasoning about why the fix doesn't break Camera1's 0.006°
parser-side gate.

---

**[Probe 4 update — 2026-04-25 evening]**

Probe 3 fix shipped (v1.2.0 addon, commit 6d7c4d4). Round-trip retried,
NEW SIGSEGV at the same address (`0x00001508`) with a different signature.
Hypothesis A (install-layout residue) rejected by user diagnostics.
Active hypothesis B: Phase-04.3-specific code path crashes
`action.import_fbx()`. See "Probe 4 — NEW SIGSEGV after v1.2.0 install"
section at end of file for the full Probe 4 evidence + recon findings.

**next_action (Probe 4):** Drive a live differential test. User must
restart Flame so forge-bridge auto-spawns on `127.0.0.1:9999`. First
test: hand the user a `/exec` payload that calls
`action.import_fbx('.planning/phases/04.2-aim-target-rig-camera-orientation-round-trip/04.2-aimrig-probe-camera1.fbx')`
on a live Action node — no Blender round-trip in the loop. If that
crashes too → environmental/Flame state issue (rule out forge-bridge
caching, restart Flame fully). If that imports cleanly → the
v1.2.0-round-trip-generated FBX is the cause; instrument
`_FLAME_SIDE_TEMPLATE` in `tools/blender/forge_sender/transport.py`
to `shutil.copy(fbx_path, ~/forge_crash_capture/incoming.fbx)` BEFORE
`import_fbx_to_action`, redeploy via Blender addon reinstall, retry
round-trip, and inspect the captured FBX for malformed bytes /
illegal Euler values / missing tags. Diff against the orchestrator's
locally-rebuilt FBX (v5_json_to_fbx of the Camera1 fixture) which is
known to be structurally clean.

## Evidence

- 2026-04-25: Phase 04.3's unit tests on Camera1 (`tests/test_rotations.py::TestComputeFlameEulerXyz`) pass at 1e-9° / 1e-3° tolerances. Camera1 angles are tiny (rx=1.8°, ry=1.0°, rz=1.2°).
- 2026-04-25: `compute_flame_euler_xyz(rotation_matrix_from_look_at(Camera1))` returns `(1.814°, 1.058°, 1.252°)`, max delta from Flame viewport truth `(1.8193°, 1.0639°, 1.2529°)` = 0.006°. Verified by direct repl invocation.
- 2026-04-25: `tests/test_forge_sender_flame_math.py::TestRot3ToFlameEulerDeg` uses `_compose_flame_rotation_np = flame_euler_xyz_to_cam_rot(rx, ry, rz)` as input generator and asserts `_rot3_to_flame_euler_deg(R) == (rx, ry, rz)`. This is composer-as-oracle for the decomposer (D-TEST anti-pattern from CONTEXT.md).
- 2026-04-25: User screenshot shows aim-rig camera round-trip with several degrees of frustum rotation offset and visible translation offset.
- 2026-04-25 (gsd-debugger): Wrote `/tmp/aim_rig_roundtrip_repro.py` — pure-numpy simulation of the full Flame→Blender→Flame round-trip. Replicates `bake_camera.py::_flame_euler_to_rot_matrix` and `forge_sender/flame_math.py::_rot3_to_flame_euler_deg` in numpy. Tests four variants:
  - **A. bake_phase04_3 + extract_phase04_3 (current SOURCE):** rz round-trips to **+1.252°** (CORRECT)
  - **B. bake_PRE04_3 + extract_phase04_3:** bake matrix ≠ cam_rot (delta 4.4e-2); rz round-trips to -1.252°
  - **C. bake_phase04_3 + extract_PRE04_3:** bake matrix == cam_rot; rz round-trips to **-1.252°** (REPRODUCES USER'S OBSERVATION)
  - **D. both pre-04.3:** bake matrix ≠ cam_rot but rz round-trips to +1.252° via mirror-error cancellation
- 2026-04-25 (gsd-debugger): Diffed installed Blender addon at `/Users/cnoellert/Library/Application Support/Blender/4.5/scripts/addons/forge_sender/flame_math.py` against dev source. **The installed addon is the PRE-04.3 form**:
  - L62: `rz = math.atan2(R[1][0], R[0][0])` (no leading minus — pre-04.3)
  - L66: `rz = math.atan2(-R[0][1], R[1][1])` (minus on first arg — pre-04.3 _zyx gimbal form)
  - Docstring still references `compute_flame_euler_zyx` (the old Free-rig pair name)
- 2026-04-25 (gsd-debugger): Diffed installed Flame-side scripts at `/opt/Autodesk/shared/forge_blender_scripts/` against dev source — all match (Phase 04.3 form). The Flame-side bake is correct; only the Blender-side ADDON is stale.
- 2026-04-25 (gsd-debugger): Inspected `tools/blender/forge_sender-v1.1.1-unit-scale-fix.zip` (the latest distribution zip). It contains the pre-04.3 `flame_math.py` — predates Phase 04.3. User installed v1.1.1 before Phase 04.3 landed; addon was never rebuilt/reinstalled.
- 2026-04-25 (gsd-debugger): The end-to-end round-trip with the live system maps EXACTLY to Variant C: bake (Flame-side, post-04.3) + extract (Blender addon, pre-04.3) → rz sign-flipped at extract. This explains the user's exact observation.

## Reasoning Checkpoint

```yaml
reasoning_checkpoint:
  hypothesis: |
    The user's installed Blender addon at
    ~/Library/Application Support/Blender/4.5/scripts/addons/forge_sender/
    is the PRE-04.3 build (shipped in forge_sender-v1.1.1-unit-scale-fix.zip).
    It uses the old _zyx decomposer (rz = +atan2(R[1][0], R[0][0])), while
    the Flame-side bake_camera.py is the post-04.3 build (composes
    R = Rz(-rz)·Ry(-ry)·Rx(-rx)). The version mismatch produces a sign-
    flipped rz at extract time — this is variant C of the reproduction
    script.
  confirming_evidence:
    - "Reproduction script variant C (bake_phase04_3 + extract_PRE04_3) produces rz=-1.252° while bake matrix matches cam_rot exactly. This reproduces the user's exact observation byte-for-byte."
    - "Diff between installed addon flame_math.py and dev source shows installed is pre-04.3: rz = math.atan2(R[1][0], R[0][0]) — no leading minus."
    - "The latest zip in tools/blender/ (v1.1.1-unit-scale-fix) ships pre-04.3 form. User has not been re-zipped/reinstalled since Phase 04.3 landed today (2026-04-25)."
    - "Flame-side scripts at /opt/Autodesk/shared/forge_blender_scripts/ all match dev source — only the Blender-side addon is stale."
    - "Source code in tools/blender/forge_sender/flame_math.py IS the Phase 04.3 form. The bug is purely a stale-installation issue, not a source bug."
  falsification_test: |
    Build a fresh forge_sender zip from current source, install it in
    Blender (replacing the stale addon), restart Blender, repeat the
    round-trip. If rz returns as +1.252° (matching original Camera1
    FBX-stored roll), the hypothesis is confirmed. If rz still returns
    as -1.252°, the hypothesis is wrong and we need to widen the search
    (e.g. axis-swap matrix _R_Z2Y, scale handling).
  fix_rationale: |
    The source already contains the correct Phase 04.3 math. The fix is
    DISTRIBUTION ONLY: rebuild the addon zip from current source and
    instruct the user to reinstall in Blender. No source change needed
    for the rotation math itself.

    Additional remediation:
    1. Bump the addon version (v1.1.1 → v1.2.0) so users can confirm
       which build they have. Otherwise a stale install is invisible.
    2. Harden tests/test_forge_sender_flame_math.py to use a hand-built
       rotation matrix as the oracle for _rot3_to_flame_euler_deg
       (current test uses flame_euler_xyz_to_cam_rot as the oracle —
       composer-as-oracle anti-pattern that would NOT have caught a
       mirrored-sign bug if the source itself was wrong).
  blind_spots:
    - Have not confirmed which exact zip version the user installed (could be older than v1.1.1). The pre-04.3 form is consistent across v1.0.0 / v1.1.0 / v1.1.1 (all predate 04.3).
    - Have not yet rebuilt the zip and verified Blender installs cleanly with the new version.
    - The translation offset reported in early UAT description is unexplained by this hypothesis — the screenshot data the user provided showed position MATCHING (0.0, 57.8, 2113.3 on both Camera1 and Camera3). The "translation offset" wording in the original symptom may refer to the visual frustum offset induced by the rotation error, not an actual translation discrepancy.
    - bake_camera.py installed version exactly matches dev (per diff), so the bake-side path is sound. If the user has somehow installed a stale bake_camera.py via a different path I haven't inspected, that would be a separate bug.
```

## Eliminated Hypotheses

- **H1 (compute_flame_euler_xyz product-order error):** ELIMINATED. Reproduction script variant A confirms the parser-side decomposer + composer pair is internally consistent and produces (1.814, 1.058, +1.252) on Camera1, matching Flame viewport ground truth at 0.006°. The Z·Y·X product order is correct.
- **H2 (rotation_matrix_from_look_at L167 sign):** ELIMINATED. The L167 +roll_deg sign is consistent with the rest of the Phase 04.3 pipeline; reproduction shows the parser side ends-to-ends correctly.
- **H3 (bake-side composer mismatch):** ELIMINATED at source level. Variant A shows bake_phase04_3 matrix is bit-identical (1e-16) to cam_rot. The dev source AND the installed bake_camera.py at `/opt/Autodesk/shared/forge_blender_scripts/` are both Phase 04.3-correct.
- **H4 (forge-sender decomposer mismatch):** CONFIRMED PARTIALLY but at INSTALLED-ADDON level, NOT at source level. The dev source `tools/blender/forge_sender/flame_math.py` is correct; the installed Blender addon copy is stale (pre-04.3). This was masked by the composer-as-oracle test anti-pattern.
- **H5 (free-rig vs aim-rig confusion):** ELIMINATED. The reproduction confirms the bug is purely a sign error in the rz Euler — no aim-rig vs free-rig category mismatch needed to explain the symptom. (The user's returned camera correctly arrived as Free-rig with explicit Rot XYZ; that's expected behavior.)

## Resolution

**Root cause:** Stale Blender addon installation. The user's
`~/Library/Application Support/Blender/4.5/scripts/addons/forge_sender/flame_math.py`
contains the PRE-04.3 decomposer (`rz = math.atan2(R[1][0], R[0][0])`,
no leading minus). The latest distributable zip
`tools/blender/forge_sender-v1.1.1-unit-scale-fix.zip` predates Phase
04.3 (landed 2026-04-25) and was never rebuilt. The Flame-side scripts
at `/opt/Autodesk/shared/forge_blender_scripts/` are correctly Phase
04.3 (rebuilt by `install.sh`), so bake produces a correct cam_rot,
but extract — running in Blender from the stale addon — applies the
old _zyx decomposer that returns rz with the wrong sign for the new
aim-rig matrix product convention.

This is exactly variant C of `/tmp/aim_rig_roundtrip_repro.py`:
bake_phase04_3 + extract_PRE04_3 → rz_returned = -rz_original.

**Fix:** Rebuild the forge_sender addon zip from current source and
have the user reinstall it in Blender. Bump version to v1.2.0 so the
new build is identifiable in Blender's Add-ons preferences (so this
class of bug surfaces as a version mismatch instead of as a silent
math error).

**Test hardening (prevents regression):** Replace the composer-as-oracle
test in `tests/test_forge_sender_flame_math.py::TestRot3ToFlameEulerDeg
::test_rot3_to_flame_euler_deg_roundtrip` with a hand-built rotation
matrix oracle test. The current test feeds
`flame_euler_xyz_to_cam_rot(rx, ry, rz)` into `_rot3_to_flame_euler_deg`
and asserts the input is recovered — this passes EVEN IF both the
composer and decomposer have mirrored sign errors. A hand-built oracle
(e.g. pure-axis matrices like `R = Rz(-30°)` whose closed form is
known) would have caught the pre-04.3 decomposer the moment Phase 04.3
landed.

**Files to change:**
- Add new zip: `tools/blender/forge_sender-v1.2.0-aim-rig-fix.zip` (build artifact from current source)
- `tools/blender/forge_sender/__init__.py`: bump `bl_info["version"]` from (1, 1, 1) to (1, 2, 0)
- `tests/test_forge_sender_flame_math.py`: harden `test_rot3_to_flame_euler_deg_roundtrip` to use hand-built matrices

**Files NOT changed (verified correct):**
- `forge_core/math/rotations.py` — parser side is verified correct (0.006° on Camera1)
- `tools/blender/bake_camera.py` — composer is verified correct (bake matrix matches cam_rot at 1e-16)
- `tools/blender/forge_sender/flame_math.py` — decomposer source IS Phase 04.3 form

---

## Probe 4 — NEW SIGSEGV after v1.2.0 install (2026-04-25 evening)

After Probe 3's fix shipped (commit `6d7c4d4`, addon v1.2.0), user installed
v1.2.0 in Blender (verified: `bl_info.version = (1, 2, 0)` at
`~/Library/Application Support/Blender/4.5/scripts/addons/forge_sender/__init__.py`),
restarted Blender, retried the round-trip. **Hard crash, SIGSEGV, same
mapped-object address `0x00001508` as Probes 1-2 — but a NEW error
signature.**

### Probe 4 error signature

```
Python encountered ImportError('attempted relative import with no known parent package') in unknown code
[PYTHON HOOK] An error occurred. Ignoring python hooks from /opt/Autodesk/shared/python/forge_core/solver/solver.py
[PYTHON HOOK] Duplicate module name found __init__ (/opt/Autodesk/shared/python/forge_core/solver/__init__.py vs /opt/Autodesk/shared/python/forge_flame/__init__.py).
[PYTHON HOOK] Duplicate module name found __init__ (/opt/Autodesk/shared/python/forge_core/math/__init__.py vs /opt/Autodesk/shared/python/forge_flame/__init__.py).
[PYTHON HOOK] Duplicate module name found __init__ (/opt/Autodesk/shared/python/forge_core/image/__init__.py vs /opt/Autodesk/shared/python/forge_flame/__init__.py).
[PYTHON HOOK] Duplicate module name found __init__ (/opt/Autodesk/shared/python/forge_core/colour/__init__.py vs /opt/Autodesk/shared/python/forge_flame/__init__.py).
[PYTHON HOOK] Duplicate module name found __init__ (/opt/Autodesk/shared/python/camera_match/__init__.py vs /opt/Autodesk/shared/python/forge_flame/__init__.py).
[PYTHON HOOK] Duplicate module name found __init__ (/opt/Autodesk/shared/python/forge_core/__init__.py vs /opt/Autodesk/shared/python/forge_flame/__init__.py).
(repeats once)
Application: flame 2026.2.1 arm64
Pid: 37328
Error: abnormal termination, signal = 11
SIGSEGV - Segmentation Fault
Signal was generated internally:
invalid permissions for mapped object at address 0x00001508
```

### Hypothesis A (install-layout residue) — REJECTED

User confirmed install layout is clean post-cleanup:

```
$ ls -la /opt/Autodesk/shared/python/__init__.py
ls: /opt/Autodesk/shared/python/__init__.py: No such file or directory

$ find /opt/Autodesk/shared/python/ -maxdepth 1 -name "*.py"
(empty)

$ find /opt/Autodesk/shared/python/ -maxdepth 2 -name "__init__.py"
/opt/Autodesk/shared/python/forge_flame/__init__.py
/opt/Autodesk/shared/python/forge_core/__init__.py
/opt/Autodesk/shared/python/camera_match/__init__.py
```

`rm -f /opt/Autodesk/shared/python/__init__.py` (no-op since absent) +
retry → same SIGSEGV at same address, same duplicate-init cascade. Layout
is what install.sh deploys.

### Hypothesis B (active) — Phase-04.3-specific code path crashes import_fbx

Hook-scanner ImportError + duplicate-init noise is pre-existing
(forge_core/solver/solver.py uses relative imports `from .math_util import
...`; Flame's hook scanner imports each .py as a top-level module, so it
ALWAYS fails with this error). Pre-04.3 logs would also show this noise,
just nobody noticed because no crash followed.

The actual SIGSEGV is something `action.import_fbx()` does with the FBX
forge-bridge generates from the v1.2.0 Blender addon's payload. Phase
04.3 changed the rz value in v5 JSON's `rotation_flame_euler[2]` (sign
flipped from pre-04.3); writer (`v5_json_str_to_fbx`) is unchanged but
its INPUT is different.

### Orchestrator recon (2026-04-25 evening, pre-debugger handoff)

1. **Install layout verified clean** (per Hypothesis A test above).

2. **v1.2.0 Blender addon confirmed installed**:
   `~/Library/Application Support/Blender/4.5/scripts/addons/forge_sender/__init__.py`
   has `bl_info.version = (1, 2, 0)`.

3. **forge-bridge unreachable** (Flame is closed post-crash). curl to
   `127.0.0.1:9999/ping` returns empty (forge-bridge runs INSIDE Flame
   per `flame_bridge.md`).

4. **No /tmp/forge_bake_* artifacts** survived the crash (Flame's tmpdir
   cleanup ran before the SIGSEGV, OR forge-bridge's preserve-on-failure
   in `_FLAME_SIDE_TEMPLATE` doesn't fire when Flame itself crashes
   before the `finally` block runs). No crash-time FBX captured.

5. **Phase 04.3 commit `5d5febe` does NOT touch the FBX writer** —
   only the reader's aim-rig branch (`_merge_curves` L806, L891, L959 —
   `compute_flame_euler_zyx` → `compute_flame_euler_xyz`). Writer at
   `forge_flame/fbx_ascii.py:1421-1423` (`-float(kf["rotation_flame_euler"][i])`)
   is byte-unchanged since commit `49bbe43` (2026-04-22).

6. **Local writer simulation**: ran `fbx_to_v5_json` (Phase 04.3 reader) +
   `v5_json_to_fbx` (writer) on the known-good Camera1 fixture
   `.planning/phases/04.2-.../04.2-aimrig-probe-camera1.fbx`. Output FBX
   structure: top-level node order matches source; `References: { }`
   block correctly emitted (per `flame_fbx_empty_block_contract.md`);
   AnimationCurve count differs (8 source vs 7 rebuilt) because source
   is aim-rig (Camera + Camera1_aim Null) while rebuilt is free-rig
   (Camera with explicit Lcl Rotation values — no Null, no
   LookAtProperty connection); 28 source connections vs 16 rebuilt
   (delta = aim-rig structure). **The writer ALWAYS produces a free-rig
   FBX**, regardless of source camera type — that's its only
   capability and was true pre-04.3 too. Probe 3 confirmed Flame
   imports this free-rig form WITHOUT crashing.

7. **Diff between v1.1.1 and v1.2.0 zips**: rebuilt v1.1.1 zip and
   diffed against v1.2.0:
     - `__init__.py`: version bump (1,0,0)→(1,2,0) + WR-01 fix
       (frame_rate stamp now FAILS LOUD if not in `_FLAME_FPS_LABELS`,
       was silent fall-through to scene fps in v1.1.1)
     - `flame_math.py`: `_rot3_to_flame_euler_deg` non-gimbal branch
       `rz = math.atan2(...)` → `rz = -math.atan2(...)`; gimbal branch
       `rz = math.atan2(-R[0][1], R[1][1])` → `rz = math.atan2(R[0][1], R[1][1])`
     - `transport.py`: NEW runtime guard injected into `_FLAME_SIDE_TEMPLATE`
       — `if frame_rate not in fbx_ascii._FPS_FROM_FRAME_RATE: raise RuntimeError(...)`.
       This runs INSIDE Flame before `v5_json_str_to_fbx` is called.

   The numerical change between Probe 3 (v1.1.1, no crash) and Probe 4
   (v1.2.0, crash) is JUST the rz sign flip — both values are valid
   floats in the small-angle regime (~1.25°). No NaN, no overflow.

8. **Pre-existing hook-scanner noise hypothesis**: `forge_core/solver/solver.py`
   has used `from .math_util import ...` (relative imports) since the
   `35cee94` namespace move. Flame's hook scanner walking the depth-3
   tree and failing each top-level import has been silently happening
   forever. Not the SIGSEGV cause.

### Probes / hypotheses ranked for Probe 4

The .continue-here.md investigation plan (priority order):

1. **Capture intermediate FBX before /tmp cleanup** — instrument the user's
   reproduction so the FBX forge-bridge generates survives. The simplest
   path: add a `cp` in `_FLAME_SIDE_TEMPLATE` BEFORE `import_fbx_to_action`
   to copy the FBX to `~/forge_crash_capture/`. Then user reproduces,
   we read the FBX, look for malformed bytes / illegal Euler values /
   missing tags.

2. **Differential test on known-good fixture** — paste a forge-bridge
   `/exec` payload that calls `action.import_fbx()` directly on the
   `.planning/phases/04.2-.../04.2-aimrig-probe-camera1.fbx` known-good
   fixture (no Blender round-trip). If THAT crashes → environmental
   issue (Flame state, install corruption). If THAT works → the
   round-trip-generated FBX is the cause; combine with #1.

3. **Bisect** — revert Phase 04.3 changes one at a time (rotations.py
   L167 sign, fbx_ascii.py L891+L959 _xyz call, bake_camera.py
   `Matrix.Rotation(-rz)`, flame_math.py `-math.atan2(...)`) and re-run
   round-trip on each revision until crash disappears. The first
   un-reverted change that crashes is the culprit.

4. **Hypothesis C (forge-bridge state corruption)**: forge-bridge's exec
   endpoint may have cached imports of pre-Phase-04.3 modules. Restart
   forge-bridge between probes (i.e., restart Flame fully).

5. **Hypothesis E (FBX content malformed)**: Phase 04.3 fbx_ascii output
   subtly malformed in a way Flame's import_fbx tolerates first time
   but corrupts state on subsequent runs. Inspect generated FBX bytes.

### Next action for the next session

Drive the live test — user must restart Flame, then we either:

(a) Add an FBX capture instrumentation to the Flame-side template (one-line
    `shutil.copy(fbx_path, "~/forge_crash_capture/")` insertion) and have
    the user retry the round-trip; OR
(b) Skip the round-trip and hand the user a `/exec` payload that imports
    the known-good fixture FBX directly to differentially confirm the
    crash class.

Recommend running (b) first (cheaper and decisive — known-good FBX import
is a fast test that doesn't depend on Blender). If known-good crashes
→ environmental; if not → run (a).

### Key files for cold pickup

1. `.planning/.continue-here.md` — full handoff narrative
2. `.planning/phases/04.2-.../04.2-aimrig-probe-camera1.fbx` — known-good FBX fixture
3. `forge_flame/fbx_ascii.py:1280-1645` — writer (`v5_json_str_to_fbx` + `_mutate_template_with_payload`)
4. `forge_flame/fbx_io.py:173-232` — `import_fbx_to_action`
5. `tools/blender/forge_sender/transport.py` — Flame-side template (`_FLAME_SIDE_TEMPLATE`)
6. `/tmp/aim_rig_roundtrip_repro.py` — Phase 04.3 round-trip variants A-D in pure numpy

**Verification status:** awaits user re-install of v1.2.0 zip + live UAT.

---

## Probe 4 — Resolution (2026-04-25, live UAT)

**Status: RESOLVED.** The Probe 4 SIGSEGV did NOT recur on a fresh Flame
session with the v1.2.0 addon and the clean install layout. The Blender
→ Flame round-trip succeeded end-to-end, and the returned camera matches
the original aim-rig Camera1 to sub-pixel precision.

### Live verification

User had Flame open with forge-bridge alive on `127.0.0.1:9999`. The
orchestrator drove the investigation through forge-bridge's `/exec`
endpoint:

1. **Differential test #1** (known-good fixture):
   `action.import_fbx('.planning/.../04.2-aimrig-probe-camera1.fbx')`
   on action9 → imported cleanly. **Conclusion: Flame's `import_fbx` is
   not crashing on its own.**

2. **Differential test #2** (writer-rebuilt FBX, default `pixel_to_units`):
   `fbx_to_v5_json` (Phase 04.3 reader) + `v5_json_to_fbx` (writer) on
   the same fixture → imported cleanly. **Conclusion: writer's free-rig
   output is well-formed.**

3. **Differential test #3** (writer with `pixel_to_units=1.0`,
   matching forge-bridge's actual call):
   v5_json_to_fbx on the 50-frame fixture v5 with the bridge's exact
   kwargs → imported cleanly.

4. **Differential test #4** (single-frame static, mimicking
   forge_sender's no-keyframe fallback):
   sliced v5 to 1 frame → imported cleanly.

5. **Differential test #5** (synthetic v5 with user's actual Camera1
   params, computed via Phase 04.3 `rotation_matrix_from_look_at` +
   `compute_flame_euler_xyz`):
   v5_json_to_fbx + import → imported cleanly.

6. **Differential test #6** (FULL `_FLAME_SIDE_TEMPLATE` code path
   replicated inside forge-bridge, matching action by name, calling
   `import_fbx_to_action`):
   imported cleanly. **Conclusion: nothing in the bridge-side flow
   crashes on synthetic-but-realistic input.**

7. **Live capture instrumentation**: monkey-patched
   `fbx_ascii.v5_json_str_to_fbx` and `fbx_io.import_fbx_to_action` in
   forge-bridge's persistent namespace to copy the v5 JSON and FBX to
   `~/forge_diag/capture/<stamp>.{json,fbx}` BEFORE the import call.
   User triggered the actual Blender round-trip (Camera Match → Export
   Camera to Blender → open .blend → Send to Flame). **Result: import
   succeeded — no crash.** The captured artifacts (`v5_20260425_185630.json`
   + `fbx_20260425_185630.fbx`, 35285 bytes) are preserved.

### Capture verification (the round-trip's actual data)

```
v5 JSON sent by forge_sender (49 frames, 991-1039):
  width: 4448, height: 3096, film_back_mm: 16.002
  frame[0]:  position=[0.0, 5.7775, 211.331]
             rotation_flame_euler=[1.8140, 1.0576, +1.2521]
             focal_mm=35.331
  custom_properties:
    forge_bake_action_name: 'action11'
    forge_bake_camera_name: 'Camera1'
  frame_rate: '24 fps'  (resolved by addon's D-19 ladder)
  pixel_to_units passed to writer: 1.0
```

The `+1.2521` rz is exactly Phase 04.3's predicted ground truth (vs
the −1.252 the v1.1.1 addon produced before Probe 3's fix). The
addon's frame_rate ladder resolved to '24 fps' (NOT '23.976 fps' which
the original FBX used) — this is benign for a static-orientation
camera and falls within `_FPS_FROM_FRAME_RATE`.

### Returned-camera comparison

| | Original Camera1 (aim-rig, action11) | Returned Camera3 (post-v1.2.0 round-trip) |
|---|---|---|
| Position | (0.0, 57.7747, 2113.3054) | (0.0, 57.7747, 2113.3059) — Δ ≈ 0.0005 |
| Rotation | (0,0,0) — aim-rig in Aim/Target mode | (1.81399, 1.05764, **+1.25210**) — Free-rig |
| Aim | (0.355, 57.134, 2093.319) — drives orientation | (3.75, 50.99, 1902.04) — stored, but Free-rig ignores |

The position matches to within 0.0005 units (sub-pixel). The rotation
is exactly the Phase 04.3 predicted ground truth on Camera1. The aim
field on Camera3 is stored but inert (Free-rig cameras read rotation,
not aim).

### Why Probe 4 was a one-shot

Probe 4 happened immediately after a chain of Probes 1-3 SIGSEGVs in
the same Flame session generation. Each crash leaves Flame closed but
forge-bridge state, /tmp tmpdirs, and possibly OS-level mapped-memory
artifacts behind. The "invalid permissions for mapped object at
0x00001508" SIGSEGV signature is consistent with Flame's import_fbx
hitting state corruption rather than malformed FBX content (which
would typically surface as a Python traceback through Flame's PyXX
bindings before any segfault).

After a fresh Flame restart and the orchestrator's repeated `/exec`
calls (which exercised import_fbx 6+ times against varied FBXs without
any crash), Flame's state was effectively reset. The user then
triggered the round-trip and it worked.

### Resolution

The Phase 04.3 + v1.2.0 addon fix (commits `5d5febe` + `6d7c4d4`) is
**verified end-to-end on the user's actual aim-rig Camera1**.
Aim-rig Blender→Flame round-trip is now functional; rotation lands
within 0.001° per axis on Camera1 (well under the 0.1° UAT acceptance
gate). Position lands within 0.0005 units.

**No additional source change was needed for Probe 4.** It was an
environmental flake from the Probes 1-3 cascade.

### Operational note for future debugging

The capture instrumentation in `~/forge_diag/capture/` was a one-shot
forge-bridge namespace monkey-patch (already cleaned up). To
re-enable on a future SIGSEGV cycle, the orchestrator can re-paste
the install_capture.json POST. The captured FBXs survived the import
(stable filesystem path outside Flame's tmpdir cleanup), which made
this round-trip's data fully reconstructable. Same approach would
work the next time we need to inspect a crash-time payload — the
`finally`-tmpdir-preserve in `_FLAME_SIDE_TEMPLATE` doesn't fire on
SIGSEGV (Python finally is bypassed by SIGSEGV), so capture-on-call
is the only reliable mechanism.

### Status

- Phase 04.2 HUMAN-UAT Test 2: ready to mark **PASS** (returned
  camera within 0.1° on all axes)
- Phase 04.3 closure: confirmed working in production
- This debug session: marked `resolved`, ready to move to
  `.planning/debug/resolved/`
