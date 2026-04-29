"""
Unit tests for forge_core.image.buffer — the pure pixel-transform helpers
extracted from the hook's _read_source_frame.

The important assertions:
    - decode_raw_rgb_buffer flips vertically AND applies the bit-depth-keyed
      channel permutation when both flags are set (Wiretap defaults).
      Flipping ALONE or permuting alone must NOT accidentally do both.
    - Header-stripping works via tail-slicing regardless of header length.
    - apply_ocio_or_passthrough produces identical uint8 output whether
      processor is None or raises — both fall back to clip+quantise.
    - decode_image_container rejects bytes that don't start with a known
      magic signature (returns None), instead of delegating to cv2 and
      eating arbitrary data.

No Flame, no PyOpenColorIO — these tests can run in any environment with
numpy + opencv-python. They form the contract forge_flame.wiretap relies on.
"""

import os
import sys
import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from forge_core.image.buffer import (
    sniff_container,
    decode_image_container,
    decode_raw_rgb_buffer,
    apply_ocio_or_passthrough,
)


# =============================================================================
# Raw buffer decode
# =============================================================================


class TestDecodeRawBuffer:
    """decode_raw_rgb_buffer: strip header, reshape, flip, permute channels."""

    def _make_buffer(self, w, h, header_bytes=0):
        """Build a deterministic GBR buffer where each pixel encodes its
        (row, col) position so flips and channel swaps are visible by eye.
        Channel 0 (G in source, swaps to R) = col * 2
        Channel 1 (B in source, swaps to G) = row * 2 + 1
        Channel 2 (R in source, swaps to B) = col + row + 100
        """
        arr = np.zeros((h, w, 3), dtype=np.uint8)
        for y in range(h):
            for x in range(w):
                arr[y, x, 0] = (x * 2) % 256
                arr[y, x, 1] = (y * 2 + 1) % 256
                arr[y, x, 2] = (x + y + 100) % 256
        header = bytes(header_bytes)  # zero-filled; we tail-slice past it
        return header + arr.tobytes(), arr

    def test_strips_leading_header_via_tail_slice(self):
        raw_with_hdr, _ = self._make_buffer(4, 3, header_bytes=16)
        raw_no_hdr,   _ = self._make_buffer(4, 3, header_bytes=0)
        # channel_order="RGB" + bottom_up=False: we only care that the payload
        # identified by tail-slicing is the same with or without header.
        a = decode_raw_rgb_buffer(raw_with_hdr, 4, 3, 8, channel_order="RGB", bottom_up=False)
        b = decode_raw_rgb_buffer(raw_no_hdr,   4, 3, 8, channel_order="RGB", bottom_up=False)
        np.testing.assert_array_equal(a, b)

    def test_no_transforms_preserves_layout(self):
        raw, src = self._make_buffer(5, 4, header_bytes=16)
        out = decode_raw_rgb_buffer(raw, 5, 4, 8, channel_order="RGB", bottom_up=False)
        np.testing.assert_array_equal(out, src)

    def test_bottom_up_flip_only(self):
        raw, src = self._make_buffer(5, 4, header_bytes=16)
        out = decode_raw_rgb_buffer(raw, 5, 4, 8, channel_order="RGB", bottom_up=True)
        np.testing.assert_array_equal(out, src[::-1])

    def test_gbr_swap_only(self):
        raw, src = self._make_buffer(5, 4, header_bytes=16)
        out = decode_raw_rgb_buffer(raw, 5, 4, 8, channel_order="GBR", bottom_up=False)
        # GBR → RGB means take source channels [2, 0, 1] into [0, 1, 2].
        expected = src[..., [2, 0, 1]]
        np.testing.assert_array_equal(out, expected)

    def test_wiretap_default_uint8_flips_and_gbr_swaps(self):
        """Both flags ON is the Wiretap default for uint8. Verifies the
        combined operation does both transforms correctly, not one or the
        other. uint8 still auto-resolves to GBR via _DEFAULT_CHANNEL_ORDER."""
        raw, src = self._make_buffer(5, 4, header_bytes=16)
        out = decode_raw_rgb_buffer(raw, 5, 4, 8)  # defaults: bottom_up=True, channel_order=None→GBR
        expected = src[::-1][..., [2, 0, 1]]
        np.testing.assert_array_equal(out, expected)

    def test_rejects_buffer_too_small(self):
        tiny = b"\x00" * 10
        assert decode_raw_rgb_buffer(tiny, 100, 100, 8) is None

    def test_unknown_bit_depth_returns_none(self):
        # bd=12 is now supported (260429-ebd); bd=14 stands in as the
        # "unmapped depth" coverage gap so the unsupported-bit-depth dialog
        # branch in flame/camera_match_hook.py:_open_camera_match has a
        # corresponding decoder return-None path that can be exercised.
        assert decode_raw_rgb_buffer(b"\x00" * 1000, 4, 4, bit_depth=14) is None

    def test_float32_bit_depth(self):
        h, w = 3, 4
        src = np.random.rand(h, w, 3).astype(np.float32)
        raw = b"\x00" * 16 + src.tobytes()
        out = decode_raw_rgb_buffer(raw, w, h, 32, channel_order="RGB", bottom_up=False)
        assert out.dtype == np.float32
        np.testing.assert_allclose(out, src)

    def test_float16_bit_depth(self):
        h, w = 3, 4
        src = (np.random.rand(h, w, 3) * 0.5).astype(np.float16)
        raw = b"\x00" * 16 + src.tobytes()
        out = decode_raw_rgb_buffer(raw, w, h, 16, channel_order="RGB", bottom_up=False)
        assert out.dtype == np.float16
        np.testing.assert_array_equal(out, src)

    def test_contiguous_after_transforms(self):
        """Qt's QImage requires a contiguous buffer; the decoder must ensure
        it, even after combined slicing + fancy indexing."""
        raw, _ = self._make_buffer(4, 3, header_bytes=0)
        out = decode_raw_rgb_buffer(raw, 4, 3, 8)
        assert out.flags["C_CONTIGUOUS"]

    def test_channel_order_auto_swaps_uint8_via_gbr(self):
        """channel_order=None auto-resolves to 'GBR' for 8-bit Wiretap dumps
        because they are tagged ``rgb_float_le`` but actually arrive in
        GBR order (transcoded MXF / proxy buffers). Auto-detect path."""
        raw, src = self._make_buffer(5, 4, header_bytes=16)
        out_auto = decode_raw_rgb_buffer(raw, 5, 4, 8, bottom_up=False)
        expected_swapped = src[..., [2, 0, 1]]
        np.testing.assert_array_equal(out_auto, expected_swapped)

    def test_channel_order_auto_brg_swaps_for_float16(self):
        """channel_order=None auto-resolves to 'BRG' for float16 because Wiretap's
        float buffers (EXR-sourced ACEScg) are laid out B,R,G in memory.
        Verified 2026-04-28 against C002_260302_C005 (4448x3096 float16) on portofino;
        BRG is the perm that produced the only natural-looking output through
        Flame Player's Rec.709/ACES SDR view."""
        h, w = 3, 4
        src = (np.random.rand(h, w, 3) * 0.5).astype(np.float16)
        raw = b"\x00" * 16 + src.tobytes()
        out_auto = decode_raw_rgb_buffer(raw, w, h, 16, bottom_up=False)
        expected = src[..., [1, 2, 0]]
        np.testing.assert_array_equal(out_auto, expected)

    def test_channel_order_auto_brg_swaps_for_float32(self):
        """Same as float16 — float32 auto-resolves to 'BRG' via
        _DEFAULT_CHANNEL_ORDER. Assumed-consistent with float16 layout
        (no 32-bit clip available to verify, but the Wiretap raw-buffer
        path is shared)."""
        h, w = 3, 4
        src = np.random.rand(h, w, 3).astype(np.float32)
        raw = b"\x00" * 16 + src.tobytes()
        out_auto = decode_raw_rgb_buffer(raw, w, h, 32, bottom_up=False)
        expected = src[..., [1, 2, 0]]
        np.testing.assert_allclose(out_auto, expected)

    def test_explicit_channel_order_overrides_auto(self):
        """Callers can force any of RGB/GBR/BRG explicitly. Auto-detect only
        fires when channel_order is None."""
        h, w = 3, 4
        src_f = (np.random.rand(h, w, 3) * 0.5).astype(np.float16)
        raw_f = b"\x00" * 16 + src_f.tobytes()
        # Force RGB on float (bypass the BRG default).
        out_rgb = decode_raw_rgb_buffer(raw_f, w, h, 16, channel_order="RGB", bottom_up=False)
        np.testing.assert_array_equal(out_rgb, src_f)
        # Force GBR on float (legacy buggy path; sanity-check the perm wiring).
        out_gbr = decode_raw_rgb_buffer(raw_f, w, h, 16, channel_order="GBR", bottom_up=False)
        np.testing.assert_array_equal(out_gbr, src_f[..., [2, 0, 1]])
        # Force RGB on uint8 (bypass the GBR default).
        raw8, src8 = self._make_buffer(5, 4, header_bytes=16)
        out_rgb_u8 = decode_raw_rgb_buffer(raw8, 5, 4, 8, channel_order="RGB", bottom_up=False)
        np.testing.assert_array_equal(out_rgb_u8, src8)
        # Force BRG on uint8 (sanity-check the BRG perm on integer dtype).
        out_brg_u8 = decode_raw_rgb_buffer(raw8, 5, 4, 8, channel_order="BRG", bottom_up=False)
        np.testing.assert_array_equal(out_brg_u8, src8[..., [1, 2, 0]])

    @pytest.mark.parametrize("bit_depth,expected_perm,dtype_factory", [
        (8,  [2, 0, 1], lambda h, w: np.random.randint(0, 256, (h, w, 3), dtype=np.uint8)),
        (16, [1, 2, 0], lambda h, w: (np.random.rand(h, w, 3) * 0.5).astype(np.float16)),
        (32, [1, 2, 0], lambda h, w: np.random.rand(h, w, 3).astype(np.float32)),
    ])
    def test_default_channel_order_per_bit_depth(self, bit_depth, expected_perm, dtype_factory):
        """_DEFAULT_CHANNEL_ORDER maps 8→GBR, 16→BRG, 32→BRG. Each call with
        channel_order=None must produce the matching permutation."""
        h, w = 3, 4
        src = dtype_factory(h, w)
        raw = b"\x00" * 16 + src.tobytes()
        out = decode_raw_rgb_buffer(raw, w, h, bit_depth, bottom_up=False)
        expected = src[..., expected_perm]
        if src.dtype.kind == "f":
            np.testing.assert_allclose(out, expected)
        else:
            np.testing.assert_array_equal(out, expected)

    # =========================================================================
    # 12-bit (uint16, BRG, /65535 normalize)
    # =========================================================================
    #
    # Wiretap delivers 12-bit clips as full-range uint16 (verified live on
    # portofino against testImage12bit, 5184x3456, 2026-04-29 — see
    # 260429-ebd-SUMMARY.md). The 12-bit source values are spread across the
    # full uint16 range (max observed 64508 ≈ 65535), NOT zero-padded into the
    # high 12 bits. So normalization is /65535.0, not /4095.0. This was a
    # deviation from the plan's "/4095" assumption — bridge probe disagreed
    # with the docstring guess and the data won.

    def _make_buffer_12bit(self, w, h, header_bytes=0):
        """Build a deterministic uint16 BRG buffer where each pixel encodes
        its (row, col) position scaled into the uint16 range. Source channel
        order in the raw buffer is B,R,G (matches Wiretap's 12-bit layout);
        decoder must permute back to R,G,B via [1, 2, 0]."""
        src = np.zeros((h, w, 3), dtype=np.uint16)
        for y in range(h):
            for x in range(w):
                # Distinct values per channel so flips/perms are visible.
                src[y, x, 0] = (x * 257) % 65536          # B in source layout
                src[y, x, 1] = (y * 513 + 1000) % 65536   # R in source layout
                src[y, x, 2] = (x * 113 + y * 199) % 65536  # G in source layout
        header = bytes(header_bytes)
        return header + src.tobytes(), src

    def test_bit_depth_12_round_trip(self):
        """bd=12: synth uint16 BRG buffer, decode with channel_order=None
        (auto-resolves to BRG), confirm float32 (h,w,3) array equal to
        (src/65535.0)[..., [1,2,0]] within 1e-6."""
        raw, src = self._make_buffer_12bit(5, 4, header_bytes=16)
        out = decode_raw_rgb_buffer(raw, 5, 4, 12, bottom_up=False)
        assert out is not None
        assert out.dtype == np.float32
        assert out.shape == (4, 5, 3)
        expected = (src.astype(np.float32) / 65535.0)[..., [1, 2, 0]]
        np.testing.assert_allclose(out, expected, atol=1e-6)

    def test_bit_depth_12_strips_header_via_tail_slice(self):
        """bd=12 header-strip via tail-slicing; result identical to no-header
        case. Mirrors test_strips_leading_header_via_tail_slice for uint8."""
        raw_with_hdr, _ = self._make_buffer_12bit(4, 3, header_bytes=16)
        raw_no_hdr,   _ = self._make_buffer_12bit(4, 3, header_bytes=0)
        a = decode_raw_rgb_buffer(raw_with_hdr, 4, 3, 12, bottom_up=False)
        b = decode_raw_rgb_buffer(raw_no_hdr,   4, 3, 12, bottom_up=False)
        np.testing.assert_array_equal(a, b)

    def test_bit_depth_12_explicit_channel_order_overrides_auto(self):
        """Force channel_order='RGB' on a 12-bit buffer to bypass the BRG
        auto-default. Output values still divided by 65535.0; just no perm."""
        raw, src = self._make_buffer_12bit(5, 4, header_bytes=16)
        out = decode_raw_rgb_buffer(raw, 5, 4, 12, channel_order="RGB", bottom_up=False)
        expected = src.astype(np.float32) / 65535.0
        np.testing.assert_allclose(out, expected, atol=1e-6)

    def test_bit_depth_12_does_not_clamp_out_of_range(self):
        """Sanity: the decoder normalizes by uint16 max (65535) but does NOT
        clip. A synthesized uint16=65535 normalizes to exactly 1.0; no
        downstream clamping happens in this layer (OCIO / passthrough does)."""
        # Single 1x1 pixel at uint16 max in all 3 channels.
        src = np.full((1, 1, 3), 65535, dtype=np.uint16)
        raw = b"\x00" * 16 + src.tobytes()
        out = decode_raw_rgb_buffer(raw, 1, 1, 12, channel_order="RGB", bottom_up=False)
        np.testing.assert_allclose(out, np.full((1, 1, 3), 1.0, dtype=np.float32))

    # =========================================================================
    # 10-bit (DPX method A, big-endian DWORD, R/G/B in bits 31-22 / 21-12 / 11-2)
    # =========================================================================
    #
    # Bridge-probed against testImage10bit on portofino (2026-04-29). Of the
    # four candidate unpack schemes (R210 BE, r210 LE, DPX method A BE, DPX
    # method A LE), only DPX method A BE produces spatially-coherent
    # gradients across all three channels (whole-frame stats: R∈[0,1007],
    # G∈[0,943], B∈[0,923] on warm-brown stair test image). The two LSBs of
    # each DWORD are padding. See 260429-ebd-SUMMARY.md for the 4-DWORD probe
    # data and full discrimination logic.

    def _pack_10bit_dpx_methodA_be(self, src_rgb):
        """Encode an (h, w, 3) array of 10-bit values [0, 1023] into a DPX
        method-A big-endian packed DWORD buffer. Inverse of the decoder.

        Per pixel: DWORD = (R << 22) | (G << 12) | (B << 2), high-byte first.
        """
        h, w, _ = src_rgb.shape
        r = src_rgb[..., 0].astype(np.uint32) & 0x3ff
        g = src_rgb[..., 1].astype(np.uint32) & 0x3ff
        b = src_rgb[..., 2].astype(np.uint32) & 0x3ff
        dwords = (r << 22) | (g << 12) | (b << 2)
        # Big-endian DWORD layout matches the bridge-probed scheme.
        return dwords.astype(">u4").reshape(h, w).tobytes()

    def _make_buffer_10bit(self, w, h, header_bytes=0):
        """Build a packed 10-bit buffer with each pixel encoding its position
        so flips/perms are detectable. Returns (raw_bytes, src_rgb_uint16)
        where src_rgb_uint16 contains the unpacked R,G,B 10-bit values for
        comparison against the decoder output."""
        src = np.zeros((h, w, 3), dtype=np.uint16)
        for y in range(h):
            for x in range(w):
                src[y, x, 0] = (x * 17 + y * 3) % 1024     # R
                src[y, x, 1] = (y * 13 + 100) % 1024       # G
                src[y, x, 2] = (x + y + 200) % 1024        # B
        payload = self._pack_10bit_dpx_methodA_be(src)
        header = bytes(header_bytes)
        return header + payload, src

    def test_bit_depth_10_round_trip(self):
        """bd=10: pack a known 10-bit RGB pattern using DPX method A BE,
        decode with bd=10, confirm float32 (h,w,3) equals (src/1023.0)
        within one 10-bit step (1/1023 ≈ 9.78e-4)."""
        raw, src = self._make_buffer_10bit(8, 6, header_bytes=16)
        out = decode_raw_rgb_buffer(raw, 8, 6, 10, bottom_up=False)
        assert out is not None
        assert out.dtype == np.float32
        assert out.shape == (6, 8, 3)
        expected = src.astype(np.float32) / 1023.0
        np.testing.assert_allclose(out, expected, atol=1e-3)

    def test_bit_depth_10_strips_header_via_tail_slice(self):
        """bd=10 header-strip via tail-slicing; result identical to no-header
        case. Wiretap's 10-bit raw buffer carries a leading ~16-byte header."""
        raw_with_hdr, _ = self._make_buffer_10bit(4, 3, header_bytes=16)
        raw_no_hdr,   _ = self._make_buffer_10bit(4, 3, header_bytes=0)
        a = decode_raw_rgb_buffer(raw_with_hdr, 4, 3, 10, bottom_up=False)
        b = decode_raw_rgb_buffer(raw_no_hdr,   4, 3, 10, bottom_up=False)
        np.testing.assert_array_equal(a, b)

    # =========================================================================
    # Coverage gap: unmapped bit_depth → None (locks the unsupported-bit-depth
    # dialog branch in _open_camera_match's testability)
    # =========================================================================

    def test_bit_depth_14_returns_none(self):
        """bd=14 is unmapped; decoder must return None so the hook can show
        the 'unsupported_bit_depth' dialog branch (vs the generic media-path
        error). Locks the explicit fall-through behavior even though it would
        also be implied by the absence of bd=14 in _BIT_DEPTH_TO_DTYPE — we
        want a regression-protected assertion."""
        # Buffer is large enough that an over-eager dispatch would NOT trip on
        # the size check; the rejection must come from the bit-depth lookup.
        big = b"\x00" * (4 * 4 * 6 + 16)
        assert decode_raw_rgb_buffer(big, 4, 4, bit_depth=14) is None


# =============================================================================
# Container sniff + decode
# =============================================================================


class TestSniffContainer:
    def test_png(self):
        assert sniff_container(b"\x89PNG\r\n\x1a\n" + b"rest") == "png"

    def test_jpg(self):
        assert sniff_container(b"\xff\xd8\xff\xe0" + b"rest") == "jpg"

    def test_tiff_little_endian(self):
        assert sniff_container(b"II*\x00" + b"rest") == "tiff-le"

    def test_tiff_big_endian(self):
        assert sniff_container(b"MM\x00*" + b"rest") == "tiff-be"

    def test_exr(self):
        assert sniff_container(b"\x76\x2f\x31\x01" + b"rest") == "exr"

    def test_dpx_big_endian(self):
        assert sniff_container(b"SDPX" + b"rest") == "dpx-be"

    def test_unknown_returns_none(self):
        assert sniff_container(b"\x00" * 16) is None
        assert sniff_container(b"random junk") is None

    def test_empty_returns_none(self):
        assert sniff_container(b"") is None


class TestDecodeImageContainer:
    def test_rejects_non_container_bytes(self):
        """Must NOT call cv2.imdecode on unrecognised bytes — a raw Wiretap
        buffer with 16-byte header of zeros would pass cv2's sanity checks
        and return garbage. The magic-byte gate is what prevents that."""
        assert decode_image_container(b"\x00" * 1000) is None

    def test_decodes_png_via_cv2(self):
        """Round-trip a synthesized PNG to confirm the container path works."""
        import cv2
        src = np.random.randint(0, 256, (8, 12, 3), dtype=np.uint8)
        _, encoded = cv2.imencode(".png", cv2.cvtColor(src, cv2.COLOR_RGB2BGR))
        out = decode_image_container(encoded.tobytes())
        assert out is not None
        assert out.dtype == np.uint8
        assert out.shape == src.shape
        np.testing.assert_array_equal(out, src)


# =============================================================================
# Tonemap: OCIO applyRGB vs passthrough
# =============================================================================


class _FakeProcessor:
    """Stand-in for an OCIO CPU processor. Multiplies in place so we can
    see that applyRGB was called without pulling PyOpenColorIO in."""
    def __init__(self, scale=0.5, raise_exc=None):
        self.scale = scale
        self.raise_exc = raise_exc
        self.calls = 0

    def applyRGB(self, arr):
        self.calls += 1
        if self.raise_exc is not None:
            raise self.raise_exc
        arr *= self.scale


class TestApplyOcioOrPassthrough:
    def test_none_processor_clip_and_quantise(self):
        src = np.array([[[0.0, 0.5, 1.5]]], dtype=np.float32)
        out = apply_ocio_or_passthrough(src, processor=None)
        assert out.dtype == np.uint8
        # 0 → 0, 0.5 → 127, 1.5 clipped → 255
        np.testing.assert_array_equal(out[0, 0], [0, 127, 255])

    def test_processor_is_called_and_output_quantised(self):
        src = np.full((2, 2, 3), 1.0, dtype=np.float32)
        proc = _FakeProcessor(scale=0.5)
        out = apply_ocio_or_passthrough(src, processor=proc)
        assert proc.calls == 1
        # All pixels 1.0 * 0.5 = 0.5 → 127
        assert np.all(out == 127)

    def test_processor_exception_falls_back_to_passthrough(self):
        """If OCIO raises (e.g. the processor was set up wrong), the preview
        should still render using a clip+quantise path — the user gets a
        slightly-wrong preview instead of a crash."""
        src = np.full((2, 2, 3), 0.5, dtype=np.float32)
        proc = _FakeProcessor(raise_exc=RuntimeError("deliberate"))
        out = apply_ocio_or_passthrough(src, processor=proc)
        assert proc.calls == 1
        assert np.all(out == 127)  # 0.5 * 255 = 127.5 → 127

    def test_float16_input_accepted(self):
        src = np.full((2, 2, 3), 0.5, dtype=np.float16)
        out = apply_ocio_or_passthrough(src, processor=None)
        assert out.dtype == np.uint8
        assert np.all(out == 127)

    def test_output_is_contiguous(self):
        src = np.full((4, 5, 3), 0.25, dtype=np.float32)
        out = apply_ocio_or_passthrough(src, processor=None)
        assert out.flags["C_CONTIGUOUS"]
