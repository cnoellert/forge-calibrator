---
created: 2026-04-29T02:10:00Z
session: 2026-04-28 evening
topic: channel-order full fix + cold-install todo status
---

# Session Passoff — 2026-04-28 evening

## What landed tonight

**Channel-order fix completed.** Bridge probes against four batch clips on portofino, plus visual UAT through Flame Player Rec.709 / ACES SDR view, settled the per-bit-depth Wiretap raw-buffer layout. Replaced the broken `gbr_order` boolean (commit `0dcd772`) with `channel_order: Optional[Literal["RGB", "GBR", "BRG"]]` and a bit-depth auto-detect map.

| bit_depth | format_tag       | raw layout       | perm                | verified via              |
|-----------|------------------|------------------|---------------------|---------------------------|
| 8         | `rgb`            | G B R            | `[2, 0, 1]` GBR     | testImage                 |
| 10        | `rgb`            | R G B            | `[0, 1, 2]` no-op   | testImage10bit            |
| 12        | `rgb_le`         | B R G uint16 LE  | `[1, 2, 0]` BRG     | testImage12bit            |
| 16-float  | `rgb_float_le`   | B R G float16 LE | `[1, 2, 0]` BRG     | C002_260302_C005 (ACEScg) |
| 32-float  | `rgb_float_le`   | B R G float32 LE | `[1, 2, 0]` BRG     | **untested** (no clip)    |

10/12-bit are documented in the empirical map but `decode_raw_rgb_buffer` still returns `None` for those bit-depths (pre-existing scope; calibrator hot path is 8 + float).

**Commits:**
- `6a6df75` fix(260428-q8c) — code + tests + memory + passoff + todo
- `d658dba` docs(quick-260428-q8c) — STATE.md + reconstructed SUMMARY.md

**Tests:** 437 passed, 2 skipped. `grep -rn "gbr_order" --include="*.py"` → 0 matches.

## Cold-install todo status (post-fix)

| Status | Todo | Blocking on |
|--------|------|-------------|
| 🟡 fixed_pending_visual_uat | `2026-04-27-camera-calibrator-preview-channel-order-cast.md` | Final menu-flow UAT on portofino across all four verifying clips |
| 🟡 portofino_verified_pending_flame01 | `2026-04-27-camera-scope-export-nonetype-regression-on-cold-install.md` | flame-01 (RHEL 9 x86_64) cold-install retest at HEAD |
| ⏸️ infra-not-code | `2026-04-27-wiretap-no-route-to-host-blocks-camera-calibrator-on-legacy-.md` | Mount `flame-01` autofs entry OR detect & route via mounted media path; see todo's Solution section |

✅ Closed prior:
- VP solver X+Z (closed via `1412555` + `32c7bfc` — todo at `.planning/todos/completed/2026-04-27-vp-solver-fails-on-x-z-axis-pair.md`)
- Multi-camera picker UAT (closed; in `completed/`)

## Next-session entry points

**(a) Visual UAT for channel-order fix** — open Camera Match menu on portofino against `testImage`, `testImage10bit`, `testImage12bit`, and `C002_260302_C005`. If preview renders cleanly on all four, move the channel-order todo to `done/`. ~5 min of clicking.

**(b) flame-01 cold-install retest** — boot flame-01, pull HEAD, run the camera-scope export flow per the todo's `next_steps`. Outcome (a) closes the camera-scope todo; outcome (b) ships back diag JSON and reopens the debug session.

**(c) Wiretap "No route" workaround** — separate investigation; this is infra drift (autofs mount missing for `flame-01` storage), not a code bug. Two options in the todo's Solution section: mount the autofs entry, or fall through to the mounted media path when `wiretap_rw_frame` fails. Lowest priority of the three.

**(d) 32-bit float verification (passive)** — first time anyone loads a 32-bit float clip on portofino, eyeball the calibrator preview. If it's color-cast, the assumed-BRG default is wrong and we need one more probe. Otherwise the auto-detect map is fully validated.

## State snapshot

- Active branch: `main` at `d658dba`
- forge-bridge: alive at `127.0.0.1:9999` end-of-session
- Active batch on portofino: `testImage`, `testImage10bit`, `testImage12bit`, `A005C008_120101_NQ96`, `C002_260302_C005`, plus calibrator dump artifacts. Bridge namespace holds `_RAW`, `_W`, `_H`, `_BD` from C002 if anything else needs probing without re-extracting.
- Memory crumbs touched tonight: `forge_wiretap_channel_order_by_bit_depth.md` (rewritten with the verified table)

## What this session did NOT do

- **Did not move** the channel-order todo to `done/`. Visual UAT through the actual menu is the gate, not unit tests.
- **Did not commit** the `/tmp/forge_*_perms/` PNG dumps; they're disposable diagnostic artifacts on portofino's filesystem. Will be cleared on the next OS reboot.
- **Did not touch** any flame-01 issues. All work tonight was on portofino.
- **Did not test 32-bit float** — no clip in batch, see (d) above.
