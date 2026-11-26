# LG1 experimental codec contract

LG1 is a new experimental codec with fixed order 10. It is not a valid production
LPX/V9 stream. All payload fields are least-significant-bit first, including
signed two's-complement fields and Exp-Golomb suffixes. No byte alignment
is inserted between fields. Unused high bits of the final byte must be zero.

## Header

The 13-byte header uses the same field offsets as bounded LPX/V9:

| Offset | Bytes | Meaning |
| --- | ---: | --- |
| 0 | 2 | ASCII `LG` |
| 2 | 1 | Profile 4 or 6, optionally OR 128 for extra-pulse presence fields |
| 3 | 2 | Little-endian sample rate; must be 8000 |
| 5 | 2 | Little-endian sample count, 1..64000 |
| 7 | 2 | Little-endian pre-emphasis Q14, 0..16384 |
| 9 | 2 | Little-endian brightness Q14, 0..11469 |
| 11 | 2 | Little-endian payload byte count; file size must be 13 plus this count |

The decoder resets output and excitation history at `begin()`. A source is
either a direct memory pointer (PROGMEM on actual AVR) or a bounded borrowed
byte callback. Hardware access selection depends on the compiler's real
`__AVR__` macro and is independent of the arithmetic backend.

## Frame and subframe schedule

A frame contains 320 samples, two 160-sample parameter blocks, eight 40-sample
pulse packets and sixteen 20-sample coefficient subframes. Only packets or
commands whose starting sample is played are stored. A stored 40-sample packet
always contains both main pulses, including an unplayed second pulse in a
partial final packet.

At frame sample 0, read the one-bit spectrum flag. `0` repeats the previous
decoded end anchor for the whole frame. The first frame cannot repeat.
Flag `1` starts a changed frame:

- In the first frame, decode one end anchor relative to zero and use it
  constantly for the whole frame. No anchor is stored at sample 80.
- In a later changed frame, decode a midpoint anchor relative to the previous
  decoded end. At sample 80, decode the end anchor relative to that decoded
  midpoint. The second anchor is omitted if sample 80 is not played.

During each 80-sample transition, subframes use
`a = base + (target-base)*t/8`, with `t=1,3,5,7` and signed division truncating
toward zero. At sample 80, midpoint becomes the new base. At sample 160, the
end becomes the exact coefficient vector and is constant for the rest of the
frame. Filter output history is preserved at all boundaries.

At coincident boundaries, fields occur in this strict order:

1. Frame spectrum flag and first anchor, if sample 0.
2. Second coefficient anchor, if sample 80 of a later changed frame.
3. Scale command/materialization, then pitch command/materialization, if a
   played 160-sample block starts.
4. Main pulse packet and optional extra pulse, if a played 40-sample packet starts.

## Anchor vector

Read one `changed` bit. If zero, `target=base`, with no other fields. Otherwise
read a two-bit grouping plan:

| Plan | Groups |
| --- | --- |
| 0 | One group of 10 |
| 1 | Two groups of 5 |
| 2 | Five groups of 2 |
| 3 | Custom contiguous groups; each starts with four-bit `length-1` |

Groups cover coefficients in order 0..9, exactly once. A custom group must not
overshoot ten coefficients. Immediately after each custom length, or for each
fixed-plan group, read its three-bit width code:

| Code | Representation |
| --- | --- |
| 0/1/2/3/4 | Signed 4/6/8/10/12-bit delta mantissas |
| 5 | Raw signed 16-bit absolute target coefficients |
| 6 | Zero deltas: preserve base coefficients in this group |
| 7 | Invalid/reserved |

For a mantissa group, read one four-bit exponent `e`, then one signed mantissa
per coefficient. Reconstruct each target as `base + mantissa*2^e` using signed 32-bit
arithmetic. Raw groups have no exponent. All reconstructed and raw coefficients
must be in [-32767,32767], matching the production arithmetic bounds. There is
no implied clipping, permutation, floating-point operation or exponent for a
zero group. Illegal ranges are decoder errors.

## Run duration

For positive run length `N`, write `z=floor(log2(N))` zero bits, one bit 1, then
`N-2^z` in `z` LSB-first bits. Thus `N=1` is one bit 1. The prefix must contain
at most eight zeros. A run must be 1..400 and must not exceed the number of
played 160-sample blocks remaining, including the current block.

Scale and pitch have independent run state. A command is read only when its
own previous run expires. Materialization still happens at every 160-sample
block. Spectrum repeats do not suspend either trajectory.

## Scale commands

Read a two-bit command when scale run state is empty:

| Command | Fields and behavior |
| --- | --- |
| 0 | Literal five-bit original LPX scale index; one block |
| 1 | Five-bit original scale index, then run duration; constant exact step |
| 2 | Five-bit original start scale, signed 12-bit log2-Q8 slope, then duration |
| 3 | Duration, then inline five-bit original scale index at every block, including the first |

Original scale indices map exactly to:

```text
0,0,0,0,0,0,1,1,1,1,2,3,4,6,8,12,16,23,33,46,66,93,131,185,
262,371,524,741,1049,1483,2097,2966
```

Command 2 models **true log2(step)**, not the logarithmic scale-index number.
Its initial log2-Q8 values are:

```text
-1,-1,-1,-1,-1,-1,0,0,0,0,256,406,512,662,768,918,1024,1158,
1291,1414,1547,1674,1801,1928,2057,2185,2313,2441,2569,2697,2825,2953
```

Negative initial values forbid a log run starting at a zero step. At block
`i`, `q=initial+i*slope` must remain 0..3071. Convert q without runtime floats:

```text
LUT = [4096,4277,4467,4664,4871,5087,5312,5547,5793,
       6049,6317,6597,6889,7194,7512,7845,8192]
node = (q & 255) >> 4
base = LUT[node] + (((LUT[node+1]-LUT[node])*(q & 15)+8) >> 4)
step = ((base << (q >> 8)) + 2048) >> 12
```

The maximal intermediate fits unsigned 32-bit arithmetic. A log curve may approximate the
original step, including at its first block. Exact storage uses literal,
constant or raw-run commands. Step zero does not skip excitation updates,
filter history or the filter's remaining output tail.

## Pitch commands

A literal pitch is a three-bit half-gain `g` (actual gain `2*g`), followed by
seven-bit `lag-18` only when gain is nonzero. A zero-gain literal uses lag 18.
Read a two-bit command when pitch run state is empty:

| Command | Fields and behavior |
| --- | --- |
| 0 | Literal pitch; one block |
| 1 | Literal pitch, then duration; constant gain/lag |
| 2 | Nonzero three-bit half-gain, seven-bit start `lag-18`, signed 8-bit lag slope, duration |
| 3 | Duration, then inline literal pitch at every block, including the first |

Pitch command 2 retains the same nonzero gain and uses `lag=start+i*slope`;
every lag must remain 18..145. This is linear **lag**, not linear Hertz.

## Excitation and output

Main pulses and optional extra pulses retain the production P4/P6 bit widths.
P4 has two four-bit position codes and sign bits per 40 samples, mapping
position code `c` to `c+(c+2)/4`, amplitudes -8/+8. P6 writes four low position bits,
a five-bit high pair index, then two signed 4-bit amplitudes. Its high pair index must be
less than 25 and maps as in current V9. When header bit 128 is set, every stored
packet also has one extra-presence bit; a present extra has a six-bit position (0..39)
and a signed four-bit amplitude. No main/extra field is skipped solely because a value
is zero.

Pitch prediction, saturation, Q12 synthesis, deemphasis, brightness and PWM
rounding use the existing LPX arithmetic contract. Portable C is the default.
`LPX4_ENABLE_ASM=1` selects existing helpers only when compiler architecture
macros identify a supported AVR5/AVR25 target. Actual AVR memory access remains
PROGMEM even when the arithmetic C fallback is explicitly selected.

The complete stream rejects bad metadata, out-of-bounds/callback reads,
reserved groups, coefficient overflow, illegal runs/curves, invalid pulse
positions, trailing payload bytes and nonzero final padding. There is no heap
allocation or floating-point calculation in the decoder. These format and
memory bounds do not by themselves prove spectral stability or real-time
playback; the encoder and interrupt-active whole-player tests provide that
separate evidence.
