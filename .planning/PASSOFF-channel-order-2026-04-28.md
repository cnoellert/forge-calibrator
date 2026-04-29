---
created: 2026-04-29T00:55:00Z
status: investigation_paused_partial_fix_landed
todo: .planning/todos/pending/2026-04-27-camera-calibrator-preview-channel-order-cast.md
---

# Passoff — Channel-Order Cast Investigation

## Summary

The original channel-order bug (magenta cast on green/brown plates, EXR ACEScg) is **NOT fully resolved** by today's fix. The fix landed (`0dcd772`) is a real but partial improvement; the float-buffer channel order is more complex than the bit-depth-gated heuristic captures.

**Current shipped state:** `decode_raw_rgb_buffer` auto-detects: 8-bit applies the GBR→RGB swap, float16/32 applies NO swap. Verified correct for `testImage` (8-bit). Verified INSUFFICIENT for `A005C008_120101_NQ96` (16-bit ACEScg) — see evidence below.

## What we know

### 8-bit path (verified correct)
- `testImage` (5184×3456 uint8) needs the GBR→RGB swap `[2, 0, 1]`. Probe: payload byte 0 → `(118, 98, 154)` raw → `(R=154, G=118, B=98)` after swap → matches warm-brown stairs. ✓
- This is the v6.2 "Wiretap mis-tags GBR as RGB" claim, accurate for transcoded/8-bit Wiretap outputs.

### Float16 path (broken — different swap needed)
- `A005C008_120101_NQ96` (4448×3096 float16 ACEScg). Probe with **no swap** for body_side region (3*h//5, w//8) gave raw float = ch0:low, ch1:high, ch2:mid. After OCIO ACEScg→sRGB:
  - **RGB ordering (no swap):** uint8 = (38, 64, 61) — G-dominant teal. Visibly WRONG (image 31).
  - **GRB→RGB (`[1, 0, 2]` swap):** uint8 = (70, 48, 62) — R-dominant warm. Matches expected warm-silver-in-shadow. ✓ likely correct.
  - GBR→RGB (`[2, 0, 1]`, the 8-bit swap): (65, 61, 48) — also R-dominant warm. Plausible.
- PNG dumps with LUTs bypassed in Flame Player (image 34) confirmed: hue shifts BY LUMINANCE — signature of OCIO per-channel tone curve operating on wrong-order data.

### What we tried that didn't work
1. **Bit-depth-gated `gbr_order=None` auto-detect** (committed `0dcd772`): correctly handles 8-bit, but float buffer with NO swap still produces teal. Improved image 30 → 31 (eliminated the magenta-on-shadow split) but didn't reach correctness.
2. **All 6 permutations through OCIO** showed GRB and GBR are the most plausible orderings for float16. Neither matches the 8-bit GBR convention exactly.

### Likely root cause
Wiretap's raw-buffer layout differs by bit-depth:
- 8-bit: GBR (ch0=G, ch1=B, ch2=R) → swap `[2, 0, 1]`
- float16/32: **GRB** (ch0=G, ch1=R, ch2=B) → swap `[1, 0, 2]` — UNVERIFIED but most consistent with our OCIO probes

This needs verification against another float ACEScg plate (different content) to rule out content-specific artifacts, before being committed.

## Open work

1. **Verify GRB-for-float hypothesis** on a second 16-bit or 32-bit float ACEScg clip. Run the same all-6-permutations OCIO probe; pick the permutation that produces the most natural-looking output for known-color regions (sky, road, neutral surfaces).
2. **Update `decode_raw_rgb_buffer`** to apply the right swap per bit-depth instead of just gating gbr_order. Suggested API change: replace `gbr_order: Optional[bool]` with explicit channel permutation mode like `channel_order: Optional[Literal["RGB", "GBR", "GRB"]] = None` with auto-detect mapping bit_depth → channel_order.
3. **Update tests** in `tests/test_image_buffer.py` — the 4 new tests landed today assume "no swap on float" which is wrong per evidence above.
4. **Re-verify on `testImage`** that any new fix doesn't break the 8-bit case.
5. **Visual UAT** on multiple ACEScg plates to confirm fix.

## Diagnostic artifacts on portofino

- `/tmp/forge_calibrator_dump_rgb_interpretation.png` — calibrator's raw uint8 buffer dumped via cv2 (correct interpretation path)
- `/tmp/forge_calibrator_dump_bgr_interpretation.png` — calibrator's buffer with R↔B swapped at write time
- Both dumps are from A005C008 frame 761094, 1112×774 downsample for fast viewing

## State of the repo

HEAD: `0dcd772` — bit-depth-gated `gbr_order` auto-detect + 4 tests + memory crumb. Tests green at 434 passed, 2 skipped. **Do not revert** — the 8-bit path improvement is real and the float-side improvement (eliminated magenta-on-shadow split) is real even if not full correctness.

The `.planning/todos/pending/2026-04-27-camera-calibrator-preview-channel-order-cast.md` was edited in working tree (not committed) to mark `fixed_pending_visual_uat`. That status is now WRONG — the visual UAT failed. The todo should stay in `pending/` and its status field updated to reflect this passoff.

## Other cold-install todos (still open, not blocked by this)

- ✅ Camera-scope NoneType (closed via 4-commit cascade)
- ✅ VP solver X+Z (obsoleted by `1412555` + `32c7bfc`)
- 🔄 **Channel-order cast (this doc — partial fix landed, full fix pending)**
- ⏸️ Wiretap "No route to host" (likely infra)
- ⏸️ flame-01 retest (cross-platform confirmation, no progress yet)

## Memory crumbs landed today (relevant)

- `flame_camera_scope_session_state_decay.md` — restart cures degraded mid-session wrappers
- `flame_calibrator_overlay_axis_label_vs_cross_sign.md` — `_plane_basis` overlay vs solver
- `forge_pytest_blender_session_exit.md` — `pytest -p no:pytest-blender` to bypass blender check
- `flame_perspective_camera.md` — broadened to "intrinsic, not actionable"
- `forge_wiretap_channel_order_by_bit_depth.md` — **needs revision per this passoff** (claims float is RGB-correct; evidence says it's likely GRB)

## Next session entry point

Read this file. Then either:
- (a) Run the GRB-for-float verification probe on a second ACEScg clip via bridge to confirm hypothesis before code change.
- (b) Just ship the GRB swap on float and visually UAT on portofino across 2-3 plates. If correct, lock it in.

The bridge is at `127.0.0.1:9999` and was working at end of this session. The relevant clip is `A005C008_120101_NQ96` in the active batch on portofino.

---

## Resolution (2026-04-29)

Empirical bridge probes against four batch clips on portofino, with visual UAT through
Flame Player's Rec.709 / ACES SDR view, established the per-bit-depth channel-order layout:

| bit_depth | format_tag       | raw layout | perm to recover RGB | verifying clip            |
|-----------|------------------|------------|---------------------|---------------------------|
| 8         | rgb              | G B R      | GBR [2, 0, 1]       | testImage                 |
| 10        | rgb              | R G B      | RGB (no-op)         | testImage10bit            |
| 12        | rgb_le           | B R G u16  | BRG [1, 2, 0]       | testImage12bit            |
| 16-float  | rgb_float_le     | B R G f16  | BRG [1, 2, 0]       | C002_260302_C005 (ACEScg) |
| 32-float  | rgb_float_le     | B R G f32  | BRG [1, 2, 0]       | (assumed; no clip)        |

The previous fix (`0dcd772`) was wrong on float — "no-swap-on-float" produced the
G-dominant teal cast visible in image 31. The float layout is BRG, not RGB. The earlier
GRB-for-float hypothesis from this passoff was also wrong; visual UAT through the Flame
Player monitor (which the OCIO-only probes lacked) made BRG unambiguous.

**Code change:** replaced `gbr_order: Optional[bool]` with
`channel_order: Optional[Literal["RGB", "GBR", "BRG"]]`, with auto-detect
`_DEFAULT_CHANNEL_ORDER = {8: "GBR", 16: "BRG", 32: "BRG"}`. Existing call sites
(`flame/camera_match_hook.py:223`, `forge_flame/wiretap.py`) pass no kwargs and pick up
the corrected auto-detect transparently. Test suite green via
`pytest tests/ -p no:pytest-blender`.

**32-bit float caveat:** assumed-BRG (consistent with float16 layout); no 32-bit clip
in batch to verify against. Revisit if a 32-bit plate ever shows up and the cast is wrong.

**Pending:** final visual UAT through the Camera Match menu flow on portofino across
all four clips. Then the todo at
`.planning/todos/pending/2026-04-27-camera-calibrator-preview-channel-order-cast.md`
moves to `done/`.
