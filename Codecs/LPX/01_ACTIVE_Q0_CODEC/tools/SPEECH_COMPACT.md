# Compact speech v5

Explicit build flags: `LPX4_ENABLE_SPEECH=1` and
`LPX4_ENABLE_SPEECH_COMPACT=1`, consistently on the core and its consumers.
The second flag defaults to zero and adds one state byte when enabled.
The C/AVR arithmetic selection and hardware Flash access remain independent.
There is no new assembly, floating-point decoder, trained dictionary or
large lookup table. v2/v3/v4 parsing and defaults remain available.

The first20 bytes retain `<4sBBHIHHHH`: `L4HY`, version5, profile flags,
8000Hz, exact1..64000 samples, pre Q14, bright Q14, frame320, block160.
Profile flags are4 or6, optionally OR128 to enable extra-pulse markers.
Bytes20..21 are the little-endian payload byte count; total file size must
equal22 plus that count. The payload is LSB first, without per-packet byte
alignment. The last byte is zero padded. Each packet represents320 samples.
The encoder writes a complete final packet even for a partial sample tail.

## Exact spectral coding

Reconstruct the same ten ordered scalar indices as v4 (5 bits for4k,
6 bits for6k). Prefixes below are listed in **read order**, not numeric MSB
notation:

- `0`: repeat the previous vector (invalid before initialization).
- `10`: unsigned gaps `g0=v0`, `gi=vi-v(i-1)-1`.
- `11`: zigzag temporal deltas `di=vi-oldi`, mapped to `2d` for nonnegative
  d and `-2d-1` otherwise (invalid before initialization).

Gaps use Rice k1/k2 for4k/6k; deltas use k0/k1. For quotient below8, emit
quotient zero bits, terminator1 and k remainder bits. Otherwise emit eight
zero bits and the complete unsigned value, without a terminator: width5/6
for gaps and6/7 for deltas. Each unary loop is bounded by8. Reconstructed
indices must be in range and strictly ordered. The encoder chooses the
least expensive legal mode for each packet. No coefficient changes occur.

The original v4 LSF-to-LPC interpolation and all synthesis are retained.
The6 reserved bits of v4 profile6 are omitted.

## Parameters and base excitation

After the spectrum, each of two halves contains the unchanged15-bit
scale/lag/gain fields:5,7,3 bits with the same reconstruction as v4. Its
four40-sample chunks follow immediately. For4k, each chunk stores the two
original position/sign pairs (4+1 bits each). For6k, store `p0+20*p1` in
9 bits, then two signed4 amplitudes. Values400..511 are invalid. The two
positions are0..19; the second belongs to the second20-sample subframe.

MCU division by20 uses the exact bounded identity
`second=((uint16_t)(uint8_t)(pair>>2)*205u)>>10` for pair0..399. This is
ordinary portable C; all400 cases are tested against host division/modulo.

## Optional extra innovations

When header bit128 is set, each40-sample chunk additionally has a presence
bit, followed when present by position6 and signed amplitude4 (-8..7).
Position0..39 is legal,40..63 invalid. The added pulse is sorted with the
two base pulses. On a collision, sum amplitudes before the existing final
q saturation; at most three distinct pulses are stored in the old sparse
arrays. Present extras cost10 bits beyond the presence markers. When the
global bit is absent there are no markers and plain repacking is field-exact
and PCM/PWM-exact to v4. Optional extras deliberately change audio.

## Validation and quality scope

The native decoder rejects truncated declared payloads. At an exact final
320-sample boundary, it also rejects unread trailing bytes and nonzero
padding bits. For partial sample tails it stops at the requested count,
so the remaining declared payload is not fully validated; Python `unpack`
validates the whole packet and its zero padding. There is no CRC and no
claim of detecting every syntactically valid corruption. Restart needs a
fresh header/zero state; arbitrary state-free packet seeking is not provided.

`speech_compact.py` performs pure repacking; `refine_speech_v4.py` searches
existing energy/pitch/base pulses with a longer horizon and fixed spectra;
`enhance_speech_compact.py` spends some saved bits on extra pulses, freezing
all base fields. Accepted edits improve full-reference SSE without reducing
full-reference STOI. These are bounded searches, not global optima or human
listening scores. Report exact file sizes rather than assuming fixed bitrate.
The new parser's Flash/SRAM/timing costs must be included when deciding
whether smaller audio files also reduce the total firmware footprint.

All source audio, caches and generated WAVs remain in ignored build trees.
See `../../SPEECH_COMPACT_PLAN_RU.md` and the compact-study research report.
