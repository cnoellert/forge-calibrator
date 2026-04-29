---
quick_id: 260429-ebd
type: execute
wave: 1
depends_on: []
files_modified:
  - forge_core/image/buffer.py
  - tests/test_image_buffer.py
  - flame/camera_match_hook.py
autonomous: false   # final task is a HUMAN-UAT checkpoint
requirements:
  - QUICK-260429-EBD-01  # 10-bit packed RGB decode path
  - QUICK-260429-EBD-02  # 12-bit padded uint16 BRG decode path
  - QUICK-260429-EBD-03  # bit-depth-unsupported dialog branch in hook

must_haves:
  truths:
    - "decode_raw_rgb_buffer(bit_depth=10) returns a (h, w, 3) float32 array (values normalized to [0, 1])"
    - "decode_raw_rgb_buffer(bit_depth=12) returns a (h, w, 3) float32 array (values normalized to [0, 1])"
    - "decode_raw_rgb_buffer rejects bit_depth=14 (and any other unmapped depth) by returning None"
    - "_read_source_frame distinguishes 'media path failed' from 'decode rejected unsupported bit_depth' so the dialog can show the right message"
    - "Camera Match menu opens cleanly (no color cast) on a 10-bit clip (testImage10bit) and a 12-bit clip (testImage12bit) on portofino"
    - "Camera Match menu on a 14-bit (or otherwise unsupported) clip surfaces an unsupported-bit-depth dialog, NOT the generic media-path message"
  artifacts:
    - path: "forge_core/image/buffer.py"
      provides: "decode_raw_rgb_buffer with 10-bit + 12-bit paths"
      contains: "bit_depth == 10"
      contains_alt: "bit_depth == 12"
    - path: "tests/test_image_buffer.py"
      provides: "Round-trip + header-strip tests for bd=10 and bd=12"
      contains: "test_bit_depth_10_round_trip"
      contains_alt: "test_bit_depth_12_round_trip"
    - path: "flame/camera_match_hook.py"
      provides: "Branched dialog message for unsupported-bit-depth vs media-path failure"
      contains: "unsupported_bit_depth"
  key_links:
    - from: "forge_core/image/buffer.py:decode_raw_rgb_buffer"
      to: "_BIT_DEPTH_TO_DTYPE / _DEFAULT_CHANNEL_ORDER"
      via: "bit_depth dispatch"
      pattern: "bit_depth\\s*==\\s*(10|12)"
    - from: "flame/camera_match_hook.py:_read_source_frame"
      to: "_open_camera_match dialog"
      via: "tuple return shape — (None, '<reason>', None) on decode failure"
      pattern: "unsupported_bit_depth"
---

<objective>
Add 10-bit and 12-bit decode paths to `decode_raw_rgb_buffer`, then teach the
hook to differentiate "Wiretap could not deliver bytes" (legitimate media-path
error) from "Wiretap delivered bytes but we don't support this bit_depth"
(actionable user-facing message). Closes `.planning/todos/pending/2026-04-27-camera-calibrator-preview-channel-order-cast.md` for the bit-depth axis.

Purpose: testImage10bit and testImage12bit currently fail to preview with the
generic "media path is inaccessible" dialog, even though the media path is
fine — the decoder just rejects those bit_depths. Both paths are recorded in
the empirical layout map (verified live 2026-04-28 on portofino) but the dtype
tables in `_BIT_DEPTH_TO_DTYPE` were never extended. This quick wires them up.

Output:
- `forge_core/image/buffer.py` extended with bd=10 (R210/DPX-style packed
  unpack) and bd=12 (uint16 BRG /4095 normalize) paths.
- `tests/test_image_buffer.py` extended with round-trip + header-strip tests
  for both new bit-depths plus a coverage-gap test (bd=14 → None) that locks
  the unsupported-fallthrough behavior.
- `flame/camera_match_hook.py:_read_source_frame` returns a reason code on
  decode failure so the dialog can branch.
- `./install.sh --force` run at end so live Flame on portofino picks up the
  changes.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/PASSOFF-2026-04-28-night.md
@CLAUDE.md
@forge_core/image/buffer.py
@tests/test_image_buffer.py
@flame/camera_match_hook.py

<interfaces>
<!-- Extracted from forge_core/image/buffer.py — already at HEAD with channel_order API.
     Executor should not need to re-explore the codebase. -->

Current decode_raw_rgb_buffer signature (forge_core/image/buffer.py:115):
```python
def decode_raw_rgb_buffer(
    raw_bytes: bytes,
    width: int,
    height: int,
    bit_depth: int,
    channels: int = 3,
    channel_order: Optional[Literal["RGB", "GBR", "BRG"]] = None,
    bottom_up: bool = True,
) -> Optional[np.ndarray]:
```

Current dispatch tables (forge_core/image/buffer.py:94-112):
```python
_BIT_DEPTH_TO_DTYPE = {
    8:  np.uint8,
    16: np.float16,
    32: np.float32,
}
_DEFAULT_CHANNEL_ORDER = {8: "GBR", 16: "BRG", 32: "BRG"}
_PERMS = {"RGB": None, "GBR": [2, 0, 1], "BRG": [1, 2, 0]}
```

Current _read_source_frame return contract (flame/camera_match_hook.py:200-239):
```python
# Returns (img_rgb_uint8, width, height) on success
# Returns (None, None, None) on:
#   - extract_frame_bytes failure (Wiretap CLI failure, missing node_id, etc.)
#   - decode_raw_rgb_buffer rejection (unsupported bit_depth, undersized buffer)
```

Current dialog block (flame/camera_match_hook.py:307-313):
```python
if img_rgb is None:
    flame.messages.show_in_dialog(
        title="Camera Calibrator",
        message="Could not read frame from clip source. "
                "Check the clip's media path is accessible.",
        type="error", buttons=["OK"])
    return
```

Empirical layout (verified 2026-04-28 on portofino, recorded in
forge_core/image/buffer.py docstring — DO NOT re-derive):

| bit_depth | bytes/pixel    | format       | layout              | channel perm |
|-----------|----------------|--------------|---------------------|--------------|
| 8         | 1.0            | rgb          | G B R uint8         | GBR [2,0,1]  |
| 10        | 4.0            | rgb          | packed 32-bit DWORD | RGB no-op*   |
| 12        | 6.0            | rgb_le       | B R G uint16 LE     | BRG [1,2,0]  |
| 16-float  | 6.0            | rgb_float_le | B R G float16 LE    | BRG [1,2,0]  |
| 32-float  | 12.0 (assumed) | rgb_float_le | B R G float32 LE    | BRG [1,2,0]  |

*10-bit channel order needs bridge-probe verification before the unpack lands —
the table records "RGB no-op" from the empirical map but the bit-layout within
the DWORD is the actual unknown. Likely R210 (Apple, big-endian, 10/10/10/2)
or DPX-method-A (10/10/10/2 LSB padding). Bridge probe in Task 1 verifies.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Probe 10-bit packing via bridge, then implement bd=10 + bd=12 decode paths</name>
  <files>forge_core/image/buffer.py, tests/test_image_buffer.py</files>

  <behavior>
    bd=12 (trivial, no probe needed):
    - Test 1 (round-trip): synth uint16 BRG buffer with values in [0, 4095],
      decode with bd=12 and channel_order=None (auto BRG), expect float32
      array equal to (src/4095.0)[..., [1,2,0]] within atol=1e-6.
    - Test 2 (header-strip): prepend 16 bytes of garbage; decode result
      identical to no-header case.
    - Test 3 (explicit channel_order overrides auto): force RGB; result
      bypasses the BRG perm.
    - Test 4 (out-of-range clamp NOT applied): values >4095 are not produced
      by Wiretap (it pads with zeros at the high bits) but a synthesized
      uint16=8000 should normalize to 8000/4095 ≈ 1.953 — DO NOT clip in
      the decoder; OCIO/passthrough handles clamping downstream.

    bd=10 (probe-first, then implement):
    - Test 5 (round-trip): synth a packed buffer using the unpack scheme
      verified by the bridge probe, with known RGB triplets at known pixel
      positions; decode with bd=10 and channel_order=None; expect float32
      array equal to (src/1023.0) within atol=1e-3 (one 10-bit step).
    - Test 6 (header-strip): same buffer with prepended garbage decodes
      identically.

    Coverage gap (locks unsupported behavior so the hook branch in Task 2
    is testable):
    - Test 7: decode_raw_rgb_buffer(b"\x00"*1024, 4, 4, bit_depth=14)
      returns None (already true today; locks it explicitly).
    - Update existing test_unknown_bit_depth_returns_none in
      tests/test_image_buffer.py: it currently asserts bd=12 returns None.
      Change that case to bd=14 (or any unmapped value), since bd=12 is
      now supported. Keep the test intent: "unmapped bit_depth → None".
  </behavior>

  <action>
    PART A — Bridge-probe the 10-bit layout BEFORE writing any unpack code.
    The forge-bridge is alive on portofino at 127.0.0.1:9999/exec
    (see memory/flame_bridge.md). Probe testImage10bit:

    ```python
    # POST to http://127.0.0.1:9999/exec
    {
      "code": (
        "import flame, struct\n"
        "clip = next(c for c in flame.batch.nodes if c.name == 'testImage10bit')\n"
        "fmt = clip.versions[0].tracks[0].segments[0].source_clip.format\n"
        "from forge_flame.wiretap import extract_frame_bytes\n"
        "raw, w, h, bd = extract_frame_bytes(clip, 1)\n"
        "payload = raw[-(w*h*4):]  # 10-bit is 4 bytes/pixel (DWORD)\n"
        "# Sample first row, first 4 pixels — read as little- AND big-endian DWORDs\n"
        "le = struct.unpack('<4I', payload[:16])\n"
        "be = struct.unpack('>4I', payload[:16])\n"
        "(w, h, bd, len(raw), len(payload), le, be)"
      )
    }
    ```

    From the four DWORDs, decode candidate bit-layouts and pick the one
    that produces sane RGB values (each 10-bit channel should be in [0,
    1023] and the spatial pattern should make sense for testImage10bit).
    The four candidates to test in the probe response:

    1. **R210 big-endian (Apple/Quicktime):** `r = (be>>20)&0x3ff; g = (be>>10)&0x3ff; b = be&0x3ff` (high 30 bits used, low 2 padding)
    2. **r210 little-endian:** same masks on `le` instead of `be`.
    3. **DPX method A (10/10/10/2, MSB-first):** `r = (be>>22)&0x3ff; g = (be>>12)&0x3ff; b = (be>>2)&0x3ff` (low 2 bits padding)
    4. **DPX method A LE-byteswapped:** same masks on `le`.

    Pick the candidate whose channels (a) all fall in [0, 1023], (b) do
    not look like noise (variance across the 4 sample pixels suggests an
    image, not random bits). Record the chosen scheme + masks in the
    decoder docstring. If none of the four work, post a follow-up probe
    that prints `payload[:16]` as hex; do not guess.

    PART B — Implement bd=12 path in `decode_raw_rgb_buffer`:

    ```python
    if bit_depth == 12:
        # 6 bytes/pixel = uint16 padded to 12 bits in [0, 4095].
        # Layout per empirical table: B R G uint16 LE.
        sample_size = 2  # uint16
        expected = width * height * channels * sample_size
        if len(raw_bytes) < expected:
            return None
        payload = raw_bytes[-expected:]
        arr = np.frombuffer(payload, dtype=np.uint16).reshape(height, width, channels)
        arr = arr.astype(np.float32) / 4095.0
        # Then fall through to the existing flip/perm pipeline below.
    ```

    Refactor cleanly — DO NOT special-case 12-bit at the top with its own
    return path. Instead, extend `_BIT_DEPTH_TO_DTYPE[12] = np.uint16`,
    add `_DEFAULT_CHANNEL_ORDER[12] = "BRG"` (matches empirical map), and
    introduce a small post-load normalize step keyed on bit_depth:

    ```python
    _BIT_DEPTH_NORMALIZE = {12: 4095.0}  # divide by this and cast to float32
    ```

    After `arr = np.frombuffer(...)`, if `bit_depth in _BIT_DEPTH_NORMALIZE`,
    do `arr = arr.astype(np.float32) / _BIT_DEPTH_NORMALIZE[bit_depth]`
    BEFORE the flip+perm steps. This keeps the flip+perm code path
    unchanged.

    PART C — Implement bd=10 path. 10-bit doesn't fit the
    `_BIT_DEPTH_TO_DTYPE` model because the DWORD packs three channels;
    handle it as a dedicated branch at the top of the function:

    ```python
    if bit_depth == 10:
        sample_size = 4  # one 32-bit DWORD per pixel
        expected = width * height * sample_size
        if len(raw_bytes) < expected:
            return None
        payload = raw_bytes[-expected:]
        # Unpack scheme verified via bridge probe — see chosen scheme above.
        # Example for R210 big-endian:
        dwords = np.frombuffer(payload, dtype=">u4").reshape(height, width)
        r = ((dwords >> 20) & 0x3ff).astype(np.float32) / 1023.0
        g = ((dwords >> 10) & 0x3ff).astype(np.float32) / 1023.0
        b = ( dwords        & 0x3ff).astype(np.float32) / 1023.0
        arr = np.stack([r, g, b], axis=-1)
        # Channel order: 10-bit empirical map says RGB no-op, BUT the unpack
        # already places channels in R,G,B order. So channel_order auto for
        # bd=10 must be "RGB" (no perm). Then fall through to flip/perm.
        if channel_order is None:
            channel_order = "RGB"
        # Skip the dtype/_BIT_DEPTH_TO_DTYPE path entirely.
        # ... continue to bottom_up flip + perm at end of function ...
    ```

    Restructure so the 10-bit branch joins the common flip+perm tail
    rather than duplicating it. One clean way: compute `arr` and resolved
    `channel_order` in a single pre-tail block, then have ONE flip+perm
    tail that handles both the integer/float fast path and the 10-bit
    unpacked path uniformly.

    Add `_DEFAULT_CHANNEL_ORDER[10] = "RGB"` for documentation symmetry
    even though the unpack already lands in RGB order.

    PART D — Update the docstring's empirical layout table to mark bd=10
    and bd=12 as IMPLEMENTED (remove the "10/12-bit dtype isn't wired up
    in `_BIT_DEPTH_TO_DTYPE` today" caveat). Note the verified 10-bit
    unpack scheme + the bridge probe date.

    PART E — Extend `tests/test_image_buffer.py` with the 7 tests in the
    `<behavior>` block. Use `_make_buffer_12bit` and `_make_buffer_10bit`
    helpers that mirror the existing `_make_buffer` style — synthesize
    a buffer where each pixel encodes its position so flips/perms are
    visible by eye. For 10-bit, the helper packs a known RGB triplet
    into the chosen scheme (e.g. R210 big-endian) so the round-trip
    test inverts what the decoder will do.

    Update `test_unknown_bit_depth_returns_none` to assert bd=14 (not
    bd=12) returns None, since bd=12 is now supported.
  </action>

  <verify>
    <automated>cd /Users/cnoellert/Documents/GitHub/forge-calibrator && conda run -n forge pytest tests/test_image_buffer.py -p no:pytest-blender -v</automated>
    Expected: all existing tests still pass, plus 7 new tests for bd=10 / bd=12 / bd=14-coverage-gap pass.

    Bridge UAT (executor runs after pytest passes, before commit):
    POST to 127.0.0.1:9999/exec — for each of testImage (bd=8),
    testImage10bit (bd=10), testImage12bit (bd=12), C002_260302_C005
    (bd=16): call `extract_frame_bytes(clip, 1)` then
    `decode_raw_rgb_buffer(raw, w, h, bd)` and confirm:
      - return is non-None ndarray
      - shape is (h, w, 3)
      - dtype is np.uint8 for bd=8, np.float32 for bd=10/12, np.float16
        for bd=16
      - values are in expected range ([0, 255] uint8; [0, 1] for the
        normalized float paths in the testImage* synthetic plates)

    Record bridge probe results inline in the SUMMARY.md (executor
    writes SUMMARY at end of plan).
  </verify>

  <done>
    - `_BIT_DEPTH_TO_DTYPE` has entry for 12 (uint16); 10 handled as
      dedicated branch
    - `_DEFAULT_CHANNEL_ORDER` has entries for 10 (RGB) and 12 (BRG)
    - `decode_raw_rgb_buffer(raw, w, h, 10)` returns float32 (h, w, 3) in [0, 1]
    - `decode_raw_rgb_buffer(raw, w, h, 12)` returns float32 (h, w, 3) in [0, 1]
    - `decode_raw_rgb_buffer(raw, w, h, 14)` returns None
    - All 437+ existing tests still pass; 7 new tests pass
    - Bridge probe against 4 portofino clips returns correctly-shaped arrays
    - Docstring's empirical layout table updated to remove the
      "not wired up" caveat for 10/12-bit; verified-on-date noted for bd=10
  </done>
</task>

<task type="auto">
  <name>Task 2: Branch the hook dialog between media-path failure and unsupported-bit-depth</name>
  <files>flame/camera_match_hook.py</files>

  <action>
    Surgically modify `_read_source_frame` (around lines 199-239) and the
    one caller in `_open_camera_match` (around lines 305-313).

    PART A — Change `_read_source_frame` return contract:
    - Success: `(img_rgb_uint8, width, height)` — UNCHANGED
    - Wiretap/extract_frame_bytes failure: `(None, None, None)` — UNCHANGED
    - decode_raw_rgb_buffer rejection: NEW — `(None, "unsupported_bit_depth:{bd}", None)`

    Implementation:

    ```python
    extracted = extract_frame_bytes(clip, target_frame)
    if extracted is None:
        return None, None, None  # media path / Wiretap CLI failure
    raw, w, h, bit_depth = extracted

    img = decode_image_container(raw)
    if img is not None:
        return img, int(img.shape[1]), int(img.shape[0])

    arr = decode_raw_rgb_buffer(raw, w, h, bit_depth)
    if arr is None:
        # Wiretap delivered bytes but our decoder rejects this bit_depth.
        # Surface the reason so the caller can show an actionable dialog.
        print(f"decode_raw_rgb_buffer rejected buffer "
              f"({len(raw)} bytes, {w}x{h}, bit_depth={bit_depth})")
        return None, f"unsupported_bit_depth:{bit_depth}", None

    # ... rest unchanged ...
    ```

    Update the docstring's "Returns" line to document the new shape.

    PART B — Update `_open_camera_match`'s caller (around line 305):

    ```python
    img_rgb, img_w, img_h = _read_source_frame(
        clip, source_colourspace=initial_source_cs)
    if img_rgb is None:
        # img_w carries either None (media-path) or a reason code string
        # (decode rejection). Branch the dialog accordingly.
        if isinstance(img_w, str) and img_w.startswith("unsupported_bit_depth:"):
            bd = img_w.split(":", 1)[1]
            message = (f"Camera Calibrator does not yet support "
                       f"{bd}-bit clips. Supported bit-depths: 8, 10, 12, 16, 32. "
                       f"If this clip really is one of those, please file a bug.")
        else:
            message = ("Could not read frame from clip source. "
                       "Check the clip's media path is accessible.")
        flame.messages.show_in_dialog(
            title="Camera Calibrator",
            message=message,
            type="error", buttons=["OK"])
        return
    ```

    Note: `img_w` is the second tuple slot. We're overloading it as
    "either an int width or a reason code string" only on the failure
    path where img_rgb is None — successful calls always return int.
    The caller's `isinstance(img_w, str)` guard makes the branch safe.

    Document this in `_read_source_frame`'s docstring: "On failure the
    second slot may be a string reason code; callers must check before
    using it as an int width."

    No other callers of `_read_source_frame` need to change — they all
    early-return on `img_rgb is None`. Verify with grep:

    ```bash
    grep -n "_read_source_frame" flame/camera_match_hook.py
    ```

    Expected: definition site + the one call in `_open_camera_match` +
    possibly one or two more call sites (frame-spinner refresh, side
    panel). For each non-error-handling caller, ensure the success path
    still works (img_w is an int when img_rgb is non-None).
  </action>

  <verify>
    <automated>cd /Users/cnoellert/Documents/GitHub/forge-calibrator && conda run -n forge pytest tests/ -p no:pytest-blender -k "not blender_bridge" --tb=short -q</automated>
    Expected: all tests still pass. (No new tests for the hook branch —
    the hook isn't unit-tested today; the testImage14bit-equivalent
    UAT happens in Task 3.)

    Manual sanity check of the dialog-branch logic:
    ```bash
    grep -n -A2 "unsupported_bit_depth" flame/camera_match_hook.py
    ```
    Should show TWO matches: the return statement in `_read_source_frame`
    and the dialog branch in `_open_camera_match`.
  </verify>

  <done>
    - `_read_source_frame` returns `(None, "unsupported_bit_depth:{bd}", None)` on decode rejection
    - `_open_camera_match` branches dialog message based on the second-slot reason code
    - All other `_read_source_frame` callers (if any) unaffected on success path
    - Test suite still green
    - Docstring updated to document the failure-path overload
  </done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <name>Task 3: Install + HUMAN-UAT — preview cleanly on testImage / testImage10bit / testImage12bit / C002_260302_C005</name>
  <what-built>
    - `decode_raw_rgb_buffer` now decodes bd=10 (R210/DPX-style packed)
      and bd=12 (uint16 BRG /4095 normalized), in addition to bd=8/16/32.
    - `_read_source_frame` returns a reason code on decode rejection
      so the Camera Calibrator dialog can distinguish "media path
      broken" from "bit-depth not supported."
    - 437+ existing tests still pass; new tests cover the 10/12-bit
      paths and the unsupported-bit-depth coverage gap.
    - Bridge probe (recorded in SUMMARY.md) confirmed live decode on
      portofino against testImage / testImage10bit / testImage12bit /
      C002_260302_C005.
  </what-built>

  <how-to-verify>
    Executor first runs:
    ```bash
    cd /Users/cnoellert/Documents/GitHub/forge-calibrator
    ./install.sh --force
    ```
    This refreshes `/opt/Autodesk/shared/python/{forge_core,forge_flame,camera_match,tools/blender}/`
    and purges stale `__pycache__/` (including the sibling pycaches per
    `forge_install_pycache_gap.md`).

    Then the user does ONE of:
    - **(a) Restart Flame** (cleanest — picks up `flame/camera_match_hook.py` changes)
    - **(b) In-process reload via the snippet from install.sh** (faster but
      hook menu callbacks won't re-bind; the user will need to right-click
      a fresh node to pick up the new menu handler)

    Then on portofino's active batch, in this order:

    1. Right-click `testImage` clip → Camera Match → Open Camera Match.
       Expect: preview renders cleanly, no color cast, no error dialog. (bd=8 sanity check; should still work.)

    2. Right-click `testImage10bit` clip → Camera Match → Open Camera Match.
       Expect: preview renders cleanly, no color cast. (NEW — was the generic media-path error before this fix.)

    3. Right-click `testImage12bit` clip → Camera Match → Open Camera Match.
       Expect: preview renders cleanly, no color cast. (NEW — was the generic media-path error before this fix.)

    4. Right-click `C002_260302_C005` clip → Camera Match → Open Camera Match.
       Expect: preview renders cleanly, no color cast. (bd=16 ACEScg sanity check; should still work.)

    5. (If a 14-bit / 24-bit / otherwise-unsupported clip is available
       on the batch — A005 maybe?) Right-click → Open Camera Match.
       Expect: dialog says "Camera Calibrator does not yet support
       N-bit clips" — NOT the generic "media path is inaccessible"
       message. If no such clip is available, skip; the unit test
       (Test 7) locks the behavior.

    All four (or five) menu opens should succeed without color cast or
    spurious media-path errors. If ANY clip color-casts or fails, paste
    the stdout from Flame's terminal into the resume signal so we can
    diagnose (most likely: the bridge-probed 10-bit unpack scheme was
    wrong; revisit the candidates from Task 1).
  </how-to-verify>

  <on-pass>
    Move `.planning/todos/pending/2026-04-27-camera-calibrator-preview-channel-order-cast.md`
    to `.planning/todos/done/`. The bit-depth axis of that todo is now
    closed; the channel-order axis was closed by 260428-q8c. Mark
    "fixed_pending_visual_uat" → "closed" in the todo body before moving.

    Update PASSOFF (or write a brief note) recording: "32-bit float
    still untested live (no clip on batch); the assumed-BRG default
    will be validated opportunistically per PASSOFF entry (d)."
  </on-pass>

  <resume-signal>Type "approved" if all four (or five) clips preview cleanly. Otherwise paste the failing clip name + Flame terminal stdout.</resume-signal>
</task>

</tasks>

<verification>
End-to-end success requires all three:

1. `pytest tests/test_image_buffer.py -p no:pytest-blender` — all green, including the 7 new tests
2. Bridge probe (Task 1 verify) — `decode_raw_rgb_buffer` returns correctly-shaped arrays for bd=8/10/12/16 on the four portofino test clips
3. Human UAT (Task 3) — Camera Match menu opens cleanly on all four clips with no color cast and no spurious media-path error

If (1) passes but (2) fails on bd=10, the bridge-probed unpack scheme was wrong — revisit the four candidates in Task 1's probe section. If (2) passes but (3) shows a color cast on testImage10bit, the channel_order auto-default for bd=10 may be wrong; bridge-probe with the alternate perms (GBR / BRG) and pick the one that produces sane output.
</verification>

<success_criteria>
- Code: `decode_raw_rgb_buffer` supports bd=10 and bd=12 with verified unpack schemes
- Code: `_read_source_frame` returns a reason code on decode failure; `_open_camera_match` branches the dialog
- Tests: 437+ existing tests still pass; 7 new tests cover the 10/12-bit + unsupported-coverage paths
- Live: bridge probe and human UAT both confirm clean preview on portofino's testImage / testImage10bit / testImage12bit / C002_260302_C005
- Docs: docstring's empirical layout table updated to mark 10/12-bit as IMPLEMENTED with verification dates
- Install: `./install.sh --force` run; user told to restart Flame OR use the in-process reload
- Todo: channel-order-cast pending todo moves to `done/` after HUMAN-UAT clears
</success_criteria>

<output>
After completion, create `.planning/quick/260429-ebd-add-10-bit-12-bit-decode-support-to-deco/260429-ebd-SUMMARY.md` with:
- Bridge probe results from Task 1 (the 4 DWORD samples + the chosen unpack scheme)
- Final 10-bit unpack code snippet (so the next person doesn't have to re-derive)
- Test count delta (437 → 444 expected)
- Live UAT results per clip (4 or 5 entries, one per tested clip)
- Status of the moved-to-done channel-order-cast todo
- Notes on 32-bit float (still untested live; deferred per PASSOFF entry (d))
</output>
