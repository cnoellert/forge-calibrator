---
created: 2026-04-27T20:30:00Z
updated: 2026-04-29T01:30:00Z
status: fixed_pending_visual_uat
passoff: .planning/PASSOFF-channel-order-2026-04-28.md
title: Camera Calibrator preview shows wrong channel order (magenta cast on green/brown plates)
area: image-pipeline
files:
  - forge_core/image/buffer.py:103   # decode_raw_rgb_buffer (channel_order param + bit-depth-keyed BRG/GBR auto-detect)
  - tests/test_image_buffer.py        # regression coverage (parametric per-bit-depth + explicit-override coverage)
  - flame/camera_match_hook.py:223   # raw-buffer call site (no change needed; auto-detect picks up new defaults)
---

## Status (2026-04-29 fix landed)

Per-bit-depth channel_order API landed: 8→GBR, 16→BRG, 32→BRG (assumed). Replaces the
broken `gbr_order` boolean from `0dcd772`. Visual UAT on portofino against four clips
(testImage, testImage10bit, testImage12bit, C002_260302_C005) confirmed the layout map
through Flame Player Rec.709/ACES SDR view; pre-commit unit tests green via
`pytest tests/ -p no:pytest-blender`.

Final menu-flow visual UAT through the actual Camera Match menu on portofino still
pending — DO NOT move this todo to `done/` until that's confirmed. See
`.planning/PASSOFF-channel-order-2026-04-28.md` "Resolution (2026-04-29)" for the
verified table and code-change summary.

## Status (2026-04-29 passoff)

The bit-depth-gated `gbr_order` auto-detect (commit `0dcd772`) **DID NOT fully fix the bug.** It correctly handles the 8-bit path (`testImage` verified) but the float16 path (`A005C008_120101_NQ96` ACEScg) still renders with luminance-dependent hue shift — visible as teal car body where it should be warm-silver, plus pink/red highlights and wrong-colored mountains. Compared to image 32 (Flame's native viewport rendering of the same clip), the calibrator preview has clearly mis-ordered channels even after today's fix.

Bridge probes (all 6 channel permutations through OCIO ACEScg→sRGB on the same body-side region) suggest the float buffer is in **GRB order** (ch0=G, ch1=R, ch2=B), needing a `[1, 0, 2]` swap — NOT the no-swap default the current fix applies. This is unverified against a second clip and was not committed.

See `.planning/PASSOFF-channel-order-2026-04-28.md` for full investigation state, OCIO probe outputs, PNG diagnostic artifacts on `/tmp/`, and resume path for the next session.

---

## Original problem (kept for context)


## Resolution (2026-04-29)

Bridge probes on portofino confirmed the channel-order swap is **bit-depth-dependent**, not blanket-correct as the previous default assumed:

- 8-bit uint8 (testImage probe, `5184×3456`): payload arrives in GBR order, swap is REQUIRED. Pixel 0 reads `(R=154, G=118, B=98)` only after the swap, matching warm-brown stairs.
- float16 (A005C008_120101_NQ96 ACEScg probe, `4448×3096`): payload arrives correctly tagged AND laid out as RGB. Swap was the bug — applying `[2, 0, 1]` on a green-shadow pixel `(0.016, 0.041, 0.025)` produces `(0.025, 0.016, 0.041)` (B-dominant), which through OCIO Rec.709 + sRGB display transform presents as the canonical magenta-on-greens cast.

`decode_raw_rgb_buffer` now defaults `gbr_order=None` and auto-detects: True on uint8, False on float16/float32. The hook's call site doesn't pass the kwarg, so the new auto behavior applies transparently. Tests and custom callers can still force the swap on/off explicitly.

Test suite green: 434 passed, 2 skipped (4 new regression tests added).

Pattern captured in `memory/forge_wiretap_channel_order_by_bit_depth.md`.

**Pending visual UAT:** open the calibrator on `A005C008_120101_NQ96` (or any ACEScg float plate) and confirm the magenta cast is gone. If it is — close this todo. If anything looks wrong, the explicit override `gbr_order=True` is still available as a one-line revert.

---

## Original problem (kept for context)


## Problem

The Camera Calibrator preview displays plates with a clear magenta /
pink cast on what should be brown/green grass and gray road. Reported
on **two separate machines** (flame-01 and portofino) on
2026-04-27 against a 4448x3096 16-bit OpenEXR ACEScg plate
(`B004C006_260302_RNTM`). User identified the symptom as channel-order
related.

This is not an OCIO source-tag mismatch (the dialog correctly shows
"ACEScg" as the Source); the colour cast pattern (magenta/pink where
green should be) is the canonical signature of a Red/Blue swap or a
GBR-vs-RGB confusion.

## Diagnosis (current understanding)

`forge_core/image/buffer.py:103` (`decode_raw_rgb_buffer`) takes a
`gbr_order: bool = True` flag that swaps the channel axis via
`arr[..., [2, 0, 1]]`. The docstring says:

> Default True matches Wiretap's `rgb_float_le` tag — which is
> empirically lying: the bytes are actually in GBR order.

So the code's standing claim is "Wiretap mis-tags GBR as RGB; we
unconditionally swap". If the plate ACTUALLY arrives as RGB on these
machines, applying `[2, 0, 1]` re-orders the channels to BRG, which
would explain the observed magenta cast on grass:
- Grass true colour: high G, mid R, low B
- After `[2, 0, 1]` on (R, G, B): (B, R, G) → put low value in red,
  mid value in green, high value in blue → magenta-blue cast.

**What we don't know yet:**

- Whether the plate ACTUALLY arrives GBR or RGB. The default flag
  was set against Sony/ARRI MXF clips during v6.2 work — OpenEXR
  via Wiretap may behave differently.
- Whether the swap is correct for `extract_frame_bytes`'s container
  path (`decode_image_container`, cv2-based, returns RGB after
  cv2.cvtColor) but wrong for the raw-buffer fallback path on
  EXR-via-Wiretap.
- Whether the OCIO `apply_ocio_or_passthrough` chain re-swaps
  channels somewhere downstream and double-scrambles them.

Reproduces on TWO machines (flame-01 RHEL 9 cold install + portofino
dev workstation), so it's a code-level issue, not environmental drift.
The dev workstation has been tolerating this — the user noticed it
during the rollout-prep verification cycle.

## Reproduction

1. Open Camera Calibrator on a 16-bit OpenEXR ACEScg plate (e.g.,
   B004C006_260302_RNTM, 4448x3096).
2. Observe the preview pane: grass and road have a magenta/pink cast.
3. Compare against Flame's own viewport rendering of the same clip
   in the same colourspace — Flame shows the correct colours.

## Next steps

1. **Confirm the swap direction**: capture one frame's first 12 bytes
   straight from `extract_frame_bytes` for a known-colour plate
   (e.g., a calibration chart with red/green/blue patches) and check
   which channel index actually carries red. This is a one-shot
   bridge probe; no code change needed.
2. **Possible fixes** (depend on (1)):
   a. If EXR plates arrive RGB but Sony MXF arrives GBR: gate the
      swap on bit-depth or container-path (e.g., never swap for the
      cv2-decoded container path, swap only for raw-buffer 8-bit).
   b. If all plates now arrive RGB on this Flame version: drop the
      swap entirely. The "Wiretap mis-tags GBR as RGB" claim may
      have been version-specific to whichever Flame the v6.2 work
      ran against.
   c. If the bug is downstream in OCIO (e.g., `[2, 0, 1]` then
      OCIO transform expecting RGB): pin the OCIO contract and
      verify the swap happens BEFORE OCIO sees the buffer.
3. **Add a test fixture**: drop a synthetic 4-pixel plate with
   known (255,0,0)(0,255,0)(0,0,255)(128,128,128) channels and
   round-trip it through `decode_raw_rgb_buffer`. The colour cast
   bug would have been caught at unit-test time.

## Scope

Visual correctness of the preview matters for the artist UX (line
marking is harder when colours are wrong), but this does NOT affect
the solved camera — the solver operates on luminance / line geometry,
not chroma. Geometric fidelity is intact. So this is a quality-of-life
bug, not a correctness bug. Still worth fixing soon — testers will
flag it on first contact.
