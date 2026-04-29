---
quick_id: 260429-ebd
type: execute
subsystem: image-pipeline
tags: [wiretap, bit-depth, dpx, channel-order, ocio]

# Dependency graph
requires:
  - quick: 260428-q8c
    provides: per-bit-depth channel_order auto-detect (8→GBR, 16/32→BRG)
provides:
  - decode_raw_rgb_buffer support for bd=10 (DPX method A BE) and bd=12 (uint16 /65535)
  - hook dialog branch distinguishing media-path failure from unsupported-bit-depth
affects: image-pipeline, camera-match-hook, future-bit-depths

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pre-tail unify pattern: bit-depth-specific decode produces (arr, channel_order) then a SHARED flip+perm tail handles all paths uniformly"
    - "_BIT_DEPTH_NORMALIZE table: post-load /N normalize keyed off bit_depth (12: 65535.0); future depths add one entry rather than one branch"
    - "Failure-path tuple-slot overload: _read_source_frame returns (None, str_reason, None) on decode reject vs (None, None, None) on Wiretap fail; isinstance() guard keeps callers safe"

key-files:
  created: []
  modified:
    - forge_core/image/buffer.py  # bd=10 / bd=12 decode paths + normalize table
    - tests/test_image_buffer.py  # +7 new tests (round-trip, header-strip, override, no-clamp, coverage gap)
    - flame/camera_match_hook.py  # dialog branch on unsupported_bit_depth reason code

key-decisions:
  - "10-bit packing: DPX method A (>>22 / >>12 / >>2 masks) on big-endian DWORD chosen over R210 BE / R210 LE / DPX LE by spatial-coherence test on 8 consecutive mid-row pixels of testImage10bit."
  - "12-bit normalization: /65535.0 (full uint16 range) NOT /4095.0 (low-12-bit-aligned). Bridge probe showed Wiretap delivers values up to 64508 with non-zero LSBs, contradicting the plan's 'right-aligned in low 12 bits' assumption — Rule 1 deviation."
  - "Failure-path overload: chose to reuse the second tuple slot for the reason code rather than add a 4th tuple element, because every other call site already early-returns on rgb is None and never reads the second slot. Backward-compat preserved with zero call-site churn."

patterns-established:
  - "Bit-depth dispatch table extension: _BIT_DEPTH_TO_DTYPE for simple per-pixel dtypes, _BIT_DEPTH_NORMALIZE for post-load float casts, dedicated branch for non-trivial unpacks (bd=10 packs 3ch into 1 DWORD)."
  - "Reason-code-on-failure tuple-slot overload: backward-compatible if all non-target callers already guard on the first slot; document explicitly in docstring."

requirements-completed:
  - QUICK-260429-EBD-01  # 10-bit packed RGB decode path
  - QUICK-260429-EBD-02  # 12-bit padded uint16 BRG decode path
  - QUICK-260429-EBD-03  # bit-depth-unsupported dialog branch in hook

# Metrics
duration: 6m 36s
completed: 2026-04-29
---

# Quick Task 260429-ebd: 10-bit + 12-bit decode support Summary

**`decode_raw_rgb_buffer` now decodes Wiretap's bd=10 (DPX method A BE packed DWORD → /1023) and bd=12 (uint16 BRG → /65535) plates, and the Camera Match dialog distinguishes "media path inaccessible" from "unsupported bit-depth" so 14-bit / future-unsupported clips surface an actionable error.**

## Performance

- **Duration:** ~6 min (3 commits)
- **Started:** 2026-04-29T17:26:14Z
- **Completed:** 2026-04-29T17:32:50Z (Task 1 + Task 2; Task 3 is human UAT, not bot-completed)
- **Tasks completed by executor:** 2 of 3 (Task 3 is a HUMAN-UAT checkpoint — see "Awaiting Human UAT" below)
- **Files modified:** 3

## Accomplishments

- **bd=10 decode path landed.** DPX method A BE unpack: `R = (DWORD >> 22) & 0x3ff; G = (DWORD >> 12) & 0x3ff; B = (DWORD >> 2) & 0x3ff` on `np.frombuffer(payload, dtype='>u4')`. Returns float32 `(h, w, 3)` normalized `/1023`. Channel order auto = "RGB" (no perm — unpack already lays channels in R,G,B order).
- **bd=12 decode path landed.** uint16 BRG buffer normalized `/65535.0` (NOT `/4095` — bridge probe disagreed with plan). Returns float32 `(h, w, 3)` in `[0, 1]`. Channel order auto = "BRG" (matches float16/32 layout).
- **Hook dialog branch landed.** `_read_source_frame` returns `(None, "unsupported_bit_depth:{bd}", None)` on decoder reject; `_open_camera_match` shows actionable "Camera Calibrator does not yet support N-bit clips" message.
- **7 new tests, all passing.** Total: 444 passed, 2 skipped (was 437; +7 = bd=10 round-trip + header-strip; bd=12 round-trip + header-strip + override + no-clamp; bd=14 coverage gap).
- **Live bridge UAT confirmed clean decode** on portofino against testImage / testImage10bit / testImage12bit / C002_260302_C005 (4 of 4).

## Task Commits

1. **Task 1 RED: Failing tests for bd=10 + bd=12** — `4e96d31` (test)
2. **Task 1 GREEN: bd=10 + bd=12 decode paths** — `d87dc95` (feat)
3. **Task 2: Hook dialog branch on unsupported_bit_depth** — `c25e542` (feat)

(REFACTOR phase not needed — restructure was done in the GREEN commit since the existing function body fit the new shape cleanly without dead code.)

**Plan/state metadata commit:** _to be made by orchestrator (per executor constraints — quick tasks don't commit docs from this agent)._

## Files Modified

- `forge_core/image/buffer.py` — Added bd=10 dedicated branch (DPX method A BE unpack); added bd=12 to `_BIT_DEPTH_TO_DTYPE` (uint16); added new `_BIT_DEPTH_NORMALIZE` table (`{12: 65535.0}`) for post-load /N float32 casts; extended `_DEFAULT_CHANNEL_ORDER` with `10: "RGB", 12: "BRG"`; restructured to a shared flip+perm tail.
- `tests/test_image_buffer.py` — +149 lines: helper `_make_buffer_12bit` (uint16 BRG synth); helper `_make_buffer_10bit` + `_pack_10bit_dpx_methodA_be` (DPX method A BE encoder); 7 new tests; updated `test_unknown_bit_depth_returns_none` from bd=12 → bd=14.
- `flame/camera_match_hook.py` — `_read_source_frame` failure-path tuple now emits `(None, "unsupported_bit_depth:{bd}", None)` on decoder rejection; docstring updated to document second-slot overload contract; `_open_camera_match` dialog now branches `isinstance(img_w, str) and img_w.startswith("unsupported_bit_depth:")` to show actionable message.

## Bridge Probe Results (Task 1 Part A)

**Bridge:** `127.0.0.1:9999/exec` on portofino (alive throughout, no crashes).

### testImage10bit (5184 × 3456, bd=10)

- **Total raw length:** 71,663,632 bytes
- **Expected payload:** `5184 × 3456 × 4 = 71,663,616` (4 bytes per pixel, one 32-bit DWORD per pixel)
- **Header length:** 16 bytes (tail-strip ok)
- **First 16 hex bytes (4 DWORDs):** `9f9dd5e7 9f9d9627 9a9d5627 939c15d7`
- **First 4 DWORDs as integers:**
  - LE: `(3889536415, 664182175, 659987866, 3608517779)`
  - BE: `(2677921255, 2677904935, 2594002471, 2476479959)`
- **Four candidate decodes for first 4 pixels:**
  | Scheme | masks | first-4-pixel RGB triples |
  |---|---|---|
  | R210_BE_high30 | `>>20/>>10/>>0` on BE | `(505,885,487) (505,869,551) (425,853,551) (313,773,471)` |
  | r210_LE_high30 | `>>20/>>10/>>0` on LE | `(637,359,415) (633,423,415) (629,423,410) (369,359,147)` |
  | **DPX_methodA_BE** ← chosen | `>>22/>>12/>>2` on BE | `(638,477,377) (638,473,393) (618,469,393) (590,449,373)` |
  | DPX_methodA_LE | `>>22/>>12/>>2` on LE | `(927,345,871) (158,361,871) (157,361,870) (860,345,804)` |

- **Discriminator:** 8 consecutive mid-row pixels in `DPX_methodA_BE` show smooth gradients in all 3 channels: `(610,477,353) (606,473,349) (594,477,357) (582,465,345) (574,465,349) (562,453,337) (562,453,345) (554,433,329)`. R210_BE has coherent G but jumpy R/B; the LE candidates produce noise.
- **Whole-frame stats (DPX method A BE):** R∈[0, 1007], G∈[0, 943], B∈[0, 923]; means R=549.13, G=511.69, B=419.76 (warm-leaning, consistent with brown-stair test image).

### testImage12bit (5184 × 3456, bd=12)

- **Total raw length:** 107,495,440 bytes
- **Expected payload:** `5184 × 3456 × 6 = 107,495,424` (6 bytes per pixel = uint16 × 3 channels)
- **Header length:** 16 bytes
- **uint16 stats:** min=0, max=64508, mean=31613.24
- **Low-nibble distribution:** roughly uniform across 0–15 (NOT zero-padded). High-4-bit divided gives max 4031 (< 4095), confirming 12-bit dynamic range spread to full uint16, NOT right-aligned in low 12 bits.
- **Three candidate normalizations:**
  | normalization | min | max | result |
  |---|---|---|---|
  | `/4095` | 0.0 | **15.75** | wrong (saturated to white) |
  | **`/65535`** ← chosen | 0.0 | **0.984** | correct |
  | `(arr >> 4) / 4095` | 0.0 | 0.984 | equivalent, more verbose |

This contradicts the plan's "uint16 padded to 12 bits in [0, 4095]" assumption. Rule 1 deviation applied — see "Deviations from Plan" below.

### Live decode UAT (Task 1 verify gate)

After force-reloading `forge_core.image.buffer` from the worktree path into Flame's `sys.modules`, decode_raw_rgb_buffer was called against all 4 portofino test clips:

| clip | bd | dtype | shape | min | max | mean | result |
|---|---|---|---|---|---|---|---|
| testImage | 8 | uint8 | (3456, 5184, 3) | 0 | 251 | **123.00** | ok |
| testImage10bit | 10 | float32 | (3456, 5184, 3) | 0 | 0.984 | **0.4824** | ok |
| testImage12bit | 12 | float32 | (3456, 5184, 3) | 0 | 0.984 | **0.4824** | ok |
| C002_260302_C005 | 16 | float16 | (2880, 5120, 3) | 0 | 2.010 | 0.1161 | ok (ACEScg float, not the same plate) |

**Cross-validation:** the 8/10/12-bit clips are the same source image transcoded; `testImage`'s mean of 123/255 = `0.4824` matches the 10-bit and 12-bit means to 4 decimal places. Three independent decode paths converging on the identical mean intensity is the strongest cross-check of correctness.

## 10-bit Unpack Code Snippet (for reference)

```python
# bd=10: DPX method A, big-endian DWORD, low 2 bits padding.
# Bridge-verified on portofino testImage10bit (2026-04-29).
sample_size = 4  # one 32-bit DWORD per pixel
expected = width * height * sample_size
if len(raw_bytes) < expected:
    return None
payload = raw_bytes[-expected:]
dwords = np.frombuffer(payload, dtype=">u4").reshape(height, width)
r = ((dwords >> 22) & 0x3ff).astype(np.float32) / 1023.0
g = ((dwords >> 12) & 0x3ff).astype(np.float32) / 1023.0
b = ((dwords >>  2) & 0x3ff).astype(np.float32) / 1023.0
arr = np.stack([r, g, b], axis=-1)
# channel_order auto for bd=10 = "RGB" (no perm — unpack lands channels in R,G,B).
# Falls through to common flip+perm tail.
```

## Test Count Delta

- **Before:** 437 passed, 2 skipped (per plan)
- **After:** 444 passed, 2 skipped
- **Delta:** +7 tests, exactly matching the planned count

New tests in `tests/test_image_buffer.py::TestDecodeRawBuffer`:
1. `test_bit_depth_12_round_trip` — uint16 BRG decode + /65535 normalize + BRG perm
2. `test_bit_depth_12_strips_header_via_tail_slice` — 16-byte header strip on bd=12
3. `test_bit_depth_12_explicit_channel_order_overrides_auto` — force `channel_order="RGB"` bypass
4. `test_bit_depth_12_does_not_clamp_out_of_range` — uint16=65535 → 1.0 exact
5. `test_bit_depth_10_round_trip` — DPX method A BE pack/unpack within 1e-3 (one 10-bit step)
6. `test_bit_depth_10_strips_header_via_tail_slice` — 16-byte header strip on bd=10
7. `test_bit_depth_14_returns_none` — coverage gap locks unsupported-bit-depth → None

Existing test `test_unknown_bit_depth_returns_none` updated: bd=12 → bd=14 (since bd=12 is now supported).

## Decisions Made

- **DPX method A BE for 10-bit unpack** — chosen over R210 BE / R210 LE / DPX LE by spatial-coherence test on 8 consecutive mid-row pixels of testImage10bit. Only DPX method A BE produced smooth gradients in all 3 channels.
- **/65535 (not /4095) for 12-bit normalization** — Rule 1 deviation. Bridge probe showed Wiretap delivers full-range uint16 with non-zero LSBs, not right-aligned 12-bit values. The plan's `/4095` would have over-saturated everything to white (max 15.75).
- **Reason-code-on-failure tuple-slot overload** — chose to reuse the second tuple slot rather than add a fourth element, because all other call sites already early-return on `rgb is None` and never read the second slot. Backward-compat preserved with zero churn at non-target sites.
- **bd=10 dedicated branch (not in `_BIT_DEPTH_TO_DTYPE`)** — three 10-bit channels packing into one 32-bit DWORD doesn't fit the single-dtype-per-pixel model. Dedicated branch keeps the table clean and the dispatch logic obvious.
- **`_BIT_DEPTH_NORMALIZE` as a separate table** — extends cleanly for future bit-depths (e.g. if 14-bit ever lands as uint16 zero-padded in low 14 bits, add `_BIT_DEPTH_NORMALIZE[14] = 16383.0`). Keeps normalization concerns separate from dtype dispatch.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] 12-bit normalization: /4095 was wrong; correct is /65535**

- **Found during:** Task 1 Part A bridge probe on testImage12bit.
- **Issue:** Plan's `<action>` block specified `arr.astype(np.float32) / 4095.0` and described 12-bit as "uint16 padded to 12 bits in [0, 4095]." Bridge probe of the actual Wiretap buffer disagreed: max value observed was 64508 (≈ 65535, not ≈ 4095), and low-nibble distribution was uniform across 0–15 (NOT zero-padded). The data is full-range uint16, not right-aligned 12-bit.
- **Fix:** Set `_BIT_DEPTH_NORMALIZE[12] = 65535.0`. The 12-bit dynamic range is preserved (high 4 bits ≤ 4031 < 4095) but distributed across the full uint16 range, presumably by Wiretap doing `(value_12bit << 4) | (value_12bit >> 8)` to fill the LSBs. Either way, `/65535` is the correct normalization to map the data into `[0, 1]`.
- **Files modified:** `forge_core/image/buffer.py` (`_BIT_DEPTH_NORMALIZE = {12: 65535.0}`), `tests/test_image_buffer.py` (`test_bit_depth_12_round_trip` uses `/65535.0` not `/4095.0`).
- **Verification:** Three independent decode paths (8/10/12-bit) produce identical mean intensity (0.4824) on the same source plate, confirming the normalization is correct. Plan's `/4095` would have produced means of `~7.7` (saturated white) on 12-bit.
- **Committed in:** `d87dc95` (Task 1 GREEN).

---

**Total deviations:** 1 auto-fixed (1 Rule 1 bug — wrong constant in plan).
**Impact on plan:** Critical correctness fix. The /4095 normalization would have made testImage12bit unrenderable (saturated white), producing a different bug than the original "media-path failure" — visible as a totally different failure mode in the human UAT. The bridge probe caught it before any human visual UAT was needed.

## Issues Encountered

- **Bridge module-reload nuance.** The first attempt to UAT the new decoder via the bridge picked up the **installed** `/opt/Autodesk/shared/python/forge_core/image/buffer.py`, not the worktree version, because that module was already in `sys.modules`. A simple `importlib.reload(B)` doesn't change which file the loader pulls from — `sys.path.insert(0, ...)` only affects fresh imports. Workaround: `del sys.modules[k]` for each `forge_core.image*` key, then `import forge_core.image.buffer` afresh. Documented inline in the bridge probe code so future probes against worktree code don't trip on the same gotcha.

## Awaiting Human UAT (Task 3 — checkpoint:human-verify, NOT executor-completed)

Per executor constraints, Task 3 is a **HUMAN-UAT checkpoint** that the bot must NOT mark complete. Prerequisites for the human:

### Step 1 — Install (executor recommendation; human runs the command)

```bash
cd /Users/cnoellert/Documents/GitHub/forge-calibrator
./install.sh --force
```

This refreshes `/opt/Autodesk/shared/python/{forge_core,forge_flame,camera_match,tools/blender}/` and purges stale `__pycache__/` (sibling-pycache fix per `memory/forge_install_pycache_gap.md`).

**NOTE:** `install.sh --force` is an outstanding pending todo item from the cold-install verification cycle — the worktree code has not been installed live yet. The user must do this before UAT.

### Step 2 — Pick ONE of:

- **(a) Restart Flame** (cleanest — picks up `flame/camera_match_hook.py` menu-handler changes; required if the dialog branch behavior is part of the test)
- **(b) In-process reload via the install.sh snippet** (faster but hook menu callbacks won't re-bind; user must right-click a fresh node to pick up the new menu handler)

Per `memory/flame_module_reload.md`, option (a) is safer.

### Step 3 — On portofino's active batch, in this order:

1. Right-click `testImage` clip → Camera Match → Open Camera Match. **Expect:** preview renders cleanly, no color cast, no error dialog. (bd=8 sanity check; was passing before this fix.)
2. Right-click `testImage10bit` clip → Camera Match → Open Camera Match. **Expect:** preview renders cleanly, no color cast. (NEW — was generic media-path error before.)
3. Right-click `testImage12bit` clip → Camera Match → Open Camera Match. **Expect:** preview renders cleanly, no color cast. (NEW — was generic media-path error before.)
4. Right-click `C002_260302_C005` clip → Camera Match → Open Camera Match. **Expect:** preview renders cleanly, no color cast. (bd=16 ACEScg sanity check; was passing before this fix.)
5. (If a 14-bit / 24-bit / otherwise-unsupported clip exists on the batch — A005 maybe?) Right-click → Open Camera Match. **Expect:** dialog says "Camera Calibrator does not yet support N-bit clips" — NOT the generic "media path is inaccessible" message. If no such clip is available, skip; the unit test (`test_bit_depth_14_returns_none`) locks the behavior.

### Step 4 — On UAT pass, the human moves the pending todo to done

The pending todo at `.planning/todos/pending/2026-04-27-camera-calibrator-preview-channel-order-cast.md` (frontmatter `status: fixed_pending_visual_uat`) should be moved to `.planning/todos/done/` ONLY after the human visual UAT clears (steps 1–4 above). The bot left it in `pending/` per executor constraints.

Before moving, change the frontmatter status from `fixed_pending_visual_uat` → `closed`.

### Step 5 — Update PASSOFF

Brief PASSOFF entry recommended noting:
- "32-bit float still untested live (no clip on batch); the assumed-BRG default will be validated opportunistically per PASSOFF entry (d)."
- "10/12-bit decode paths landed and bridge-verified; full menu-flow UAT pending human."

## 32-bit Float Status (Carry-Forward)

Per the PASSOFF entry (d), 32-bit float is **still untested live** — no 32-bit clip exists on portofino's active batch. The `_DEFAULT_CHANNEL_ORDER[32] = "BRG"` is assumed-consistent with float16 because both are tagged `rgb_float_le` by Wiretap, but this hasn't been visually verified. Carry-forward: when a 32-bit float clip first lands in batch, open it through Camera Match and confirm no color cast. If wrong, the explicit override `channel_order="GBR"` or `"RGB"` is available as a one-line revert.

## Self-Check: PASSED

**Files claimed to be modified — verified present and modified:**
- `forge_core/image/buffer.py` — modified (bd=10/12 paths, normalize table)
- `tests/test_image_buffer.py` — modified (+7 new tests, bd=14 update)
- `flame/camera_match_hook.py` — modified (dialog branch)

**Commits claimed — verified present in git log:**
- `4e96d31` (test RED) — present
- `d87dc95` (feat GREEN) — present
- `c25e542` (feat hook branch) — present

**Test counts — verified:**
- Before: 437 passed, 2 skipped (per plan claim and 260428-q8c summary)
- After: 444 passed, 2 skipped (verified via `pytest tests/ -p no:pytest-blender`)
- Delta +7 matches.

**Bridge UAT — verified:**
- 4 of 4 portofino clips returned non-None ndarrays of correct shape, dtype, and value range.
- Cross-validation: 8/10/12-bit clips converge on identical mean (0.4824) — strongest possible correctness check.

**Threat surface scan:** No new network endpoints, auth paths, file access patterns, or schema changes. Decoder and dialog text only — internal trusted-storage tool per CLAUDE.md security posture.

## TDD Gate Compliance

Plan was tagged `tdd="true"` on Task 1. Gate sequence verified:
- ✅ RED: `4e96d31` (`test(quick-260429-ebd): add failing tests...`) — 4 tests fail before implementation
- ✅ GREEN: `d87dc95` (`feat(quick-260429-ebd): add 10-bit + 12-bit decode paths...`) — all tests pass after implementation
- (REFACTOR not needed — restructure was done as part of GREEN)

## Next Phase Readiness

- **All three executor-completable tasks done.** Code shipping; 444 tests green; bridge probe live-verified against 4 portofino clips.
- **Blocker for closure:** human UAT through actual menu flow on portofino (per Task 3 checkpoint and constraints). Until that clears, the channel-order pending todo stays in `pending/`.
- **Future work surfaced:** 32-bit float live UAT (no clip available); install.sh sibling-pycache discipline (existing pending item, unaffected by this quick).

---
*Quick task: 260429-ebd*
*Completed (executor portion): 2026-04-29*
*Awaiting: install + human menu-flow UAT on portofino*
