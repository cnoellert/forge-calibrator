---
quick_id: 260428-q8c
description: Fix Wiretap channel-order decoding to be per-bit-depth (channel_order={RGB,GBR,BRG} keyed off bit_depth)
date: 2026-04-29
status: complete
commit: 6a6df75
plan: 260428-q8c-PLAN.md
---

# 260428-q8c — Summary

## Outcome

Replaced the bit-depth-gated `gbr_order: Optional[bool]` parameter with a per-bit-depth `channel_order: Optional[Literal["RGB", "GBR", "BRG"]]` API. Auto-detect picks `GBR` for 8-bit, `BRG` for 16/32-bit float. The previous `0dcd772` "no swap on float" branch produced a G-dominant teal cast on float ACEScg plates; the new BRG default produces R-dominant warm matching the ACES SDR view through Flame's monitor.

## Empirical evidence anchor

Verified via forge-bridge probes + visual UAT through Flame Player monitor on portofino against four batch clips:

| bit_depth | format_tag       | raw layout       | perm                 | clip                       |
|-----------|------------------|------------------|----------------------|----------------------------|
| 8         | `rgb`            | G B R            | `(2, 0, 1)` GBR      | testImage                  |
| 10        | `rgb`            | R G B (post-extract) | `(0, 1, 2)` RGB | testImage10bit             |
| 12        | `rgb_le`         | B R G (uint16 LE) | `(1, 2, 0)` BRG     | testImage12bit             |
| 16-float  | `rgb_float_le`   | B R G (float16 LE) | `(1, 2, 0)` BRG    | C002_260302_C005 (ACEScg)  |
| 32-float  | `rgb_float_le`   | B R G (assumed)  | `(1, 2, 0)` BRG      | (untested)                 |

The 10-bit and 12-bit cases are out of `decode_raw_rgb_buffer`'s current scope (returns `None` for those bit depths via `_BIT_DEPTH_TO_DTYPE`); they're documented in the empirical map but not added as new decode paths.

## Files changed

| File | Change |
|------|--------|
| `forge_core/image/buffer.py` | `gbr_order` → `channel_order`; `_DEFAULT_CHANNEL_ORDER = {8: "GBR", 16: "BRG", 32: "BRG"}`; `_PERMS = {"RGB": None, "GBR": [2,0,1], "BRG": [1,2,0]}`; full docstring rewrite with verified table |
| `tests/test_image_buffer.py` | All `gbr_order=` callsites moved to `channel_order=`; float-no-swap regressions flipped to BRG assertions; new parametric `test_default_channel_order_per_bit_depth` exhausts 8/16/32 |
| `.planning/PASSOFF-channel-order-2026-04-28.md` | Appended `## Resolution (2026-04-29)` section |
| `.planning/todos/pending/2026-04-27-camera-calibrator-preview-channel-order-cast.md` | Status flipped to `fixed_pending_visual_uat` |
| `~/.claude/projects/.../memory/forge_wiretap_channel_order_by_bit_depth.md` | Full rewrite with verified 5-row table and named verifying clips |

## Caller audit

- `flame/camera_match_hook.py:223` — sole production caller; passes no kwargs, so the new BRG-on-float default lands transparently. No edit needed.
- `forge_flame/wiretap.py` — only docstring mention.
- `grep -rn "gbr_order" --include="*.py"` returns 0 matches post-fix.

## Verification

- Test suite: **437 passed, 2 skipped** (was 434 → +3 from new parametric test).
- Run command: `python -m pytest tests/ -p no:pytest-blender -q` (the `-p no:pytest-blender` flag is required per `forge_pytest_blender_session_exit.md`).

## Follow-up

Visual UAT through the actual Camera Match menu on portofino across the four verifying clips (testImage, testImage10bit, testImage12bit, C002_260302_C005). When that confirms no preview cast, move `2026-04-27-camera-calibrator-preview-channel-order-cast.md` from `pending/` to `done/`.

32-bit float remains assumed-but-unverified — first 32-bit clip on portofino will exercise the BRG branch and reveal any deviation.

## Note on this summary

The SUMMARY.md the executor originally wrote was uncommitted inside its worktree and was lost when the worktree was force-removed (it was locked — see `cannot remove a locked working tree, lock reason: claude agent` from the cleanup step). This file was reconstructed from the executor's return message; commit hashes and test counts are verbatim from that report.
