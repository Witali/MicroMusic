# Structured voiced noise: PC probe

`q3_shaped_noise.py` keeps the existing16-tap Q3/T1 source and adds one of
three deterministic noise colors, selected per source row. This is a PC
experiment; no AVR implementation, code-size or timing claim is made.

The64-byte encoded book stores coefficient+8 in bits0..3 and a uniform row
noise mode in bits4..5:0 off,1 low-pass,2 high-pass,3 white. Bits6..7 are zero.
`encode_book`, `decode_book`, `pack_book`, `unpack_book` validate the format;
the model schema is `hq4-q3-shaped-noise-v1`. Model `pulsebook` contains the
encoded4x16 bytes, rather than signed coefficients. Frames are unchanged.

Flagged voiced samples advance the old LFSR, including at gain0 or1. With
`cur=±(gain>>1)` and a single signed `prev` initialized to0, the added term is
`(cur+prev)>>1`, `(cur-prev)>>1` or `cur`. Then `prev=cur`. Off voiced samples
freeze both LFSR and `prev`. Unvoiced samples keep the old±gain LFSR source
and freeze `prev`. Frame changes do not reset this state. The pulse term is
added before the unchanged byte Q3 lattice and output tilt. All-off books
preserve exact PCM and every arithmetic guard count in both rounding modes.

`tools/probe-q3-shaped-noise.py` screens all256 row-mode combinations for
each seed and each quantized gain scale0.8 and1.0. Each has its own all-off
control at the same conservatively capped600-byte speech stream. Only a
strict paired STOI increase **and** spectral-loss decrease enables at most
1500 joint frame/book/mode proposals. The source reference is never warped,
cropped, normalized or DC corrected. Finalists and controls get eSTOI and
matched/raw-level strongest10-partial diagnostics in addition to the search
metrics. Data size alone does not establish a complete1KB firmware fit.

Tests: `tools/test-q3-shaped-noise.py` and
`tools/test-probe-q3-shaped-noise.py`.
