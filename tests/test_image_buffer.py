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
        assert decode_raw_rgb_buffer(b"\x00" * 1000, 4, 4, bit_depth=12) is None

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
